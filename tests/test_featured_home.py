"""Cookie-gated Featured in The Coastal Brief homepage section (Ed t412u).

Public / stays unchanged. The section renders only with a valid cb_preview cookie.
"""
from __future__ import annotations

import os
import re
import sys
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import featured_home  # noqa: E402
import server  # noqa: E402
import showcase  # noqa: E402
import signature_helm  # noqa: E402
import sprint_home  # noqa: E402
import theme_toggle  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
KEY = "featured-home-test-key-24ok!!"
CREDIT = b"Photograph: Vancemiller, public domain, via Wikimedia Commons."
HEADLINE = b"When the Sound Turns Cold"
TEASER = "What winter water temperatures mean for speckled trout in North Carolina’s coastal sounds.".encode()
HREF = b'href="/reports/crystal-coast/when-the-sound-turns-cold"'
ALT = b'alt="Fog over Bogue Sound, with a pier in silhouette."'
SECTION = b'id="featured-in-the-coastal-brief"'

def _normalize_live(body: bytes) -> bytes:
    """Strip volatile homepage media URLs so two renders can be compared."""
    body = re.sub(rb"https://[^\s\"']+supabase\.co/[^\s\"']+", b"CATCHWALL", body)
    body = re.sub(rb"/catch-wall-media/[^\s\"']+", b"CATCHWALL", body)
    return body




def _headers(resp):
    return {k.lower(): v for k, v in resp.getheaders()}


class Record(unittest.TestCase):
    def test_load_has_approved_copy(self):
        feat = featured_home.load()
        self.assertIsNotNone(feat)
        self.assertEqual(feat["category"], "On the Water")
        self.assertEqual(feat["headline"], "When the Sound Turns Cold")
        self.assertEqual(
            feat["dek"],
            "What winter water temperatures mean for speckled trout in North Carolina’s coastal sounds.",
        )
        self.assertEqual(feat["href"], "/reports/crystal-coast/when-the-sound-turns-cold")
        self.assertEqual(feat["cta"], "Read the Story")
        self.assertEqual(feat["image"]["credit"], "Photograph: Vancemiller, public domain, via Wikimedia Commons.")
        self.assertEqual(feat["image"]["alt"], "Fog over Bogue Sound, with a pier in silhouette.")
        self.assertNotIn("Spotted Seatrout and Winter Water Temperatures", feat["headline"])
        # Never name a more precise place than Bogue Sound, and never name the pier.
        alt = feat["image"]["alt"].lower()
        self.assertIn("bogue sound", alt)
        for banned in ("indian beach", "emerald isle", "beaufort inlet", "taylor", "hatteras"):
            self.assertNotIn(banned, alt)
        self.assertNotRegex(feat["image"]["alt"], r"(?i)named pier|the \\w+ pier")

    def test_inject_places_section_after_showcase_before_life(self):
        page = (
            b'<!doctype html><html><head></head><body>'
            b'<section class="cg" id="conditions">C</section>'
            b'<section class="sc sc-a" id="showcase">S</section>'
            b'<aside class="cb-life">L</aside>'
            b'<section class="hz">P</section></body></html>'
        )
        out = featured_home.inject(page).decode("utf-8")
        self.assertIn('id="featured-in-the-coastal-brief"', out)
        self.assertIn('id="cb-featured-css"', out)
        self.assertLess(out.find('id="showcase"'), out.find('id="featured-in-the-coastal-brief"'))
        self.assertLess(out.find('id="featured-in-the-coastal-brief"'), out.find('class="cb-life"'))
        self.assertIn("loading=\"lazy\"", out)
        self.assertIn("decoding=\"async\"", out)
        self.assertNotIn("fetchpriority", out)
        self.assertIn('type="image/avif"', out)
        self.assertIn('type="image/webp"', out)
        self.assertIn("srcset=", out)
        self.assertIn('width="1920"', out)
        self.assertIn('height="1080"', out)
        self.assertIn("Read the Story", out)
        self.assertIn("On the Water", out)
        # Freshwater hybrid pages stay unchanged.
        self.assertEqual(featured_home.inject(page, "falls-lake"), page)

    def test_picture_attrs_and_asset_files(self):
        html = featured_home.section()
        self.assertIn('srcset="/static/featured-in/bogue-sound-fog/bogue-sound-fog-640.avif 640w', html)
        self.assertIn("960w", html)
        self.assertIn("1280w", html)
        base = ROOT / "static" / "featured-in" / "bogue-sound-fog"
        for w in (640, 960, 1280):
            self.assertTrue((base / f"bogue-sound-fog-{w}.avif").is_file())
            self.assertTrue((base / f"bogue-sound-fog-{w}.webp").is_file())
        self.assertTrue((base / "bogue-sound-fog-1280.jpg").is_file())
        # Mobile 640 AVIF stays inside the 60–90 KB budget (this photo is much smaller).
        self.assertLess((base / "bogue-sound-fog-640.avif").stat().st_size, 60 * 1024)


