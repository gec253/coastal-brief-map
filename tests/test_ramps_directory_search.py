"""/ramps directory search (Ed t559u, t560u): searches work immediately from every homepage entry
point, look across North Carolina by default, show active filters as removable chips, offer
'Search all North Carolina ramps' when filters leave nothing, and match the statewide map exactly."""
import json
import os
import re
import threading
import unittest
from http.client import HTTPConnection
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
        self.assertIn('addEventListener("pageshow",function(e){ if(e.persisted){ form.reset(); run(); mapHref(); } });', h)
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

    def test_theme_and_navigation_are_preserved(self):
        h = sw.render_list(DATA, {"region": ["crystal-coast"], "q": ["Goldsboro"]}, public=True)
        for must in ("theme-toggle", "The Coastal Brief", 'aria-label="Site"', "Ramp Finder",
                     'action="/ramps"', ">Search</button>", ">Reset</button>", "Skip to the ramp list"):
            self.assertIn(must, h, must)
        self.assertIn('id="theme-toggle"', h)
        # no public Map tab while PUBLIC_RAMP_MAP is off
        self.assertNotIn(">Map</a>", h)
        self.assertNotIn("/preview/ramps-statewide/map", h)
        self.assertNotIn("Private preview", h)

class ServedDirectory(unittest.TestCase):
    """The public /ramps page as the server paints it (theme system, optional site nav)."""
    KEY = "local-test-key-directory-search-not-production"

    @classmethod
    def setUpClass(cls):
        import launch_flags
        import server
        cls.launch_flags = launch_flags
        cls.saved = {k: os.environ.get(k) for k in (launch_flags.PUBLIC_RAMPS, launch_flags.PUBLIC_RAMP_MAP, "PREVIEW_KEY", "NAV_V2")}
        os.environ[launch_flags.PUBLIC_RAMPS] = "1"
        os.environ.pop(launch_flags.PUBLIC_RAMP_MAP, None)
        os.environ["PREVIEW_KEY"] = cls.KEY
        os.environ["NAV_V2"] = "1"  # production has the shared masthead on /ramps
        cls.httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.port = cls.httpd.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown(); cls.httpd.server_close()
        for k, v in cls.saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def req(self, path):
        c = HTTPConnection("127.0.0.1", self.port, timeout=15)
        c.request("GET", path)
        r = c.getresponse(); body = r.read(); h = {k.lower(): v for k, v in r.getheaders()}; c.close()
        return r.status, body, h

    def test_theme_controls_and_site_navigation_are_on_the_served_page(self):
        st, body, _ = self.req("/ramps")
        self.assertEqual(st, 200)
        self.assertIn(b'data-cb-theme-control', body)
        self.assertIn(b'Find a Ramp', body)
        self.assertIn(b'Morning Brief', body)
        self.assertIn(b'Catch Wall', body)
        self.assertIn(b'>Search</button>', body)
        self.assertIn(b'>Reset</button>', body)
        self.assertNotIn(b'href="/ramps/map', body)  # flag off: no public map tab or View map link
        self.assertNotIn(b'id="sw-viewmap"', body)
        # Light / Dark / Auto still present after a search from a homepage region link
        st, body, _ = self.req("/ramps?q=Goldsboro&region=crystal-coast")
        self.assertEqual(st, 200)
        self.assertIn(b'data-cb-theme-control', body)
        self.assertIn(b'Find a Ramp', body)
        self.assertIn(b'Showing 3 sites', body)

    def test_preview_hub_stays_gated_and_lists_the_private_map(self):
        self.assertEqual(self.req("/preview")[0], 404)
        self.assertEqual(self.req("/preview/ramps-statewide/map")[0], 404)
        st, sm, _ = self.req("/sitemap.xml")
        self.assertEqual(st, 200)
        self.assertNotIn(b"/preview/", sm)
        self.assertNotIn(b"/ramps/map", sm)

class MapLinks(unittest.TestCase):
    """Public launch prep (Ed t564u): View map from the directory and List from the map, with search and
    filters (never location) handed across by the shared URL keys."""

    def test_directory_shows_view_map_only_when_the_map_flag_is_on(self):
        import launch_flags
        saved = os.environ.get(launch_flags.PUBLIC_RAMP_MAP)
        try:
            os.environ.pop(launch_flags.PUBLIC_RAMP_MAP, None)
            self.assertNotIn('id="sw-viewmap"', sw.render_list(DATA, {}, public=True))
            self.assertNotIn('id="sw-viewmap"', sw.render_list(DATA, {}, public=False))
            os.environ[launch_flags.PUBLIC_RAMP_MAP] = "1"
            h = sw.render_list(DATA, {"q": ["Kerr Lake"], "type": ["trailer"], "status": ["temporarily_closed"]}, public=True)
            self.assertIn('id="sw-viewmap" href="/ramps/map?q=Kerr+Lake&amp;type=trailer&amp;status=temporarily_closed"', h)
            self.assertIn("View map", h)
            self.assertIn('var mv=document.getElementById("sw-viewmap")', h)
            self.assertNotIn('id="sw-viewmap"', sw.render_list(DATA, {}, public=False))  # private directory keeps its own nav
            self.assertIn("min-height:44px", sw.EXTRA_CSS[sw.EXTRA_CSS.index(".sw-viewmap"):][:80])
        finally:
            if saved is None:
                os.environ.pop(launch_flags.PUBLIC_RAMP_MAP, None)
            else:
                os.environ[launch_flags.PUBLIC_RAMP_MAP] = saved

    def test_directory_filters_the_map_understands_are_the_only_ones_handed_over(self):
        import launch_flags
        os.environ[launch_flags.PUBLIC_RAMP_MAP] = "1"
        try:
            h = sw.render_list(DATA, {"q": ["Goldsboro"], "region": ["wilmington"], "water": ["fresh"]}, public=True)
            self.assertIn('href="/ramps/map?q=Goldsboro"', h)  # area and water are directory-only; no location ever
        finally:
            os.environ.pop(launch_flags.PUBLIC_RAMP_MAP, None)

    def test_map_has_a_list_link_that_carries_search_and_single_filters(self):
        import ramp_map
        js = ramp_map.JS_PATH.read_text()
        for public, d in ((True, "/ramps"), (False, "/preview/ramps-statewide")):
            h = ramp_map.render_html(public=public)
            self.assertIn('<a class="dirlink" id="dirlink" href="%s">List</a>' % d, h)
        fn = js[js.index("function dirHref()"):js.index("function refresh(fit)")]
        self.assertIn('u.push("q="', fn); self.assertIn('u.push("type="', fn); self.assertIn('u.push("status="', fn)
        for bad in ("NEAR", "coords", "lat", "lon", "geolocation"):
            self.assertNotIn(bad, fn, bad)
        self.assertIn('$("#dirlink").setAttribute("href", dirHref())', js)
        self.assertIn("min-height:44px", ramp_map.CSS_PATH.read_text()[ramp_map.CSS_PATH.read_text().index(".dirlink{"):][:200])
