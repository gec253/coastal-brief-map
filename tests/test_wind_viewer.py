"""/wind private viewer (Wind & Radar Signature Experience, Phase 1, Ed t349u).

Covers the NOAA GFS grid pipeline (windgrid.py), the shared particle engine math (wind-lab.js,
run in Node), labelling (MODEL FORECAST, never observed/live), ET formatting, controls, route
gating (preview cookie or WIND_PARTICLES_ENABLED only) and a payload budget for the page."""
import json
import math
import os
import re
import secrets
import shutil
import subprocess
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "tests" / "fixtures" / "gfs_uv10m_ncbox.grb2"   # real NOMADS GFS 0.25° 10 m U/V, 2026-11-19 12Z f009
import sys
sys.path.insert(0, str(ROOT))
import windgrid  # noqa: E402

NODE = shutil.which("node")


def _grid(ahead=0):
    windgrid._cache.clear()
    with mock.patch.object(windgrid, "_fetch", return_value=FIX.read_bytes()), \
         mock.patch.object(windgrid.time, "time", return_value=1795122000.0):  # 2026-11-19 21:00Z
        return windgrid.latest_grid(ahead=ahead)


def _node(script: str):
    out = subprocess.run([NODE, "-e", script], cwd=ROOT, capture_output=True, text=True, timeout=30)
    if out.returncode:
        raise AssertionError(out.stderr)
    return json.loads(out.stdout)


class GridIntegrity(unittest.TestCase):
    def test_decode_real_gfs_fixture(self):
        msgs = windgrid.decode(FIX.read_bytes())
        self.assertEqual([(m["cat"], m["num"]) for m in msgs], [(2, 2), (2, 3)])  # UGRD, VGRD
        for m in msgs:
            g = m["grid"]
            self.assertEqual((g["nx"], g["ny"], g["dx"], g["dy"]), (29, 21, 0.25, 0.25))
            self.assertEqual((g["la1"], g["lo1"], g["la2"], g["lo2"]), (32.5, 280.0, 37.5, 287.0))
            self.assertEqual(len(m["values"]), 29 * 21)
            self.assertEqual(m["fhour"], 9)

    def test_payload_bounds_units_and_times(self):
        g = _grid()
        self.assertTrue(g["ok"])
        self.assertEqual(g["kind"], "model forecast")
        self.assertEqual(g["units"], "m/s")
        self.assertIn("GFS", g["source"])
        self.assertEqual(g["lo1"], -80.0)                       # 280°E normalised to -80°
        north = (g["scan"] & 0x40) == 0
        self.assertFalse(north)                                 # row 0 is the southern edge (32.5°N)
        self.assertAlmostEqual(g["la1"] + (g["ny"] - 1) * g["dy"], windgrid.BBOX["toplat"])
        self.assertAlmostEqual(g["lo1"] + (g["nx"] - 1) * g["dx"], windgrid.BBOX["rightlon"])
        self.assertEqual(len(g["u"]), g["nx"] * g["ny"])
        self.assertEqual(len(g["v"]), g["nx"] * g["ny"])
        self.assertTrue(all(abs(x) < 75 for x in g["u"] + g["v"]))      # m/s, physically plausible
        self.assertGreater(max(map(abs, g["u"])), 0.5)                  # not an all-zero field
        self.assertRegex(g["run"], r"^\d{4}-\d\d-\d\dT\d\d:00Z$")
        self.assertEqual((g["run"], g["valid"], g["forecastHour"]), ("2026-11-19T12:00Z", "2026-11-19T21:00Z", 9))

    def test_ahead_steps_request_later_file_and_cache_separately(self):
        windgrid._cache.clear()
        urls = []

        def fake(url):
            urls.append(url)
            return FIX.read_bytes()
        now = 1795528800.0  # 2026-11-24T14:00Z: 12Z run, f002
        with mock.patch.object(windgrid, "_fetch", side_effect=fake):
            g0 = windgrid.latest_grid(now=now)
            g6 = windgrid.latest_grid(now=now, ahead=6)
            windgrid.latest_grid(now=now, ahead=6)               # cached
            bad = windgrid.latest_grid(now=now, ahead=5)          # not offered -> treated as 0, cached
        self.assertEqual(len(urls), 2)
        self.assertIn("gfs.t12z.pgrb2.0p25.f002", urls[0])
        self.assertIn("gfs.t12z.pgrb2.0p25.f008", urls[1])
        self.assertEqual((g0["ahead"], g6["ahead"], bad["ahead"]), (0, 6, 0))
        self.assertEqual(windgrid.AHEAD_HOURS, (0, 3, 6, 9, 12))


