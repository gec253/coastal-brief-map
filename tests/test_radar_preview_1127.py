"""Private Radar Viewer Chart Helm preview (Ed t512u). Public /radar stays on production assets."""
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
KEY = "a" * 32
BASELINE = "d0b0953000e8c6da95e27a25f1216019b1065e7c"
FROZEN = (
    "wind.html", "wind-viewer.js", "wind.css", "wind-lab.js", "wind-coast.js",
    "radar.html", "radar-viewer.js", "radar.css", "radar-player.js",
)


def _cookie():
    import server
    return "%s=%s" % (server.PREVIEW_COOKIE, server._preview_cookie_value(KEY))


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
            for p in ("/preview/radar", "/preview/radar/viewer.js", "/preview/radar/radar.css"):
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
            self.assertIn(b"mm/h", body)
            self.assertNotIn(b"Reflectivity <b>dBZ</b>", body)
            self.assertIn(b"not an NWS reflectivity (dBZ) scale", body)
            self.assertIn(b"Coast", body)
            self.assertIn(b">Me<", body)
            self.assertNotIn(b'href="/radar.css"', body)
            self.assertNotIn(b'src="/radar/viewer.js"', body)

            st, h, css = self._get("/preview/radar/radar.css", ck)
            self.assertEqual(st, 200)
            self.assertIn("text/css", h.get("Content-Type") or h.get("content-type") or "")
            self.assertIn("no-store", (h.get("Cache-Control") or h.get("cache-control") or "").lower())
            self.assertEqual(css, (ROOT / "preview" / "radar" / "radar.css").read_bytes())

            st, h, js = self._get("/preview/radar/viewer.js", ck)
            self.assertEqual(st, 200)
            self.assertIn("javascript", h.get("Content-Type") or h.get("content-type") or "")
            self.assertEqual(js, (ROOT / "preview" / "radar" / "viewer.js").read_bytes())
            self.assertIn(b"/wind/labels.json", js)
            self.assertIn(b"setForecast", js)

            st, _, hub = self._get("/preview", ck)
            self.assertEqual(st, 200)
            self.assertIn(b'href="/preview/radar"', hub)
            self.assertIn(b"Radar viewer", hub)

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
