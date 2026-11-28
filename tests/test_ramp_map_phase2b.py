"""Ramp Finder Phase 2 remainder (Ed t558u, t559u, t560u): shared search, filters and URL state,
directions, the self-hosted water layer (license, size, Falls/Jordan accuracy), and a browser
privacy proof that location is never requested before the Near Me tap and never stored or sent."""
import gzip
import json
import math
import os
import shutil
import subprocess
import threading
import unittest
from pathlib import Path

import ramp_map
import ramp_map_data as rmd
import ramp_search as rs

ROOT = Path(__file__).resolve().parent.parent
SW = json.loads(rmd.STATEWIDE.read_text())["records"]
DOC = json.loads(rmd.OUT.read_text())
JS = ramp_map.JS_PATH.read_text()
GEO_DIR = ROOT / "preview" / "ramp-finder" / "map"
LO = json.loads((GEO_DIR / "geo-lo.json").read_text())
HI = json.loads((GEO_DIR / "geo-hi.json").read_text())
NODE = shutil.which("node")
QUERIES = ["Goldsboro", "New Bern", "Wilmington", "Beaufort", "Raleigh", "Falls Lake", "Jordan Lake", "Kerr Lake",
           "Lake Jordan", "Wake", "Wake County", "Carteret county", "Neuse", "Cape Fear River", "Seaforth",
           "COUNTY LINE", "crystal coast", "Bogue Sound", "Énfield", "  kerr  ", "new-bern", "zzz no match", ""]
EXPECT = {"Goldsboro": 3, "New Bern": 7, "Wilmington": 8, "Beaufort": 9, "Raleigh": 1, "Falls Lake": 11,
          "Jordan Lake": 7, "Kerr Lake": 4, "Lake Jordan": 7, "Wake County": 7, "zzz no match": 0, "": 285}


class SharedSearch(unittest.TestCase):
    def test_expected_counts_for_ed_s_test_queries(self):
        for q, n in EXPECT.items():
            self.assertEqual(sum(rs.matches(rs.record_haystack(r), q) for r in SW), n, q)

    def test_falls_and_jordan_are_never_confused(self):
        for r in SW:
            h = rs.record_haystack(r)
            w = (r.get("body_of_water") or "").lower() + " " + (r.get("area_label") or "").lower()
            if rs.matches(h, "Jordan Lake"):
                self.assertIn("jordan", w, r["id"])
            if rs.matches(h, "Falls Lake"):
                self.assertIn("falls", w, r["id"])
                self.assertNotIn("jordan", w, r["id"])
            if rs.matches(h, "Kerr Lake"):
                self.assertIn("kerr", w, r["id"])

    def test_goldsboro_means_goldsboro_not_a_neuse_note(self):
        for r in SW:
            if rs.matches(rs.record_haystack(r), "Goldsboro"):
                self.assertIn("goldsboro", rs.norm(" ".join([r.get("display_name") or "", r.get("city") or "", r.get("alias") or ""])), r["id"])

    def test_map_records_carry_what_the_shared_haystack_needs(self):
        by = {r["id"]: r for r in SW}
        for m in DOC["records"]:
            r = by[m["id"]]
            self.assertEqual(rs.haystack(rs.parts(m["n"], m["al"], m["ci"], m["co"], m["w"], m["a"])), rs.record_haystack(r), m["id"])

    @unittest.skipUnless(NODE, "node not installed")
    def test_javascript_twin_gives_identical_results_on_every_record(self):
        maps = [[m["n"], m["al"], m["ci"], m["co"], m["w"], m["a"]] for m in DOC["records"]]
        script = rs.JS.replace("window.CBRampSearch=", "var window={};window.CBRampSearch=") + """
var S=window.CBRampSearch, inp=JSON.parse(require('fs').readFileSync(0,'utf8')), out={hay:[],m:{}};
inp.maps.forEach(function(p){out.hay.push(S.haystack(S.parts.apply(null,p)));});
inp.q.forEach(function(q){out.m[q]=out.hay.map(function(h){return S.matches(h,q);});});
process.stdout.write(JSON.stringify(out));"""
        r = subprocess.run([NODE, "-e", script], input=json.dumps({"maps": maps, "q": QUERIES}), capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)
        py_hay = [rs.haystack(rs.parts(*p)) for p in maps]
        self.assertEqual(out["hay"], py_hay)
        for q in QUERIES:
            self.assertEqual(out["m"][q], [rs.matches(h, q) for h in py_hay], q)

    def test_map_uses_the_shared_search_and_page_inlines_it(self):
        self.assertIn("var RS = window.CBRampSearch;", JS)
        self.assertIn("return RS.matches(r._hay, S.q);", JS)
        self.assertIn("RS.haystack(RS.parts(r.n, r.al, r.ci, r.co, r.w, r.a))", JS)
        h = ramp_map.render_html()
        self.assertLess(h.index("window.CBRampSearch="), h.index('.js" defer></script>'))

    def test_filters_are_visible_removable_and_never_need_a_reset(self):
        self.assertIn('id="actf"', ramp_map.render_html())
        self.assertIn("Search all North Carolina ramps", JS)
        self.assertIn('aria-label="Remove filter: ', JS)
        self.assertIn("function searchAllNC()", JS)
        self.assertNotIn("fishing", JS.lower())
        self.assertIn("ADA features listed", JS)


