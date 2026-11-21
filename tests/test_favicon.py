"""Favicon and app-icon package (Concept A, Ed t386u): tags, theme-color, and routes."""
from __future__ import annotations

import struct
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import server

ROOT = Path(__file__).resolve().parents[1]
V = "v=20261121"
THEME = b'<meta name="theme-color" content="#071C29">'
ICON_MARKERS = (
    b'rel="icon" href="/favicon.ico?v=20261121"',
    b'rel="icon" href="/branding/favicon.svg?v=20261121"',
    b'rel="apple-touch-icon" href="/apple-touch-icon.png?v=20261121"',
    b'rel="manifest" href="/site.webmanifest?v=20261121"',
)
PUBLIC_PAGES = (
    "/",
    "/dashboard",
    "/?region=hatteras",
    "/lake",
    "/brief",
    "/brief?region=hatteras",
    "/brief?region=falls-lake",
    "/catch-wall",
    "/coastal-life",
    "/photos",
    "/wind",
    "/radar",
    "/feedback",
)
PRIVATE_PAGES = (
    "/preview",
    "/lab/wind",
    "/lab/tiles",
    "/preview/catch-wall",
    "/wind?model=hrrr",
)


def _get(base, path, method="GET"):
    req = urllib.request.Request(base + path, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


def _hdr(headers, name):
    for k, v in headers.items():
        if k.lower() == name.lower():
            return v
    return ""


class FaviconPackage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.base = "http://127.0.0.1:%d" % cls.httpd.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def get(self, path, method="GET"):
        return _get(self.base, path, method)

    def test_public_pages_have_icon_tags_and_theme_color(self):
        for path in PUBLIC_PAGES:
            st, h, body = self.get(path)
            self.assertEqual(st, 200, path)
            ctype = _hdr(h, "Content-Type")
            self.assertIn("text/html", ctype, path)
            self.assertIn(THEME, body, path)
            for marker in ICON_MARKERS:
                self.assertIn(marker, body, "%s missing %s" % (path, marker.decode()))
            self.assertNotIn(b'name="theme-color" content="#0B2A3D"', body, path)

    def test_icon_routes_ok_types_and_cache(self):
        cases = (
            ("/favicon.ico", "image/x-icon", None),
            ("/apple-touch-icon.png", "image/png", None),
            ("/apple-touch-icon-precomposed.png", "image/png", None),
            ("/site.webmanifest", "application/manifest+json", None),
            ("/branding/favicon.svg", "image/svg+xml", None),
            ("/branding/favicon-16.png", "image/png", None),
            ("/branding/favicon-32.png", "image/png", None),
            ("/branding/icon-192.png", "image/png", None),
            ("/branding/icon-512.png", "image/png", None),
            ("/branding/icon-512-maskable.png", "image/png", None),
            ("/branding/apple-touch-icon.png", "image/png", None),
            ("/favicon.ico?%s" % V, "image/x-icon", None),
        )
        for path, want_type, _ in cases:
            st, h, body = self.get(path)
            self.assertEqual(st, 200, path)
            self.assertIn(want_type, _hdr(h, "Content-Type").split(";")[0].strip(), path)
            self.assertIn("max-age=604800", _hdr(h, "Cache-Control"), path)
            self.assertGreater(len(body), 32, path)

        # SVG is compact, outlined (no live font), Folio colors only.
        st, h, svg = self.get("/branding/favicon.svg")
        self.assertLess(len(svg), 2000)
        self.assertIn(b"<path ", svg)
        self.assertNotIn(b"@font-face", svg)
        self.assertNotIn(b"fraunces", svg.lower())
        self.assertIn(b"#071C29", svg)
        self.assertIn(b"#F3E6D0", svg)
        self.assertIn(b"#C4A36A", svg)

        # ICO contains 16, 32 and 48.
        st, h, ico = self.get("/favicon.ico")
        reserved, typ, count = struct.unpack_from("<HHH", ico, 0)
        self.assertEqual((reserved, typ, count), (0, 1, 3))
        sizes = set()
        off = 6
        for _ in range(count):
            w, height, *rest = struct.unpack_from("<BBBBHHII", ico, off)
            sizes.add((w, height))
            off += 16
        self.assertEqual(sizes, {(16, 16), (32, 32), (48, 48)})

        # Manifest names the site and uses Folio navy.
        import json
        st, h, raw = self.get("/site.webmanifest")
        data = json.loads(raw)
        self.assertEqual(data["name"], "The Coastal Brief")
        self.assertEqual(data["theme_color"], "#071C29")
        self.assertEqual(data["background_color"], "#071C29")
        srcs = {i["src"] for i in data["icons"]}
        self.assertTrue(any("icon-192.png" in s for s in srcs))
        self.assertTrue(any("icon-512.png" in s for s in srcs))
        self.assertTrue(any(i.get("purpose") == "maskable" for i in data["icons"]))

        # HEAD works on the root aliases.
        st, h, body = self.get("/favicon.ico", method="HEAD")
        self.assertEqual(st, 200)
        self.assertFalse(body)
        self.assertIn("image/x-icon", _hdr(h, "Content-Type"))

    def test_private_routes_stay_404_without_cookie(self):
        for path in PRIVATE_PAGES:
            st, h, body = self.get(path)
            self.assertEqual(st, 404, path)

    def test_asset_files_exist_and_are_small(self):
        svg = (ROOT / "branding" / "favicon.svg").read_bytes()
        self.assertLess(len(svg), 2000)
        ico = (ROOT / "branding" / "favicon.ico").stat().st_size
        self.assertLess(ico, 20_000)
        self.assertTrue((ROOT / "site.webmanifest").is_file())
        for name in ("favicon-16.png", "favicon-32.png", "apple-touch-icon.png",
                     "icon-192.png", "icon-512.png", "icon-512-maskable.png"):
            self.assertTrue((ROOT / "branding" / name).is_file(), name)


if __name__ == "__main__":
    unittest.main()
