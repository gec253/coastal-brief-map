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


class AlertsUnknownNotClear(unittest.TestCase):
    """Could-not-check alerts are is-unknown, never the verified all-clear class."""

    def test_homepage_boot(self):
        import homepage_boot
        self.assertEqual(homepage_boot.render_alerts_html({"status": "error", "items": []})[1], "is-unknown")
        self.assertEqual(homepage_boot.render_alerts_html(None)[1], "is-unknown")
        self.assertEqual(homepage_boot.render_alerts_html({"status": "ok", "items": [], "zones": ["AMZ158"]})[1], "is-clear")

    def test_client_scripts_and_style(self):
        root = Path(__file__).resolve().parents[1]
        lake = (root / "lake.js").read_text()
        self.assertIn('a.status !== "ok") { box.className = "dash-alert is-unknown"', lake)
        dash = (root / "dashboard.js").read_text()
        self.assertIn('(a && a.status === "ok" ? "is-clear" : "is-unknown")', dash)
        self.assertNotRegex(dash, r'is-clear";\s*\n\s*al\.innerHTML = \'<div class="al-item"><span class="al-dot"></span><span class="al-ev">Alerts unavailable')
        css = (root / "styles.css").read_text()
        self.assertIn(".dash-alert.is-unknown {", css)
        self.assertNotIn(".dash-alert.is-clear, .dash-alert.is-unknown", css)


class NwpsForecastIsLabelledStageOnly(unittest.TestCase):
    def test_forecast_block(self):
        from unittest import mock
        import freshwater
        gauge = {"name": "Neuse at Clayton", "flood": {"categories": {"minor": {"stage": 9}}},
                 "status": {"observed": {}, "forecast": {"primary": 4.2, "floodCategory": "no_flooding"}}}
        sf = {"issuedTime": "2026-11-16T12:00:00Z", "primaryUnits": "ft", "secondaryUnits": "kcfs",
              "data": [{"validTime": "2026-11-17T00:00:00Z", "primary": 4.2, "secondary": 1.3},
                       {"validTime": "2026-11-17T06:00:00Z", "primary": 4.5, "secondary": 1.5}]}
        with mock.patch.object(freshwater, "_get_json", side_effect=lambda url, ttl: sf if "stageflow" in url else gauge):
            out = freshwater.nwps("CLYN7")
        fc = out["forecast"]
        self.assertEqual(fc["kind"], "forecast")
        self.assertEqual(fc["crestStage"], 4.5)
        self.assertNotIn("crestFlowCfs", fc)
        self.assertNotIn("kcfs", repr(fc))


class FreshPreviewCrestWording(unittest.TestCase):
    """Private Falls/Jordan/Neuse previews: a falling NWPS forecast is not called a crest."""

    def test_phrase(self):
        import preview_copy
        import brief_preview
        rising = {"crestStage": 4.5, "crestTime": "2026-11-17T06:00:00Z", "series": [["a", 4.1], ["b", 4.5], ["c", 4.3]]}
        falling = {"crestStage": 4.5, "crestTime": "2026-11-17T00:00:00Z", "series": [["a", 4.5], ["b", 4.2]]}
        self.assertEqual(preview_copy.crest_phrase(rising), "NWS forecasts a crest of")
        self.assertEqual(preview_copy.crest_phrase(falling), "NWS forecasts no rise; highest forecast stage")
        blk = lambda fc: {"nwps": {"status": "ok", "lid": "CLYN7", "forecast": dict(fc, category="no_flooding")}}
        self.assertIn("crest 4.5 ft", brief_preview._nwps_forecast(blk(rising)))
        f = brief_preview._nwps_forecast(blk(falling))
        self.assertIn("highest stage, no rise forecast; 4.5 ft", f)
        self.assertNotIn("crest", f)


class TopsailZoneNames(unittest.TestCase):
    def test_dashboard_labels_local_area_as_unofficial(self):
        root = Path(__file__).resolve().parents[1]
        js = (root / "dashboard.js").read_text()
        self.assertIn("Local area (not an NWS name): ", js)
        self.assertEqual(js.count("mfArea("), 3)  # helper + single-zone + multi-zone
        self.assertNotIn("North Topsail / New River Inlet", js)


class CapeFearPreviewCrestWording(unittest.TestCase):
    def test_falling_forecast_take_has_no_crest(self):
        from unittest import mock
        import brief_preview
        import freshwater
        import preview_copy
        import test_cape_fear as cf
        p = cf._cape()
        for b in p["river"]:
            fc = (b.get("nwps") or {}).get("forecast")
            if fc:
                fc["series"] = [[fc["crestTime"], fc["crestStage"]], ["later", fc["crestStage"] - 0.4]]
        with mock.patch.object(freshwater, "assemble", return_value=(200, p)):
            b = brief_preview.compose(cf.RID, cf.NOW)
        text = preview_copy.take_text(b["captainsTake"])
        self.assertIn("NWS forecasts no rise; highest forecast stage 9.4 ft", text)
        self.assertNotIn("crest", text.lower())
