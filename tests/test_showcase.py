"""Wind & Radar homepage section: flag, public data endpoints, labels, lazy/static loading."""
import json
import os
import re
import secrets
import sys
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import showcase  # noqa: E402
import windgrid  # noqa: E402

PAGE = ('<html><head><meta name="robots" content="index, follow"></head><body><main>'
        '<section class="cg cg-hybrid" id="conditions"><div class="al">Small Craft Advisory</div>'
        '<section class="inner">x</section></section><aside class="cb-life">life</aside>'
        '<section class="hz">photo</section></main></body></html>').encode()
META = (200, {"ok": True, "attribution": "Radar: NOAA/NSSL MRMS; Source: Météo-France & co.", "disclaimer": "Radar is for general information only."})
FAKE_GRID = {
    "ok": True, "kind": "model forecast", "source": "NOAA NCEP GFS 0.25°, 10 m wind, via NOMADS",
    "run": "2026-11-20T12:00Z", "valid": "2026-11-20T17:00Z", "forecastHour": 5, "units": "m/s",
    "nx": 2, "ny": 2, "la1": 35.0, "lo1": -78.0, "dx": 0.25, "dy": 0.25, "scan": 0, "ahead": 0,
    "u": [1.0, 1.0, 1.0, 1.0], "v": [0.5, 0.5, 0.5, 0.5],
}


def env(**kv):
    base = {k: v for k, v in os.environ.items() if k not in ("RENDER", "RENDER_SERVICE_ID", "HOME_SHOWCASE")}
    base.update(kv)
    return mock.patch.dict(os.environ, base, clear=True)


class Gate(unittest.TestCase):
    def test_flag_defaults_off(self):
        with env():
            self.assertFalse(showcase.enabled())
            self.assertIsNone(showcase.variant({}, None))
            self.assertIsNone(showcase.variant({"showcase": ["A"]}, "crystal-coast"))

    def test_flag_on_serves_a_on_crystal_coast_only(self):
        with env(HOME_SHOWCASE="1"):
            self.assertEqual(showcase.variant({}, None), "A")
            self.assertEqual(showcase.variant({}, "crystal-coast"), "A")
            self.assertEqual(showcase.variant({"showcase": ["B"]}, "crystal-coast"), "A")
            self.assertIsNone(showcase.variant({}, "hatteras"))
        with env(HOME_SHOWCASE="true"):
            self.assertTrue(showcase.enabled())
        with env(HOME_SHOWCASE="0"):
            self.assertFalse(showcase.enabled())

    def test_flag_works_on_render(self):
        with env(HOME_SHOWCASE="1", RENDER="true"):
            self.assertTrue(showcase.enabled())
            self.assertEqual(showcase.variant({}, None), "A")
        with env(RENDER="true"):
            self.assertFalse(showcase.enabled())
            self.assertIsNone(showcase.variant({}, None))

    def test_assets_not_served_statically(self):
        import server
        for p in ("/showcase.js", "/showcase.css", "/showcase.py"):
            self.assertFalse(server._static_allowed(p), p)


class Inject(unittest.TestCase):
    def test_after_conditions_before_rest_and_content_intact(self):
        out = showcase.inject(PAGE, "A", radar_meta=lambda: META).decode()
        i_cond, i_sc, i_life = out.find('id="conditions"'), out.find('id="showcase"'), out.find('class="cb-life"')
        self.assertTrue(0 < i_cond < out.find("Small Craft Advisory") < i_sc < i_life)
        self.assertIn('class="sc sc-a"', out)
        for keep in ("Small Craft Advisory", "life", "photo"):
            self.assertIn(keep, out)
        # Public section: do not replace the homepage robots rule.
        self.assertIn('content="index, follow"', out)
        self.assertNotIn("noindex", out)
        self.assertEqual(out.count('<script src="/showcase.js" defer>'), 1)

    def test_labels_credits_and_links(self):
        out = showcase.inject(PAGE, "A", radar_meta=lambda: META).decode()
        self.assertIn("Model forecast · GFS", out)
        self.assertIn(">Observed<", out)
        self.assertNotIn("Forecast</span>", out.split('class="sc-inst sc-radar"')[1].split("</a>")[0])
        self.assertIn(showcase.GFS_CREDIT, out)
        self.assertIn("Radar: NOAA/NSSL MRMS; Source: Météo-France &amp; co.", out)  # verbatim (escaped)
        self.assertIn("Radar is for general information only.", out)
        self.assertIn('href="/wind"', out)
        self.assertIn('href="/radar"', out)

    def test_meta_failure_still_renders(self):
        def boom():
            raise RuntimeError("x")
        self.assertIn('id="showcase"', showcase.inject(PAGE, "A", radar_meta=boom).decode())


