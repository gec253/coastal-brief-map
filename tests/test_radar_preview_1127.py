"""Private Radar Viewer Chart Helm preview (Ed t512u / t514u / t515u). Public /radar stays on production assets."""
from __future__ import annotations

import json
import os
import subprocess
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
KEY = "a" * 32
BASELINE = "d0b0953000e8c6da95e27a25f1216019b1065e7c"
FROZEN = (
    "wind.html", "wind-viewer.js", "wind.css", "wind-lab.js", "wind-coast.js",
    "data/wind-labels.json",
    "wind-coast/lo.json", "wind-coast/hi.json",
    "radar.html", "radar-viewer.js", "radar.css", "radar-player.js",
)
MM_PER_IN = 25.4
PROVIDER_BINS_MM = (0.1, 0.5, 1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 64.0)


def _cookie():
    import server
    return "%s=%s" % (server.PREVIEW_COOKIE, server._preview_cookie_value(KEY))


# Display ticks on the colour bar (Ed t515u). Colour mapping still uses exact from_mm_h.
INH_TICK = {
    0.1: "<0.01",
    0.5: "0.02",
    1.0: "0.04",
    2.0: "0.08",
    4.0: "0.15",
    8.0: "0.3",
    16.0: "0.6",
    32.0: "1.25",
    64.0: "2.5+",
}


def format_in_h(mm):
    """Match preview/radar/viewer.js formatInh display ticks."""
    return INH_TICK[mm]


def format_in_h_exact(mm):
    """Match preview/radar/viewer.js formatInhExact: 4 decimals below 1 in/h, 3 at or above."""
    inches = mm / MM_PER_IN
    return ("%.4f" if inches < 1 else "%.3f") % inches


def classify_view(available=True, loading=False, fail=0, opaque=False):
    if not available:
        return "unavailable"
    if loading:
        return "loading"
    if fail > 0:
        return "incomplete"
    if not opaque:
        return "clear"
    return "precip"


def classify_coverage(available=True, stale=False, loading=False, fail=0, opaque=False):
    if not available:
        return "unavailable"
    if stale:
        return "stale"
    return classify_view(available, loading, fail, opaque)


