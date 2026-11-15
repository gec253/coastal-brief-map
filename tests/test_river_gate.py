"""Freshwater preview quality gate (Jordan Lake, Neuse River).

The gate lives in river_gate.py and is used only by the private previews.
brief.validate, coastal previews, and the public Falls Lake brief stay unchanged.
"""
from __future__ import annotations

import sys
import unittest
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import brief  # noqa: E402
import brief_preview  # noqa: E402
import preview_alerts  # noqa: E402
import river_gate  # noqa: E402

NOW = datetime(2026, 11, 15, 15, 0, tzinfo=timezone.utc)  # 10:00 AM ET


def _iso(hours_ago):
    return (NOW - timedelta(hours=hours_ago)).isoformat()


def _obs(value, hours_ago=0.7):
    return {"value": value, "time": _iso(hours_ago), "ageH": hours_ago, "stale": hours_ago > river_gate.USGS_FRESH_H}


def _flow_block(usgs, lid, label, stage, flow, hours_ago=0.7, forecast=None, nwps_status="ok"):
    nw = {"lid": lid, "status": nwps_status}
    if forecast:
        nw["forecast"] = forecast
    return {"usgs": usgs, "label": label, "kind": "observed", "regulated": True,
            "stageFt": _obs(stage, hours_ago) if stage is not None else None,
            "flowCfs": _obs(flow, hours_ago) if flow is not None else None,
            "nwps": nw}


def _forecast(hours_ago=3.0, lid_crest=1.4):
    return {"issued": _iso(hours_ago), "crestStage": lid_crest,
            "crestTime": _iso(-3), "category": "no_flooding"}


def _neuse(hours=0.7, forecast_h=3.0, drop=None, alerts="ok", nwps_status="ok"):
    """A passing Neuse payload, then optionally drop a gauge id or tweak freshness."""
    blocks = [
        _flow_block("02087183", "NEUN7", "Neuse River below Falls Dam", 0.94, 60.0, hours, nwps_status=nwps_status),
        _flow_block("02087500", "CLYN7", "Neuse River near Clayton", 1.19, 204.0, hours,
                    forecast=_forecast(forecast_h) if forecast_h is not None else None, nwps_status=nwps_status),
        {"usgs": "02087570", "label": "Neuse River at Smithfield", "kind": "observed", "regulated": True,
         "stageOnly": True, "flowCfs": None, "stageFt": _obs(4.30, hours),
         "flowNote": "USGS stopped publishing discharge here; stage only.",
         "nwps": {"lid": "SMFN7", "status": nwps_status,
                  "forecast": _forecast(forecast_h, 4.4) if forecast_h is not None and nwps_status == "ok" else None}},
        _flow_block("02089000", "GLDN7", "Neuse River near Goldsboro", 2.51, 262.0, hours, nwps_status=nwps_status),
    ]
    if drop:
        blocks = [b for b in blocks if b["usgs"] not in drop]
    return {
        "ok": True,
        "region": {"id": "neuse-river", "name": "Neuse River (Falls Dam to Goldsboro)"},
        "lake": None,
        "waterTemp": {"status": "unavailable", "note": "No active USGS water-temperature sensor on the Neuse main stem."},
        "rain": None,
        "release": None,
        "inflows": [],
        "river": blocks,
        "forecast": {"status": "ok", "updated": _iso(1.0), "periods": [
            {"name": "Today", "tempF": 57, "short": "Sunny", "windDir": "NW", "windMph": "2 to 6 mph"}]},
        "alerts": ({**preview_alerts.ok_coverage("neuse-river"), "status": alerts} if alerts == "ok" else {"status": alerts, "items": [], "coverage": []}),
    }


