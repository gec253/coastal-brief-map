"""Phase 3A guards: station mapping and water classification (Ed, Nov 28, 2026). Data only; no page uses it yet."""
import json
import re
import sys
import unittest
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import build_ramp_stations as B  # noqa: E402

DATA = json.loads((ROOT / "stations/ramp_stations.json").read_text())
RECORDS = json.loads((ROOT / "preview/ramp-finder/map-data.json").read_text())["records"]
SITES = {e["id"]: e for e in DATA["sites"]}
REGIONAL = {"Falls Lake", "Jordan Lake", "Neuse River", "Crystal Coast", "Wilmington · Wrightsville Beach",
            "Nags Head · Outer Banks", "Topsail", "Hatteras Island"}


def stations(kind=None):
    for e in DATA["sites"]:
        for c in e["stations"]:
            if kind is None or c["type"] == kind:
                yield e, c


class NotServed(unittest.TestCase):
    """The station files live in stations/, which the public site never serves (Ed t569u)."""

    MOVED = ("ramp_stations.json", "ramp_stations_inputs.json", "ramp_stations_review.json")

    def test_moved_out_of_the_public_data_folder(self):
        for n in self.MOVED:
            self.assertFalse((ROOT / "data" / n).exists(), n)
            self.assertTrue((ROOT / "stations" / n).exists(), n)
        self.assertEqual(sorted(p.name for p in (ROOT / "data").glob("ramp_station*")), [])

    def test_static_route_config_denies_the_folder(self):
        import server
        self.assertIn("/stations/", server._STATIC_DENY_PREFIX)
        for n in self.MOVED:
            for p in ("/stations/" + n, "/stations/../stations/" + n, "/%73tations/" + n, "/data/" + n):
                if p.startswith("/data/"):
                    continue  # allowed by extension, but the file is not there (next test proves 404)
                self.assertFalse(server._static_allowed(p), p)

    def test_every_moved_file_is_404_over_http(self):
        import threading
        from http.client import HTTPConnection
        import server
        httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        try:
            for n in self.MOVED:
                for p in ("/data/" + n, "/stations/" + n, "/stations/", "/stations"):
                    c = HTTPConnection("127.0.0.1", httpd.server_address[1], timeout=15)
                    c.request("GET", p)
                    r = c.getresponse(); r.read(); c.close()
                    self.assertEqual(r.status, 404, p)
        finally:
            httpd.shutdown(); httpd.server_close()


class Coverage(unittest.TestCase):
    def test_every_record_is_covered_once(self):
        self.assertEqual(len(RECORDS), 285)
        self.assertEqual(sorted(SITES), sorted(r["id"] for r in RECORDS))
        self.assertEqual(len(DATA["sites"]), 285)

    def test_pilot_is_exactly_the_79_regional_ramps(self):
        want = {r["id"] for r in RECORDS if r["a"] in REGIONAL}
        self.assertEqual(len(want), 79)
        self.assertEqual({e["id"] for e in DATA["sites"] if e["pilot"]}, want)

    def test_pilot_ramps_are_all_reviewed_and_the_rest_are_not(self):
        for e in DATA["sites"]:
            if e["pilot"]:
                self.assertIn(e["review"]["status"], ("reviewed", "needs_followup"), e["id"])
                self.assertTrue(e["review"]["note"], e["id"])
            else:
                self.assertEqual(e["review"]["status"], "unreviewed", e["id"])

    def test_enums(self):
        for e in DATA["sites"]:
            self.assertIn(e["water_class"], B.WATER_CLASSES, e["id"])
            self.assertIn(e["tide_policy"], B.TIDE_POLICIES, e["id"])
            self.assertTrue(e["class_basis"] and e["tide_basis"], e["id"])
            for c in e["stations"]:
                self.assertIn(c["type"], B.TYPES, (e["id"], c))
                self.assertIn(c["relation"], B.RELATIONS, (e["id"], c))
                self.assertIn(c["status"], B.STATUSES, (e["id"], c))
                if c["status"] == "rejected":
                    self.assertTrue(c.get("reject_reason"), (e["id"], c["id"]))

    def test_built_file_matches_the_builder(self):
        inp = json.loads((ROOT / "stations/ramp_stations_inputs.json").read_text())
        rev = json.loads((ROOT / "stations/ramp_stations_review.json").read_text())
        self.assertEqual(B.build(RECORDS, inp, rev), DATA)


