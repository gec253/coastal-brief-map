"""t461u freshwater V4: 45/50s timeouts, shared USGS flights, non-blocking stats."""
from __future__ import annotations

import sys
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import freshwater  # noqa: E402

NOW = datetime(2026, 11, 24, 21, 0, tzinfo=timezone.utc)
RIDS = ("falls-lake", "jordan-lake", "neuse-river")


def _clear():
    freshwater.reset_caches()


def _rain(t):
    return [(t - timedelta(hours=i), 0.0 if i else 0.01) for i in range(24, -1, -1)]


def _canned_iv(sites, params, period="P1D"):
    t = NOW - timedelta(minutes=20)
    out, names = {}, {}
    for site in sites:
        names[site] = site
        if period == "P7D":
            if site == "02087182":
                out[(site, "62614")] = [(t, 244.74)]
                out[(site, "62615")] = [(t, 244.1)]
                out[(site, "00010")] = [(t, 14.8)]
                out[(site, "00045")] = _rain(t)
            elif site == "02098197":
                out[(site, "62614")] = [(t, 211.94)]
                out[(site, "62615")] = [(t, 211.3)]
                out[(site, "00045")] = _rain(t)
        else:
            for p in params:
                if p == "00060":
                    out[(site, "00060")] = [(t, 30.4 if site == "02087183" else 100.0)]
                if p == "00065":
                    out[(site, "00065")] = [(t, 5.91)]
    return out, names


def _quick_nws():
    return (
        patch("freshwater.nwps", return_value={"status": "unavailable"}),
        patch("freshwater.qpf_block", return_value={"status": "unavailable", "kind": "forecast"}),
        patch("freshwater.alerts_point", return_value={"status": "ok", "items": []}),
        patch("freshwater.usace_guide_check", return_value={"status": "unavailable"}),
        patch("conditions.forecast_block", return_value={
            "status": "ok", "updated": NOW.isoformat(),
            "periods": [{"name": "This Afternoon", "tempF": 68, "short": "Sunny"}],
        }),
    )


class V4TimeoutsAndSaltwater(unittest.TestCase):
    def test_freshwater_timeouts_are_45_and_50(self):
        self.assertEqual(freshwater.FETCH_TIMEOUT, 45)
        self.assertEqual(freshwater.RESULT_TIMEOUT, 50)
        self.assertEqual(freshwater.USER_DEADLINE, 8)
        self.assertEqual(freshwater.FETCH_TRIES, 1)
        self.assertEqual(freshwater.USGS_CONCURRENCY, 4)

    def test_saltwater_fetch_url_defaults_unchanged(self):
        src = Path(__file__).resolve().parents[1].joinpath("server.py").read_text()
        # Saltwater default must stay 45s / 4 tries. Do not import server.py here
        # (it installs hooks and a fetch wrapper as a side effect).
        self.assertIn("def fetch_url(url: str, tries: int = 4, timeout: float = 45", src)


class V4StatsDoNotBlockReadings(unittest.TestCase):
    def setUp(self):
        _clear()

    def tearDown(self):
        _clear()

    def test_slow_stats_do_not_delay_verified_readings(self):
        def fake_iv(sites, params, period="P1D"):
            time.sleep(0.12)
            return _canned_iv(sites, params, period)

        def fake_stats(site, day):
            time.sleep(0.9)
            return {"years": "1990–2025", "p50": 10, "p10": 2, "p25": 5, "p75": 20, "p90": 40, "min": 1, "max": 80}

        p_nws = _quick_nws()
        t0 = time.time()
        with patch("freshwater.usgs_iv", side_effect=fake_iv), \
                patch("freshwater.usgs_daily_stats", side_effect=fake_stats), \
                p_nws[0], p_nws[1], p_nws[2], p_nws[3], p_nws[4]:
            freshwater.assemble("falls-lake", wait=0)
            hit = None
            while time.time() - t0 < 3:
                hit = freshwater.peek("falls-lake")
                if hit and freshwater.usgs_refresh_complete(hit):
                    break
                time.sleep(0.02)
        elapsed = time.time() - t0
        self.assertIsNotNone(hit)
        self.assertTrue(freshwater.usgs_refresh_complete(hit))
        self.assertLess(elapsed, 0.55, "readings must publish without waiting on 0.9s stats, got %.2fs" % elapsed)
        self.assertEqual(hit["lake"]["elevation"]["value"], 244.74)
        # generatedAt is the assemble start stamp, not a stats-arrival stamp.
        self.assertTrue(hit.get("generatedAt"))

    def test_stat_502_retries_once_and_iv_url_does_not(self):
        _clear()
        calls = []

        def fetcher(url, timeout=None, tries=None):
            calls.append(url)
            if "/nwis/stat" in url:
                stat_n = sum(1 for u in calls if "/nwis/stat" in u)
                if stat_n == 1:
                    return 502, "text/plain", b"Bad Gateway"
                return 200, "text/plain", b"# \nsite_no\t00060\n"
            return 502, "application/json", b"Bad Gateway"

        prev = freshwater._FETCH
        freshwater.install_fetch(fetcher)
        try:
            stat = freshwater._get_body("https://waterservices.usgs.gov/nwis/stat/?sites=02087183", 60)
            iv = freshwater._get_body("https://waterservices.usgs.gov/nwis/iv/?sites=02087183", 60)
        finally:
            freshwater.install_fetch(prev)
        self.assertIsNotNone(stat)
        self.assertIsNone(iv)
        self.assertEqual(sum(1 for u in calls if "/nwis/stat" in u), 2)
        self.assertEqual(sum(1 for u in calls if "/nwis/iv" in u), 1)


