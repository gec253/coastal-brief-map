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
        as_of = {r["source_name"]: r["as_of"] for r in h["reports"]}
        self.assertEqual(as_of.get("Frank & Fran's, Avon"), "2026-11-21")
        marty = next(r for r in h["reports"] if "Capt. Marty" in r["source_name"])
        self.assertEqual(marty["as_of"], "2026-11-23")
        self.assertEqual(marty["title"], "Fishing Report 11-23")
        self.assertEqual(
            {r["as_of"] for r in h["reports"] if "Fran" not in r["source_name"] and "Capt. Marty" not in r["source_name"]},
            {"2026-11-20"},
        )
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
        # Nov 20 or Nov 21 versus Nov 21 is Fresh.
        self.assertIn("badge-fresh", h)
        self.assertIn("November 20, 2026", h)
        self.assertIn("November 21, 2026", h)
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
        self.assertIn("November 23, 2026", top)
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
        saved = {k: os.environ.get(k) for k in ("PREVIEW_KEY", "MORNING_BRIEF_ENABLED", "FRESHWATER_ENABLED", "PUBLIC_WHATS_BITING", "PUBLIC_RAMPS", "PUBLIC_RAMP_MAP")}
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
        # Ed t444u: the Wind & Radar region fix intentionally changed these; they are pinned to that fix instead.
        t444u = {"showcase.js": "d6b4900", "showcase.css": "d6b4900", "showcase.py": "d6b4900", "radar-viewer.js": "d6b4900"}
        # Ed t468u: the shared Light / Dark / Auto theme system needed small listeners here; pinned to that fix.
        t444u.update({"app.js": "c4ac86c", "radar-viewer.js": "c4ac86c"})
        # Ed t476u / t477u: homepage_boot.py and dashboard.js are pinned to the
        # approved Hatteras wind-selection repair (c039549).
        # Ed t489u: both re-pinned to the approved Full Dashboard alert-display repair (d5ea520; SHA-256
        # homepage_boot.py 9e9f3591349135a7bb84c5c27978637a5805291d33a35337262d2ee6979d959f,
        # dashboard.js e6e4e879bcad83b4ed6aa9445bc50b0b8aacc534b19a99f8f1acce30a45ffdf6).
        t444u.update({"homepage_boot.py": "d5ea520", "dashboard.js": "d5ea520"})
        # t440u / t446u: brief.py and brief.css are the approved Morning Brief
        # refinements; homepage, viewers, and Catch Wall stay locked.
        for rel in whats_biting.PROTECTED_PATHS:
            if rel in ("brief.py", "brief.css"):
                continue
            proc = subprocess.run(
                ["git", "diff", "--name-only", t444u.get(rel, baseline), "--", rel],
                cwd=ROOT, capture_output=True, text=True, check=True,
            )
            self.assertEqual(proc.stdout.strip(), "", f"{rel} changed from {baseline}")




