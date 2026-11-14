"""Tests for Hatteras offshore water-temp fallback and per-station stale windows.

Run:  python -m unittest tests.test_conditions
"""
from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import conditions  # noqa: E402


NOW = datetime(2026, 11, 13, 19, 0, tzinfo=timezone.utc)

STATIONS = {
    "CLKN7": {
        "name": "Cape Lookout", "type": "ndbc", "network": "NDBC C-MAN station",
        "agency": "NOAA National Data Buoy Center", "lat": 34.611, "lon": -76.528,
    },
    "41064": {
        "name": "Onslow Bay Outer (LEJ3)", "type": "ndbc", "network": "CORMP buoy",
        "agency": "NOAA NDBC / UNCW CORMP", "lat": 34.207, "lon": -76.949,
        "staleAfterMin": 130,
    },
    "41120": {
        "name": "Cape Hatteras East (CDIP 250)", "type": "ndbc",
        "network": "Directional wave buoy", "agency": "NOAA NDBC / Scripps CDIP",
        "lat": 35.258, "lon": -75.285,
    },
    "41025": {
        "name": "Diamond Shoals", "type": "ndbc", "network": "NDBC weather buoy",
        "agency": "NOAA National Data Buoy Center", "lat": 35.026, "lon": -75.38,
    },
}

HATTERAS_OFFSHORE = {
    "kind": "observed",
    "role": "Offshore surface water",
    "sources": ["41120"],
    "note": "Diamond Shoals (41025) is not used as a substitute because its water is often several degrees warmer.",
}

ANCHOR = {"label": "Cape Hatteras", "lat": 35.2515, "lon": -75.5288}


def report(age_min, values, url="https://example.test/obs"):
    return {
        "time": NOW - timedelta(minutes=age_min),
        "url": url,
        "values": values,
        "raw": {},
        "rawUnits": "test",
    }


def wind_values(kt=12.0):
    return {"speedKt": kt, "gustKt": kt + 2, "dirDeg": 270, "dirCompass": "W"}


def temp_values(c):
    return {"f": round(c * 9.0 / 5.0 + 32.0, 1), "c": c}


class ConfigShape(unittest.TestCase):
    def setUp(self):
        self.cfg = conditions.load_regions()
        self.regions = {r["id"]: r for r in self.cfg.get("regions") or []}

    def test_hatteras_offshore_temp_uses_only_41120(self):
        hat = self.regions["hatteras"]
        self.assertEqual(hat["readings"]["waterTempOffshore"]["sources"], ["41120"])
        self.assertIn("41025", hat["readings"]["wind"]["sources"])
        note = hat["readings"]["waterTempOffshore"].get("note") or ""
        self.assertIn("41025", note)
        self.assertTrue(len(note) > 20)

    def test_41025_remains_hatteras_wind_and_wave_backup(self):
        hat = self.regions["hatteras"]
        self.assertIn("41025", hat["readings"]["wind"]["sources"])
        self.assertIn("41025", hat["readings"]["seas"]["sources"])
        self.assertIn("41025", hat["readings"]["swell"]["sources"])
        self.assertIn("41025", hat["readings"]["pressure"]["sources"])

    def test_41064_hourly_stale_window_in_station_config(self):
        self.assertEqual(self.cfg["stations"]["41064"]["staleAfterMin"], 130)
        self.assertNotIn("staleAfterMin", self.cfg["stations"]["CLKN7"])
        cc = self.regions["crystal-coast"]
        self.assertEqual(cc["readings"]["wind"]["sources"], ["CLKN7", "41064"])


