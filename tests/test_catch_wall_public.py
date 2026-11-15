"""Public Catch Wall: server-rendered approved photos, no sample states."""
from __future__ import annotations

import os
import subprocess
import time
import threading
import unittest
from pathlib import Path
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
    def test_featured_prefers_admin_flag(self):
        rows = [dict(p) for p in PHOTOS]
        rows[2]["featured"] = True
        model = cw.assemble("catch", "all", live=rows)
        self.assertEqual(model["featured"]["id"], rows[2]["id"])
        self.assertEqual(len(model["photos"]), 3)
        self.assertFalse(model["invite"])
        # A flagged life photo wins on All Photos over a newer unflagged catch.
        mixed = [dict(p) for p in (PHOTOS[0], PHOTOS[3])]
        mixed[1]["featured"] = True
        all_view = cw.assemble("all", "all", live=mixed)
        self.assertEqual(all_view["featured"]["id"], mixed[1]["id"])

    def test_featured_falls_back_to_newest_fishing(self):
        # Lists are newest-first. With no admin flag, the first fishing photo is featured.
        model = cw.assemble("catch", "all", live=PHOTOS)
        self.assertEqual(model["featured"]["id"], PHOTOS[0]["id"])
        self.assertEqual(len(model["photos"]), 3)
        self.assertFalse(model["invite"])
        later_first = [PHOTOS[1], PHOTOS[2], PHOTOS[0], PHOTOS[3]]
        model = cw.assemble("catch", "all", live=later_first)
        self.assertEqual(model["featured"]["id"], PHOTOS[1]["id"])
        # A newer life photo does not beat an approved fishing photo.
        all_view = cw.assemble("all", "all", live=[PHOTOS[3], PHOTOS[1], PHOTOS[0]])
        self.assertEqual(all_view["featured"]["id"], PHOTOS[1]["id"])

    def test_share_cta_matches_view(self):
        self.assertEqual(cw.share_cta("catch"), "Share your catch")
        self.assertEqual(cw.share_cta("life"), "Share your photo")
        self.assertEqual(cw.share_cta("all"), "Share your photo")
        catch = cw.intro_html("catch") + cw.invite_html("catch")
        self.assertIn("Share your catch", catch)
        self.assertNotIn("Share your photo", catch)
        life = cw.intro_html("life") + cw.invite_html("life")
        self.assertIn("Share your photo", life)
        self.assertNotIn("Share your catch", life)
        allp = cw.intro_html("all") + cw.invite_html("all")
        self.assertIn("Share your photo", allp)
        self.assertNotIn("Share your catch", allp)

    def test_invite_when_zero_or_one(self):
        none = cw.assemble("catch", "all", live=[])
        self.assertIsNone(none["featured"])
        self.assertTrue(none["invite"])
        one = cw.assemble("catch", "all", live=PHOTOS[:1])
        self.assertEqual(one["featured"]["id"], PHOTOS[0]["id"])
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
        _reset_cw_cache()
        with patch.object(photos, "backend", return_value=object()):
            with patch.object(photos, "public_photos", return_value={"ok": True, "configured": True, "photos": []}):
                with patch.object(cw, "_self_fetch_approved") as fetch:
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
        cw._store_cache(PHOTOS)
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
        cw._store_cache(PHOTOS)
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

def _reset_cw_cache():
    if cw._REFRESHING:
        cw._REFRESH_DONE.wait(6.0)
    with cw._CACHE_LOCK:
        cw._PUBLIC_CACHE.update({"t": 0.0, "photos": [], "ok": True, "filled": False})
    with cw._MEDIA_LOCK:
        cw._MEDIA_CACHE.clear()
    photos._pub_cache.clear()