def _jordan(elev_h=0.6, rel_h=0.9, alerts="ok"):
    return {
        "ok": True,
        "region": {"id": "jordan-lake", "name": "Jordan Lake"},
        "lake": {"usgs": "02098197", "elevation": _obs(212.13, elev_h), "datum": "NGVD29",
                 "guideCurveFt": 216.0, "vsGuideFt": -3.87},
        "waterTemp": {"status": "unavailable", "note": "No USGS water-temperature sensor at Jordan Lake dam (02098197)."},
        "rain": {"status": "ok", "usgs": "02098197", "last24In": 0.0, "time": _iso(elev_h)},
        "release": {"usgs": "02098206", "label": "Haw River near Moncure (release plus local runoff)",
                    "flowCfs": _obs(287.0, rel_h), "stageFt": _obs(2.05, rel_h),
                    "note": "Dam release plus local runoff, not the official gate outflow."},
        "inflows": [{"usgs": "02096960", "label": "Haw River near Bynum (inflow above the lake)",
                     "flowCfs": _obs(77.4, rel_h)}],
        "river": [],
        "forecast": {"status": "ok", "updated": _iso(1.0), "periods": [
            {"name": "Today", "tempF": 57, "short": "Sunny", "windDir": "NW", "windMph": "2 to 7 mph"}]},
        "alerts": ({**preview_alerts.ok_coverage("jordan-lake"), "status": alerts} if alerts == "ok" else {"status": alerts, "items": [], "coverage": []}),
    }


def _by_id(gate, check_id):
    return next(c for c in gate["checks"] if c["id"] == check_id)


class Limits(unittest.TestCase):
    def test_limits_match_documented_rationale(self):
        self.assertEqual(river_gate.USGS_FRESH_H, 3.0)
        self.assertEqual(river_gate.USGS_REJECT_H, 24.0)
        self.assertEqual(river_gate.NWPS_FORECAST_FRESH_H, 18.0)
        self.assertIn("15-minute", river_gate.__doc__)
        self.assertIn("few times a", river_gate.__doc__)
        self.assertIn("02098206", river_gate.__doc__)


