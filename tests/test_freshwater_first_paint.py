"""t455u/t456u freshwater first-paint: immediate HTML, single-flight, backoff, retry button."""
from __future__ import annotations

import json
import os
import sys
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
from http.client import HTTPConnection
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import freshwater  # noqa: E402
import sprint_home  # noqa: E402

NOW = datetime(2026, 11, 24, 18, 30, tzinfo=timezone.utc)
ROOT = Path(__file__).resolve().parents[1]


def _pt(age_h, value):
    return (NOW - timedelta(hours=age_h), value)


def _clear():
    freshwater.reset_caches()


def _payload_falls():
    t = (NOW - timedelta(minutes=20)).isoformat()
    return {
        "ok": True,
        "generatedAt": NOW.isoformat(),
        "region": {"id": "falls-lake", "name": "Falls Lake", "area": "Falls Lake",
                   "waterType": "freshwater", "instrumentSet": "freshwater-lake"},
        "lake": {"usgs": "02087182", "kind": "observed", "datum": "NGVD29",
                 "guideCurveFt": 251.5,
                 "elevation": {"value": 250.12, "time": t, "stale": False},
                 "vsGuideFt": -1.38},
        "waterTemp": {"kind": "observed", "status": "ok", "c": 12.0, "f": 53.6, "time": t, "stale": False},
        "rain": {"status": "ok", "last24In": 0.0, "time": t, "stale": False},
        "release": {"usgs": "02087183", "tileTitle": "Release", "kind": "observed",
                    "flowCfs": {"value": 80.0, "time": t, "stale": False}, "stageFt": None},
        "inflows": [
            {"usgs": "02085070", "label": "Eno River near Durham", "kind": "observed",
             "flowCfs": {"value": 40.0, "time": t, "stale": False}},
            {"usgs": "02085500", "label": "Flat River at Bahama", "kind": "observed",
             "flowCfs": {"value": 30.0, "time": t, "stale": False}},
        ],
        "river": [
            {"usgs": "02087500", "label": "Neuse River near Clayton", "kind": "observed",
             "flowCfs": {"value": 90.0, "time": t, "stale": False}},
            {"usgs": "02087570", "label": "Neuse River at Smithfield", "kind": "observed",
             "stageOnly": True, "stageFt": {"value": 3.2, "time": t, "stale": False}},
            {"usgs": "02089000", "label": "Neuse River near Goldsboro", "kind": "observed",
             "flowCfs": {"value": 120.0, "time": t, "stale": False}},
        ],
        "forecast": {"status": "ok", "office": "NWS", "updated": t,
                     "periods": [{"name": "This Afternoon", "short": "Sunny", "detail": "Sunny"}]},
        "alerts": {"status": "ok", "items": []},
        "links": [], "staleRuleH": 3,
    }


