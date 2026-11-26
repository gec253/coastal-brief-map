"""Public /catch-wall (Catch Wall redesign) and the brief-polish look on public /brief.
Presentation only: approved photos only, the existing share flow, a logged fallback to the
previous render, and /preview/* still cookie-gated."""
import os
import re
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]

KEY = "test-public-catchwall-key-0123456789abcdef"


def _ph(pid, water="saltwater", status="approved", category="fishing", **kw):
    p = {"id": pid, "status": status, "category": category, "water": water, "w": 1600, "h": 1200,
         "species": "Red drum", "location": "Test Inlet",
         "src": {k: "/catch-wall-media/%s/%s.webp" % (pid, k) for k in ("400", "800", "1600")}}
    p.update(kw)
    return p


LIVE = [_ph("a-salt"), _ph("b-salt"), _ph("c-fresh", water="freshwater"),
        _ph("d-pending", status="pending"), _ph("e-life", category="life"),
        _ph("f-rejected", approved=False)]
APPROVED_CATCH = {"a-salt", "b-salt", "c-fresh"}


class PublicCatchWallBrief(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for k in ("MORNING_BRIEF_ENABLED", "FRESHWATER_ENABLED"):
            os.environ.pop(k, None)
        os.environ["PREVIEW_KEY"] = KEY
        import server
        import catch_wall_public
        cls.server = server
        cls._p = [patch.object(server, "get_ads", lambda force=False: {"adsOn": False, "mode": "paused"}),
                  patch.object(catch_wall_public, "_cache_snapshot", lambda: (1.0, [], True, True)),
                  patch.object(catch_wall_public, "load_state", lambda live=None: {"photos": [dict(p) for p in LIVE], "ok": True, "unavailable": False})]
        for p in cls._p:
            p.start()
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.base = "http://127.0.0.1:%d" % cls.httpd.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        for p in cls._p:
            p.stop()
        os.environ.pop("PREVIEW_KEY", None)

    def _get(self, path, cookie=False):
        h = {"Cookie": "cb_preview=" + self.server._preview_cookie_value(self.server._preview_secret())} if cookie else {}
        try:
            with urllib.request.urlopen(urllib.request.Request(self.base + path, headers=h), timeout=30) as r:
                return r.status, r.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            return e.code, ""

    def _assert_public_clean(self, h, share_dialog=False):
        if share_dialog:   # the existing share form keeps its own "sh-preview" (chosen-photo thumbnail) ids
            h = re.sub(r'<dialog class="share-dlg".*?</dialog>', "", h, flags=re.S)
            h = re.sub(r"\.sh-preview[^{]*\{[^}]*\}", "", h)
        self.assertNotRegex(h, r"(?i)preview")
        self.assertNotIn("PRIVATE", h.upper())
        self.assertNotRegex(h, r"(?i)noindex")
        self.assertNotRegex(h, r'(?i)concept ·|class="pv-flag"')

    # ---- /catch-wall --------------------------------------------------------------
    def test_catch_wall_public_200_indexable_and_clean(self):
        for path in ("/catch-wall", "/catch-wall/"):
            s, h = self._get(path)
            self.assertEqual(s, 200, path)
            self.assertIn('<meta name="robots" content="index, follow">', h)
            self.assertIn("<title>Catch Wall \u2014 The Coastal Brief</title>", h)
            self.assertIn('<link rel="canonical" href="https://thecoastalbrief.com/catch-wall">', h)
            self.assertIn('<meta property="og:url" content="https://thecoastalbrief.com/catch-wall">', h)
            self.assertIn('<h1 id="cw-h" class="cw-h">The Catch Wall</h1>', h)
            self.assertIn('<a href="/catch-wall" aria-current="page">Catch Wall</a>', h)
            self._assert_public_clean(h, share_dialog=True)

    def test_catch_wall_header_matches_folio_chrome(self):
        """Public /catch-wall keeps its photos, but uses the Folio navy masthead and nav."""
        s, h = self._get("/catch-wall")
        self.assertEqual(s, 200)
        self.assertIn('data-concept="a"', h)
        self.assertIn("data-catch-wall", h)
        self.assertIn('header class="site"', h)
        self.assertIn("data-identity", h)
        self.assertNotIn('<header class="mh mh-hybrid">', h)
        self.assertNotIn('class="mh-name"', h)
        self.assertIn('<a href="/catch-wall" aria-current="page">Catch Wall</a>', h)
        self.assertIn("Conditions</a>", h)
        self.assertIn("Coastal Life</a>", h)
        self.assertIn('id="nav-brief"', h)
        self.assertIn("coastalBrief.theme", h)
        self.assertIn('id="cw-folio-chrome"', h)
        self.assertIn("--id-navy", h)
        self.assertIn('<h1 id="cw-h" class="cw-h">The Catch Wall</h1>', h)
        self.assertIn('class="pl pl-f"', h)
        self.assertIn('id="share-dlg"', h)
        self.assertNotIn(".mh-hybrid{background:#F7F9F9}", h)

    def test_featured_catch_present_and_approved_only(self):
        s, h = self._get("/catch-wall")
        self.assertEqual(h.count('data-featured="1"'), 1)
        self.assertEqual(h.count('class="pl-feat">Featured catch<'), 1)
        shown = set(re.findall(r"/catch-wall-media/([a-z-]+)/", h))
        self.assertEqual(shown, APPROVED_CATCH)       # no pending, rejected or Coastal Life photos
        feat = re.search(r'<figure class="pl pl-f"[^>]*data-featured="1".*?</figure>', h, re.S).group(0)
        fid = re.search(r"/catch-wall-media/([a-z-]+)/", feat).group(1)
        import catch_wall_preview as C
        self.assertEqual(fid, C.featured_catch(C.catch_photos([dict(p) for p in LIVE]))["id"])
        self.assertIn(fid, APPROVED_CATCH)

    def test_share_links_only_to_existing_submit_path_and_form_kept(self):
        s, h = self._get("/catch-wall")
        links = re.findall(r'<a class="cw-submit"[^>]*href="([^"]+)"', h)
        self.assertEqual(len(links), 2)
        self.assertEqual(set(links), {"/catch-wall#share"})
        # the existing share dialog and its script, unchanged and still posting to the existing API
        self.assertIn('<dialog class="share-dlg" id="share-dlg"', h)
        self.assertIn('<form id="share-form" class="share-form" novalidate>', h)
        self.assertIn('<script src="/catch-wall-public.js" defer></script>', h)
        self.assertEqual(h.count('id="share-open"'), 1)
        self.assertIn('id="share-soon"', h)
        old = (ROOT / "catch-wall.html").read_text(encoding="utf-8")
        self.assertIn(re.search(r'<dialog class="share-dlg".*?</dialog>', old, re.S).group(0), h)
        js = (ROOT / "catch-wall-public.js").read_text(encoding="utf-8")
        self.assertIn('fetch("/api/photos/submit"', js)
        # share form is unchanged (no action); the feedback form posts to /feedback
        self.assertNotRegex(h, r'<form(?![^>]*(id="fb-form"|id="share-form"))[^>]*action=')
        self.assertIn('<form class="fb-form" id="fb-form" method="post" action="/feedback"', h)

    def test_catch_wall_fallback_serves_previous_render_on_exception(self):
        import catch_wall_preview
        with patch.object(catch_wall_preview, "page", side_effect=RuntimeError("boom")), \
             patch("sys.stderr") as err:
            s, h = self._get("/catch-wall")
        self.assertEqual(s, 200)
        self.assertNotIn('class="pl pl-f"', h)
        self.assertIn('<dialog class="share-dlg" id="share-dlg"', h)   # the old page, share flow intact
        self.assertIn('href="https://thecoastalbrief.com/catch-wall"', h)
        self.assertTrue(any("public catch wall redesign failed" in str(c) for c in err.write.call_args_list))

    def test_water_filter_still_works(self):
        s, h = self._get("/catch-wall?water=fresh")
        self.assertEqual(s, 200)
        self.assertEqual(set(re.findall(r"/catch-wall-media/([a-z-]+)/", h)), {"c-fresh"})
        self.assertIn('<link rel="canonical" href="https://thecoastalbrief.com/catch-wall">', h)

    def test_empty_or_unavailable_uses_previous_render_quietly(self):
        import catch_wall_public
        for st in ({"photos": [], "ok": True, "unavailable": False}, {"photos": [], "ok": False, "unavailable": True}):
            with patch.object(catch_wall_public, "load_state", lambda live=None, st=st: st), patch("sys.stderr") as err:
                s, h = self._get("/catch-wall")
            self.assertEqual(s, 200)
            self.assertNotIn('class="pl pl-f"', h)
            self.assertIn('id="share-dlg"', h)
            self.assertFalse(any("redesign failed" in str(c) for c in err.write.call_args_list))

    def test_cold_cache_uses_previous_render_without_a_second_wait(self):
        import catch_wall_public
        with patch.object(catch_wall_public, "_cache_snapshot", lambda: (0.0, [], False, False)):
            s, h = self._get("/catch-wall")
        self.assertEqual(s, 200)
        self.assertNotIn('class="pl pl-f"', h)

    def test_other_photo_pages_unchanged(self):
        for path in ("/coastal-life", "/photos"):
            s, h = self._get(path)
            self.assertEqual(s, 200)
            self.assertNotIn('class="pl pl-f"', h)

    # ---- /brief ---------------------------------------------------------------------
    def test_brief_and_region_brief_200_polished_and_clean(self):
        for path in ("/brief", "/brief?region=hatteras"):
            s, h = self._get(path)
            self.assertEqual(s, 200, path)
            self.assertIn('<style id="brief-style">', h)
            self.assertIn('<body class="mb-page mb-polish">', h)
            self.assertIn('aria-label="Print"', h)
            self.assertIn('role="radiogroup" aria-label="Color theme"', h)  # Ed t468u shared control
            self.assertIn('data-name-prefix="Region: "', h)
            self.assertIn('content="index, follow"', h)
            self._assert_public_clean(h)

    def test_brief_polish_is_presentation_only(self):
        import brief
        import server
        st, b = brief.get("hatteras", include_fresh=True)
        # t487u: the route adds a live "Status now" check; pin one result so both renders share it.
        sn = brief.status_now_for(b, lambda u: None)
        with patch.object(brief, "status_now_for", return_value=sn):
            s, h = self._get("/brief?region=hatteras")
        raw = server._paint_public_brief(brief.page(b, include_fresh=True, public=True, ads_on=False,
                                                    status_now=sn).encode("utf-8")).decode("utf-8")
        text = lambda x: re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", re.sub(r"(?s)<(script|style|svg)\b.*?</\1>", "", x))).strip()
        drop = lambda t: t.replace(" Print ", " ").replace(" Dark mode ", " ").replace(" Light Dark Auto ", " ")
        self.assertEqual(drop(text(raw)), drop(text(h)))   # same words, same order

    def test_brief_fallback_serves_unpolished_on_exception(self):
        import brief_preview
        with patch.object(brief_preview, "_compact_tools", side_effect=RuntimeError("boom")), \
             patch("sys.stderr") as err:
            s, h = self._get("/brief?region=hatteras")
        self.assertEqual(s, 200)
        self.assertNotIn('id="brief-style"', h)
        self.assertIn('<body class="mb-page">', h)
        self.assertTrue(any("public brief polish failed" in str(c) for c in err.write.call_args_list))

    # ---- /preview/* still gated -------------------------------------------------------
    def test_preview_routes_still_gated(self):
        for path in ("/preview/catch-wall", "/preview/home-hybrid", "/preview/brief/wilmington"):
            self.assertEqual(self._get(path)[0], 404, path)
        s, h = self._get("/preview/catch-wall", cookie=True)
        self.assertEqual(s, 200)
        self.assertIn('content="noindex, nofollow"', h)
        self.assertIn('<a class="cw-submit" href="/catch-wall">', h)   # preview still links to the public page


if __name__ == "__main__":
    unittest.main()
