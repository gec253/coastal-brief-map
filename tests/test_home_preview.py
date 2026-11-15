"""Private /preview/home gating, photo rotation, and public pages stay byte-identical."""
from __future__ import annotations

import os
import sys
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ROOT = Path(__file__).resolve().parents[1]

HOME_MARKERS = (
    b"data-home",
    b"home-photo-band",
    b"/preview/home.css",
    b"/preview/home/photos/",
    b"mast-date-short",
)


class HomePreview(unittest.TestCase):
    KEY = "preview-test-key-24-chars-ok"

    @classmethod
    def setUpClass(cls):
        import server
        cls.server = server
        cls.httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        cls.host, cls.port = cls.httpd.server_address

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def _req(self, path, env=None, cookie=None):
        saved = {k: os.environ.get(k) for k in ("PREVIEW_KEY", "MORNING_BRIEF_ENABLED", "FRESHWATER_ENABLED")}
        try:
            os.environ.pop("PREVIEW_KEY", None)
            if env:
                for k, v in env.items():
                    if v is None:
                        os.environ.pop(k, None)
                    else:
                        os.environ[k] = v
            headers = {}
            if cookie:
                headers["Cookie"] = cookie
            conn = HTTPConnection("127.0.0.1", self.port, timeout=8)
            conn.request("GET", path, headers=headers)
            resp = conn.getresponse()
            body = resp.read()
            hdrs = {k.lower(): v for k, v in resp.getheaders()}
            conn.close()
            return resp.status, body, hdrs
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    def _cookie(self):
        return "%s=%s" % (self.server.PREVIEW_COOKIE, self.server._preview_cookie_value(self.KEY))

    def test_public_homepage_is_the_final_design(self):
        status, body, hdrs = self._req("/")
        self.assertEqual(status, 200)
        self.assertNotIn("noindex", hdrs.get("x-robots-tag", ""))
        self.assertIn(b'data-concept="a"', body)
        self.assertIn(b'data-home="folio"', body)
        self.assertIn(b"folio-photo", body)
        self.assertIn(b"/featured/bodie-sunrise", body)
        self.assertIn(b'href="/styles.css"', body)
        self.assertIn(b'id="folio-water-h"', body)
        self.assertIn(b'id="region-select"', body)
        self.assertIn(b'id="region-nav"', body)
        self.assertIn(b'property="og:image"', body)
        self.assertNotIn(b"/preview/home.css", body)
        self.assertNotIn(b"/preview/home/photos/", body)
        self.assertNotIn(b'id="mast-preview-dock"', body)

    def test_public_homepage_identical_with_preview_cookie(self):
        env = {"PREVIEW_KEY": self.KEY}
        status, body, hdrs = self._req("/", env=env, cookie=self._cookie())
        self.assertEqual(status, 200)
        # Cookie must not swap public / for a gated comparison preview.
        self.assertIn(b'data-home="folio"', body)
        self.assertIn(b"/featured/bodie-sunrise", body)
        self.assertNotIn(b"data-preview", body)
        self.assertNotIn(b'id="mast-preview-dock"', body)
        self.assertNotIn("noindex", hdrs.get("x-robots-tag", ""))

    def test_preview_404_without_cookie(self):
        for path in (
            "/preview/home",
            "/preview/home?c=cinematic",
            "/preview/home?c=final",
            "/preview/home.css",
            "/preview/home/photos/bodie-sunrise-w800.webp",
        ):
            status, _, _ = self._req(path)
            self.assertEqual(status, 404, path)
            status, _, _ = self._req(path, env={"PREVIEW_KEY": self.KEY})
            self.assertEqual(status, 404, path + " key set, no cookie")

    def test_cookie_unlocks_home_concepts(self):
        env = {"PREVIEW_KEY": self.KEY}
        ck = self._cookie()
        for concept in ("cinematic", "magazine"):
            status, body, hdrs = self._req("/preview/home?c=" + concept, env=env, cookie=ck)
            self.assertEqual(status, 200, concept)
            self.assertEqual(hdrs.get("cache-control"), "no-store")
            self.assertIn("noindex", hdrs.get("x-robots-tag", ""))
            self.assertIn(b'name="robots" content="noindex, nofollow"', body)
            self.assertIn(('data-home="%s"' % concept).encode(), body)
            self.assertIn(b'data-concept="c"', body)
            self.assertIn(b"home-photo-band", body)
            self.assertIn(b"mast-wave", body)
            self.assertIn(b'id="conditions"', body)
            self.assertIn(b'id="region-nav"', body)
            self.assertIn(b'id="nav-brief"', body)
            self.assertIn(b'id="region-select"', body)
            self.assertIn(b"mast-date-short", body)
            self.assertIn(b"fetchpriority=\"high\"", body)
            self.assertIn(b"type=\"image/avif\"", body)
            self.assertIn(b"type=\"image/webp\"", body)
            self.assertIn(b"home-photo-credit", body)
            self.assertIn(b'id="preview-css"', body)
            self.assertNotIn(b'href="/preview/home.css"', body)
            # Instruments stay in the page immediately after the band.
            band_at = body.find(b"home-photo-band")
            cond_at = body.find(b'id="conditions"')
            self.assertTrue(0 <= band_at < cond_at)
        status, css, hdrs = self._req("/preview/home.css", env=env, cookie=ck)
        self.assertEqual(status, 200)
        self.assertIn("text/css", hdrs.get("content-type", ""))
        self.assertIn("noindex", hdrs.get("x-robots-tag", ""))
        self.assertIn(b"home-photo-band", css)

    def test_photo_query_and_asset_gating(self):
        env = {"PREVIEW_KEY": self.KEY}
        ck = self._cookie()
        status, body, _ = self._req("/preview/home?c=cinematic&photo=bodie-sunrise&shot=1", env=env, cookie=ck)
        self.assertEqual(status, 200)
        self.assertIn(b"bodie-sunrise-w800", body)
        self.assertIn(b"Sunrise at the Bodie Island Lighthouse", body)
        self.assertIn(b"data-shot", body)
        self.assertNotIn(b'id="mast-preview-dock"', body)
        # Photo asset with cookie.
        status, data, hdrs = self._req("/preview/home/photos/bodie-sunrise-w800.webp", env=env, cookie=ck)
        self.assertEqual(status, 200)
        self.assertIn("image/webp", hdrs.get("content-type", ""))
        self.assertEqual(hdrs.get("cache-control"), "no-store")
        self.assertIn("noindex", hdrs.get("x-robots-tag", ""))
        self.assertGreater(len(data), 1000)
        status, data, hdrs = self._req("/preview/home/photos/bodie-sunrise-w800.avif", env=env, cookie=ck)
        self.assertEqual(status, 200)
        self.assertIn("image/avif", hdrs.get("content-type", ""))
        # Unknown or path-traversal names 404 even with the cookie.
        status, _, _ = self._req("/preview/home/photos/../masthead.css", env=env, cookie=ck)
        self.assertEqual(status, 404)
        status, _, _ = self._req("/preview/home/photos/not-a-real-photo-w800.webp", env=env, cookie=ck)
        self.assertEqual(status, 404)

    def test_pinned_photo_is_the_default(self):
        a = self.server._featured_photo()
        b = self.server._featured_photo()
        self.assertEqual(a["id"], "bodie-sunrise")
        self.assertEqual(a["id"], b["id"])
        forced = self.server._featured_photo("lookout-night")
        self.assertEqual(forced["id"], "lookout-night")
        unknown = self.server._featured_photo("not-real")
        self.assertEqual(unknown["id"], "bodie-sunrise")

    def test_final_is_default_home_on_masthead_a(self):
        env = {"PREVIEW_KEY": self.KEY}
        ck = self._cookie()
        for path in ("/preview/home", "/preview/home?c=final", "/preview/home?c=final&shot=1"):
            status, body, hdrs = self._req(path, env=env, cookie=ck)
            self.assertEqual(status, 200, path)
            self.assertEqual(hdrs.get("cache-control"), "no-store")
            self.assertIn("noindex", hdrs.get("x-robots-tag", ""))
            self.assertIn(b'data-concept="a"', body)
            self.assertIn(b'data-home="magazine"', body)
            self.assertIn(b" data-final", body)
            self.assertIn(b"bodie-sunrise-w800", body)
            self.assertIn(b"Sunrise at the Bodie Island Lighthouse", body)
            self.assertIn(b'id="preview-css"', body)
            self.assertNotIn(b'href="/preview/masthead.css"', body)
            self.assertNotIn(b'href="/preview/home.css"', body)
            self.assertIn(b'id="region-select"', body)
            self.assertIn(b"region-pick", body)
            # Final keeps the in-card picker; the hide rule excludes [data-final].
            self.assertIn(b":not([data-final])", body)
            self.assertIn(b'id="conditions"', body)
            self.assertIn(b'id="region-nav"', body)
            self.assertIn(b'id="nav-brief"', body)
            if "shot=1" in path:
                self.assertIn(b"data-shot", body)
                self.assertNotIn(b'id="mast-preview-dock"', body)
            else:
                self.assertIn(b"mast-preview-dock", body)
