"""Private preview Morning Briefs for Wilmington, Nags Head, Emerald Isle and Topsail.

They are behind the cb_preview cookie at /preview/brief/<id>, never on /brief, never in
brief.enabled_regions(), and never stored or archived."""
from __future__ import annotations

import hashlib
import hmac
import os
import sys
import threading
import unittest
from datetime import datetime, timezone
from http.client import HTTPConnection
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import brief  # noqa: E402
import brief_preview  # noqa: E402

NEW = ["wilmington", "nags-head", "emerald-isle", "topsail"]
KEY = "preview-test-key-24-chars-ok"
NOW = datetime(2026, 11, 14, 15, 0, tzinfo=timezone.utc)


def _body(rid, missing=(), pressure="30.03 inHg, 3-hour trend not reported, up 6.5 hPa over 10 h at 41064."):
    cfg = brief_preview._cfg(rid)
    return {"region": {"id": rid, "name": cfg["name"], "area": cfg.get("area"), "anchor": cfg["anchor"]},
            "waterType": "saltwater",
            "items": [("Advisories", "No NWS marine advisories for this area."), ("Wind", "10 kt from the N, gusting 14, at X."),
                      ("Seas", "2.0 ft every 6 s from the E at Y."), ("Pressure", pressure),
                      ("Marine forecast", "Today: N winds 10 kt. (NWS %s)" % cfg["marine"]["zone"]),
                      ("Tides", "high 10:31 AM ET (4.3 ft) at Z, MLLW."),
                      ("Water temp", "Inshore unavailable (no sensor in this area); 63°F offshore at Nags Head offshore (CDIP 243).")],
            "freshness": [], "take": ["No advisories and no big overnight changes in the readings."], "missing": list(missing),
            "marineZone": cfg["marine"]["zone"], "marineUpdated": None, "forecastUpdated": None, "sources": "NOAA"}


OFF = {"ok": True, "readings": {"waterTempOffshore": {"status": "ok", "values": {"f": 63.1},
                                                      "time": "2026-11-14T14:50:00+00:00", "station": {"id": "44086", "name": "Nags Head offshore"}}}}


class Unchanged(unittest.TestCase):
    def test_enabled_regions_unchanged(self):
        self.assertEqual(brief.enabled_regions(False), ["crystal-coast", "hatteras"])
        for rid in NEW:
            self.assertNotIn(rid, brief.enabled_regions(True))
            self.assertNotIn(rid, brief.enabled_regions(False))

    def test_public_get_still_404(self):
        for rid in NEW:
            self.assertEqual(brief.get(rid, include_fresh=True)[0], 404, rid)

    def test_live_regions_have_no_preview(self):
        for rid in ("crystal-coast", "hatteras", "falls-lake", "bogus"):
            self.assertFalse(brief_preview.available(rid), rid)
        for rid in NEW:
            self.assertTrue(brief_preview.available(rid), rid)


class Compose(unittest.TestCase):
    def test_never_stores_or_archives(self):
        with patch.object(brief, "build_salt", side_effect=lambda rid, now: _body(rid)), \
             patch("conditions.assemble", return_value=(200, OFF)), \
             patch.object(brief, "_save") as save, patch.object(brief, "build") as build:
            before = dict(brief._mem)
            b = brief_preview.compose("nags-head", NOW)
            save.assert_not_called(); build.assert_not_called()
            self.assertEqual(brief._mem, before)
        self.assertTrue(b["preview"])
        self.assertNotIn("water temp", b["missing"])
        wt = dict(b["items"])["Water temp"]
        self.assertIn("Not measured", wt); self.assertIn("63°F", wt); self.assertIn("offshore", wt.lower())
        self.assertIn("Inshore water temp", [k for k, _ in b["unavailable"]])
        self.assertNotIn("None", dict(b["items"])["Pressure"])
        self.assertEqual(b["validation"]["errors"], [])

    def test_page_is_private_and_labeled(self):
        with patch.object(brief, "build_salt", side_effect=lambda rid, now: _body(rid)), \
             patch("conditions.assemble", return_value=(200, OFF)):
            html = brief_preview.page(brief_preview.compose("topsail", NOW))
        self.assertIn("Private preview · not published", html)
        self.assertIn('content="noindex, nofollow"', html)
        self.assertIn("Not measured in this area", html)
        self.assertIn('href="/preview/brief/wilmington"', html)
        self.assertNotIn('href="/brief?region=', html)


class Gate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import server
        cls.server = server
        cls.httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.port = cls.httpd.server_address[1]
        cls.cookie = "cb_preview=" + hmac.new(KEY.encode(), b"coastal-brief-preview-v1", hashlib.sha256).hexdigest()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown(); cls.httpd.server_close()

    def setUp(self):
        self._saved = os.environ.get("PREVIEW_KEY")
        os.environ["PREVIEW_KEY"] = KEY
        brief_preview._cache.clear()
        p1 = patch.object(brief, "build_salt", side_effect=lambda rid, now: _body(rid))
        p2 = patch("conditions.assemble", return_value=(200, OFF))
        p1.start(); p2.start()
        self.addCleanup(p1.stop); self.addCleanup(p2.stop)

    def tearDown(self):
        if self._saved is None:
            os.environ.pop("PREVIEW_KEY", None)
        else:
            os.environ["PREVIEW_KEY"] = self._saved
        brief_preview._cache.clear()

    def _get(self, path, cookie=None):
        c = HTTPConnection("127.0.0.1", self.port, timeout=10)
        c.request("GET", path, headers={"Cookie": cookie} if cookie else {})
        r = c.getresponse(); body = r.read(); hdrs = {k.lower(): v for k, v in r.getheaders()}; c.close()
        return r.status, body.decode("utf-8", "replace"), hdrs

    def test_404_without_cookie(self):
        for rid in NEW:
            self.assertEqual(self._get("/preview/brief/" + rid)[0], 404, rid)
            self.assertEqual(self._get("/preview/brief/" + rid, "cb_preview=wrong")[0], 404, rid)

    def test_404_when_no_key_configured(self):
        os.environ.pop("PREVIEW_KEY", None)
        self.assertEqual(self._get("/preview/brief/wilmington", self.cookie)[0], 404)

    def test_200_with_cookie(self):
        for rid in NEW:
            st, body, h = self._get("/preview/brief/" + rid, self.cookie)
            self.assertEqual(st, 200, rid)
            self.assertIn("Private preview", body)
            self.assertEqual(h.get("x-robots-tag"), "noindex, nofollow")
            self.assertIn("no-store", h.get("cache-control", ""))

    def test_unknown_or_live_region_404_even_with_cookie(self):
        for rid in ("crystal-coast", "hatteras", "falls-lake", "bogus", ""):
            self.assertEqual(self._get("/preview/brief/" + rid, self.cookie)[0], 404, rid)

    def test_public_brief_routes_unchanged(self):
        for rid in NEW:
            for ck in (None, self.cookie):
                self.assertEqual(self._get("/brief?region=" + rid, ck)[0], 404, rid)
                self.assertEqual(self._get("/api/brief?region=" + rid, ck)[0], 404, rid)
                self.assertEqual(self._get("/%s/brief" % rid, ck)[0], 404, rid)

    def test_hub_lists_preview_briefs(self):
        st, body, _ = self._get("/preview", self.cookie)
        self.assertEqual(st, 200)
        for rid in NEW:
            self.assertIn('href="/preview/brief/%s"' % rid, body)

    def test_sitemap_has_no_preview_briefs(self):
        st, body, _ = self._get("/sitemap.xml")
        self.assertNotIn("/preview/brief", body)


if __name__ == "__main__":
    unittest.main()