class NeuseGate(unittest.TestCase):
    def test_fresh_three_gauges_passes(self):
        g = river_gate.evaluate("neuse-river", _neuse(), NOW)
        self.assertTrue(g["ok"], g["errors"])
        self.assertEqual(_by_id(g, "neuse-core-gauges")["status"], "pass")
        self.assertEqual(_by_id(g, "nwps-forecast")["status"], "pass")
        self.assertEqual(_by_id(g, "alerts")["status"], "pass")
        self.assertEqual(_by_id(g, "water-temp")["status"], "n/a")
        self.assertEqual(_by_id(g, "rain")["status"], "n/a")
        self.assertEqual(_by_id(g, "flow-02087570")["status"], "n/a")
        self.assertIn("regulated", _by_id(g, "flow-02087500")["kind"])
        self.assertEqual(_by_id(g, "nwps-forecast")["kind"], "forecast")

    def test_two_of_three_gauges_passes(self):
        payload = _neuse()
        # Goldsboro missing entirely.
        payload["river"] = [b for b in payload["river"] if b["usgs"] != "02089000"]
        g = river_gate.evaluate("neuse-river", payload, NOW)
        self.assertTrue(g["ok"], g["errors"])
        self.assertIn("2 of 3", _by_id(g, "neuse-core-gauges")["reason"])

    def test_only_one_gauge_fails(self):
        payload = _neuse()
        payload["river"] = [b for b in payload["river"] if b["usgs"] in ("02087500", "02087570")]
        g = river_gate.evaluate("neuse-river", payload, NOW)
        self.assertFalse(g["ok"])
        self.assertTrue(any("Only 1 of 3" in e for e in g["errors"]), g["errors"])

    def test_stale_gauge_does_not_count(self):
        payload = _neuse()
        for b in payload["river"]:
            if b["usgs"] in ("02087183", "02089000"):
                if b.get("stageFt"):
                    b["stageFt"] = _obs(b["stageFt"]["value"], 4.0)
                if b.get("flowCfs"):
                    b["flowCfs"] = _obs(b["flowCfs"]["value"], 4.0)
        g = river_gate.evaluate("neuse-river", payload, NOW)
        self.assertFalse(g["ok"])
        self.assertEqual(_by_id(g, "stage-02087183")["status"], "stale")
        self.assertEqual(_by_id(g, "flow-02089000")["status"], "stale")
        self.assertTrue(any("Only 1 of 3" in e for e in g["errors"]), g["errors"])

    def test_rejected_old_point_is_missing_not_stale(self):
        payload = _neuse()
        for b in payload["river"]:
            if b["usgs"] == "02087500":
                b["flowCfs"] = _obs(204.0, 30.0)  # older than 24 h
        g = river_gate.evaluate("neuse-river", payload, NOW)
        self.assertEqual(_by_id(g, "flow-02087500")["status"], "missing")
        # Still 2 of 3 (Falls + Goldsboro) so the gate passes.
        self.assertTrue(g["ok"], g["errors"])

    def test_failed_fetch_on_alerts(self):
        g = river_gate.evaluate("neuse-river", _neuse(alerts="unavailable"), NOW)
        self.assertFalse(g["ok"])
        self.assertEqual(_by_id(g, "alerts")["status"], "failed-fetch")
        self.assertTrue(any("alerts check failed" in e.lower() for e in g["errors"]))

    def test_failed_fetch_on_usgs_flow(self):
        payload = _neuse()
        for b in payload["river"]:
            if b["usgs"] in ("02087183", "02089000"):
                b["flowCfs"] = {"status": "failed-fetch"}
                b["stageFt"] = {"status": "failed-fetch"}
        g = river_gate.evaluate("neuse-river", payload, NOW)
        self.assertEqual(_by_id(g, "flow-02087183")["status"], "failed-fetch")
        self.assertFalse(g["ok"])  # only Clayton remains

    def test_forecast_too_old_fails(self):
        g = river_gate.evaluate("neuse-river", _neuse(forecast_h=19.0), NOW)
        self.assertFalse(g["ok"])
        self.assertEqual(_by_id(g, "nwps-forecast")["status"], "stale")
        self.assertTrue(any("stale" in e and "18" in e for e in g["errors"]), g["errors"])

    def test_forecast_at_12h_still_passes(self):
        g = river_gate.evaluate("neuse-river", _neuse(forecast_h=12.0), NOW)
        self.assertTrue(g["ok"], g["errors"])
        self.assertEqual(_by_id(g, "nwps-forecast")["status"], "pass")

    def test_missing_forecast_fails(self):
        g = river_gate.evaluate("neuse-river", _neuse(forecast_h=None), NOW)
        self.assertFalse(g["ok"])
        self.assertEqual(_by_id(g, "nwps-forecast")["status"], "missing")

    def test_failed_nwps_fetch_is_failed_fetch(self):
        g = river_gate.evaluate("neuse-river", _neuse(forecast_h=None, nwps_status="unavailable"), NOW)
        self.assertFalse(g["ok"])
        self.assertEqual(_by_id(g, "nwps-forecast")["status"], "failed-fetch")

    def test_smithfield_has_no_flow_and_is_not_required(self):
        payload = _neuse()
        smf = next(b for b in payload["river"] if b["usgs"] == "02087570")
        smf["flowCfs"] = None
        smf["stageFt"] = None
        g = river_gate.evaluate("neuse-river", payload, NOW)
        self.assertTrue(g["ok"], g["errors"])
        self.assertEqual(_by_id(g, "flow-02087570")["status"], "n/a")
        self.assertEqual(_by_id(g, "stage-02087570")["status"], "optional")

    def test_weather_optional_does_not_fail(self):
        payload = _neuse()
        payload["forecast"] = {"status": "unavailable"}
        g = river_gate.evaluate("neuse-river", payload, NOW)
        self.assertTrue(g["ok"], g["errors"])
        self.assertEqual(_by_id(g, "weather")["status"], "optional")

    def test_water_temp_na_is_not_a_failure(self):
        g = river_gate.evaluate("neuse-river", _neuse(), NOW)
        self.assertEqual(_by_id(g, "water-temp")["status"], "n/a")
        self.assertNotIn("water temp", " ".join(g["errors"]).lower())

    def test_assemble_failure(self):
        g = river_gate.evaluate("neuse-river", {"ok": False, "error": "unavailable"}, NOW)
        self.assertFalse(g["ok"])
        self.assertEqual(g["checks"][0]["status"], "failed-fetch")


