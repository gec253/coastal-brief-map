"""Ramp Finder private preview — gate, headers, data integrity (Ed t415u)."""
from __future__ import annotations

import json
import os
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path

import ramp_finder

ROOT = Path(__file__).resolve().parents[1]
KEY = "a" * 32
PROD = "e2e427a"

PROTECTED_PUBLIC_PATHS = (
    "index.html",
    "brief.py",
    "brief.html",
    "wind.html",
    "radar.html",
    "catch-wall.html",
    "catch_wall.py",
    "conditions.py",
    "freshwater.py",
    "lake.html",
)


class DataIntegrity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = ramp_finder.load_data()
        cls.records = cls.data["records"]
        cls.counts = cls.data["counts"]

    def test_reconciled_counts_are_mutually_exclusive_and_sum(self):
        totals = self.counts["total"]
        self.assertEqual(totals["general"] + totals["limited"] + totals["needs_review"], totals["total"])
        self.assertEqual(totals["total"], 55)
        self.assertEqual(totals["general"], 48)
        self.assertEqual(totals["limited"], 3)
        self.assertEqual(totals["needs_review"], 4)
        area_sum = 0
        for area, row in self.counts["by_area"].items():
            self.assertEqual(row["general"] + row["limited"] + row["needs_review"], row["total"], area)
            area_sum += row["total"]
        self.assertEqual(area_sum, totals["total"])
        self.assertEqual(len(self.records), totals["total"])
        classes = {r["listing_class"] for r in self.records}
        self.assertEqual(classes, {"general", "limited", "needs_review"})
        for rec in self.records:
            self.assertIn(rec["listing_class"], ("general", "limited", "needs_review"))

    def test_every_record_has_coordinates_or_address_for_directions(self):
        for rec in self.records:
            d = rec["directions"]
            has_coords = d.get("latitude") is not None and d.get("longitude") is not None
            has_addr = bool(d.get("address"))
            self.assertTrue(has_coords or has_addr, rec["id"])
            self.assertTrue(d.get("apple_url") and d.get("google_url"), rec["id"])
            if (rec.get("coordinates_source") or "").startswith("not stated"):
                self.assertEqual(d["mode"], "address", rec["id"])
                self.assertIsNone(d.get("latitude"), rec["id"])
                self.assertIsNone(d.get("longitude"), rec["id"])

    def test_default_view_is_general_only(self):
        g, l, r = ramp_finder.visible_sets(self.data, ramp_finder.parse_filters({}))
        self.assertEqual(len(g), 48)
        self.assertEqual(l, [])
        self.assertEqual(r, [])
        # optional filters reveal limited / needs-review
        g, l, r = ramp_finder.visible_sets(self.data, ramp_finder.parse_filters({"limited": ["1"], "needs_review": ["1"]}))
        self.assertEqual(len(l), 3)
        self.assertEqual(len(r), 4)

    def test_poes_ridge_fee_conflict_shows_both_figures_and_sources(self):
        rec = ramp_finder.by_id("usace-jordan-poes-ridge", self.data)
        self.assertIsNotNone(rec)
        fees = rec["fees"]
        self.assertTrue(fees["conflict"])
        amounts = " ".join(e["amount"] for e in fees["entries"])
        self.assertIn("$5", amounts)
        self.assertIn("$7", amounts)
        urls = {e["source_url"] for e in fees["entries"]}
        self.assertIn("https://www.saw.usace.army.mil/Locations/District-Lakes-and-Dams/B-Everett-Jordan/Recreation/", urls)
        self.assertIn("https://www.saw.usace.army.mil/Locations/District-Lakes-and-Dams/B-Everett-Jordan/Recreation/User-Fees/", urls)
        html = ramp_finder.render_detail(self.data, rec)
        self.assertIn("$5.00", html)
        self.assertIn("$7.00", html)
        self.assertIn('data-fee-conflict="true"', html)
        self.assertIn("Recreation/User-Fees/", html)
        self.assertIn("/Locations/District-Lakes-and-Dams/B-Everett-Jordan/Recreation/", html)
        self.assertNotIn("Open Now", html)

    def test_notice_categories_are_distinct_and_never_open_now(self):
        cats = set()
        for rec in self.records:
            for n in rec.get("notices") or []:
                cats.add(n["category"])
                self.assertIn(n["category"], ("current_dated_notice", "standing_caution", "general_information"))
                self.assertNotIn("Open Now", n.get("text") or "")
        self.assertEqual(cats, {"current_dated_notice", "standing_caution", "general_information"})
        seaforth = ramp_finder.by_id("parks-jordan-seaforth", self.data)
        html = ramp_finder.render_detail(self.data, seaforth)
        self.assertIn("Current dated notice", html)
        self.assertIn("November 30, 2026", html)
        self.assertIn('data-notice-category="current_dated_notice"', html)
        self.assertNotIn("Open Now", html)
        newport = ramp_finder.by_id("baa-newport", self.data)
        html = ramp_finder.render_list(self.data, ramp_finder.parse_filters({}))
        # default list includes Newport standing caution, excludes limited
        self.assertIn("Newport", html)
        self.assertIn("Standing caution", html)
        self.assertIn("Seaforth", html)
        self.assertIn("Current dated notice", html)
        self.assertNotIn("Open Now", html)
        self.assertNotIn("South 10th", html)
        self.assertNotIn("Beaverdam", html)
        self.assertNotIn("West Bogue", html)

    def test_haywood_landing_is_crystal_coast_jones_county(self):
        rec = ramp_finder.by_id("baa-haywood-landing", self.data)
        self.assertEqual(rec["area"], "crystal-coast")
        self.assertEqual(rec["county"], "Jones")
        html = ramp_finder.render_detail(self.data, rec)
        self.assertIn("Jones County", html)
        self.assertIn("Crystal Coast", html)
        self.assertIn("White Oak", html)

    def test_ebenezer_hours_conflict_shows_both_sources(self):
        rec = ramp_finder.by_id("parks-jordan-ebenezer", self.data)
        html = ramp_finder.render_detail(self.data, rec)
        self.assertIn('data-hours-conflict="true"', html)
        self.assertIn("24-hour boat ramp", html)
        self.assertIn("gates", html.lower())
        self.assertIn("ebenezer-church-access", html)
        self.assertIn("jordan-lake-state-recreation-area", html)

    def test_lawson_creek_and_glenburnie_from_official_city_map(self):
        one = ramp_finder.by_id("local-newbern-lawson-creek-1", self.data)
        two = ramp_finder.by_id("local-newbern-lawson-creek-2", self.data)
        glen = ramp_finder.by_id("local-newbern-glenburnie", self.data)
        self.assertEqual(one["listing_class"], "general")
        self.assertEqual(two["listing_class"], "general")
        self.assertEqual(glen["listing_class"], "general")
        self.assertEqual(one["directions"]["mode"], "address")
        self.assertIn("1309 Country Club Road", one["directions"]["address"])
        self.assertIn("340 Glenburnie Drive", glen["directions"]["address"])
        self.assertIsNone(one["directions"]["latitude"])
        finding = self.data["meta"]["lawson_creek_finding"]
        self.assertEqual(finding["map_date_printed"], "2025-05-06")
        self.assertIn("newbernnc.gov/departments/boat_ramps.php", finding["page_url"])


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
            "/preview/ramps", "/preview/ramps/", "/preview/ramps.css",
            "/preview/ramps.json", "/preview/ramps/usace-jordan-poes-ridge",
        ]
        for path in paths:
            status, _, _ = self._req(path)
            self.assertEqual(status, 404, path)
            status, _, _ = self._req(path, env={"PREVIEW_KEY": KEY})
            self.assertEqual(status, 404, path + " key set, no cookie")

    def test_cookie_unlocks_noindex_pages(self):
        for path in ("/preview/ramps", "/preview/ramps/",
                     "/preview/ramps/usace-jordan-poes-ridge",
                     "/preview/ramps/parks-jordan-ebenezer",
                     "/preview/ramps/parks-jordan-seaforth"):
            status, body, hdrs = self._ok(path)
            self.assertEqual(status, 200, path)
            self.assertIn("noindex", hdrs.get("x-robots-tag", ""))
            self.assertIn(b"noindex, nofollow", body)
            self.assertIn("no-store", hdrs.get("cache-control", ""))
            self.assertIn("Cookie", hdrs.get("vary", ""))
            self.assertNotIn(b"Open Now", body)
        status, body, hdrs = self._ok("/preview/ramps.css")
        self.assertEqual(status, 200)
        self.assertIn("text/css", hdrs.get("content-type", ""))
        self.assertIn("noindex", hdrs.get("x-robots-tag", ""))

    def test_unknown_ramp_is_404_even_with_cookie(self):
        status, _, _ = self._ok("/preview/ramps/not-a-real-ramp")
        self.assertEqual(status, 404)

    def test_not_in_sitemap_or_robots(self):
        status, body, _ = self._req("/sitemap.xml")
        self.assertEqual(status, 200)
        text = body.decode()
        self.assertNotIn("/preview/ramps", text)
        self.assertNotIn("Ramp Finder", text)
        status, robots, _ = self._req("/robots.txt")
        self.assertEqual(status, 200)
        self.assertNotIn("/preview/ramps", robots.decode())

    def test_not_in_public_nav(self):
        for path in ("/", "/catch-wall", "/wind", "/radar"):
            status, body, _ = self._req(path)
            self.assertEqual(status, 200, path)
            text = body.decode("utf-8", "replace")
            self.assertNotIn("/preview/ramps", text)
            self.assertNotIn("Ramp Finder", text)

    def test_preview_hub_lists_the_feature_when_unlocked(self):
        status, body, _ = self._ok("/preview")
        self.assertEqual(status, 200)
        self.assertIn(b"/preview/ramps", body)
        self.assertIn(b"Ramp Finder", body)
        status, _, _ = self._req("/preview")
        self.assertEqual(status, 404)

    def test_public_pages_not_changed_on_disk(self):
        import subprocess
        for rel in PROTECTED_PUBLIC_PATHS:
            proc = subprocess.run(
                ["git", "diff", "--name-only", PROD, "--", rel],
                cwd=ROOT, capture_output=True, text=True, check=True,
            )
            self.assertEqual(proc.stdout.strip(), "", f"{rel} changed from {PROD}")

    def test_accessible_touch_targets_declared(self):
        css = ramp_finder.css_bytes().decode()
        self.assertIn("--touch:44px", css)
        self.assertIn("min-height:var(--touch)", css)


class PublicPagesUnchanged(unittest.TestCase):
    def test_public_static_files_match_e2e427a(self):
        import hashlib
        import subprocess
        for rel in ("index.html", "wind.html", "radar.html", "lake.html", "catch-wall.html"):
            current = hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()
            baseline = subprocess.check_output(["git", "show", f"{PROD}:{rel}"], cwd=ROOT)
            self.assertEqual(current, hashlib.sha256(baseline).hexdigest(), rel)
