"""Phase 3C Before You Launch (private): reviewed coastal instruments, datums, charts, shared caches,
last-known-good, reserved slot heights and the preview hub."""
import json
import re
import unittest
import html as html_lib
from datetime import datetime, timedelta
from pathlib import Path

import byl_data as B
import byl_page as P
from test_byl import CEDAR, FALLS, NOW, RECS, SITES, UNION, fake, run, usgs_payload

ROOT = Path(__file__).resolve().parents[1]
REVIEW = json.loads((ROOT / "stations/byl_coastal_review.json").read_text())
CZ = {x["id"]: x for x in REVIEW["sites"]}
WB = "baa-west-beaufort"
CITIZEN = re.compile(r"^(?:[A-E]\d{4}|APRS|AR\d|AT\d|AU\d|AV\d|AX\d|COOP)")


class CoastalReview(unittest.TestCase):
    def test_covers_exactly_the_coastal_pilot_ramps(self):
        coastal = {s for s, e in SITES.items() if e["water_class"] not in B.FRESH_CLASSES}
        self.assertEqual(set(CZ), coastal)
        self.assertEqual(len(coastal), 49)

    def test_every_candidate_has_a_recorded_decision(self):
        for x in REVIEW["sites"]:
            for w in x["wind"] + x["water"]:
                self.assertIn(w["decision"], ("accepted", "rejected"))
                self.assertTrue(w["reason"])
            self.assertIn((x["marine_zone"] or {"decision": "none"})["decision"], ("accepted", "none", "error"))

    def test_wind_rules(self):
        for x in REVIEW["sites"]:
            acc = B.accepted(x["wind"])
            self.assertLessEqual(len(acc), 1)
            for w in acc:
                self.assertIn(w["source"], ("NOAA CO-OPS", "NWS ASOS"))
                self.assertLessEqual(w["distance_mi"], 8.0)
                self.assertEqual(w["label"], "Related station")
                self.assertFalse(CITIZEN.match(w["id"]), w["id"])
                if w["exposure"] == "ocean_pier":
                    self.assertIn("Ocean pier", w["reason"])

    def test_water_rules(self):
        for x in REVIEW["sites"]:
            for w in B.accepted(x["water"]):
                self.assertLessEqual(w["distance_mi"], 3.0)
                self.assertNotEqual(w["exposure"], "ocean_pier")
                self.assertNotEqual(x["water_class"], "unresolved")
                if w["type"] == "water_level":
                    self.assertEqual(w["datum"], "MLLW")

    def test_marine_zone_rules(self):
        for x in REVIEW["sites"]:
            z = x["marine_zone"] or {}
            if z.get("decision") != "accepted":
                continue
            if "NM" in z["name"] or "nm" in z["name"]:
                self.assertEqual(z["kind"], "ocean_beyond_inlet")
                self.assertIn("not for the sound", z["reason"])
            else:
                self.assertEqual(z["kind"], "sound_river")
                self.assertLessEqual(z["distance_km"], 1.5)
        self.assertEqual(CZ[UNION]["marine_zone"]["id"], "AMZ137")

    def test_review_file_holds_no_readings(self):
        txt = json.dumps(REVIEW)
        for k in ('"value"', '"mph"', '"kt"', '"v":', '"temperature"'):
            self.assertNotIn(k, txt)

    def test_review_file_is_not_served(self):
        import server
        for p in ("/stations/byl_coastal_review.json", "/scripts/review_byl_coastal.py"):
            self.assertFalse(server._static_allowed(p), p)
        self.assertFalse(list((ROOT / "data").glob("byl_*")))  # nothing under the served /data/ folder

    def test_charts_are_official_noaa(self):
        for x in REVIEW["sites"]:
            if x["chart"]:
                self.assertRegex(x["chart"]["url"], r"^https://www\.charts\.noaa\.gov/OnLineViewer/\d{5}\.shtml$")


