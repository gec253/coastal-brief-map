"""brief.build_salt fixes approved by Ed on 14 Nov 2026:
1. a pressure reading with no 3-hour trend never prints "None";
2. a region with no inshore water-temp sensor keeps a Water temp line from the offshore buoy,
   labeled offshore, with inshore marked unavailable.
Crystal Coast-style input (inshore temp and a pressure trend) must produce the same lines as before."""
from __future__ import annotations

import copy
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import brief  # noqa: E402

NOW = datetime(2026, 11, 14, 15, 0, tzinfo=timezone.utc)
T = "2026-11-14T14:50:00+00:00"


def _ok(sid, name, values):
    return {"status": "ok", "time": T, "ageMin": 10, "staleAfterMin": 90, "station": {"id": sid, "name": name}, "values": values}


def _payload(rid, name, zone, inshore=True, trend="rising"):
    R = {
        "wind": _ok("CLKN7", "Cape Lookout", {"speedKt": 12.0, "gustKt": 16.0, "dirCompass": "NE"}),
        "seas": _ok("41159", "Onslow Bay Outer (CDIP 217)", {"heightFt": 3.3, "dominantPeriodS": 8.0, "meanDirCompass": "E"}),
        "pressure": _ok("8656483", "Beaufort", {"inHg": 30.03, "hPa": 1017.0, "trend": trend}),
        "waterTempOffshore": _ok("41159", "Onslow Bay Outer (CDIP 217)", {"f": 70.0}),
    }
    if inshore:
        R["waterTemp"] = _ok("8656483", "Beaufort, Duke Marine Lab", {"f": 66.0})
    else:
        R["waterTemp"] = {"status": "unavailable", "kind": "observed", "tried": [], "note": "No sensor."}
    return {"ok": True, "region": {"id": rid, "name": name},
            "readings": R,
            "alerts": {"status": "ok", "items": []},
            "marine": {"status": "ok", "zone": zone, "updated": "2026-11-14T13:00:00+00:00",
                       "periods": [{"name": "This Afternoon", "text": "NE winds 10 to 15 kt. Seas 3 ft."}]},
            "forecast": {"status": "ok", "updated": "2026-11-14T13:00:00+00:00",
                         "periods": [{"pop": 10, "short": "Sunny", "tempF": 60}, {"pop": 0, "short": "Clear", "tempF": 45}]},
            "tides": {"status": "unavailable"}}


def _build(rid, payload):
    with patch("conditions.assemble", return_value=(200, copy.deepcopy(payload))), \
         patch.object(brief, "_trend", return_value=None):
        return brief.build_salt(rid, NOW)


class PressureTrend(unittest.TestCase):
    def test_no_trend_never_prints_none(self):
        b = _build("emerald-isle", _payload("emerald-isle", "Emerald Isle", "AMZ158", inshore=False, trend=None))
        line = dict(b["items"])["Pressure"]
        self.assertNotIn("None", line)
        self.assertEqual(line, "30.03 inHg, 3-hour trend not reported.")

    def test_trend_kept_when_reported(self):
        b = _build("crystal-coast", _payload("crystal-coast", "Morehead City · Beaufort", "AMZ158"))
        self.assertEqual(dict(b["items"])["Pressure"], "30.03 inHg, rising.")


class OffshoreOnlyWaterTemp(unittest.TestCase):
    def test_no_inshore_sensor_uses_offshore_labeled(self):
        for rid in ("nags-head", "emerald-isle", "topsail"):
            b = _build(rid, _payload(rid, rid, "AMZ158", inshore=False))
            line = dict(b["items"]).get("Water temp")
            self.assertEqual(line, "Inshore unavailable (no sensor in this area); 70°F offshore at Onslow Bay Outer (CDIP 217).", rid)
            self.assertNotIn("water temp", b["missing"])
            self.assertIn("Offshore water temp", [f["label"] for f in b["freshness"]])

    def test_inshore_sensor_down_is_still_missing(self):
        # Crystal Coast has an inshore sensor: when it is down, nothing is substituted (unchanged behavior).
        b = _build("crystal-coast", _payload("crystal-coast", "Morehead City · Beaufort", "AMZ158", inshore=False))
        self.assertNotIn("Water temp", dict(b["items"]))
        self.assertIn("water temp", b["missing"])

    def test_no_inshore_and_no_offshore_is_missing(self):
        p = _payload("topsail", "Topsail", "AMZ158", inshore=False)
        p["readings"]["waterTempOffshore"] = {"status": "unavailable"}
        b = _build("topsail", p)
        self.assertNotIn("Water temp", dict(b["items"]))
        self.assertIn("water temp", b["missing"])


class CrystalCoastUnchanged(unittest.TestCase):
    def test_normal_input_lines(self):
        b = _build("crystal-coast", _payload("crystal-coast", "Morehead City · Beaufort", "AMZ158"))
        items = dict(b["items"])
        self.assertEqual(items["Water temp"], "66°F inshore (Beaufort, Duke Marine Lab), 70°F offshore (buoy 41159).")
        self.assertEqual(items["Pressure"], "30.03 inHg, rising.")
        self.assertEqual([f["label"] for f in b["freshness"]], ["Wind", "Seas", "Barometer", "Water temp"])
        self.assertIn("Offshore water is 4°F warmer than inshore.", b["take"])
        self.assertEqual(b["missing"], ["tides"])


if __name__ == "__main__":
    unittest.main()
