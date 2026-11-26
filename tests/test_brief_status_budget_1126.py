"""Morning Brief "Status now" overall time budget (Ed t491u, Nov 26, 2026).

brief_status.status_now waits at most the budget for all NWS work, then shows a verified result
or "Status unconfirmed — check NWS"; the check finishes in the background (single-flight, bounded)
and the next visitor gets the verified result. Real NWS records: tests/fixtures/nws-alerts-2026-11-26.json.
"""
from __future__ import annotations

import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from tests.test_alert_display_1126 import FIX, NOON, ROOT, fetcher  # noqa: F401  (real fixture helpers)

import brief  # noqa: E402
import brief_status as S  # noqa: E402

HAT = FIX["briefs"]["hatteras"]
CC = FIX["briefs"]["crystal-coast"]
B = 0.6  # short budget in tests; production constant is S.BUDGET_S


def snf(b, fetch):
    return brief.status_now_for(b, fetch, now=NOON)


class Slow:
    """fetch(url) over the real fixture with per-kind delays or a gate that hangs until released."""

    def __init__(self, active=0.0, lookup=0.0, history=0.0, gate_lookups=False, gate_all=False, fail_history=False):
        self.base = fetcher(FIX["active"], FIX["lookups"], FIX["history"])
        self.d = {"active": active, "lookup": lookup, "history": history}
        self.gate = threading.Event()
        self.gate_lookups, self.gate_all, self.fail_history = gate_lookups, gate_all, fail_history
        self.calls = {"active": 0, "lookup": 0, "history": 0}
        self.lock = threading.Lock()

    def kind(self, url):
        if "/alerts/active" in url:
            return "active"
        return "history" if url.startswith("https://api.weather.gov/alerts?") else "lookup"

    def __call__(self, url):
        k = self.kind(url)
        with self.lock:
            self.calls[k] += 1
        if self.gate_all or (self.gate_lookups and k == "lookup"):
            self.gate.wait(10)
        time.sleep(self.d[k])
        if k == "history" and self.fail_history:
            return None
        return self.base(url)


def _states(sn, b=HAT):
    rows = brief._issued_rows(b)
    return {r["event"]: rc["state"] for r, rc in zip(rows, sn["issued"])}


def _wait_idle(timeout=10):
    t = time.time() + timeout
    while time.time() < t:
        with S._LOCK:
            if not S._INFLIGHT:
                return
        time.sleep(0.02)
    raise AssertionError("background check still running")


class Base(unittest.TestCase):
    def setUp(self):
        S._reset_for_tests()

    def tearDown(self):
        _wait_idle()
        S._reset_for_tests()

    def timed(self, b, fetch, budget=B):
        t = time.monotonic()
        sn = S.status_now(b, fetch, snf, budget_s=budget)
        return sn, time.monotonic() - t


class Budget(Base):
    def test_production_budget_is_3_5_seconds_and_fresh_window_matches_cache(self):
        import server
        self.assertEqual(S.BUDGET_S, 3.5)
        self.assertEqual(S.FRESH_S, server.ALERT_STATUS_TTL)

    def test_fast_nws_gives_the_same_verified_result_as_a_direct_check(self):
        sn, dt = self.timed(HAT, Slow())
        self.assertLess(dt, B)
        self.assertTrue(sn["ok"])
        self.assertEqual(sn["issued"], snf(HAT, fetcher(FIX["active"], FIX["lookups"], FIX["history"]))["issued"])
        self.assertEqual(_states(sn)["Storm Warning"], "cancelled")

    def test_just_under_budget_is_verified(self):
        sn, dt = self.timed(HAT, Slow(active=0.2, history=0.15))
        self.assertTrue(sn["ok"])
        self.assertLess(dt, B + 0.1)

    def test_over_budget_is_unconfirmed_within_budget_then_verified_for_next_visitor(self):
        f = Slow(active=1.0)
        sn, dt = self.timed(HAT, f)
        self.assertLess(dt, B + 0.25)
        self.assertFalse(sn["ok"])
        self.assertTrue(all(s == "unconfirmed" for s in _states(sn).values()), _states(sn))
        html = brief._status_now_html(HAT, sn, brief.html.escape if hasattr(brief, "html") else (lambda s: s), NOON)
        self.assertIn("Status unconfirmed — check NWS", html)
        _wait_idle()
        sn2, dt2 = self.timed(HAT, f)
        self.assertTrue(sn2["ok"])
        self.assertLess(dt2, 0.1)
        self.assertEqual(_states(sn2)["Storm Warning"], "cancelled")
        self.assertEqual(f.calls["active"], 1)          # cached verified result, no second upstream read

    def test_hanging_nws_never_blocks_past_budget(self):
        f = Slow(gate_all=True)
        try:
            sn, dt = self.timed(HAT, f)
            self.assertLess(dt, B + 0.25)
            self.assertFalse(sn["ok"])
        finally:
            f.gate.set()

    def test_timeout_raised_by_fetch_reads_unconfirmed(self):
        def fetch(url):
            raise TimeoutError("read timed out")
        sn, dt = self.timed(HAT, fetch)
        self.assertFalse(sn["ok"])
        self.assertTrue(all(s == "unconfirmed" for s in _states(sn).values()))

    def test_bug_in_check_reads_unconfirmed(self):
        def boom(b, fetch):
            raise RuntimeError("bug")
        sn = S.status_now(HAT, Slow(), boom, budget_s=B)
        self.assertFalse(sn is None)
        self.assertFalse(sn["ok"])


