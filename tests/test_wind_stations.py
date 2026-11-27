"""Phase B2 observed-station bundle: fixture-based, no live NOAA in CI."""
from __future__ import annotations

import json
import threading
import unittest
from datetime import datetime, timedelta, timezone
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock
from urllib.request import Request, urlopen
from urllib.error import HTTPError

import server
import wind_stations

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 11, 26, 22, 17, tzinfo=timezone.utc)  # 5:17 PM ET, matching the plan sample clock

NDBC_BULK = """#STN     LAT      LON  YYYY MM DD hh mm  WDIR WSPD  GST WVHT
41025   35.026  -75.380 2026 11 26 21 30   230 15.0 19.0    MM
41064   34.207  -76.949 2026 11 26 21 08   240 15.0 22.1    MM
41038   34.141  -77.715 2026 11 26 21 08   210 14.0 18.0    MM
41013   33.436  -77.764 2026 11 26 21 30   240 14.0 16.0    MM
CLKN7   34.611  -76.528 2026 11 26 21 30   230  9.3 14.4    MM
MBNN7   34.171  -77.824 2026 11 26 21 30   240  6.7 10.8    MM
MBIN7   34.091  -77.868 2026 11 26 21 30   250  7.2 11.3    MM
"""


def _coops(speed, gust, direc, t="2026-11-26 22:12"):
    return json.dumps({"data": [{"t": t, "s": str(speed) if speed is not None else "", "g": str(gust) if gust is not None else "", "d": str(direc) if direc is not None else ""}]}).encode()


def _nws(speed_kt=None, gust_kt=None, direc=None, ts="2026-11-26T21:50:00+00:00"):
    def prop(kt, unit="kt"):
        if kt is None:
            return {"value": None, "unitCode": "unit:kn"}
        return {"value": kt, "unitCode": "unit:kn"}
    return json.dumps({"properties": {
        "timestamp": ts,
        "windSpeed": prop(speed_kt),
        "windGust": prop(gust_kt),
        "windDirection": {"value": direc, "unitCode": "unit:degree_(angle)"},
    }}).encode()


def _fetch_map(now_bulk=NDBC_BULK, coops=None, nws=None, drop=(), delay=None):
    """Return a (url)->(status, body) fixture fetcher."""
    coops = coops or {}
    nws = nws or {}

    def fetch(url: str):
        if delay:
            delay()
        if any(s in url for s in drop):
            return 502, b""
        if "latest_obs/latest_obs.txt" in url:
            return 200, now_bulk.encode()
        if "latest_obs/" in url and url.endswith(".txt"):
            return 404, b""
        if "tidesandcurrents.noaa.gov" in url or "api.tidesandcurrents.noaa.gov" in url:
            for sid, body in coops.items():
                if "station=%s" % sid in url or "station=%s&" % sid in url:
                    return 200, body
            return 404, b""
        if "api.weather.gov/stations/" in url:
            sid = url.rsplit("/stations/", 1)[1].split("/")[0]
            if sid in nws:
                return 200, nws[sid]
            return 404, b""
        return 404, b""
    return fetch


DEFAULT_COOPS = {
    "8651370": _coops(22.16, 28, 199),
    "8652587": _coops(25.08, 30, 227),
    "8654467": _coops(15.16, 21, 235),
    "8656483": _coops(16.91, 30, 237),
    "8658163": _coops(21.97, 26, 228),
    "8661070": _coops(18.86, 25, 239),
}
DEFAULT_NWS = {
    "KONX": _nws(12.1, 20, 180, "2026-11-26T21:35:00+00:00"),
    "KFFA": _nws(8.0, 16, 190, "2026-11-26T21:35:00+00:00"),
    "KECG": _nws(15.0, None, 200, "2026-11-26T21:50:00+00:00"),
    "KMQI": _nws(None, 32.1, None, "2026-11-26T21:35:00+00:00"),
    "KHSE": _nws(15.0, 21, 230, "2026-11-26T21:50:00+00:00"),
    "KEWN": _nws(12.0, 19, 210, "2026-11-26T21:50:00+00:00"),
    "KMRH": _nws(None, 31.0, None, "2026-11-26T21:50:00+00:00"),
    "KNCA": _nws(13.0, 25.1, 10, "2026-11-25T19:56:00+00:00"),  # > 12 h
    "KILM": _nws(13.0, None, 230, "2026-11-26T21:50:00+00:00"),
    "KSUT": _nws(20.0, 28, 220, "2026-11-26T21:35:00+00:00"),
    "KCRE": _nws(13.0, None, 240, "2026-11-26T21:50:00+00:00"),
    "KNKT": _nws(None, None, None, "2026-11-26T21:15:00+00:00"),
    "KNJM": _nws(None, None, None, "2026-11-26T21:05:00+00:00"),
}


