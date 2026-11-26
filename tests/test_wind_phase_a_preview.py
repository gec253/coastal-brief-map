"""Private Phase A wind preview (Ed t480u). Public /wind stays on production assets."""
from __future__ import annotations

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
PROD = "58a376c"
KEY = "a" * 32


def _cookie():
    import server
    return "%s=%s" % (server.PREVIEW_COOKIE, server._preview_cookie_value(KEY))


class PhaseAPreview(unittest.TestCase):
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
        with mock.patch.dict(os.environ, {"PREVIEW_KEY": KEY, "WIND_PARTICLES_ENABLED": ""}):
            for p in ("/preview/wind", "/preview/wind/engine.js", "/preview/wind/wind.css"):
                st, _, body = self._get(p)
                self.assertEqual(st, 404, p)
                self.assertIn(b"not found", body.lower())
            self.assertEqual(self._get("/preview/wind", "cb_preview=nope")[0], 404)

    def test_authenticated_preview_serves_phase_a_assets(self):
        ck = _cookie()
        with mock.patch.dict(os.environ, {"PREVIEW_KEY": KEY, "WIND_PARTICLES_ENABLED": ""}):
            st, h, body = self._get("/preview/wind", ck)
            self.assertEqual(st, 200)
            self.assertIn("private, no-store", (h.get("Cache-Control") or h.get("cache-control") or "").lower())
            self.assertIn("noindex", (h.get("X-Robots-Tag") or h.get("x-robots-tag") or "").lower())
            self.assertIn(b'href="/preview/wind/wind.css"', body)
            self.assertIn(b'src="/preview/wind/engine.js"', body)
            self.assertNotIn(b'href="/wind.css"', body)
            self.assertNotIn(b'src="/wind/engine.js"', body)
            self.assertIn(b"Model forecast", body)
            self.assertIn(b"NOAA NCEP GFS", body)

            st, h, css = self._get("/preview/wind/wind.css", ck)
            self.assertEqual(st, 200)
            self.assertIn("text/css", h.get("Content-Type") or h.get("content-type") or "")
            self.assertIn("private, no-store", (h.get("Cache-Control") or h.get("cache-control") or "").lower())
            self.assertIn(b"--map-bg: #CDDCE6", css)
            self.assertEqual(css, (ROOT / "preview" / "wind" / "wind.css").read_bytes())

            st, h, js = self._get("/preview/wind/engine.js", ck)
            self.assertEqual(st, 200)
            self.assertIn("javascript", h.get("Content-Type") or h.get("content-type") or "")
            self.assertIn("private, no-store", (h.get("Cache-Control") or h.get("cache-control") or "").lower())
            self.assertIn(b"[75, 156, 211]", js)
            self.assertEqual(js, (ROOT / "preview" / "wind" / "engine.js").read_bytes())

            # Hub lists the preview entry once the cookie is set.
            st, _, hub = self._get("/preview", ck)
            self.assertEqual(st, 200)
            self.assertIn(b'href="/preview/wind"', hub)
            self.assertIn(b"Wind viewer \xc2\xb7 Phase A", hub)

    def test_public_wind_matches_production_baseline(self):
        with mock.patch.dict(os.environ, {"PREVIEW_KEY": KEY, "WIND_PARTICLES_ENABLED": ""}):
            st, _, html = self._get("/wind")
            self.assertEqual(st, 200)
            self.assertIn(b'href="/wind.css"', html)
            self.assertIn(b'src="/wind/engine.js"', html)
            self.assertNotIn(b"/preview/wind/", html)

            st, _, css = self._get("/wind.css")
            self.assertEqual(st, 200)
            prod_css = subprocess.check_output(["git", "show", "%s:wind.css" % PROD], cwd=ROOT)
            self.assertEqual(css, prod_css)
            self.assertNotIn(b"#CDDCE6", css)

            st, _, js = self._get("/wind/engine.js")
            self.assertEqual(st, 200)
            prod_js = subprocess.check_output(["git", "show", "%s:wind-lab.js" % PROD], cwd=ROOT)
            self.assertEqual(js, prod_js)
            self.assertIn(b"[240, 95, 95]", js)
            self.assertNotIn(b"[75, 156, 211]", js)

        # On-disk public files stay at the production commit (payload budget uses these).
        for rel in ("wind.css", "wind-lab.js", "wind.html", "wind-viewer.js"):
            current = (ROOT / rel).read_bytes()
            baseline = subprocess.check_output(["git", "show", "%s:%s" % (PROD, rel)], cwd=ROOT)
            self.assertEqual(current, baseline, rel)

    def test_preview_not_in_sitemap_or_public_raw_paths(self):
        with mock.patch.dict(os.environ, {"PREVIEW_KEY": KEY, "WIND_PARTICLES_ENABLED": ""}):
            st, _, sm = self._get("/sitemap.xml")
            self.assertEqual(st, 200)
            self.assertNotIn(b"/preview/wind", sm)
            for p in ("/preview/wind/engine.js", "/preview/wind/wind.css",
                      "/preview/wind/../wind.css"):
                self.assertEqual(self._get(p)[0], 404, p)


if __name__ == "__main__":
    unittest.main()