class PartialFailures(Base):
    def test_current_ok_but_replacement_lookups_hang(self):
        f = Slow(gate_lookups=True)
        try:
            sn, dt = self.timed(HAT, f)
            self.assertLess(dt, B + 0.25)
            self.assertFalse(sn["ok"])                   # nothing partial or old presented as current
        finally:
            f.gate.set()
        _wait_idle()
        sn2, _ = self.timed(HAT, f)
        self.assertTrue(sn2["ok"])
        st = _states(sn2)
        self.assertEqual(st["Storm Warning"], "cancelled")
        self.assertEqual(st["High Wind Warning"], "ended")

    def test_history_read_fails_is_not_evidence_of_ending(self):
        sn, _ = self.timed(HAT, Slow(fail_history=True))
        self.assertTrue(sn["ok"])
        self.assertEqual(sn["history"], 0)
        direct = A_direct(HAT, fail_history=True)
        self.assertEqual(sn["issued"], direct["issued"])

    def test_quick_nws_error_is_shown_as_unconfirmed_and_not_cached(self):
        calls = []

        def fetch(url):
            calls.append(url)
            return None
        sn, _ = self.timed(HAT, fetch)
        self.assertFalse(sn["ok"])
        _wait_idle()
        self.assertNotIn(S._key(HAT, snf), S._VERIFIED)
        self.timed(HAT, fetch)
        self.assertEqual(sum("/alerts/active" in u for u in calls), 2)   # retried, not a cached failure


def A_direct(b, **kw):
    return snf(b, Slow(**kw))


class Concurrency(Base):
    def test_twenty_visitors_one_upstream_refresh_all_within_budget(self):
        f = Slow(active=1.0)
        with ThreadPoolExecutor(20) as ex:
            res = list(ex.map(lambda _: self.timed(HAT, f), range(20)))
        self.assertTrue(all(dt < B + 0.4 for _, dt in res), [round(dt, 2) for _, dt in res])
        self.assertTrue(all(not sn["ok"] for sn, _ in res))
        _wait_idle()
        self.assertEqual(f.calls["active"], 1)
        with ThreadPoolExecutor(20) as ex:
            res = list(ex.map(lambda _: self.timed(HAT, f), range(20)))
        self.assertTrue(all(sn["ok"] for sn, _ in res))
        self.assertEqual(f.calls["active"], 1)

    def test_later_visitors_to_a_hung_check_are_not_held_again(self):
        f = Slow(gate_all=True)
        try:
            _, dt1 = self.timed(HAT, f)
            _, dt2 = self.timed(HAT, f)
            self.assertGreater(dt1, B - 0.05)
            self.assertLess(dt2, 0.1)
            self.assertEqual(f.calls["active"], 1)
        finally:
            f.gate.set()

    def test_fast_twenty_visitors_share_the_verified_result(self):
        f = Slow(active=0.2)
        with ThreadPoolExecutor(20) as ex:
            res = list(ex.map(lambda _: self.timed(HAT, f), range(20)))
        self.assertTrue(all(sn["ok"] for sn, _ in res))
        self.assertEqual(f.calls["active"], 1)

    def test_bounded_inflight_and_threads(self):
        gates = []
        try:
            for i in range(S.MAX_INFLIGHT):
                f = Slow(gate_all=True)
                gates.append(f)
                b = dict(HAT, issuedAt="2026-11-26T05:15:%02d-05:00" % i)
                S.status_now(b, f, snf, budget_s=0.01)
            with S._LOCK:
                self.assertEqual(len(S._INFLIGHT), S.MAX_INFLIGHT)
            extra = Slow()
            sn, dt = self.timed(dict(HAT, issuedAt="2026-11-26T05:15:59-05:00"), extra)
            self.assertFalse(sn["ok"])
            self.assertEqual(sum(extra.calls.values()), 0)  # not queued, not fetched
            self.assertLess(dt, 0.1)
            self.assertLessEqual(S._POOL._max_workers, S.MAX_WORKERS)
        finally:
            for g in gates:
                g.gate.set()