class Conversions(unittest.TestCase):
    def test_speed_knots(self):
        self.assertAlmostEqual(windgrid.speed_kt(10, 0), 19.43844, places=4)
        self.assertAlmostEqual(windgrid.speed_kt(3, 4), 5 * 1.943844, places=4)

    def test_direction_is_meteorological_from(self):
        self.assertAlmostEqual(windgrid.from_deg(0, -5), 0)      # blowing south = from N
        self.assertAlmostEqual(windgrid.from_deg(-5, 0), 90)     # blowing west = from E
        self.assertAlmostEqual(windgrid.from_deg(0, 5), 180)
        self.assertAlmostEqual(windgrid.from_deg(5, 0), 270)
        self.assertAlmostEqual(windgrid.from_deg(5, 5), 225)     # SW wind
        self.assertEqual(windgrid.compass(225), "SW")
        self.assertEqual(windgrid.compass(359), "N")


class Interpolation(unittest.TestCase):
    def setUp(self):
        self.g = _grid()

    def node_at(self, i, j):
        g = self.g
        return g["u"][j * g["nx"] + i], g["v"][j * g["nx"] + i], g["la1"] + j * g["dy"], g["lo1"] + i * g["dx"]

    def test_exact_at_raw_nodes(self):
        for i, j in [(0, 0), (14, 10), (28, 20), (20, 9)]:
            u, v, lat, lon = self.node_at(i, j)
            su, sv = windgrid.sample(self.g, lat, lon)
            self.assertAlmostEqual(su, u, places=9)
            self.assertAlmostEqual(sv, v, places=9)

    def test_midpoint_is_mean_of_four_nodes(self):
        a, b, c, d = self.node_at(15, 8), self.node_at(16, 8), self.node_at(15, 9), self.node_at(16, 9)
        su, sv = windgrid.sample(self.g, a[2] + 0.125, a[3] + 0.125)
        self.assertAlmostEqual(su, (a[0] + b[0] + c[0] + d[0]) / 4, places=9)
        self.assertAlmostEqual(sv, (a[1] + b[1] + c[1] + d[1]) / 4, places=9)

    def test_outside_grid_is_none(self):
        self.assertIsNone(windgrid.sample(self.g, 38.0, -76.0))
        self.assertIsNone(windgrid.sample(self.g, 35.0, -81.0))

    @unittest.skipUnless(NODE, "node not installed")
    def test_browser_engine_matches_python_and_raw_nodes(self):
        pts = [(34.6, -76.5), (35.0, -75.33), (34.62, -76.52), (33.1, -78.9), (36.9, -73.4), (32.5, -80.0), (37.5, -73.0)]
        g = self.g
        res = _node("const M=require('./wind-lab.js');const g=%s;const s=M.makeSampler(g);const o=[0,0];"
                    "console.log(JSON.stringify(%s.map(p=>s(p[0],p[1],o)?[o[0],o[1],M.speedKt(o[0],o[1]),M.fromDeg(o[0],o[1])]:null)))"
                    % (json.dumps(g), json.dumps(pts)))
        for (lat, lon), r in zip(pts, res):
            u, v = windgrid.sample(g, lat, lon)
            self.assertAlmostEqual(r[0], u, places=4)            # Float32 in the browser
            self.assertAlmostEqual(r[1], v, places=4)
            self.assertAlmostEqual(r[2], windgrid.speed_kt(u, v), places=3)
            self.assertAlmostEqual((r[3] - windgrid.from_deg(u, v) + 180) % 360 - 180, 0, places=2)
        self.assertIsNone(_node("const M=require('./wind-lab.js');const s=M.makeSampler(%s);console.log(JSON.stringify(s(40,-76,[0,0])||null))" % json.dumps(g)))


@unittest.skipUnless(NODE, "node not installed")
class EasternTime(unittest.TestCase):
    def test_et_labels(self):
        r = _node("const M=require('./wind-lab.js');console.log(JSON.stringify([M.etShort('2026-11-19T21:00Z'),M.etShort('2026-07-04T16:00Z'),"
                  "M.etLong('2026-11-19T12:00Z'),M.etShort('2026-11-20T04:30Z')]))")
        self.assertEqual(r[0], "Thu 4:00 PM ET")      # EST, UTC-5
        self.assertEqual(r[1], "Sat 12:00 PM ET")     # EDT, UTC-4
        self.assertEqual(r[2], "Thu, Nov 19, 7:00 AM ET")
        self.assertEqual(r[3], "Thu 11:30 PM ET")     # crosses midnight UTC -> still Thursday ET


