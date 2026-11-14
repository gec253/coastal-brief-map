"""Private /preview/masthead gating, and public pages stay byte-identical to origin/main."""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ROOT = Path(__file__).resolve().parents[1]

# Public surfaces that must not change on this branch.
PUBLIC_FILES = (
    "index.html",
    "styles.css",
    "dashboard.js",
    "region-nav.js",
    "app.js",
    "brief-link.js",
    "coast-strip.js",
    "identity.js",
    "lake.html",
    "catch-wall.html",
    "brief.css",
)

CONCEPT_MARKERS = (
    b"data-concept",
    b"mast-wave",
    b"mast-preview-dock",
    b"/preview/masthead.css",
    b"cb-mast-reveal",
    b"wave-swell",
    b"wave-glint",
)


class MastheadPreview(unittest.TestCase):
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

    def test_public_files_match_origin_main(self):
        for rel in PUBLIC_FILES:
            committed = subprocess.check_output(["git", "show", "origin/main:" + rel], cwd=ROOT)
            self.assertEqual(committed, (ROOT / rel).read_bytes(), rel)

    def test_public_homepage_has_no_concept_markup(self):
        status, body, hdrs = self._req("/")
        self.assertEqual(status, 200)
        for marker in CONCEPT_MARKERS:
            self.assertNotIn(marker, body, marker)
        # Same bytes as serving index.html through the existing chrome helper
        # (dateline included), so this branch does not alter the public homepage.
        expected = self.server._apply_chrome((ROOT / "index.html").read_bytes())
        self.assertEqual(body, expected)
        self.assertNotIn("noindex", hdrs.get("x-robots-tag", ""))

    def test_other_public_pages_have_no_concept_markup(self):
        for path in ("/catch-wall", "/coastal-life", "/photos"):
            status, body, _ = self._req(path)
            self.assertEqual(status, 200, path)
            for marker in CONCEPT_MARKERS:
                self.assertNotIn(marker, body, "%s %s" % (path, marker))

    def test_preview_404_without_key_or_cookie(self):
        for path in ("/preview/masthead", "/preview/masthead?c=a", "/preview/masthead.css"):
            status, _, _ = self._req(path)
            self.assertEqual(status, 404, path)
            status, _, _ = self._req(path, env={"PREVIEW_KEY": self.KEY})
            self.assertEqual(status, 404, path + " key set, no cookie")

    def test_cookie_unlocks_preview_and_sets_noindex(self):
        env = {"PREVIEW_KEY": self.KEY}
        ck = self._cookie()
        for concept in ("a", "b", "c"):
            status, body, hdrs = self._req("/preview/masthead?c=" + concept, env=env, cookie=ck)
            self.assertEqual(status, 200, concept)
            self.assertEqual(hdrs.get("cache-control"), "no-store")
            self.assertIn("noindex", hdrs.get("x-robots-tag", ""))
            self.assertIn(b'name="robots" content="noindex, nofollow"', body)
            self.assertIn(('data-concept="%s"' % concept).encode(), body)
            self.assertIn(b"mast-wave", body)
            self.assertIn(b'id="region-nav"', body)
            self.assertIn(b'id="nav-brief"', body)
            self.assertIn(b'id="conditions"', body)
            self.assertIn(b"From the rivers to the sounds to the sea", body)
            self.assertIn(b"mast-preview-dock", body)
            self.assertIn(b"Replay", body)
            # Region is in the picker only, not repeated as a mast line.
            self.assertNotIn(b"mast-region-line", body)
        status, body, hdrs = self._req("/preview/masthead.css", env=env, cookie=ck)
        self.assertEqual(status, 200)
        self.assertIn("text/css", hdrs.get("content-type", ""))
        self.assertIn("noindex", hdrs.get("x-robots-tag", ""))
        self.assertIn(b"wave-swell", body)
        # With the cookie, the public homepage is still the shipped identity.
        status, home, _ = self._req("/", env=env, cookie=ck)
        self.assertEqual(status, 200)
        for marker in CONCEPT_MARKERS:
            self.assertNotIn(marker, home, marker)

    def test_shot_mode_hides_preview_dock(self):
        env = {"PREVIEW_KEY": self.KEY}
        status, body, _ = self._req("/preview/masthead?c=c&shot=1", env=env, cookie=self._cookie())
        self.assertEqual(status, 200)
        self.assertIn(b"data-shot", body)
        self.assertNotIn(b"mast-preview-dock", body)
        self.assertIn(b"mast-wave", body)