class RadarUnitsAndCoverage(unittest.TestCase):
    def test_inch_conversion_preserves_provider_bin_edges(self):
        self.assertEqual(MM_PER_IN, 25.4)
        expected_tick = INH_TICK
        expected_exact = {
            0.1: "0.0039",
            0.5: "0.0197",
            1.0: "0.0394",
            2.0: "0.0787",
            4.0: "0.1575",
            8.0: "0.3150",
            16.0: "0.6299",
            32.0: "1.260",
            64.0: "2.520",
        }
        for mm in PROVIDER_BINS_MM:
            self.assertEqual(format_in_h(mm), expected_tick[mm], mm)
            exact = format_in_h_exact(mm)
            self.assertEqual(exact, expected_exact[mm], mm)
            # Exact About-panel values stay on the true bin edge (inches = mm / 25.4).
            inches = mm / MM_PER_IN
            # Four decimals below 1 in/h, three at or above: stay within half a unit in the last place.
            self.assertLess(abs(float(exact) - inches), 0.00005 if inches < 1 else 0.0005, mm)
        # Display rounding is labels only; neighbouring bin ticks must stay distinct.
        ticks = [format_in_h(mm) for mm in PROVIDER_BINS_MM]
        self.assertEqual(len(ticks), len(set(ticks)))
        js = (ROOT / "preview" / "radar" / "viewer.js").read_text()
        self.assertIn("MM_PER_IN = 25.4", js)
        self.assertIn('0.1: "<0.01"', js)
        self.assertIn('64: "2.5+"', js)
        self.assertIn("function formatInhExact", js)
        self.assertIn("formatInh(v)", js)
        self.assertIn("formatInhExact(mm)", js)
        self.assertIn("Legend labels are rounded for reading", js)
        html = (ROOT / "preview" / "radar" / "index.html").read_text()
        self.assertIn("Precip rate <b>in/h</b>", html)
        self.assertIn('aria-label="Observed precipitation rate colour scale, inches per hour"', html)
        self.assertIn("id=\"r-bins\"", html)
        self.assertIn("millimetre-per-hour", html)
        self.assertIn("Legend labels are rounded for reading", html)
        self.assertIn("Exact millimetre-per-hour and inch-per-hour values are listed below", html)
        self.assertNotIn("Precip rate <b>mm/h</b>", html)
        self.assertNotIn("Reflectivity <b>dBZ</b>", html)
        self.assertIn("not an NWS reflectivity (dBZ) scale", html)

    def test_coverage_states_never_treat_missing_as_clear(self):
        self.assertEqual(classify_view(opaque=False, fail=0, loading=False), "clear")
        self.assertEqual(classify_view(opaque=True, fail=0, loading=False), "precip")
        self.assertEqual(classify_view(opaque=False, fail=1, loading=False), "incomplete")
        self.assertEqual(classify_view(opaque=True, fail=2, loading=False), "incomplete")
        self.assertEqual(classify_view(opaque=False, fail=0, loading=True), "loading")
        self.assertEqual(classify_coverage(available=False), "unavailable")
        self.assertEqual(classify_coverage(stale=True, opaque=False, fail=0), "stale")
        self.assertEqual(classify_coverage(stale=True, fail=1), "stale")
        self.assertNotEqual(classify_view(fail=1, opaque=False), "clear")
        self.assertNotEqual(classify_view(loading=True, opaque=False), "clear")
        js = (ROOT / "preview" / "radar" / "viewer.js").read_text()
        self.assertIn("function classifyCoverage", js)
        self.assertIn("function classifyView", js)
        self.assertIn("Incomplete coverage. Missing tiles are not clear skies.", js)
        self.assertIn("No precipitation in view", js)
        self.assertIn("paintMissing", js)
        self.assertIn("STALE_MIN = 15", js)
        html = (ROOT / "preview" / "radar" / "index.html").read_text()
        self.assertIn("Missing data is uncertainty, never evidence of safety", html)
        self.assertIn("id=\"r-cover\"", html)
        self.assertIn("id=\"r-unavail\"", html)


