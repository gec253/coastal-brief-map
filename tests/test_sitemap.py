"""robots.txt and sitemap.xml: content types, Sitemap line, and flag gating."""
import os
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from xml.etree import ElementTree as ET

SITE = "https://thecoastalbrief.com"
NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}

ALWAYS = {
    SITE + "/",
    SITE + "/catch-wall",
    SITE + "/coastal-life",
    SITE + "/photos",
}
SALT_BRIEFS = {
    SITE + "/brief?region=crystal-coast",
    SITE + "/brief?region=hatteras",
}
FALLS_BRIEF = SITE + "/brief?region=falls-lake"
LAKE_PAGES = {
    SITE + "/lake?region=falls-lake",
    SITE + "/lake?region=jordan-lake",
    SITE + "/lake?region=neuse-river",
}


class RobotsAndSitemap(unittest.TestCase):
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
        for k in ("MORNING_BRIEF_ENABLED", "FRESHWATER_ENABLED", "PREVIEW_KEY"):
            os.environ.pop(k, None)

    def setUp(self):
        for k in ("MORNING_BRIEF_ENABLED", "FRESHWATER_ENABLED", "PREVIEW_KEY"):
            os.environ.pop(k, None)

    def _get(self, path):
        req = urllib.request.Request(self.base + path)
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                return r.status, r.read(), dict(r.headers)
        except urllib.error.HTTPError as e:
            return e.code, e.read(), dict(e.headers)

    def _locs(self, body: bytes):
        root = ET.fromstring(body)
        return [el.text for el in root.findall("sm:url/sm:loc", NS)]

    def test_robots_allow_all_and_absolute_sitemap_line(self):
        status, body, headers = self._get("/robots.txt")
        self.assertEqual(status, 200)
        ctype = headers.get("Content-Type") or headers.get("content-type")
        self.assertTrue(ctype.startswith("text/plain"), msg=ctype)
        text = body.decode()
        self.assertIn("User-agent: *", text)
        self.assertIn("Allow: /", text)
        self.assertIn("Sitemap: https://thecoastalbrief.com/sitemap.xml", text)
        self.assertNotIn("Disallow: /", text)

    def test_sitemap_content_type_and_default_public_urls(self):
        status, body, headers = self._get("/sitemap.xml")
        self.assertEqual(status, 200)
        ctype = headers.get("Content-Type") or headers.get("content-type")
        self.assertTrue(ctype.startswith("application/xml"), msg=ctype)
        locs = self._locs(body)
        self.assertEqual(set(locs), ALWAYS | SALT_BRIEFS | {FALLS_BRIEF} | LAKE_PAGES)
        # No Jordan/Neuse briefs: those regions have /lake pages only.
        self.assertNotIn(SITE + "/brief?region=jordan-lake", locs)
        self.assertNotIn(SITE + "/brief?region=neuse-river", locs)

    def test_brief_kill_switch_omits_briefs_keeps_lakes(self):
        os.environ["MORNING_BRIEF_ENABLED"] = "0"
        locs = set(self._locs(self._get("/sitemap.xml")[1]))
        self.assertTrue(ALWAYS.issubset(locs))
        self.assertTrue(LAKE_PAGES.issubset(locs))
        self.assertFalse(SALT_BRIEFS & locs)
        self.assertNotIn(FALLS_BRIEF, locs)
        self.assertEqual(self._get("/brief?region=crystal-coast")[0], 404)

    def test_freshwater_kill_switch_omits_lakes_and_falls_brief(self):
        os.environ["FRESHWATER_ENABLED"] = "0"
        locs = set(self._locs(self._get("/sitemap.xml")[1]))
        self.assertTrue(ALWAYS.issubset(locs))
        self.assertTrue(SALT_BRIEFS.issubset(locs))
        self.assertNotIn(FALLS_BRIEF, locs)
        self.assertFalse(LAKE_PAGES & locs)
        self.assertEqual(self._get("/lake?region=falls-lake")[0], 404)
        self.assertEqual(self._get("/brief?region=hatteras")[0], 200)

    def test_both_kill_switches_leave_only_always_public_pages(self):
        os.environ["MORNING_BRIEF_ENABLED"] = "off"
        os.environ["FRESHWATER_ENABLED"] = "false"
        locs = set(self._locs(self._get("/sitemap.xml")[1]))
        self.assertEqual(locs, ALWAYS)