class Freshness(Base):
    def test_verified_result_reused_inside_window_then_refreshed_after(self):
        f = Slow()
        clock = [1000.0]
        with patch.object(S.time, "monotonic", lambda: clock[0]):
            sn1 = S.status_now(HAT, f, snf, budget_s=B)
            _wait_idle()
            clock[0] += S.FRESH_S - 1
            sn2 = S.status_now(HAT, f, snf, budget_s=B)
            self.assertIs(sn1, sn2)
            self.assertEqual(f.calls["active"], 1)
            clock[0] += 2
            sn3 = S.status_now(HAT, f, snf, budget_s=B)
            _wait_idle()
        self.assertTrue(sn3["ok"])
        self.assertEqual(f.calls["active"], 2)

    def test_expired_verified_result_is_never_shown_when_refresh_is_slow(self):
        clock = [1000.0]
        with patch.object(S.time, "monotonic", lambda: clock[0]):
            S.status_now(HAT, Slow(), snf, budget_s=B)
            _wait_idle()
            clock[0] += S.FRESH_S + 5
            slow = Slow(gate_all=True)
            try:
                sn = S.status_now(HAT, slow, snf, budget_s=0.3)
                self.assertFalse(sn["ok"])               # old verified result is past the window
            finally:
                slow.gate.set()

    def test_cached_result_keeps_its_own_checked_time(self):
        sn1 = S.status_now(HAT, Slow(), snf, budget_s=B)
        _wait_idle()
        sn2 = S.status_now(HAT, Slow(), snf, budget_s=B)
        self.assertEqual(sn1["checkedAt"], sn2["checkedAt"])

    def test_briefs_are_cached_separately(self):
        a = S.status_now(HAT, Slow(), snf, budget_s=B)
        c = S.status_now(CC, Slow(), snf, budget_s=B)
        _wait_idle()
        self.assertNotEqual(S._key(HAT, snf), S._key(CC, snf))
        self.assertEqual(_states(c, CC)["Storm Warning"], "cancelled")
        self.assertTrue(a["ok"] and c["ok"])


class Recovery(Base):
    def test_outage_then_recovery_unconfirmed_then_verified_reconciliation(self):
        down = {"on": True}
        base = Slow()

        def fetch(url):
            return None if down["on"] else base(url)
        sn, _ = self.timed(HAT, fetch)
        self.assertFalse(sn["ok"])
        _wait_idle()
        down["on"] = False
        sn2, _ = self.timed(HAT, fetch)
        self.assertTrue(sn2["ok"])
        st = _states(sn2)
        self.assertEqual(st["Storm Warning"], "cancelled")
        self.assertEqual(st["High Wind Warning"], "ended")
        self.assertIn(st["Gale Warning"], ("in_effect", "updated", "upgraded", "replaced"))
        self.assertTrue(sn2["current"])


class PageAndRoute(Base):
    def test_published_brief_render_is_unchanged(self):
        import copy
        sn = snf(HAT, fetcher(FIX["active"], FIX["lookups"], FIX["history"]))
        before = copy.deepcopy(HAT)
        p1 = brief.page(HAT, public=True, ads_on=False, status_now=sn)
        S.status_now(HAT, Slow(), snf, budget_s=B)
        p2 = brief.page(HAT, public=True, ads_on=False, status_now=sn)
        self.assertEqual(p1, p2)
        self.assertEqual(before, HAT)                    # the 5:15 AM snapshot is never edited

    def test_brief_route_uses_the_budget(self):
        src = (ROOT / "server.py").read_text()
        self.assertIn("brief_status.status_now(b, _alert_status_fetch, brief.status_now_for)", src)
        self.assertNotIn("status_now = brief.status_now_for(b, _alert_status_fetch)", src)


if __name__ == "__main__":
    unittest.main()