class JordanGate(unittest.TestCase):
    def test_fresh_passes_and_moncure_is_labeled(self):
        g = river_gate.evaluate("jordan-lake", _jordan(), NOW)
        self.assertTrue(g["ok"], g["errors"])
        mon = _by_id(g, "moncure-runoff")
        self.assertEqual(mon["status"], "pass")
        self.assertIn("release plus runoff at Moncure, not official gate outflow", mon["reason"])
        self.assertEqual(_by_id(g, "water-temp")["status"], "n/a")
        self.assertEqual(_by_id(g, "official-outflow")["status"], "n/a")
        self.assertEqual(_by_id(g, "lake-elev")["status"], "pass")
        self.assertEqual(_by_id(g, "alerts")["status"], "pass")

    def test_stale_lake_fails(self):
        g = river_gate.evaluate("jordan-lake", _jordan(elev_h=5.0), NOW)
        self.assertFalse(g["ok"])
        self.assertEqual(_by_id(g, "lake-elev")["status"], "stale")

    def test_stale_moncure_fails(self):
        g = river_gate.evaluate("jordan-lake", _jordan(rel_h=4.2), NOW)
        self.assertFalse(g["ok"])
        self.assertEqual(_by_id(g, "moncure-runoff")["status"], "stale")
        self.assertIn("not official gate outflow", _by_id(g, "moncure-runoff")["reason"])

    def test_missing_moncure_fails(self):
        payload = _jordan()
        payload["release"]["flowCfs"] = None
        g = river_gate.evaluate("jordan-lake", payload, NOW)
        self.assertFalse(g["ok"])
        self.assertEqual(_by_id(g, "moncure-runoff")["status"], "missing")

    def test_failed_alerts(self):
        g = river_gate.evaluate("jordan-lake", _jordan(alerts="unavailable"), NOW)
        self.assertFalse(g["ok"])
        self.assertEqual(_by_id(g, "alerts")["status"], "failed-fetch")

    def test_missing_water_temp_is_na_not_missing(self):
        payload = _jordan()
        payload["waterTemp"] = {"status": "unavailable", "c": None, "f": None, "time": None}
        g = river_gate.evaluate("jordan-lake", payload, NOW)
        self.assertTrue(g["ok"], g["errors"])
        self.assertEqual(_by_id(g, "water-temp")["status"], "n/a")
        self.assertTrue(any("water temp not applicable" in n for n in g["notes"]))

    def test_optional_rain_and_weather_do_not_fail(self):
        payload = _jordan()
        payload["rain"] = {"status": "unavailable"}
        payload["forecast"] = {"status": "unavailable"}
        payload["inflows"] = []
        g = river_gate.evaluate("jordan-lake", payload, NOW)
        self.assertTrue(g["ok"], g["errors"])
        self.assertEqual(_by_id(g, "rain")["status"], "optional")
        self.assertEqual(_by_id(g, "weather")["status"], "optional")


