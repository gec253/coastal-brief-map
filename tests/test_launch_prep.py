"""Launch-prep flags (t425u): default-off public routes, fixtures, homepage headers."""
from __future__ import annotations

import os
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path
from xml.etree import ElementTree as ET

import launch_flags
import server
import ramp_finder
import whats_biting

ROOT = Path(__file__).resolve().parents[1]
KEY = "k" * 32
SITE = "https://thecoastalbrief.com"
NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
FLAG_KEYS = (
    "PREVIEW_KEY",
    "HOME_SHOWCASE",
    "MORNING_BRIEF_ENABLED",
    "FRESHWATER_ENABLED",
    launch_flags.PUBLIC_WHATS_BITING,
    launch_flags.PUBLIC_RAMPS,
    launch_flags.PUBLIC_RAMP_MAP,
)


def _headers(r):
    return {k.lower(): v for k, v in r.getheaders()}


class LaunchFlags(unittest.TestCase):
    def setUp(self):
        self._env = {k: os.environ.get(k) for k in FLAG_KEYS}
        for k in FLAG_KEYS:
            os.environ.pop(k, None)

    def tearDown(self):
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_all_flags_default_off(self):
        self.assertFalse(launch_flags.whats_biting_public())
        self.assertFalse(launch_flags.ramps_public())
        self.assertFalse(launch_flags.ramp_map_public())
        self.assertFalse(launch_flags.ramps_routes_public())

    def test_opt_in_values(self):
        os.environ[launch_flags.PUBLIC_WHATS_BITING] = "1"
        self.assertTrue(launch_flags.whats_biting_public())
        os.environ[launch_flags.PUBLIC_WHATS_BITING] = "false"
        self.assertFalse(launch_flags.whats_biting_public())