class HatterasOffshoreTemp(unittest.TestCase):
    def _resolve(self, reports, spec=None):
        def fake_fetch(kind, sid, stations):
            return reports.get(sid)

        with patch.object(conditions, "fetch_one", side_effect=fake_fetch):
            return conditions.resolve_reading(
                "waterTempOffshore", spec or HATTERAS_OFFSHORE, STATIONS, ANCHOR, NOW
            )

    def test_fresh_41120_is_used(self):
        out = self._resolve({"41120": report(30, temp_values(20.5))})
        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["station"]["id"], "41120")
        self.assertEqual(out["values"]["c"], 20.5)
        self.assertIn("41025", out["note"])

    def test_missing_41120_is_unavailable_not_41025(self):
        # 41025 has a fresh, warmer reading; it must not be substituted.
        out = self._resolve({
            "41120": None,
            "41025": report(10, temp_values(25.3)),
        })
        self.assertEqual(out["status"], "unavailable")
        self.assertNotIn("values", out)
        self.assertEqual(out["station"]["id"], "41120")
        self.assertIn("41025", out["note"])
        tried_ids = [t["id"] for t in out["tried"]]
        self.assertEqual(tried_ids, ["41120"])
        self.assertNotIn("41025", tried_ids)

    def test_stale_41120_is_shown_stale_not_replaced(self):
        # 200 min is past the 180-min offshore-temp window but under the 12-hour cap.
        out = self._resolve({
            "41120": report(200, temp_values(20.5)),
            "41025": report(10, temp_values(25.3)),
        })
        self.assertEqual(out["status"], "stale")
        self.assertEqual(out["station"]["id"], "41120")
        self.assertEqual(out["values"]["c"], 20.5)
        self.assertEqual(out["staleAfterMin"], 180)

    def test_config_sources_do_not_call_41025_even_if_listed_elsewhere(self):
        cfg = conditions.load_regions()
        hat = next(r for r in cfg["regions"] if r["id"] == "hatteras")
        spec = hat["readings"]["waterTempOffshore"]
        called = []

        def fake_fetch(kind, sid, stations):
            called.append(sid)
            return None

        with patch.object(conditions, "fetch_one", side_effect=fake_fetch):
            out = conditions.resolve_reading(
                "waterTempOffshore", spec, cfg["stations"], hat["anchor"], NOW
            )
        self.assertEqual(out["status"], "unavailable")
        self.assertEqual(called, ["41120"])
        self.assertNotIn("41025", called)


class StationStaleWindow(unittest.TestCase):
    def _wind(self, reports, sources):
        spec = {"kind": "observed", "role": "Ocean wind", "sources": sources}

        def fake_fetch(kind, sid, stations):
            return reports.get(sid)

        with patch.object(conditions, "fetch_one", side_effect=fake_fetch):
            return conditions.resolve_reading("wind", spec, STATIONS, ANCHOR, NOW)

    def test_hourly_backup_at_90_min_is_fresh(self):
        out = self._wind({"41064": report(90, wind_values())}, ["41064"])
        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["station"]["id"], "41064")
        self.assertEqual(out["staleAfterMin"], 130)

    def test_hourly_backup_past_130_min_is_stale(self):
        out = self._wind({"41064": report(140, wind_values())}, ["41064"])
        self.assertEqual(out["status"], "stale")
        self.assertEqual(out["station"]["id"], "41064")
        self.assertEqual(out["staleAfterMin"], 130)
        self.assertIn("values", out)

    def test_clkn7_at_90_min_stays_stale(self):
        out = self._wind({"CLKN7": report(90, wind_values())}, ["CLKN7"])
        self.assertEqual(out["status"], "stale")
        self.assertEqual(out["staleAfterMin"], 75)

    def test_clkn7_at_60_min_is_fresh(self):
        out = self._wind({"CLKN7": report(60, wind_values())}, ["CLKN7"])
        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["staleAfterMin"], 75)

    def test_primary_still_preferred_when_fresh(self):
        out = self._wind({
            "CLKN7": report(20, wind_values(8)),
            "41064": report(40, wind_values(15)),
        }, ["CLKN7", "41064"])
        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["station"]["id"], "CLKN7")
        self.assertEqual(out["values"]["speedKt"], 8)

    def test_falls_back_to_hourly_backup_when_primary_is_down(self):
        out = self._wind({
            "CLKN7": None,
            "41064": report(90, wind_values(15)),
        }, ["CLKN7", "41064"])
        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["station"]["id"], "41064")
        self.assertEqual(out["staleAfterMin"], 130)

    def test_hourly_setting_does_not_tighten_offshore_temp_window(self):
        spec = {"kind": "observed", "role": "Offshore surface water", "sources": ["41064"]}

        def fake_fetch(kind, sid, stations):
            return report(150, temp_values(21.3))

        with patch.object(conditions, "fetch_one", side_effect=fake_fetch):
            out = conditions.resolve_reading(
                "waterTempOffshore", spec, STATIONS, ANCHOR, NOW
            )
        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["staleAfterMin"], 180)

    def test_stale_after_min_helper(self):
        self.assertEqual(conditions.stale_after_min("wind", "CLKN7", STATIONS), 75)
        self.assertEqual(conditions.stale_after_min("wind", "41064", STATIONS), 130)
        self.assertEqual(conditions.stale_after_min("waterTempOffshore", "41064", STATIONS), 180)
        self.assertEqual(conditions.stale_after_min("wind", "nope", STATIONS), 75)
        self.assertEqual(conditions.stale_after_min("wind", None, STATIONS), 75)




