"""/wind theme (Ed t354u): /wind uses the site's own theme preference (localStorage "coastalBrief.theme",
same as the Morning Brief and dashboard toggles; nothing stored = follow the phone), applies it before
first paint, stays in sync live (storage event, phone appearance change, back/forward cache), and has a
discreet 44 px sun/moon toggle in the top bar that writes the same preference. A switch repaints the
Census coastline and particle palette in place (no reload, same view, data and animation)."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HTML = (ROOT / "wind.html").read_text()
CSS = (ROOT / "wind.css").read_text()
JS = (ROOT / "wind-viewer.js").read_text()
ENGINE = (ROOT / "wind-lab.js").read_text()
COAST = (ROOT / "wind-coast.js").read_text()
KEY = "coastalBrief.theme"


class SharedPreference(unittest.TestCase):
    def test_same_key_as_main_site(self):
        app = (ROOT / "app.js").read_text()
        self.assertIn('const THEME_STORE = "%s";' % KEY, app)                       # dashboard toggle
        brief = (ROOT / "brief.py").read_text()
        self.assertIn('localStorage.setItem("%s",n)' % KEY, brief)                   # Morning Brief toggle
        self.assertIn('localStorage.getItem("%s")' % KEY, HTML)
        self.assertIn('const THEME_STORE = "%s";' % KEY, JS)
        self.assertIn("localStorage.setItem(THEME_STORE, t)", JS)
        self.assertEqual(set(re.findall(r'"(coastalBrief\.theme[^"]*)"', HTML + JS)), {KEY})

    def test_pre_paint_script_in_head_before_css(self):
        head = HTML.split("</head>")[0]
        script = head.index('localStorage.getItem("%s")' % KEY)
        self.assertLess(script, head.index('rel="stylesheet"'))
        self.assertLess(script, head.index('rel="preload"'))
        # Same resolution as the site: ?theme= override, then the stored choice, then the phone's appearance.
        self.assertIn("[?&]theme=(light|dark)", head)
        self.assertIn('if (t !== "light" && t !== "dark") t = window.matchMedia && matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";', head)
        self.assertIn('d.setAttribute("data-theme", t)', head)
        # toggle icon is CSS-driven from data-theme, so the right icon is there at first paint too
        self.assertIn('html[data-theme="dark"] .w-theme .i-sun { display: block; }', CSS)

    def test_live_sync_hooks(self):
        self.assertIn('window.addEventListener("storage"', JS)
        self.assertIn("e.key === THEME_STORE", JS)
        self.assertIn('matchMedia("(prefers-color-scheme: dark)")', JS)
        self.assertIn('addEventListener("change", onSys)', JS)
        self.assertIn("if (!stored() && !qTheme)", JS)                 # a stored choice beats the phone setting
        self.assertIn('window.addEventListener("pageshow"', JS)        # Safari back/forward cache
        self.assertIn("e.persisted", JS)


class Toggle(unittest.TestCase):
    def test_markup_aria_and_placement(self):
        top = HTML[HTML.index('<header class="w-top">'):HTML.index("</header>")]
        self.assertIn('<button type="button" class="w-theme" id="w-theme" aria-label="Night mode" aria-pressed="false"', top)
        ctl = HTML[HTML.index('<nav class="w-ctl"'):HTML.index("</nav>")]
        self.assertNotIn("w-theme", ctl)                                  # clear of the bottom wind controls
        for svg in re.findall(r"<svg[^>]*>", top):
            self.assertIn('aria-hidden="true"', svg)
        self.assertIn('tbtn.setAttribute("aria-pressed", String(dark))', JS)

    def test_touch_target_44px(self):
        rule = re.search(r"\.w-theme \{([^}]*)\}", CSS).group(1)
        self.assertIn("width: 44px", rule)
        self.assertIn("height: 44px", rule)
        self.assertIn("flex: none", rule)
        self.assertIn(".w-theme:focus-visible", CSS)

    def test_switch_repaints_in_place(self):
        self.assertIn("onTheme = function () { coast.restyle(coastStyle()); wind.setDark(dark); };", JS)
        self.assertIn("l.restyle = function (o)", COAST)
        self.assertIn("x.clearRect(0, 0, t.width, t.height)", COAST)
        self.assertIn("setDark: function (on)", ENGINE)
        self.assertNotIn("location.reload", JS)
        self.assertNotIn(".redraw()", COAST)                              # no blank tiles on a switch
        # palettes unchanged
        self.assertIn("--coast-land: #F6F1E7", CSS)
        self.assertIn("--coast-land: #1B4263", CSS)

    def test_still_esri_free(self):
        for t in (HTML, CSS, JS, COAST):
            self.assertNotIn("arcgisonline", t)
            self.assertNotIn("arcgis.com", t)


if __name__ == "__main__":
    unittest.main()