class LoadingShell(unittest.TestCase):
    def setUp(self):
        _clear()

    def tearDown(self):
        _clear()

    def test_cold_home_html_is_immediate_with_loading_copy(self):
        def slow(*a, **k):
            time.sleep(30)
            return 200, _payload_falls()

        with patch.object(freshwater, "ensure_refresh", side_effect=lambda rid: threading.Event()):
            # model still calls ensure_refresh; do not start a 30s assemble
            t0 = time.time()
            # But peek is empty, so model should return loading without waiting.
            data = sprint_home.page("hybrid", "falls-lake", public=True)
            elapsed = time.time() - t0
        html = data.decode("utf-8")
        self.assertLess(elapsed, 2.0, "cold first HTML must not wait on upstream: %.3fs" % elapsed)
        self.assertIn("Loading official readings…", html)
        self.assertIn('data-fresh-pending="1"', html)
        self.assertIn('data-fresh-region="falls-lake"', html)
        self.assertIn('aria-busy="true"', html)
        self.assertIn("/fresh-home.js", html)
        self.assertIn('id="conditions"', html)
        self.assertNotIn("250.12", html)
        self.assertNotIn("t-kind", html.split('id="conditions"')[1][:4000] if False else html.split("<div class=\"t t-lake")[1][:400] if "<div class=\"t t-lake" in html else "")
        # Loading tiles must not show an Observed chip implying a value.
        section = html.split('id="conditions"', 1)[1][:8000]
        self.assertNotIn(">Observed<", section)
        self.assertIn("Lake level", section)

    def test_warm_home_html_shows_readings_not_pending(self):
        payload = _payload_falls()
        freshwater._ASSEMBLED["falls-lake"] = (time.time(), payload)
        t0 = time.time()
        data = sprint_home.page("hybrid", "falls-lake", public=True)
        elapsed = time.time() - t0
        html = data.decode("utf-8")
        self.assertLess(elapsed, 2.0)
        self.assertIn("250.12", html)
        self.assertIn("Observed", html)
        self.assertNotIn('data-fresh-pending="1"', html)
        self.assertNotIn("/fresh-home.js", html)
        self.assertNotIn("Loading official readings…", html)

    def test_loading_model_has_reserved_slots_no_numerals(self):
        m = sprint_home.fresh_loading_model("jordan-lake")
        self.assertTrue(m["pending"])
        self.assertTrue(m["ok"])
        self.assertEqual(m["region"]["id"], "jordan-lake")
        self.assertEqual(m["region"]["name"], "Jordan Lake")
        names = [t["name"] for t in m["tiles"]]
        self.assertIn("Lake level", names)
        self.assertTrue(all(t["state"] == "off" and t["off"] == sprint_home.LOADING_OFF and not t.get("num") for t in m["tiles"]))
        html = sprint_home.conditions_html(m, variant="hybrid", public=True)
        self.assertIn("Loading official readings…", html)
        self.assertIn("min-height", Path(ROOT / "preview/sprint-home/hybrid.css").read_text())
        self.assertNotIn("216.0", html)

    def test_neuse_loading_uses_river_slots_not_lake_level(self):
        m = sprint_home.fresh_loading_model("neuse-river")
        names = [t["name"] for t in m["tiles"]]
        self.assertNotIn("Lake level", names)
        self.assertTrue(any("Smithfield" in n or "stage" in n.lower() or n for n in names))
        # Config labels, no invented station names as readings
        self.assertTrue(all(not t.get("num") for t in m["tiles"]))

    def test_saltwater_path_untouched(self):
        with patch("conditions.assemble", return_value=(200, {
            "ok": True, "region": {"id": "crystal-coast", "name": "Crystal Coast", "waterType": "saltwater"},
            "generatedAt": NOW.isoformat(),
            "wind": {"status": "unavailable"}, "waterTemp": {}, "tides": {}, "alerts": {"status": "ok", "items": []},
        })) as asm:
            t0 = time.time()
            data = sprint_home.page("hybrid", "crystal-coast", public=True)
            elapsed = time.time() - t0
        html = data.decode("utf-8")
        self.assertLess(elapsed, 2.0)
        self.assertNotIn("/fresh-home.js", html)
        self.assertNotIn('data-fresh-pending="1"', html)
        self.assertNotIn("data-fresh-region", html)
        asm.assert_called()


