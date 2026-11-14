"""Public launch checks for the Morning Brief: default-on saltwater, private Falls Lake."""
import os
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import brief


class FlagOn(unittest.TestCase):
    def setUp(self):
        self._prev = os.environ.get("MORNING_BRIEF_ENABLED")
        os.environ.pop("MORNING_BRIEF_ENABLED", None)

    def tearDown(self):
        if self._prev is None:
            os.environ.pop("MORNING_BRIEF_ENABLED", None)
        else:
            os.environ["MORNING_BRIEF_ENABLED"] = self._prev

    def test_default_on_with_no_env(self):
        os.environ.pop("MORNING_BRIEF_ENABLED", None)
        self.assertTrue(brief.flag_on())

    def test_kill_switch(self):
        for v in ("0", "false", "off", "FALSE", "Off", " 0 "):
            os.environ["MORNING_BRIEF_ENABLED"] = v
            self.assertFalse(brief.flag_on(), msg=repr(v))

    def test_explicit_on_still_works(self):
        for v in ("1", "true", "on", "yes", ""):
            os.environ["MORNING_BRIEF_ENABLED"] = v
            self.assertTrue(brief.flag_on(), msg=repr(v))


class BriefPublicHTTP(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for k in ("MORNING_BRIEF_ENABLED", "FRESHWATER_ENABLED", "PREVIEW_KEY"):
            os.environ.pop(k, None)
        import server
        cls.server = server
        cls._orig_get_ads = server.get_ads
        def _fake_ads(force=False):
            return {"adsOn": False, "mode": "paused"}
        server.get_ads = _fake_ads
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.port = cls.httpd.server_address[1]
        t = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        t.start()
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
            body = e.read().decode("utf-8", "replace")
            return e.code, body, dict(e.headers)

    def test_public_saltwater_brief_200_with_no_env(self):
        for rid in ("crystal-coast", "hatteras"):
            status, body, headers = self._get("/brief?region=%s" % rid)
            self.assertEqual(status, 200, msg=rid)
            self.assertNotIn("private preview", body.lower())
            self.assertIn('name="robots" content="index, follow"', body)
            robots = (headers.get("X-Robots-Tag") or headers.get("x-robots-tag") or "").lower()
            self.assertIn("index", robots)
            self.assertIn("follow", robots)
            self.assertNotIn("noindex", robots)
            self.assertNotIn("Ad slot placeholder", body)
            self.assertNotIn("/brief?region=falls-lake", body)

    def test_falls_lake_404_without_freshwater_or_preview(self):
        status, body, _ = self._get("/brief?region=falls-lake")
        self.assertEqual(status, 404)

    def test_kill_switch_gives_404(self):
        os.environ["MORNING_BRIEF_ENABLED"] = "0"
        status, body, _ = self._get("/brief?region=crystal-coast")
        self.assertEqual(status, 404)
        status, _, _ = self._get("/brief?region=hatteras")
        self.assertEqual(status, 404)

    def test_homepage_unchanged_200(self):
        status, body, _ = self._get("/")
        self.assertEqual(status, 200)
        self.assertNotIn('href="/brief', body)
        self.assertNotIn("private preview", body.lower())

    def test_lake_dashboard_stays_404_with_no_flags(self):
        status, _, _ = self._get("/lake")
        self.assertEqual(status, 404)

    def test_falls_lake_200_with_freshwater_flag_is_noindex(self):
        os.environ["FRESHWATER_ENABLED"] = "1"
        status, body, headers = self._get("/brief?region=falls-lake")
        self.assertEqual(status, 200)
        self.assertIn('name="robots" content="noindex, nofollow"', body)
        robots = (headers.get("X-Robots-Tag") or headers.get("x-robots-tag") or "").lower()
        self.assertIn("noindex", robots)
        self.assertNotIn("private preview", body.lower())


if __name__ == "__main__":
    unittest.main()
