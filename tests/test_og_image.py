"""Open Graph / Twitter Card meta on public pages, and the new masthead card file."""
import os
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from PIL import Image

import server

ROOT = Path(__file__).resolve().parents[1]
IMAGE_URL = "https://thecoastalbrief.com/branding/og-masthead.jpg"
ALT = (
    "The Coastal Brief nameplate in ivory serif on deep navy, with a faint "
    "North Carolina nautical-chart texture and the line From the rivers to "
    "the sounds to the sea."
)
PAGES = (
    "/",
    "/catch-wall",
    "/coastal-life",
    "/photos",
    "/brief?region=crystal-coast",
    "/brief?region=hatteras",
    "/lake?region=falls-lake",
    "/lake",
)


class OgMastheadFile(unittest.TestCase):
    def test_new_card_exists_and_old_preview_is_untouched(self):
        new = ROOT / "branding" / "og-masthead.jpg"
        old = ROOT / "branding" / "og-preview.png"
        self.assertTrue(new.is_file(), "branding/og-masthead.jpg must be committed")
        self.assertTrue(old.is_file(), "must not replace branding/og-preview.png")
        self.assertGreater(old.stat().st_size, 1000)
        self.assertLess(new.stat().st_size, 300 * 1024)
        im = Image.open(new)
        self.assertEqual(im.size, (1200, 630))
        src = ROOT / "branding" / "og-masthead.html"
        self.assertTrue(src.is_file(), "reproducible HTML source must be committed")


class OgMastheadMeta(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._env = {k: os.environ.get(k) for k in ("MORNING_BRIEF_ENABLED", "FRESHWATER_ENABLED")}
        os.environ.pop("MORNING_BRIEF_ENABLED", None)
        os.environ.pop("FRESHWATER_ENABLED", None)
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = "http://127.0.0.1:%d" % cls.httpd.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        for k, v in cls._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def _get(self, path):
        req = urllib.request.Request(self.base + path, headers={"Accept": "text/html"})
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                return r.status, r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8", "replace")

    def test_public_pages_point_at_the_new_card(self):
        checked = 0
        for path in PAGES:
            status, body = self._get(path)
            if status == 404:
                # A region with no published brief should still be covered by the other brief URL.
                continue
            self.assertEqual(status, 200, path)
            self.assertIn('property="og:image" content="%s"' % IMAGE_URL, body, path)
            self.assertIn('name="twitter:image" content="%s"' % IMAGE_URL, body, path)
            self.assertIn('property="og:image:width" content="1200"', body, path)
            self.assertIn('property="og:image:height" content="630"', body, path)
            self.assertIn('property="og:image:alt" content="%s"' % ALT, body, path)
            self.assertIn('name="twitter:image:alt" content="%s"' % ALT, body, path)
            self.assertIn('name="twitter:card" content="summary_large_image"', body, path)
            self.assertNotIn("branding/og-preview.png", body, path)
            checked += 1
        self.assertGreaterEqual(checked, 7)

    def test_image_is_served(self):
        req = urllib.request.Request(self.base + "/branding/og-masthead.jpg")
        with urllib.request.urlopen(req, timeout=15) as r:
            self.assertEqual(r.status, 200)
            self.assertIn("image/jpeg", r.headers.get("Content-Type", ""))
            data = r.read()
        self.assertGreater(len(data), 10000)
        self.assertLess(len(data), 300 * 1024)