class Routes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        cls.port = cls.httpd.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def setUp(self):
        self._env = {k: os.environ.get(k) for k in ("PREVIEW_KEY", "HOME_SHOWCASE", "MORNING_BRIEF_ENABLED", "FRESHWATER_ENABLED", "PUBLIC_WHATS_BITING", "PUBLIC_RAMPS", "PUBLIC_RAMP_MAP")}
        for k in self._env:
            os.environ.pop(k, None)

    def tearDown(self):
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def _req(self, path, cookie=None, key=None):
        if key:
            os.environ["PREVIEW_KEY"] = key
        elif key is None and cookie:
            os.environ["PREVIEW_KEY"] = KEY
        headers = {}
        if cookie == "valid":
            headers["Cookie"] = "%s=%s" % (server.PREVIEW_COOKIE, server._preview_cookie_value(os.environ["PREVIEW_KEY"]))
        elif cookie == "invalid":
            headers["Cookie"] = "%s=deadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef" % server.PREVIEW_COOKIE
        elif isinstance(cookie, str) and cookie not in ("valid", "invalid"):
            headers["Cookie"] = cookie
        c = HTTPConnection("127.0.0.1", self.port, timeout=25)
        c.request("GET", path, headers=headers)
        r = c.getresponse()
        body = r.read()
        hdrs = _headers(r)
        c.close()
        return r.status, hdrs, body

    def _cookie(self):
        return "valid"

    def _public_pipeline(self, rid=None, query=None):
        # Public homepage is Signature Helm (Ed t534u/t535u); showcase, featured and the shared theme
        # system (theme_toggle.paint) are built in by signature_helm.page.
        sc = showcase.variant(query or {}, rid)
        return signature_helm.page(rid, public=True, showcase_v=sc, radar_meta=server.handle_radar_meta), sc

    def test_no_cookie_section_absent_and_body_matches_pipeline(self):
        os.environ["HOME_SHOWCASE"] = "1"
        expected, _ = self._public_pipeline()
        status, hdrs, body = self._req("/")
        self.assertEqual(status, 200)
        self.assertNotIn(SECTION, body)
        self.assertNotIn(CREDIT, body)
        self.assertNotIn(b'id="cb-featured-css"', body)
        self.assertNotIn(b"/static/featured-in/bogue-sound-fog/", body)
        self.assertNotIn(HREF, body)
        self.assertEqual(_normalize_live(body), _normalize_live(expected))
        self.assertNotIn("cookie", (hdrs.get("vary") or "").lower())
        self.assertNotIn("noindex", (hdrs.get("x-robots-tag") or "").lower())
        self.assertIn("no-store", hdrs.get("cache-control") or "")

    def test_invalid_cookie_is_same_as_public(self):
        os.environ["HOME_SHOWCASE"] = "1"
        os.environ["PREVIEW_KEY"] = KEY
        status_pub, hdrs_pub, pub = self._req("/")
        status_bad, hdrs_bad, bad = self._req("/", cookie="invalid", key=KEY)
        self.assertEqual(status_pub, 200)
        self.assertEqual(status_bad, 200)
        # Live conditions can change between requests; the public pipeline is
        # compared in test_no_cookie_section_absent_and_body_matches_pipeline.
        self.assertNotIn(SECTION, pub)
        self.assertNotIn(SECTION, bad)
        self.assertNotIn(CREDIT, bad)
        self.assertNotIn(HREF, bad)
        self.assertNotIn("cookie", (hdrs_bad.get("vary") or "").lower())
        self.assertNotIn("noindex", (hdrs_bad.get("x-robots-tag") or "").lower())
        self.assertEqual(hdrs_pub.get("cache-control"), hdrs_bad.get("cache-control"))
        self.assertEqual(hdrs_pub.get("vary"), hdrs_bad.get("vary"))
        self.assertEqual(hdrs_pub.get("x-robots-tag"), hdrs_bad.get("x-robots-tag"))

    def test_key_set_without_cookie_stays_public(self):
        os.environ["HOME_SHOWCASE"] = "1"
        os.environ["PREVIEW_KEY"] = KEY
        expected, _ = self._public_pipeline()
        status, hdrs, body = self._req("/")
        self.assertEqual(status, 200)
        self.assertEqual(_normalize_live(body), _normalize_live(expected))
        self.assertNotIn(SECTION, body)

    def test_valid_cookie_does_not_inject_featured_when_flag_off(self):
        os.environ["HOME_SHOWCASE"] = "1"
        status, hdrs, body = self._req("/", cookie="valid", key=KEY)
        self.assertEqual(status, 200)
        self.assertNotIn(SECTION, body)
        self.assertNotIn("cookie", (hdrs.get("vary") or "").lower())
        self.assertNotIn("noindex", (hdrs.get("x-robots-tag") or "").lower())

    def test_flag_on_renders_featured_for_everyone_without_noindex_or_cookie_vary(self):
        os.environ["PUBLIC_WHATS_BITING"] = "1"
        os.environ["HOME_SHOWCASE"] = "1"
        status, hdrs, body = self._req("/")
        self.assertEqual(status, 200)
        self.assertIn(SECTION, body)
        self.assertIn(b">On the Water<", body)
        self.assertIn(b">Featured in The Coastal Brief<", body)
        self.assertIn(HEADLINE, body)
        self.assertNotIn(b"Spotted Seatrout and Winter Water Temperatures", body)
        self.assertIn(TEASER, body)
        self.assertIn(CREDIT, body)
        self.assertIn(HREF, body)
        self.assertIn(b">Read the Story</a>", body)
        self.assertIn(ALT, body)
        self.assertIn(b'type="image/avif"', body)
        self.assertIn(b'type="image/webp"', body)
        self.assertIn(b'srcset="', body)
        self.assertIn(b'width="1920"', body)
        self.assertIn(b'height="1080"', body)
        self.assertIn(b'loading="lazy"', body)
        self.assertIn(b'decoding="async"', body)
        feat_html = body[body.find(SECTION):body.find(b'<p class="index" id="tools"')]
        self.assertNotIn(b"fetchpriority", feat_html)
        self.assertNotIn("cookie", (hdrs.get("vary") or "").lower())
        self.assertNotIn("noindex", (hdrs.get("x-robots-tag") or "").lower())
        # Placement: after Wind & Radar, before the Morning Brief entry and the tools index (Signature Helm).
        sc = body.find(b'id="showcase"')
        feat = body.find(SECTION)
        life = body.find(b'<a class="briefbox"')
        self.assertTrue(0 < sc < feat < life < body.find(b'<p class="index" id="tools"'), (sc, feat, life))
        # Existing homepage chrome is still there.
        self.assertIn(b'id="helm"', body)
        self.assertIn(b'<html lang="en" data-helm data-water="salt"', body)
        self.assertIn(b"More than the forecast", body)

    def test_flag_on_without_showcase_still_sits_before_lifestyle(self):
        os.environ["PUBLIC_WHATS_BITING"] = "1"
        status, hdrs, body = self._req("/")
        self.assertEqual(status, 200)
        self.assertIn(SECTION, body)
        self.assertNotIn("cookie", (hdrs.get("vary") or "").lower())
        self.assertNotIn("noindex", (hdrs.get("x-robots-tag") or "").lower())
        self.assertEqual(body.find(b'id="showcase"'), -1)
        self.assertLess(0, body.find(SECTION))
        self.assertLess(body.find(SECTION), body.find(b'<p class="index" id="tools"'))

    def test_freshwater_home_does_not_get_the_feature(self):
        os.environ["FRESHWATER_ENABLED"] = "1"
        os.environ["PREVIEW_KEY"] = KEY
        status, _, body = self._req("/?region=falls-lake", cookie="valid", key=KEY)
        self.assertEqual(status, 200)
        self.assertNotIn(SECTION, body)
        self.assertNotIn(CREDIT, body)

    def test_article_stays_cookie_gated(self):
        path = "/reports/crystal-coast/when-the-sound-turns-cold"
        os.environ["PREVIEW_KEY"] = KEY
        s404, _, b404 = self._req(path)
        self.assertEqual(s404, 404)
        self.assertNotIn(HEADLINE, b404)
        s_bad, _, _ = self._req(path, cookie="invalid", key=KEY)
        self.assertEqual(s_bad, 404)
        s_ok, hdrs, body = self._req(path, cookie="valid", key=KEY)
        self.assertEqual(s_ok, 200)
        self.assertIn(b"When the Sound Turns Cold", body)
        self.assertIn("no-store", hdrs.get("cache-control") or "")
        self.assertIn("Cookie", hdrs.get("vary") or "")

    def test_photo_assets_are_served(self):
        s, hdrs, body = self._req("/static/featured-in/bogue-sound-fog/bogue-sound-fog-640.avif")
        self.assertEqual(s, 200)
        self.assertIn("avif", (hdrs.get("content-type") or "").lower())
        self.assertGreater(len(body), 100)
        s2, _, _ = self._req("/static/featured-in/featured.css")
        self.assertEqual(s2, 200)


if __name__ == "__main__":
    unittest.main()
