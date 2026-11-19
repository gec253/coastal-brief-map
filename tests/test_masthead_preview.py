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
    b"data-home",
    b"home-photo",
    b"/preview/home.css",
    b"featured-photos",
    b"mast-date-short",
    b"mast-date-full",
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

    # Homepage speed-trim files, the Catch Wall form, and the header picker's default region list
    # (region-nav.js, which gains each region when it goes public) may differ from origin/main.
    # lake.html and brief.css are on main again, so they are locked against origin/main.
    # This branch does not edit those files: the Neuse CLS reservation lives in
    # styles.css (still unlocked) plus a data-region stamp in the server paint path.
    PUBLIC_FILES_LOCKED = tuple(
        rel for rel in PUBLIC_FILES
        if rel not in (
            "index.html",
            "dashboard.js",
            "app.js",
            "styles.css",
            "catch-wall.html",
            "region-nav.js",
            # Ed (Nov 19 launch audit, t336u) changed the Morning Brief link rule: each region opens
            # its own /brief page. brief-link.js is the only file that rule touches here; its
            # behavior is covered by tests/test_launch_audit_1119.py instead of this byte lock.
            "brief-link.js",
        )
    )

    def test_brief_link_js_still_served_and_loaded(self):
        # Replaces the byte lock on brief-link.js (Ed, Nov 19, t336u/t337u): the file is still served
        # as JavaScript, still exposes CoastalBriefLink.sync for the pickers, and every page with the
        # header Morning Brief link (public pages and this masthead preview) still loads it.
        status, body, hdrs = self._req("/brief-link.js")
        self.assertEqual(status, 200)
        self.assertIn("javascript", hdrs.get("content-type", ""))
        self.assertIn(b"window.CoastalBriefLink = { sync: sync, briefRegion: briefRegion }", body)
        self.assertIn(b'["nav-brief", "folio-brief"]', body)
        for path, ck in (("/dashboard", None), ("/catch-wall", None), ("/coastal-life", None), ("/lake", None),
                         ("/lake?region=jordan-lake", None), ("/preview/masthead", self._cookie())):
            status, body, _ = self._req(path, env={"PREVIEW_KEY": self.KEY} if ck else None, cookie=ck)
            self.assertEqual(status, 200, path)
            self.assertIn(b'id="nav-brief"', body, path)
            self.assertIn(b'src="/brief-link.js"', body, path)

    def test_public_files_match_origin_main(self):
        for rel in self.PUBLIC_FILES_LOCKED:
            committed = subprocess.check_output(["git", "show", "origin/main:" + rel], cwd=ROOT)
            self.assertEqual(committed, (ROOT / rel).read_bytes(), rel)

    def test_public_homepage_is_the_final_design(self):
        status, body, hdrs = self._req("/dashboard")
        self.assertEqual(status, 200)
        self.assertNotIn("noindex", hdrs.get("x-robots-tag", ""))
        self.assertIn(b'data-concept="a"', body)
        self.assertIn(b'data-home="folio"', body)
        self.assertNotIn(b"data-preview", body)
        self.assertIn(b"folio-photo", body)
        self.assertIn(b"/featured/bodie-sunrise", body)
        self.assertIn(b"Photograph: U.S. National Park Service, Cape Hatteras National Seashore", body)
        self.assertIn(b'id="region-select"', body)
        self.assertIn(b'id="region-nav"', body)
        self.assertIn(b"region-pick", body)
        self.assertIn(b'id="nav-brief"', body)
        self.assertIn(b'property="og:image"', body)
        self.assertIn(b"cb-mast-reveal", body)
        self.assertIn(b'id="cb-boot-conditions"', body)
        # Comparison previews stay gated and are not inlined into public /.
        self.assertNotIn(b"/preview/home.css", body)
        self.assertNotIn(b"/preview/masthead.css", body)
        self.assertNotIn(b'id="mast-preview-dock"', body)

    def test_other_public_pages_have_no_preview_markup(self):
        # Catch Wall now uses public Folio chrome (data-concept, data-home).
        # Comparison previews and private docks must still stay off these pages.
        preview_only = (
            b"data-preview",
            b"mast-preview-dock",
            b"/preview/masthead.css",
            b"/preview/home.css",
            b"home-photo",
            b"featured-photos",
        )
        for path in ("/catch-wall", "/coastal-life", "/photos"):
            status, body, _ = self._req(path)
            self.assertEqual(status, 200, path)
            for marker in preview_only:
                self.assertNotIn(marker, body, "%s %s" % (path, marker))

    def test_preview_404_without_key_or_cookie(self):
        for path in ("/preview/masthead", "/preview/masthead?c=a", "/preview/masthead.css",
                     "/preview/home", "/preview/home?c=cinematic", "/preview/home.css",
                     "/preview/photos-check"):
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
            self.assertIn(b"mast-date-short", body)
            self.assertIn(b"mast-date-full", body)
            self.assertIn(b'id="region-select"', body)
            self.assertIn(b"region-pick", body)
            # Region is in the picker only, not repeated as a mast line.
            self.assertNotIn(b"mast-region-line", body)
        status, body, hdrs = self._req("/preview/masthead.css", env=env, cookie=ck)
        self.assertEqual(status, 200)
        self.assertIn("text/css", hdrs.get("content-type", ""))
        self.assertIn("noindex", hdrs.get("x-robots-tag", ""))
        self.assertIn(b"wave-swell", body)
        # With the cookie, public / is still the published homepage, not a gated preview.
        status, home, hdrs = self._req("/dashboard", env=env, cookie=ck)
        self.assertEqual(status, 200)
        self.assertIn(b'data-concept="a"', home)
        self.assertIn(b'data-home="folio"', home)
        self.assertNotIn(b"data-preview", home)
        self.assertNotIn(b'id="mast-preview-dock"', home)
        self.assertNotIn("noindex", hdrs.get("x-robots-tag", ""))

    def test_shot_mode_hides_preview_dock(self):
        env = {"PREVIEW_KEY": self.KEY}
        status, body, _ = self._req("/preview/masthead?c=c&shot=1", env=env, cookie=self._cookie())
        self.assertEqual(status, 200)
        self.assertIn(b"data-shot", body)
        self.assertNotIn(b'id="mast-preview-dock"', body)
        self.assertIn(b"mast-wave", body)
