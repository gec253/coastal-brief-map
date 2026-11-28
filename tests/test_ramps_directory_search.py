"""/ramps directory search (Ed t559u, t560u): searches work immediately from every homepage entry
point, look across North Carolina by default, show active filters as removable chips, offer
'Search all North Carolina ramps' when filters leave nothing, and match the statewide map exactly."""
import json
import re
import unittest
from urllib.parse import parse_qs, urlparse

import folio_entry
import ramp_map_data as rmd
import ramp_search as rs
import ramp_statewide as sw

DATA = sw.load()
EXPECT = {"Goldsboro": 3, "New Bern": 7, "Wilmington": 8, "Beaufort": 9, "Raleigh": 1, "Falls Lake": 11,
          "Jordan Lake": 7, "Kerr Lake": 4, "Wake County": 7}
CATEGORY = {"COUNTY LINE": "name", "Seaforth": "name", "Manson": "town", "Carteret County": "county", "Carteret": "county",
            "Cape Fear River": "waterbody", "Bogue Sound": "waterbody"}
HOMEPAGE_REGIONS = ["crystal-coast", "emerald-isle", "wilmington", "topsail", "nags-head", "hatteras",
                    "falls-lake", "jordan-lake", "neuse-river", None, ""]


def shown(html):
    m = re.search(r'<p class="count">Showing (\d+) site', html)
    return int(m.group(1)) if m else None


def form_submit(href, q):
    """What the form sends: the query plus every field pre-filled from the page URL (as before the fix)."""
    p = {k: v[0] for k, v in parse_qs(urlparse(href).query).items()}
    return {"q": [q], "region": [p.get("region", "")], "type": [""], "status": [""], "water": [""]}


class DirectorySearch(unittest.TestCase):
    def test_every_homepage_entry_point_searches_statewide(self):
        for rid in HOMEPAGE_REGIONS:
            href = folio_entry.ramps_entry(rid)[0]
            for q, n in EXPECT.items():
                h = sw.render_list(DATA, form_submit(href, q), public=True)
                self.assertEqual(shown(h), n, (rid, href, q))

    def test_every_search_category_works_from_every_entry_point(self):
        for rid in HOMEPAGE_REGIONS:
            href = folio_entry.ramps_entry(rid)[0]
            for q, cat in CATEGORY.items():
                self.assertGreater(shown(sw.render_list(DATA, form_submit(href, q), public=True)) or 0, 0, (rid, q, cat))

    def test_server_live_and_map_use_the_same_rules(self):
        by = {r["id"]: r for r in json.loads(rmd.OUT.read_text())["records"]}
        for r in DATA["records"]:
            m = by[r["id"]]
            self.assertEqual(sw._find_text(r), rs.haystack(rs.parts(m["n"], m["al"], m["ci"], m["co"], m["w"], m["a"])))
        h = sw.render_list(DATA, {}, public=True)
        self.assertIn("window.CBRampSearch=", h)
        self.assertIn("S.matches(li.getAttribute(\"data-find\"),raw)", h)
        for q, n in EXPECT.items():
            self.assertEqual(sum(rs.matches(sw._find_text(r), q) for r in DATA["records"]), n, q)

    def test_intentional_area_is_kept_and_shown_as_a_removable_chip(self):
        h = sw.render_list(DATA, {"q": ["Goldsboro"], "region": ["wilmington"], "in_area": ["1"]}, public=True)
        self.assertEqual(shown(h), 0)
        self.assertIn('aria-label="Remove filter: Area: Wilmington · Wrightsville Beach"', h)
        self.assertIn('href="/ramps?q=Goldsboro" aria-label="Remove filter: Area', h)
        self.assertIn('class="btn sw-allnc" data-allnc href="/ramps?q=Goldsboro">Search all North Carolina ramps</a>', h)
        # browsing an area without a search still shows that area, with its chip
        h = sw.render_list(DATA, {"region": ["wilmington"]}, public=True)
        self.assertEqual(shown(h), 8)
        self.assertIn("Remove filter: Area: Wilmington", h)

    def test_inherited_area_is_named_with_a_way_to_narrow(self):
        h = sw.render_list(DATA, {"q": ["Goldsboro"], "region": ["crystal-coast"]}, public=True)
        self.assertEqual(shown(h), 3)
        self.assertIn("Searching all of North Carolina for “Goldsboro”.", h)
        self.assertIn('in_area=1">Only search Crystal Coast</a>', h)
        self.assertNotIn("Remove filter: Area", h)

    def test_other_filters_stay_and_show_chips_and_the_statewide_button(self):
        h = sw.render_list(DATA, {"q": ["Kerr Lake"], "type": ["paddle"]}, public=True)
        self.assertEqual(shown(h), 0)
        self.assertIn('Remove filter: Type: Paddle / carry-in', h)
        self.assertIn('href="/ramps?q=Kerr+Lake">Search all North Carolina ramps</a>', h)
        self.assertNotIn("Only search All of North Carolina", h)
        self.assertNotIn('data-scope="statewide"', h)  # no area in play, so no area notice
        self.assertEqual(shown(sw.render_list(DATA, {"q": ["Kerr Lake"]}, public=True)), 4)

    def test_no_manual_reset_needed_and_no_stale_state(self):
        h = sw.render_list(DATA, {"region": ["jordan-lake"]}, public=True)
        self.assertIn('autocomplete="off"', h)
        self.assertIn('addEventListener("pageshow",function(e){ if(e.persisted){ form.reset(); run(); } });', h)
        self.assertIn('name="in_area" value="1"> Only search in the selected area', h)
        self.assertNotIn("localStorage", h[h.index("window.CBRampSearch="):])
        self.assertIn('data-area="Jordan Lake"', h)
        self.assertIn("Press Search to look across all of North Carolina.", h)

    def test_unknown_area_with_a_search_still_searches(self):
        self.assertEqual(shown(sw.render_list(DATA, {"q": ["Kerr"], "region": ["bogus"]}, public=True)), 4)
        self.assertIn('data-honest="unknown-region"', sw.render_list(DATA, {"region": ["bogus"]}, public=True))

    def test_area_pages_without_a_search_are_unchanged(self):
        for rid in ("crystal-coast", "wilmington", "jordan-lake", "falls-lake", "neuse-river", "hatteras"):
            q = {"region": [rid]}
            expected = sum(1 for r in DATA["records"] if sw.region_match(r, rid))
            self.assertEqual(shown(sw.render_list(DATA, q, public=True)), expected, rid)
        self.assertEqual(shown(sw.render_list(DATA, {}, public=True)), 285)


if __name__ == "__main__":
    unittest.main()
