"""Tests for public Falls Lake, Jordan Lake and Neuse River freshwater views.

Run:  python -m unittest tests.test_freshwater
"""
from __future__ import annotations

import os
import sys
import threading
import unittest
from datetime import datetime, timedelta, timezone
from http.client import HTTPConnection
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import freshwater  # noqa: E402
from freshwater import REJECT_H, STALE_H, latest  # noqa: E402

NOW = datetime(2026, 11, 13, 19, 30, tzinfo=timezone.utc)  # 2:30 PM EST


def _pt(age_h, value):
    return (NOW - timedelta(hours=age_h), value)


def _reading(age_min, value):
    t = NOW - timedelta(minutes=age_min)
    return {"value": value, "time": t.isoformat(), "ageH": round(age_min / 60, 2), "stale": age_min / 60 > STALE_H}


class LatestRejection(unittest.TestCase):
    def test_fresh_point_is_returned(self):
        out = latest([_pt(0.5, 4.45)], NOW)
        self.assertIsNotNone(out)
        self.assertEqual(out["value"], 4.45)
        self.assertFalse(out["stale"])

    def test_stale_but_recent_is_flagged_not_dropped(self):
        # 5 h is past STALE_H (3) but under REJECT_H (24) — same rule Falls uses.
        out = latest([_pt(5, 4.45)], NOW)
        self.assertIsNotNone(out)
        self.assertEqual(out["value"], 4.45)
        self.assertTrue(out["stale"])

    def test_1991_discharge_is_rejected(self):
        old = datetime(1991, 9, 30, 16, tzinfo=timezone.utc)
        self.assertIsNone(latest([(old, 298.0)], NOW))

    def test_point_older_than_reject_window_is_dropped(self):
        self.assertIsNone(latest([_pt(REJECT_H + 1, 12.0)], NOW))

    def test_newest_old_point_does_not_hide_an_earlier_fresh_one(self):
        # Defensive: if a series somehow ends on an ancient value, skip it.
        series = [_pt(1, 4.4), (datetime(1991, 9, 30, tzinfo=timezone.utc), 298.0)]
        out = latest(series, NOW)
        self.assertEqual(out["value"], 4.4)


class ConfigShape(unittest.TestCase):
    def setUp(self):
        self.regs = freshwater.regions()

    def test_jordan_and_neuse_are_public_and_preview_ready(self):
        for rid in ("falls-lake", "jordan-lake", "neuse-river"):
            r = self.regs[rid]
            self.assertTrue(r.get("previewReady"), rid)
            self.assertTrue(r.get("enabled"), rid)
            self.assertFalse(r.get("draft"), rid)
            self.assertEqual(r.get("waterType"), "freshwater")

    def test_jordan_gauges_and_guide_curve(self):
        j = self.regs["jordan-lake"]
        self.assertEqual(j["instrumentSet"], "freshwater-lake")
        self.assertEqual(j["lake"]["usgs"], "02098197")
        self.assertEqual(j["lake"]["elevNgvd29"], "62614")
        self.assertEqual(j["lake"]["elevNavd88"], "62615")
        self.assertEqual(j["lake"]["guideCurveFt"], 216.0)
        self.assertNotIn("waterTemp", j["lake"])
        self.assertEqual(j["release"]["usgs"], "02098206")
        self.assertIn("release plus local runoff", j["release"]["label"])
        self.assertEqual(j["inflows"][0]["usgs"], "02096960")
        self.assertIn("inflow above the lake", j["inflows"][0]["label"])
        used = {j["lake"]["usgs"], j["release"]["usgs"], j["inflows"][0]["usgs"]}
        self.assertNotIn("02098198", used)

    def test_neuse_gauges_smithfield_stage_only_no_kinston(self):
        n = self.regs["neuse-river"]
        self.assertEqual(n["instrumentSet"], "freshwater-river")
        ids = [s["usgs"] for s in n["river"]]
        self.assertEqual(ids, ["02087183", "02087500", "02087570", "02089000"])
        self.assertNotIn("02089500", ids)
        smf = next(s for s in n["river"] if s["usgs"] == "02087570")
        self.assertIs(smf["flow"], False)
        self.assertIn("stage only", smf["flowNote"].lower())
        self.assertEqual(n["waterTemp"]["status"], "none")
        self.assertEqual(smf["floodStages"]["minor"], 15)


def _empty_nwps(lid):
    return {"lid": lid, "status": "ok", "name": lid, "floodStages": {}, "url": "https://water.noaa.gov/gauges/%s" % lid.lower()}


def _forecast_ok():
    return {"status": "ok", "updated": NOW.isoformat(), "periods": [
        {"name": "This Afternoon", "tempF": 68, "short": "Sunny", "windDir": "SW", "windMph": "5 mph"}
    ] * 4, "sourceUrl": "https://forecast.weather.gov/"}