class PhotoCache(unittest.TestCase):
    def setUp(self):
        _reset_cw_cache()
        self._backend = patch.object(photos, "backend", return_value=None)
        self._backend.start()
        self.addCleanup(self._backend.stop)
        self.addCleanup(_reset_cw_cache)

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
        def _state(live=None):
            rows = list(PHOTOS) if live is None else [dict(p) for p in live]
            return {"photos": rows, "ok": True, "unavailable": False}

        cls._live = patch.object(cw, "load_state", side_effect=_state)
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

    def test_share_cta_on_pages(self):
        status, catch, _ = self._get("/catch-wall")
        self.assertEqual(status, 200)
        self.assertIn(">Share your catch</button>", catch)
        self.assertNotIn('id="share-open" hidden>Share your photo</button>', catch)
        status, life, _ = self._get("/coastal-life")
        self.assertEqual(status, 200)
        self.assertIn(">Share your photo</button>", life)
        self.assertNotIn('id="share-open" hidden>Share your catch</button>', life)
        status, allp, _ = self._get("/photos")
        self.assertEqual(status, 200)
        self.assertIn(">Share your photo</button>", allp)
        self.assertNotIn('id="share-open" hidden>Share your catch</button>', allp)

    def test_open_share_helpers_are_in_scope(self):
        js = Path(__file__).resolve().parents[1].joinpath("catch-wall-public.js").read_text()
        open_at = js.find("function openShare(")
        dlg_at = js.find("if (dlg) {", open_at)
        sync_at = js.find("function syncSpecies(")
        fill_at = js.find("function fillRegions(")
        self.assertGreater(open_at, 0)
        self.assertGreater(dlg_at, open_at)
        self.assertTrue(0 < sync_at < open_at, "syncSpecies must be in the same scope as openShare, not inside if (dlg)")
        self.assertTrue(0 < fill_at < open_at, "fillRegions must be in the same scope as openShare, not inside if (dlg)")
        inner = js[dlg_at:js.find('fetch("/api/photos/config")', dlg_at)]
        self.assertNotIn("function syncSpecies", inner)
        self.assertNotIn("function fillRegions", inner)
        self.assertIn("syncSpecies();", js[open_at:dlg_at])
        self.assertIn("fillRegions();", js[open_at:dlg_at])

    def test_share_open_opens_dialog_in_stub_dom(self):
        stub = Path(__file__).resolve().parent / "share_open_stub.mjs"
        result = subprocess.run(
            ["node", str(stub)],
            cwd=str(Path(__file__).resolve().parents[1]),
            capture_output=True,
            text=True,
            timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        self.assertIn("share-open-ok", result.stdout)

    def test_share_open_opens_dialog_in_browser(self):
        pw = "/tmp/pwvenv/bin/python"
        script = Path(__file__).resolve().parent / "share_open_playwright.py"
        if not os.path.exists(pw):
            self.skipTest("Playwright venv is not available")
        cfg = {
            "uploads": True,
            "regions": [{"id": "neuse", "name": "Neuse River"}],
            "turnstileSiteKey": "",
        }
        with patch.object(photos, "public_config", return_value=cfg):
            result = subprocess.run(
                [pw, str(script), self.base + "/catch-wall"],
                capture_output=True,
                text=True,
                timeout=60,
            )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        self.assertIn("playwright-share-ok", result.stdout)

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
        with patch.object(cw, "load_state", return_value={"photos": [], "ok": True, "unavailable": False}):
            status, body, _ = self._get("/catch-wall")
        self.assertEqual(status, 200)
        self.assertIn("A place for real photographs", body)
        self.assertNotIn("class=\"cw-feature\"", body)
        self.assertNotIn("cw-open-frames", body)

    def test_removed_photo_media_is_404_after_refresh(self):
        pid = PHOTOS[0]["id"]
        cw._store_cache(PHOTOS)
        with cw._MEDIA_LOCK:
            cw._MEDIA_CACHE[(pid, "800")] = b"RIFF" + b"x" * 200
        try:
            status, body, hdrs = self._get("/catch-wall-media/%s/800.webp" % pid)
            self.assertEqual(status, 200)
            self.assertEqual(hdrs.get("cache-control", ""), "public, max-age=300")
            self.assertIsNotNone(cw.media_bytes(pid, "800"))
            remaining = [p for p in PHOTOS if p["id"] != pid]
            cw._store_cache(remaining)
            status, _, _ = self._get("/catch-wall-media/%s/800.webp" % pid)
            self.assertEqual(status, 404)
            self.assertIsNone(cw.media_bytes(pid, "800"))
        finally:
            with cw._MEDIA_LOCK:
                cw._MEDIA_CACHE.clear()
            cw._store_cache([])
            cw._PUBLIC_CACHE["t"] = 0.0

    def test_non_approved_media_id_is_404(self):
        cw._store_cache(PHOTOS)
        fake = "00000000-0000-0000-0000-000000000099"
        with cw._MEDIA_LOCK:
            cw._MEDIA_CACHE[(fake, "800")] = b"RIFF" + b"x" * 200
        try:
            status, _, _ = self._get("/catch-wall-media/%s/800.webp" % fake)
            self.assertEqual(status, 404)
            self.assertIsNone(cw.media_bytes(fake, "800"))
            # The current featured catch is still servable.
            featured = PHOTOS[0]["id"]
            with cw._MEDIA_LOCK:
                cw._MEDIA_CACHE[(featured, "800")] = b"RIFF" + b"x" * 200
            status, _, _ = self._get("/catch-wall-media/%s/800.webp" % featured)
            self.assertEqual(status, 200)
        finally:
            with cw._MEDIA_LOCK:
                cw._MEDIA_CACHE.clear()
            cw._store_cache([])
            cw._PUBLIC_CACHE["t"] = 0.0


class _ConfigurableBackend:
    name = "supabase"

    def __init__(self, rows, delay=0.0, fail=False):
        self.rows = list(rows)
        self.delay = delay
        self.fail = fail
        self.calls = 0

    def select(self, status=None, category=None, featured=None, limit=200, row_id=None):
        self.calls += 1
        if self.delay:
            time.sleep(self.delay)
        if self.fail:
            raise photos.StorageError("down")
        rows = [
            r for r in self.rows
            if (not status or r.get("status") == status)
            and (not category or r.get("category") == category)
            and (featured is None or bool(r.get("featured")) == featured)
            and (not row_id or r.get("id") == row_id)
        ]
        return rows[:limit]

    def public_url(self, key):
        return "https://example.supabase.co/storage/v1/object/public/photos-approved/" + key


def _db_row(photo, **extra):
    water = photo.get("water") or "saltwater"
    row = {
        "id": photo["id"],
        "status": "approved",
        "category": photo.get("category") or "fishing",
        "water_type": water,
        "width": photo.get("w") or 1600,
        "height": photo.get("h") or 1200,
        "display_name": photo.get("name") or "",
        "anonymous": False,
        "species": photo.get("species") or "",
        "location": photo.get("location") or "",
        "region_id": "",
        "taken_on": "",
        "caption": "",
        "featured": bool(photo.get("featured")),
    }
    row.update(extra)
    return row


class ConfiguredPath(unittest.TestCase):
    """SWR on the configured public_photos path: bounded cold miss, stale warm, takedown."""

    @classmethod
    def setUpClass(cls):
        for k in ("MORNING_BRIEF_ENABLED", "FRESHWATER_ENABLED", "PREVIEW_KEY"):
            os.environ.pop(k, None)
        import server
        cls.server = server
        cls._orig_get_ads = server.get_ads
        server.get_ads = lambda force=False: {"adsOn": False, "mode": "paused"}
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.port = cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.base = "http://127.0.0.1:%d" % cls.port

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.server.get_ads = cls._orig_get_ads
        _reset_cw_cache()

    def setUp(self):
        _reset_cw_cache()
        self.backend = _ConfigurableBackend([_db_row(p) for p in PHOTOS])
        self._backend_patch = patch.object(photos, "backend", side_effect=lambda: self.backend)
        self._backend_patch.start()
        self._self_fetch = patch.object(cw, "_self_fetch_approved")
        self._self_fetch_mock = self._self_fetch.start()
        self._warm = patch.object(cw, "_warm_featured_media")
        self._warm.start()
        self.addCleanup(self._backend_patch.stop)
        self.addCleanup(self._self_fetch.stop)
        self.addCleanup(self._warm.stop)
        self.addCleanup(_reset_cw_cache)

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

    def test_slow_select_does_not_block_html(self):
        self.backend.delay = 5.0
        t0 = time.monotonic()
        status, body, _ = self._get("/catch-wall")
        elapsed = time.monotonic() - t0
        self.assertEqual(status, 200)
        self.assertLess(elapsed, 1.2)
        self.assertIn("Photos are unavailable right now", body)
        self.assertNotIn("just getting started", body)
        self._self_fetch_mock.assert_not_called()

        # After warmup the same slow backend is served from the SWR cache.
        self.assertTrue(cw._REFRESH_DONE.wait(6.0))
        self.backend.delay = 5.0
        t0 = time.monotonic()
        status, body, _ = self._get("/catch-wall")
        elapsed = time.monotonic() - t0
        self.assertEqual(status, 200)
        self.assertLess(elapsed, 0.3)
        self.assertIn("Red Drum", body)
        self.assertNotIn("Photos are unavailable right now", body)
        self.assertNotIn("just getting started", body)

    def test_storage_error_shows_unavailable_and_keeps_stale(self):
        self.backend.fail = True
        t0 = time.monotonic()
        status, body, _ = self._get("/catch-wall")
        elapsed = time.monotonic() - t0
        self.assertEqual(status, 200)
        self.assertLess(elapsed, 1.2)
        self.assertIn("Photos are unavailable right now", body)
        self.assertNotIn("just getting started", body)

        # A later success fills the cache; a subsequent StorageError keeps that list.
        self.backend.fail = False
        cw.invalidate()
        self.assertTrue(cw._REFRESH_DONE.wait(2.0))
        status, body, _ = self._get("/catch-wall")
        self.assertIn("Red Drum", body)
        self.assertNotIn("Photos are unavailable right now", body)

        photos._pub_cache.clear()
        self.backend.fail = True
        cw.invalidate()
        self.assertTrue(cw._REFRESH_DONE.wait(2.0))
        t0 = time.monotonic()
        status, body, _ = self._get("/catch-wall")
        elapsed = time.monotonic() - t0
        self.assertEqual(status, 200)
        self.assertLess(elapsed, 0.3)
        self.assertIn("Red Drum", body)
        self.assertNotIn("Photos are unavailable right now", body)
        self.assertNotIn("just getting started", body)

    def test_bust_cache_evicts_removed_featured_media(self):
        cw.warm_cache()
        self.assertTrue(cw._REFRESH_DONE.wait(2.0))
        pid = RED_DRUM_ID
        with cw._MEDIA_LOCK:
            cw._MEDIA_CACHE[(pid, "800")] = b"RIFF" + b"x" * 200
        status, _, _ = self._get("/catch-wall-media/%s/800.webp" % pid)
        self.assertEqual(status, 200)

        # Takedown: approved list no longer includes the Red Drum.
        self.backend.rows = [_db_row(p) for p in PHOTOS if p["id"] != pid]
        photos._bust_cache()
        self.assertTrue(cw._REFRESH_DONE.wait(2.0))
        status, _, _ = self._get("/catch-wall-media/%s/800.webp" % pid)
        self.assertEqual(status, 404)
        self.assertIsNone(cw.media_bytes(pid, "800"))
        self._self_fetch_mock.assert_not_called()

    def test_self_fetch_is_off_on_render(self):
        _reset_cw_cache()
        with patch.object(photos, "backend", return_value=None):
            with patch.object(photos, "on_render", return_value=True):
                with patch.object(cw, "_self_fetch_approved") as fetch:
                    state = cw.load_state()
        self.assertTrue(state["unavailable"])
        self.assertEqual(state["photos"], [])
        fetch.assert_not_called()
