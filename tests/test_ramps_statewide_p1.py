"""Phase 1 statewide Ramp Finder (Ed t547u): private preview data + pages.

Covers slug stability, field-by-field merge, no invented facilities, dedupe,
access types and dated closures, honest region handling, the Neuse split,
regulatory vs salinity labels, last-known-good refresh protection, public
/ramps isolation and cookie gating.
"""
import importlib.util
import json
import math
import os
import re
import shutil
import sys
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import ramp_finder  # noqa: E402
import ramp_statewide  # noqa: E402

RF = ROOT / "preview" / "ramp-finder"
NS = "not stated"
KEY = "unit-test-statewide-preview-key-0001"


def load_build():
    spec = importlib.util.spec_from_file_location("build_ramps_statewide", ROOT / "scripts" / "build_ramps_statewide.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def miles(a, b, c, d):
    p1, p2 = math.radians(a), math.radians(c)
    x = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(d - b) / 2) ** 2
    return 2 * 3958.7613 * math.asin(math.sqrt(x))


class Data(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inv = json.loads((RF / "inventory.json").read_text())
        cls.sw = json.loads((RF / "statewide.json").read_text())
        cls.snap = json.loads((RF / "ncwrc_snapshot.json").read_text())
        cls.by = {r["id"]: r for r in cls.sw["records"]}

    def test_ids_unique(self):
        ids = [r["id"] for r in self.sw["records"]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_every_existing_slug_resolves_to_the_same_ramp(self):
        for m in self.inv["records"]:
            r = self.by.get(m["id"])
            self.assertIsNotNone(r, m["id"])
            for k in ("official_name", "display_name", "area", "listing_class", "directions", "county", "body_of_water"):
                self.assertEqual(r[k], m[k], (m["id"], k))
            st, _, body = ramp_statewide.resolve_request("/preview/ramps-statewide/" + m["id"], {})
            self.assertEqual(st, 200, m["id"])
            self.assertIn(ramp_finder.esc(m["display_name"]), body)

    def test_crosswalk_slugs_are_stable(self):
        cw = json.loads((RF / "ncwrc_crosswalk.json").read_text())["by_slug"]
        for slug, gid in cw.items():
            self.assertEqual(self.by[slug]["ncwrc"]["globalid"], gid)
        self.assertEqual(len(set(cw.values())), len(cw))

    def test_manual_fields_win_and_fills_are_attributed(self):
        for m in self.inv["records"]:
            r = self.by[m["id"]]
            for k, v in m.items():
                if k == "notices":
                    self.assertEqual(r[k][:len(v)], v, m["id"])  # original notices kept, in order
                    continue
                if r[k] != v:
                    self.assertIn(v, (None, "", NS), (m["id"], k))
                    self.assertTrue(r["field_sources"].get(k, "").startswith("ncwrc:"), (m["id"], k))
            self.assertEqual(r["record_basis"], "manual_verified")

    def test_new_records_copy_ncwrc_exactly_and_never_invent(self):
        raw = self.snap["records"]
        yn = {1: "yes", 0: "no", None: NS}
        nums = {"lanes": "Launch_Lane_No", "trailer_parking": "Parking_Trailer", "trailer_parking_ada": "Parking_Trailer_ADA",
                "nontrailer_parking": "Parking_nonTrailer", "fixed_docks": "Fix_Dock_No", "floating_docks": "Float_Dock_No",
                "courtesy_docks": "Courtesy_Dock_No"}
        flags = {"restrooms": "Restroom", "lighting": "Lighting", "kiosk": "Kiosk", "trash_can": "Trash_Can",
                 "fishing_pier": "Fishing_Pier", "ada_paved_walkway": "ADA_Paved_Walkway",
                 "ada_dock_handrails": "ADA_Dock_Handrails"}
        n = 0
        for r in self.sw["records"]:
            if r["record_basis"] != "ncwrc_official_listing":
                continue
            n += 1
            a = raw[r["ncwrc"]["globalid"]]
            for k, f in nums.items():
                self.assertEqual(r[k], a[f] if a[f] is not None else NS, (r["id"], k))
            for k, f in flags.items():
                want = a[f].strip() if isinstance(a[f], str) else yn[a[f]]
                self.assertEqual(r[k], want, (r["id"], k))
            self.assertEqual(r["directions"]["latitude"], a["Latitude"])
            if a["Owner"] != "NC WRC":
                self.assertTrue(r["fees"]["summary"].startswith("Not stated"), r["id"])
                self.assertTrue(r["hours"]["summary"].startswith("Not stated"), r["id"])
            self.assertEqual(r["verification_status"], "official_listing")
        self.assertEqual(n, 230)

    def test_no_duplicates(self):
        gids = [r["ncwrc"]["globalid"] for r in self.sw["records"] if r.get("ncwrc")]
        self.assertEqual(len(gids), len(set(gids)))
        self.assertEqual(len(gids), len(self.snap["records"]))
        b = load_build()
        pts = [(r, r["directions"]) for r in self.sw["records"] if isinstance((r.get("directions") or {}).get("latitude"), float)]
        for i, (r1, d1) in enumerate(pts):
            for r2, d2 in pts[i + 1:]:
                if b.haversine_m(d1["latitude"], d1["longitude"], d2["latitude"], d2["longitude"]) <= b.MATCH_RADIUS_M:
                    self.assertFalse(b.names_match(r1["official_name"], r2["official_name"]), (r1["id"], r2["id"]))

    def test_counts_add_up(self):
        c = self.sw["counts"]
        self.assertEqual(c["total"], len(self.sw["records"]))
        self.assertEqual(c["by_basis"], {"manual_verified": 55, "ncwrc_official_listing": 230})
        self.assertEqual(sum(c["by_access_type"].values()), c["total"])

    def test_closures_and_dated_notices(self):
        st = lambda rid: self.by[rid]["access_status"]
        for rid in ("baa-flemingtown-landing", "baa-henderson-point", "baa-county-line", "baa-outfall-canal"):
            self.assertEqual(st(rid)["code"], "temporarily_closed", rid)
            self.assertTrue(st(rid)["as_of"].startswith("2026-"), rid)
        self.assertEqual(st("baa-hibernia")["code"], "conflicting")
        self.assertEqual(st("baa-norwood")["code"], "conflicting")
        self.assertEqual(st("parks-falls-holly-point-campers")["code"], "temporarily_closed")
        self.assertIn("Nov 27, 2026", st("parks-falls-holly-point-campers")["as_of"])
        self.assertEqual(st("parks-jordan-vista-point-sailboat")["code"], "temporarily_closed")
        self.assertEqual(st("parks-jordan-seaforth")["code"], "partially_open")
        for r in self.sw["records"]:
            s = r["access_status"]
            self.assertIn(s["code"], {"listed_open", "temporarily_closed", "partially_open", "conflicting", "not_stated"})
            if s["code"] == "listed_open":
                self.assertEqual((r.get("site_status_official") or "").upper(), "OPEN", r["id"])
            if not ramp_finder._facility(r, "site_status_official") and not r.get("applied_notices"):
                self.assertEqual(s["code"], "not_stated", r["id"])  # missing data is never "open"

    def test_access_types(self):
        for r in self.sw["records"]:
            if r["record_basis"] == "ncwrc_official_listing":
                a = self.snap["records"][r["ncwrc"]["globalid"]]
                if a["Portable_Boat_Access_Type"]:
                    self.assertEqual(r["access_type"], "paddle", r["id"])
                elif (a["Launch_Lane_No"] or 0) >= 1:
                    self.assertEqual(r["access_type"], "trailer", r["id"])
                if a["Motorboats_Restricted"] == 1:
                    self.assertEqual(r["listing_class"], "limited", r["id"])

    def test_regulatory_and_salinity_are_separate(self):
        for r in self.sw["records"]:
            self.assertIn(r["regulatory_class"], {"INLAND", "COASTAL", "JOINT", NS})
            sal = r["salinity"]
            self.assertIn(sal["basis"], {"verified", "inferred", "not_inferred", "unknown"})
            if sal["basis"] == "inferred":
                self.assertIn("(inferred)", sal["label"])
                self.assertTrue(sal["method"])
            if r["record_basis"] == "manual_verified" and sal["basis"] == "verified":
                self.assertEqual(sal["class"], self.inv_by(r["id"])["salinity_class"])
        r = self.by["baa-beaufort"]
        rows = dict(ramp_finder.facility_rows(r))
        self.assertIn("Coastal fishing waters", rows["Fishing-rules classification"])
        self.assertEqual(rows["Water (fresh / brackish / salt)"], "Saltwater (verified)")

    def inv_by(self, rid):
        return next(m for m in self.inv["records"] if m["id"] == rid)

    def test_region_rule(self):
        rules = self.sw["meta"]["rules"]
        anchors = rules["anchors"]
        for r in self.sw["records"]:
            ar = r["area_rule"]
            if "anchor_region" in ar and not ar.get("exception"):
                d = r["directions"]
                dist = {k: miles(d["latitude"], d["longitude"], v["lat"], v["lon"]) for k, v in anchors.items()}
                self.assertLessEqual(ar["anchor_distance_mi"], rules["region_radius_mi"])
                self.assertEqual(min(dist, key=dist.get), ar["anchor_region"], r["id"])
        areas = self.sw["counts"]["by_area"]
        for a in ("wilmington", "topsail", "nags-head"):
            self.assertGreater(areas.get(a, 0), 0, a)
        hat = [r for r in self.sw["records"] if r["area"] == "hatteras"]
        self.assertEqual([r["id"] for r in hat], ["baa-rodanthe"])  # only by the documented exception (t548u)
        self.assertTrue(hat[0]["area_rule"].get("exception"))
        self.assertGreater(miles(hat[0]["directions"]["latitude"], hat[0]["directions"]["longitude"],
                                 anchors["hatteras"]["lat"], anchors["hatteras"]["lon"]), rules["region_radius_mi"])

    def test_neuse_split(self):
        ne = [r for r in self.sw["records"] if r["area"] == "neuse-river"]
        self.assertEqual(len(ne), 25)
        up = {r["id"] for r in ne if r["neuse_segment"] == "upper"}
        self.assertIn("baa-goldsboro", up)
        self.assertNotIn("baa-seven-springs", up)
        self.assertNotIn("local-newbern-union-point", up)
        for r in ne:
            if r["neuse_segment"] == "upper":
                self.assertLessEqual(r["directions"]["longitude"], -78.0)
                self.assertEqual(r["salinity"]["class"], "freshwater")


class Pages(unittest.TestCase):
    def get(self, **q):
        st, _, body = ramp_statewide.resolve_request("/preview/ramps-statewide", {k: [v] for k, v in q.items()})
        self.assertEqual(st, 200)
        return body

    def cards(self, body):
        return re.findall(r'href="/preview/ramps-statewide/([a-z0-9-]+)"', body)

    def test_unknown_region_is_honest_not_all(self):
        b = self.get(region="atlantis")
        self.assertIn('data-honest="unknown-region"', b)
        self.assertEqual(self.cards(b), [])
        self.assertIn('href="/preview/ramps-statewide"', b)

    def test_hatteras_is_honest(self):
        b = self.get(region="hatteras")
        self.assertIn('data-honest="hatteras"', b)
        self.assertIn("Hatteras Island coverage is limited", b)
        self.assertIn("documented exception", b)
        self.assertIn("baa-rodanthe", self.cards(b))
        self.assertRegex(b, r"\d+ mi straight line from Cape Hatteras")  # nearest launches outside the area
        self.assertNotIn("National Park Service sound-side areas are listed", b)

    def test_new_regions_list_only_their_records(self):
        sw = ramp_statewide.load()
        for reg in ("wilmington", "topsail", "nags-head"):
            want = sorted(r["id"] for r in sw["records"] if r["area"] == reg)  # all types now shown, grouped by type
            got = sorted(self.cards(self.get(region=reg)))
            self.assertEqual(got, want, reg)

    def test_statewide_default_distinguishes_types(self):
        b = self.get()
        for sec in ('data-section="trailer"', 'data-section="paddle"', 'data-section="limited"', 'data-section="needs_review"'):
            self.assertIn(sec, b)
        self.assertIn("Temporarily closed", b)
        self.assertIn("6 temporarily closed", b)  # status is its own dimension (t548u)

    def test_neuse_river_url_still_works_and_splits(self):
        b = self.get(region="neuse-river")
        self.assertIn("Upper Neuse, Falls Dam to Goldsboro", b)
        self.assertIn("Lower Neuse, below Goldsboro", b)
        self.assertEqual(len(set(self.cards(b))), 25)

    def test_filters(self):
        for c in self.cards(self.get(type="paddle")):
            self.assertEqual(ramp_statewide.by_id(c, ramp_statewide.load())["access_type"], "paddle")
        for c in self.cards(self.get(water="fresh")):
            self.assertEqual(ramp_statewide.by_id(c, ramp_statewide.load())["salinity"]["class"], "freshwater")

    def test_detail_keeps_directions_and_shows_status(self):
        st, _, b = ramp_statewide.resolve_request("/preview/ramps-statewide/baa-hibernia", {})
        self.assertEqual(st, 200)
        self.assertIn("Status unclear", b)
        self.assertIn("maps.apple.com/?daddr=", b)
        self.assertIn("noindex, nofollow", b)
        st, _, b = ramp_statewide.resolve_request("/preview/ramps-statewide/baa-beaufort", {})
        self.assertIn("https://www.google.com/maps/dir/?api=1&amp;destination=34.70975803,-76.63196738", b)
        self.assertEqual(ramp_statewide.resolve_request("/preview/ramps-statewide/nope", {})[0], 404)

    def test_public_ramps_never_read_statewide(self):
        st, _, b = ramp_finder.resolve_request("/ramps", {}, public=True)
        self.assertEqual(st, 200)
        self.assertNotIn("ramps-statewide", b)
        self.assertNotIn("badge-paddle", b)
        self.assertIn("Showing 48 ramps", b)
        st, _, b = ramp_finder.resolve_request("/preview/ramps", {}, public=False)
        self.assertNotIn("ramps-statewide", b)
        self.assertIsNone(ramp_finder.STATEWIDE_BASE.get())


class Refresh(unittest.TestCase):
    def setUp(self):
        self.b = load_build()
        self.tmp = Path(tempfile.mkdtemp())
        for name in ("OUT", "SNAPSHOT", "CROSSWALK", "REPORT", "NOAA_CACHE"):
            src = getattr(self.b, name)
            dst = self.tmp / src.name
            if src.exists():
                shutil.copy(src, dst)
            setattr(self.b, name, dst)
        snap = json.loads(self.b.SNAPSHOT.read_text())
        self.fields = snap["fields"]
        self.attrs = list(snap["records"].values())
        self.edit = snap["editingInfo"]
        self.before = self.b.OUT.read_bytes()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def save(self, attrs, fields=None):
        p = self.tmp / "resp.json"
        p.write_text(json.dumps({"features": [{"attributes": a} for a in attrs],
                                 "fields": [{"name": f} for f in (fields or self.fields)], "editingInfo": self.edit}))
        return str(p)

    def records_of(self, raw):
        return json.loads(raw)["records"]

    def test_failed_fetch_keeps_last_known_good(self):
        rc = self.b.main(["--from-file", str(self.tmp / "missing.json"), "--checked", "2026-11-28"])
        self.assertEqual(rc, 2)
        after = json.loads(self.b.OUT.read_text())
        self.assertEqual(after["records"], self.records_of(self.before))
        self.assertEqual(after["meta"]["refresh"]["status"], "kept_last_known_good")
        self.assertIn("fetch failed", after["meta"]["refresh"]["reason"])
        st, _, body = ramp_statewide.render_list(after, {}), None, None
        self.assertIn('data-refresh="kept-last-known-good"', st)

    def test_count_drop_keeps_last_known_good(self):
        rc = self.b.main(["--from-file", self.save(self.attrs[:200]), "--checked", "2026-11-28"])
        self.assertEqual(rc, 2)
        after = json.loads(self.b.OUT.read_text())
        self.assertEqual(len(after["records"]), len(self.records_of(self.before)))
        self.assertIn("record count dropped from 267 to 200", after["meta"]["refresh"]["reason"])

    def test_schema_change_keeps_last_known_good(self):
        attrs = [{k: v for k, v in a.items() if k != "Launch_Lane_No"} for a in self.attrs]
        rc = self.b.main(["--from-file", self.save(attrs, [f for f in self.fields if f != "Launch_Lane_No"]), "--checked", "2026-11-28"])
        self.assertEqual(rc, 2)
        self.assertIn("schema change", json.loads(self.b.OUT.read_text())["meta"]["refresh"]["reason"])

    def test_small_change_is_applied_and_reported(self):
        attrs = json.loads(json.dumps(self.attrs))
        gone = attrs.pop()
        attrs[0]["Launch_Lane_No"] = (attrs[0]["Launch_Lane_No"] or 0) + 1
        rc = self.b.main(["--from-file", self.save(attrs), "--checked", "2026-11-28"])
        self.assertEqual(rc, 0)
        rep = json.loads(self.b.REPORT.read_text())
        self.assertEqual([x["globalid"] for x in rep["diff"]["removed"]], [gone["GlobalID"]])
        ch = rep["diff"]["changed"][attrs[0]["GlobalID"]]["fields"]
        self.assertIn("Launch_Lane_No", ch)
        after = json.loads(self.b.OUT.read_text())
        self.assertEqual(len(after["records"]), 284)
        # existing slugs survive a refresh
        self.assertTrue({r["id"] for r in self.records_of(self.before)} - {r["id"] for r in after["records"]}
                        <= {r["id"] for r in self.records_of(self.before) if (r.get("ncwrc") or {}).get("globalid") == gone["GlobalID"]})


class Gating(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import server
        cls.server = server
        cls.httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.port = cls.httpd.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def req(self, path, cookie=None, key=KEY):
        saved = os.environ.get("PREVIEW_KEY")
        os.environ["PREVIEW_KEY"] = key
        try:
            conn = HTTPConnection("127.0.0.1", self.port, timeout=15)
            conn.request("GET", path, headers={"Cookie": cookie} if cookie else {})
            r = conn.getresponse()
            body = r.read()
            h = {k.lower(): v for k, v in r.getheaders()}
            conn.close()
            return r.status, body, h
        finally:
            if saved is None:
                os.environ.pop("PREVIEW_KEY", None)
            else:
                os.environ["PREVIEW_KEY"] = saved

    def test_anonymous_404(self):
        for p in ("/preview/ramps-statewide", "/preview/ramps-statewide/baa-beaufort", "/preview/ramps-statewide?region=hatteras"):
            self.assertEqual(self.req(p)[0], 404, p)

    def test_cookie_unlocks_noindex_nostore(self):
        ck = "%s=%s" % (self.server.PREVIEW_COOKIE, self.server._preview_cookie_value(KEY))
        st, body, h = self.req("/preview/ramps-statewide", cookie=ck)
        self.assertEqual(st, 200)
        self.assertIn("no-store", h.get("cache-control", ""))
        self.assertIn("noindex", h.get("x-robots-tag", "") + body.decode()[:3000])
        st, body, _ = self.req("/preview", cookie=ck)
        self.assertIn(b'href="/preview/ramps-statewide"', body)

    def test_not_in_sitemap(self):
        st, body, _ = self.req("/sitemap.xml")
        self.assertNotIn(b"ramps-statewide", body)


if __name__ == "__main__":
    unittest.main()
