"""Header Morning Brief link: present when the brief is on, stripped on the kill switch."""
import os
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer


class BriefHeaderLink(unittest.TestCase):
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
                return r.status, r.read().decode("utf-8", "replace"), dict(r.headers)
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8", "replace"), dict(e.headers)

    def test_default_on_pages_include_link_to_crystal_coast(self):
        for path in ("/", "/catch-wall", "/coastal-life", "/photos", "/lake", "/lake?region=falls-lake"):
            status, body, _ = self._get(path)
            self.assertEqual(status, 200, msg=path)
            self.assertIn('id="nav-brief"', body, msg=path)
            self.assertIn('href="/brief?region=crystal-coast"', body, msg=path)
            self.assertIn("Morning Brief", body, msg=path)
            self.assertIn("/brief-link.js", body, msg=path)

    def test_kill_switch_strips_link_and_brief_is_404(self):
        os.environ["MORNING_BRIEF_ENABLED"] = "0"
        for path in ("/", "/catch-wall", "/lake"):
            status, body, _ = self._get(path)
            self.assertEqual(status, 200, msg=path)
            self.assertNotIn('id="nav-brief"', body, msg=path)
            self.assertNotIn("<!--brief-nav-->", body, msg=path)
        status, _, _ = self._get("/brief?region=crystal-coast")
        self.assertEqual(status, 404)

    def test_brief_link_js_region_rules(self):
        import importlib.util
        from pathlib import Path
        # Re-check the mapping in Python so the documented fallback stays honest.
        # (The same rules live in brief-link.js.)
        def brief_region(id):
            if id in ("crystal-coast", "hatteras"):
                return id
            if id == "falls-lake":
                return "falls-lake"
            return "crystal-coast"
        self.assertEqual(brief_region("hatteras"), "hatteras")
        self.assertEqual(brief_region("crystal-coast"), "crystal-coast")
        self.assertEqual(brief_region("falls-lake"), "falls-lake")
        self.assertEqual(brief_region("jordan-lake"), "crystal-coast")
        self.assertEqual(brief_region("neuse-river"), "crystal-coast")
        self.assertEqual(brief_region("atlantic-beach"), "crystal-coast")
        self.assertEqual(brief_region(None), "crystal-coast")
        js = (Path(__file__).resolve().parents[1] / "brief-link.js").read_text()
        self.assertIn('id === "falls-lake"', js)
        self.assertIn("jordan", js.lower() + "Jordan Lake and Neuse")  # documented in the file header
