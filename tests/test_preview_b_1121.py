"""Concept B preview gate (Ed t391u): /preview/home-b shows the real homepage with hybrid-b.css to the
preview cookie only; the public homepage never carries B."""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import sprint_home  # noqa: E402
import theme_toggle  # noqa: E402
from test_hybrid_public import HybridPublic  # noqa: E402

B_MARK = b"--rf-surface-warm"
_Base = HybridPublic
del HybridPublic  # do not re-run the public suite from this module


class PreviewB(_Base):
    for _n in [n for n in dir(_Base) if n.startswith("test_")]:
        locals()[_n] = None
    del _n

    def test_public_home_has_no_concept_b(self):
        for path in ("/", "/?region=hatteras", "/index.html"):
            s, h, b = self._get(path)
            self.assertEqual(s, 200, path)
            self.assertNotIn(B_MARK, b, path)
            self.assertNotIn(b"Concept B", b, path)
            # Ed t468u: inline dark blocks are rewritten by the shared theme system (theme_toggle.paint).
            self.assertIn(theme_toggle._rewrite_styles(sprint_home._CSS_COMMENT.sub("", sprint_home.style_tag("hybrid")).encode()), b, path)
        s, h, b = self._get("/", cookie=True)          # the cookie alone never changes "/"
        self.assertNotIn(B_MARK, b)

    def test_route_is_404_without_cookie(self):
        s, h, b = self._get("/preview/home-b")
        self.assertEqual(s, 404)
        self.assertNotIn(B_MARK, b)
        os.environ["PREVIEW_KEY"] = self.KEY
        s, h, b = self._get("/preview/home-b")         # key set, no cookie
        self.assertEqual(s, 404)

    def test_cookie_gets_real_homepage_with_b(self):
        s, h, b = self._get("/preview/home-b", cookie=True)
        self.assertEqual(s, 200)
        self.assertIn(B_MARK, b)
        self.assertNotIn(sprint_home._CSS_COMMENT.sub("", sprint_home.style_tag("hybrid")).encode(), b)
        self.assertIn(b'data-sprint="hybrid"', b)
        self.assertIn(b'id="conditions"', b)
        self.assertIn(b"Private preview", b)
        self.assertIn(b'content="noindex, nofollow"', b)
        self.assertIn("noindex", h.get("x-robots-tag", ""))
        self.assertIn("no-store", h.get("cache-control", ""))
        self.assertIn("Cookie", h.get("vary", ""))
        self.assertIn(b'href="/preview/home-b?region=hatteras"', b)

    def test_unknown_region_falls_back_to_crystal_coast(self):
        s, h, b = self._get("/preview/home-b?region=nowhere", cookie=True)
        self.assertEqual(s, 200)
        self.assertNotIn(b"nowhere", b)

    def test_b_page_text_matches_public_apart_from_css(self):
        _, _, pub = self._get("/")
        _, _, prv = self._get("/preview/home-b", cookie=True)
        strip = lambda d: d[d.index(b"<main"):d.index(b"</main>")].replace(b'href="/preview/home-b?region=', b'href="/?region=')
        self.assertEqual(strip(pub), strip(prv))


del _Base

if __name__ == "__main__":
    unittest.main()