class Directions(unittest.TestCase):
    def test_destination_only_apple_on_iphone_google_elsewhere(self):
        fn = JS[JS.index("function isApple()"):JS.index("function directionsURL(r)") + 400]
        self.assertIn("iPhone|iPad|iPod", fn)
        self.assertIn('return r.pr === "exact" ? r.la + "," + r.lo : r.ad;', fn)
        self.assertIn('"https://maps.apple.com/?daddr=" + d', fn)
        self.assertIn('"https://www.google.com/maps/dir/?api=1&destination=" + d', fn)
        for bad in ("saddr", "origin=", "NEAR"):
            self.assertNotIn(bad, fn, bad)

    def test_every_record_has_a_directions_destination(self):
        for r in DOC["records"]:
            if r["pr"] == "exact":
                self.assertIsNotNone(r["la"], r["id"])
            else:
                self.assertTrue(r["ad"].strip(), r["id"])  # approximate and address-only sites route by address

    def test_approximate_points_are_never_presented_as_exact(self):
        self.assertIn('(r.pr === "approx" ? "≈ " : "")', JS)
        self.assertIn("Approximate location", JS)
        self.assertIn('rel="noopener noreferrer"', JS)


def _dec(a):
    x, y = a[0], a[1]; pts = [(x / 1e4, y / 1e4)]
    for i in range(2, len(a), 2):
        x += a[i]; y += a[i + 1]; pts.append((x / 1e4, y / 1e4))
    return pts


def _inside(pt, ring):
    x, y = pt; c = False
    for i in range(len(ring)):
        (x1, y1), (x2, y2) = ring[i], ring[i - 1]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            c = not c
    return c


def _seg_km(p, a, b):
    k = math.cos(math.radians(p[1]))
    px, py, ax, ay, bx, by = p[0] * k, p[1], a[0] * k, a[1], b[0] * k, b[1]
    dx, dy = bx - ax, by - ay
    t = 0 if dx == dy == 0 else max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - ax - t * dx, py - ay - t * dy) * 111.32