class Integrity(unittest.TestCase):
    def test_only_reviewed_entries_on_reviewed_pilot_ramps_are_publishable(self):
        for e, c in stations():
            ok = e["pilot"] and e["review"]["status"] == "reviewed" and c["status"] == "reviewed"
            self.assertEqual(c["publishable"], ok, (e["id"], c["id"], c["type"]))
        self.assertFalse(any(c["publishable"] for e, c in stations() if not e["pilot"]))
        self.assertTrue(all(e["nws_point"] is None or e["nws_point"]["status"] == "unreviewed" for e in DATA["sites"] if not e["pilot"]))

    def test_lake_elevation_is_same_waterbody_only(self):
        for e, c in stations("lake_elevation"):
            if c["status"] != "rejected":
                self.assertEqual(c["relation"], "same_waterbody", (e["id"], c["id"]))
                self.assertIn(e["water_class"], ("reservoir", "natural_lake"), (e["id"], c["id"]))

    def test_no_cross_dam_assignment_for_reservoir_elevation(self):
        for e, c in stations("lake_elevation"):
            if c["status"] != "rejected":
                self.assertNotRegex(c.get("name", ""), B.DAM_BELOW, (e["id"], c["id"]))
                self.assertNotEqual(c.get("found"), "nldi_upstream", (e["id"], c["id"]))  # inflow tributaries are never the lake
        beaver = {(c["id"], c["status"]) for c in SITES["parks-falls-beaverdam"]["stations"] if c["type"] == "lake_elevation"}
        self.assertIn(("02087182", "rejected"), beaver)   # Falls Lake pool is behind a different dam
        self.assertIn(("0208706575", "reviewed"), beaver)
        for k in ("baa-eno-river", "parks-falls-rolling-view"):
            st = {c["id"]: c for c in SITES[k]["stations"]}
            self.assertEqual(st["02085039"]["status"], "rejected")
            self.assertIn("Inflow", st["02085039"]["reject_reason"])

    def test_downstream_flow_is_its_own_reading_never_lake_local_or_release(self):
        for e, c in stations():
            if c["relation"] in ("downstream_river_flow", "dam_release_reported"):
                self.assertEqual(c["type"], c["relation"], (e["id"], c["id"]))
            if c["type"] in ("downstream_river_flow", "dam_release_reported"):
                self.assertEqual(c["relation"], c["type"], (e["id"], c["id"]))
            if c["type"] in ("lake_elevation", "river_stage_flow", "water_temp") and c["status"] != "rejected":
                self.assertNotRegex(c.get("name", ""), B.DAM_BELOW, (e["id"], c["id"]))
            # Only a dam operator's own reported outflow may be called a release; a USGS gauge never is.
            if c["type"] == "dam_release_reported":
                self.assertEqual(c["source"], "USACE", (e["id"], c["id"]))
            if c["source"] == "USGS":
                self.assertNotEqual(c["type"], "dam_release_reported", (e["id"], c["id"]))
                self.assertNotIn("dam release (reported", (c.get("note") or "").lower(), (e["id"], c["id"]))
        self.assertEqual(B.TYPE_LABELS["downstream_river_flow"], "River flow below the dam (measured)")
        hyco = [c for c in SITES["baa-hyco-afterbay"]["stations"] if c["id"] == "02077303"]
        self.assertTrue(hyco and all(c["type"] == "downstream_river_flow" for c in hyco))
        falls = {(c["id"], c["type"]) for c in SITES["parks-falls-rolling-view"]["stations"] if c["status"] == "reviewed"}
        self.assertIn(("02087183", "downstream_river_flow"), falls)

    def test_beaverdam_gauge_is_documented_reservoir_elevation(self):
        c = [c for c in SITES["parks-falls-beaverdam"]["stations"] if c["id"] == "0208706575" and c["type"] == "lake_elevation"][0]
        self.assertEqual(c["status"], "reviewed")
        self.assertEqual(c["datum"], "NAVD88")
        for s in ("62615", "reservoir water surface", "2.85 ft", "at the dam"):
            self.assertIn(s, c["note"])

    def test_no_tide_predictions_on_wind_driven_or_unresolved_water(self):
        for e in DATA["sites"]:
            pub = [c for c in e["stations"] if c["type"] == "tide_predictions" and c["status"] != "rejected"]
            if e["water_class"] != "tidal_lunar":
                self.assertEqual(pub, [], e["id"])  # not even a hidden lead on wind-driven, fresh or unresolved water
            elif e["tide_policy"] != "predictions":
                self.assertEqual([c for c in pub if c["status"] == "reviewed" or c["publishable"]], [], e["id"])
                self.assertTrue(all(c["relation"] == "related" for c in pub), e["id"])
            if e["water_class"] == "estuary_wind_driven":
                self.assertEqual(e["tide_policy"], "omit_wind_driven", e["id"])
            if e["tide_policy"] == "predictions":
                self.assertEqual(len(pub), 1, e["id"])
                self.assertEqual(pub[0]["relation"], "same_waterbody", e["id"])
        for k in ("baa-rodanthe", "baa-cedar-island", "baa-manns-harbor", "baa-oriental", "local-newbern-union-point"):
            self.assertEqual(SITES[k]["tide_policy"], "omit_wind_driven", k)

    def test_ocean_and_other_water_tide_stations_are_rejected(self):
        for k, sid in (("baa-avalon-beach", "8651605"), ("baa-surf-city", "8657419"), ("baa-newport", "8656467")):
            c = [c for c in SITES[k]["stations"] if c["id"] == sid][0]
            self.assertEqual(c["status"], "rejected", k)

    def test_candidates_stay_within_25_miles(self):
        for e, c in stations():
            if c["status"] != "rejected" and c.get("distance_mi") is not None:
                self.assertLessEqual(c["distance_mi"], 25.0, (e["id"], c["id"]))

    def test_no_readings_are_stored(self):
        text = (ROOT / "stations/ramp_stations.json").read_text()
        for bad in ('"value"', '"reading"', '"observed_at"', '"elevation_ft"', '"stage_ft"', '"temp_f"', '"wind_mph"', '"high_tide"'):
            self.assertNotIn(bad, text, bad)
        for e, c in stations():
            self.assertFalse(set(c) & {"value", "latest", "reading", "time"}, (e["id"], c["id"]))

    def test_regulation_links_are_official_and_follow_jurisdiction(self):
        for e in DATA["sites"]:
            r = e["regs"]
            self.assertIn(r["jurisdiction"], ("coastal", "inland", "joint", "unresolved"), e["id"])
            self.assertTrue(r["links"], e["id"])
            for l in r["links"] + [{"url": r["boundary_map"]}]:
                u = urlparse(l["url"])
                self.assertEqual(u.scheme, "https", e["id"])
                self.assertIn(u.hostname, B.OFFICIAL_DOMAINS, (e["id"], l["url"]))
            ag = sorted(l["agency"] for l in r["links"])
            want = {"coastal": ["NCDMF"], "inland": ["NCWRC"], "joint": ["NCDMF", "NCWRC"], "unresolved": ["NCDMF", "NCWRC"]}[r["jurisdiction"]]
            self.assertEqual(ag, want, e["id"])
            self.assertNotIn("summary", r)

    def test_operator_terms_are_recorded_with_evidence(self):
        ops = DATA["operators"]
        self.assertEqual(sorted(ops), ["cube", "dominion", "duke", "tva"])
        for k, o in ops.items():
            self.assertIn(o["verdict"], ("approved", "unavailable", "unavailable_pending"), k)
            self.assertTrue(o["clause"] and o["levels_url"] and o["reason"], k)
            self.assertNotEqual(o["verdict"], "approved", k)  # nothing approved yet, so nothing from an operator may be used
        for e, c in stations():
            self.assertIn(c["source"], ("USGS", "USACE", "NOAA CO-OPS"), (e["id"], c["id"]))


if __name__ == "__main__":
    unittest.main()