class PageCopyAndControls(unittest.TestCase):
    html = (ROOT / "wind.html").read_text()
    css = (ROOT / "wind.css").read_text()
    js = (ROOT / "wind-viewer.js").read_text()
    engine = (ROOT / "wind-lab.js").read_text()

    def visible_text(self):
        t = re.sub(r"<script.*?</script>|<style.*?</style>", " ", self.html, flags=re.S)
        return re.sub(r"<[^>]+>", " ", t)

    def test_model_forecast_prominent_never_observed_or_live(self):
        self.assertRegex(self.html, r'<span class="w-badge" id="w-badge">Model forecast</span>')
        self.assertRegex(self.css, r"\.w-badge \{[^}]*text-transform: uppercase")
        self.assertIn("Model forecast, not measurements", self.html)
        strings = " ".join(re.findall(r'"([^"]*)"', self.js))   # JS string literals = UI copy
        attrs = re.sub(r'aria-live="[^"]*"', "", self.html)          # attribute name, not copy
        for copy in (self.visible_text(), attrs, strings):
            self.assertIsNone(re.search(r"observ", copy, re.I))
            self.assertIsNone(re.search(r"\blive\b", copy, re.I))
        self.assertIn("model forecast", strings)                # tap readout labels the value too

    def test_run_valid_forecast_hour_in_et(self):
        for i in ("w-run", "w-valid", "w-fh", "w-clock"):
            self.assertIn('id="%s"' % i, self.html)
        self.assertIn("Model run", self.html)
        self.assertIn(">Valid<", self.html)
        self.assertIn("Fcst hour", self.html)
        self.assertIn('aria-label="Model run and valid time, Eastern Time"', self.html)
        self.assertIn('M.etShort(g.run)', self.js)
        self.assertIn('M.etShort(g.valid)', self.js)
        self.assertIn('timeZone: "America/New_York"', self.js)
        self.assertIn('" ET"', self.js)

    def test_controls_present_and_thumb_sized(self):
        for i, label in (("w-play", None), ("w-prev", "Earlier forecast hour"), ("w-next", "Later forecast hour"),
                         ("w-center", "Recenter"), ("w-locate", "my location")):
            m = re.search(r'<button type="button"[^>]*id="%s"[^>]*>' % i, self.html)
            self.assertIsNotNone(m, i)
            if label:
                self.assertIn(label, m.group(0))
        self.assertIn('class="w-ctl"', self.html)

        def px(sel, prop):
            m = re.search(re.escape(sel) + r" \{[^}]*?" + prop + r": (\d+)px", self.css)
            return int(m.group(1))
        self.assertGreaterEqual(px(".w-btn", "min-width"), 44)
        self.assertGreaterEqual(px(".w-btn", "min-height"), 44)
        self.assertGreaterEqual(px(".w-about summary", "width"), 44)
        self.assertGreaterEqual(px(".w-about summary", "height"), 44)
        # every breakpoint keeps the control buttons at 44 px or more
        for rule in re.findall(r"\.w-(?:btn|arrow|play) \{([^}]*)\}", self.css):
            for v in re.findall(r"min-(?:width|height): (\d+)px", rule):
                self.assertGreaterEqual(int(v), 44, rule)
        # controls sit in the bottom grid row
        self.assertRegex(self.css, r"grid-template-rows:[^;]*calc\(var\(--ctl-h\) \+ env\(safe-area-inset-bottom\)\)")

    def test_location_prompt_only_after_tap(self):
        i = self.js.index("getCurrentPosition")
        self.assertGreater(i, self.js.index('$("w-locate").addEventListener("click"'))
        self.assertEqual(self.js.count("geolocation.getCurrentPosition"), 1)
        self.assertNotIn("watchPosition", self.js)

    def test_frame_rate_reduced_motion_and_pausing(self):
        self.assertIn("phone ? 30 : 60", self.js)
        self.assertIn("frameMs: fps === 30 ? 33.3 : 0", self.js)
        self.assertIn("Math.min(screen.width, screen.height) < 600", self.js)
        self.assertIn("!osReduce", self.js)
        self.assertIn("(prefers-reduced-motion: reduce)", self.js)
        self.assertIn('document.addEventListener("visibilitychange", sync)', self.engine)
        self.assertIn("IntersectionObserver", self.engine)
        self.assertIn("!document.hidden", self.engine)
        self.assertIn("drawArrows", self.engine)              # static arrows when motion is off

    def test_attribution_and_on_page_limitations(self):
        self.assertIn("NOAA NCEP GFS", self.html)
        self.assertIn("Basemap: Esri, HERE, Garmin", self.html)
        self.assertIn("25&nbsp;km", self.html)
        self.assertIn("CLKN7", self.html)
        self.assertIn("BFTN7", self.html)
        doc = (ROOT / "docs" / "WIND_VIEWER.md").read_text()
        for s in ("25 km", "CLKN7", "BFTN7", "41025", "HRRR", "model forecast"):
            self.assertIn(s, doc)

    def test_payload_budget_and_no_homepage_css(self):
        self.assertNotIn("/styles.css", self.html)
        self.assertNotIn("@font-face", self.css)
        self.assertNotIn(".woff2", self.html + self.css)
        self.assertNotIn("fonts.googleapis", self.html)
        own = sum((ROOT / f).stat().st_size for f in ("wind.html", "wind.css", "wind-viewer.js", "wind-lab.js"))
        self.assertLess(own, 45 * 1024, own)
        self.assertLess((ROOT / "wind.css").stat().st_size, 12 * 1024)
        scripts = re.findall(r'<script src="([^"]+)"', self.html)
        self.assertEqual(scripts, ["/vendor/leaflet/leaflet.js", "/lab/wind.js", "/wind/viewer.js"])
        self.assertTrue(all("defer" in s for s in re.findall(r"<script src=[^>]+>", self.html)))
        # Esri tiles are drawn into <canvas>, never <img>, so a tile can't be the LCP element.
        self.assertIn("L.GridLayer.extend", self.js)
        self.assertNotIn("L.tileLayer", self.js)
        # attribution is static HTML, painted with the chrome
        self.assertIn('class="w-attrib"', self.html)

    def test_dashboard_home_and_freshwater_do_not_link_wind(self):
        for f in ("index.html", "dashboard.js", "app.js", "lake.html", "site_chrome.py", "sprint_home.py"):
            p = ROOT / f
            if p.exists():
                self.assertNotRegex(p.read_text(), r'href="/wind["?#]', f)


