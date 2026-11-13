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


if __name__ == "__main__":
    unittest.main()