class Catalog(unittest.TestCase):
    def test_required_ids_present_and_twins_dropped(self):
        ids = {s["id"] for s in wind_stations.catalog_stations()}
        for sid in ("41025", "41064", "41038", "41013", "CLKN7", "8651370", "8652587",
                    "8654467", "8656483", "8658163", "MBNN7", "MBIN7",
                    "KONX", "KFFA", "KHSE", "KEWN", "KILM", "KSUT", "KMQI", "KMRH", "KNCA"):
            self.assertIn(sid, ids, sid)
        dropped = wind_stations.dropped_ids()
        for twin in ("DUKN7", "ORIN7", "HCGN7", "BFTN7", "JMPN7", "MROS1", "WLON7", "8658120"):
            self.assertIn(twin, dropped, twin)
            self.assertNotIn(twin, ids, twin)
        # Wave- and tide-only IDs stay out.
        for sid in ("41110", "41108", "8652226", "8657419", "TEC2837"):
            self.assertNotIn(sid, ids)

    def test_41064_window_lengthens_to_130(self):
        meta = next(s for s in wind_stations.catalog_stations() if s["id"] == "41064")
        self.assertEqual(meta["staleAfterMin"], 130)
        self.assertEqual(wind_stations._stale_min(meta), 130)

    def test_harbor_window_is_45(self):
        for sid in ("8652587", "8654467", "8656483"):
            meta = next(s for s in wind_stations.catalog_stations() if s["id"] == sid)
            self.assertEqual(meta["kindWind"], "harborWind")
            self.assertEqual(wind_stations._stale_min(meta), 45)


