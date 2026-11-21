"""Private /reports What’s Biting? preview: freshness, gating, empty states, exclusions."""
from __future__ import annotations

import hashlib
import re
import os
import sys
import threading
import unittest
from datetime import datetime, timedelta
from http.client import HTTPConnection
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import whats_biting  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
KEY = "preview-test-key-24-chars-ok"


class FreshnessLogic(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 21, 16, 2, tzinfo=whats_biting.ET)

    def _date(self, days_ago: int):
        return (self.now.date() - timedelta(days=days_ago))

    def test_fresh_recent_aging_boundaries(self):
        f = whats_biting.freshness_label
        for d in (0, 1, 2, 3):
            self.assertEqual(f(self._date(d), self.now), "Fresh", d)
        for d in (4, 5, 7):
            self.assertEqual(f(self._date(d), self.now), "Recent", d)
        for d in (8, 10, 14):
            self.assertEqual(f(self._date(d), self.now), "Aging", d)
        self.assertIsNone(f(self._date(15), self.now))
        self.assertIsNone(f(None, self.now))

    def test_confirmed_and_local_reports_archive_after_14_days(self):
        region = {
            "reports": [{"source_name": "X", "as_of": self._date(14).isoformat()},
                        {"source_name": "Y", "as_of": self._date(15).isoformat()}],
            "confirmed": [{"source_name": "A", "as_of": self._date(14).isoformat(), "body": "ok"},
                          {"source_name": "B", "as_of": self._date(15).isoformat(), "body": "old"}],
        }
        reports = whats_biting.visible_reports(region, self.now)
        confirmed = whats_biting.visible_confirmed(region, self.now)
        self.assertEqual([r["source_name"] for r in reports], ["X"])
        self.assertEqual([c["source_name"] for c in confirmed], ["A"])
        self.assertTrue(whats_biting.is_archived(self._date(15), self.now))
        self.assertFalse(whats_biting.is_archived(self._date(14), self.now))

    def test_outlook_expires_after_48_hours(self):
        issued = self.now - timedelta(hours=48, seconds=1)
        still = self.now - timedelta(hours=47, minutes=59)
        dead = {"as_of": issued.isoformat(), "body": "old outlook"}
        live = {"as_of": still.isoformat(), "body": "current outlook"}
        self.assertFalse(whats_biting.outlook_visible(dead, self.now))
        self.assertTrue(whats_biting.outlook_visible(live, self.now))
        self.assertEqual(len(whats_biting.visible_outlooks({"outlooks": [dead, live]}, self.now)), 1)

    def test_outlook_expires_sooner_when_observations_are_stale(self):
        issued = self.now - timedelta(hours=1)
        item = {
            "as_of": issued.isoformat(),
            "observations_as_of": (self.now - timedelta(hours=6, minutes=1)).isoformat(),
            "body": "stale readings",
        }
        flagged = {"as_of": issued.isoformat(), "observations_stale": True, "body": "flagged"}
        fresh_obs = {
            "as_of": issued.isoformat(),
            "observations_as_of": (self.now - timedelta(hours=1)).isoformat(),
            "body": "fresh readings",
        }
        self.assertFalse(whats_biting.outlook_visible(item, self.now))
        self.assertFalse(whats_biting.outlook_visible(flagged, self.now))
        self.assertTrue(whats_biting.outlook_visible(fresh_obs, self.now))