class AssembleJordanNeuse(unittest.TestCase):
    def setUp(self):
        freshwater._ASSEMBLED.clear()

    def tearDown(self):
        freshwater._ASSEMBLED.clear()

    def _assemble(self, rid, iv7=None, ivq=None, names=None):
        iv7 = iv7 or {}
        ivq = ivq or {}
        names = names or {}

        def fake_iv(sites, params, period="P1D"):
            if period == "P7D":
                return iv7, names
            return ivq, names

        class Frozen(datetime):
            @classmethod
            def now(cls, tz=None):
                return NOW if tz else NOW.replace(tzinfo=None)
        with patch("freshwater.datetime", Frozen), \
                patch("freshwater.usgs_iv", side_effect=fake_iv), \
                patch("freshwater.usgs_daily_stats", return_value=None), \
                patch("freshwater.nwps", side_effect=_empty_nwps), \
                patch("freshwater.qpf_block", return_value={"status": "unavailable", "kind": "forecast"}), \
                patch("freshwater.alerts_point", return_value={"status": "ok", "items": []}), \
                patch("freshwater.usace_guide_check", return_value={"status": "ok", "matches": True, "values": [216.0, 251.5]}), \
                patch("conditions.forecast_block", return_value=_forecast_ok()):
            return freshwater.assemble(rid)

    def test_unknown_region_is_404(self):
        status, body = freshwater.assemble("no-such-lake")
        self.assertEqual(status, 404)
        self.assertFalse(body["ok"])

    def test_not_preview_ready_is_404(self):
        fake = {"draft-lake": {"id": "draft-lake", "previewReady": False,
                               "instrumentSet": "freshwater-lake", "lake": {"usgs": "x"}}}
        with patch.object(freshwater, "regions", return_value=fake):
            status, body = freshwater.assemble("draft-lake")
        self.assertEqual(status, 404)

    def test_jordan_guide_curve_delta(self):
        t = _pt(0.4, 212.23)
        iv7 = {
            ("02098197", "62614"): [t],
            ("02098197", "62615"): [_pt(0.4, 211.46)],
            ("02098197", "00045"): [_pt(0.4, 0.0)],
        }
        ivq = {
            ("02098206", "00060"): [_pt(0.5, 245.0)],
            ("02098206", "00065"): [_pt(0.5, 2.02)],
            ("02096960", "00060"): [_pt(0.3, 77.4)],
            ("02096960", "00065"): [_pt(0.3, 2.62)],
        }
        names = {"02098197": "B. EVERETT JORDAN LAKE AT DAM NR MONCURE, NC"}
        status, body = self._assemble("jordan-lake", iv7=iv7, ivq=ivq, names=names)
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])
        self.assertEqual(body["region"]["id"], "jordan-lake")
        self.assertEqual(body["lake"]["datum"], "NGVD29")
        self.assertEqual(body["lake"]["guideCurveFt"], 216.0)
        self.assertEqual(body["lake"]["elevation"]["value"], 212.23)
        self.assertEqual(body["lake"]["vsGuideFt"], round(212.23 - 216.0, 2))
        self.assertEqual(body["lake"]["vsGuideFt"], -3.77)
        self.assertEqual(body["lake"]["datumOffsetFt"], round(212.23 - 211.46, 2))
        self.assertEqual(body["waterTemp"]["status"], "unavailable")
        self.assertIsNone(body["waterTemp"].get("c"))
        self.assertEqual(body["release"]["usgs"], "02098206")
        self.assertIn("release plus local runoff", body["release"]["label"])
        self.assertEqual(body["release"]["flowCfs"]["value"], 245.0)
        self.assertEqual(body["inflows"][0]["usgs"], "02096960")
        self.assertIn("inflow above the lake", body["inflows"][0]["label"])

    def test_neuse_smithfield_never_shows_discharge(self):
        old = datetime(1991, 9, 30, 16, tzinfo=timezone.utc)
        ivq = {
            ("02087183", "00060"): [_pt(0.4, 60.0)],
            ("02087183", "00065"): [_pt(0.4, 0.94)],
            ("02087500", "00060"): [_pt(0.5, 217.0)],
            ("02087500", "00065"): [_pt(0.5, 1.22)],
            ("02087570", "00060"): [(old, 298.0)],
            ("02087570", "00065"): [_pt(0.5, 4.45)],
            ("02089000", "00060"): [_pt(0.5, 319.0)],
            ("02089000", "00065"): [_pt(0.5, 2.69)],
        }
        status, body = self._assemble("neuse-river", ivq=ivq)
        self.assertEqual(status, 200)
        self.assertIsNone(body["lake"])
        self.assertEqual(body["waterTemp"]["status"], "unavailable")
        self.assertIn("No active USGS water-temperature sensor", body["waterTemp"]["note"])
        ids = [s["usgs"] for s in body["river"]]
        self.assertEqual(ids, ["02087183", "02087500", "02087570", "02089000"])
        smf = next(s for s in body["river"] if s["usgs"] == "02087570")
        self.assertTrue(smf["stageOnly"])
        self.assertIsNone(smf["flowCfs"])
        self.assertNotIn(298.0, [smf.get("flowCfs") and smf["flowCfs"].get("value")])
        self.assertEqual(smf["stageFt"]["value"], 4.45)
        self.assertIn("stage only", smf["flowNote"].lower())
        # Documented NWS flood stages are present even if live NWPS categories are empty.
        self.assertEqual(smf["floodStages"]["minor"], 15)

    def test_missing_feed_is_unavailable(self):
        # Jordan pool series missing entirely.
        iv7 = {("02098197", "62615"): [_pt(0.4, 211.46)]}  # NAVD only; no 62614
        status, body = self._assemble("jordan-lake", iv7=iv7, ivq={})
        self.assertEqual(status, 200)
        self.assertIsNone(body["lake"]["elevation"])
        self.assertNotIn("vsGuideFt", body["lake"])
        self.assertIsNone(body["release"]["flowCfs"])
        self.assertIsNone(body["release"]["stageFt"])

    def test_stale_pool_is_rejected_not_used_for_guide_delta(self):
        iv7 = {("02098197", "62614"): [_pt(REJECT_H + 2, 212.23)]}
        status, body = self._assemble("jordan-lake", iv7=iv7, ivq={})
        self.assertEqual(status, 200)
        self.assertIsNone(body["lake"]["elevation"])
        self.assertNotIn("vsGuideFt", body["lake"])

    def test_falls_lake_still_assembles_with_guide_251_5(self):
        t = _pt(0.3, 245.07)
        iv7 = {
            ("02087182", "62614"): [t],
            ("02087182", "62615"): [_pt(0.3, 244.17)],
            ("02087182", "00010"): [_pt(0.3, 16.7)],
            ("02087182", "00045"): [_pt(0.3, 0.0)],
        }
        ivq = {
            ("02087183", "00060"): [_pt(0.4, 60.0)],
            ("02087183", "00065"): [_pt(0.4, 0.94)],
            ("02087500", "00060"): [_pt(0.5, 217.0)],
            ("02087500", "00065"): [_pt(0.5, 1.22)],
            ("02087570", "00065"): [_pt(0.5, 4.45)],
            ("02089000", "00060"): [_pt(0.5, 319.0)],
            ("02089000", "00065"): [_pt(0.5, 2.69)],
            ("02085070", "00060"): [_pt(0.4, 5.88)],
            ("02085070", "00065"): [_pt(0.4, 1.2)],
            ("02085500", "00060"): [_pt(0.4, 2.88)],
            ("02085500", "00065"): [_pt(0.4, 0.8)],
        }
        status, body = self._assemble("falls-lake", iv7=iv7, ivq=ivq)
        self.assertEqual(status, 200)
        self.assertEqual(body["region"]["id"], "falls-lake")
        self.assertEqual(body["lake"]["guideCurveFt"], 251.5)
        self.assertEqual(body["lake"]["vsGuideFt"], round(245.07 - 251.5, 2))
        self.assertEqual(body["waterTemp"]["status"], "ok")
        self.assertEqual(body["waterTemp"]["c"], 16.7)
        self.assertEqual(body["release"]["usgs"], "02087183")
        self.assertEqual(len(body["river"]), 3)
        self.assertEqual(len(body["inflows"]), 2)
        smf = next(s for s in body["river"] if s["usgs"] == "02087570")
        self.assertTrue(smf["stageOnly"])
        self.assertIsNone(smf["flowCfs"])