class Banner(unittest.TestCase):
    def test_neuse_pass_banner(self):
        with patch("freshwater.assemble", return_value=(200, _neuse())):
            b = brief_preview.compose("neuse-river", NOW)
        text = brief_preview.banner_check(b)
        self.assertTrue(text.startswith("Data checks: would pass"), text)
        self.assertNotIn("would NOT pass", text)
        self.assertNotIn("lake level", text.lower())
        html = brief_preview.page(b)
        self.assertIn("would pass", html)
        self.assertIn("Private preview · not published", html)

    def test_neuse_fail_banner(self):
        with patch("freshwater.assemble", return_value=(200, _neuse(forecast_h=19.0))):
            b = brief_preview.compose("neuse-river", NOW)
        text = brief_preview.banner_check(b)
        self.assertTrue(text.startswith("Data checks: would NOT pass"), text)
        self.assertIn("stale", text.lower())
        self.assertIn(str(int(river_gate.NWPS_FORECAST_FRESH_H)), text)

    def test_jordan_pass_banner_mentions_runoff_label(self):
        with patch("freshwater.assemble", return_value=(200, _jordan())):
            b = brief_preview.compose("jordan-lake", NOW)
        text = brief_preview.banner_check(b)
        self.assertTrue(text.startswith("Data checks: would pass"), text)
        self.assertIn("release plus runoff at Moncure, not official gate outflow", text)
        self.assertIn("water temp not applicable", text)

    def test_coastal_banner_still_uses_brief_validate(self):
        # A coastal preview must not pick up the freshwater gate, and its
        # "would pass" wording stays the pre-existing brief.validate form.
        body = {"region": {"id": "topsail", "name": "Topsail", "area": "x",
                           "anchor": {"lat": 0, "lon": 0}},
                "waterType": "saltwater",
                "items": [("Advisories", "No NWS marine advisories for this area."),
                          ("Wind", "10 kt from the N, gusting 14, at X."),
                          ("Seas", "2.0 ft every 6 s from the E at Y."),
                          ("Pressure", "30.03 inHg, 3-hour trend not reported."),
                          ("Marine forecast", "Today: N winds 10 kt. (NWS AMZ133)"),
                          ("Tides", "high 10:31 AM ET (4.3 ft) at Z, MLLW.")],
                "freshness": [], "take": ["No advisories."], "missing": ["water temp"],
                "marineZone": "AMZ133", "marineUpdated": None, "forecastUpdated": None, "sources": "NOAA"}
        # Use the real region config by going through compose with build_salt patched
        # if topsail is available. Fall back to a direct banner_check on a salt validation.
        cfg = brief_preview._cfg("topsail")
        if cfg.get("marine"):
            body["marineZone"] = cfg["marine"]["zone"]
            body["region"]["name"] = cfg["name"]
            body["region"]["anchor"] = cfg["anchor"]
            body["region"]["area"] = cfg.get("area")
        with patch.object(brief, "build_salt", return_value=body), \
             patch("conditions.assemble", return_value=(200, {"ok": True, "readings": {}})):
            b = brief_preview.compose("topsail", NOW)
        self.assertNotEqual((b.get("validation") or {}).get("gate"), "freshwater-preview")
        text = brief_preview.banner_check(b)
        # Coastal wording: "all core readings present" or "some readings have no local sensor"
        self.assertTrue(text.startswith("Data checks: would pass"), text)
        self.assertIn("some readings have no local sensor, listed below", text)