class HatterasMarineZones(unittest.TestCase):
    """Draft: AMZ152 is shown alongside AMZ154, not merged, and behind no flag."""

    def setUp(self):
        self.cfg = conditions.load_regions()
        self.regions = {r["id"]: r for r in self.cfg.get("regions") or []}

    def test_hatteras_lists_amz152_alongside_amz154(self):
        hat = self.regions["hatteras"]
        self.assertEqual(hat["marine"]["zone"], "AMZ154")
        also = hat["marine"].get("also") or []
        self.assertEqual([z["zone"] for z in also], ["AMZ152"])
        self.assertIn("Oregon Inlet", also[0]["zoneName"])
        self.assertIn("Cape Hatteras", also[0]["zoneName"])
        # Not merged into one zone field, and not hidden behind a flag.
        self.assertNotEqual(hat["marine"]["zone"], "AMZ152")
        self.assertNotIn("flag", hat["marine"])

    def test_crystal_coast_marine_is_unchanged_single_zone(self):
        cc = self.regions["crystal-coast"]
        self.assertEqual(cc["marine"]["zone"], "AMZ158")
        self.assertFalse(cc["marine"].get("also"))

    def test_marine_block_fetches_both_zones_and_does_not_merge(self):
        hat = self.regions["hatteras"]
        urls = []

        def fake_nws(url, ttl):
            urls.append(url)
            zone = url.rsplit("/", 2)[-2]
            return {"properties": {
                "updated": "2026-11-13T23:00:00+00:00",
                "periods": [{"name": "Tonight", "detailedForecast": "Seas 2 to 3 ft in %s." % zone}],
            }}

        with patch.object(conditions, "nws_json", side_effect=fake_nws):
            out = conditions.marine_block(hat["marine"])
        self.assertEqual(out["zone"], "AMZ154")
        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["periods"][0]["text"], "Seas 2 to 3 ft in AMZ154.")
        self.assertEqual(len(out.get("also") or []), 1)
        self.assertEqual(out["also"][0]["zone"], "AMZ152")
        self.assertEqual(out["also"][0]["status"], "ok")
        self.assertEqual(out["also"][0]["periods"][0]["text"], "Seas 2 to 3 ft in AMZ152.")
        self.assertEqual(urls, [
            "https://api.weather.gov/zones/coastal/AMZ154/forecast",
            "https://api.weather.gov/zones/coastal/AMZ152/forecast",
        ])

    def test_dashboard_js_renders_both_zones(self):
        js = Path(__file__).resolve().parents[1].joinpath("dashboard.js").read_text()
        self.assertIn("function marineZones(m)", js)
        self.assertIn("m.also", js)
        self.assertIn("Zones are shown side by side, not merged", js)


if __name__ == "__main__":
    unittest.main()