class FlagOn(unittest.TestCase):
    def setUp(self):
        self._prev = os.environ.get("FRESHWATER_ENABLED")
        os.environ.pop("FRESHWATER_ENABLED", None)

    def tearDown(self):
        if self._prev is None:
            os.environ.pop("FRESHWATER_ENABLED", None)
        else:
            os.environ["FRESHWATER_ENABLED"] = self._prev

    def test_default_on_with_no_env(self):
        os.environ.pop("FRESHWATER_ENABLED", None)
        self.assertTrue(freshwater.flag_on())

    def test_kill_switch(self):
        for v in ("0", "false", "off", "FALSE", "Off", " 0 "):
            os.environ["FRESHWATER_ENABLED"] = v
            self.assertFalse(freshwater.flag_on(), msg=repr(v))

    def test_explicit_on_still_works(self):
        for v in ("1", "true", "on", "yes", ""):
            os.environ["FRESHWATER_ENABLED"] = v
            self.assertTrue(freshwater.flag_on(), msg=repr(v))


class GatingHttp(unittest.TestCase):
    """Public by default (200, no private-preview text). Kill switch → 404. Homepage stays 200."""

    @classmethod
    def setUpClass(cls):
        # Import late so freshwater patches in other tests are not affected.
        import server
        cls.server_mod = server
        cls.httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        cls.host, cls.port = cls.httpd.server_address

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def _req(self, path, env=None):
        saved = {k: os.environ.get(k) for k in ("FRESHWATER_ENABLED", "PREVIEW_KEY")}
        try:
            os.environ.pop("FRESHWATER_ENABLED", None)
            os.environ.pop("PREVIEW_KEY", None)
            if env:
                os.environ.update(env)
            conn = HTTPConnection("127.0.0.1", self.port, timeout=5)
            conn.request("GET", path)
            resp = conn.getresponse()
            body = resp.read()
            headers = {k.lower(): v for k, v in resp.getheaders()}
            conn.close()
            return resp.status, body, headers
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    def test_pages_and_api_200_with_no_env(self):
        stub = (200, {"ok": True, "region": {"id": "jordan-lake", "name": "Jordan Lake"},
                      "lake": {"guideCurveFt": 216.0, "vsGuideFt": -3.77, "elevation": {"value": 212.23}}})
        paths = ("/lake", "/lake?region=falls-lake", "/lake?region=jordan-lake", "/lake?region=neuse-river")
        with patch.object(freshwater, "assemble", return_value=stub):
            for path in paths:
                status, body, headers = self._req(path)
                self.assertEqual(status, 200, path)
                low = body.lower()
                self.assertNotIn(b"private preview", low, path)
                self.assertIn(b'name="robots" content="index, follow"', body, path)
                robots = (headers.get("x-robots-tag") or "").lower()
                self.assertIn("index", robots, path)
                self.assertIn("follow", robots, path)
                self.assertNotIn("noindex", robots, path)
                self.assertIn(b'href="/lake?region=falls-lake"', body)
                self.assertIn(b'href="/lake?region=jordan-lake"', body)
                self.assertIn(b'href="/lake?region=neuse-river"', body)
                self.assertIn(b'href="/"', body)
            status, body, _ = self._req("/api/freshwater?region=jordan-lake")
            self.assertEqual(status, 200)
            self.assertIn(b"jordan-lake", body)
            status, _, _ = self._req("/api/freshwater?region=falls-lake")
            self.assertEqual(status, 200)
            status, _, _ = self._req("/api/freshwater?region=neuse-river")
            self.assertEqual(status, 200)

    def test_kill_switch_gives_404(self):
        for path in ("/lake", "/lake?region=jordan-lake", "/lake?region=neuse-river",
                     "/api/freshwater?region=jordan-lake", "/api/freshwater?region=neuse-river",
                     "/api/freshwater?region=falls-lake"):
            status, _, _ = self._req(path, env={"FRESHWATER_ENABLED": "0"})
            self.assertEqual(status, 404, path)

    def test_home_is_200_with_or_without_kill_switch(self):
        status, body, _ = self._req("/")
        self.assertEqual(status, 200)
        self.assertIn(b"The Coastal Brief", body)
        self.assertNotIn(b"private preview", body.lower())
        self.assertNotIn(b"Freshwater coming soon", body)
        status, body, _ = self._req("/", env={"FRESHWATER_ENABLED": "0"})
        self.assertEqual(status, 200)
        self.assertIn(b"The Coastal Brief", body)

    def test_home_freshwater_query_redirects(self):
        for rid in ("falls-lake", "jordan-lake", "neuse-river"):
            status, _, headers = self._req("/?region=" + rid)
            self.assertEqual(status, 303, rid)
            self.assertEqual(headers.get("location"), "/lake?region=" + rid)
        status, body, _ = self._req("/?region=falls-lake", env={"FRESHWATER_ENABLED": "0"})
        self.assertEqual(status, 200)
        self.assertIn(b"The Coastal Brief", body)

    def test_api_regions_stays_saltwater(self):
        status, body, _ = self._req("/api/regions")
        self.assertEqual(status, 200)
        self.assertNotIn(b"falls-lake", body)
        self.assertNotIn(b"jordan-lake", body)
        self.assertNotIn(b"neuse-river", body)

    def test_dashboard_js_lists_freshwater_links(self):
        js = Path(__file__).resolve().parents[1].joinpath("dashboard.js").read_text()
        self.assertNotIn("Coming soon", js)
        self.assertIn("/lake?region=", js)
        for rid in ("falls-lake", "jordan-lake", "neuse-river"):
            self.assertIn(rid, js)


if __name__ == "__main__":
    unittest.main()