class AssembleBehavior(unittest.TestCase):
    def setUp(self):
        _clear()

    def tearDown(self):
        _clear()

    def _patch_sources(self, iv=None, daily=None, slow=None, fail=None):
        def fake_iv(sites, params, period="P1D"):
            if slow:
                time.sleep(slow)
            if fail == "iv":
                raise RuntimeError("usgs down")
            return iv or {}, {}

        def fake_daily(site, day):
            if slow:
                time.sleep(slow)
            if fail == "stats":
                raise RuntimeError("stats down")
            return daily

        return (
            patch("freshwater.datetime") if False else patch("freshwater.usgs_iv", side_effect=fake_iv),
            patch("freshwater.usgs_daily_stats", side_effect=fake_daily),
            patch("freshwater.nwps", side_effect=lambda lid: {"lid": lid, "status": "ok", "name": lid, "floodStages": {}, "url": ""}),
            patch("freshwater.qpf_block", return_value={"status": "unavailable", "kind": "forecast"}),
            patch("freshwater.alerts_point", side_effect=(RuntimeError("alerts") if fail == "alerts" else lambda *a: {"status": "ok", "items": []})),
            patch("freshwater.usace_guide_check", return_value={"status": "ok", "matches": True, "values": [251.5]}),
            patch("conditions.forecast_block", side_effect=(RuntimeError("fc") if fail == "forecast" else lambda cfg: {
                "status": "ok", "updated": NOW.isoformat(),
                "periods": [{"name": "This Afternoon", "tempF": 68, "short": "Sunny", "windDir": "SW", "windMph": "5 mph"}] * 4,
                "sourceUrl": "https://forecast.weather.gov/",
            })),
        )

    def test_failed_source_returns_partial_not_invented(self):
        t = _pt(0.4, 250.12)
        iv7 = {("02087182", "62614"): [t], ("02087182", "62615"): [_pt(0.4, 249.5)]}
        ivq = {}

        def fake_iv(sites, params, period="P1D"):
            if period == "P7D":
                return iv7, {"02087182": "FALLS LAKE"}
            return ivq, {}

        with patch("freshwater.usgs_iv", side_effect=fake_iv), \
                patch("freshwater.usgs_daily_stats", return_value=None), \
                patch("freshwater.nwps", return_value={"lid": "FLLN7", "status": "unavailable"}), \
                patch("freshwater.qpf_block", return_value={"status": "unavailable", "kind": "forecast"}), \
                patch("freshwater.alerts_point", side_effect=RuntimeError("alerts down")), \
                patch("freshwater.usace_guide_check", return_value={"status": "unavailable"}), \
                patch("conditions.forecast_block", side_effect=RuntimeError("forecast down")):
            status, body = freshwater.assemble("falls-lake", wait=5)
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])
        self.assertEqual(body["lake"]["elevation"]["value"], 250.12)
        self.assertEqual(body["alerts"]["status"], "unavailable")
        self.assertEqual(body["forecast"]["status"], "unavailable")
        self.assertFalse(body["alerts"].get("items"))
        # Never invent an alert-clear sentence in the payload
        self.assertNotEqual(body["alerts"].get("status"), "ok")

    def test_slow_source_is_bounded_not_thirty_seconds(self):
        def slow_iv(*a, **k):
            time.sleep(30)
            return {}, {}

        t0 = time.time()
        with patch("freshwater.usgs_iv", side_effect=slow_iv), \
                patch("freshwater.usgs_daily_stats", return_value=None), \
                patch("freshwater.nwps", return_value={"status": "unavailable"}), \
                patch("freshwater.qpf_block", return_value={"status": "unavailable", "kind": "forecast"}), \
                patch("freshwater.alerts_point", return_value={"status": "ok", "items": []}), \
                patch("freshwater.usace_guide_check", return_value={"status": "unavailable"}), \
                patch("conditions.forecast_block", return_value={"status": "unavailable"}):
            status, body = freshwater.assemble("jordan-lake", wait=freshwater.USER_DEADLINE)
        elapsed = time.time() - t0
        self.assertEqual(status, 200)
        self.assertLess(elapsed, 16, "API cap ~20s, first-wave bound 12s, got %.2fs" % elapsed)
        # No invented lake elevation
        el = (body.get("lake") or {}).get("elevation")
        self.assertTrue(el is None or el.get("value") is None)

    def test_single_flight_shares_one_refresh(self):
        calls = {"n": 0}
        gate = threading.Event()

        def fake_iv(*a, **k):
            calls["n"] += 1
            gate.wait(timeout=2)
            return {}, {}

        with patch("freshwater.usgs_iv", side_effect=fake_iv), \
                patch("freshwater.usgs_daily_stats", return_value=None), \
                patch("freshwater.nwps", return_value={"status": "unavailable"}), \
                patch("freshwater.qpf_block", return_value={"status": "unavailable", "kind": "forecast"}), \
                patch("freshwater.alerts_point", return_value={"status": "ok", "items": []}), \
                patch("freshwater.usace_guide_check", return_value={"status": "unavailable"}), \
                patch("conditions.forecast_block", return_value={"status": "unavailable"}):
            results = []

            def run():
                results.append(freshwater.assemble("falls-lake", wait=5))

            threads = [threading.Thread(target=run) for _ in range(5)]
            for th in threads:
                th.start()
            time.sleep(0.2)
            started = calls["n"]
            gate.set()
            for th in threads:
                th.join(timeout=6)
        self.assertTrue(all(st == 200 for st, _ in results))
        # One in-flight assemble issues iv twice (P7D + P1D), not once per waiter.
        self.assertLessEqual(started, 2)
        self.assertLessEqual(calls["n"], 2)
        self.assertGreaterEqual(calls["n"], 1)

    def test_changing_region_does_not_reuse_other_cache(self):
        freshwater._ASSEMBLED["falls-lake"] = (time.time(), _payload_falls())
        m = sprint_home.model("jordan-lake")
        self.assertEqual(m["region"]["id"], "jordan-lake")
        self.assertTrue(m.get("pending") or (m.get("region") or {}).get("id") == "jordan-lake")
        self.assertNotIn("250.12", json.dumps(m))
        self.assertNotEqual(m["region"]["name"], "Falls Lake")