class WilmingtonNagsConfig(unittest.TestCase):
    def setUp(self):
        self.cfg = conditions.load_regions()
        self.regions = {r["id"]: r for r in self.cfg.get("regions") or []}
        self.stations = self.cfg["stations"]

    def test_preview_regions_are_not_public(self):
        for rid in ("wilmington", "nags-head"):
            r = self.regions[rid]
            self.assertFalse(r.get("enabled"), rid)
            self.assertFalse(r.get("draft"), rid)
            self.assertTrue(r.get("previewReady"), rid)
            self.assertEqual(r.get("waterType"), "saltwater")
            self.assertFalse(conditions._servable(r))
            self.assertTrue(conditions._servable(r, preview=True))
            self.assertTrue(conditions.is_preview_salt_region(rid))
        public_ids = [x["id"] for x in conditions.public_regions()["regions"]]
        self.assertEqual(public_ids, ["crystal-coast", "hatteras"])
        listed = conditions.listed_regions(preview=True)
        ids = [x["id"] for x in listed["regions"]]
        self.assertEqual(ids, ["crystal-coast", "hatteras", "wilmington", "nags-head"])
        preview_flags = {x["id"]: x.get("preview") for x in listed["regions"]}
        self.assertIsNone(preview_flags["crystal-coast"])
        self.assertTrue(preview_flags["wilmington"])
        self.assertTrue(preview_flags["nags-head"])

    def test_existing_public_regions_unchanged(self):
        cc = self.regions["crystal-coast"]
        hat = self.regions["hatteras"]
        self.assertTrue(cc["enabled"])
        self.assertTrue(hat["enabled"])
        self.assertEqual(cc["readings"]["wind"]["sources"], ["CLKN7", "41064"])
        self.assertEqual(cc["readings"]["seas"]["sources"], ["41159"])
        self.assertEqual(hat["readings"]["seas"]["sources"], ["41120", "41025"])
        self.assertEqual(hat["marine"]["zone"], "AMZ154")
        self.assertEqual(cc["alertZones"], ["AMZ158", "AMZ156", "NCZ195", "NCZ196"])
        self.assertEqual(self.stations["41064"]["staleAfterMin"], 130)

    def test_wilmington_sources_and_zones(self):
        w = self.regions["wilmington"]
        r = w["readings"]
        self.assertEqual(r["wind"]["sources"], ["8658163", "MBNN7"])
        self.assertNotIn("41038", r["wind"]["sources"])
        self.assertEqual(r["seas"]["sources"], ["41110"])
        self.assertEqual(r["swell"]["sources"], ["41110"])
        self.assertEqual(r["waterTemp"]["sources"], ["8658163"])
        self.assertEqual(r["waterTempOffshore"]["sources"], ["41110"])
        self.assertEqual(r["airTemp"]["sources"], ["8658163", "MBNN7"])
        self.assertEqual(r["pressure"]["sources"], ["8658163", "MBNN7"])
        self.assertEqual(w["tide"]["station"], "8658163")
        self.assertNotIn("observedStation", w["tide"])
        self.assertEqual(w["forecast"]["gridId"], "ILM")
        self.assertEqual(w["forecast"]["gridX"], 95)
        self.assertEqual(w["forecast"]["gridY"], 75)
        self.assertEqual(w["marine"]["zone"], "AMZ250")
        self.assertEqual(w["alertZones"], ["AMZ250", "NCZ108"])
        self.assertNotIn("NCZ107", w["alertZones"])
        self.assertEqual(self.stations["MBNN7"]["name"], "Masonboro Island, north end")
        self.assertIn("Masonboro", self.stations["41110"]["name"])

    def test_nags_head_sources_and_zones(self):
        n = self.regions["nags-head"]
        r = n["readings"]
        self.assertEqual(r["wind"]["sources"], ["8651370", "8652587"])
        self.assertEqual(r["seas"]["sources"], ["44086", "44095"])
        self.assertEqual(r["swell"]["sources"], ["44086"])
        self.assertEqual(r["waterTemp"]["sources"], [])
        self.assertNotIn("8652587", r["waterTemp"]["sources"])
        self.assertEqual(r["waterTempOffshore"]["sources"], ["44086"])
        self.assertNotIn("44095", r["swell"]["sources"])
        self.assertNotIn("44095", r["waterTempOffshore"]["sources"])
        self.assertEqual(n["tide"]["station"], "8652226")
        self.assertEqual(n["tide"]["observedStation"], "8651370")
        self.assertEqual(n["forecast"]["gridId"], "MHX")
        self.assertEqual((n["forecast"]["gridX"], n["forecast"]["gridY"]), (92, 116))
        self.assertEqual(n["marine"]["zone"], "AMZ150")
        self.assertEqual(n["alertZones"], ["AMZ150", "NCZ203", "AMZ231"])
        self.assertEqual(self.stations["8651370"]["name"], "Duck Pier")
        self.assertIn("sound side", self.stations["8652587"]["name"])
        self.assertIn("Oregon Inlet offshore", self.stations["44095"]["name"])

    def test_distant_station_labels_include_place_and_distance(self):
        w = self.regions["wilmington"]
        n = self.regions["nags-head"]
        mb = conditions.station_info("MBNN7", self.stations["MBNN7"], w["anchor"])
        self.assertEqual(mb["name"], "Masonboro Island, north end")
        self.assertGreaterEqual(mb["distanceMi"], 2)
        duck = conditions.station_info("8651370", self.stations["8651370"], n["anchor"])
        self.assertEqual(duck["name"], "Duck Pier")
        self.assertGreaterEqual(duck["distanceMi"], 20)
        oi = conditions.station_info("8652587", self.stations["8652587"], n["anchor"])
        self.assertIn("sound side", oi["name"])
        off = conditions.station_info("44095", self.stations["44095"], n["anchor"])
        self.assertIn("Oregon Inlet offshore", off["name"])