class WaterLayer(unittest.TestCase):
    FEATS = [[_dec(r) for r in f] for f in HI["water"]]

    def dist_km(self, pt):
        best, which = 1e9, None
        for i, f in enumerate(self.FEATS):
            if sum(_inside(pt, r) for r in f) % 2:
                return 0.0, i
            for r in f:
                for j in range(len(r)):
                    d = _seg_km(pt, r[j], r[j - 1])
                    if d < best:
                        best, which = d, i
        return best, which

    def test_license_and_source_recorded(self):
        for d in (LO, HI):
            self.assertIn("U.S. Census Bureau", d["source"])
            self.assertIn("Public domain", d["license"])
            self.assertIn("17 U.S.C. 105", d["license"])
            self.assertIn("not for navigation", d["generalization"])
        doc = (ROOT / "docs" / "RAMP_MAP_GEO_SOURCES.md").read_text()
        for must in ("TIGERweb/Hydro/MapServer/1", "Title 17 U.S.C., Section 105", "registered trademark", "Falls Lake", "Jordan Lake"):
            self.assertIn(must, doc, must)
        self.assertIn("TIGER/Line® water and places (public domain)", JS)

    def test_size_budget(self):
        self.assertLessEqual(len(gzip.compress((GEO_DIR / "geo-lo.json").read_bytes(), 9)), 60 * 1024)
        self.assertLessEqual(len(gzip.compress((GEO_DIR / "geo-hi.json").read_bytes(), 9)), 200 * 1024)

    def test_no_third_party_tiles_or_libraries(self):
        self.assertNotIn("tileLayer", JS)
        self.assertNotRegex(JS, r"(tile\.openstreetmap|mapbox|arcgisonline|googleapis|stadia)")

    def test_falls_and_jordan_labels_sit_in_their_own_distinct_lakes(self):
        lab = {l["t"]: l for l in LO["labels"] if l["k"] == "lake"}
        f, j = lab["Falls Lake"], lab["Jordan Lake"]
        df, fi = self.dist_km((f["lo"], f["la"]))
        dj, ji = self.dist_km((j["lo"], j["la"]))
        self.assertEqual((df, dj), (0.0, 0.0))
        self.assertNotEqual(fi, ji)
        self.assertGreater(f["la"], 35.9); self.assertLess(j["la"], 35.85)  # Falls north of Durham/Raleigh, Jordan south-west
        for bad in ("Falls Lk", "B Everett Jordan Lk", "Jordan Lk"):
            self.assertNotIn(bad, [l["t"] for l in LO["labels"]])

    def test_falls_and_jordan_pins_sit_on_or_beside_the_water(self):
        lab = {l["t"]: l for l in LO["labels"] if l["k"] == "lake"}
        lake_feat = {name: self.dist_km((lab[name]["lo"], lab[name]["la"]))[1] for name in ("Falls Lake", "Jordan Lake")}
        checked = 0
        for r in DOC["records"]:
            w = (r["w"] or "").lower()
            name = "Falls Lake" if "falls lake" in w and "blewett" not in w else "Jordan Lake" if "jordan" in w else None
            if not name or r["pr"] == "none":
                continue
            d, feat = self.dist_km((r["lo"], r["la"]))
            limit = 0.5 if r["pr"] == "exact" else 1.0  # approximate State Parks points are access-area points
            self.assertLessEqual(d, limit, (r["id"], round(d, 3)))
            other = "Jordan Lake" if name == "Falls Lake" else "Falls Lake"
            self.assertNotEqual(feat, lake_feat[other], (r["id"], name))  # TIGER splits a lake into arms, never into the other lake
            checked += 1
        self.assertGreaterEqual(checked, 15)


CHROME = "/usr/bin/google-chrome"