class ValidateUnchanged(unittest.TestCase):
    """brief.validate itself must keep its coastal and Falls behavior."""

    def test_salt_core_and_fresh_core_unchanged(self):
        self.assertEqual(brief.SALT_CORE, ("Advisories", "Wind", "Seas", "Marine forecast", "Tides", "Water temp"))
        self.assertEqual(brief.FRESH_CORE, ("Lake level", "Dam release", "Water temp", "Weather"))

    def test_falls_shaped_brief_still_uses_lake_core(self):
        now = NOW
        cfg = brief._region_cfg("falls-lake", True)
        self.assertIsNotNone(cfg)
        b = {"ok": True, "regionId": "falls-lake", "waterType": "freshwater",
             "issueDate": brief._issue_date(now), "issuedAt": now.isoformat(),
             "region": {"id": "falls-lake", "name": cfg["name"], "anchor": cfg["anchor"]},
             "items": [("Alerts", "No NWS alerts at the dam."),
                       ("Lake level", "245.00 ft (NGVD29)."),
                       ("Dam release", "80 cfs below Falls Dam."),
                       ("Water temp", "55°F at the dam sensor."),
                       ("Weather", "Sunny, high 60°F, wind SW 5 mph.")],
             "missing": [], "take": ["ok"]}
        errs, summary = brief.validate(b, "falls-lake", now)
        self.assertEqual(errs, [])
        self.assertEqual(summary["status"], "ok")
        self.assertEqual(summary["missingCore"], [])

        missing = {**b, "items": [("Alerts", "No NWS alerts at the dam."), ("Weather", "Sunny, high 60°F.")]}
        errs, summary = brief.validate(missing, "falls-lake", now)
        self.assertTrue(any("most core readings are missing" in e and "lake level" in e for e in errs), errs)
        self.assertIn("dam release", ",".join(summary["missingCore"]))
        self.assertIn("water temp", ",".join(summary["missingCore"]))

    def test_validate_still_rejects_a_neuse_brief_against_the_lake_core(self):
        # The new river gate must not have softened brief.validate for a river brief.
        now = NOW
        cfg = brief._region_cfg("neuse-river", True)
        b = {"ok": True, "regionId": "neuse-river", "waterType": "freshwater",
             "issueDate": brief._issue_date(now), "issuedAt": now.isoformat(),
             "region": {"id": "neuse-river", "name": cfg["name"], "anchor": cfg["anchor"]},
             "items": [("Alerts", "No NWS alerts at Clayton."),
                       ("Neuse River near Clayton", "1.19 ft stage, 204 cfs."),
                       ("Weather", "Sunny, high 57°F, wind NW 2 mph.")],
             "missing": [], "take": ["ok"]}
        errs, summary = brief.validate(b, "neuse-river", now)
        self.assertTrue(any("most core readings are missing" in e for e in errs), errs)
        self.assertIn("lake level", ",".join(summary["missingCore"]))
        self.assertIn("dam release", ",".join(summary["missingCore"]))
        self.assertIn("water temp", ",".join(summary["missingCore"]))



class AlertCoverage(unittest.TestCase):
    def test_neuse_full_coverage_passes(self):
        payload = _neuse()
        payload["alerts"] = preview_alerts.ok_coverage("neuse-river")
        g = river_gate.evaluate("neuse-river", payload, NOW)
        self.assertTrue(g["ok"], g["errors"])
        c = _by_id(g, "alerts")
        self.assertEqual(c["status"], "pass")
        self.assertIn("Wake, Johnston and Wayne counties", c["reason"])

    def test_neuse_partial_zone_coverage_fails(self):
        payload = _neuse()
        payload["alerts"] = preview_alerts.failed_coverage("neuse-river", ["NCC191"])
        g = river_gate.evaluate("neuse-river", payload, NOW)
        self.assertFalse(g["ok"])
        c = _by_id(g, "alerts")
        self.assertEqual(c["status"], "failed-fetch")
        self.assertIn("Wayne County (NCC191)", c["reason"])
        self.assertIn("Wake, Johnston and Wayne counties", c["reason"])
        self.assertIn("NCZ041", c["reason"])
        self.assertTrue(any("Wayne County (NCC191)" in e for e in g["errors"]))

    def test_neuse_missing_coverage_fails(self):
        payload = _neuse()
        payload["alerts"] = {"status": "ok", "items": [], "coverage": []}
        g = river_gate.evaluate("neuse-river", payload, NOW)
        self.assertFalse(g["ok"])
        self.assertIn("Wake County (NCZ041)", _by_id(g, "alerts")["reason"])

    def test_jordan_full_coverage_passes(self):
        payload = _jordan()
        payload["alerts"] = preview_alerts.ok_coverage("jordan-lake")
        g = river_gate.evaluate("jordan-lake", payload, NOW)
        self.assertTrue(g["ok"], g["errors"])
        self.assertIn("Chatham County", _by_id(g, "alerts")["reason"])

    def test_jordan_partial_zone_coverage_fails(self):
        payload = _jordan()
        payload["alerts"] = preview_alerts.failed_coverage("jordan-lake", ["NCZ040"])
        g = river_gate.evaluate("jordan-lake", payload, NOW)
        self.assertFalse(g["ok"])
        c = _by_id(g, "alerts")
        self.assertIn("Chatham County (NCZ040)", c["reason"])
        self.assertIn("NCC037", c["reason"])


if __name__ == "__main__":
    unittest.main()
