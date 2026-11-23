"""Wind & Radar homepage instruments on every public region (Ed t444u).

Each public saltwater and freshwater region gets both instruments, focused on that region's own
NWS forecast point; a region without a usable point gets a plain explanation, never Morehead City."""
import json
import os
import re
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

SALT = ("crystal-coast", "hatteras", "wilmington", "nags-head", "emerald-isle", "topsail")
FRESH = ("falls-lake", "jordan-lake", "neuse-river")
REG = {r["id"]: r for r in json.loads((ROOT / "data" / "regions.json").read_text())["regions"]}
PAGE = ('<html><head></head><body><main><section class="cg cg-hybrid" id="conditions"><p>x</p></section>'
        '</main></body></html>').encode()


def attrs(html):
    m = re.search(r'<section class="sc[^"]*" id="showcase"([^>]*)>', html)
    return dict(re.findall(r'data-([a-z]+)="([^"]*)"', m.group(1))) if m else None


class Focus(unittest.TestCase):
    def test_crystal_coast_framing_unchanged(self):
        for rid in (None, "", "crystal-coast"):
            f = showcase.focus(rid)
            self.assertEqual((f["lat"], f["lon"], f["clat"], f["clon"], f["label"]), (34.72, -76.70, 34.62, -76.75, "Morehead City"))
        html = showcase.section("A")
        self.assertIn('href="/wind"', html)
        self.assertIn('href="/radar"', html)
        self.assertIn("Crystal Coast · tap", html)

    def test_every_public_region_gets_both_viewers_on_its_own_point(self):
        for rid in SALT[1:] + FRESH:
            with self.subTest(rid=rid):
                html = showcase.section("A", region=rid)
                a = attrs(html)
                fc = REG[rid]["forecast"]
                self.assertEqual(a["region"], rid)
                self.assertAlmostEqual(float(a["lat"]), fc["lat"], places=3)
                self.assertAlmostEqual(float(a["lon"]), fc["lon"], places=3)
                self.assertEqual(a["label"], fc["label"])
                self.assertNotIn("Morehead City", html)
                self.assertNotIn("Crystal Coast", html)
                self.assertEqual(html.count('class="sc-inst sc-wind"'), 1)
                self.assertEqual(html.count('class="sc-inst sc-radar"'), 1)
                self.assertIn('href="/wind?at=%s,%s"' % (a["lat"], a["lon"]), html)
                self.assertIn('href="/radar?at=%s,%s"' % (a["lat"], a["lon"]), html)
                # labels keep model vs observed apart
                self.assertIn("Model forecast · GFS", html)
                self.assertIn('sc-tag-obs">Observed', html)
                self.assertIn(showcase.GFS_CREDIT, html)

    def test_unknown_or_pointless_region_explains_instead_of_morehead(self):
        for rid in ("nowhere", "atlantic-beach"):  # atlantic-beach has no forecast point on file
            with self.subTest(rid=rid):
                html = showcase.section("A", region=rid)
                self.assertIn('data-unsupported="1"', html)
                self.assertIn("aren't set up for", html)
                self.assertNotIn("sc-cv", html)
                self.assertNotIn("data-lat", html)
                self.assertNotIn("Morehead City", html)

    def test_point_outside_data_area_is_unsupported(self):
        fake = [{"id": "far", "name": "Far Away", "forecast": {"label": "X", "lat": 40.7, "lon": -74.0}}]
        with mock.patch.object(showcase, "_regions", return_value=fake):
            self.assertFalse(showcase.focus("far")["supported"])
            self.assertIn('data-unsupported="1"', showcase.section("A", region="far"))

    def test_inject_passes_region(self):
        out = showcase.inject(PAGE, "A", region="falls-lake").decode()
        self.assertEqual(attrs(out)["region"], "falls-lake")


class Client(unittest.TestCase):
    js = (ROOT / "showcase.js").read_text(encoding="utf-8")

    def test_js_reads_focus_and_bails_on_unsupported(self):
        self.assertIn("sec.dataset.unsupported", self.js)
        self.assertIn('num("clat", 34.62)', self.js)
        self.assertIn("No model wind for", self.js)
        self.assertNotIn("innerHTML = (k < 1", self.js)

    def test_full_viewers_accept_bounded_at(self):
        for f in ("wind-viewer.js", "radar-viewer.js"):
            s = (ROOT / f).read_text(encoding="utf-8")
            self.assertIn("[?&]at=", s)
            self.assertIn("AT[0] >= 32.5 && AT[0] <= 37.5 && AT[1] >= -80 && AT[1] <= -73", s)


def env(**kv):
    base = {k: v for k, v in os.environ.items() if k not in ("RENDER", "RENDER_SERVICE_ID", "HOME_SHOWCASE")}
    base.update(kv)
    return mock.patch.dict(os.environ, base, clear=True)


class Routes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import server
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.base = "http://127.0.0.1:%d" % cls.httpd.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def _get(self, path):
        try:
            with urllib.request.urlopen(self.base + path, timeout=60) as r:
                return r.status, r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            return e.code, ""

    def test_every_public_region_homepage_has_focused_section(self):
        with env(HOME_SHOWCASE="1", PREVIEW_KEY=""):
            import freshwater
            regions = SALT + (FRESH if freshwater.flag_on() else ())
            for rid in regions:
                with self.subTest(rid=rid):
                    st, body = self._get("/?region=%s" % rid)
                    self.assertEqual(st, 200)
                    a = attrs(body)
                    self.assertIsNotNone(a, rid)
                    self.assertEqual(a.get("region"), rid)
                    self.assertEqual(body.count('id="showcase"'), 1)

    def test_flag_off_no_section_any_region(self):
        with env(HOME_SHOWCASE="", PREVIEW_KEY=""):
            for rid in ("hatteras", "falls-lake"):
                st, body = self._get("/?region=%s" % rid)
                if st == 200:
                    self.assertNotIn('id="showcase"', body)


if __name__ == "__main__":
    unittest.main()