class TestOnTheWaterArticles(unittest.TestCase):
    """Cookie-gated On the Water articles and regional headline cards."""

    CC = "/reports/crystal-coast/when-the-sound-turns-cold"
    HI = "/reports/hatteras/seatrout-winterkill-pamlico"
    PATHS = (
        CC,
        HI,
        "/preview/reports/crystal-coast/when-the-sound-turns-cold",
        "/preview/reports/hatteras/seatrout-winterkill-pamlico",
    )

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
        saved = {k: os.environ.get(k) for k in ("PREVIEW_KEY", "MORNING_BRIEF_ENABLED", "FRESHWATER_ENABLED", "PUBLIC_WHATS_BITING", "PUBLIC_RAMPS", "PUBLIC_RAMP_MAP")}
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

    def _html(self, path: str) -> str:
        status, body, _ = self._ok(path)
        self.assertEqual(status, 200, path)
        return body.decode("utf-8")

    def _article_body(self, path: str) -> str:
        return re.sub(r"<style>.*?</style>", "", self._html(path), flags=re.S)

    def test_articles_404_without_cookie(self):
        for path in self.PATHS:
            with self.subTest(path=path):
                status, _, _ = self._req(path)
                self.assertEqual(status, 404)
                status, _, _ = self._req(path, env={"PREVIEW_KEY": KEY})
                self.assertEqual(status, 404, path + " key set, no cookie")

    def test_articles_200_gated_headers(self):
        for path in self.PATHS:
            with self.subTest(path=path):
                status, body, hdrs = self._ok(path)
                self.assertEqual(status, 200)
                self.assertIn("noindex", hdrs.get("x-robots-tag", "").lower())
                self.assertIn("no-store", hdrs.get("cache-control", "").lower())
                self.assertIn("Cookie", hdrs.get("vary", ""))
                self.assertIn(b"noindex, nofollow", body)

    def test_unknown_or_mismatched_slugs_404(self):
        for path in (
            "/reports/crystal-coast/missing",
            "/reports/hatteras/when-the-sound-turns-cold",
            "/reports/crystal-coast/seatrout-winterkill-pamlico",
            "/reports/falls-lake/when-the-sound-turns-cold",
            "/reports/jordan-lake/seatrout-winterkill-pamlico",
            "/reports/hatteras/seatrout-winterkill-pamlico/extra",
        ):
            with self.subTest(path=path):
                status, _, _ = self._ok(path)
                self.assertEqual(status, 404)

    def test_crystal_coast_approved_text(self):
        html = self._article_body(self.CC)
        self.assertIn("When the Sound Turns Cold: Spotted Seatrout and Winter Water Temperatures", html)
        self.assertIn("DMF’s 2019 management explainer sets useful marks, in Fahrenheit:", html)
        self.assertIn(
            "Effective December 1, 2025, harvested spotted seatrout must be reported to DMF at",
            html,
        )
        self.assertIn('href="https://deq.nc.gov/report-my-fish"', html)
        self.assertIn("deq.nc.gov/report-my-fish", html)
        self.assertNotIn("certain inland waters", html)
        self.assertIn("Reviewed Nov 21, 2026", html)
        self.assertNotIn("pending approval", html)
        self.assertNotIn("Published:", html)
        self.assertIn('href="/reports/crystal-coast"', html)
        self.assertIn("Rules to check", html)
        self.assertIn("Skip to the article", html)

    def test_hatteras_approved_text(self):
        html = self._article_body(self.HI)
        self.assertIn("Winterkill Science in Pamlico Sound: Spotted Seatrout After a Hard Winter", html)
        self.assertIn("almost 5.5 percent", html)
        self.assertIn("Pungo Creek", html)
        self.assertIn(
            "Effective December 1, 2025, harvested spotted seatrout must be reported to DMF at",
            html,
        )
        self.assertIn('href="https://deq.nc.gov/report-my-fish"', html)
        self.assertNotIn("DMF’s 2019 management explainer sets useful marks, in Fahrenheit:", html)
        self.assertIn("Reviewed Nov 21, 2026", html)
        self.assertNotIn("pending approval", html)
        self.assertNotIn("Published:", html)
        self.assertIn('href="/reports/hatteras"', html)
        self.assertIn("Rules to check", html)

    def test_articles_have_no_freshness_labels(self):
        for path in (self.CC, self.HI):
            body = self._article_body(path)
            with self.subTest(path=path):
                self.assertNotIn("badge-fresh", body)
                self.assertNotIn("badge-recent", body)
                self.assertNotIn("badge-aging", body)
                self.assertNotIn(">Fresh<", body)
                self.assertNotIn(">Recent<", body)
                self.assertNotIn(">Aging<", body)

    def test_headline_cards_follow_reports_and_confirmed(self):
        cc = self._html("/reports/crystal-coast")
        self.assertIn('href="/reports/crystal-coast/when-the-sound-turns-cold"', cc)
        self.assertIn("When the Sound Turns Cold: Spotted Seatrout and Winter Water Temperatures", cc)
        self.assertIn("Reviewed Nov 21, 2026", cc)
        self.assertNotIn("pending approval", cc)
        self.assertNotIn("Published:", cc)
        self.assertLess(cc.find(">Latest local reports<"), cc.find(">Confirmed activity<"))
        self.assertLess(cc.find(">Confirmed activity<"), cc.find('id="otw-heading"'))
        self.assertLess(cc.find('id="otw-heading"'), cc.find(">Official notices<"))
        otw = cc[cc.find('id="otw-heading"'):cc.find(">Official notices<")]
        self.assertNotIn("badge-fresh", otw)
        self.assertNotIn("badge-recent", otw)
        self.assertNotIn("badge-aging", otw)

        hi = self._html("/reports/hatteras")
        self.assertIn('href="/reports/hatteras/seatrout-winterkill-pamlico"', hi)
        self.assertIn("Winterkill Science in Pamlico Sound: Spotted Seatrout After a Hard Winter", hi)
        self.assertLess(hi.find(">Latest local reports<"), hi.find(">Confirmed activity<"))
        self.assertLess(hi.find(">Confirmed activity<"), hi.find('id="otw-heading"'))
        self.assertLess(hi.find('id="otw-heading"'), hi.find(">Official notices<"))

    def test_other_regions_have_no_article_cards_or_routes(self):
        data = whats_biting.load()
        slugs = sorted(
            (r.get("id"), a.get("slug"))
            for r in data.get("regions") or []
            for a in (r.get("articles") or [])
        )
        self.assertEqual(
            slugs,
            [
                ("crystal-coast", "when-the-sound-turns-cold"),
                ("hatteras", "seatrout-winterkill-pamlico"),
            ],
        )
        for path in ("/reports/falls-lake", "/reports/jordan-lake", "/reports/neuse-river", "/reports"):
            html = re.sub(r"<style>.*?</style>", "", self._html(path), flags=re.S)
            with self.subTest(path=path):
                self.assertNotIn("otw-card", html)
                self.assertNotIn('id="otw-heading"', html)
                self.assertNotIn("when-the-sound-turns-cold", html)
                self.assertNotIn("seatrout-winterkill-pamlico", html)

    def test_articles_not_in_sitemap_robots_or_public_nav(self):
        for path in ("/sitemap.xml", "/robots.txt", "/", "/catch-wall", "/wind", "/radar"):
            status, body, _ = self._req(path)
            text = body.decode("utf-8", "replace")
            with self.subTest(path=path):
                self.assertEqual(status, 200, path)
                self.assertNotIn("when-the-sound-turns-cold", text)
                self.assertNotIn("seatrout-winterkill-pamlico", text)
        status, preview, _ = self._ok("/preview")
        self.assertEqual(status, 200)
        self.assertNotIn(b"when-the-sound-turns-cold", preview)
        self.assertNotIn(b"seatrout-winterkill-pamlico", preview)

    def test_official_source_links_present(self):
        html = self._html(self.CC) + self._html(self.HI)
        urls = [
            "https://deq.nc.gov/report-my-fish",
            "https://www.deq.nc.gov/about/divisions/marine-fisheries/public-information-and-education/cold-stun-facts",
            "https://www.deq.nc.gov/about/divisions/marine-fisheries/news-media/insight-newsletter/february-2019/how-state-manages-spotted-seatrout-event-cold-stun",
            "https://ncseagrant.ncsu.edu/hooklinescience/when-do-spotted-seatrout-succumb-to-winterkill/",
            "https://ncseagrant.ncsu.edu/hooklinescience/how-does-winter-weather-affect-spotted-seatrout/",
            "https://www.deq.nc.gov/marine-fisheries/fisheries-management/spotted-seatrout/spotted-seatrout-fmp-update-2026/open",
            "https://www.deq.nc.gov/marine-fisheries/fisheries-management-proclamations/2026/spotted-seatrout-commercial-and-recreational-coastal-and-joint-fishing-waters-including-atlantic/open",
            "https://www.deq.nc.gov/about/divisions/marine-fisheries/rules-proclamations-and-size-and-bag-limits/recreational-size-and-bag-limits",
            "https://www.deq.nc.gov/about/divisions/marine-fisheries/rules-proclamations-and-size-and-bag-limits/fisheries-management-proclamations",
            "https://www.deq.nc.gov/printable-recreational-guide/open",
        ]
        for url in urls:
            with self.subTest(url=url):
                self.assertIn(url, html)

    def test_articles_do_not_name_excluded_publications(self):
        html = (self._article_body(self.CC) + self._article_body(self.HI)).lower()
        for bad in (
            "fisherman's post",
            "fisherman’s post",
            "fishermanspost",
            "carolina sportsman",
            "coastal angler",
            "outerbankssurffishing",
            "island free press",
        ):
            self.assertNotIn(bad, html)


if __name__ == "__main__":
    unittest.main()