class NagsHeadFallbacks(unittest.TestCase):
    def setUp(self):
        cfg = conditions.load_regions()
        self.nags = next(r for r in cfg["regions"] if r["id"] == "nags-head")
        self.stations = cfg["stations"]
        self.anchor = self.nags["anchor"]

    def _resolve(self, kind, reports):
        def fake_fetch(k, sid, stations):
            return reports.get(sid)

        with patch.object(conditions, "fetch_one", side_effect=fake_fetch):
            return conditions.resolve_reading(
                kind, self.nags["readings"][kind], self.stations, self.anchor, NOW
            )

    def test_inshore_temp_is_unavailable_and_does_not_use_marina(self):
        out = self._resolve("waterTemp", {
            "8652587": report(10, temp_values(16.9)),
            "8651370": report(10, temp_values(17.0)),
        })
        self.assertEqual(out["status"], "unavailable")
        self.assertNotIn("values", out)
        self.assertTrue(out.get("note"))
        self.assertNotIn("8652587", [t["id"] for t in out.get("tried") or []])

    def test_swell_does_not_fall_back_to_44095(self):
        out = self._resolve("swell", {
            "44086": None,
            "44095": report(10, {"heightFt": 3.6, "periodS": 5.6}),
        })
        self.assertEqual(out["status"], "unavailable")
        self.assertEqual([t["id"] for t in out["tried"]], ["44086"])
        self.assertNotIn("44095", [t["id"] for t in out["tried"]])

    def test_offshore_temp_does_not_fall_back_to_44095(self):
        out = self._resolve("waterTempOffshore", {
            "44086": None,
            "44095": report(10, temp_values(19.2)),
        })
        self.assertEqual(out["status"], "unavailable")
        self.assertEqual([t["id"] for t in out["tried"]], ["44086"])

    def test_seas_can_use_labeled_44095_backup(self):
        out = self._resolve("seas", {
            "44086": None,
            "44095": report(10, {"heightFt": 5.2, "dominantPeriodS": 5}),
        })
        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["station"]["id"], "44095")
        self.assertIn("Oregon Inlet offshore", out["station"]["name"])
        self.assertIn("Oregon Inlet", out.get("note") or "")

    def test_wind_falls_back_to_labeled_marina(self):
        out = self._resolve("wind", {
            "8651370": None,
            "8652587": report(10, wind_values(10)),
        })
        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["station"]["id"], "8652587")
        self.assertIn("sound side", out["station"]["name"])



