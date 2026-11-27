"""Phase 1.1 statewide Ramp Finder refinements (Ed t548u), private preview only."""
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import ramp_finder  # noqa: E402
import ramp_statewide  # noqa: E402

RF = ROOT / "preview" / "ramp-finder"
TYPES = ("trailer", "paddle", "limited", "needs_review", "unknown")
STATUSES = ("listed_open", "temporarily_closed", "partially_open", "conflicting", "not_stated")


class Dimensions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sw = json.loads((RF / "statewide.json").read_text())
        cls.by = {r["id"]: r for r in cls.sw["records"]}

    def test_both_dimensions_total_every_record(self):
        c = self.sw["counts"]
        n = len(self.sw["records"])
        self.assertEqual(sum(c["by_type_dimension"].values()), n)
        self.assertEqual(sum(c["by_status"].values()), n)
        self.assertEqual(sum(sum(v.values()) for v in c["type_by_status"].values()), n)
        self.assertEqual(set(c["by_type_dimension"]), set(TYPES))
        self.assertEqual(set(c["by_status"]), set(STATUSES))

    def test_type_never_comes_from_status(self):
        for r in self.sw["records"]:
            want = ("needs_review" if r["listing_class"] == "needs_review" else "limited" if r["listing_class"] == "limited"
                    else r["access_type"] if r["access_type"] in ("trailer", "paddle") else "unknown")
            self.assertEqual(r["type_dimension"], want, r["id"])
        # closed launches keep their access type
        self.assertEqual(self.by["baa-flemingtown-landing"]["type_dimension"], "trailer")
        self.assertEqual(self.by["parks-falls-holly-point-campers"]["type_dimension"], "needs_review")

    def test_conflicts_stay_conservative(self):
        for rid in ("baa-hibernia", "baa-norwood"):
            self.assertEqual(self.by[rid]["access_status"]["code"], "conflicting")
            self.assertNotIn("open", self.by[rid]["access_status"]["label"].lower().replace("status unclear", ""))

    def test_rechecked_notices_dated(self):
        for rid in ("parks-falls-holly-point-campers", "parks-jordan-seaforth", "parks-jordan-vista-point-sailboat", "baa-hibernia"):
            self.assertIn("Nov 27, 2026, 6:20 PM ET", self.by[rid]["access_status"]["as_of"], rid)
        for rid in ("baa-outfall-canal", "baa-county-line", "baa-norwood"):
            self.assertIn("rechecked 2026-11-27", self.by[rid]["access_status"]["as_of"], rid)
        self.assertIn("no Nov. 30 seasonal close for Seaforth", self.by["parks-jordan-seaforth"]["notices"][-1]["text"])

    def test_official_coordinates_only_from_owner_and_directions_unchanged(self):
        oc = json.loads((RF / "official_coordinates.json").read_text())
        inv = {m["id"]: m for m in json.loads((RF / "inventory.json").read_text())["records"]}
        for rid, c in oc["records"].items():
            r = self.by[rid]
            self.assertEqual((r["official_coordinates"]["lat"], r["official_coordinates"]["lon"]), (c["lat"], c["lon"]))
            self.assertTrue(r["official_coordinates"]["source_url"].startswith("https://www.ncparks.gov/"))
            self.assertEqual(r["directions"], inv[rid]["directions"])  # directions stay by verified address
        missing = [r["id"] for r in self.sw["records"] if not isinstance((r.get("directions") or {}).get("latitude"), (int, float))
                   and not r.get("official_coordinates")]
        self.assertEqual(sorted(missing), sorted(oc["unresolved"]))
        for rid in missing:
            self.assertEqual(self.by[rid]["directions"]["mode"], "address")

    def test_rodanthe_exception_documented(self):
        r = self.by["baa-rodanthe"]
        self.assertEqual(r["area"], "hatteras")
        self.assertIn("Documented geographic exception", r["area_rule"]["rule"])


class Page(unittest.TestCase):
    def get(self, **q):
        st, _, body = ramp_statewide.resolve_request("/preview/ramps-statewide", {k: [v] for k, v in q.items()})
        self.assertEqual(st, 200)
        return body

    def test_statewide_groups_are_collapsible_and_search_has_label(self):
        b = self.get()
        self.assertIn('<label class="q-lab" for="q">Search by ramp name, town, county or waterbody</label>', b)
        self.assertGreater(b.count('<details class="sw-group"'), 8)
        self.assertNotIn('<details class="sw-group" data-area="crystal-coast" open>', b)  # collapsed by default
        self.assertIn('aria-live="polite"', b)
        self.assertIn("min-height:44px", b)
        self.assertEqual(len(re.findall(r"<li data-find=", b)), 285)

    def test_no_js_search_still_works_server_side(self):
        b = self.get(q="kerr")
        ids = set(re.findall(r'href="/preview/ramps-statewide/([a-z0-9-]+)"', b))
        self.assertEqual(ids, {"baa-county-line", "baa-flemingtown-landing", "baa-henderson-point", "baa-hibernia"})
        self.assertNotIn('<details class="sw-group"', b)  # results are not hidden in collapsed groups

    def test_dimension_line_on_page(self):
        b = self.get()
        self.assertIn("263 trailer · 11 paddle / carry-in · 7 limited / restricted · 4 needs review", b)
        self.assertIn("261 open as listed · 6 temporarily closed · 1 partly open · 2 status unclear · 15 unknown / not stated", b)

    def test_status_filter(self):
        b = self.get(status="conflicting")
        self.assertEqual(set(re.findall(r'href="/preview/ramps-statewide/([a-z0-9-]+)"', b)), {"baa-hibernia", "baa-norwood"})

    def test_detail_shows_official_point_or_unresolved(self):
        _, _, b = ramp_statewide.resolve_request("/preview/ramps-statewide/parks-jordan-seaforth", {})
        self.assertIn("Official location point", b)
        _, _, b = ramp_statewide.resolve_request("/preview/ramps-statewide/local-newbern-glenburnie", {})
        self.assertIn("Map point", b)

    def test_public_unaffected(self):
        st, _, b = ramp_finder.resolve_request("/ramps", {}, public=True)
        self.assertNotIn("sw-group", b)
        self.assertNotIn("data-find", b)


if __name__ == "__main__":
    unittest.main()