class V4SharedFlights(unittest.TestCase):
    def setUp(self):
        _clear()

    def tearDown(self):
        _clear()

    def test_corridor_sites_are_the_four_shared_gauges(self):
        shared = freshwater._shared_corridor_sites()
        self.assertEqual(shared, {"02087183", "02087500", "02087570", "02089000"})

    def test_three_regions_share_one_corridor_iv_and_dedupe_stats(self):
        iv_calls, stat_calls = [], []
        gate = threading.Barrier(3, timeout=5)

        def fake_iv_fetch(sites, params, period="P1D"):
            iv_calls.append((tuple(sorted(sites)), period))
            time.sleep(0.15)
            return _canned_iv(sites, params, period)

        def fake_stat_fetch(site, day):
            stat_calls.append(site)
            time.sleep(0.05)
            return {"years": "1990–2025", "p50": 10, "p10": 2, "p25": 5, "p75": 20, "p90": 40, "min": 1, "max": 80}

        p_nws = _quick_nws()
        with patch("freshwater._usgs_iv_fetch", side_effect=fake_iv_fetch), \
                patch("freshwater._usgs_daily_stats_fetch", side_effect=fake_stat_fetch), \
                p_nws[0], p_nws[1], p_nws[2], p_nws[3], p_nws[4]:
            def one(rid):
                gate.wait()
                freshwater.assemble(rid, wait=2)

            threads = [threading.Thread(target=one, args=(rid,)) for rid in RIDS]
            for th in threads:
                th.start()
            for th in threads:
                th.join(timeout=10)

        corridor = tuple(sorted({"02087183", "02087500", "02087570", "02089000"}))
        corridor_calls = [k for k in iv_calls if k[0] == corridor and k[1] == "P1D"]
        self.assertEqual(len(corridor_calls), 1, "Falls and Neuse must share one corridor IV, got %s" % (iv_calls,))
        # Lake P7D once each, plus Falls inflows and Jordan flow sites — no duplicate corridor.
        self.assertEqual(len(iv_calls), 5, iv_calls)
        self.assertEqual(len(stat_calls), 7, stat_calls)
        self.assertEqual(len(set(stat_calls)), 7)
        for rid in RIDS:
            hit = freshwater.peek(rid)
            self.assertTrue(hit and freshwater.usgs_refresh_complete(hit), rid)

    def test_usgs_concurrency_stays_at_or_below_cap(self):
        peak = {"n": 0}
        lock = threading.Lock()
        inflight = {"n": 0}

        def fetcher(url, timeout=None, tries=None):
            with lock:
                inflight["n"] += 1
                peak["n"] = max(peak["n"], inflight["n"])
            time.sleep(0.08)
            with lock:
                inflight["n"] -= 1
            return 200, "application/json", b"{}"

        prev = freshwater._FETCH
        freshwater.install_fetch(fetcher)
        try:
            def one(i):
                freshwater._get_body("https://waterservices.usgs.gov/nwis/iv/?sites=%s" % (80000000 + i), 1)

            threads = [threading.Thread(target=one, args=(i,)) for i in range(10)]
            for th in threads:
                th.start()
            for th in threads:
                th.join(timeout=5)
        finally:
            freshwater.install_fetch(prev)
        self.assertLessEqual(peak["n"], freshwater.USGS_CONCURRENCY)
        self.assertGreaterEqual(peak["n"], 2)


class V4PartialAndRetry(unittest.TestCase):
    def setUp(self):
        _clear()

    def tearDown(self):
        _clear()

    def test_partial_usgs_is_not_five_minute_success(self):
        # Lake IV ok, flow IV empty -> missing expected USGS, not a 5-minute success.
        def fake_iv(sites, params, period="P1D"):
            if period == "P7D":
                return _canned_iv(sites, params, period)
            return {}, {}

        p_nws = _quick_nws()
        with patch("freshwater.usgs_iv", side_effect=fake_iv), \
                patch("freshwater.usgs_daily_stats", return_value=None), \
                p_nws[0], p_nws[1], p_nws[2], p_nws[3], p_nws[4]:
            status, body = freshwater.assemble("falls-lake", wait=2)
        self.assertEqual(status, 200)
        self.assertEqual(body["lake"]["elevation"]["value"], 244.74)
        self.assertTrue(freshwater.has_verified_usgs(body))
        self.assertFalse(freshwater.usgs_refresh_complete(body))
        self.assertFalse(freshwater._is_complete("falls-lake"))
        self.assertIn("falls-lake", freshwater._PARTIAL)


if __name__ == "__main__":
    unittest.main()