class RadarPreviewLabels(unittest.TestCase):
    def setUp(self):
        self.data = json.loads((ROOT / "preview" / "radar" / "labels.json").read_text())
        self.places = self.data["places"]
        self.by_name = {}
        for p in self.places:
            self.by_name.setdefault(p["n"], []).append(p)

    def test_falls_lake_is_never_jordan_lake(self):
        falls = self.by_name["Falls Lake"]
        jordan = self.by_name["Jordan Lake"]
        self.assertEqual(len(falls), 1)
        self.assertEqual(len(jordan), 1)
        f, j = falls[0], jordan[0]
        self.assertEqual(f["s"], "gnis:999761")
        self.assertEqual(j["s"], "gnis:980401")
        self.assertAlmostEqual(f["la"], 36.01666667, places=5)
        self.assertAlmostEqual(f["lo"], -78.71666667, places=5)
        self.assertAlmostEqual(j["la"], 35.7080038, places=5)
        self.assertAlmostEqual(j["lo"], -79.0346229, places=5)
        self.assertGreater(abs(f["la"] - j["la"]), 0.2)
        self.assertGreater(abs(f["lo"] - j["lo"]), 0.2)
        self.assertIn("999761", self.data["sources"]["gnis:999761"])
        self.assertIn("This is not Jordan Lake", self.data["sources"]["gnis:999761"])
        self.assertIn("980401", self.data["sources"]["gnis:980401"])
        self.assertIn("not Falls Lake", self.data["sources"]["gnis:980401"])

    def test_gazetteer_has_verified_inland_places_and_cited_sources(self):
        names = {p["n"] for p in self.places}
        for n in (
            "Charlotte", "Raleigh", "Asheville", "Greensboro", "Murphy",
            "Fayetteville", "Durham", "Boone", "Lake Norman", "Fontana Lake",
            "Kerr Lake", "Harris Lake", "Tar River", "Yadkin River",
        ):
            self.assertIn(n, names, n)
        for p in self.places:
            self.assertIn(p["s"], self.data["sources"], p["n"])
            self.assertGreaterEqual(p["z1"], p["z0"])
            # All of NC plus a western buffer: no label should sit west of -86.5 or east of -74.
            self.assertGreater(p["lo"], -86.5, p["n"])
            self.assertLess(p["lo"], -74.0, p["n"])
        # Coastal originals were copied through, not dropped.
        self.assertIn("Cape Hatteras", names)
        self.assertIn("Wilmington", names)
        self.assertIn("data/wind-labels.json", self.data["note"])

    def test_wind_labels_file_is_not_used_or_modified(self):
        js = (ROOT / "preview" / "radar" / "viewer.js").read_text()
        self.assertIn("/radar/labels.json", js)
        self.assertNotIn("/wind/labels.json", js)
        self.assertNotIn("/preview/radar/labels.json", js)
        current = (ROOT / "data" / "wind-labels.json").read_bytes()
        baseline = subprocess.check_output(["git", "show", "%s:data/wind-labels.json" % BASELINE], cwd=ROOT)
        self.assertEqual(current, baseline)

    def test_neighboring_state_context_labels_are_verified_and_not_crowded(self):
        names = {p["n"] for p in self.places}
        # North Carolina Greenville stays; the South Carolina city is explicitly suffixed.
        self.assertIn("Greenville", names)
        self.assertIn("Greenville, SC", names)
        nc_g = self.by_name["Greenville"][0]
        sc_g = self.by_name["Greenville, SC"][0]
        self.assertEqual(nc_g["s"], "gnis:1023721")
        self.assertEqual(sc_g["s"], "gnis:1245842")
        self.assertGreater(nc_g["la"] - sc_g["la"], 0.5)
        expected = {
            "Knoxville, TN": ("gnis:1648562", 35.96166667, -83.92333333, 5),
            "Atlanta, GA": ("gnis:351615", 33.75444444, -84.38972222, 5),
            "Roanoke, VA": ("gnis:1498439", 37.27055556, -79.9425, 5),
            "Columbia, SC": ("gnis:1245051", 34.00055556, -81.04416667, 6),
            "Chattanooga, TN": ("gnis:1307240", 35.04555556, -85.26722222, 6),
            "Charleston, SC": ("gnis:1221516", 32.78333333, -79.93194444, 6),
            "Myrtle Beach, SC": ("gnis:1249770", 33.71, -78.88361111, 6.5),
            "Greenville, SC": ("gnis:1245842", 34.84444444, -82.38555556, 6.5),
            "Johnson City, TN": ("gnis:1328579", 36.31344444, -82.35347222, 7),
            "Danville, VA": ("gnis:1498421", 36.587238, -79.404404, 7),
            "Florence, SC": ("gnis:1222461", 34.18388889, -79.77416667, 7),
        }
        for n, (src, la, lo, z0) in expected.items():
            self.assertEqual(len(self.by_name[n]), 1, n)
            p = self.by_name[n][0]
            self.assertEqual(p["s"], src, n)
            self.assertAlmostEqual(p["la"], la, places=5, msg=n)
            self.assertAlmostEqual(p["lo"], lo, places=5, msg=n)
            self.assertEqual(p["z0"], z0, n)
            self.assertIn(src, self.data["sources"])
            self.assertIn(src.split(":")[1], self.data["sources"][src])
        # Mid-zoom neighbors should not appear at the statewide default zoom.
        self.assertGreaterEqual(sc_g["z0"], 6.5)
        self.assertGreaterEqual(self.by_name["Johnson City, TN"][0]["z0"], 7)
        # Atlanta is low-zoom context only, so it drops once the map is in on North Carolina.
        self.assertLessEqual(self.by_name["Atlanta, GA"][0]["z1"], 7.5)
        self.assertIn("neighboring-state", self.data["note"])