class AlertMerge(unittest.TestCase):
    """c610f2f rules must stay: merge only on identical (event, onset, end); drop test/replaced."""

    def test_alerts_point_merges_identical_and_keeps_distinct(self):
        def feat(event, onset, ends, area, status="Actual", replaced=False, cancelled=False):
            p = {"event": event, "onset": onset, "ends": ends, "expires": ends,
                 "status": status, "severity": "Moderate", "areaDesc": area, "headline": event}
            if replaced:
                p["replacedBy"] = "https://api.weather.gov/alerts/x"
            if cancelled:
                p["messageType"] = "Cancel"
            return {"properties": p}

        feed = {"features": [
            feat("Flood Watch", "2026-11-24T12:00:00-05:00", "2026-11-25T00:00:00-05:00", "Wake"),
            feat("Flood Watch", "2026-11-24T12:00:00-05:00", "2026-11-25T00:00:00-05:00", "Durham"),
            feat("Flood Watch", "2026-11-24T18:00:00-05:00", "2026-11-25T00:00:00-05:00", "Franklin"),  # distinct onset
            feat("Winter Storm Warning", "2026-11-24T12:00:00-05:00", "2026-11-25T00:00:00-05:00", "Wake"),
            feat("Flood Watch", "2026-11-24T12:00:00-05:00", "2026-11-25T00:00:00-05:00", "Test County", status="Test"),
            feat("Flood Watch", "2026-11-24T12:00:00-05:00", "2026-11-25T00:00:00-05:00", "Old", replaced=True),
        ]}
        with patch.object(freshwater, "_get_json", return_value=feed):
            out = freshwater.alerts_point(35.94, -78.58)
        self.assertEqual(out["status"], "ok")
        events = [(it["event"], it["ends"]) for it in out["items"]]
        floods = [it for it in out["items"] if it["event"] == "Flood Watch"]
        # Two Flood Watches remain (different onset); identical pair merged with unioned areas.
        self.assertEqual(len(floods), 2)
        areas = " ".join(f["areas"] or "" for f in floods)
        self.assertIn("Wake", areas)
        self.assertIn("Durham", areas)
        self.assertIn("Franklin", areas)
        self.assertNotIn("Test County", areas)
        self.assertNotIn("Old", areas)
        self.assertEqual(len([it for it in out["items"] if it["event"] == "Winter Storm Warning"]), 1)


class StaleJs(unittest.TestCase):
    def test_should_apply_ignores_stale_region_response(self):
        js = (ROOT / "fresh-home.js").read_text()
        self.assertIn("shouldApply", js)
        self.assertIn("replaceWith", js)
        self.assertIn("pagehide", js)
        self.assertIn("retry=1", js)
        self.assertIn("Retry readings", js)
        src = js + """
        const elFalls = { getAttribute: (k) => k === "data-fresh-region" ? "falls-lake" : null };
        const elJordan = { getAttribute: (k) => k === "data-fresh-region" ? "jordan-lake" : null };
        const fallsData = { region: { id: "falls-lake" }, html: "<section id='conditions'>falls</section>" };
        const jordanData = { region: { id: "jordan-lake" }, html: "<section id='conditions'>jordan</section>" };
        const neuseData = { region: { id: "neuse-river" }, html: "<section id='conditions'>neuse</section>" };
        const cases = [
          ["falls-lake", elFalls, fallsData, true],
          ["falls-lake", elJordan, fallsData, false],
          ["jordan-lake", elFalls, jordanData, false],
          ["neuse-river", elJordan, neuseData, false],
          ["jordan-lake", elJordan, jordanData, true],
          ["falls-lake", elFalls, { region: { id: "falls-lake" } }, false],
        ];
        for (const [rid, el, data, ok] of cases) {
          const got = FreshHome.shouldApply(rid, el, data);
          if (got !== ok) {
            console.log(JSON.stringify({rid, ok, got}));
            process.exit(2);
          }
        }
        console.log("ok");
        """
        import subprocess
        proc = subprocess.run(["node", "-e", src], cwd=str(ROOT), capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("ok", proc.stdout)


class NavAndWaterSwitch(unittest.TestCase):
    def setUp(self):
        _clear()

    def tearDown(self):
        _clear()
        os.environ.pop("NAV_V2", None)

    def test_water_switch_stays_above_conditions_with_nav_on_or_off(self):
        # NAV off: conditions is in main; no .cbw
        data = sprint_home.page("hybrid", "falls-lake", public=True)
        import nav_v2
        off = data.decode()
        self.assertIn('id="conditions"', off)
        self.assertNotIn('class="cbw"', off)
        os.environ["NAV_V2"] = "1"
        on = nav_v2.apply(data, "/?region=falls-lake").decode()
        # switch before conditions
        i_sw = on.find('class="cbw"')
        i_cg = on.find('id="conditions"')
        self.assertGreater(i_sw, 0)
        self.assertGreater(i_cg, i_sw)
        # Fill script still only mentions #conditions, not .cbw
        js = (ROOT / "fresh-home.js").read_text()
        self.assertIn("#conditions", js)
        self.assertNotIn('querySelector(".cbw")', js)
        self.assertIn("must not be replaced", js)
        # Retry-state page (partial official data) also keeps the switch above #conditions.
        partial = dict(_payload_falls())
        partial["release"] = {**(partial["release"] or {}), "flowCfs": None, "stageFt": None}
        freshwater._ASSEMBLED["falls-lake"] = (time.time(), partial)
        retry_page = sprint_home.page("hybrid", "falls-lake", public=True)
        os.environ["NAV_V2"] = "1"
        on_retry = nav_v2.apply(retry_page, "/?region=falls-lake").decode()
        self.assertIn('id="fresh-retry"', on_retry)
        self.assertIn("/fresh-home.js", on_retry)
        self.assertGreater(on_retry.find('id="conditions"'), on_retry.find('class="cbw"'))
        os.environ.pop("NAV_V2", None)
        off_retry = retry_page.decode()
        self.assertIn('id="fresh-retry"', off_retry)
        self.assertNotIn('class="cbw"', off_retry)


class FirstPaintHttp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import server
        cls.httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        cls.host, cls.port = cls.httpd.server_address

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def setUp(self):
        _clear()

    def tearDown(self):
        _clear()

    def _req(self, path, timeout=5):
        conn = HTTPConnection("127.0.0.1", self.port, timeout=timeout)
        conn.request("GET", path)
        resp = conn.getresponse()
        body = resp.read()
        headers = {k.lower(): v for k, v in resp.getheaders()}
        conn.close()
        return resp.status, body, headers

    def test_cold_http_first_html_under_two_seconds(self):
        with patch.object(freshwater, "ensure_refresh", return_value=threading.Event()):
            t0 = time.time()
            status, body, _ = self._req("/?region=falls-lake")
            elapsed = time.time() - t0
        self.assertEqual(status, 200)
        self.assertLess(elapsed, 2.0, "HTTP first HTML %.3fs" % elapsed)
        self.assertIn(b"Loading official readings", body)
        self.assertIn(b'data-sprint="hybrid"', body)
        self.assertIn(b"/fresh-home.js", body)

    def test_fresh_home_js_and_api_routes(self):
        status, body, _ = self._req("/fresh-home.js")
        self.assertEqual(status, 200)
        self.assertIn(b"shouldApply", body)
        freshwater._ASSEMBLED["jordan-lake"] = (time.time(), {
            **_payload_falls(),
            "region": {"id": "jordan-lake", "name": "Jordan Lake", "waterType": "freshwater",
                       "instrumentSet": "freshwater-lake"},
            "lake": {**_payload_falls()["lake"], "usgs": "02098197", "guideCurveFt": 216.0,
                     "elevation": {"value": 212.23, "time": NOW.isoformat(), "stale": False},
                     "vsGuideFt": -3.77},
        })
        status, body, _ = self._req("/api/fresh-home?region=jordan-lake")
        self.assertEqual(status, 200)
        payload = json.loads(body)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["region"]["id"], "jordan-lake")
        self.assertIn("212.23", payload["html"])
        self.assertIn('id="conditions"', payload["html"])
        self.assertNotIn("data-fresh-pending", payload["html"])
        # Falls numbers must not appear on the Jordan fragment
        self.assertNotIn("250.12", payload["html"])

    def test_kill_switch_hides_fresh_home_api(self):
        saved = os.environ.get("FRESHWATER_ENABLED")
        os.environ["FRESHWATER_ENABLED"] = "0"
        try:
            status, _, _ = self._req("/api/fresh-home?region=falls-lake")
            self.assertEqual(status, 404)
        finally:
            if saved is None:
                os.environ.pop("FRESHWATER_ENABLED", None)
            else:
                os.environ["FRESHWATER_ENABLED"] = saved

    def test_to_saltwater_is_not_a_fresh_pending_page(self):
        status, body, _ = self._req("/?region=crystal-coast")
        self.assertEqual(status, 200)
        self.assertNotIn(b'data-fresh-pending="1"', body)
        self.assertNotIn(b"/fresh-home.js", body)