class DataAndPages(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 21, 16, 2, tzinfo=whats_biting.ET)
        self.data = whats_biting.load()

    def test_five_regions_and_expected_first_party_dates(self):
        ids = [r["id"] for r in self.data["regions"]]
        self.assertEqual(ids, list(whats_biting.REGION_IDS))
        h = whats_biting.region_by_id(self.data, "hatteras")
        names = {r["source_name"] for r in h["reports"]}
        self.assertTrue(any("Capt. Marty" in n for n in names))
        self.assertTrue(any("Frank" in n and "Fran" in n for n in names))
        self.assertTrue(any("Frisco" in n for n in names))
        self.assertTrue(any("Hatteras Harbor" in n for n in names))
        self.assertEqual({r["as_of"] for r in h["reports"]}, {"2026-11-20"})
        cc = whats_biting.region_by_id(self.data, "crystal-coast")
        self.assertEqual(cc["reports"][0]["source_name"], "Bogue Inlet Pier")
        self.assertEqual(cc["reports"][0]["as_of"], "2026-11-15")
        self.assertEqual(cc["reports"][0]["source_url"], "https://www.bogueinletpier.com/fishing-reports/")

    def test_no_fishermans_post_in_data_or_html(self):
        raw = (ROOT / "data" / "whats_biting.json").read_text().lower()
        self.assertNotIn("fisherman's post", raw)
        self.assertNotIn("fishermanspost", raw)
        self.assertNotIn("fishermans post", raw)
        html = whats_biting.render_index(self.data, self.now) + "".join(
            whats_biting.render_region(self.data, r, self.now) for r in self.data["regions"]
        )
        low = html.lower()
        self.assertNotIn("fisherman", low)
        self.assertNotIn("fishermanspost", low)

    def _body(self, html: str) -> str:
        """Page body without the region switcher, which legitimately lists every region."""
        return re.sub(r'<nav class="region-nav"[^>]*>.*?</nav>', "", html, flags=re.S)

    def test_falls_is_never_jordan(self):
        falls = whats_biting.render_region(self.data, whats_biting.region_by_id(self.data, "falls-lake"), self.now)
        jordan = whats_biting.render_region(self.data, whats_biting.region_by_id(self.data, "jordan-lake"), self.now)
        self.assertIn("This is not Jordan Lake", falls)
        self.assertIn("This is not Falls Lake", jordan)
        falls_body = self._body(falls)
        jordan_body = self._body(jordan)
        # The only mention of the other lake on a lake page is the clarifying "this is not …" line.
        self.assertEqual(falls_body.count("Jordan Lake"), 1)
        self.assertEqual(jordan_body.count("Falls Lake"), 1)
        self.assertIn("does not appear on the 2026", falls_body)
        self.assertIn("Farrington Point", jordan_body)
        self.assertNotIn("Farrington Point", falls_body)
        self.assertNotIn("Falls Lake State Recreation Area", jordan_body)
        self.assertNotIn("Jordan Lake State Recreation Area", falls_body)

    def test_neuse_scope_excludes_lower_river_and_kennel_beach(self):
        neuse = whats_biting.render_region(self.data, whats_biting.region_by_id(self.data, "neuse-river"), self.now)
        self.assertIn("Falls Dam to Goldsboro", neuse)
        self.assertIn("not the lower tidal Neuse", neuse)
        self.assertNotIn("Kennel Beach", neuse)
        # "New Bern" may appear only in the clarifying "is not" sentence.
        self.assertIn("not the lower tidal Neuse or the New Bern estuary", neuse)
        self.assertEqual(neuse.count("New Bern"), 1)

    def test_empty_states_for_freshwater_and_confirmed(self):
        for rid in ("falls-lake", "jordan-lake", "neuse-river"):
            html = whats_biting.render_region(self.data, whats_biting.region_by_id(self.data, rid), self.now)
            self.assertIn('data-empty="reports"', html)
            self.assertIn('data-empty="confirmed"', html)
            self.assertIn("No dated first-party local reports", html)
            self.assertIn("No independently confirmed catch observations", html)
        h = whats_biting.render_region(self.data, whats_biting.region_by_id(self.data, "hatteras"), self.now)
        self.assertNotIn('data-empty="reports"', h)
        self.assertIn('data-empty="confirmed"', h)
        self.assertIn("None independently confirmed", h)
        # Nov 20 versus Nov 21 is Fresh.
        self.assertIn("badge-fresh", h)
        self.assertIn("November 20, 2026", h)
        cc = whats_biting.render_region(self.data, whats_biting.region_by_id(self.data, "crystal-coast"), self.now)
        # Nov 15 versus Nov 21 is Recent (6 days).
        self.assertIn("badge-recent", cc)
        self.assertIn("November 15, 2026", cc)

    def test_pages_are_noindex_and_do_not_republish_catch_body_from_sources(self):
        h = whats_biting.render_region(self.data, whats_biting.region_by_id(self.data, "hatteras"), self.now)
        self.assertIn('name="robots" content="noindex, nofollow"', h)
        self.assertIn("not republished", h.lower())
        # Glance shows newest date near the top, before official notices.
        top = h.split("Latest local reports")[0]
        self.assertIn("November 20, 2026", top)
        self.assertIn("Verified species", top)

    def test_flagged_publications_are_not_rendered(self):
        html = "".join(whats_biting.render_region(self.data, r, self.now) for r in self.data["regions"])
        self.assertNotIn("carolinasportsman.com", html)
        self.assertNotIn("coastalanglermag.com", html)
        self.assertNotIn("outerbankssurffishing.com", html)
        self.assertNotIn("islandfreepress.org", html)
        self.assertTrue(self.data.get("flagged_for_review"))

    def test_fixture_labels_and_hides_archived(self):
        fx = whats_biting.freshness_fixture_region(self.now)
        html = whats_biting.render_region(self.data, fx, self.now)
        self.assertIn("TEST FIXTURE", html)
        self.assertIn("badge-fresh", html)
        self.assertIn("badge-recent", html)
        self.assertIn("badge-aging", html)
        self.assertNotIn("should be hidden", html)
        empty = whats_biting.render_region(self.data, whats_biting.empty_fixture_region(), self.now)
        self.assertIn('data-empty="reports"', empty)
        self.assertIn('data-empty="confirmed"', empty)
        self.assertIn("TEST FIXTURE", empty)