class LaunchPrepRoutes(unittest.TestCase):
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
        self._env = {k: os.environ.get(k) for k in FLAG_KEYS}
        for k in FLAG_KEYS:
            os.environ.pop(k, None)

    def tearDown(self):
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def _req(self, path, cookie=False):
        headers = {}
        if cookie:
            os.environ["PREVIEW_KEY"] = KEY
            headers["Cookie"] = "%s=%s" % (server.PREVIEW_COOKIE, server._preview_cookie_value(KEY))
        c = HTTPConnection("127.0.0.1", self.port, timeout=25)
        c.request("GET", path, headers=headers)
        r = c.getresponse()
        body = r.read()
        hdrs = _headers(r)
        c.close()
        return r.status, hdrs, body

    def _locs(self, body: bytes):
        root = ET.fromstring(body)
        return [el.text for el in root.findall("sm:url/sm:loc", NS)]

    def test_flags_off_reports_and_ramps_are_404_and_homepage_unchanged(self):
        for path in (
            "/reports",
            "/reports/crystal-coast",
            "/reports/crystal-coast/when-the-sound-turns-cold",
            "/reports?fixture=freshness",
            "/ramps",
            "/ramps/parks-jordan-seaforth",
            "/ramps/map",
        ):
            status, _, body = self._req(path)
            self.assertEqual(status, 404, path)
            text = body.decode("utf-8", "replace").lower()
            self.assertNotIn("test fixture", text)
            self.assertNotIn("what’s biting?", text) if path.startswith("/ramps") else None
        status, hdrs, body = self._req("/")
        self.assertEqual(status, 200)
        self.assertNotIn(b'href="/reports"', body)
        self.assertNotIn(b'<nav class="folio-guides"', body)
        self.assertNotIn(b"Find a Ramp", body)
        self.assertNotIn(b"featured-in-the-coastal-brief", body)
        self.assertNotIn("cookie", (hdrs.get("vary") or "").lower())
        self.assertNotIn("noindex", (hdrs.get("x-robots-tag") or "").lower())
        st, _, sm = self._req("/sitemap.xml")
        self.assertEqual(st, 200)
        text = sm.decode()
        self.assertNotIn("/reports", text)
        self.assertNotIn("/ramps", text)

    def test_flags_off_preview_reports_still_cookie_gated_with_banner(self):
        status, _, _ = self._req("/reports")
        self.assertEqual(status, 404)
        os.environ["PREVIEW_KEY"] = KEY
        status, hdrs, body = self._req("/reports", cookie=True)
        self.assertEqual(status, 200)
        self.assertIn(b"Private preview", body)
        self.assertIn(b"noindex", body)
        self.assertIn("noindex", (hdrs.get("x-robots-tag") or "").lower())
        self.assertIn("Cookie", hdrs.get("vary") or "")
        self.assertNotIn(b"pending approval", body)

    def test_fixtures_blocked_on_public_reports_paths(self):
        os.environ["PREVIEW_KEY"] = KEY
        # Even with a cookie, /reports?fixture= is not a fixture page.
        status, _, body = self._req("/reports?fixture=freshness", cookie=True)
        self.assertEqual(status, 200)
        self.assertNotIn(b"TEST FIXTURE", body)
        self.assertIn("What’s Biting?".encode(), body)
        # Protected preview path may still serve fixtures.
        status, hdrs, body = self._req("/preview/reports?fixture=freshness", cookie=True)
        self.assertEqual(status, 200)
        self.assertIn(b"TEST FIXTURE", body)
        self.assertIn("noindex", (hdrs.get("x-robots-tag") or "").lower())
        status, _, _ = self._req("/preview/reports?fixture=freshness")
        self.assertEqual(status, 404)

    def test_whats_biting_flag_on_is_public_indexable_and_in_sitemap(self):
        os.environ[launch_flags.PUBLIC_WHATS_BITING] = "1"
        for path in (
            "/reports",
            "/reports/crystal-coast",
            "/reports/hatteras",
            "/reports/crystal-coast/when-the-sound-turns-cold",
            "/reports/hatteras/seatrout-winterkill-pamlico",
        ):
            status, hdrs, body = self._req(path)
            self.assertEqual(status, 200, path)
            self.assertNotIn(b"Private preview", body)
            self.assertNotIn(b"TEST FIXTURE", body)
            self.assertNotIn(b"pending approval", body)
            self.assertIn(b'name="robots" content="index, follow"', body)
            self.assertIn(b'rel="canonical"', body)
            self.assertNotIn("noindex", (hdrs.get("x-robots-tag") or "").lower())
            self.assertNotIn("cookie", (hdrs.get("vary") or "").lower())
        # Fixtures still blocked on the public route when the flag is on.
        status, _, body = self._req("/reports?fixture=freshness")
        self.assertEqual(status, 200)
        self.assertNotIn(b"TEST FIXTURE", body)
        status, _, sm = self._req("/sitemap.xml")
        text = sm.decode()
        self.assertIn(SITE + "/reports", text)
        self.assertIn(SITE + "/reports/crystal-coast", text)
        self.assertIn(SITE + "/reports/crystal-coast/when-the-sound-turns-cold", text)
        self.assertNotIn(SITE + "/ramps", text)
        # Homepage entry + featured, no noindex / cookie vary.
        status, hdrs, body = self._req("/")
        self.assertEqual(status, 200)
        self.assertIn(b'<div class="fr" id="fishing">', body)   # Signature Helm reports entry (was folio-guides)
        self.assertIn(b'href="/reports/crystal-coast"', body)
        self.assertNotIn(b"Find a Ramp", body)
        self.assertIn(b"featured-in-the-coastal-brief", body)
        self.assertNotIn("cookie", (hdrs.get("vary") or "").lower())
        self.assertNotIn("noindex", (hdrs.get("x-robots-tag") or "").lower())
        # Region pages
        status, _, body = self._req("/?region=hatteras")
        self.assertIn(b'href="/reports/hatteras"', body)
        status, _, body = self._req("/?region=nags-head")
        self.assertIn(b'href="/reports/hatteras"', body)
        self.assertIn(b"Hatteras Island reports", body)
        status, _, body = self._req("/?region=emerald-isle")
        self.assertIn(b'href="/reports/crystal-coast"', body)
        self.assertIn(b"Crystal Coast reports", body)
        self.assertNotIn(b"Find a Ramp", body)
        status, _, body = self._req("/?region=wilmington")
        self.assertIn(b'href="/reports"', body)
        status, _, body = self._req("/?region=falls-lake")
        self.assertIn(b'href="/reports/falls-lake"', body)
        self.assertNotIn(b"Find a Ramp", body)

    def test_published_at_hidden_until_set(self):
        data = whats_biting.load()
        region = whats_biting.region_by_id(data, "crystal-coast")
        article = whats_biting.article_by_slug(region, "when-the-sound-turns-cold")
        # Hidden when unset; set to the actual Stage A public-release date, never earlier.
        self.assertEqual(article.get("published_at"), "2026-11-23")
        html = whats_biting.render_article(data, region, article, public=True)
        self.assertIn("Published Nov 23, 2026", html)
        self.assertIn("Reviewed Nov 21, 2026", html)
        self.assertNotIn("pending approval", html)
        copy = dict(article)
        copy["published_at"] = None
        html = whats_biting.render_article(data, region, copy, public=True)
        self.assertIn("Reviewed Nov 21, 2026", html)
        self.assertNotIn("Published ", html)
        earlier = dict(article)
        earlier["published_at"] = "2026-11-22"
        html = whats_biting.render_article(data, region, earlier, public=True)
        self.assertIn("Published Nov 22, 2026", html)
        self.assertNotEqual(article.get("published_at"), "2026-11-22")

    def test_ramps_and_map_flags_off_keep_preview_cookie_gate(self):
        os.environ["PREVIEW_KEY"] = KEY
        status, _, _ = self._req("/preview/ramps")
        self.assertEqual(status, 404)
        status, hdrs, body = self._req("/preview/ramps", cookie=True)
        self.assertEqual(status, 200)
        self.assertIn(b"Private preview", body)
        self.assertIn("Cookie", hdrs.get("vary") or "")
        status, _, _ = self._req("/ramps")
        self.assertEqual(status, 404)
        status, _, _ = self._req("/ramps/map")
        self.assertEqual(status, 404)

    def test_home_b_stays_private(self):
        status, _, _ = self._req("/preview/home-b")
        self.assertEqual(status, 404)
        os.environ["PREVIEW_KEY"] = KEY
        os.environ[launch_flags.PUBLIC_WHATS_BITING] = "1"
        status, _, _ = self._req("/preview/home-b")
        self.assertEqual(status, 404)
        status, hdrs, body = self._req("/preview/home-b", cookie=True)
        self.assertEqual(status, 200)
        self.assertIn(b"noindex", body)


    def test_excluded_sources_stay_unpublished(self):
        raw = (ROOT / "data" / "whats_biting.json").read_text().lower()
        self.assertIn("flagged_for_review", (ROOT / "data" / "whats_biting.json").read_text())
        os.environ[launch_flags.PUBLIC_WHATS_BITING] = "1"
        status, _, body = self._req("/reports")
        self.assertEqual(status, 200)
        low = body.decode().lower()
        for needle in (
            "fisherman's post",
            "outerbankssurffishing",
            "carolinasportsman",
            "coastalanglermag",
            "islandfreepress",
        ):
            self.assertNotIn(needle, low)
        # Flagged URLs may remain in the data file but must not render.
        self.assertIn("outerbankssurffishing.com", raw)


    def test_dph_advisory_url_is_current_destination(self):
        data = whats_biting.load()
        url = data["notices"]["dph-advisories"]["source_url"]
        self.assertEqual(url, "https://epi.dph.ncdhhs.gov/oee/fish/arcg.html")
        html = whats_biting.render_region(
            data, whats_biting.region_by_id(data, "crystal-coast"), public=True
        )
        self.assertIn(url, html)
        self.assertNotIn("oee/fish/advisories.html", html)


