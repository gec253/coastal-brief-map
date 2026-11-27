"""Ed t468u (Nov 25 2026): one Light / Dark / Auto theme system on every public page.

Every public HTML route carries the shared head boot script (data-theme set before <body>, so no
flash), exactly one accessible control, and the wiring script, with NAV_V2 off, with the preview
cookie (NAV_V2 preview) and with NAV_V2=1. Auto follows prefers-color-scheme; no sunset rule."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import sprint_home  # noqa: E402
import theme_toggle  # noqa: E402

KEY = "preview-test-key-24-chars-ok"
ENV_KEYS = ("PREVIEW_KEY", "NAV_V2", "MORNING_BRIEF_ENABLED", "FRESHWATER_ENABLED", "HOME_SHOWCASE",
            "PUBLIC_WHATS_BITING", "PUBLIC_RAMPS", "PUBLIC_RAMP_MAP")
LIVE = {"PUBLIC_WHATS_BITING": "1", "PUBLIC_RAMPS": "1", "MORNING_BRIEF_ENABLED": "1",
        "FRESHWATER_ENABLED": "1", "HOME_SHOWCASE": "1"}

ROUTES = ("/", "/?region=crystal-coast", "/?region=hatteras", "/?region=wilmington", "/?region=nags-head",
          "/?region=emerald-isle", "/?region=topsail", "/?region=falls-lake", "/?region=jordan-lake",
          "/?region=neuse-river", "/lake?region=falls-lake", "/lake?region=jordan-lake", "/lake?region=neuse-river",
          "/dashboard", "/dashboard?region=hatteras", "/brief?region=crystal-coast", "/brief?region=hatteras",
          "/brief?region=falls-lake", "/brief?region=topsail", "/catch-wall", "/coastal-life", "/photos",
          "/ramps", "/ramps/baa-beaufort", "/reports", "/reports/crystal-coast",
          "/reports/crystal-coast/when-the-sound-turns-cold", "/wind", "/radar", "/feedback", "/?region=nowhere")

CONTROL = b'role="radiogroup" aria-label="Color theme"'
LEGACY = (b'id="theme-toggle"', b'id="w-theme"', b'id="mh-theme"')


class Server(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import server
        cls.server = server
        cls.httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.port = cls.httpd.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def _req(self, path, env=None, cookie=None):
        saved = {k: os.environ.get(k) for k in ENV_KEYS}
        try:
            for k in ENV_KEYS:
                os.environ.pop(k, None)
            for k, v in (env or {}).items():
                os.environ[k] = v
            conn = HTTPConnection("127.0.0.1", self.port, timeout=90)
            conn.request("GET", path, headers={"Cookie": cookie} if cookie else {})
            r = conn.getresponse()
            body = r.read()
            conn.close()
            return r.status, body
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    def _cookie(self):
        return "%s=%s" % (self.server.PREVIEW_COOKIE, self.server._preview_cookie_value(KEY))

    def _check(self, path, body, state):
        where = "%s [%s]" % (path, state)
        # boot script is the first thing in <head>, so data-theme is set before <body> is parsed
        self.assertRegex(body, rb"<head\b[^>]*>\s*<script data-cb-theme>\(function\(\)\{var d=document\.documentElement",
                         where)
        self.assertLess(body.index(b"<script data-cb-theme>"), body.index(b"<body"), where)
        self.assertEqual(body.count(CONTROL), 1, where)
        i = body.index(CONTROL)
        self.assertLess(body.index(b"<body"), i, where)
        ctl = body[body.rfind(b"<div", 0, i):body.index(b"</div>", i)]
        self.assertEqual(ctl.count(b'role="radio"'), 3, where)
        for v in (b"light", b"dark", b"auto"):
            self.assertIn(b'data-v="%s"' % v, ctl, where)
        for old in LEGACY:
            self.assertNotIn(old, body, where)
        self.assertIn(b"window.__cbTheme;if(!T)return", body[i:], where)  # wiring runs after the control
        self.assertEqual(body.count(b"window.__cbTheme={"), 1, where)

    def _all(self, env, cookie, state, nav_expected):
        for path in ROUTES:
            status, body = self._req(path, env=env, cookie=cookie)
            self.assertIn(status, (200, 404), path)
            if path in ("/?region=nowhere", "/brief?region=topsail"):
                self.assertIn(b"<title>", body, path)
            self._check(path, body, state)
            if nav_expected and path not in ("/wind", "/radar"):
                if b"<html lang=\"en\" data-helm" in body:   # Signature Helm homepage: its own masthead and Menu
                    self.assertIn(b'<header class="bridge">', body, path)
                    self.assertIn(b'<nav class="nav" aria-label="Sections">', body, path)
                    continue
                self.assertIn(b'class="cbn"', body, "%s [%s] NAV_V2 masthead missing" % (path, state))


class EveryPublicRoute(Server):
    def test_nav_v2_off(self):
        self._all(LIVE, None, "NAV_V2 off", False)
        _, body = self._req("/", env=LIVE)
        self.assertNotIn(b'class="cbn"', body)

    def test_preview_cookie_nav_v2_preview(self):
        self._all(dict(LIVE, PREVIEW_KEY=KEY), self._cookie(), "preview cookie", True)

    def test_nav_v2_env_on(self):
        self._all(dict(LIVE, NAV_V2="1"), None, "NAV_V2=1", True)

    def test_nav_v2_control_in_new_masthead_tools(self):
        for path in ("/reports", "/ramps", "/brief?region=crystal-coast", "/dashboard", "/lake?region=falls-lake",
                     "/catch-wall", "/feedback"):
            _, body = self._req(path, env=dict(LIVE, NAV_V2="1"))
            t = body.find(b'<div class="cbm-tools">')
            self.assertGreaterEqual(t, 0, path)
            self.assertLess(t, body.index(CONTROL), path)
            self.assertLess(body.index(CONTROL), body.index(b"</header>", t), path)

    def test_homepage_control_in_masthead_ear(self):
        for env in (LIVE, dict(LIVE, NAV_V2="1")):
            _, body = self._req("/", env=env)
            ear = body.index(b'<div class="cbm-tools">')   # Signature Helm masthead tools (t534u)
            self.assertLess(ear, body.index(CONTROL))
            self.assertLess(body.index(CONTROL), body.index(b"</header>", ear))

    def test_viewers_use_compact_menu(self):
        for path in ("/wind", "/radar"):
            _, body = self._req(path, env=LIVE)
            self.assertIn(b'class="cbt-menu" data-cb-theme-menu', body, path)
            self.assertIn(b'aria-haspopup="true" aria-expanded="false"', body, path)

    def test_not_public_routes_untouched(self):
        for path in ("/api/health", "/robots.txt", "/sitemap.xml", "/styles.css"):
            _, body = self._req(path, env=LIVE)
            self.assertNotIn(b"data-cb-theme", body, path)


class Module(unittest.TestCase):
    def test_auto_follows_device_not_sunset(self):
        boot = theme_toggle.BOOT.lower()
        self.assertIn("prefers-color-scheme: dark", boot)
        self.assertIn("addeventlistener('change'", boot)          # reacts live to the phone switching
        for word in ("sunset", "sunrise", "gethours", "night", "astro"):
            self.assertNotIn(word, boot)

    def test_one_key_auto_is_no_value_and_stale_values_removed(self):
        b = theme_toggle.BOOT
        self.assertEqual(theme_toggle.STORE, "coastalBrief.theme")
        self.assertIn("K='coastalBrief.theme'", b)
        self.assertIn("if(np==='auto')localStorage.removeItem(K);else localStorage.setItem(K,np)", b)
        self.assertIn("if(s!==null&&s!=='light'&&s!=='dark'){localStorage.removeItem(K)", b)
        self.assertIn("addEventListener('storage'", b)      # other tabs
        self.assertIn("addEventListener('pageshow'", b)     # back/forward cache
        self.assertNotIn("sessionStorage", b)

    def test_control_is_accessible(self):
        c = theme_toggle.control_html()
        self.assertIn(CONTROL.decode(), c)
        self.assertEqual(c.count('role="radio"'), 3)
        self.assertEqual(c.count('tabindex="0"'), 1)
        for label in ("Light theme", "Dark theme", "Auto theme (follow this device)"):
            self.assertIn('aria-label="%s"' % label, c)
        self.assertRegex(theme_toggle.CSS, r"\.cbt-b\{[^}]*min-width:44px;min-height:44px")
        self.assertRegex(theme_toggle.CSS, r"\.cbt-m\{[^}]*width:44px;height:44px")
        s = theme_toggle.SCRIPT
        for key in ("ArrowRight", "ArrowLeft", "Home", "End", "Escape"):
            self.assertIn(key, s)

    def test_paint_is_idempotent_and_presentation_only(self):
        data = sprint_home.page("hybrid", None, public=True)
        once = theme_toggle.paint(data)
        self.assertEqual(theme_toggle.paint(once), once)
        stripped = (once.replace(theme_toggle.BOOT.encode(), b"").replace(theme_toggle.CSS.encode(), b"")
                    .replace(theme_toggle.SCRIPT.encode(), b"").replace(theme_toggle.control_html().encode(), b""))
        self.assertEqual(stripped.replace(b"<head>\n", b"<head>", 1).replace(b"<head>\n", b"<head>"),
                         theme_toggle._rewrite_styles(data).replace(b"<head>\n", b"<head>"))

    def test_labels_and_warnings_untouched(self):
        data = sprint_home.page("hybrid", "crystal-coast", public=True)
        out = theme_toggle.paint(data)
        txt = lambda x: re.sub(rb"(?s)<(script|style|svg)\b.*?</\1>", b"", x)
        for word in (b"Observed", b"OBSERVED", b"Predicted", b"PREDICTED", b"Forecast", b"FORECAST", b"Warning", b"Advisory"):
            self.assertEqual(txt(data).count(word), txt(out).count(word), word)
        self.assertNotIn(b"display:none", theme_toggle.CSS.replace(".cbt-pop[hidden]{display:none}", "")
                         .replace(".cbt-pop::before{display:none}", "").replace("{.cbt{display:none}}", "")
                         .replace(".cbt-i{display:none;", "").encode())

    def test_page_ok_scope(self):
        for p in ("/", "/dashboard", "/lake", "/brief", "/reports/x/y", "/ramps/a", "/wind", "/radar", "/feedback",
                  "/catch-wall/", "/coastal-life", "/photos"):
            self.assertTrue(theme_toggle.page_ok(p), p)
        for p in ("/preview/home-b", "/api/brief", "/admin", "/lab/wind", "/preview", "/preview/reports"):
            self.assertFalse(theme_toggle.page_ok(p), p)


# Runs the real head boot script in Node with a tiny DOM, localStorage and matchMedia stub.
_HARNESS = r"""
const [boot, planJson] = process.argv.slice(-2), plan = JSON.parse(planJson);
const store = new Map(Object.entries(plan.stored || {}));
let sysDark = !!plan.sysDark; const sysL = [];
const attrs = {}; const winL = {};
global.document = {documentElement: {setAttribute(k, v) { attrs[k] = String(v); }, getAttribute(k) { return k in attrs ? attrs[k] : null; }}};
global.localStorage = {getItem: k => store.has(k) ? store.get(k) : null, setItem: (k, v) => store.set(k, String(v)), removeItem: k => store.delete(k)};
global.location = {search: plan.search || ""};
global.CustomEvent = function (t, o) { this.type = t; this.detail = o && o.detail; };
global.window = {matchMedia: q => ({get matches() { return /dark/.test(q) ? sysDark : false; }, addEventListener: (t, f) => sysL.push(f)}),
  addEventListener: (t, f) => (winL[t] = winL[t] || []).push(f), dispatchEvent: e => (winL[e.type] || []).forEach(f => f(e))};
