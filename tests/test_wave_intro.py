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
        # Ed (v7): about 1.0-1.3s total, hard cap 1.5s even after a stall.
        self.assertGreaterEqual(wave_intro.DURATION_MS, 1000)
        self.assertLessEqual(wave_intro.DURATION_MS, 1300)
        self.assertLessEqual(wave_intro.HARD_MAX_MS, 1500)
        self.assertGreaterEqual(wave_intro.HARD_MAX_MS, wave_intro.DURATION_MS)
        status, body, _ = self._intro()
        self.assertEqual(status, 200)
        self.assertIn(b"var DURATION = %d" % wave_intro.DURATION_MS, body)
        self.assertIn(b"var HARD_MAX = %d" % wave_intro.HARD_MAX_MS, body)
        self.assertIn(b"requestAnimationFrame", body)
        self.assertIn(b"getBoundingClientRect", body)
        self.assertIn(b"wave-settle", body)
        self.assertIn(b"mapRule", body)
        self.assertIn(b"wi-brass-aged", body)

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
        # v5: reduced motion paints no overlay at all (the page with its
        # static rule), decided in the head before first paint.
        self.assertNotIn(b"REDUCE_MS", body)
        boot = body[body.find(b'var force = q.get("play") === "1"'):]
        self.assertRegex(boot, rb'if \(reduce\) \{\s*//[^\n]*\n\s*document\.documentElement\.classList\.add\("intro-seen"\);\s*return;')
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
        self.assertIn(b"function delay(u, t, amp)", body)
        self.assertIn(b'class="wi-fill"', body)
        self.assertIn(b"translate3d(0,", body)
        # Stalls are capped so a long first frame never shows as a jump.
        self.assertIn(b"Math.min(dt, Math.max(34, 2 * ema))", body)
        # The 1.8s cap carries the clock forward instead of cutting the wave.
        self.assertIn(b"var floor = DURATION - (HARD_MAX - (now - playT0));", body)
        self.assertNotIn(b"DURATION + 600", body)
        # v5: ONE swell. No stepped translucent wash bands, no trailing
        # ripples, no mid-sequence rule swap; two or three opaque contours
        # (navy body + one or two bands) on the same crest.
        self.assertNotIn(b"wi-wash", body)
        self.assertNotIn(b"wi-ripple", body)
        self.assertNotIn(b"washY", body)
        self.assertNotIn(b"intro-rule-live", body)
        self.assertNotIn(b"intro-reduce", body)
        contours = body.count(b'class="wi-contour ') + body.count(b'class="wi-sheet"')
        self.assertGreaterEqual(contours, 2)
        self.assertLessEqual(contours, 3)
        self.assertIn(b"var LAGS = [", body)
        self.assertIn(b"var AMPS = [", body)
        self.assertIn(b"function layerY(x, t, k)", body)
        self.assertNotRegex(css, rb"\.wi-contour[^{]*\{[^}]*(fill-)?opacity")
        self.assertNotRegex(css, rb"\.wi-sheet[^{]*\{[^}]*(fill-)?opacity")
        # The real masthead rule is in its final state throughout: never
        # hidden, faded or swapped while the intro plays; the swell's brass
        # edge settles onto it through a smooth monotone remap.
        self.assertNotRegex(css, rb"intro-play[^{]*\.wave-settle")
        self.assertNotRegex(css, rb"\.wave-settle[^{]*\{[^}]*opacity:\s*0")
        self.assertNotIn(b"ensureAgedBrass", body)
        self.assertIn(b"function settle(y)", body)
        self.assertIn(b"Math.tanh((y - ruleBox.y) / SETTLE_W)", body)
        # The overlay is removed only once the whole swell is off-screen.
        self.assertIn(b"state.minTop > vh + 3", body)
        # The page itself is never restyled by the intro.
        self.assertNotRegex(css, rb"\.intro-play[^{]*(body|main|header|\.mast)[^{]*\{")
        overlay = body[body.find(b'id="wave-intro"'):body.find(b'id="wi-skip"')]
        for banned in (b"<filter", b"feGaussianBlur", b"<mask", b"blur("):
            self.assertNotIn(banned, overlay)
        self.assertNotRegex(css, rb"filter\s*:")
        # No video files in the product. site.webmanifest contains the letters
        # ".webm", so strip the manifest name before the check.
        no_manifest = body.replace(b"webmanifest", b"")
        self.assertNotIn(b".mp4", no_manifest)
        self.assertNotIn(b".webm", no_manifest)

    def test_v6_aged_brass_on_edge_and_rule(self):
        import wave_intro
        status, body, _ = self._intro()
        self.assertEqual(status, 200)
        css = body[body.find(b'id="wave-intro-css"'):body.find(b"</style>")]
        # Ed (v6): the aged-brass gradient is back on BOTH the swell's leading
        # edge and the real masthead rule; V5's solid rule is gone.
        stops = wave_intro._BRASS_STOPS.encode("utf-8")
        self.assertEqual(body.count(stops), 2)
        self.assertRegex(css, rb"\.wave-settle\s*\{[^}]*stroke:\s*url\(#wi-rule-aged\)")
        self.assertRegex(css, rb"\.wi-line-brass\s*\{[^}]*stroke:\s*url\(#wi-brass-aged\)")
        self.assertIn(b'id="wi-rule-aged" gradientUnits="userSpaceOnUse"', body)
        # The rule's gradient lives outside the overlay (which ends display:none).
        self.assertLess(body.find(b'id="wi-rule-aged"'), body.find(b'id="wave-intro"'))
        # The brass settles into the rule; it is never faded out.
        self.assertNotIn(b"wi-brass-fade", body)
        self.assertNotIn(b"BRASS_FADE", body)
        self.assertIn(b'clip-path="url(#wi-brass-clip)"', body)
        # Very restrained seafoam: one thin, low-opacity highlight.
        self.assertRegex(css, rb"\.wi-line-foam\s*\{[^}]*stroke-opacity:\s*0\.[0-5]\d*;")
        # Nothing of the page (the phone mini-bar is z-index 900) shows over the swell.
        z = re.search(rb"\.wave-intro\s*\{[^}]*z-index:\s*(\d+)", css)
        self.assertGreater(int(z.group(1)), 900)

    def test_v6_one_direction_motion_model(self):
        status, body, _ = self._intro()
        self.assertEqual(status, 200)
        # A positive-weight (quadratic B-spline) edge: no interpolating
        # overshoot, so if every sample only moves down, so does every pixel.
        self.assertIn(b"function curveD(xs, ys)", body)
        self.assertIn(b'd += " Q "', body)
        self.assertNotIn(b"Catmull", body)
        self.assertNotIn(b"D_TROUGH", body)
        self.assertIn(b"var dt = lastTs ? now - lastTs : 16.7;", body)
        js = (Path(__file__).resolve().parents[1] / "preview" / "wave-intro" / "wave-intro.js").read_text(encoding="utf-8")
        node = None
        for cand in ("/usr/local/bin/node", "/usr/bin/node"):
            if os.path.exists(cand):
                node = cand
                break
        if not node:
            self.skipTest("node not available")
        import json
        import subprocess
        harness = """
var store = {};
var stubEl = {getBoundingClientRect: function () { return RULE; }};
global.window = global;
global.innerWidth = VW; global.innerHeight = VH;
global.location = {search: "", pathname: "/x", origin: "http://x"};
global.sessionStorage = {getItem: function () { return "1"; }, setItem: function () {}, removeItem: function () {}};
global.localStorage = sessionStorage;
global.document = {getElementById: function () { return null; }, querySelector: function (q) { return q === ".wave-settle" ? stubEl : null; },
  addEventListener: function () {}, documentElement: {classList: {add: function () {}, remove: function () {}}}, referrer: ""};
global.addEventListener = function () {};
global.matchMedia = function () { return {matches: false}; };
global.requestAnimationFrame = function () { return 0; };
global.top = global;
""" + js + """
window.__wiMapRule();
var D = window.__wiDuration, out = {rate: window.__wiMaxDelayRate(), maxRate: window.__wiMaxRate, back: 0, worst: 0, exitMs: -1};
var xs = []; for (var i = 0; i <= 120; i++) xs.push(-0.05 * VW + 1.1 * VW * i / 120);
var prev = null;
for (var t = 0; t <= D; t += 1000 / 240) {
  var cur = xs.map(function (x) { return Math.min(window.__wiLayer(x, t, 2), window.__wiLayer(x, t, 1), window.__wiLayer(x, t, 0)); });
  var top = xs.map(function (x) { return window.__wiTop(x, t); });
  if (prev) for (var j = 0; j < xs.length; j++) { var dy = top[j] - prev[j]; if (dy < out.worst) out.worst = dy; if (dy < -1e-9) out.back++; }
  if (out.exitMs < 0 && Math.min.apply(null, top) > VH + 3) out.exitMs = t;
  var rev = top.reduce(function (a, y) { return a + Math.min(1, Math.max(0, y / VH)); }, 0) / top.length;
  if (out.rev0 === undefined) out.rev0 = rev;
  if (out.rev100 === undefined && t >= 100) out.rev100 = rev;
  if (out.rev500 === undefined && t >= 500) out.rev500 = rev;
  prev = top;
}
out.washUp = 0; out.wash0 = window.__wiWash(0);
for (var tw = 4; tw <= D; tw += 4) if (window.__wiWash(tw) > window.__wiWash(tw - 4) + 1e-12) out.washUp++;
console.log(JSON.stringify(out));
"""
        for vw, vh, rule in ((390, 844, (0, 390, 128)), (1280, 800, (272, 1008, 176))):
            src = (harness.replace("VW", str(vw)).replace("VH", str(vh))
                   .replace("RULE", json.dumps({"left": rule[0], "right": rule[1], "top": rule[2], "bottom": rule[2], "height": 0})))
            res = subprocess.run([node, "-e", src], capture_output=True, text=True, timeout=60)
            self.assertEqual(res.returncode, 0, res.stderr)
            out = json.loads(res.stdout.strip().splitlines()[-1])
            # d(delay)/dt < 1 everywhere: no local clock ever runs backwards.
            self.assertLess(out["rate"], out["maxRate"])
            self.assertLess(out["maxRate"], 1)
            # The leading edge never moves up anywhere: nothing is re-covered.
            self.assertEqual(out["back"], 0, out)
            # And the swell is fully off-screen in about 1.0-1.3s.
            self.assertGreaterEqual(out["exitMs"], 900, out)
            self.assertLessEqual(out["exitMs"], 1300, out)
            # Ed (v7): no solid-navy hold. The edge is on screen at frame 0,
            # a meaningful share is uncovered by 100ms and most by 500ms.
            self.assertGreaterEqual(out["rev0"], 0.06, out)
            self.assertGreaterEqual(out["rev100"], 0.15, out)
            self.assertGreaterEqual(out["rev500"], 0.5, out)
            # The wash only ever thins: what is under it only gets clearer.
            self.assertEqual(out["washUp"], 0, out)
            self.assertLess(out["wash0"], 0.9, out)

    def test_v7_overlay_never_blocks_the_page(self):
        status, body, _ = self._intro()
        self.assertEqual(status, 200)
        css = body[body.find(b'id="wave-intro-css"'):body.find(b"</style>")]
        # Ed (v7): the dashboard stays interactive under and through the
        # intro. The overlay takes no pointer events; only Skip does.
        self.assertRegex(css, rb"\.wave-intro\s*\{[^}]*pointer-events:\s*none")
        self.assertRegex(css, rb"\.wi-skip\s*\{[^}]*pointer-events:\s*auto")
        for sel, block in re.findall(rb"([^{}]+)\{([^}]*)\}", css):
            if re.search(rb"pointer-events:\s*auto", block):
                self.assertIn(b".wi-skip", sel, sel)
        js = body[body.find(b'var KEY = "cb-wave-intro-seen"'):]
        for m in re.finditer(rb"(\w+)\.style\.pointerEvents", js):
            self.assertEqual(m.group(1), b"skip")
        self.assertNotIn(b'role="dialog"', body)
        # The page renders underneath from frame 0: the wash is translucent
        # from the start and only Skip is opaque.
        self.assertIn(b"var WASH_FROM = 0.84", body)
        self.assertRegex(css, rb"\.wi-water \.wi-fill,\s*\.wi-water \.wi-svg\s*\{[^}]*opacity:\s*0\.84")
        # Ed (v7b): the phone mini-bar is shown from first paint UNDER the
        # wash and is never hidden or delayed during (or after) the intro.
        self.assertNotRegex(css, rb"\.mini-bar[^{]*\{[^}]*(visibility:\s*hidden|display:\s*none|opacity:\s*0)")
        self.assertNotRegex(css, rb"intro-play[^{]*\.mini-bar")
        # Pinned only until the first scroll/interaction, then the page's
        # normal glance-on-screen auto-hide takes over (no permanent override).
        self.assertRegex(css, rb"html\[data-wave-intro\]:not\(\.bar-released\) body\.glance-on-screen \.mini-bar\s*\{[^}]*transform:\s*none")
        self.assertNotRegex(css, rb"html\[data-wave-intro\] body\.glance-on-screen \.mini-bar")
        js = (Path(__file__).resolve().parents[1] / "preview" / "wave-intro" / "wave-intro.js").read_text(encoding="utf-8")
        self.assertIn('classList.add("bar-released")', js)
        for ev in ("scroll", "wheel", "touchstart", "pointerdown", "keydown"):
            self.assertIn('"%s"' % ev, js)
        self.assertNotRegex(js, r"setTimeout\([^)]*bar-released")
        # It sits below the overlay in z-order (mini-bar 900 in styles.css).
        page_css = (Path(__file__).resolve().parents[1] / "styles.css").read_text(encoding="utf-8")
        mz = re.search(r"\.mini-bar\s*\{[^}]*z-index:\s*(\d+)", page_css)
        oz = re.search(rb"\.wave-intro\s*\{[^}]*z-index:\s*(\d+)", css)
        self.assertLess(int(mz.group(1)), int(oz.group(1)))

    def test_public_dashboard_untouched(self):
        status, body, hdrs = self._req("/dashboard")
        self.assertEqual(status, 200)
        self.assertNotIn("noindex", hdrs.get("x-robots-tag", ""))
        self.assertNotIn(b"data-wave-intro", body)
        self.assertNotIn(b'id="wave-intro"', body)
        self.assertNotIn(b'id="wi-skip"', body)
        self.assertNotIn(b"Replay intro", body)
        self.assertNotIn(b"wave-intro-css", body)
        self.assertIn(b'data-home="folio"', body)
        self.assertIn(b'data-concept="a"', body)
        status, body, hdrs = self._req("/dashboard", env={"PREVIEW_KEY": self.KEY}, cookie=self._cookie())
        self.assertEqual(status, 200)
        self.assertNotIn(b"data-wave-intro", body)
        self.assertNotIn(b'id="wave-intro"', body)
        self.assertNotIn("noindex", hdrs.get("x-robots-tag", ""))

    def test_hub_lists_the_intro(self):
        status, body, _ = self._req("/preview", env={"PREVIEW_KEY": self.KEY}, cookie=self._cookie())
        self.assertEqual(status, 200)
        self.assertIn(b'href="/preview/intro?play=1"', body)