def _fail_all_patches():
    return (
        patch("freshwater.usgs_iv", side_effect=RuntimeError("usgs down")),
        patch("freshwater.usgs_daily_stats", side_effect=RuntimeError("stats down")),
        patch("freshwater.nwps", return_value={"status": "unavailable"}),
        patch("freshwater.qpf_block", return_value={"status": "unavailable", "kind": "forecast"}),
        patch("freshwater.alerts_point", side_effect=RuntimeError("alerts down")),
        patch("freshwater.usace_guide_check", return_value={"status": "unavailable"}),
        patch("conditions.forecast_block", side_effect=RuntimeError("forecast down")),
    )


def _partial_payload():
    """Official lake level only; other configured sources unavailable."""
    body = freshwater.empty_payload("falls-lake")
    t = (NOW - timedelta(minutes=20)).isoformat()
    body["generatedAt"] = NOW.isoformat()
    body["partial"] = True
    body["lake"] = {
        "usgs": "02087182", "kind": "observed", "datum": "NGVD29", "guideCurveFt": 251.5,
        "elevation": {"value": 250.12, "time": t, "stale": False}, "vsGuideFt": -1.38,
    }
    body["alerts"] = {"status": "ok", "items": []}
    return body


class NegativeCache(unittest.TestCase):
    def setUp(self):
        _clear()

    def tearDown(self):
        _clear()

    def test_complete_failure_is_not_cached_at_success_ttl(self):
        calls = {"n": 0}

        def boom(*a, **k):
            calls["n"] += 1
            raise RuntimeError("usgs down")

        with patch("freshwater.usgs_iv", side_effect=boom), \
                patch("freshwater.usgs_daily_stats", side_effect=RuntimeError("stats down")), \
                patch("freshwater.nwps", return_value={"status": "unavailable"}), \
                patch("freshwater.qpf_block", return_value={"status": "unavailable"}), \
                patch("freshwater.alerts_point", side_effect=RuntimeError("alerts down")), \
                patch("freshwater.usace_guide_check", return_value={"status": "unavailable"}), \
                patch("conditions.forecast_block", side_effect=RuntimeError("forecast down")):
            status, body = freshwater.assemble("falls-lake", wait=5)
            n1 = calls["n"]
            self.assertEqual(status, 200)
            self.assertTrue(body.get("ok"))
            self.assertIsNone(freshwater.peek("falls-lake"))
            self.assertNotIn("falls-lake", freshwater._ASSEMBLED)
            self.assertIn("falls-lake", freshwater._FAILED)
            self.assertGreater(body.get("retryAfterS") or 0, 0)
            self.assertLessEqual(body["retryAfterS"], freshwater.FAIL_BACKOFF + 1)
            el = (body.get("lake") or {}).get("elevation")
            self.assertTrue(el is None or el.get("value") is None)

            # Immediate retry must not start another upstream attempt (backoff).
            status2, body2 = freshwater.assemble("falls-lake", force=True, wait=5)
            self.assertEqual(status2, 200)
            self.assertEqual(calls["n"], n1)
            self.assertGreater(body2.get("retryAfterS") or 0, 0)

            status3, _body3 = freshwater.assemble("falls-lake", wait=5)
            self.assertEqual(status3, 200)
            self.assertEqual(calls["n"], n1)

            # After backoff expires, a new full attempt is allowed.
            freshwater._FAILED["falls-lake"] = time.time() - freshwater.FAIL_BACKOFF - 1
            status4, _body4 = freshwater.assemble("falls-lake", force=True, wait=5)
            self.assertEqual(status4, 200)
            self.assertGreater(calls["n"], n1)
            self.assertIsNone(freshwater.peek("falls-lake"))

    def test_partial_success_is_cached_and_keeps_valid_sources(self):
        t = _pt(0.4, 250.12)
        iv7 = {("02087182", "62614"): [t], ("02087182", "62615"): [_pt(0.4, 249.5)]}

        def fake_iv(sites, params, period="P1D"):
            if period == "P7D":
                return iv7, {"02087182": "FALLS LAKE"}
            return {}, {}

        with patch("freshwater.usgs_iv", side_effect=fake_iv), \
                patch("freshwater.usgs_daily_stats", return_value=None), \
                patch("freshwater.nwps", return_value={"status": "unavailable"}), \
                patch("freshwater.qpf_block", return_value={"status": "unavailable"}), \
                patch("freshwater.alerts_point", return_value={"status": "ok", "items": []}), \
                patch("freshwater.usace_guide_check", return_value={"status": "unavailable"}), \
                patch("conditions.forecast_block", return_value={"status": "unavailable"}):
            status, body = freshwater.assemble("falls-lake", wait=8)
        self.assertEqual(status, 200)
        self.assertEqual(body["lake"]["elevation"]["value"], 250.12)
        self.assertEqual(body["alerts"]["status"], "ok")
        hit = freshwater.peek("falls-lake")
        self.assertIsNotNone(hit)
        self.assertEqual(hit["lake"]["elevation"]["value"], 250.12)
        self.assertTrue(freshwater.has_verified_data(hit))
        self.assertTrue(freshwater.missing_expected(hit))
        self.assertNotIn("falls-lake", freshwater._FAILED)

    def test_complete_failure_does_not_drop_or_restamp_valid_cache(self):
        payload = _payload_falls()
        stamp = time.time() - 30
        freshwater._ASSEMBLED["falls-lake"] = (stamp, payload)
        p0, p1, p2, p3, p4, p5, p6 = _fail_all_patches()
        with p0, p1, p2, p3, p4, p5, p6:
            status, body = freshwater.assemble("falls-lake", force=True, wait=5)
        self.assertEqual(status, 200)
        self.assertEqual(body["lake"]["elevation"]["value"], 250.12)
        self.assertEqual(body["alerts"]["status"], "ok")
        hit, age = freshwater.peek_age("falls-lake")
        self.assertEqual(hit["lake"]["elevation"]["value"], 250.12)
        # Original success timestamp is preserved (not rewritten as a new 5-min TTL).
        self.assertAlmostEqual(freshwater._ASSEMBLED["falls-lake"][0], stamp, places=2)
        self.assertIn("falls-lake", freshwater._FAILED)


