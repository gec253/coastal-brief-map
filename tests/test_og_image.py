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

    def test_photo_pages_have_their_own_share_title_and_url(self):
        want = {
            "/catch-wall": ("Catch Wall \u2014 The Coastal Brief", "https://thecoastalbrief.com/catch-wall"),
            "/coastal-life": ("Coastal Life \u2014 The Coastal Brief", "https://thecoastalbrief.com/coastal-life"),
            "/photos": ("Photos \u2014 Catch Wall &amp; Coastal Life \u2014 The Coastal Brief", "https://thecoastalbrief.com/photos"),
        }
        bodies = {}
        for path, (title, url) in want.items():
            status, body = self._get(path)
            self.assertEqual(status, 200, path)
            self.assertIn('property="og:title" content="%s"' % title, body, path)
            self.assertIn('name="twitter:title" content="%s"' % title, body, path)
            self.assertIn('property="og:url" content="%s"' % url, body, path)
            # Only the head tags differ; the page body is the same file.
            bodies[path] = body.split("</head>", 1)[1]
        self.assertEqual(len(set(bodies.values())), 1)

    def test_og_render_sources_are_not_served(self):
        for path in ("/branding/og-masthead.html", "/branding/render-og-masthead.js"):
            status, _ = self._get(path)
            self.assertEqual(status, 404, path)


class ChartTextureNotOnPhones(unittest.TestCase):
    def test_chart_texture_only_inside_min_width_media_query(self):
        import re
        for name in ("styles.css", "brief.css"):
            css = re.sub(r"/\*.*?\*/", "", (ROOT / name).read_text(), flags=re.S)
            self.assertIn("masthead-chart.webp", css, name)
            for m in re.finditer(r"masthead-chart\.webp", css):
                before = css[: m.start()]
                opened = before.rfind("@media (min-width: 761px)")
                self.assertNotEqual(opened, -1, name)
                # every brace opened after the media query is still open at the url
                depth = before[opened:].count("{") - before[opened:].count("}")
                self.assertGreaterEqual(depth, 2, name)