class RadarPreview1127(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import server
        cls.server = server
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.base = "http://127.0.0.1:%d" % cls.httpd.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def _get(self, path, cookie=None):
        req = urllib.request.Request(self.base + path, headers={"Cookie": cookie} if cookie else {})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status, dict(r.headers), r.read()
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers), e.read()

    def test_unauthenticated_preview_is_404(self):
        with mock.patch.dict(os.environ, {"PREVIEW_KEY": KEY}):
            for p in ("/preview/radar", "/preview/radar/viewer.js", "/preview/radar/radar.css", "/preview/radar/labels.json",
                       "/preview/radar/coast-lo.json", "/preview/radar/coast-hi.json", "/preview/radar/borders.json"):
                st, _, body = self._get(p)
                self.assertEqual(st, 404, p)
                self.assertIn(b"not found", body.lower())
            self.assertEqual(self._get("/preview/radar", "cb_preview=nope")[0], 404)

    def test_authenticated_preview_serves_chart_helm_assets(self):
        ck = _cookie()
        with mock.patch.dict(os.environ, {"PREVIEW_KEY": KEY}):
            st, h, body = self._get("/preview/radar", ck)
            self.assertEqual(st, 200)
            cache = (h.get("Cache-Control") or h.get("cache-control") or "").lower()
            self.assertIn("no-store", cache)
            robots = (h.get("X-Robots-Tag") or h.get("x-robots-tag") or "").lower()
            self.assertIn("noindex", robots)
            self.assertIn(b'content="noindex, nofollow"', body)
            self.assertIn(b'href="/radar/app.css"', body)
            self.assertIn(b'src="/radar/app.js"', body)
            self.assertIn(b'src="/radar/player.js"', body)
            self.assertIn(b'href="/wind.css"', body)
            self.assertIn(b'src="/wind/coast.js"', body)
            self.assertIn(b"/branding/favicon.svg", body)
            self.assertIn(b'id="r-center"', body)
            self.assertIn(b'id="r-locate"', body)
            self.assertIn(b'id="r-labels"', body)
            self.assertIn(b"Precip rate", body)
            self.assertIn(b"in/h", body)
            self.assertIn(b"mm/h", body)
            self.assertNotIn(b"Reflectivity <b>dBZ</b>", body)
            self.assertIn(b"not an NWS reflectivity (dBZ) scale", body)
            self.assertIn(b"Coast", body)
            self.assertIn(b">Me<", body)
            self.assertNotIn(b'href="/radar.css"', body)
            self.assertNotIn(b'src="/radar/viewer.js"', body)
            self.assertNotIn(b"dashed amber frame", body)
            self.assertIn(b'id="r-cover"', body)

            st, h, css = self._get("/preview/radar/radar.css", ck)
            self.assertEqual(st, 200)
            self.assertIn("text/css", h.get("Content-Type") or h.get("content-type") or "")
            self.assertIn("no-store", (h.get("Cache-Control") or h.get("cache-control") or "").lower())
            self.assertEqual(css, (ROOT / "preview" / "radar" / "radar.css").read_bytes())
            self.assertNotIn(b"html[data-frame=\"fc\"] .rv-stage::after", css)
            self.assertNotIn(b"border: 3px dashed var(--fc)", css)

            st, h, js = self._get("/preview/radar/viewer.js", ck)
            self.assertEqual(st, 200)
            self.assertIn("javascript", h.get("Content-Type") or h.get("content-type") or "")
            self.assertEqual(js, (ROOT / "preview" / "radar" / "viewer.js").read_bytes())
            self.assertIn(b"/radar/labels.json", js)
            self.assertNotIn(b"/wind/labels.json", js)
            self.assertIn(b"setForecast", js)
            self.assertIn(b"keepBuffer: 1", js)
            self.assertNotIn(b"if (shown && shown !== layers.get(f.time)) { shown.setOpacity(0); shown = null; }", js)

            st, h, lab = self._get("/preview/radar/labels.json", ck)
            self.assertEqual(st, 200)
            self.assertIn("json", (h.get("Content-Type") or h.get("content-type") or "").lower())
            self.assertEqual(lab, (ROOT / "preview" / "radar" / "labels.json").read_bytes())
            self.assertIn(b"Falls Lake", lab)
            self.assertIn(b"Jordan Lake", lab)

            st, h, clo = self._get("/preview/radar/coast-lo.json", ck)
            self.assertEqual(st, 200)
            self.assertEqual(clo, (ROOT / "preview" / "radar" / "coast-lo.json").read_bytes())
            st, _, brd = self._get("/preview/radar/borders.json", ck)
            self.assertEqual(st, 200)
            self.assertEqual(brd, (ROOT / "preview" / "radar" / "borders.json").read_bytes())
            self.assertIn(b"/radar/coast-", js)
            self.assertNotIn(b"/wind/coast-", js)
            self.assertIn(b"afterFirstPaint", js)
            self.assertIn(b"backgroundPreload", js)

            st, _, hub = self._get("/preview", ck)
            self.assertEqual(st, 200)
            self.assertIn(b'href="/preview/radar"', hub)
            self.assertIn(b"Radar viewer", hub)

    def test_forecast_cues_remain_without_map_perimeter(self):
        html = (ROOT / "preview" / "radar" / "index.html").read_text()
        css = (ROOT / "preview" / "radar" / "radar.css").read_text()
        js = (ROOT / "preview" / "radar" / "viewer.js").read_text()
        self.assertIn("Forecast +" , js)
        self.assertIn("not observed", js)
        self.assertIn("hatchImageData", js)
        self.assertIn("data-frame", css)
        self.assertIn(".rv-fcs", css)
        self.assertIn("html[data-frame=\"fc\"] .rv-badge", css)
        self.assertNotIn("html[data-frame=\"fc\"] .rv-stage::after", css)
        self.assertIn("Hatched = forecast", html)
        self.assertIn("min-height: 52px", css)
        self.assertIn("width: 44px; height: 44px", css)
        self.assertIn("-86.5", js)

    def test_public_radar_serves_chart_helm_and_frozen_files_stay_pinned(self):
        with mock.patch.dict(os.environ, {"PREVIEW_KEY": KEY}):
            st, h, html = self._get("/radar")
            self.assertEqual(st, 200)
            tag = (h.get("X-Robots-Tag") or h.get("x-robots-tag") or "").lower()
            self.assertIn("index", tag)
            self.assertNotIn("noindex", tag)
            self.assertIn(b'content="index, follow"', html)
            self.assertNotIn(b'content="noindex, nofollow"', html)
            self.assertIn(b'href="/radar/app.css"', html)
            self.assertIn(b'src="/radar/app.js"', html)
            self.assertIn(b'src="/radar/player.js"', html)
            self.assertIn(b'href="/wind.css"', html)
            self.assertIn(b'src="/wind/coast.js"', html)
            self.assertIn(b'href="/radar/coast-lo.json"', html)
            self.assertNotIn(b"/preview/radar", html)
            self.assertNotIn(b'href="/radar.css"', html)
            self.assertNotIn(b'src="/radar/viewer.js"', html)
            self.assertIn(b'data-radar-view="viewer"', html)
            self.assertIn(b'id="r-test" hidden', html)
            # Public assets, no cookie.
            assets = {
                "/radar/app.css": (ROOT / "preview" / "radar" / "radar.css", "css"),
                "/radar/app.js": (ROOT / "preview" / "radar" / "viewer.js", "javascript"),
                "/radar/labels.json": (ROOT / "preview" / "radar" / "labels.json", "json"),
                "/radar/coast-lo.json": (ROOT / "preview" / "radar" / "coast-lo.json", "json"),
                "/radar/coast-hi.json": (ROOT / "preview" / "radar" / "coast-hi.json", "json"),
                "/radar/borders.json": (ROOT / "preview" / "radar" / "borders.json", "json"),
            }
            for path, (file, needle) in assets.items():
                st, h, body = self._get(path)
                self.assertEqual(st, 200, path)
                self.assertIn(needle, (h.get("Content-Type") or h.get("content-type") or "").lower(), path)
                self.assertEqual(body, file.read_bytes(), path)
            # Legacy public paths remain the d0b0953 files (pins stay put).
            st, _, css = self._get("/radar.css")
            self.assertEqual(st, 200)
            self.assertEqual(css, (ROOT / "radar.css").read_bytes())
            st, _, js = self._get("/radar/viewer.js")
            self.assertEqual(st, 200)
            self.assertEqual(js, (ROOT / "radar-viewer.js").read_bytes())
            st, _, player = self._get("/radar/player.js")
            self.assertEqual(st, 200)
            self.assertEqual(player, (ROOT / "radar-player.js").read_bytes())
            # Preview route stays gated.
            self.assertEqual(self._get("/preview/radar")[0], 404)
        # Ed t576u (Phase 3C.1): wind-viewer.js is pinned to the approved wind-direction standard commit 960ebe1
        # (SHA-256 b3749937c6b564aead9dbbfc3c5f9d2dfafd98fd61cbf334bd15c9e7280f4c3e). All other files stay on BASELINE.
        for rel in FROZEN:
            current = (ROOT / rel).read_bytes()
            baseline = subprocess.check_output(["git", "show", "%s:%s" % ("960ebe1" if rel == "wind-viewer.js" else BASELINE, rel)], cwd=ROOT)
            self.assertEqual(current, baseline, rel)