class MergeAndRetry(unittest.TestCase):
    def setUp(self):
        _clear()

    def tearDown(self):
        _clear()

    def test_retry_fills_only_missing_and_keeps_newer_verified(self):
        old = _partial_payload()
        new = freshwater.empty_payload("falls-lake")
        older = (NOW - timedelta(hours=3)).isoformat()
        newer = (NOW - timedelta(minutes=20)).isoformat()
        new["lake"] = {
            "usgs": "02087182", "kind": "observed",
            "elevation": {"value": 249.00, "time": older, "stale": False},  # older, must not win
        }
        new["release"] = {
            "usgs": "02087183", "tileTitle": "Release", "kind": "observed",
            "flowCfs": {"value": 80.0, "time": newer, "stale": False}, "stageFt": None,
        }
        new["alerts"] = {"status": "unavailable", "items": []}
        merged = freshwater.merge_verified(old, new)
        self.assertEqual(merged["lake"]["elevation"]["value"], 250.12)
        self.assertEqual(merged["lake"]["elevation"]["time"], old["lake"]["elevation"]["time"])
        self.assertEqual(merged["release"]["flowCfs"]["value"], 80.0)
        # Failed alerts re-check must not drop a prior official "no alerts" result.
        self.assertEqual(merged["alerts"]["status"], "ok")

    def test_successful_alerts_recheck_replaces_previous_set(self):
        old = _payload_falls()
        old["alerts"] = {"status": "ok", "items": [
            {"event": "Flood Watch", "onset": "2026-11-24T12:00:00-05:00",
             "ends": "2026-11-25T00:00:00-05:00", "areas": "Wake", "severity": "Moderate"},
        ]}
        new = dict(old)
        new["alerts"] = {"status": "ok", "items": []}
        merged = freshwater.merge_verified(old, new)
        self.assertEqual(merged["alerts"]["status"], "ok")
        self.assertEqual(merged["alerts"]["items"], [])

    def test_jordan_missing_water_temp_sensor_is_not_retryable(self):
        body = freshwater.empty_payload("jordan-lake")
        t = NOW.isoformat()
        body["generatedAt"] = t
        body["lake"] = {"usgs": "02098197", "kind": "observed", "guideCurveFt": 216.0,
                        "elevation": {"value": 212.23, "time": t, "stale": False}}
        body["rain"] = {"status": "ok", "last24In": 0.0, "time": t, "stale": False}
        body["release"] = {"usgs": "02098198", "kind": "observed",
                           "flowCfs": {"value": 10.0, "time": t, "stale": False}}
        r = freshwater.regions()["jordan-lake"]
        body["inflows"] = [{
            "usgs": r["inflows"][0]["usgs"], "label": r["inflows"][0]["label"], "kind": "observed",
            "flowCfs": {"value": 5.0, "time": t, "stale": False},
        }]
        body["forecast"] = {"status": "ok", "periods": [{"name": "Today", "short": "Sunny"}]}
        body["alerts"] = {"status": "ok", "items": []}
        self.assertFalse(freshwater.missing_expected(body))

    def test_retry_button_on_unavailable_slots_not_on_loading_or_complete(self):
        pending = sprint_home.fresh_loading_model("falls-lake")
        html_pending = sprint_home.conditions_html(pending, variant="hybrid", public=True)
        self.assertNotIn("fresh-retry", html_pending)
        self.assertNotIn("Retry readings", html_pending)

        complete = sprint_home.fresh_model(_payload_falls())
        self.assertFalse(complete.get("canRetry"))
        html_ok = sprint_home.conditions_html(complete, variant="hybrid", public=True)
        self.assertNotIn("fresh-retry", html_ok)

        partial = sprint_home.fresh_model(_partial_payload())
        self.assertTrue(partial.get("canRetry"))
        html = sprint_home.conditions_html(partial, variant="hybrid", public=True)
        self.assertIn('id="fresh-retry"', html)
        self.assertIn('type="button"', html)
        self.assertIn("Retry readings", html)
        self.assertIn('aria-live="polite"', html)
        self.assertIn("cg-retry-status", html)
        self.assertIn('data-fresh-retry="1"', html)
        page = sprint_home.page("hybrid", "falls-lake", public=True)
        # page() peeks cache; seed it
        freshwater._ASSEMBLED["falls-lake"] = (time.time(), _partial_payload())
        page = sprint_home.page("hybrid", "falls-lake", public=True).decode()
        self.assertIn('id="fresh-retry"', page)
        self.assertIn("/fresh-home.js", page)
        self.assertNotIn("data-fresh-pending=", page)

    def test_retry_css_is_44px_and_before_night_wash(self):
        css = (ROOT / "preview/sprint-home/hybrid.css").read_text()
        night = css.index("/* Night only: one continuous wash")
        self.assertLess(css.index(".cg-retry"), night)
        self.assertIn("min-height:44px", css)
        self.assertIn("min-width:44px", css)
        # Night-strip rule must not gain height declarations (existing contract).
        self.assertNotIn("height:", css[night:])

    def test_rapid_retries_share_one_upstream_fetch(self):
        calls = {"n": 0}
        gate = threading.Event()
        t = _pt(0.4, 250.12)
        iv7 = {("02087182", "62614"): [t]}

        def fake_iv(sites, params, period="P1D"):
            calls["n"] += 1
            gate.wait(timeout=2)
            if period == "P7D":
                return iv7, {}
            return {}, {}

        freshwater._ASSEMBLED["falls-lake"] = (time.time(), _partial_payload())
        with patch("freshwater.usgs_iv", side_effect=fake_iv), \
                patch("freshwater.usgs_daily_stats", return_value=None), \
                patch("freshwater.nwps", return_value={"status": "unavailable"}), \
                patch("freshwater.qpf_block", return_value={"status": "unavailable"}), \
                patch("freshwater.alerts_point", return_value={"status": "ok", "items": []}), \
                patch("freshwater.usace_guide_check", return_value={"status": "unavailable"}), \
                patch("conditions.forecast_block", return_value={"status": "unavailable"}):
            results = []

            def run():
                results.append(freshwater.assemble("falls-lake", force=True, wait=5))

            threads = [threading.Thread(target=run) for _ in range(5)]
            for th in threads:
                th.start()
            time.sleep(0.2)
            started = calls["n"]
            gate.set()
            for th in threads:
                th.join(timeout=6)
        self.assertTrue(all(st == 200 for st, _ in results))
        self.assertLessEqual(started, 2)
        self.assertLessEqual(calls["n"], 2)
        # Verified lake level is still present; retry did not invent release if IV P1D was empty.
        for _st, body in results:
            self.assertEqual(body["lake"]["elevation"]["value"], 250.12)