new Function(boot.replace(/^<script[^>]*>/, "").replace(/<\/script>$/, ""))();
const out = [];
const snap = tag => out.push({tag, theme: attrs["data-theme"], pref: attrs["data-theme-pref"], stored: store.has("coastalBrief.theme") ? store.get("coastalBrief.theme") : null,
  mq: window.matchMedia("(prefers-color-scheme: dark)").matches});
snap("load");
for (const step of plan.steps || []) {
  if (step.sys !== undefined) { sysDark = step.sys; sysL.forEach(f => f({matches: sysDark})); }
  if (step.set) window.__cbTheme.set(step.set);
  snap(step.tag);
}
console.log(JSON.stringify({out, events: (winL["cb:theme"] || []).length}));
"""


@unittest.skipUnless(shutil.which("node"), "node not installed")
class BootBehaviour(unittest.TestCase):
    """Ed t469u item 3: Auto is the default, follows the device live; Light/Dark persist until changed."""

    def run_boot(self, plan):
        r = subprocess.run(["node", "-e", _HARNESS, "--", theme_toggle.BOOT, json.dumps(plan)],
                           capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        return {x["tag"]: x for x in json.loads(r.stdout)["out"]}

    def test_new_visitor_is_auto_and_follows_device_live(self):
        o = self.run_boot({"sysDark": False, "steps": [{"tag": "phone-dark", "sys": True}, {"tag": "phone-light", "sys": False}]})
        self.assertEqual((o["load"]["pref"], o["load"]["theme"], o["load"]["stored"]), ("auto", "light", None))
        self.assertEqual((o["phone-dark"]["theme"], o["phone-dark"]["mq"]), ("dark", True))
        self.assertEqual(o["phone-light"]["theme"], "light")
        self.assertIsNone(o["phone-light"]["stored"])           # Auto never writes a value
        o = self.run_boot({"sysDark": True})
        self.assertEqual((o["load"]["pref"], o["load"]["theme"]), ("auto", "dark"))

    def test_explicit_choice_persists_and_ignores_device_until_changed(self):
        o = self.run_boot({"sysDark": False, "steps": [{"tag": "dark", "set": "dark"}, {"tag": "phone-dark", "sys": True},
                                                       {"tag": "light", "set": "light"}, {"tag": "phone-light", "sys": False},
                                                       {"tag": "phone-dark2", "sys": True}, {"tag": "auto", "set": "auto"}]})
        self.assertEqual((o["dark"]["theme"], o["dark"]["stored"]), ("dark", "dark"))
        self.assertEqual((o["light"]["theme"], o["light"]["stored"]), ("light", "light"))
        self.assertEqual(o["phone-dark2"]["theme"], "light")      # explicit Light holds while the phone is dark
        self.assertEqual((o["auto"]["pref"], o["auto"]["theme"], o["auto"]["stored"]), ("auto", "dark", None))
        for saved, phone in (("dark", False), ("light", True)):   # a new page load keeps the saved choice
            o = self.run_boot({"sysDark": phone, "stored": {"coastalBrief.theme": saved}, "steps": [{"tag": "flip", "sys": not phone}]})
            self.assertEqual((o["load"]["theme"], o["load"]["pref"]), (saved, saved))
            self.assertEqual(o["flip"]["theme"], saved)

    def test_stale_value_becomes_auto(self):
        o = self.run_boot({"sysDark": True, "stored": {"coastalBrief.theme": "night"}})
        self.assertEqual((o["load"]["pref"], o["load"]["theme"], o["load"]["stored"]), ("auto", "dark", None))


class Components(unittest.TestCase):
    """Ed t469u items 1-2: /feedback dark styling; dashboard tide charts follow a live switch."""

    def test_feedback_has_dark_tokens_that_follow_the_choice(self):
        src = (Path(__file__).resolve().parents[1] / "feedback.py").read_text()
        self.assertIn(":root{--paper:#0E2433;--page:#071C29;--ink:#F3EEE3", src)
        css = theme_toggle.rewrite_css("@media (prefers-color-scheme:dark){:root{--page:#071C29}}")
        self.assertIn(':root:where(:root[data-theme="dark"]){--page:#071C29}', css)   # forced Dark on a light phone

    def test_tide_chart_colors_are_css_driven(self):
        root = Path(__file__).resolve().parents[1]
        js = (root / "dashboard.js").read_text()
        body = js[js.index("function drawTideChart("):js.index("// ---------- secondary")]
        self.assertNotRegex(body, r'(fill|stroke|stop-color)="#')     # no baked-in colors: CSS repaints live
        self.assertNotIn("data-theme", body)
        css = (root / "styles.css").read_text()
        for sel in ('[data-theme="dark"] .tide-chart .tf-top', '[data-theme="dark"] .tide-chart .tm-h'):
            self.assertIn(sel, css)
        self.assertIn('html[data-theme="dark"] .tide-curve polyline{stroke:#A9D6CC}', theme_toggle.CSS)


if __name__ == "__main__":
    unittest.main()
