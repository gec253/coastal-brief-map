"""Private /preview/intro gating, session behavior hooks, and public / stays untouched."""
from __future__ import annotations

import os
import re
import sys
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class WaveIntroPreview(unittest.TestCase):
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
            conn = HTTPConnection("127.0.0.1", self.port, timeout=12)
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

    def test_preview_404_without_cookie(self):
        for path in ("/preview/intro", "/preview/intro?play=1", "/preview/intro?seen=1"):
            status, _, _ = self._req(path)
            self.assertEqual(status, 404, path)
            status, _, _ = self._req(path, env={"PREVIEW_KEY": self.KEY})
            self.assertEqual(status, 404, path + " key set, no cookie")

    def test_cookie_unlocks_intro_and_sets_noindex(self):
        status, body, hdrs = self._req("/preview/intro", env={"PREVIEW_KEY": self.KEY}, cookie=self._cookie())
        self.assertEqual(status, 200)
        self.assertEqual(hdrs.get("cache-control"), "no-store")
        self.assertIn("noindex", hdrs.get("x-robots-tag", ""))
        self.assertIn(b'name="robots" content="noindex, nofollow"', body)
        self.assertIn(b"data-wave-intro", body)
        self.assertIn(b'data-home="folio"', body)
        self.assertIn(b'data-concept="a"', body)
        self.assertIn(b'id="wave-intro"', body)
        self.assertIn(b'id="wi-skip"', body)
        self.assertIn(b"Skip intro", body)
        self.assertIn(b'min-height: 44px', body)
        self.assertIn(b'id="wi-replay"', body)
        self.assertIn(b"Replay intro", body)
        self.assertIn(b"Know the Water. Live the Coast.", body)
        self.assertIn(b"cb-wave-intro-seen", body)
        self.assertIn(b"prefers-reduced-motion", body)
        # Public homepage is still underneath.
        self.assertIn(b'id="conditions"', body)
        self.assertIn(b"The Coastal Brief", body)

    def test_no_autoplay_media(self):
        status, body, _ = self._req("/preview/intro", env={"PREVIEW_KEY": self.KEY}, cookie=self._cookie())
        self.assertEqual(status, 200)
        self.assertNotIn(b"<audio", body)
        self.assertNotIn(b"<video", body)
        self.assertNotRegex(body.lower(), rb"<[^>]+autoplay\b")
        self.assertNotIn(b"new Audio", body)
        self.assertIn(b'data-sound-hook', body)
        self.assertIn(b'id="wi-sound" hidden', body)

    def test_session_and_skip_hooks(self):
        status, body, _ = self._req("/preview/intro", env={"PREVIEW_KEY": self.KEY}, cookie=self._cookie())
        self.assertEqual(status, 200)
        js = body.split(b"cb-wave-intro-seen")[1] if body.count(b"cb-wave-intro-seen") else body
        self.assertIn(b'sessionStorage.setItem(KEY, "1")', body)
        self.assertIn(b'Escape', body)
        self.assertIn(b'skip.focus()', body)
        self.assertIn(b'prefers-reduced-motion: reduce', body)
        # Boot script hides the overlay before paint when the session already saw it.
        self.assertIn(b'classList.add("intro-seen")', body)

    def test_animations_are_compositor_only(self):
        status, body, _ = self._req("/preview/intro", env={"PREVIEW_KEY": self.KEY}, cookie=self._cookie())
        css = body[body.find(b'id="wave-intro-css"'):body.find(b"</style>")]
        # Keyframe bodies should only change transform, opacity, and stroke-dashoffset.
        props = set()
        for block in re.findall(rb"@keyframes[^{]+\{(.+?)\n\}", css, re.S):
            for prop in re.findall(rb"([a-z-]+)\s*:", block):
                if prop in (b"from", b"to") or prop.endswith(b"%") or prop.decode().replace(".", "").isdigit():
                    continue
                if re.fullmatch(rb"\d+%", prop):
                    continue
                props.add(prop.decode())
        allowed = {"transform", "opacity", "stroke-dashoffset"}
        self.assertTrue(props, "expected keyframes")
        self.assertFalse(set(props) - allowed, set(props) - allowed)

    def test_public_homepage_untouched(self):
        status, body, hdrs = self._req("/")
        self.assertEqual(status, 200)
        self.assertNotIn("noindex", hdrs.get("x-robots-tag", ""))
        self.assertNotIn(b"data-wave-intro", body)
        self.assertNotIn(b'id="wave-intro"', body)
        self.assertNotIn(b'id="wi-skip"', body)
        self.assertNotIn(b"Replay intro", body)
        self.assertNotIn(b"wave-intro-css", body)
        self.assertIn(b'data-home="folio"', body)
        self.assertIn(b'data-concept="a"', body)
        # Cookie must not leak the intro onto public /.
        status, body, hdrs = self._req("/", env={"PREVIEW_KEY": self.KEY}, cookie=self._cookie())
        self.assertEqual(status, 200)
        self.assertNotIn(b"data-wave-intro", body)
        self.assertNotIn(b'id="wave-intro"', body)
        self.assertNotIn("noindex", hdrs.get("x-robots-tag", ""))

    def test_hub_lists_the_intro(self):
        status, body, _ = self._req("/preview", env={"PREVIEW_KEY": self.KEY}, cookie=self._cookie())
        self.assertEqual(status, 200)
        self.assertIn(b'href="/preview/intro"', body)