class RetryHttp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import server
        cls.httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        cls.host, cls.port = cls.httpd.server_address

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def setUp(self):
        _clear()

    def tearDown(self):
        _clear()

    def _req(self, path, timeout=5):
        conn = HTTPConnection("127.0.0.1", self.port, timeout=timeout)
        conn.request("GET", path)
        resp = conn.getresponse()
        body = resp.read()
        conn.close()
        return resp.status, body

    def test_retry_query_bypasses_success_ttl_and_merges(self):
        freshwater._ASSEMBLED["falls-lake"] = (time.time(), _partial_payload())
        t = _pt(0.1, 80.0)

        def fake_iv(sites, params, period="P1D"):
            # P1D current conditions include the release gauge only (no lake, so lake stays from cache).
            if period == "P7D":
                return {}, {}
            return {("02087183", "00060"): [t]}, {}

        with patch("freshwater.usgs_iv", side_effect=fake_iv), \
                patch("freshwater.usgs_daily_stats", return_value=None), \
                patch("freshwater.nwps", return_value={"status": "unavailable"}), \
                patch("freshwater.qpf_block", return_value={"status": "unavailable"}), \
                patch("freshwater.alerts_point", return_value={"status": "ok", "items": []}), \
                patch("freshwater.usace_guide_check", return_value={"status": "unavailable"}), \
                patch("conditions.forecast_block", return_value={"status": "unavailable"}):
            status, body = self._req("/api/fresh-home?region=falls-lake&retry=1&public=1")
        self.assertEqual(status, 200)
        payload = json.loads(body)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["region"]["id"], "falls-lake")
        self.assertIn("250.12", payload["html"])
        self.assertIn("80", payload["html"])
        # Region switching: a Jordan request must not return Falls HTML,
        # including when a retry is requested (stale/other-region data is dropped).
        freshwater._ASSEMBLED["jordan-lake"] = (time.time(), {
            **_payload_falls(),
            "region": {"id": "jordan-lake", "name": "Jordan Lake", "waterType": "freshwater",
                       "instrumentSet": "freshwater-lake"},
            "lake": {"usgs": "02098197", "kind": "observed", "guideCurveFt": 216.0,
                     "elevation": {"value": 212.23, "time": NOW.isoformat(), "stale": False}},
        })
        p0, p1, p2, p3, p4, p5, p6 = _fail_all_patches()
        with p0, p1, p2, p3, p4, p5, p6:
            status, body = self._req("/api/fresh-home?region=jordan-lake&retry=1&public=1")
        payload = json.loads(body)
        self.assertEqual(status, 200)
        self.assertEqual(payload["region"]["id"], "jordan-lake")
        self.assertIn("212.23", payload["html"])
        self.assertNotIn("250.12", payload["html"])



if __name__ == "__main__":
    unittest.main()