class Bundle(unittest.TestCase):
    def setUp(self):
        wind_stations.reset_cache()

    def _assemble(self, **kw):
        fetch = _fetch_map(
            coops=kw.get("coops", DEFAULT_COOPS),
            nws=kw.get("nws", DEFAULT_NWS),
            now_bulk=kw.get("bulk", NDBC_BULK),
            drop=kw.get("drop", ()),
            delay=kw.get("delay"),
        )
        return wind_stations.assemble(now=kw.get("now", NOW), fetch=fetch, budget_s=kw.get("budget_s", 3.5))

    def _by_id(self, payload):
        return {s["id"]: s for s in payload["stations"]}

    def test_fresh_schema_and_frying_pan(self):
        g = self._assemble()
        self.assertTrue(g["ok"])
        self.assertEqual(g["kind"], "observed")
        self.assertNotIn("forecastHour", g)
        self.assertNotIn("u", g)
        blob = json.dumps(g)
        self.assertNotIn("GFS", blob)
        self.assertNotIn("HRRR", blob)
        self.assertNotIn("PARTIAL", blob)
        self.assertNotIn("backup", blob.lower())
        fp = self._by_id(g)["41013"]
        self.assertEqual(fp["name"], "Frying Pan Shoals")
        self.assertEqual(fp["kind"], "observed")
        self.assertEqual(fp["status"], "fresh")
        self.assertEqual(fp["source"], "NOAA NDBC")
        self.assertIsNotNone(fp["observedAt"])
        self.assertTrue(fp["observedAt"].endswith("Z"))
        self.assertAlmostEqual(fp["wind"]["speedKt"], 27.2, places=0)
        self.assertAlmostEqual(fp["wind"]["gustKt"], 31.1, places=0)
        self.assertEqual(fp["wind"]["dirDeg"], 240.0)
        self.assertEqual(fp["wind"]["dirCompass"], "WSW")
        self.assertEqual(fp["staleAfterMin"], 75)
        duck = self._by_id(g)["8651370"]
        self.assertEqual(duck["status"], "fresh")
        self.assertEqual(duck["source"], "NOAA NOS CO-OPS")
        self.assertEqual(duck["wind"]["speedKt"], 22.2)
        self.assertEqual(duck["observedAt"], "2026-11-26T22:12:00Z")

    def test_gust_only_never_invents_speed(self):
        g = self._assemble()
        for sid in ("KMQI", "KMRH"):
            row = self._by_id(g)[sid]
            self.assertEqual(row["status"], "gust_only", sid)
            self.assertIsNone(row["wind"]["speedKt"])
            self.assertIsNotNone(row["wind"]["gustKt"])
            self.assertGreater(row["wind"]["gustKt"], 0)

    def test_unavailable_older_than_12_hours_drops_speed(self):
        row = self._by_id(self._assemble())["KNCA"]
        self.assertEqual(row["status"], "unavailable")
        self.assertIsNone(row["wind"]["speedKt"])
        self.assertIsNone(row["wind"]["gustKt"])
        self.assertEqual(row["observedAt"], "2026-11-25T19:56:00Z")

    def test_stale_keeps_numbers(self):
        # 90 min old wind on a 75-min window, still under 12 h.
        t = (NOW - timedelta(minutes=90)).strftime("%Y-%m-%d %H:%M")
        coops = dict(DEFAULT_COOPS)
        coops["8651370"] = _coops(10, 12, 180, t)
        row = self._by_id(self._assemble(coops=coops))["8651370"]
        self.assertEqual(row["status"], "stale")
        self.assertEqual(row["wind"]["speedKt"], 10.0)
        self.assertEqual(row["wind"]["gustKt"], 12.0)

    def test_41064_130_min_window_still_fresh_at_70(self):
        row = self._by_id(self._assemble())["41064"]
        self.assertEqual(row["staleAfterMin"], 130)
        self.assertEqual(row["status"], "fresh")
        self.assertAlmostEqual(row["ageMin"], 69, delta=2)

    def test_dedupe_not_in_payload(self):
        ids = [s["id"] for s in self._assemble()["stations"]]
        for twin in ("DUKN7", "ORIN7", "HCGN7", "BFTN7", "JMPN7", "MROS1"):
            self.assertNotIn(twin, ids)

    def test_no_hatteras_backup_substitution(self):
        # Diamond Shoals missing does not inherit USCG Hatteras 15 kt.
        g = self._assemble(bulk=NDBC_BULK.replace("41025", "XXXXX"))
        rows = self._by_id(g)
        self.assertEqual(rows["41025"]["status"], "unavailable")
        self.assertIsNone(rows["41025"]["wind"]["speedKt"])
        self.assertEqual(rows["8654467"]["status"], "fresh")
        self.assertEqual(rows["8654467"]["wind"]["speedKt"], 15.2)
        self.assertNotEqual(rows["41025"]["wind"]["speedKt"], rows["8654467"]["wind"]["speedKt"])

    def test_timeout_partial_failure_uses_last_good(self):
        # First call succeeds and seeds last-good.
        first = self._assemble()
        self.assertTrue(first["ok"])
        duck0 = self._by_id(first)["8651370"]["wind"]["speedKt"]
        # Second call: every upstream fails immediately; last-good is served.
        def dead(_url):
            return 502, b""
        second = wind_stations.assemble(now=NOW + timedelta(minutes=1), fetch=dead, budget_s=0.2)
        self.assertTrue(second["ok"])
        self.assertTrue(second.get("staleCache"))
        duck = self._by_id(second)["8651370"]
        self.assertEqual(duck["wind"]["speedKt"], duck0)
        self.assertTrue(duck.get("fromCache") or second.get("staleCache"))

    def test_feed_down_without_cache_is_ok_false(self):
        wind_stations.reset_cache()
        g = wind_stations.assemble(now=NOW, fetch=lambda url: (502, b""), budget_s=0.2)
        self.assertFalse(g["ok"])
        self.assertEqual(g["error"], "Observed stations unavailable right now.")
        self.assertNotIn("speedKt", json.dumps({k: v for k, v in g.items() if k != "stations"}))
        # Stations may be listed as unavailable, but no invented speeds.
        for s in g["stations"]:
            self.assertEqual(s["status"], "unavailable")
            self.assertIsNone(s["wind"]["speedKt"])

    def test_failure_does_not_touch_windgrid(self):
        import windgrid
        # A broken station assemble must not be able to mutate the grid cache.
        before = dict(windgrid._cache)
        wind_stations.assemble(now=NOW, fetch=lambda url: (_ for _ in ()).throw(RuntimeError("boom")), budget_s=0.2)
        # assemble catches inner errors per-source; force a top-level throw via fetch during get:
        self.assertEqual(windgrid._cache, before)


