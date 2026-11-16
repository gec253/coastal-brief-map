"""Nov 16 accuracy audit: labels, distant-station disclosure, observed vs predicted."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import sprint_home  # noqa: E402
from test_sprint_home_preview import ok, salt, tides, iso, st  # noqa: E402


def station(sid, name, dist, brg, anchor):
    return {"id": sid, "name": name, "distanceMi": dist, "bearingFromAnchor": brg, "anchor": anchor}


class WaterLabels(unittest.TestCase):
    def test_design_label_strings(self):
        ins = ok({"f": 61.0}, "8656483", "Beaufort, Duke Marine Lab")
        off = ok({"f": 66.0})
        off["station"] = station("41159", "Onslow Bay Outer (CDIP 217)", 37, "SSW", "Beaufort Inlet")
        t = sprint_home._water_tile({"waterTemp": ins, "waterTempOffshore": off})
        self.assertEqual(t["label"], "Inshore water · Beaufort, Duke Marine Lab")
        self.assertEqual(t["offshore_label"], "Offshore water · buoy 41159, 37 mi SSW of Beaufort Inlet")
        t2 = sprint_home._water_tile({"waterTemp": {"status": "unavailable"}, "waterTempOffshore": off})
        self.assertEqual(t2["label"], "Offshore water · buoy 41159, 37 mi SSW of Beaufort Inlet")
        self.assertTrue(t2["offshore"])

    def test_stale_offshore_subline_is_marked(self):
        ins = ok({"f": 61.0}, "8656483", "Beaufort, Duke Marine Lab")
        off = ok({"f": 66.0}, "41159", "Onslow Bay Outer", age=300)
        off["status"] = "stale"
        t = sprint_home._water_tile({"waterTemp": ins, "waterTempOffshore": off})
        self.assertIn("66°F (stale, last report", t["sub"])
        off["status"] = "ok"
        self.assertNotIn("stale", sprint_home._water_tile({"waterTemp": ins, "waterTempOffshore": off})["sub"])


class TideStations(unittest.TestCase):
    def nags(self):
        t = tides()
        t["station"] = station("8652226", "Jennette's Pier (ocean)", 0.2, "S", "Jennette's Pier")
        t["curveStation"] = station("8651370", "Duck Pier", 21, "NNW", "Jennette's Pier")
        t["observed"]["station"] = station("8651370", "Duck Pier", 21, "NNW", "Jennette's Pier")
        return t

    def test_observed_level_from_other_gauge_is_named_with_distance(self):
        tt = sprint_home._tide_tile(self.nags())
        self.assertEqual(tt["obs"], "Observed at Duck Pier (21 mi NNW): 2.9 ft, +0.6 vs predicted there")
        self.assertIn("curve from Duck Pier · 8651370", tt["src"])
        html = sprint_home.tile_html(tt)
        self.assertIn("6-minute NOAA predictions from Duck Pier", html)
        self.assertIn("Predicted · Duck Pier", html)

    def test_same_station_unchanged(self):
        tt = sprint_home._tide_tile(tides())
        self.assertEqual(tt["obs"], "Observed 2.9 ft, +0.6 vs predicted")
        self.assertNotIn("curve from", tt["src"])
        self.assertEqual(tt["kind"], "Predicted")


if __name__ == "__main__":
    unittest.main()
