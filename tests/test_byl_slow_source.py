"""BYL readings defect (Ed t577u, 2026-11-28): on production a cold USGS request took 16-22 s, so the first
.json answer took about 25 s, the page's 20 s abort fired first, and every reading showed Unavailable.
The .json answer must arrive within its budget with what is ready, list slower sources as pending, and
never fill anything in for them; a second identical request must join the one already running."""
import json
import re
import threading
import time
import unittest
from unittest import mock

import byl_data as B
import byl_page as P
from test_byl import FALLS, NOW, RECS, ROOT, SITES, fake


def slow_usgs(delay, fail=False):
    f, calls = fake()
    orig = f.opener

    def op(url, t):
        if "usgs" in url:
            time.sleep(delay)
            if fail:
                raise OSError("down")
        return orig(url, t)
    f.opener = op
    return f, calls


class SlowSource(unittest.TestCase):
    def test_answer_arrives_within_budget_and_lists_slow_source_as_pending(self):
        f, _ = slow_usgs(1.5)
        t = time.time()
        d = B.assemble(FALLS, f=f, now=NOW, sites=SITES, records=RECS, budget=0.3)
        self.assertLess(time.time() - t, 1.2)
        self.assertIn("usgs", d["pending"])
        self.assertIn(d["cards"]["forecast"]["kind"], ("fcst", "stale"))
        self.assertIn("alerts", d["cards"])
        for k in ("lake", "temp", "below_dam"):
            self.assertNotIn(k, d["cards"], "nothing is filled in for a pending source")

    def test_next_request_gets_the_reading_from_the_background_fetch(self):
        f, calls = slow_usgs(0.8)
        d1 = B.assemble(FALLS, f=f, now=NOW, sites=SITES, records=RECS, budget=0.2)
        self.assertIn("usgs", d1["pending"])
        d2 = B.assemble(FALLS, f=f, now=NOW, sites=SITES, records=RECS, budget=3)
        self.assertEqual(d2["pending"], [])
        self.assertEqual(d2["cards"]["lake"]["kind"], "obs")
        self.assertEqual(sum("period=PT25H" in u for u in calls), 1, "the second request joins the USGS request already running")

    def test_fast_sources_have_no_pending(self):
        f, _ = fake()
        d = B.assemble(FALLS, f=f, now=NOW, sites=SITES, records=RECS)
        self.assertEqual(d["pending"], [])
        self.assertEqual(d["cards"]["lake"]["kind"], "obs")

    def test_failed_slow_source_becomes_unavailable_not_a_value(self):
        f, _ = slow_usgs(0.5, fail=True)
        B.assemble(FALLS, f=f, now=NOW, sites=SITES, records=RECS, budget=0.1)
        time.sleep(0.8)
        d = B.assemble(FALLS, f=f, now=NOW, sites=SITES, records=RECS, budget=3)
        self.assertEqual(d["pending"], [])
        self.assertEqual(d["cards"]["lake"]["kind"], "unav")


class Coalesce(unittest.TestCase):
    def test_concurrent_requests_for_one_url_make_one_upstream_call(self):
        n = []

        def op(url, t):
            n.append(url); time.sleep(0.3); return b'{"ok": 1}'
        f = B.Fetcher(opener=op, clock=lambda: 1000.0)
        out = []
        th = [threading.Thread(target=lambda: out.append(f.get("usgs", "https://waterservices.usgs.gov/x"))) for _ in range(4)]
        [x.start() for x in th]; [x.join() for x in th]
        self.assertEqual(len(n), 1)
        self.assertEqual(out, [{"ok": 1}] * 4)

    def test_waiter_on_a_failed_request_gets_source_down(self):
        def op(url, t):
            time.sleep(0.2); raise OSError("down")
        f = B.Fetcher(opener=op, clock=lambda: 1000.0)
        errs = []

        def go():
            try:
                f.get("usgs", "https://waterservices.usgs.gov/y")
            except B.SourceDown:
                errs.append(1)
        th = [threading.Thread(target=go) for _ in range(3)]
        [x.start() for x in th]; [x.join() for x in th]
        self.assertEqual(len(errs), 3)


class Client(unittest.TestCase):
    JS = (ROOT / "preview/before-you-launch/byl.js").read_text()

    def test_budget_is_well_inside_the_page_abort(self):
        abort_ms = int(re.search(r"ctl\.abort\(\)\},(\d+)\)", self.JS).group(1))
        self.assertLessEqual(B.BUDGET + 5, abort_ms / 1000)

    def test_page_asks_again_while_sources_are_pending_then_marks_the_rest_unavailable(self):
        self.assertIn("d.pending", self.JS)
        self.assertRegex(self.JS, r"tries<\d")
        self.assertIn("Readings could not be loaded", self.JS)
        self.assertIn("credentials:'same-origin'", self.JS)

    def test_json_carries_pending(self):
        fake_d = {"id": FALLS, "generated": NOW.isoformat(), "withheld": None, "cards": {}, "pending": ["usgs"]}
        with mock.patch.object(B, "assemble", return_value=fake_d), mock.patch.object(B, "warm"):
            st, ct, body = P.resolve_request("/preview/before-you-launch/%s.json" % FALLS)
        self.assertEqual(st, 200)
        self.assertEqual(json.loads(body)["pending"], ["usgs"])


if __name__ == "__main__":
    unittest.main()
