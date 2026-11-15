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

    def _req(self, path, env=None, cookie=None, headers=None):
        saved = {k: os.environ.get(k) for k in ("PREVIEW_KEY", "MORNING_BRIEF_ENABLED", "FRESHWATER_ENABLED")}
        try:
            os.environ.pop("PREVIEW_KEY", None)
            if env:
                for k, v in env.items():
                    if v is None:
                        os.environ.pop(k, None)
                    else:
                        os.environ[k] = v
            hdr = {}
            if headers:
                hdr.update(headers)
            if cookie:
                hdr["Cookie"] = cookie
            conn = HTTPConnection("127.0.0.1", self.port, timeout=12)
            conn.request("GET", path, headers=hdr)
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

    def _intro(self, path="/preview/intro"):
        return self._req(path, env={"PREVIEW_KEY": self.KEY}, cookie=self._cookie())

    def test_preview_404_without_cookie(self):
        for path in ("/preview/intro", "/preview/intro?play=1", "/preview/intro?seen=1"):
            status, _, _ = self._req(path)
            self.assertEqual(status, 404, path)
            status, _, _ = self._req(path, env={"PREVIEW_KEY": self.KEY})
            self.assertEqual(status, 404, path + " key set, no cookie")

    def test_cookie_unlocks_intro_and_sets_noindex(self):
        status, body, hdrs = self._intro()
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
        self.assertIn(b"min-height: 44px", body)
        self.assertIn(b'id="wi-replay"', body)
        self.assertIn(b"Replay intro", body)
        self.assertIn(b"Know the Water. Live the Coast.", body)
        self.assertIn(b"cb-wave-intro-seen", body)
        self.assertIn(b"prefers-reduced-motion", body)
        self.assertIn(b'id="conditions"', body)
        self.assertIn(b"The Coastal Brief", body)
        # No extra overlay tagline — the real masthead already carries it.
        self.assertNotIn(b'class="wi-motto"', body)
        self.assertNotIn(b'id="wi-motto"', body)

    def test_duration_is_brief(self):
        import wave_intro
        # Ed (v4): 2.0s hard max in total, aiming for about 1.7-1.9s.
        self.assertGreaterEqual(wave_intro.DURATION_MS, 1400)
        self.assertLessEqual(wave_intro.DURATION_MS, 2000)
        self.assertLessEqual(wave_intro.HARD_MAX_MS, 2000)
        status, body, _ = self._intro()
        self.assertEqual(status, 200)
        self.assertIn(b"var DURATION = %d" % wave_intro.DURATION_MS, body)
        self.assertIn(b"var HARD_MAX = %d" % wave_intro.HARD_MAX_MS, body)
        self.assertIn(b"requestAnimationFrame", body)
        self.assertIn(b"getBoundingClientRect", body)
        self.assertIn(b"wave-settle", body)
        self.assertIn(b"mapRule", body)
        self.assertIn(b"wi-aged-brass", body)

    def test_playback_rules(self):
        status, body, _ = self._intro()
        self.assertEqual(status, 200)
        self.assertIn(b"cb-wave-intro-seen-at", body)
        self.assertIn(b"12 * 60 * 60 * 1000", body)
        self.assertIn(b"sessionStorage.getItem(KEY) === \"1\"", body)
        self.assertIn(b'localStorage.getItem(TS_KEY)', body)
        self.assertIn(b"sameOriginReferrer", body)
        self.assertIn(b"document.referrer", body)
        self.assertIn(b"location.origin", body)
        self.assertIn(b"new URL(document.referrer)", body)
        self.assertIn(b"back_forward", body)
        self.assertIn(b"performance.navigation.type === 2", body)
        self.assertIn(b'params.get("play") === "1"', body)
        self.assertIn(b'q.get("play") === "1"', body)
        self.assertIn(b"prefers-reduced-motion: reduce", body)
        self.assertIn(b"var REDUCE_MS = 200", body)
        self.assertIn(b"skip.focus()", body)
        self.assertIn(b"Escape", body)
        # ?play=1 is still a review override.
        status, body, _ = self._intro("/preview/intro?play=1")
        self.assertEqual(status, 200)
        self.assertIn(b'id="wave-intro"', body)

    def test_no_autoplay_media(self):
        status, body, _ = self._intro()
        self.assertEqual(status, 200)
        self.assertNotIn(b"<audio", body)
        self.assertNotIn(b"<video", body)
        self.assertNotRegex(body.lower(), rb"<[^>]+\bautoplay\b")
        self.assertNotIn(b"new Audio", body)
        self.assertIn(b"data-sound-hook", body)
        self.assertIn(b'id="wi-sound" hidden', body)

    def test_session_and_skip_hooks(self):
        status, body, _ = self._intro()
        self.assertEqual(status, 200)
        self.assertIn(b'sessionStorage.setItem(KEY, "1")', body)
        self.assertIn(b"Escape", body)
        self.assertIn(b"skip.focus()", body)
        self.assertIn(b"prefers-reduced-motion: reduce", body)
        self.assertIn(b'classList.add("intro-seen")', body)

    def test_animations_are_compositor_only(self):
        status, body, _ = self._intro()
        css = body[body.find(b'id="wave-intro-css"'):body.find(b"</style>")]
        # Path d is driven from rAF, not CSS. Any leftover keyframes must
        # only change compositor properties.
        props = set()
        for block in re.findall(rb"@keyframes[^{]+\{(.+?)\n\}", css, re.S):
            for prop in re.findall(rb"([a-z-]+)\s*:", block):
                if prop in (b"from", b"to") or prop.endswith(b"%") or prop.decode().replace(".", "").isdigit():
                    continue
                if re.fullmatch(rb"\d+%", prop):
                    continue
                props.add(prop.decode())
        allowed = {"transform", "opacity", "stroke-dashoffset"}
        self.assertFalse(set(props) - allowed, set(props) - allowed)
        # Confirm we did not add a CSS d animation (Safari does not support it).
        self.assertNotRegex(css, rb"@keyframes[^}]*\bd\s*:")

    def test_travelling_crest_and_no_background_swap(self):
        status, body, _ = self._intro()
        self.assertEqual(status, 200)
        css = body[body.find(b'id="wave-intro-css"'):body.find(b"</style>")]
        # The end-of-intro colour jump came from painting html/body navy while
        # playing; the page must keep its own background throughout.
        self.assertNotRegex(css, rb"\.intro-play[^{]*body[^{]*\{[^}]*background")
        self.assertNotRegex(css, rb"html\[data-wave-intro\]\.intro-play\s*,")
        # One live swell: a crest that travels across x on its own clock,
        # and a composited fill layer moved only by transform.
        self.assertIn(b"function crestAt(t)", body)
        self.assertIn(b"function delay(u, t, lag)", body)
        self.assertIn(b'class="wi-fill"', body)
        self.assertIn(b"translate3d(0,", body)
        # Stalls are capped so a long first frame never shows as a jump.
        self.assertIn(b"Math.min(dt, Math.max(34, 2 * ema))", body)
        # The 2.0s cap carries the clock forward instead of cutting the wave.
        self.assertIn(b"var floor = DURATION - (HARD_MAX - (now - playT0));", body)
        self.assertNotIn(b"DURATION + 600", body)
        # The brass line lands on the measured rule and hands off in-frame.
        self.assertIn(b"smin(brassRaw(x, t), ruleBox.y, SMIN_K)", body)
        self.assertIn(b"intro-rule-live", body)
        # v4: a soft, layered leading edge (translucent wash layers and
        # trailing ripples) instead of a hard mask, with no filters or blur,
        # and the overlay only leaves once the faintest wash is off-screen.
        self.assertGreaterEqual(body.count(b'class="wi-wash '), 3)
        self.assertGreaterEqual(body.count(b"wi-ripple wi-ripple-"), 1)
        self.assertIn(b"function washY(x, t, f)", body)
        self.assertIn(b"state.minWash > vh + 1", body)
        overlay = body[body.find(b'id="wave-intro"'):body.find(b'id="wi-skip"')]
        for banned in (b"<filter", b"feGaussianBlur", b"<mask", b"blur("):
            self.assertNotIn(banned, overlay)
        self.assertNotRegex(css, rb"filter\s*:")
        # No video files in the product.
        self.assertNotIn(b".mp4", body)
        self.assertNotIn(b".webm", body)

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
        status, body, hdrs = self._req("/", env={"PREVIEW_KEY": self.KEY}, cookie=self._cookie())
        self.assertEqual(status, 200)
        self.assertNotIn(b"data-wave-intro", body)
        self.assertNotIn(b'id="wave-intro"', body)
        self.assertNotIn("noindex", hdrs.get("x-robots-tag", ""))

    def test_hub_lists_the_intro(self):
        status, body, _ = self._req("/preview", env={"PREVIEW_KEY": self.KEY}, cookie=self._cookie())
        self.assertEqual(status, 200)
        self.assertIn(b'href="/preview/intro?play=1"', body)