class Instruments(unittest.TestCase):
    def test_no_tide_curve_on_wind_driven_water(self):
        d, calls = run(UNION)
        html = P.render(UNION, SITES, RECS) + json.dumps(P.fragments(d))
        self.assertNotIn("a-pred", html)
        self.assertNotIn("Tide predictions", html)
        self.assertFalse([u for u in calls if "product=predictions" in u])

    def test_tide_curve_from_noaa_predictions(self):
        d, _ = run(CEDAR)
        t = d["cards"]["tide"]
        self.assertTrue(t["curve"]["pts"])
        self.assertEqual(t["curve"]["interval_min"], 6)
        self.assertNotIn("interpolated", t["curve"])
        h = P.card_html(t)
        self.assertIn("a-pred", h); self.assertIn("MLLW", h); self.assertIn("6-minute", h)

    def test_curve_uses_six_minute_predictions_only(self):
        d, calls = run(CEDAR)
        pred = [u for u in calls if "product=predictions" in u and "interval=hilo" not in u]
        self.assertTrue(pred)
        self.assertTrue(all("interval=6&" in u for u in pred), pred)
        # every plotted point is a NOAA point: 6-minute spacing, nothing added in between
        ts = [datetime.fromisoformat(t) for t, _ in d["cards"]["tide"]["curve"]["pts"]]
        self.assertTrue(all((b - a).total_seconds() == 360 for a, b in zip(ts, ts[1:])))

    def test_subordinate_station_gets_high_low_schedule_not_a_curve(self):
        f, _ = fake()
        orig = f.opener

        def op(url, t):
            if "interval=6&" in url:
                return json.dumps({"error": {"message": "No Predictions data was found."}}).encode()
            if "interval=hilo" in url:
                base = NOW.astimezone(B.ET)
                return json.dumps({"predictions": [{"t": (base + timedelta(hours=h)).strftime("%Y-%m-%d %H:%M"), "type": "H" if h % 12 == 0 else "L",
                                                    "v": "2.0" if h % 12 == 0 else "0.1"} for h in range(-30, 31, 6)]}).encode()
            return orig(url, t)
        f.opener = op
        d = B.assemble(CEDAR, f=f, now=NOW, sites=SITES, records=RECS)
        t = d["cards"]["tide"]
        self.assertIsNone(t["curve"])
        h = P.card_html(t)
        self.assertNotIn("l-pred", h); self.assertNotIn("a-pred", h)  # no manufactured curve
        self.assertIn('class="b-hi"', h); self.assertIn('class="b-lo"', h)
        self.assertIn("official high and low predictions only", h)
        self.assertIn("MLLW", h)
        # readout carries only the official events
        rows = json.loads(html_lib.unescape(re.search(r'data-scrub="([^"]+)"', h).group(1)))
        self.assertTrue(rows and all(r[1].startswith(("High", "Low")) for r in rows))

    def test_datums_and_discharge_are_labelled(self):
        d, _ = run(FALLS)
        lake = d["cards"]["lake"]
        self.assertEqual(lake["datum"], "NGVD29")
        self.assertIn("not water depth", lake["note"])
        self.assertIn("NGVD29", P.card_html(lake))
        self.assertEqual(lake["guide"], 251.5)
        bd = d["cards"]["below_dam"]
        self.assertEqual(bd["unit"], "cfs"); self.assertIn("Measured discharge", bd["note"])
        d, _ = run(WB)
        wl = d["cards"]["water_level"]
        self.assertEqual(wl["datum"], "MLLW"); self.assertIn("not water depth", wl["note"])

    def test_beaverdam_is_navd88_without_falls_guide(self):
        d, _ = run("parks-falls-beaverdam") if "parks-falls-beaverdam" in SITES else (None, None)
        sid = next(s for s in SITES if any(c["id"] == "0208706575" and c["publishable"] for c in SITES[s]["stations"]))
        f, _ = fake()
        orig = f.opener
        f.opener = lambda u, t: json.dumps(usgs_payload(0.5, ids=["0208706575"])).encode().replace(b'"62614"', b'"62615"') if "usgs" in u else orig(u, t)
        d = B.assemble(sid, f=f, now=NOW, sites=SITES, records=RECS)
        lake = d["cards"]["lake"]
        self.assertEqual(lake.get("datum"), "NAVD88")
        self.assertIsNone(lake.get("guide"))

    def test_lake_chart_when_history_available(self):
        f, _ = fake()
        d = B.assemble(FALLS, f=f, now=NOW, sites=SITES, records=RECS)
        if d["cards"]["lake"].get("hist"):
            self.assertIn("14 days", P.card_html(d["cards"]["lake"]))
        else:
            self.assertIn("chart-ph", P.card_html(d["cards"]["lake"]))

    def test_wind_observed_is_related_station(self):
        d, _ = run(UNION)
        w = d["cards"]["wind_obs"]
        self.assertEqual(w["kind"], "rel")
        self.assertEqual(w["dir"], "WSW")
        self.assertIn("not at the ramp", w["note"])

    def test_wind_too_old_hidden_and_stale_labelled(self):
        self.assertEqual(run(UNION, obs_age=2)[0]["cards"]["wind_obs"]["kind"], "stale")
        c = run(UNION, obs_age=4)[0]["cards"]["wind_obs"]
        self.assertEqual(c["kind"], "unav"); self.assertNotIn("mph", c)

    def test_marine_ocean_zone_is_labelled_beyond_inlet(self):
        d, _ = run(CEDAR)
        h = P.card_html(d["cards"]["marine"])
        self.assertIn("Not a forecast for the sound", h)

    def test_marine_old_forecast_hidden(self):
        c = run(UNION, marine_issued="1112 AM EST Thu Nov 26 2026")[0]["cards"]["marine"]
        self.assertEqual(c["kind"], "unav")

    def test_no_marine_or_charts_on_freshwater(self):
        for sid, e in SITES.items():
            if e["water_class"] in B.FRESH_CLASSES:
                d, calls = run(sid)
                self.assertNotIn("marine", d["cards"])
                self.assertNotIn("Nautical charts", P.render(sid, SITES, RECS))
                self.assertFalse([u for u in calls if "tgftp" in u])

    def test_charts_gateway_on_coastal_pages(self):
        for sid in (CEDAR, UNION):
            h = P.render(sid, SITES, RECS)
            self.assertIn("Nautical charts", h)
            # NOAA has sunset raster charts: link only the current ENC products (HTTP-checked Nov 28, 2026)
            self.assertNotIn("OnLineViewer", h)
            self.assertIn('href="https://nauticalcharts.noaa.gov/enconline/enconline.html"', h)
            self.assertIn('href="https://www.charts.noaa.gov/InteractiveCatalog/nrnc.shtml"', h)
            self.assertIn("former NOAA chart", h)

    def test_below_dam_heading_only_where_relevant(self):
        self.assertIn("Below the dam", P.render(FALLS, SITES, RECS))
        for sid in (CEDAR, UNION):
            self.assertNotIn("Below the dam", P.render(sid, SITES, RECS))