class Routes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import server
        cls.server = server
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.base = "http://127.0.0.1:%d" % cls.httpd.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown(); cls.httpd.server_close()

    def _get(self, path, cookie=None):
        req = urllib.request.Request(self.base + path, headers={"Cookie": cookie} if cookie else {})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status, dict(r.headers), r.read()
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers), e.read()

    PATHS = ("/wind", "/wind.css", "/wind/viewer.js", "/lab/wind", "/lab/wind.js", "/api/wind-grid", "/api/wind-grid?ahead=3")

    def test_404_for_public(self):
        key = secrets.token_hex(16)
        with mock.patch.dict(os.environ, {"WIND_PARTICLES_ENABLED": "", "PREVIEW_KEY": key}), \
             mock.patch.object(windgrid, "latest_grid", side_effect=AssertionError("must not fetch")):
            for p in self.PATHS:
                self.assertEqual(self._get(p)[0], 404, p)
            # a wrong cookie is still public
            self.assertEqual(self._get("/wind", "cb_preview=nope")[0], 404)

    def test_raw_files_never_served_statically(self):
        with mock.patch.dict(os.environ, {"WIND_PARTICLES_ENABLED": "1"}):
            for p in ("/wind.html", "/wind-viewer.js", "/wind-lab.js", "/wind-lab.html"):
                self.assertEqual(self._get(p)[0], 404, p)

    def test_preview_cookie_unlocks_private_noindex(self):
        key = secrets.token_hex(16)
        ck = "%s=%s" % (self.server.PREVIEW_COOKIE, self.server._preview_cookie_value(key))
        calls = []

        def fake(ahead=0):
            calls.append(ahead)
            return {"ok": True, "ahead": ahead}
        with mock.patch.dict(os.environ, {"WIND_PARTICLES_ENABLED": "", "PREVIEW_KEY": key}), \
             mock.patch.object(windgrid, "latest_grid", side_effect=fake):
            st, h, body = self._get("/wind", ck)
            self.assertEqual(st, 200)
            self.assertIn("noindex", h.get("X-Robots-Tag", ""))
            self.assertIn("no-store", h.get("Cache-Control", ""))
            self.assertIn(b'data-wind-view="viewer"', body)
            self.assertEqual(self._get("/wind.css", ck)[1]["Content-Type"], "text/css; charset=utf-8")
            self.assertEqual(self._get("/wind/viewer.js", ck)[1]["Content-Type"], "text/javascript; charset=utf-8")
            self.assertEqual(self._get("/lab/wind", ck)[0], 200)      # prototype still works
            self.assertEqual(json.loads(self._get("/api/wind-grid?ahead=9", ck)[2])["ahead"], 9)
            self._get("/api/wind-grid?ahead=7", ck)
            self._get("/api/wind-grid?ahead=x", ck)
        self.assertEqual(calls, [9, 0, 0])

    def test_flag_unlocks(self):
        with mock.patch.dict(os.environ, {"WIND_PARTICLES_ENABLED": "1"}), \
             mock.patch.object(windgrid, "latest_grid", return_value={"ok": True}):
            for p in self.PATHS:
                self.assertEqual(self._get(p)[0], 200, p)


if __name__ == "__main__":
    unittest.main()