class RampInventoryNotices(unittest.TestCase):
    def setUp(self):
        self.data = ramp_finder.load_data()

    def test_no_parkers_creek_record(self):
        ids = [r["id"] for r in self.data["records"]]
        self.assertEqual(len(ids), 55)
        self.assertFalse(any("parker" in i for i in ids))
        notice = self.data["meta"]["jordan_lake_official_notice"]
        self.assertEqual(notice["text"], ramp_finder.JORDAN_LOW_WATER_VISITOR_TEXT)
        self.assertIn("Parkers Creek", notice["text"])
        self.assertIn("no ramp record or coordinates were added", notice["internal_notes"])
        self.assertIn("Parkers Creek is not in this inventory", notice["internal_notes"])
        self.assertIn("recorded at the lake and region level only", notice["internal_notes"])
        self.assertIn("Vista Point & Parkers Creek boat ramps closed", notice["official_banner_quote"])
        self.assertIn("https://www.ncparks.gov/state-parks/jordan-lake-state-recreation-area", notice["source_url"])
        self.assertIn("8:39 PM EST", notice["accessed_at_label"])

    def test_seaforth_has_seasonal_and_low_water_notices(self):
        rec = ramp_finder.by_id("parks-jordan-seaforth", self.data)
        texts = [n["text"] for n in rec["notices"] if n["category"] == "current_dated_notice"]
        self.assertTrue(any("November 30, 2026" in t and "seasonal" in t.lower() for t in texts))
        self.assertTrue(any("distinct" in t.lower() and "November 30" in t for t in texts))
        html = ramp_finder.render_detail(self.data, rec, public=True)
        self.assertIn(ramp_finder.JORDAN_LOW_WATER_VISITOR_TEXT, html)
        self.assertIn("November 30, 2026", html)
        self.assertIn("Last checked 8:39 PM EST, Nov 22, 2026", html)
        self.assertIn("https://www.ncparks.gov/state-parks/jordan-lake-state-recreation-area", html)
        self.assertNotIn("no ramp record or coordinates were added", html)
        self.assertNotIn("not in this inventory", html)
        self.assertNotIn("Recheck this official page before any public release", html)
        self.assertNotIn("Open Now", html)
        self.assertNotIn("Private preview", html)

    def test_holly_point_keeps_conflicting_official_wording(self):
        rec = ramp_finder.by_id("parks-falls-holly-point-campers", self.data)
        text = " ".join(n["text"] for n in rec["notices"])
        self.assertIn("currently closed for construction", text)
        self.assertIn("will reopen by November 16, 2026", text)
        self.assertIn("does not invent a current open or closed state", text)
        self.assertNotIn("Open Now", text)