class SharedCacheAndLkg(unittest.TestCase):
    def test_one_usgs_request_serves_many_pages(self):
        f, calls = fake()
        lakes = [s for s, e in SITES.items() if B.water_ok(e) and B.publishable(e, "lake_elevation", "river_stage_flow")][:8]
        self.assertGreaterEqual(len(lakes), 6)
        for sid in lakes:
            B.assemble(sid, f=f, now=NOW, sites=SITES, records=RECS)
        cur = [u for u in calls if "usgs" in u and "PT25H" in u]
        self.assertEqual(len(cur), 1)

    def test_shared_forecast_grid(self):
        f, calls = fake()
        by_grid = {}
        for sid, e in SITES.items():
            if e.get("nws_point"):
                by_grid.setdefault(e["nws_point"]["url"], []).append(sid)
        url, sids = max(by_grid.items(), key=lambda kv: len(kv[1]))
        self.assertGreater(len(sids), 1)
        for sid in sids[:4]:
            B.assemble(sid, f=f, now=NOW, sites=SITES, records=RECS)
        self.assertEqual(calls.count(url), 1)

    def test_last_known_good_within_window_only(self):
        t = [0.0]
        fail = {"on": False}

        def op(url, to):
            if fail["on"]:
                raise OSError
            return b'{"v":1}'
        f = B.Fetcher(opener=op, clock=lambda: t[0])
        f.get("usgs", "u")
        t[0] = B.SOURCES["usgs"]["ttl"] + 5
        fail["on"] = True
        self.assertEqual(f.get("usgs", "u"), {"v": 1})
        self.assertIn("u", f.lkg_used)
        t[0] = B.SOURCES["usgs"]["lkg"] + 10 ** 4
        with self.assertRaises(B.SourceDown):
            f.get("usgs", "u")

    def test_alerts_never_served_from_last_known_good(self):
        t = [0.0]
        fail = {"on": False}

        def op(url, to):
            if fail["on"]:
                raise OSError
            return b'{"features":[]}'
        f = B.Fetcher(opener=op, clock=lambda: t[0])
        f.get("nws_alerts", "a")
        t[0] = B.SOURCES["nws_alerts"]["ttl"] + 1
        fail["on"] = True
        with self.assertRaises(B.SourceDown):
            f.get("nws_alerts", "a")

    def test_last_known_good_keeps_observation_age_labels(self):
        clock = [1000.0]
        f, _ = fake(usgs_age=4)
        f.clock = lambda: clock[0]
        B.assemble(FALLS, f=f, now=NOW, sites=SITES, records=RECS)
        clock[0] += 10 ** 4
        orig = f.opener
        f.opener = lambda u, t: (_ for _ in ()).throw(OSError()) if "usgs" in u else orig(u, t)
        d = B.assemble(FALLS, f=f, now=NOW, sites=SITES, records=RECS)
        self.assertEqual(d["cards"]["lake"]["kind"], "stale")
        self.assertTrue(d["last_known_good"])