class Gating(unittest.TestCase):
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
            conn = HTTPConnection("127.0.0.1", self.port, timeout=12)
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
        return "%s=%s" % (self.server.PREVIEW_COOKIE, self.server._preview_cookie_value(KEY))

    def _ok(self, path):
        return self._req(path, env={"PREVIEW_KEY": KEY}, cookie=self._cookie())

    def test_404_without_cookie_and_with_key_only(self):
        paths = [
            "/reports", "/reports/", "/reports.css",
            "/reports/hatteras", "/reports/falls-lake",
            "/preview/reports", "/preview/reports.css",
        ]
        for path in paths:
            status, _, _ = self._req(path)
            self.assertEqual(status, 404, path)
            status, _, _ = self._req(path, env={"PREVIEW_KEY": KEY})
            self.assertEqual(status, 404, path + " key set, no cookie")

    def test_cookie_unlocks_noindex_pages(self):
        for path in ("/reports", "/reports/hatteras", "/reports/crystal-coast",
                     "/reports/falls-lake", "/reports/jordan-lake", "/reports/neuse-river",
                     "/preview/reports"):
            status, body, hdrs = self._ok(path)
            self.assertEqual(status, 200, path)
            self.assertIn("noindex", hdrs.get("x-robots-tag", ""))
            self.assertIn(b"noindex, nofollow", body)
            self.assertIn("no-store", hdrs.get("cache-control", ""))
            self.assertIn("Cookie", hdrs.get("vary", ""))
        status, body, hdrs = self._ok("/reports.css")
        self.assertEqual(status, 200)
        self.assertIn("text/css", hdrs.get("content-type", ""))
        self.assertIn("noindex", hdrs.get("x-robots-tag", ""))

    def test_unknown_region_is_404_even_with_cookie(self):
        status, _, _ = self._ok("/reports/wilmington")
        self.assertEqual(status, 404)

    def test_not_in_sitemap_or_robots(self):
        status, body, _ = self._req("/sitemap.xml")
        self.assertEqual(status, 200)
        text = body.decode()
        self.assertNotIn("/reports", text)
        status, robots, _ = self._req("/robots.txt")
        self.assertEqual(status, 200)
        self.assertNotIn("/reports", robots.decode())

    def test_preview_hub_lists_the_feature_when_unlocked(self):
        status, body, _ = self._ok("/preview")
        self.assertEqual(status, 200)
        self.assertIn(b"/reports", body)
        self.assertIn("Biting".encode(), body)

    def test_homepage_and_brief_endpoints_still_public(self):
        status, body, _ = self._req("/")
        self.assertEqual(status, 200)
        self.assertIn(b"The Coastal Brief", body)
        self.assertNotIn(b'href="/reports"', body)
        status, _, _ = self._req("/brief?region=crystal-coast")
        # Brief may be on or off depending on env; either 200 or 404 is the existing flag behavior.
        self.assertIn(status, (200, 404))


class ProtectedSurfacesUnchanged(unittest.TestCase):
    def test_protected_paths_match_3bfca7e(self):
        """Homepage, Brief, viewers, and Catch Wall files must be byte-identical to the production baseline."""
        import subprocess
        baseline = "3bfca7e"
        for rel in whats_biting.PROTECTED_PATHS:
            proc = subprocess.run(
                ["git", "diff", "--name-only", baseline, "--", rel],
                cwd=ROOT, capture_output=True, text=True, check=True,
            )
            self.assertEqual(proc.stdout.strip(), "", f"{rel} changed from {baseline}")


if __name__ == "__main__":
    unittest.main()