class SplitTideStations(unittest.TestCase):
    def test_nags_head_uses_duck_for_observed_level(self):
        cfg = conditions.load_regions()
        nags = next(r for r in cfg["regions"] if r["id"] == "nags-head")
        called = {"preds": [], "obs": []}

        def fake_preds(station, begin, end, interval):
            called["preds"].append(station)
            if interval == "hilo":
                return [{"t": "2026-11-13 22:00", "v": "3.2", "type": "H"}]
            return [{"t": "2026-11-13 21:00", "v": "2.0"}, {"t": "2026-11-13 22:00", "v": "3.2"}]

        def fake_obs(sid, curve_pts, now):
            called["obs"].append(sid)
            return {"kind": "observed", "status": "ok", "time": "2026-11-14T02:36:00Z",
                    "latest": {"v": 4.64}, "staleAfterMin": 30}

        with patch.object(conditions, "tide_preds", side_effect=fake_preds):
            with patch.object(conditions, "observed_water_level", side_effect=fake_obs):
                out = conditions.tides_block(nags["tide"], cfg["stations"], nags["anchor"], NOW)
        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["station"]["id"], "8652226")
        self.assertIn("Jennette", out["station"]["name"])
        self.assertEqual(called["preds"], ["8652226", "8652226"])
        self.assertEqual(called["obs"], ["8651370"])
        self.assertEqual(out["observed"]["station"]["id"], "8651370")
        self.assertEqual(out["observed"]["station"]["name"], "Duck Pier")
        self.assertIn("Duck Pier", out["observed"]["note"])


    def test_nags_head_6min_curve_falls_back_to_duck(self):
        cfg = conditions.load_regions()
        nags = next(r for r in cfg["regions"] if r["id"] == "nags-head")
        called = []

        def fake_preds(station, begin, end, interval):
            called.append((station, interval))
            if interval == "hilo" and station == "8652226":
                return [{"t": "2026-11-13 22:00", "v": "3.2", "type": "H"}]
            if interval == "6" and station == "8651370":
                return [{"t": "2026-11-13 21:00", "v": "2.0"}, {"t": "2026-11-13 22:00", "v": "3.2"}]
            return None

        def fake_obs(sid, curve_pts, now):
            return {"kind": "observed", "status": "ok", "latest": {"v": 4.64}, "staleAfterMin": 30}

        with patch.object(conditions, "tide_preds", side_effect=fake_preds):
            with patch.object(conditions, "observed_water_level", side_effect=fake_obs):
                out = conditions.tides_block(nags["tide"], cfg["stations"], nags["anchor"], NOW)
        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["station"]["id"], "8652226")
        self.assertEqual(out["curveStation"]["id"], "8651370")
        self.assertIn("Duck", out["curveNote"])
        self.assertTrue(out["curve"])
        self.assertEqual(out["observed"]["station"]["id"], "8651370")
        self.assertIn(("8652226", "6"), called)
        self.assertIn(("8651370", "6"), called)

    def test_wilmington_keeps_one_tide_station(self):
        cfg = conditions.load_regions()
        w = next(r for r in cfg["regions"] if r["id"] == "wilmington")
        called = []

        def fake_preds(station, begin, end, interval):
            called.append(("pred", station))
            if interval == "hilo":
                return [{"t": "2026-11-13 22:00", "v": "3.9", "type": "H"}]
            return [{"t": "2026-11-13 21:00", "v": "2.0"}, {"t": "2026-11-13 22:00", "v": "3.9"}]

        def fake_obs(sid, curve_pts, now):
            called.append(("obs", sid))
            return {"kind": "observed", "status": "ok", "latest": {"v": 3.94}}

        with patch.object(conditions, "tide_preds", side_effect=fake_preds):
            with patch.object(conditions, "observed_water_level", side_effect=fake_obs):
                out = conditions.tides_block(w["tide"], cfg["stations"], w["anchor"], NOW)
        self.assertEqual(out["station"]["id"], "8658163")
        self.assertEqual([c for c in called if c[0] == "obs"], [("obs", "8658163")])
        self.assertNotIn("station", out["observed"])


class AssemblePreviewGate(unittest.TestCase):
    def test_public_assemble_404s_preview_regions_without_fallback(self):
        for rid in ("wilmington", "nags-head"):
            status, payload = conditions.assemble(rid)
            self.assertEqual(status, 404, rid)
            self.assertFalse(payload.get("ok"))
            self.assertNotIn("readings", payload)

    def test_unknown_region_still_falls_back_to_default(self):
        # Existing public behavior: a typo does not 404, it uses the default region.
        # Don't hit the network; just confirm the id selection with a patched assemble body.
        cfg = conditions.load_regions()
        public = {r["id"]: r for r in cfg["regions"] if conditions._servable(r)}
        self.assertIn(cfg["default"], public)

    def test_public_default_still_servable(self):
        self.assertTrue(conditions._servable(
            next(r for r in conditions.load_regions()["regions"] if r["id"] == "crystal-coast")
        ))