class LayoutStability(unittest.TestCase):
    def test_skeleton_and_loaded_cards_share_slot_class(self):
        for sid in (FALLS, CEDAR, UNION, WB):
            shell = P.render(sid, SITES, RECS)
            d, _ = run(sid)
            for key, frag in P.fragments(d).items():
                if key == "sun":
                    continue
                m = re.search(r'class="([^"]*)" data-card="%s"' % re.escape(key), shell)
                self.assertTrue(m, (sid, key))
                want = {c for c in m.group(1).split() if c.startswith("s-")}
                got = set(re.search(r'class="([^"]*)"', frag).group(1).split())
                self.assertTrue(want <= got, (sid, key, want, got))

    def test_css_reserves_every_slot(self):
        css = (ROOT / "preview/before-you-launch/byl.css").read_text()
        for cls in set(P.SLOT_H.values()) | {"s-spark", "s-marine-o"}:
            self.assertRegex(css, r"\.%s\{min-height:\d+px\}" % cls)


class GeographicAndInteractive(unittest.TestCase):
    def test_locator_uses_only_reviewed_stations(self):
        for sid, e in SITES.items():
            cz = CZ.get(sid) or {}
            allowed = {c["id"] for c in e["stations"] if c["publishable"]} | {x["id"] for x in B.accepted(cz.get("wind")) + B.accepted(cz.get("water"))}
            pts = P.locator_points(e, RECS[sid], cz)
            self.assertTrue({p[1] for p in pts} <= allowed, sid)
            if not B.water_ok(e):
                self.assertFalse([p for p in pts if p[0] in "GTN"], sid)
            if e["tide_policy"] != "predictions":
                self.assertFalse([p for p in pts if p[0] == "T"], sid)

    def test_locator_is_honest_without_coastline(self):
        # 3C.1: West Beaufort and Union Point now get the NOAA ENC shoreline; Dram Tree (upper Cape Fear)
        # lies outside the ENC coverage, so it still gets a plain frame and says why.
        dt = "baa-dram-tree-park"
        h = P.locator_svg(SITES[dt], RECS[dt], CZ[dt])
        self.assertIn("loc-plain", h); self.assertIn("Coastline not drawn", h); self.assertNotIn("loc-water\" d=\"M", h)
        h = P.locator_svg(SITES[UNION], RECS[UNION], CZ[UNION])
        self.assertIn("loc-enc", h); self.assertIn("not for navigation", h)

    def test_no_locator_without_coordinates(self):
        for sid, r in RECS.items():
            if sid in SITES and r.get("la") is None:
                self.assertEqual(P.locator_svg(SITES[sid], r, CZ.get(sid) or {}), "")

    def test_scrub_rows_are_the_plotted_values(self):
        d, _ = run(CEDAR)
        t = d["cards"]["tide"]
        h = P.card_html(t)
        rows = json.loads(__import__("html").unescape(re.search(r'data-scrub="([^"]+)"', h).group(1)))
        self.assertEqual(len(rows), len(t["curve"]["pts"]))
        self.assertTrue(all("MLLW" in r[1] for r in rows))
        js = (ROOT / "preview/before-you-launch/byl.js").read_text()
        self.assertIn("ArrowRight", js); self.assertIn("aria-live", js)


