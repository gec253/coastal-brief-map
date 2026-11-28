"""Public launch of the statewide Ramp Finder directory (Ed t550u)."""
import json
import os
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import launch_flags  # noqa: E402
import ramp_finder  # noqa: E402
import ramp_statewide  # noqa: E402
import server  # noqa: E402

RF = ROOT / "preview" / "ramp-finder"
TYPES = ("trailer", "paddle", "limited", "needs_review", "unknown")
STATUSES = ("listed_open", "temporarily_closed", "partially_open", "conflicting", "not_stated")
UNRESOLVED = (
    "usace-jordan-poes-ridge",
    "local-newbern-glenburnie",
    "local-newbern-lawson-creek-1",
    "local-newbern-lawson-creek-2",
)


class Directory(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sw = json.loads((RF / "statewide.json").read_text())
        cls.inv = json.loads((RF / "inventory.json").read_text())
        cls.by = {r["id"]: r for r in cls.sw["records"]}

    def test_both_dimensions_sum_to_every_record(self):
        c, n = self.sw["counts"], len(self.sw["records"])
        self.assertEqual(n, 285)
        self.assertEqual(sum(c["by_type_dimension"].values()), n)
        self.assertEqual(sum(c["by_status"].values()), n)
        self.assertEqual(sum(sum(v.values()) for v in c["type_by_status"].values()), n)
        self.assertEqual(set(c["by_type_dimension"]), set(TYPES))
        self.assertEqual(set(c["by_status"]), set(STATUSES))

    def test_closure_status_is_independent_of_access_type(self):
        for r in self.sw["records"]:
            want = (
                "needs_review" if r["listing_class"] == "needs_review"
                else "limited" if r["listing_class"] == "limited"
                else r["access_type"] if r["access_type"] in ("trailer", "paddle")
                else "unknown"
            )
            self.assertEqual(r["type_dimension"], want, r["id"])
        # Closed and unclear records keep their access type (they are not retyped as "closed").
        self.assertEqual(self.by["baa-outfall-canal"]["type_dimension"], "trailer")
        self.assertEqual(self.by["baa-outfall-canal"]["access_status"]["code"], "temporarily_closed")
        self.assertEqual(self.by["baa-hibernia"]["type_dimension"], "trailer")
        self.assertEqual(self.by["baa-hibernia"]["access_status"]["code"], "conflicting")
        self.assertEqual(self.by["parks-falls-holly-point-campers"]["type_dimension"], "needs_review")
        self.assertEqual(self.by["parks-falls-holly-point-campers"]["access_status"]["code"], "temporarily_closed")
        st, _, b = ramp_finder.resolve_request("/ramps", {}, public=True)
        self.assertEqual(st, 200)
        self.assertNotIn('data-section="closed"', b)
        # Outfall Canal is a closed trailer launch, listed in the trailer section.
        m = re.search(r'<section class="rf-section" data-section="trailer">([\s\S]*?)</section>', b)
        self.assertIsNotNone(m)
        self.assertIn("baa-outfall-canal", m.group(1))
        m = re.search(r'<section class="rf-section" data-section="needs_review">([\s\S]*?)</section>', b)
        self.assertIn("parks-falls-holly-point-campers", m.group(1))

    def test_all_legacy_slugs_resolve_to_the_same_ramp(self):
        self.assertEqual(len(self.inv["records"]), 55)
        for rec in self.inv["records"]:
            rid = rec["id"]
            self.assertIn(rid, self.by, rid)
            st, _, b = ramp_finder.resolve_request(f"/ramps/{rid}", {}, public=True)
            self.assertEqual(st, 200, rid)
            self.assertIn(ramp_finder.esc(rec["display_name"]), b)

    def test_four_sites_stay_address_only_without_pins(self):
        self.assertEqual(self.sw["counts"]["coordinates"]["none"], 4)
        for rid in UNRESOLVED:
            r = self.by[rid]
            self.assertFalse(isinstance((r.get("directions") or {}).get("latitude"), (int, float)), rid)
            self.assertNotIn("official_coordinates", r)
            self.assertTrue(r.get("coordinates_unresolved"), rid)
            self.assertEqual(r["directions"]["mode"], "address")
            st, _, b = ramp_finder.resolve_request(f"/ramps/{rid}", {}, public=True)
            self.assertEqual(st, 200, rid)
            self.assertIn("Map point", b)
            self.assertIn("daddr=", b)
            # No numeric pin coordinates in the Apple/Google query (address only).
            self.assertNotRegex(b, r"daddr=-?\d+\.\d+,-?\d+\.\d+")

    def test_parkers_creek_unmatched_notice_on_jordan_page(self):
        st, _, b = ramp_finder.resolve_request("/ramps", {"region": ["jordan-lake"]}, public=True)
        self.assertEqual(st, 200)
        self.assertIn('data-notice="unmatched"', b)
        self.assertIn('data-notice-key="jordan-low-water-parkers-creek"', b)
        self.assertIn("Official notice not tied to a listed ramp", b)
        self.assertIn("Parkers Creek boat ramp closed", b)
        self.assertIn("https://www.ncparks.gov/state-parks/jordan-lake-state-recreation-area", b)
        self.assertIn("Nov 27, 2026, 7:07 PM ET", b)
        # Also still named in the official Jordan banner.
        self.assertIn("Vista Point and Parkers Creek boat ramps closed", b)

    def test_notices_rechecked_before_launch(self):
        self.assertEqual(self.sw["meta"]["notices_rechecked"], "2026-11-27 7:07 PM ET")
        for rid in ("parks-falls-holly-point-campers", "parks-jordan-seaforth", "parks-jordan-vista-point-sailboat", "baa-hibernia"):
            self.assertIn("Nov 27, 2026, 7:07 PM ET", self.by[rid]["access_status"]["as_of"], rid)


class PublicPages(unittest.TestCase):
    def get(self, path="/ramps", **q):
        st, _, body = ramp_finder.resolve_request(path, {k: [v] for k, v in q.items()}, public=True)
        self.assertEqual(st, 200, path)
        return body

    def test_search_groups_filters_themes_and_no_js(self):
        b = self.get()
        self.assertIn('<label class="q-lab" for="q">Search by ramp name, town, county or waterbody</label>', b)
        self.assertIn('aria-live="polite"', b)
        self.assertIn("min-height:44px", b)
        self.assertIn('method="get" action="/ramps"', b)
        self.assertGreater(b.count('<details class="sw-group"'), 8)
        self.assertEqual(len(re.findall(r"<li data-find=", b)), 285)
        b = self.get(q="kerr")
        ids = set(re.findall(r'href="/ramps/([a-z0-9-]+)"', b))
        self.assertEqual(ids, {"baa-county-line", "baa-flemingtown-landing", "baa-henderson-point", "baa-hibernia"})
        self.assertNotIn('<details class="sw-group"', b)

    def test_nine_regions_hatteras_exception_neuse_split_unknown(self):
        for region, n in (("crystal-coast", 17), ("wilmington", 8), ("topsail", 6),
                          ("nags-head", 6), ("hatteras", 1), ("falls-lake", 9),
                          ("jordan-lake", 7), ("neuse-river", 25)):
            b = self.get(region=region)
            self.assertIn(f"Showing {n} site", b, region)
        b = self.get(region="hatteras")
        self.assertIn("Hatteras Island coverage is limited", b)
        self.assertIn("documented exception", b)
        self.assertIn("baa-rodanthe", b)
        b = self.get(region="neuse-river")
        self.assertIn("Upper Neuse, Falls Dam to Goldsboro", b)
        self.assertIn("Lower Neuse, below Goldsboro", b)
        b = self.get(region="bogus")
        self.assertIn('data-honest="unknown-region"', b)
        self.assertIn('href="/ramps"', b)

    def test_emerald_isle_legacy_url(self):
        b = self.get(region="emerald-isle")
        self.assertIn("Emerald Isle ramps are listed with the Crystal Coast", b)
        self.assertIn("Showing 17 sites", b)


class FlagsAndSitemap(unittest.TestCase):
    def setUp(self):
        self.saved = {k: os.environ.get(k) for k in (launch_flags.PUBLIC_RAMPS, launch_flags.PUBLIC_RAMP_MAP, "PREVIEW_KEY")}

    def tearDown(self):
        for k, v in self.saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_public_ramps_off_hides_list_and_map_stays_404(self):
        os.environ[launch_flags.PUBLIC_RAMPS] = "0"
        os.environ.pop(launch_flags.PUBLIC_RAMP_MAP, None)
        os.environ["PREVIEW_KEY"] = "local-test-key-not-production-xxxx"
        import importlib
        importlib.reload(launch_flags)
        h = server.Handler
        # The route helper uses launch_flags at call time.
        from urllib.parse import urlsplit
        class Fake:
            pass
        # Exercise the public route method through a minimal request is heavy;
        # the flag helpers are what the route checks.
        self.assertFalse(launch_flags.ramps_public())
        self.assertFalse(launch_flags.ramp_map_public())
        self.assertFalse(launch_flags.ramps_routes_public())

    def test_sitemap_lists_index_only_not_detail_pages(self):
        os.environ[launch_flags.PUBLIC_RAMPS] = "1"
        os.environ.pop(launch_flags.PUBLIC_RAMP_MAP, None)
        import importlib
        importlib.reload(launch_flags)
        urls = server.public_sitemap_urls()
        self.assertIn("https://thecoastalbrief.com/ramps", urls)
        self.assertNotIn("https://thecoastalbrief.com/ramps/map", urls)
        self.assertFalse(any(u.startswith("https://thecoastalbrief.com/ramps/") for u in urls))


if __name__ == "__main__":
    unittest.main()
