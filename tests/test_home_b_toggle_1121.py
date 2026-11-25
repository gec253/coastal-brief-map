"""Ed t392u: day/night toggle on /preview/home-b, on the site-wide coastalBrief.theme system.

Ed t468u: the public homepage and /preview/home-b now use the one shared Light / Dark / Auto system."""
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import theme_toggle  # noqa: E402
from test_hybrid_public import HybridPublic  # noqa: E402

_Base = HybridPublic
del HybridPublic  # do not re-run the public suite from this module


class ThemeCss(unittest.TestCase):
    def test_dark_block_split_into_system_and_forced(self):
        out = theme_toggle.rewrite_css("a{x:1}@media (prefers-color-scheme:dark){:root{--a:1}.b,.c{y:2}@media (min-width:9px){.d{z:3}}}")
        self.assertIn('@media (prefers-color-scheme:dark){:root:where(:root:not([data-theme="light"])){--a:1}', out)
        self.assertIn(':where(html:not([data-theme="light"])) .b,:where(html:not([data-theme="light"])) .c{y:2}', out)
        self.assertIn('}:root:where(:root[data-theme="dark"]){--a:1}', out)
        self.assertIn('@media (min-width:9px){:where(html[data-theme="dark"]) .d{z:3}}', out)
        self.assertTrue(out.startswith("a{x:1}"))

    def test_html_attribute_selectors_keep_specificity(self):
        s = theme_toggle._scope_sel('html[data-sprint="hybrid"][data-night="b"] .x', theme_toggle.FORCE)
        self.assertEqual(s, 'html[data-sprint="hybrid"][data-night="b"]:where(html[data-theme="dark"]) .x')

    def test_boot_uses_site_key(self):
        self.assertIn("coastalBrief.theme", theme_toggle.BOOT)
        ctl = theme_toggle.control_html()
        self.assertIn('role="radiogroup" aria-label="Color theme"', ctl)
        self.assertEqual(ctl.count('role="radio"'), 3)


class ToggleCss(unittest.TestCase):
    def test_toggle_only_in_b_stylesheet(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        b = open(os.path.join(root, "preview/sprint-home/hybrid-b.css")).read()
        pub = open(os.path.join(root, "preview/sprint-home/hybrid.css")).read()
        self.assertIn(".mh-theme{position:absolute", b)
        self.assertRegex(b, r"\.mh-theme::after\{[^}]*bottom:-16px")
        self.assertNotIn("mh-theme", pub)


class ToggleRoute(_Base):
    for _n in [n for n in dir(_Base) if n.startswith("test_")]:
        locals()[_n] = None
    del _n

    def test_public_homepage_has_shared_control(self):
        for path in ("/", "/?region=hatteras"):
            html = self._get(path)[2]
            self.assertNotIn(b'id="mh-theme"', html)
            self.assertEqual(html.count(b'role="radiogroup" aria-label="Color theme"'), 1, path)
            self.assertIn(b"__cbTheme", html)
            self.assertIn(b':where(html[data-theme="dark"])', html)

    def test_preview_b_has_toggle_boot_and_forced_dark(self):
        st, _h, html = self._get("/preview/home-b", cookie=True)
        self.assertEqual(st, 200)
        self.assertRegex(html, rb"<head>\s*<script data-cb-theme>\(function\(\)\{var d=document.documentElement,K='coastalBrief.theme'")
        self.assertNotIn(b'id="mh-theme"', html)
        self.assertEqual(html.count(b'role="radiogroup" aria-label="Color theme"'), 1)
        self.assertIn(b':where(html[data-theme="dark"])', html)
        i = html.index(b'class="mh-ear-in"')
        c = html.index(b'role="radiogroup" aria-label="Color theme"')
        self.assertLess(i, c)
        self.assertLess(c, html.index(b'class="mh-plate'))


del _Base
