"""Public /lake NWPS forecast line: no 'crest' without a forecast rise, issue time shown,
stale past 18 h. Renders lake.js in node against fixture payloads only (never live data)."""
import copy
import json
import shutil
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "tests" / "lake_render_harness.js"
FIXTURE = ROOT / "tests" / "fixtures" / "lake-render.json"
PUBLIC = ("falls-lake", "jordan-lake", "neuse-river")


def iso(hours_from_now):
    return (datetime.now(timezone.utc) + timedelta(hours=hours_from_now)).strftime("%Y-%m-%dT%H:%M:%SZ")


def forecast(kind, issued_h_ago=3.0, issued=True):
    if kind == "falling":
        series = [[iso(1), 5.4], [iso(7), 5.1], [iso(13), 4.8]]
    else:
        series = [[iso(1), 4.8], [iso(7), 5.4], [iso(13), 5.0]]
    fc = {"crestStage": 5.4, "crestTime": series[0][0] if kind == "falling" else series[1][0],
          "category": "no_flooding", "series": series}
    if issued:
        fc["issued"] = iso(-issued_h_ago)
    return fc


@unittest.skipUnless(shutil.which("node"), "node not installed")
class LakeNwpsLine(unittest.TestCase):
    def render(self, rid, fc):
        data = json.loads(FIXTURE.read_text())
        p = copy.deepcopy(data[rid])
        for s in (p.get("river") or []) + ([p["release"]] if p.get("release") else []):
            if (s.get("nwps") or {}).get("forecast"):
                s["nwps"]["forecast"] = copy.deepcopy(fc)
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump({rid: p}, f)
        try:
            out = subprocess.run(["node", str(HARNESS), str(ROOT / "lake.js"), f.name, rid],
                                 check=True, capture_output=True, text=True, cwd=ROOT).stdout
        finally:
            Path(f.name).unlink()
        return json.loads(out)["fw-river"]["html"]

    def test_falling_forecast_never_says_crest(self):
        for rid in PUBLIC:
            h = self.render(rid, forecast("falling"))
            self.assertNotIn("crest", h.lower(), rid)
            self.assertIn("NWS forecast: no rise, highest 5.4 ft", h, rid)

    def test_rising_forecast_keeps_crest_and_shows_issue_time(self):
        for rid in PUBLIC:
            h = self.render(rid, forecast("rising"))
            self.assertIn("NWS crest 5.4 ft", h, rid)
            self.assertIn("· NWS forecast issued ", h, rid)
            self.assertNotIn("stale", h, rid)

    def test_stale_after_18_hours(self):
        for rid in PUBLIC:
            h = self.render(rid, forecast("rising", issued_h_ago=19))
            self.assertRegex(h, r"<strong>NWS forecast issued [^<]+ ET · stale</strong>")
            self.assertIn('class="fw-meta is-stale"', h)
            fresh = self.render(rid, forecast("rising", issued_h_ago=17))
            self.assertNotIn("stale", fresh)

    def test_missing_issue_time_is_said_not_invented(self):
        h = self.render("neuse-river", forecast("rising", issued=False))
        self.assertIn("NWS did not give an issue time", h)
        self.assertNotIn("issued", h)

    def test_no_forecast_flow(self):
        fc = forecast("rising")
        fc["crestFlowCfs"] = 1234
        for rid in PUBLIC:
            h = self.render(rid, fc)
            self.assertNotIn("1,234", h)
            self.assertNotIn("1234", h)


if __name__ == "__main__":
    unittest.main()
