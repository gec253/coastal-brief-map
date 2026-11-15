"""Public Catch Wall: server-rendered approved photos, no sample states."""
from __future__ import annotations

import os
import threading
import unittest
from unittest.mock import patch

from http.server import ThreadingHTTPServer

import catch_wall_public as cw
import photos

RED_DRUM_ID = "3e41ed83-23a3-4032-8a5f-c7957b788e3f"

def _src(stem):
    return {
        "400": "https://example.supabase.co/storage/v1/object/public/photos-approved/%s-400.webp" % stem,
        "800": "https://example.supabase.co/storage/v1/object/public/photos-approved/%s-800.webp" % stem,
        "1600": "https://example.supabase.co/storage/v1/object/public/photos-approved/%s-1600.webp" % stem,
    }

PHOTOS = [
    {
        "id": RED_DRUM_ID,
        "category": "fishing",
        "water": "saltwater",
        "species": "Red Drum",
        "location": "New Bern · Neuse River",
        "name": "Ed",
        "w": 3024,
        "h": 4032,
        "src": _src("red-drum"),
    },
    {
        "id": "a225cada-1111-4000-8000-000000000002",
        "category": "fishing",
        "water": "freshwater",
        "species": "Striped Bass",
        "location": "Weldon",
        "name": "Sam",
        "w": 1600,
        "h": 1200,
        "src": _src("weldon"),
    },
    {
        "id": "bcd8fba5-1111-4000-8000-000000000003",
        "category": "fishing",
        "water": "saltwater",
        "species": "Striped Bass",
        "location": "Roanoke River",
        "name": "Pat",
        "w": 1600,
        "h": 2000,
        "src": _src("roanoke"),
    },
    {
        "id": "life-0001-1111-4000-8000-000000000004",
        "category": "life",
        "water": "saltwater",
        "title": "Morning on the sound",
        "location": "Core Sound",
        "name": "Lee",
        "w": 1600,
        "h": 1200,
        "src": _src("sound"),
    },
]


class Assemble(unittest.TestCase):
    def test_featured_prefers_red_drum(self):
        model = cw.assemble("catch", "all", live=PHOTOS)
        self.assertEqual(model["featured"]["id"], RED_DRUM_ID)
        self.assertEqual(len(model["photos"]), 3)
        self.assertFalse(model["invite"])

    def test_invite_when_zero_or_one(self):
        none = cw.assemble("catch", "all", live=[])
        self.assertIsNone(none["featured"])
        self.assertTrue(none["invite"])
        one = cw.assemble("catch", "all", live=PHOTOS[:1])
        self.assertEqual(one["featured"]["id"], RED_DRUM_ID)
        self.assertTrue(one["invite"])

    def test_life_and_water_filters(self):
        life = cw.assemble("life", "all", live=PHOTOS)
        self.assertEqual(life["featured"]["id"], "life-0001-1111-4000-8000-000000000004")
        self.assertEqual(len(life["photos"]), 1)
        self.assertTrue(life["invite"])
        fresh = cw.assemble("catch", "fresh", live=PHOTOS)
        self.assertEqual(len(fresh["photos"]), 1)
        self.assertEqual(fresh["photos"][0]["water"], "freshwater")
        self.assertTrue(fresh["invite"])

    def test_featured_markup_uses_existing_variants(self):
        model = cw.assemble("catch", "all", live=PHOTOS)
        fig = cw._photo_figure(model["featured"], 0, True)
        self.assertIn('src="' + PHOTOS[0]["src"]["800"] + '"', fig)
        self.assertIn(PHOTOS[0]["src"]["400"] + " 400w", fig)
        self.assertIn(PHOTOS[0]["src"]["800"] + " 800w", fig)
        self.assertIn(PHOTOS[0]["src"]["1600"] + " 1600w", fig)
        self.assertIn('media="(max-width: 859px)"', fig)
        self.assertIn('fetchpriority="high"', fig)
        self.assertIn('loading="eager"', fig)
        self.assertNotIn("1280w", fig)
        html = cw.featured_preload_html(model)
        self.assertIn("imagesrcset", html)
        self.assertIn("max-width: 859px", html)
        self.assertIn("min-width: 860px", html)

    def test_configured_empty_does_not_fall_back_to_production(self):
        with patch.object(photos, "public_photos", return_value={"configured": True, "photos": []}):
            with patch.object(cw, "_fetch_public_approved") as fetch:
                rows = cw.load_approved()
                self.assertEqual(rows, [])
                fetch.assert_not_called()

    def test_no_samples_or_open_frames_in_html(self):
        model = cw.assemble("catch", "all", live=PHOTOS)
        html = cw.main_html(model)
        self.assertNotIn("Design sample", html)
        self.assertNotIn("cw-banner", html)
        self.assertNotIn("cw-open-frames", html)
        self.assertNotIn("cw-slot", html)
        self.assertNotIn("sample=", html)
        self.assertIn('id="share-open" hidden', html)
        self.assertIn("Photo sharing opens soon", html)
        self.assertIn('id="share-soon"', html)




    def test_featured_uses_same_origin_media_when_cached(self):
        photo = dict(PHOTOS[0])
        pid = photo["id"]
        with cw._MEDIA_LOCK:
            cw._MEDIA_CACHE[(pid, "800")] = b"RIFF" + b"x" * 200
            cw._MEDIA_CACHE[(pid, "400")] = b"RIFF" + b"x" * 200
        try:
            loc = cw.localize_featured(photo)
            self.assertTrue(loc["src"]["800"].startswith("/catch-wall-media/"))
            self.assertIn("/800.webp", loc["src"]["800"])
            model = cw.assemble("catch", "all", live=[loc] + PHOTOS[1:])
            # assemble localizes featured again from original live photos unless we cache against PHOTOS[0]
        finally:
            with cw._MEDIA_LOCK:
                cw._MEDIA_CACHE.pop((pid, "800"), None)
                cw._MEDIA_CACHE.pop((pid, "400"), None)
        # Re-do with cache held through assemble
        with cw._MEDIA_LOCK:
            cw._MEDIA_CACHE[(pid, "800")] = b"RIFF" + b"x" * 200
            cw._MEDIA_CACHE[(pid, "400")] = b"RIFF" + b"x" * 200
        try:
            model = cw.assemble("catch", "all", live=PHOTOS)
            html = cw.featured_preload_html(model) + cw._photo_figure(model["featured"], 0, True)
            self.assertIn("/catch-wall-media/%s/800.webp" % pid, html)
            self.assertIn("/catch-wall-media/%s/400.webp" % pid, html)
            # 1600 stays on the public bucket until that derivative is cached.
            self.assertEqual(cw.parse_media_path("/catch-wall-media/%s/800.webp" % pid), (pid, "800"))
            self.assertIsNone(cw.parse_media_path("/catch-wall-media/../800.webp"))
        finally:
            with cw._MEDIA_LOCK:
                cw._MEDIA_CACHE.pop((pid, "800"), None)
                cw._MEDIA_CACHE.pop((pid, "400"), None)

