"""Public /wind and /radar (Stage 2): gating, GFS-only grid, rate limits,
upstream 429/failure handling, log redaction, and the usage gate."""
from __future__ import annotations

import io
import json
import os
import secrets
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from unittest import mock

import windgrid
import server


def _get(base, path, cookie=None, headers=None):
    h = dict(headers or {})
    if cookie:
        h["Cookie"] = cookie
    req = urllib.request.Request(base + path, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


class PublicRoutes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.base = "http://127.0.0.1:%d" % cls.httpd.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown(); cls.httpd.server_close()

    def setUp(self):
        server.API_LIMITS.reset()
        server.note_radar_feed(None)

    def get(self, path, cookie=None, headers=None):
        return _get(self.base, path, cookie, headers)

    def test_public_gfs_grid_strips_detail_and_ignores_unknown_ahead(self):
        def fake(ahead=0):
            return {"ok": False, "error": "Model wind is unavailable right now.", "detail": "nomads 500 at /secret"}
        with mock.patch.object(windgrid, "latest_grid", side_effect=fake):
            st, h, body = self.get("/api/wind-grid?ahead=99")
        self.assertEqual(st, 502)
        data = json.loads(body)
        self.assertFalse(data["ok"])
        self.assertNotIn("detail", data)
        self.assertNotIn(b"secret", body)
        self.assertNotIn("Access-Control-Allow-Origin", {k.title(): v for k, v in h.items()})

    def test_public_gfs_grid_ok_and_ahead_steps(self):
        calls = []
        def fake(ahead=0):
            calls.append(ahead)
            return {"ok": True, "ahead": ahead, "source": "NOAA NCEP GFS 0.25°, 10 m wind, via NOMADS", "u": [0], "v": [0]}
        with mock.patch.object(windgrid, "latest_grid", side_effect=fake):
            for a in (0, 3, 6, 9, 12):
                st, h, body = self.get("/api/wind-grid" + ("?ahead=%s" % a if a else ""))
                self.assertEqual(st, 200, a)
                self.assertIn("max-age=600", h.get("Cache-Control") or h.get("cache-control") or "")
                self.assertEqual(json.loads(body)["ahead"], a)
        self.assertEqual(calls, [0, 3, 6, 9, 12])

    def test_hrrr_stays_private_without_cookie(self):
        key = secrets.token_hex(16)
        with mock.patch.dict(os.environ, {"WIND_PARTICLES_ENABLED": "", "PREVIEW_KEY": key}), \
             mock.patch.object(server.hrrrgrid, "latest_grid", side_effect=AssertionError("must not fetch HRRR")):
            self.assertEqual(self.get("/api/wind-grid?model=hrrr")[0], 404)
            self.assertEqual(self.get("/api/wind-grid?model=hrrr&ahead=3")[0], 404)
            self.assertEqual(self.get("/wind?model=hrrr")[0], 404)

    def test_hrrr_works_with_preview_cookie(self):
        key = secrets.token_hex(16)
        ck = "%s=%s" % (server.PREVIEW_COOKIE, server._preview_cookie_value(key))
        with mock.patch.dict(os.environ, {"WIND_PARTICLES_ENABLED": "", "PREVIEW_KEY": key}), \
             mock.patch.object(server.hrrrgrid, "latest_grid", return_value={"ok": True, "ahead": 3, "source": "HRRR"}):
            st, h, body = self.get("/api/wind-grid?model=hrrr&ahead=3", ck)
            self.assertEqual(st, 200)
            self.assertEqual(json.loads(body)["ahead"], 3)
            self.assertEqual(self.get("/wind?model=hrrr", ck)[0], 200)

    def test_lab_stays_private_engine_is_public(self):
        key = secrets.token_hex(16)
        with mock.patch.dict(os.environ, {"WIND_PARTICLES_ENABLED": "", "PREVIEW_KEY": key}):
            self.assertEqual(self.get("/lab/wind")[0], 404)
            self.assertEqual(self.get("/lab/wind.js")[0], 404)
            st, h, body = self.get("/wind/engine.js")
            self.assertEqual(st, 200)
            self.assertIn(b"WindMath", body)
            self.assertEqual(self.get("/preview")[0], 404)

    def test_usage_is_404_without_cookie_and_200_with(self):
        key = secrets.token_hex(16)
        ck = "%s=%s" % (server.PREVIEW_COOKIE, server._preview_cookie_value(key))
        with mock.patch.dict(os.environ, {"PREVIEW_KEY": key, "WIND_PARTICLES_ENABLED": ""}):
            self.assertEqual(self.get("/api/radar/usage")[0], 404)
            st, h, body = self.get("/api/radar/usage", ck)
        self.assertEqual(st, 200)
        data = json.loads(body)
        self.assertIn("upstream_calls_today", data)
        self.assertIn("key_configured", data)
        self.assertIn("noindex", h.get("X-Robots-Tag") or h.get("x-robots-tag") or "")

    def test_robots_and_sitemap_omit_viewers_while_noindex(self):
        # Public but unindexed until the showcase launch, so they stay out of the sitemap.
        robots = self.get("/robots.txt")[2].decode()
        self.assertIn("Allow: /", robots)
        self.assertNotIn("Disallow: /wind", robots)
        sm = self.get("/sitemap.xml")[2].decode()
        self.assertNotIn("/wind", sm)
        self.assertNotIn("/radar", sm)
        st, h, _ = self.get("/wind")
        self.assertEqual(st, 200)
        self.assertIn("noindex", h.get("X-Robots-Tag") or h.get("x-robots-tag") or "")
        with mock.patch.object(server, "handle_radar_meta", return_value=(200, {"ok": True, "frames": [{"time": "202611201200", "type": "observed", "time_epoch": 1}]})):
            st, h, _ = self.get("/radar")
        self.assertEqual(st, 200)
        self.assertIn("noindex", h.get("X-Robots-Tag") or h.get("x-robots-tag") or "")

    def test_wind_grid_rate_limit_has_retry_after_and_respects_xff(self):
        with mock.patch.object(windgrid, "latest_grid", return_value={"ok": True, "ahead": 0, "u": [], "v": []}):
            for i in range(API := server.API_WIND_GRID_LIMIT):
                st, _, _ = self.get("/api/wind-grid", headers={"X-Forwarded-For": "203.0.113.9"})
                self.assertEqual(st, 200, i)
            st, h, body = self.get("/api/wind-grid", headers={"X-Forwarded-For": "203.0.113.9"})
            self.assertEqual(st, 429)
            self.assertTrue(int(h.get("Retry-After") or h.get("retry-after") or 0) >= 1)
            data = json.loads(body)
            self.assertEqual(data["reason"], "rate_limit")
            # A different client is not blocked.
            self.assertEqual(self.get("/api/wind-grid", headers={"X-Forwarded-For": "203.0.113.10"})[0], 200)

    def test_cf_connecting_ip_wins_over_spoofed_xff(self):
        with mock.patch.object(windgrid, "latest_grid", return_value={"ok": True, "ahead": 0, "u": [], "v": []}):
            hdr = {"CF-Connecting-IP": "198.51.100.2", "X-Forwarded-For": "192.0.2.1, 198.51.100.2"}
            for _ in range(server.API_WIND_GRID_LIMIT):
                self.assertEqual(self.get("/api/wind-grid", headers=hdr)[0], 200)
            self.assertEqual(self.get("/api/wind-grid", headers=hdr)[0], 429)
            # Spoofing a fresh leftmost XFF does not reset the budget when CF-Connecting-IP is the same.
            hdr2 = {"CF-Connecting-IP": "198.51.100.2", "X-Forwarded-For": "203.0.113.77"}
            self.assertEqual(self.get("/api/wind-grid", headers=hdr2)[0], 429)

    def test_rotating_client_ips_have_independent_buckets(self):
        """A new TCP/egress IP per request must not share one budget.
        That is how a rotating-proxy test can miss a 429 that a stable visitor hits."""
        with mock.patch.object(windgrid, "latest_grid", return_value={"ok": True, "ahead": 0, "u": [], "v": []}):
            for i in range(server.API_WIND_GRID_LIMIT + 5):
                ip = "198.51.100.%s" % (i + 1)
                st, _, _ = self.get("/api/wind-grid", headers={"CF-Connecting-IP": ip})
                self.assertEqual(st, 200, ip)
            # One of those IPs can still exhaust its own budget.
            ip = "198.51.100.1"
            for _ in range(server.API_WIND_GRID_LIMIT - 1):
                self.assertEqual(self.get("/api/wind-grid", headers={"CF-Connecting-IP": ip})[0], 200)
            self.assertEqual(self.get("/api/wind-grid", headers={"CF-Connecting-IP": ip})[0], 429)

    def test_tile_rate_limit_allows_a_full_viewer_load(self):
        # 37 frames × 9 tiles = 333, well under 2400 / 5 min.
        png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
        with mock.patch.object(server, "fetch_radar_tile_ex", return_value=(200, "image/png", png, {"cache": "fresh"})):
            for i in range(333):
                st, _, _ = self.get("/api/radar/tile/7/36/50.png?t=202611201200")
                self.assertEqual(st, 200, i)

    def test_stale_tile_on_upstream_429_within_terms(self):
        png = b"\x89PNG\r\n\x1a\n" + b"cached-obs"
        with mock.patch.object(server, "stale_radar_tile", return_value=(200, "image/png", png)), \
             mock.patch.object(server, "cache_get", return_value=None), \
             mock.patch.object(server, "weatherapi_key", return_value="x" * 16), \
             mock.patch.object(server, "_valid_radar_tile", return_value=True), \
             mock.patch.object(server, "_refresh_radar_mem", return_value={"ok": True}), \
             mock.patch.object(server, "fetch_url_quiet", return_value=(429, "text/plain", b"quota")):
            with server.RADAR_LOCK:
                server._RADAR_MEM["tile_url"] = "https://api.weatherapi.com/v1/radar/tile/{z}/{x}/{y}.png?t={time}&sig=s"
            st, h, body = self.get("/api/radar/tile/7/36/50.png?t=202611201200")
        self.assertEqual(st, 200)
        self.assertEqual(body, png)
        self.assertEqual((h.get("X-Radar-Cache") or h.get("x-radar-cache")), "stale")

    def test_tile_429_without_stale_cache_returns_json(self):
        with mock.patch.object(server, "stale_radar_tile", return_value=None), \
             mock.patch.object(server, "cache_get", return_value=None), \
             mock.patch.object(server, "weatherapi_key", return_value="x" * 16), \
             mock.patch.object(server, "_valid_radar_tile", return_value=True), \
             mock.patch.object(server, "_refresh_radar_mem", return_value={"ok": True}), \
             mock.patch.object(server, "fetch_url_quiet", return_value=(429, "text/plain", b"quota")):
            with server.RADAR_LOCK:
                server._RADAR_MEM["tile_url"] = "https://api.weatherapi.com/v1/radar/tile/{z}/{x}/{y}.png?t={time}&sig=s"
            st, h, body = self.get("/api/radar/tile/7/36/50.png?t=202611201200")
        self.assertEqual(st, 429)
        data = json.loads(body)
        self.assertEqual(data["reason"], "quota")
        self.assertNotIn(b"sig=s", body)

    def test_radar_view_marks_limited_after_quota(self):
        server.note_radar_feed("quota", "Radar is temporarily limited. Showing cached observed frames where available.")
        frames = {"ok": True, "available": True, "frames": [{"time": "202611201200", "type": "observed", "time_epoch": 1}]}
        with mock.patch.object(server, "handle_radar_meta", return_value=(200, frames)):
            st, _, body = self.get("/api/radar-view")
        self.assertEqual(st, 200)
        data = json.loads(body)
        self.assertTrue(data["ok"])
        self.assertTrue(data["limited"])
        self.assertEqual(data["limit_reason"], "quota")
        self.assertIn("cached observed", data["limit_message"])


class Redaction(unittest.TestCase):
    def test_redacts_key_token_preview_and_keeps_safe_query(self):
        line = '127.0.0.1 - "GET /preview?key=SUPERSECRET HTTP/1.1" 302 -'
        out = server.redact_request_text(line)
        self.assertNotIn("SUPERSECRET", out)
        self.assertIn("key=REDACTED", out)
        self.assertIn("HTTP/1.1", out)
        self.assertIn("token=REDACTED", server.redact_request_text("/x?token=abc&preview=zzz"))
        self.assertIn("ahead=3", server.redact_request_text("GET /api/wind-grid?ahead=3 HTTP/1.1"))

    def test_log_message_redacts_requestline(self):
        buf = io.StringIO()
        class Dummy(server.Handler):
            def __init__(self):
                self.client_address = ("127.0.0.1", 9)
                self.requestline = "GET /preview?key=SUPERSECRET HTTP/1.1"
            def address_string(self):
                return "127.0.0.1"
        h = Dummy.__new__(Dummy)
        Dummy.__init__(h)
        with mock.patch.object(server.sys, "stderr", buf):
            h.log_message('"%s" %s %s', h.requestline, "302", "-")
        text = buf.getvalue()
        self.assertNotIn("SUPERSECRET", text)
        self.assertIn("key=REDACTED", text)

    def test_log_message_uses_cf_connecting_ip_not_peer(self):
        from http.client import HTTPMessage
        buf = io.StringIO()
        class Dummy(server.Handler):
            def __init__(self):
                self.client_address = ("127.0.0.1", 9)
                self.requestline = "GET /api/wind-grid HTTP/1.1"
                self.headers = HTTPMessage()
                self.headers["CF-Connecting-IP"] = "198.51.100.7"
                self.headers["X-Forwarded-For"] = "203.0.113.1, 198.51.100.7"
            def address_string(self):
                return "127.0.0.1"
        h = Dummy.__new__(Dummy)
        Dummy.__init__(h)
        with mock.patch.object(server.sys, "stderr", buf):
            h.log_message('"%s" %s %s', h.requestline, "200", "-")
        text = buf.getvalue()
        self.assertIn("198.51.100.7", text)
        self.assertNotIn("203.0.113.1", text)
        self.assertTrue(text.startswith("198.51.100.7 -"), text)

    def test_log_message_uses_leftmost_xff_without_cf_header(self):
        from http.client import HTTPMessage
        buf = io.StringIO()
        class Dummy(server.Handler):
            def __init__(self):
                self.client_address = ("127.0.0.1", 9)
                self.requestline = "GET /api/wind-grid HTTP/1.1"
                self.headers = HTTPMessage()
                self.headers["X-Forwarded-For"] = "203.0.113.44, 10.0.0.1"
            def address_string(self):
                return "127.0.0.1"
        h = Dummy.__new__(Dummy)
        Dummy.__init__(h)
        with mock.patch.object(server.sys, "stderr", buf):
            h.log_message('"%s" %s %s', h.requestline, "200", "-")
        text = buf.getvalue()
        self.assertTrue(text.startswith("203.0.113.44 -"), text)


class StaleTerms(unittest.TestCase):
    def test_stale_helper_rejects_old_observed_and_old_nowcast(self):
        png = b"\x89PNG\r\n\x1a\n" + b"x"
        fresh = {"status": 200, "ctype": "image/png", "body": png, "stored": 0, "expires": 0, "age": 10}
        old_obs = dict(fresh, age=61 * 60)
        old_nc = dict(fresh, age=200)
        with mock.patch.object(server, "cache_entry", return_value=fresh), \
             mock.patch.object(server, "radar_tile_is_nowcast", return_value=False):
            self.assertIsNotNone(server.stale_radar_tile("7", "36", "50", "202611201200"))
        with mock.patch.object(server, "cache_entry", return_value=old_obs), \
             mock.patch.object(server, "radar_tile_is_nowcast", return_value=False):
            self.assertIsNone(server.stale_radar_tile("7", "36", "50", "202611201200"))
        with mock.patch.object(server, "cache_entry", return_value=old_nc), \
             mock.patch.object(server, "radar_tile_is_nowcast", return_value=True):
            self.assertIsNone(server.stale_radar_tile("7", "36", "50", "202611201200"))


class ClientNoSecrets(unittest.TestCase):
    def test_public_assets_have_no_secret_markers(self):
        for name in ("wind-viewer.js", "radar-viewer.js", "radar-player.js", "wind.html", "radar.html", "showcase.js"):
            text = (server.ROOT / name).read_text(encoding="utf-8")
            for needle in ("WEATHERAPI_KEY", "PREVIEW_KEY", "api.weatherapi.com/v1/radar/tile"):
                self.assertNotIn(needle, text, name)


if __name__ == "__main__":
    unittest.main()
