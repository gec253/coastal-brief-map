"""Ed t392u/t393u: homepage day/night toggle and Catch Wall theme on the site-wide coastalBrief.theme system."""
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
        self.assertIn("aria-pressed", theme_toggle.BUTTON)
        self.assertIn('aria-label="Switch to dark mode"', theme_toggle.BUTTON)


class ToggleCss(unittest.TestCase):
    def test_public_stylesheet_is_concept_b_with_toggle(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        b = open(os.path.join(root, "preview/sprint-home/hybrid-b.css")).read()
        pub = open(os.path.join(root, "preview/sprint-home/hybrid.css")).read()
        self.assertEqual(pub, b)
        self.assertIn(".mh-theme{position:absolute", pub)
        self.assertRegex(pub, r"\.mh-theme::after\{[^}]*bottom:-16px")


class CatchWallTheme(unittest.TestCase):
    def test_wall_css_follows_saved_theme(self):
        import catch_wall_preview
        tag = catch_wall_preview.style_tag(public=True).encode()
        out = theme_toggle.rewrite_styles(tag)
        self.assertIn(b':where(html[data-theme="dark"]) .share-dlg{', out)
        self.assertIn(b':where(html:not([data-theme="light"])) .share-dlg{', out)
        self.assertIn(b'html[data-sprint="hybrid"]:where(html[data-theme="dark"])', out)

    def test_plain_styles_untouched(self):
        page = b'<html><head><style id="a">.x{color:red}</style><style id="b">@media (prefers-color-scheme:dark){.y{color:#fff}}</style></head></html>'
        out = theme_toggle.rewrite_styles(page)
        self.assertIn(b'<style id="a">.x{color:red}</style>', out)
        self.assertIn(b':where(html[data-theme="dark"]) .y{color:#fff}', out)

    def test_server_applies_it_to_public_wall_only(self):
        import inspect
        import server
        src = inspect.getsource(server._public_catch_wall_redesign)
        self.assertIn("theme_toggle.rewrite_styles(_paint_folio_header_on_public_catch_wall(data))", src)
        self.assertNotIn("theme_toggle", inspect.getsource(server._paint_public_catch_wall))

    def test_apply_is_idempotent(self):
        page = b'<html><head><style>.a{}</style></head><body><header class="mh"><div class="mh-ear"><div class="mh-ear-in"><p>d</p></div></div></header></body></html>'
        once = theme_toggle.apply(page)
        self.assertEqual(theme_toggle.apply(once), once)


class ToggleRoute(_Base):
    for _n in [n for n in dir(_Base) if n.startswith("test_")]:
        locals()[_n] = None
    del _n

    def test_public_homepage_has_toggle(self):
        for path in ("/", "/?region=hatteras"):
            html = self._get(path)[2]
            self.assertEqual(html.count(b'id="mh-theme"'), 1, path)
            self.assertEqual(html.count(b"window.__cbTheme={"), 1, path)
            self.assertIn(b':where(html[data-theme="dark"])', html)
            self.assertRegex(html, rb"<head>\s*<meta charset=\"utf-8\">\s*<script>\(function\(\)\{var d=document.documentElement,K='coastalBrief.theme'")

    def test_preview_b_has_toggle_boot_and_forced_dark(self):
        st, _h, html = self._get("/preview/home-b", cookie=True)
        self.assertEqual(st, 200)
        self.assertRegex(html, rb"<meta charset=\"utf-8\">\s*<script>\(function\(\)\{var d=document.documentElement,K='coastalBrief.theme'")
        self.assertIn(b'<button type="button" class="mh-theme" id="mh-theme" aria-pressed="false"', html)
        self.assertIn(b':where(html[data-theme="dark"])', html)
        i = html.index(b'class="mh-ear-in"')
        self.assertLess(i, html.index(b'id="mh-theme"'))
        self.assertLess(html.index(b'id="mh-theme"'), html.index(b'class="mh-plate'))


del _Base