class PhotoCache(unittest.TestCase):
    def tearDown(self):
        cw._store_cache([])
        cw._PUBLIC_CACHE["t"] = 0.0

    def test_photo_cache_serves_stale_without_blocking(self):
        calls = []

        class FakeResp:
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False
            def read(self):
                return b'{"photos": [{"id": "x"}]}'

        def fake_open(*a, **k):
            calls.append(k.get("timeout"))
            return FakeResp()

        cw._store_cache([{"id": "cached"}])
        with patch("catch_wall_public.urlopen", fake_open):
            rows = cw._fetch_public_approved()
        self.assertEqual(rows, [{"id": "cached"}])
        self.assertEqual(calls, [])

        # Past freshness, within TTL: return stale immediately and refresh in the background.
        cw._PUBLIC_CACHE["t"] = cw.time.time() - (cw._CACHE_FRESH_S + 1)
        with patch("catch_wall_public.urlopen", fake_open):
            rows = cw._fetch_public_approved()
        self.assertEqual(rows, [{"id": "cached"}])
        cw.time.sleep(0.2)
        self.assertEqual(calls, [cw._FETCH_TIMEOUT_S])

        def boom(*a, **k):
            calls.append("boom")
            raise TimeoutError("slow")

        cw._store_cache([{"id": "stale"}])
        cw._PUBLIC_CACHE["t"] = 0.0
        with patch("catch_wall_public.urlopen", boom):
            rows = cw._fetch_public_approved()
        self.assertEqual(rows, [{"id": "stale"}])
        self.assertIn("boom", calls)