@unittest.skipUnless(os.path.exists(CHROME) and os.environ.get("RAMP_BROWSER_TESTS", "1") == "1", "chrome missing")
class BrowserPrivacy(unittest.TestCase):
    """Drives the private map with a local key: zero location requests before the tap, nothing stored or sent."""
    KEY = "local-test-key-phase2b-browser-not-production"

    @classmethod
    def setUpClass(cls):
        try:
            from playwright.sync_api import sync_playwright  # noqa: F401
        except Exception:
            raise unittest.SkipTest("playwright missing")
        import server
        cls.saved = os.environ.get("PREVIEW_KEY"); os.environ["PREVIEW_KEY"] = cls.KEY
        cls.httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.base = "http://127.0.0.1:%d" % cls.httpd.server_address[1]
        cls.cookie = server._preview_cookie_value(cls.KEY); cls.cname = server.PREVIEW_COOKIE

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown(); cls.httpd.server_close()
        if cls.saved is None:
            os.environ.pop("PREVIEW_KEY", None)
        else:
            os.environ["PREVIEW_KEY"] = cls.saved

    def test_location_only_after_tap_and_never_stored_or_sent(self):
        from playwright.sync_api import sync_playwright
        fake = {"latitude": 35.7721, "longitude": -78.6441}
        reqs, errors = [], []
        with sync_playwright() as p:
            b = p.chromium.launch(executable_path=CHROME, args=["--headless=new", "--no-sandbox", "--disable-gpu"])
            c = b.new_context(viewport={"width": 390, "height": 844}, permissions=["geolocation"], geolocation=fake)
            c.add_cookies([{"name": self.cname, "value": self.cookie, "url": self.base}])
            c.add_init_script("""(function(){window.__geo=0;var g=navigator.geolocation;['getCurrentPosition','watchPosition'].forEach(function(k){var o=g[k].bind(g);g[k]=function(){window.__geo++;return o.apply(null,arguments)}});})()""")
            pg = c.new_page(); pg.on("request", lambda r: reqs.append(r.url)); pg.on("pageerror", lambda e: errors.append(str(e)))
            url = self.base + "/preview/ramps-statewide/map"
            pg.goto(url, wait_until="networkidle"); pg.wait_for_selector("body[data-ready='1'][data-geo='1']", timeout=20000)
            # search and filters work immediately on a fresh session, statewide
            pg.fill("#q", "Goldsboro"); pg.keyboard.press("Enter"); pg.wait_for_timeout(300)
            self.assertEqual(pg.evaluate("window.__rf.results().length"), 3)
            pg.fill("#q", ""); pg.dispatch_event("#q", "input"); pg.keyboard.press("Escape")
            pg.click('.chip[data-i="1"]')  # Paddle / carry-in
            pg.fill("#q", "Kerr Lake"); pg.keyboard.press("Enter"); pg.wait_for_timeout(300)
            self.assertEqual(pg.evaluate("window.__rf.results().length"), 0)
            self.assertTrue(pg.is_visible("#actf .af.all"))
            pg.click("#actf .af.all"); pg.wait_for_timeout(300)
            self.assertEqual(pg.evaluate("window.__rf.results().length"), 4)
            pg.fill("#q", ""); pg.dispatch_event("#q", "input"); pg.keyboard.press("Escape")
            before = pg.url
            self.assertEqual(pg.evaluate("window.__geo"), 0)
            pg.click("#near"); self.assertEqual(pg.evaluate("window.__geo"), 0)  # disclosure first
            self.assertIn("never stored or sent", pg.inner_text("#pre-p"))
            pg.click("#pre-go"); pg.wait_for_selector("#nearoff:not([hidden])", timeout=15000)
            self.assertEqual(pg.evaluate("window.__geo"), 1)
            self.assertEqual(pg.url, before)
            self.assertEqual(pg.evaluate("[Object.keys(localStorage).length, Object.keys(sessionStorage).length]"), [0, 0])
            self.assertEqual(pg.evaluate("document.cookie.split(';').map(function(x){return x.split('=')[0].trim()})"), [self.cname])  # only the test's own preview cookie
            self.assertIn("straight-line", pg.inner_text("#sl").lower())
            b.close()
        self.assertEqual(errors, [])
        self.assertEqual([u for u in reqs if "35.77" in u or "78.64" in u], [])
        self.assertEqual({u.split("/")[2] for u in reqs}, {self.base.split("/")[2]})


if __name__ == "__main__":
    unittest.main()