class Route(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.base = "http://127.0.0.1:%d" % cls.httpd.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def setUp(self):
        server.API_LIMITS.reset()

    def _get(self, path, headers=None):
        req = Request(self.base + path, headers=dict(headers or {}))
        try:
            with urlopen(req, timeout=10) as r:
                return r.status, {k.lower(): v for k, v in r.headers.items()}, r.read()
        except HTTPError as e:
            return e.code, {k.lower(): v for k, v in e.headers.items()}, e.read()

    def test_cache_control_and_schema(self):
        fake = {
            "ok": True, "kind": "observed", "staleCache": False,
            "stations": [{"id": "41013", "kind": "observed", "status": "fresh",
                          "wind": {"speedKt": 27.2, "gustKt": 31.1, "dirDeg": 240, "dirCompass": "WSW"}}],
        }
        with mock.patch.object(wind_stations, "assemble", return_value=fake):
            st, h, body = self._get("/api/wind-stations")
        self.assertEqual(st, 200)
        self.assertIn("max-age=90", h.get("cache-control", ""))
        data = json.loads(body)
        self.assertTrue(data["ok"])
        self.assertEqual(data["kind"], "observed")
        self.assertEqual(data["stations"][0]["id"], "41013")

    def test_rate_limit_matches_wind_grid(self):
        fake = {"ok": True, "kind": "observed", "staleCache": False, "stations": []}
        hdr = {"X-Forwarded-For": "203.0.113.44"}
        with mock.patch.object(wind_stations, "assemble", return_value=fake):
            for i in range(server.API_WIND_GRID_LIMIT):
                self.assertEqual(self._get("/api/wind-stations", headers=hdr)[0], 200, i)
            st, h, body = self._get("/api/wind-stations", headers=hdr)
        self.assertEqual(st, 429)
        self.assertGreaterEqual(int(h.get("retry-after") or 0), 1)
        self.assertEqual(json.loads(body)["reason"], "rate_limit")
        # The grid bucket is independent — a station 429 must not block /api/wind-grid.
        with mock.patch.object(server.windgrid, "latest_grid", return_value={"ok": True, "ahead": 0, "u": [], "v": []}):
            self.assertEqual(self._get("/api/wind-grid", headers=hdr)[0], 200)

    def test_feed_down_is_502_and_leaves_grid_alone(self):
        fake = {"ok": False, "kind": "observed", "error": "Observed stations unavailable right now."}
        with mock.patch.object(wind_stations, "assemble", return_value=fake), \
             mock.patch.object(server.windgrid, "latest_grid", return_value={"ok": True, "ahead": 0, "u": [1], "v": [2]}) as grid:
            st, h, body = self._get("/api/wind-stations")
            self.assertEqual(st, 502)
            self.assertEqual(json.loads(body)["error"], "Observed stations unavailable right now.")
            gst, _, gbody = self._get("/api/wind-grid")
        self.assertEqual(gst, 200)
        self.assertEqual(json.loads(gbody)["u"], [1])
        self.assertTrue(grid.called)


if __name__ == "__main__":
    unittest.main()