class PublicPages(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for k in ("MORNING_BRIEF_ENABLED", "FRESHWATER_ENABLED", "PREVIEW_KEY"):
            os.environ.pop(k, None)
        import server
        cls.server = server
        cls._orig_get_ads = server.get_ads
        server.get_ads = lambda force=False: {"adsOn": False, "mode": "paused"}
        cls._live = patch.object(cw, "load_approved", side_effect=lambda live=None: list(PHOTOS) if live is None else [dict(p) for p in live])
        cls._live.start()
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.port = cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.base = "http://127.0.0.1:%d" % cls.port

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls._live.stop()
        cls.server.get_ads = cls._orig_get_ads

    def _get(self, path):
        import urllib.request
        import urllib.error
        req = urllib.request.Request(self.base + path)
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                hdrs = {k.lower(): v for k, v in r.headers.items()}
                return r.status, r.read().decode("utf-8", "replace"), hdrs
        except urllib.error.HTTPError as e:
            hdrs = {k.lower(): v for k, v in e.headers.items()}
            return e.code, e.read().decode("utf-8", "replace"), hdrs

    def test_catch_wall_is_server_rendered(self):
        status, body, _ = self._get("/catch-wall")
        self.assertEqual(status, 200)
        self.assertIn('data-home="folio"', body)
        self.assertIn('data-concept="a"', body)
        self.assertIn("data-catch-wall", body)
        self.assertIn('class="cw-feature"', body)
        self.assertIn("Red Drum", body)
        self.assertIn("red-drum-800.webp", body)
        self.assertIn("red-drum-1600.webp", body)
        self.assertIn("red-drum-400.webp", body)
        self.assertIn('fetchpriority="high"', body)
        self.assertIn('media="(max-width: 859px)"', body)
        self.assertIn('id="catch-wall-css"', body)
        self.assertNotIn('href="/catch-wall-public.css"', body)
        self.assertNotIn('href="/folio-chrome.css"', body)
        self.assertIn("/catch-wall-public.js", body)
        head = body.split("</head>", 1)[0]
        self.assertLess(head.find('rel="preload" as="image"'), head.find("/fonts/"))
        self.assertLess(head.find('rel="preload" as="image"'), head.find("styles.css"))
        self.assertIn('rel="preconnect"', head)
        self.assertIn("window.__CW_BOOT", body)
        self.assertNotIn('src="/gallery.js"', body)
        self.assertNotIn("Design sample", body)
        self.assertNotIn("cw-open-frames", body)
        self.assertNotIn("cw-banner", body)
        self.assertIn('id="share-open" hidden', body)
        self.assertIn("Photo sharing opens soon", body)
        self.assertIn('id="share-dlg"', body)
        self.assertIn('id="share-form"', body)
        self.assertIn('id="sh-photo"', body)
        self.assertIn("stay the property of the people who took them", body)
        self.assertIn('href="/catch-wall"', body)
        self.assertIn('href="/coastal-life"', body)
        self.assertIn('href="/photos"', body)
        self.assertIn("Weldon", body)
        self.assertIn("Roanoke River", body)
        self.assertIn('id="nav-brief"', body)
        self.assertNotIn("data-preview", body)

    def test_filters_and_views(self):
        status, body, _ = self._get("/catch-wall?water=fresh")
        self.assertEqual(status, 200)
        self.assertIn("Weldon", body)
        self.assertNotIn("Red Drum", body)
        self.assertIn("A place for real photographs", body)
        self.assertIn('href="/catch-wall?water=fresh"', body)
        status, life, _ = self._get("/coastal-life")
        self.assertEqual(status, 200)
        self.assertIn("Morning on the sound", life)
        self.assertIn("A place for real photographs", life)
        self.assertNotIn("Red Drum", life)
        status, allp, _ = self._get("/photos")
        self.assertEqual(status, 200)
        self.assertIn("Red Drum", allp)
        self.assertIn("Morning on the sound", allp)

    def test_share_assets_and_static(self):
        status, css, hdrs = self._get("/catch-wall-public.css")
        self.assertEqual(status, 200)
        self.assertIn("text/css", hdrs.get("content-type", ""))
        self.assertNotIn("#share-open { display: inline-flex !important; }", css)
        status, js, _ = self._get("/catch-wall-public.js")
        self.assertEqual(status, 200)
        self.assertIn("share-open", js)
        self.assertIn("/api/photos/submit", js)
        self.assertIn("/api/photos/config", js)
        self.assertIn("/api/photos/submit", js)
        self.assertNotIn('fetch("/api/photos?', js)
        self.assertNotIn("fetch('/api/photos?", js)

    def test_other_pages_untouched(self):
        status, home, _ = self._get("/")
        self.assertEqual(status, 200)
        self.assertNotIn("data-catch-wall", home)
        self.assertNotIn("/catch-wall-public.js", home)
        status, lake, _ = self._get("/lake")
        self.assertEqual(status, 200)
        self.assertNotIn("data-catch-wall", lake)
        status, preview, _ = self._get("/preview/catch-wall-v2")
        self.assertEqual(status, 404)

    def test_empty_catch_wall_shows_invitation(self):
        with patch.object(cw, "load_approved", return_value=[]):
            status, body, _ = self._get("/catch-wall")
        self.assertEqual(status, 200)
        self.assertIn("A place for real photographs", body)
        self.assertNotIn("class=\"cw-feature\"", body)
        self.assertNotIn("cw-open-frames", body)
