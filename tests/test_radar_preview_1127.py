"""Private Radar Viewer Chart Helm preview (Ed t512u / t514u). Public /radar stays on production assets."""
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
    "radar.html", "radar-viewer.js", "radar.css", "radar-player.js",
)
MM_PER_IN = 25.4
PROVIDER_BINS_MM = (0.1, 0.5, 1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 64.0)


def _cookie():
    import server
    return "%s=%s" % (server.PREVIEW_COOKIE, server._preview_cookie_value(KEY))


def format_in_h(mm):
    """Match preview/radar/viewer.js formatInh: 3 decimals below 1 in/h, 2 at or above."""
    inches = mm / MM_PER_IN
    return ("%.2f" if inches >= 1 else "%.3f") % inches


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
        expected = {
            0.1: "0.004",
            0.5: "0.020",
            1.0: "0.039",
            2.0: "0.079",
            4.0: "0.157",
            8.0: "0.315",
            16.0: "0.630",
            32.0: "1.26",
            64.0: "2.52",
        }
        for mm in PROVIDER_BINS_MM:
            self.assertEqual(format_in_h(mm), expected[mm], mm)
            # Rounding must not jump a displayed tick onto a different provider bin.
            inches = mm / MM_PER_IN
            shown = float(format_in_h(mm))
            self.assertLess(abs(shown - inches), 0.005, mm)
        js = (ROOT / "preview" / "radar" / "viewer.js").read_text()
        self.assertIn("MM_PER_IN = 25.4", js)
        self.assertIn("inches >= 1 ? inches.toFixed(2) : inches.toFixed(3)", js)
        self.assertIn("formatInh(v)", js)
        html = (ROOT / "preview" / "radar" / "index.html").read_text()
        self.assertIn("Precip rate <b>in/h</b>", html)
        self.assertIn('aria-label="Observed precipitation rate colour scale, inches per hour"', html)
        self.assertIn("id=\"r-bins\"", html)
        self.assertIn("millimetre-per-hour", html)
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
        self.assertIn("/preview/radar/labels.json", js)
        self.assertNotIn("/wind/labels.json", js)
        current = (ROOT / "data" / "wind-labels.json").read_bytes()
        baseline = subprocess.check_output(["git", "show", "%s:data/wind-labels.json" % BASELINE], cwd=ROOT)
        self.assertEqual(current, baseline)


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
            for p in ("/preview/radar", "/preview/radar/viewer.js", "/preview/radar/radar.css", "/preview/radar/labels.json"):
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
            self.assertIn(b'href="/preview/radar/radar.css"', body)
            self.assertIn(b'src="/preview/radar/viewer.js"', body)
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
            self.assertIn(b"/preview/radar/labels.json", js)
            self.assertNotIn(b"/wind/labels.json", js)
            self.assertIn(b"setForecast", js)
            self.assertIn(b"keepBuffer: 2", js)
            self.assertNotIn(b"if (shown && shown !== layers.get(f.time)) { shown.setOpacity(0); shown = null; }", js)

            st, h, lab = self._get("/preview/radar/labels.json", ck)
            self.assertEqual(st, 200)
            self.assertIn("json", (h.get("Content-Type") or h.get("content-type") or "").lower())
            self.assertEqual(lab, (ROOT / "preview" / "radar" / "labels.json").read_bytes())
            self.assertIn(b"Falls Lake", lab)
            self.assertIn(b"Jordan Lake", lab)

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

    def test_public_radar_and_frozen_wind_files_are_unchanged(self):
        with mock.patch.dict(os.environ, {"PREVIEW_KEY": KEY}):
            st, _, html = self._get("/radar")
            self.assertEqual(st, 200)
            self.assertIn(b'href="/radar.css"', html)
            self.assertIn(b'src="/radar/viewer.js"', html)
            self.assertNotIn(b"/preview/radar", html)
            st, _, css = self._get("/radar.css")
            self.assertEqual(st, 200)
            self.assertEqual(css, (ROOT / "radar.css").read_bytes())
        for rel in FROZEN:
            current = (ROOT / rel).read_bytes()
            baseline = subprocess.check_output(["git", "show", "%s:%s" % (BASELINE, rel)], cwd=ROOT)
            self.assertEqual(current, baseline, rel)


if __name__ == "__main__":
    unittest.main()