class Client(unittest.TestCase):
    js = (ROOT / "showcase.js").read_text(encoding="utf-8")
    css = (ROOT / "showcase.css").read_text(encoding="utf-8")

    def test_lazy_static_latest_observed_only(self):
        self.assertIn("IntersectionObserver", self.js)
        self.assertNotIn("requestAnimationFrame", self.js)  # no animation loop
        self.assertIn('f.type === "observed"', self.js)
        self.assertNotIn("nowcast", re.sub(r"/\*.*?\*/", "", self.js, flags=re.S).replace("never forecast", ""))
        self.assertIn("obs[obs.length - 1]", self.js)
        self.assertIn('timeZone: "America/New_York"', self.js)
        self.assertIn("/api/home-wind", self.js)
        self.assertIn("/api/home-coast", self.js)
        self.assertNotIn("/api/wind-grid", self.js)
        self.assertNotIn("/wind/coast-lo.json", self.js)

    def test_tap_targets_and_reduced_motion(self):
        self.assertIn("min-height:44px", self.css)
        self.assertIn("prefers-reduced-motion:reduce", self.css)
        self.assertIn("aspect-ratio:4/3", self.css)  # reserved space: no layout shift

    def test_a_layout_and_legible_credits(self):
        self.assertIn("@media (min-width:700px){.sc-a .sc-grid{grid-template-columns:1fr 1fr}}", self.css)
        self.assertIn("aspect-ratio:4/3", self.css)
        self.assertIn("font-size:.7rem", self.css)
        self.assertNotIn("display:none", self.css.replace(".sc-pv{position:absolute;left:-9999px}", "").replace(".sc-b .sc-read small{display:none}", "").replace(".sc-b .sc-age i{display:none}", ""))
        html = showcase.section("A", "Radar: credit.", "Radar is for general information only.")
        self.assertNotIn("<details", html)
        credit = html[html.find("sc-credit"):]
        self.assertNotIn(" hidden", credit)
        self.assertIn("Crystal Coast", html)
        self.assertIn(showcase.GFS_CREDIT, html)
        self.assertIn("Radar: credit.", html)
        self.assertIn("Radar is for general information only.", html)
        self.assertIn("Cape Lookout", self.js)
        self.assertIn("34.605", self.js)
        self.assertIn("-76.536", self.js)
        self.assertIn("No precipitation in view", self.js)
        self.assertIn('nm + " nm"', self.js)

    def test_client_has_no_secret_markers(self):
        blob = self.js + self.css
        for s in ("WEATHERAPI_KEY", "PREVIEW_KEY", "api.weatherapi.com", "key="):
            self.assertNotIn(s, blob)


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
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def _get(self, path, cookie=None):
        req = urllib.request.Request(self.base + path, headers={"Cookie": cookie} if cookie else {})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status, {k.lower(): v for k, v in r.headers.items()}, r.read()
        except urllib.error.HTTPError as e:
            return e.code, {k.lower(): v for k, v in e.headers.items()}, e.read()

    def test_flag_off_showcase_js_404_and_home_has_no_section(self):
        with env(HOME_SHOWCASE="", WIND_PARTICLES_ENABLED="", PREVIEW_KEY=""):
            self.assertEqual(self._get("/showcase.js")[0], 404)
            # Homepage may 200 with live conditions; it must not include the section or the script.
            st, _, body = self._get("/")
            if st == 200:
                self.assertNotIn(b'id="showcase"', body)
                self.assertNotIn(b"/showcase.js", body)

    def test_flag_on_serves_script_and_section_on_crystal_coast(self):
        with env(HOME_SHOWCASE="1", WIND_PARTICLES_ENABLED="", PREVIEW_KEY=""):
            st, h, body = self._get("/showcase.js")
            self.assertEqual(st, 200)
            self.assertIn("javascript", h.get("content-type", ""))
            self.assertIn("max-age=600", h.get("cache-control", ""))
            self.assertNotIn("access-control-allow-origin", h)
            st, _, home = self._get("/")
            self.assertEqual(st, 200)
            self.assertIn(b'id="showcase"', home)
            self.assertIn(b'data-showcase="A"', home)
            self.assertIn(b"/showcase.js", home)
            st, _, other = self._get("/?region=hatteras")
            if st == 200:
                self.assertNotIn(b'id="showcase"', other)

    def test_public_home_wind_is_gfs_only_cached_and_ignores_hrrr(self):
        calls = []

        def fake(ahead=0):
            calls.append(ahead)
            out = dict(FAKE_GRID)
            out["ahead"] = ahead
            out["detail"] = "should-not-leak"
            return out

        with env(HOME_SHOWCASE="", WIND_PARTICLES_ENABLED="", PREVIEW_KEY=""), \
             mock.patch.object(windgrid, "latest_grid", side_effect=fake):
            st, h, body = self._get("/api/home-wind?model=hrrr&ahead=9")
            self.assertEqual(st, 200)
            self.assertIn("max-age=600", h.get("cache-control", ""))
            self.assertIn("public", h.get("cache-control", ""))
            self.assertNotIn("access-control-allow-origin", h)
            data = json.loads(body)
            self.assertTrue(data["ok"])
            self.assertEqual(data.get("ahead"), 0)
            self.assertNotIn("detail", data)
            self.assertIn("u", data)
            self.assertNotIn("hrrr", json.dumps(data).lower())
            # /api/wind-grid stays private, including HRRR.
            self.assertEqual(self._get("/api/wind-grid")[0], 404)
            self.assertEqual(self._get("/api/wind-grid?model=hrrr")[0], 404)
        self.assertEqual(calls, [0])  # only the default GFS snapshot

    def test_public_home_coast_is_static_cached(self):
        with env(WIND_PARTICLES_ENABLED="", PREVIEW_KEY=""):
            st, h, body = self._get("/api/home-coast")
            self.assertEqual(st, 200)
            self.assertIn("json", h.get("content-type", ""))
            self.assertIn("max-age=86400", h.get("cache-control", ""))
            self.assertNotIn("access-control-allow-origin", h)
            data = json.loads(body)
            self.assertIn("polys", data)
            self.assertEqual(self._get("/wind/coast-lo.json")[0], 404)
            self.assertEqual(self._get("/wind/coast-hi.json")[0], 404)

    def test_viewers_stay_gated(self):
        key = secrets.token_hex(16)
        with env(HOME_SHOWCASE="1", WIND_PARTICLES_ENABLED="", PREVIEW_KEY=key):
            for p in ("/wind", "/radar", "/lab/wind", "/api/wind-grid", "/wind/coast-lo.json"):
                self.assertEqual(self._get(p)[0], 404, p)


if __name__ == "__main__":
    unittest.main()