class Hub(unittest.TestCase):
    def test_hub_links_three_water_types_and_index(self):
        src = (ROOT / "server.py").read_text()
        for p in ("/preview/before-you-launch/parks-falls-rolling-view", "/preview/before-you-launch/baa-gordon-s-myers-at-cedar-point",
                  "/preview/before-you-launch/local-newbern-union-point", 'href="/preview/before-you-launch"'):
            self.assertIn(p, src)
        self.assertNotRegex(src, r"before-you-launch[^\"']*\?key=")


if __name__ == "__main__":
    unittest.main()


class Phase3C1(unittest.TestCase):
    """Phase 3C.1: ENC shoreline in coastal station maps, gaps left blank, hi/lo schedule values."""

    def test_coastal_maps_use_enc_shoreline_or_no_outline(self):
        for sid in (CEDAR, UNION, WB):
            h = P.locator_svg(SITES[sid], RECS[sid], P.coastal(sid))
            self.assertIn("loc-enc", h, sid)
            self.assertIn("NOAA ENC land areas", h)
            self.assertIn("not for navigation", h)
            self.assertNotIn("TIGER", h)  # inland layer would paint sounds as land

    def test_enc_not_used_outside_its_coverage(self):
        self.assertIsNone(P.enc_land(-79.0, 35.7, -78.9, 35.8))  # Falls Lake area: outside ENC cover
        land = P.enc_land(-76.72, 34.66, -76.62, 34.74)  # Beaufort harbour
        self.assertTrue(land)
        for r in land:
            self.assertTrue(all(-76.72 - 1e-9 <= x <= -76.62 + 1e-9 and 34.66 - 1e-9 <= y <= 34.74 + 1e-9 for x, y in r))

    def test_inland_maps_keep_tiger_water(self):
        h = P.locator_svg(SITES[FALLS], RECS[FALLS], {})
        self.assertIn("TIGER", h)
        self.assertNotIn("loc-enc", h)

    def test_gaps_are_not_bridged(self):
        pts = [("2026-11-27T10:00:00-05:00", 1.0), ("2026-11-27T10:15:00-05:00", 1.1),
               ("2026-11-27T15:00:00-05:00", 1.3), ("2026-11-27T15:15:00-05:00", 1.2)]
        h = P.spark_svg(pts, "Stage", "ft")
        line = re.search(r'class="l-obs" d="([^"]+)"', h).group(1)
        self.assertEqual(line.count("M"), 2)
        self.assertIn("gaps in the record are left blank", h)
        hist = [("2026-11-%02dT%02d:00:00-05:00" % (14 + i // 4, (i % 4) * 6), 245.0 + i / 100) for i in range(56) if not 20 <= i < 26]
        h = P.lake_svg(hist, 251.5, "NGVD29")
        self.assertEqual(re.search(r'class="l-obs" d="([^"]+)"', h).group(1).count("M"), 2)
        self.assertIn("gaps left blank", h)

    def test_no_negative_zero_tide_heights(self):
        f, _ = fake()
        orig = f.opener

        def op(url, t):
            if "interval=hilo" in url:
                base = NOW.astimezone(B.ET)
                return json.dumps({"predictions": [{"t": (base + timedelta(hours=h)).strftime("%Y-%m-%d %H:%M"), "type": "L", "v": "-0.04"} for h in (1, 13)]}).encode()
            return orig(url, t)
        f.opener = op
        c = B.coops_card({"id": "8656451", "name": "Gallant Channel", "relation": "same_waterbody"}, NOW, f)
        self.assertTrue(all(str(e["ft"]) == "0.0" for e in c["events"]))

    def test_guide_curve_values_match_usace_header(self):
        # USACE Wilmington District dsslake.txt header: "Guide Curve for Jordan is 216.0, Falls is 251.5 ... each day of the year"
        self.assertEqual(B.GUIDE, {"SAW-FALLS": 251.5, "SAW-JORDAN": 216.0})