class PublicRampsFlags(unittest.TestCase):
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
        self._env = {k: os.environ.get(k) for k in FLAG_KEYS}
        for k in FLAG_KEYS:
            os.environ.pop(k, None)

    def tearDown(self):
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def _req(self, path):
        c = HTTPConnection("127.0.0.1", self.port, timeout=25)
        c.request("GET", path)
        r = c.getresponse()
        body = r.read()
        hdrs = {k.lower(): v for k, v in r.getheaders()}
        c.close()
        return r.status, hdrs, body

    def test_ramps_flag_on_list_and_detail_public(self):
        os.environ[launch_flags.PUBLIC_RAMPS] = "1"
        status, hdrs, body = self._req("/ramps?region=jordan-lake")
        self.assertEqual(status, 200)
        self.assertIn(b"Ramp Finder", body)
        self.assertNotIn(b"Private preview", body)
        self.assertIn(b'name="robots" content="index, follow"', body)
        self.assertIn(ramp_finder.JORDAN_LOW_WATER_VISITOR_TEXT.encode(), body)
        self.assertIn(b"Parkers Creek", body)
        self.assertIn(b"single-axle trailers only", body)
        self.assertIn(b"Last checked 2026-11-27 7:07 PM ET", body)
        self.assertNotIn(b"no ramp record or coordinates were added", body)
        self.assertNotIn("noindex", (hdrs.get("x-robots-tag") or "").lower())
        self.assertNotIn("cookie", (hdrs.get("vary") or "").lower())
        self.assertNotIn(b'href="/ramps/map"', body)  # map flag off
        status, _, body = self._req("/ramps/parks-jordan-seaforth")
        self.assertEqual(status, 200)
        self.assertIn(ramp_finder.JORDAN_LOW_WATER_VISITOR_TEXT.encode(), body)
        self.assertIn(b"November 30, 2026", body)
        self.assertIn(b"single-axle trailers only", body)
        self.assertNotIn(b"no ramp record or coordinates were added", body)
        self.assertNotIn(b"Private preview", body)
        self.assertNotIn(b"Private preview", body)
        status, _, _ = self._req("/ramps/map")
        self.assertEqual(status, 404)
        status, _, sm = self._req("/sitemap.xml")
        text = sm.decode()
        self.assertIn(SITE + "/ramps", text)
        self.assertNotIn(SITE + "/ramps/map", text)
        # Find a Ramp entry points
        status, _, body = self._req("/")
        self.assertIn(b"Find a Ramp", body)
        self.assertIn(b'href="/ramps?region=crystal-coast"', body)
        status, _, body = self._req("/?region=hatteras")
        self.assertIn(b"Find a Ramp", body)
        self.assertIn(b'href="/ramps"', body)
        self.assertIn(b"Ramps are not yet listed for this area", body)
        self.assertNotIn(b'href="/ramps?region=hatteras"', body)
        status, _, body = self._req("/?region=jordan-lake")
        self.assertIn(b'href="/ramps?region=jordan-lake"', body)

    def test_map_flag_on_serves_public_map(self):
        os.environ[launch_flags.PUBLIC_RAMP_MAP] = "1"
        status, hdrs, body = self._req("/ramps/map")
        self.assertEqual(status, 200)
        self.assertNotIn(b"Private preview", body)
        self.assertIn(b'name="robots" content="index, follow"', body)
        self.assertIn(b"Not for navigation", body)
        self.assertNotIn("noindex", (hdrs.get("x-robots-tag") or "").lower())
        status, _, js = self._req("/ramps/map.js")
        self.assertEqual(status, 200)
        status, _, sm = self._req("/sitemap.xml")
        self.assertIn(SITE + "/ramps/map", sm.decode())
        # List is also reachable so map detail links do not 404.
        status, _, body = self._req("/ramps/parks-jordan-seaforth")
        self.assertEqual(status, 200)
        self.assertIn(b"/ramps/parks-jordan-seaforth", body)  # may be canonical