class RadarPreviewCoastAndPreload(unittest.TestCase):
    def test_radar_coast_covers_pannable_extent_without_clip_edge(self):
        doc = json.loads((ROOT / "preview" / "radar" / "coast-lo.json").read_text())
        clip = doc["clip"]
        # Must extend beyond the worst-case visible extent at minZoom 5 on a
        # 390x844 or 844x390 phone with the centre at a maxBounds corner.
        # That view can reach about 51°N, 16°N, 105°W, 55°W.
        self.assertLessEqual(clip[0], -105.0)
        self.assertLessEqual(clip[1], 16.0)
        self.assertGreaterEqual(clip[2], -55.5)
        self.assertGreaterEqual(clip[3], 51.5)
        q = doc["q"]

        def decode(p):
            rings = []
            for a in p["r"]:
                out = []
                x = y = 0
                for i in range(0, len(a), 2):
                    x += a[i]
                    y += a[i + 1]
                    out.append((x / q, y / q))
                rings.append(out)
            return {"b": [v / q for v in p["b"]], "r": rings}

        polys = [decode(p) for p in doc["polys"]]

        def pip(lon, lat):
            for p in polys:
                b = p["b"]
                if lon < b[0] or lon > b[2] or lat < b[1] or lat > b[3]:
                    continue
                inside = False
                for r in p["r"]:
                    for i in range(len(r)):
                        xi, yi = r[i]
                        xj, yj = r[i - 1]
                        if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / (yj - yi) + xi:
                            inside = not inside
                if inside:
                    return True
            return False

        # Land in NC and neighbouring states, including the western buffer.
        self.assertTrue(pip(-78.64, 35.78), "Raleigh")
        self.assertTrue(pip(-84.03, 35.09), "Murphy")
        self.assertTrue(pip(-84.5, 35.1), "Tennessee just west of Murphy")
        self.assertTrue(pip(-83.92, 35.96), "Knoxville")
        self.assertTrue(pip(-86.0, 35.6), "western buffer")
        self.assertTrue(pip(-86.4, 35.5), "western buffer near pan edge")
        self.assertTrue(pip(-81.03, 34.00), "Columbia SC")
        self.assertTrue(pip(-77.44, 37.54), "Richmond VA")
        self.assertTrue(pip(-84.39, 33.75), "Atlanta")
        self.assertFalse(pip(-75.0, 34.5), "open ocean")
        # North of the previous 40.5°N seam and south of the previous 30°N seam.
        self.assertTrue(pip(-77.04, 38.91), "Washington DC")
        self.assertTrue(pip(-76.88, 40.27), "Harrisburg PA")
        self.assertTrue(pip(-80.00, 40.44), "Pittsburgh")
        self.assertTrue(pip(-81.69, 41.50), "Cleveland")
        self.assertTrue(pip(-79.38, 43.65), "Toronto")
        self.assertTrue(pip(-80.00, 50.00), "northern land inside the lo clip")
        self.assertTrue(pip(-80.19, 25.76), "Miami")
        self.assertTrue(pip(-82.46, 27.95), "Tampa")
        self.assertTrue(pip(-81.78, 24.55), "Key West")
        self.assertTrue(pip(-82.00, 29.00), "inland Florida south of 30N")
        self.assertTrue(pip(-90.05, 35.15), "Memphis")
        self.assertTrue(pip(-104.0, 35.00), "western land inside the lo clip")
        self.assertTrue(pip(-79.00, 22.00), "Cuba")
        self.assertFalse(pip(-90.00, 25.00), "Gulf of Mexico")
        self.assertFalse(pip(-70.00, 35.00), "open Atlantic")
        # West edge of land at mid-NC latitudes is the off-screen clip, not 84.3/85.
        def west_edge(lat):
            xs = []
            for p in polys:
                for r in p["r"]:
                    for i in range(len(r)):
                        x1, y1 = r[i]
                        x2, y2 = r[i - 1]
                        if (y1 > lat) != (y2 > lat):
                            xs.append((x2 - x1) * (lat - y1) / (y2 - y1) + x1)
            return min(xs) if xs else None
        for lat in (35.0, 35.5, 36.0, 40.0):
            self.assertLessEqual(west_edge(lat), -105.0, lat)
        def north_edge(lon):
            ys = []
            for p in polys:
                for r in p["r"]:
                    for i in range(len(r)):
                        x1, y1 = r[i]
                        x2, y2 = r[i - 1]
                        if (x1 > lon) != (x2 > lon):
                            ys.append((y2 - y1) * (lon - x1) / (x2 - x1) + y1)
            return max(ys) if ys else None
        # No artificial horizontal seam at the old 40.5°N clip; land continues well north.
        self.assertGreaterEqual(north_edge(-80.0), 51.5)

        # Wind coast files were not used as a write target and stay at the production clip.
        wind = json.loads((ROOT / "wind-coast" / "lo.json").read_text())
        self.assertEqual(wind["clip"][0], -85.0)
        baseline = subprocess.check_output(["git", "show", "%s:wind-coast/lo.json" % BASELINE], cwd=ROOT)
        self.assertEqual((ROOT / "wind-coast" / "lo.json").read_bytes(), baseline)

    def test_state_borders_include_nc_land_boundary(self):
        doc = json.loads((ROOT / "preview" / "radar" / "borders.json").read_text())
        neighbors = set(doc.get("nc_neighbors") or [])
        self.assertEqual(neighbors, {"VA", "TN", "GA", "SC"})
        pairs = {(min(x["a"], x["b"]), max(x["a"], x["b"])) for x in doc["lines"]}
        for a, b in (("NC", "VA"), ("NC", "TN"), ("GA", "NC"), ("NC", "SC")):
            self.assertIn((min(a, b), max(a, b)), pairs)
        # Lean: deferred border file should stay well under 80 KiB.
        self.assertLess((ROOT / "preview" / "radar" / "borders.json").stat().st_size, 80 * 1024)
        # lo is preloaded; keep it lean even with the wide clip (two-tier simplify).
        self.assertLess((ROOT / "preview" / "radar" / "coast-lo.json").stat().st_size, 80 * 1024)
        self.assertLess((ROOT / "preview" / "radar" / "coast-hi.json").stat().st_size, 120 * 1024)

    def test_preload_waits_for_first_observed_frame(self):
        js = (ROOT / "preview" / "radar" / "viewer.js").read_text()
        self.assertIn("afterFirstPaint", js)
        self.assertIn("startBackgroundPreload", js)
        self.assertIn("backgroundPreload", js)
        self.assertIn("requestIdleCallback", js)
        # Must not kick the full load-order pump at boot.
        self.assertNotIn("pump(); setInterval", js)
        html = (ROOT / "preview" / "radar" / "index.html").read_text()
        self.assertIn("/radar/coast-lo.json", html)
        self.assertNotIn('href="/wind/coast-lo.json"', html)
        self.assertNotIn("/radar/labels.json", html.split("<body")[0])  # not preloaded
        self.assertNotIn("/preview/radar/labels.json", html.split("<body")[0])


if __name__ == "__main__":
    unittest.main()
