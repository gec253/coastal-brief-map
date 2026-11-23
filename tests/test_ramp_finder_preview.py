"""Ramp Finder private preview — gate, headers, data integrity (Ed t415u–t422u)."""
from __future__ import annotations

import json
import os
import re
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path

import ramp_finder

ROOT = Path(__file__).resolve().parents[1]
KEY = "a" * 32
PROD = "e2e427a"
POLISH_BASE = "a03bf4c"

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
            "/preview/ramps/map", "/preview/ramps/map.js", "/preview/ramps/map.json",
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
                     "/preview/ramps/parks-jordan-seaforth",
                     "/preview/ramps/map"):
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
        # t440u: brief.py is refined on brief-refine-1123; other public pages stay locked.
        # t449u: conditions.py and freshwater.py carry the approved duplicate-alert safety fix
        # (c610f2f); they are pinned to that commit instead. Every other public page stays on PROD.
        t449u = {"conditions.py": "c610f2f", "freshwater.py": "c610f2f"}
        for rel in PROTECTED_PUBLIC_PATHS:
            if rel in ("brief.py", "brief.css"):
                continue
            proc = subprocess.run(
                ["git", "diff", "--name-only", t449u.get(rel, PROD), "--", rel],
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


class InventoryUnchangedFromDeploy(unittest.TestCase):
    """Verified facts stay at a03bf4c except official coordinates added in t422u.

    The only allowed inventory change is official coordinates (and the
    directions fields derived from them) for ramps where an official source
    published coordinates for that specific ramp. Counts, restrictions, fee
    conflicts, scheduled closures, sources, and all other record fields must
    match a03bf4c.
    """

    # Coordinate-related fields only, on this one record:
    # local-atlantic-beach-west-bogue-sound, from the official Carteret County
    # Boat_access feature service (retrieved Nov 22, 2026).
    ALLOWED_COORDINATE_RECORD = "local-atlantic-beach-west-bogue-sound"
    ALLOWED_TOP_FIELDS = frozenset({"coordinates_source", "directions"})
    ALLOWED_DIRECTIONS_FIELDS = frozenset({
        "mode", "latitude", "longitude", "apple_url", "google_url", "caveat",
    })
    DIGEST_AFTER_COORDINATE_UPDATE = (
        "bc484d966b24131ab101f289345d81bf775ee03234c0a474d9752a5cbcb699b5"
    )
    DIGEST_AFTER_NOTICE_UPDATE = (
        "8bccf90797ec5c7593da6b009dd93928bc8acf41ad4e63db8d3d47b4406a877c"
    )
    ALLOWED_NOTICE_RECORDS = frozenset({
        "parks-jordan-seaforth",
        "parks-jordan-vista-point-sailboat",
        "parks-jordan-ebenezer",
        "parks-jordan-new-hope",
        "parks-falls-holly-point-campers",
    })
    ALLOWED_META_KEYS = frozenset({"jordan_lake_official_notice", "recheck_before_release"})
    DIGEST_AT_A03BF4C = (
        "e93754a3cfdd705701e62728f559e26f805b3d40be22aa0601f666febaecca26"
    )

    def test_inventory_facts_unchanged_except_documented_official_coordinates(self):
        import json
        import subprocess

        current = (ROOT / "preview" / "ramp-finder" / "inventory.json").read_bytes()
        baseline = subprocess.check_output(
            ["git", "show", f"{POLISH_BASE}:preview/ramp-finder/inventory.json"],
            cwd=ROOT,
        )
        data = json.loads(current)
        base = json.loads(baseline)
        self.assertEqual(data["counts"], base["counts"])
        self.assertEqual(len(data["records"]), 55)
        self.assertEqual([r["id"] for r in data["records"]], [r["id"] for r in base["records"]])
        self.assertNotIn("parkers", " ".join(r["id"] for r in data["records"]))
        meta_diffs = []
        for key in sorted(set(data["meta"]) | set(base["meta"])):
            if data["meta"].get(key) == base["meta"].get(key):
                continue
            if key not in self.ALLOWED_META_KEYS:
                meta_diffs.append(key)
        self.assertEqual(meta_diffs, [], msg=meta_diffs)
        self.assertIn("jordan_lake_official_notice", data["meta"])
        notice = data["meta"]["jordan_lake_official_notice"]
        self.assertEqual(notice["text"], ramp_finder.JORDAN_LOW_WATER_VISITOR_TEXT)
        self.assertIn("Parkers Creek", notice["text"])
        self.assertIn("no ramp record or coordinates were added", notice["internal_notes"])
        self.assertIn("Parkers Creek is not in this inventory", notice["internal_notes"])
        self.assertIn("Vista Point & Parkers Creek boat ramps closed", notice["official_banner_quote"])

        diffs = []
        for rec, old in zip(data["records"], base["records"]):
            if rec == old:
                continue
            if rec["id"] == self.ALLOWED_COORDINATE_RECORD:
                pass
            elif rec["id"] in self.ALLOWED_NOTICE_RECORDS:
                for key in sorted(set(rec) | set(old)):
                    if rec.get(key) == old.get(key):
                        continue
                    if key != "notices":
                        diffs.append((rec["id"], f"disallowed field changed: {key}"))
                continue
            else:
                diffs.append((rec["id"], "unexpected record changed"))
                continue
            if rec["id"] != self.ALLOWED_COORDINATE_RECORD:
                continue
            for key in sorted(set(rec) | set(old)):
                if rec.get(key) == old.get(key):
                    continue
                if key not in self.ALLOWED_TOP_FIELDS:
                    diffs.append((rec["id"], f"disallowed field changed: {key}"))
                    continue
                if key == "directions":
                    for dkey in sorted(set(rec[key]) | set(old[key])):
                        if rec[key].get(dkey) == old[key].get(dkey):
                            continue
                        if dkey not in self.ALLOWED_DIRECTIONS_FIELDS:
                            diffs.append((rec["id"], f"disallowed directions field changed: {dkey}"))
        self.assertEqual(diffs, [], msg=diffs)

        wb = ramp_finder.by_id(self.ALLOWED_COORDINATE_RECORD, data)
        self.assertEqual(wb["directions"]["mode"], "coordinates")
        self.assertEqual(wb["directions"]["latitude"], 34.70275096)
        self.assertEqual(wb["directions"]["longitude"], -76.73657852)
        self.assertIn("arcgisweb.carteretcountync.gov", wb["coordinates_source"])
        self.assertIn("Nov 22, 2026", wb["coordinates_source"])

        self.assertEqual(ramp_finder.inventory_facts_digest(base), self.DIGEST_AT_A03BF4C)
        self.assertEqual(ramp_finder.inventory_facts_digest(data), self.DIGEST_AFTER_NOTICE_UPDATE)
        self.assertEqual(data["counts"]["total"]["total"], 55)
        self.assertEqual(data["counts"]["total"]["general"], 48)
        self.assertEqual(data["counts"]["total"]["limited"], 3)
        self.assertEqual(data["counts"]["total"]["needs_review"], 4)


class PresentationPolish(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = ramp_finder.load_data()

    def _visible(self, html: str) -> str:
        import re
        html = re.sub(r"<style>.*?</style>", "", html, flags=re.S)
        html = re.sub(
            r'<details class="source-details">.*?</details>',
            "",
            html,
            flags=re.S,
        )
        return html

    def test_viewport_and_safe_area_css(self):
        rec = ramp_finder.by_id("local-newbern-lawson-creek-2", self.data)
        html = ramp_finder.render_detail(self.data, rec)
        self.assertIn("viewport-fit=cover", html)
        css = ramp_finder.css_bytes().decode()
        self.assertIn("env(safe-area-inset-top", css)
        self.assertIn("--rf-safe-top", css)
        self.assertIn("env(safe-area-inset-bottom", css)
        list_html = ramp_finder.render_list(self.data, ramp_finder.parse_filters({}))
        self.assertIn("viewport-fit=cover", list_html)

    def test_source_details_is_native_and_accessible(self):
        rec = ramp_finder.by_id("local-newbern-lawson-creek-2", self.data)
        html = ramp_finder.render_detail(self.data, rec)
        self.assertIn('<details class="source-details">', html)
        self.assertIn("<summary>Source Details</summary>", html)
        css = ramp_finder.css_bytes().decode()
        self.assertIn(".source-details > summary{", css)
        self.assertIn("min-height:var(--touch)", css)

    def test_lawson_creek_general_info_is_summarized(self):
        rec = ramp_finder.by_id("local-newbern-lawson-creek-2", self.data)
        html = ramp_finder.render_detail(self.data, rec)
        visible = self._visible(html)
        self.assertIn("one of two city boat ramps at Lawson Creek Park", visible)
        self.assertNotIn("CMS image query string", visible)
        self.assertNotIn("t=202606010939380", visible)
        self.assertIn("CMS image query string", html)
        self.assertIn("t=202606010939380", html)
        self.assertIn("1309 Country Club Road", visible)
        # original research note remains in Source Details
        self.assertIn("Date Printed 5/6/2025", html)

    def test_disclaimer_once_in_visible_detail(self):
        rec = ramp_finder.by_id("local-newbern-lawson-creek-2", self.data)
        visible = self._visible(ramp_finder.render_detail(self.data, rec))
        self.assertEqual(visible.count("not a live open/closed board"), 1)
        self.assertNotIn("It is not a live open/closed confirmation", visible)
        self.assertNotIn("Open Now", visible)

    def test_notice_categories_remain_distinct_on_pages(self):
        seaforth = ramp_finder.by_id("parks-jordan-seaforth", self.data)
        html = ramp_finder.render_detail(self.data, seaforth)
        visible = self._visible(html)
        self.assertIn('data-notice-category="current_dated_notice"', visible)
        self.assertIn("November 30, 2026", visible)
        self.assertIn("Current dated notice", visible)
        newport = ramp_finder.by_id("baa-newport", self.data)
        nh = self._visible(ramp_finder.render_detail(self.data, newport))
        self.assertIn('data-notice-category="standing_caution"', nh)
        self.assertIn("VERY SHALLOW CANAL", nh)

    def test_not_stated_alias_is_not_shown(self):
        rec = ramp_finder.by_id("usace-jordan-poes-ridge", self.data)
        html = ramp_finder.render_detail(self.data, rec)
        self.assertNotIn("Also recorded as not stated", html)
        self.assertIn("Jordan Dam Road", html)

    def test_masthead_uses_fluid_type_and_keeps_safe_area(self):
        css = ramp_finder.css_bytes().decode()
        self.assertIn("env(safe-area-inset-top", css)
        self.assertIn("--rf-safe-top", css)
        self.assertIn("viewport-fit=cover", ramp_finder.render_list(self.data, ramp_finder.parse_filters({})))
        # Fluid masthead (Ed t419u): clamp, not a rigid px/rem, 44px controls kept.
        brand = css.split(".rf-brand{", 1)[1].split("}", 1)[0]
        self.assertIn("clamp(", brand)
        self.assertIn("vw", brand)
        self.assertIn("white-space:nowrap", brand)
        self.assertIn("italic", brand)
        self.assertIn("var(--ivory)", brand)
        self.assertIn("min-height:var(--touch)", brand)
        self.assertIn("--touch:44px", css)
        self.assertIn("min-height:var(--touch)", css.split(".theme-toggle{", 1)[1].split("}", 1)[0])

    def test_public_files_unchanged_vs_a03bf4c(self):
        import hashlib
        import subprocess
        for rel in ("index.html", "wind.html", "radar.html", "lake.html", "catch-wall.html", "styles.css"):
            current = hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()
            baseline = subprocess.check_output(["git", "show", f"{POLISH_BASE}:{rel}"], cwd=ROOT)
            self.assertEqual(current, hashlib.sha256(baseline).hexdigest(), rel)


class MapPrototype(unittest.TestCase):
    """Private interactive map (Ed t421u, refine t422u)."""

    @classmethod
    def setUpClass(cls):
        cls.data = ramp_finder.load_data()
        cls.payload = ramp_finder.map_payload(cls.data)
        cls.records = cls.payload["records"]

    def test_pin_counts_and_no_invented_coordinates(self):
        counts = ramp_finder.pin_inventory_counts(self.data)
        self.assertEqual(counts["total"], 55)
        self.assertEqual(counts["pin"], 41)
        self.assertEqual(counts["address"], 14)
        self.assertEqual(counts["by_class"]["general"], {"pin": 39, "address": 9})
        self.assertEqual(counts["by_class"]["limited"], {"pin": 1, "address": 2})
        self.assertEqual(counts["by_class"]["needs_review"], {"pin": 1, "address": 3})
        self.assertEqual(len(self.records), 55)
        inv = {r["id"]: r for r in self.data["records"]}
        pin_ids = set()
        for item in self.records:
            rec = inv[item["id"]]
            d = rec["directions"]
            if item["has_pin"]:
                pin_ids.add(item["id"])
                self.assertEqual(d["mode"], "coordinates", item["id"])
                self.assertEqual(item["lat"], d["latitude"])
                self.assertEqual(item["lon"], d["longitude"])
                self.assertIsInstance(item["lat"], float)
                self.assertIsInstance(item["lon"], float)
            else:
                self.assertEqual(d["mode"], "address", item["id"])
                self.assertIsNone(d.get("latitude"), item["id"])
                self.assertIsNone(d.get("longitude"), item["id"])
                self.assertIsNone(item["lat"], item["id"])
                self.assertIsNone(item["lon"], item["id"])
                self.assertTrue(item["address"], item["id"])
        official = {
            r["id"] for r in self.data["records"]
            if r["directions"].get("mode") == "coordinates"
            and r["directions"].get("latitude") is not None
        }
        self.assertEqual(pin_ids, official)
        self.assertEqual(len(pin_ids), 41)

    def test_every_map_pin_is_in_the_inventory(self):
        ids = {r["id"] for r in self.data["records"]}
        for item in self.records:
            self.assertIn(item["id"], ids)
            if item["has_pin"]:
                rec = ramp_finder.by_id(item["id"], self.data)
                self.assertEqual(item["lat"], rec["directions"]["latitude"])
                self.assertEqual(item["lon"], rec["directions"]["longitude"])

    def test_map_default_is_general_and_omits_limited(self):
        html = ramp_finder.render_map(self.data, ramp_finder.parse_filters({}))
        self.assertIn("viewport-fit=cover", html)
        self.assertIn("No map pin — address directions", html)
        self.assertIn("Seaforth", html)
        self.assertIn("November 30, 2026", html)
        self.assertIn("Current dated notice", html)
        self.assertIn("Poe", html)
        self.assertIn("Fee figures differ", html)
        self.assertIn("Newport", html)
        self.assertIn("Standing caution", html)
        self.assertIn("VERY SHALLOW CANAL", html)
        self.assertNotIn("Open Now", html)
        self.assertNotIn("Beaverdam", html)
        self.assertNotIn("West Bogue", html)
        self.assertNotIn("South 10th", html)
        self.assertIn('aria-current="page">Map</a>', html)
        self.assertIn("/vendor/leaflet/leaflet", ramp_finder.MAP_JS_PATH.read_text())
        shown = [r for r in self.data["records"] if r["id"] in html and r["listing_class"] != "general"]
        # Limited / needs-review names should not appear in the default list.
        self.assertFalse(any(r["listing_class"] != "general" and r["display_name"] in html.split("id=\"rf-map-list\"")[-1] for r in self.data["records"]))

    def test_map_filters_reveal_limited_and_needs_review(self):
        html = ramp_finder.render_map(
            self.data, ramp_finder.parse_filters({"limited": ["1"], "needs_review": ["1"]})
        )
        self.assertIn("Beaverdam", html)
        self.assertIn("West Bogue", html)
        self.assertIn("Limited access", html)
        self.assertIn("Needs review", html)
        self.assertIn("No map pin — address directions", html)

    def test_map_payload_has_no_open_now_and_keeps_digest(self):
        blob = json.dumps(self.payload)
        self.assertNotIn("Open Now", blob)
        self.assertEqual(
            ramp_finder.inventory_facts_digest(self.data),
            "8bccf90797ec5c7593da6b009dd93928bc8acf41ad4e63db8d3d47b4406a877c",
        )

    def test_map_assets_and_reserved_height(self):
        css = ramp_finder.css_bytes().decode()
        self.assertIn(".rf-map-stage{", css)
        self.assertIn("min-height:280px", css)
        self.assertIn("58svh", css)
        js = ramp_finder.map_js_bytes().decode()
        self.assertIn("basemap.nationalmap.gov", js)
        self.assertIn("USGSTopo", js)
        self.assertIn("USGSImageryOnly", js)
        self.assertNotIn("tile.openstreetmap.org", js)
        self.assertNotIn("arcgisonline.com", js)
        status, ctype, body = ramp_finder.resolve_request("/preview/ramps/map.js", {})
        self.assertEqual(status, 200)
        self.assertIn("javascript", ctype)
        self.assertEqual(body, ramp_finder.map_js_bytes())
        status, ctype, raw = ramp_finder.resolve_request("/preview/ramps/map.json", {})
        self.assertEqual(status, 200)
        payload = json.loads(raw)
        self.assertEqual(payload["counts"]["pin"], 41)
        self.assertEqual(payload["counts"]["address"], 14)


    def test_map_defaults_to_crystal_coast_and_keeps_all_areas(self):
        status, _, html = ramp_finder.resolve_request("/preview/ramps/map", {})
        self.assertEqual(status, 200)
        self.assertIn("Newport", html)
        self.assertIn("Morehead City", html)
        self.assertNotIn("Seaforth", html)
        self.assertNotIn("Poe", html)
        self.assertIn("region=all", html)
        self.assertIn("All areas", html)
        self.assertIn('id="rf-sheet"', html)
        self.assertIn('aria-label="Close ramp panel"', html)
        filters = ramp_finder.parse_map_filters({})
        self.assertEqual(filters["region"], "crystal-coast")
        self.assertEqual(ramp_finder.parse_map_filters({"region": ["all"]})["region"], "")
        self.assertEqual(ramp_finder.parse_map_filters({"region": ["falls-lake"]})["region"], "falls-lake")
        self.assertEqual(ramp_finder.parse_map_filters({"water": ["Jordan Lake"]})["region"], "jordan-lake")
        all_html = ramp_finder.render_map(
            self.data, ramp_finder.parse_map_filters({"region": ["all"]})
        )
        self.assertIn("Seaforth", all_html)
        self.assertIn("No map pin — address directions", all_html)

    def test_west_bogue_uses_official_carteret_coordinates(self):
        rec = next(r for r in self.records if r["id"] == "local-atlantic-beach-west-bogue-sound")
        self.assertTrue(rec["has_pin"])
        self.assertEqual(rec["lat"], 34.70275096)
        self.assertEqual(rec["lon"], -76.73657852)

    def test_mobile_sheet_styles_and_leaflet_idle_load(self):
        css = ramp_finder.css_bytes().decode()
        self.assertIn(".rf-sheet-panel{", css)
        self.assertIn("safe-area-inset-bottom", css)
        js = ramp_finder.map_js_bytes().decode()
        self.assertIn("requestIdleCallback", js)
        self.assertIn("rf-sheet", js)
        self.assertIn("Escape", js)
        self.assertIn("maxZoom: 13", js)
        self.assertIn("USGSTopo", js)


class StageBPresentation(unittest.TestCase):
    """Visitor-facing list/detail polish. No inventory fact or coordinate changes."""

    @classmethod
    def setUpClass(cls):
        cls.data = ramp_finder.load_data()

    def test_all_detail_leads_avoid_duplicated_waterbody_names(self):
        self.assertEqual(len(self.data["records"]), 55)
        for rec in self.data["records"]:
            lead = ramp_finder.waterbody_lead(rec)
            html = ramp_finder.render_detail(self.data, rec, public=True)
            self.assertIn(f'<p class="lead">{lead}</p>', html)
            if " — " in lead:
                left, right = lead.split(" — ", 1)
                left_n = re.sub(r"[\s.]+", " ", left).strip().casefold()
                right_n = re.sub(r"[\s.]+", " ", right).strip().casefold()
                self.assertNotEqual(left_n, right_n, rec["id"])
                self.assertFalse(right_n.startswith(left_n), rec["id"])

    def test_seaforth_and_goldsboro_leads_are_single_labels(self):
        sea = ramp_finder.by_id("parks-jordan-seaforth", self.data)
        self.assertEqual(ramp_finder.waterbody_lead(sea), "B. Everett Jordan Lake")
        html = ramp_finder.render_detail(self.data, sea, public=True)
        self.assertIn("<p class=\"lead\">B. Everett Jordan Lake</p>", html)
        self.assertNotIn("B. Everett Jordan Lake — B. Everett Jordan Lake", html)
        golds = ramp_finder.by_id("baa-goldsboro", self.data)
        self.assertEqual(ramp_finder.waterbody_lead(golds), "Neuse River")
        # Distinct official name and common name stay side by side.
        farr = ramp_finder.by_id("baa-farrington-point", self.data)
        self.assertEqual(ramp_finder.waterbody_lead(farr), "Lake Jordan — B. Everett Jordan Lake")

    def test_public_pages_do_not_say_preview_or_show_bare_not_stated_sections(self):
        for rec in self.data["records"]:
            html = ramp_finder.render_detail(self.data, rec, public=True)
            self.assertNotRegex(html, r"(?i)this preview")
            self.assertNotRegex(html, r"(?i)<h2>Hours</h2><p>not stated</p>")
            self.assertNotRegex(html, r"(?i)<h2>Fees</h2><p>not stated</p>")
        poes = ramp_finder.render_detail(self.data, ramp_finder.by_id("usace-jordan-poes-ridge", self.data), public=True)
        self.assertIn("This page shows both figures and does not choose one.", poes)
        eben = ramp_finder.render_detail(self.data, ramp_finder.by_id("parks-jordan-ebenezer", self.data), public=True)
        self.assertIn("this page does not choose one", eben)
        west = ramp_finder.render_detail(
            self.data, ramp_finder.by_id("local-atlantic-beach-west-bogue-sound", self.data), public=True
        )
        self.assertIn("<h2>Hours</h2>", west)
        self.assertIn("<h2>Fees</h2>", west)
        self.assertIn(ramp_finder.NOT_LISTED_OFFICIAL, west)

    def test_inventory_fields_unchanged_from_bc68cd6(self):
        """Presentation-only: every inventory field is identical to bc68cd6.

        The facts digest stays
        8bccf90797ec5c7593da6b009dd93928bc8acf41ad4e63db8d3d47b4406a877c
        because official names, notices, coordinates, and counts were not edited.
        """
        import json
        import subprocess
        raw = subprocess.check_output(
            ["git", "show", "bc68cd6:preview/ramp-finder/inventory.json"],
            cwd=ROOT,
        )
        base = json.loads(raw)
        data = ramp_finder.load_data()
        self.assertEqual(data["counts"], base["counts"])
        self.assertEqual(data["meta"], base["meta"])
        self.assertEqual(len(data["records"]), len(base["records"]))
        diffs = []
        for rec, old in zip(data["records"], base["records"]):
            if rec == old:
                continue
            changed = [k for k in sorted(set(rec) | set(old)) if rec.get(k) != old.get(k)]
            diffs.append((rec.get("id"), changed))
        self.assertEqual(diffs, [], msg=diffs)
        self.assertEqual(data, base)
        self.assertEqual(
            ramp_finder.inventory_facts_digest(data),
            "8bccf90797ec5c7593da6b009dd93928bc8acf41ad4e63db8d3d47b4406a877c",
        )

    def test_list_and_detail_title_case_keep_official_name_in_source_details(self):
        html = ramp_finder.render_list(
            self.data, ramp_finder.parse_filters({"region": ["crystal-coast"]}), public=True
        )
        self.assertIn("Pamlico Sound", html)
        self.assertNotIn("PAMLICO SOUND —", html)
        rec = ramp_finder.by_id("baa-farrington-point", self.data)
        self.assertEqual(rec["body_of_water"], "LAKE JORDAN")
        detail = ramp_finder.render_detail(self.data, rec, public=True)
        self.assertIn('<p class="lead">Lake Jordan — B. Everett Jordan Lake</p>', detail)
        self.assertIn("Official waterbody name as recorded", detail)
        self.assertIn("LAKE JORDAN", detail)

    def test_research_asides_move_to_source_details_and_restrictions_remain(self):
        hwy = ramp_finder.by_id("parks-falls-highway-50", self.data)
        html = ramp_finder.render_detail(self.data, hwy, public=True)
        lead = '<p class="lead">Falls Lake (main reservoir).</p>'
        self.assertIn(lead, html)
        body, _, details = html.partition('<details class="source-details">')
        self.assertNotIn("Never present as Jordan Lake", body)
        self.assertIn("Never present as Jordan Lake", details)
        beaver = ramp_finder.render_detail(
            self.data, ramp_finder.by_id("parks-falls-beaverdam", self.data), public=True
        )
        body, _, details = beaver.partition('<details class="source-details">')
        self.assertIn("Beaverdam Lake (a separated section of Falls Lake)", body)
        self.assertNotIn("Beaverdam Lake is separated from the main area", body)
        self.assertIn("gas-motored boats are prohibited on Beaverdam Lake", body)
        self.assertIn("Beaverdam Lake is separated from the main area", details)
        west = ramp_finder.render_detail(
            self.data, ramp_finder.by_id("local-atlantic-beach-west-bogue-sound", self.data), public=True
        )
        body, _, details = west.partition('<details class="source-details">')
        self.assertIn('<p class="lead">Bogue Sound</p>', west)
        self.assertNotIn("name on the official town list", body)
        self.assertIn("name on the official town list", details)
        union = ramp_finder.render_detail(
            self.data, ramp_finder.by_id("local-newbern-union-point", self.data), public=True
        )
        body, _, details = union.partition('<details class="source-details">')
        self.assertIn("Neuse River at New Bern (brackish).", body)
        self.assertNotIn("DCM PRK_FEE", body)
        self.assertIn("DCM PRK_FEE", details)
        self.assertIn(ramp_finder.NOT_LISTED_OFFICIAL, union)
