"""Unattended Morning Brief: validation, region isolation, once-a-day builds, the Nov 20 window end,
archive fallback, and the GitHub Actions helper (EST/EDT guard, verify, archive).

Everything runs offline with an injected clock, fake source data, and a temp store. Nothing is published."""
import importlib.util
import json
import os
import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

import brief
import conditions

ET = ZoneInfo("America/New_York")
ROOT = Path(__file__).resolve().parents[1]
CFG = {r["id"]: r for r in json.loads((ROOT / "data" / "regions.json").read_text())["regions"]}


def et(y, mo, d, h, mi):
    return datetime(y, mo, d, h, mi, tzinfo=ET).astimezone(timezone.utc)


def fake_payload(rid, now, zone=None, drop=(), stale=()):
    r = CFG[rid]
    t = (now - timedelta(minutes=20)).isoformat()
    st = {"id": "41159", "name": "Onslow Bay buoy"}

    def rd(kind, values):
        if kind in drop:
            return {"status": "unavailable"}
        if kind in stale:
            return {"status": "stale", "time": (now - timedelta(hours=5)).isoformat(), "station": st, "values": values}
        return {"status": "ok", "time": t, "ageMin": 20, "staleAfterMin": 90, "station": st, "values": values}
    day = now.astimezone(ET).replace(hour=11, minute=0)
    readings = {
        "wind": rd("wind", {"speedKt": 12, "dirCompass": "NE", "gustKt": 16}),
        "seas": rd("seas", {"heightFt": 3.2, "dominantPeriodS": 8, "meanDirCompass": "E"}),
        "swell": rd("swell", {"heightFt": 2.0, "periodS": 9, "dirCompass": "E"}),
        "pressure": rd("pressure", {"inHg": 30.05, "trend": "steady"}),
        "waterTemp": rd("waterTemp", {"f": 61}),
    }
    return 200, {
        "ok": True, "region": {"id": rid, "name": r["name"], "area": r.get("area"), "anchor": r.get("anchor"), "map": r.get("map")},
        "readings": readings,
        "tides": {"status": "unavailable"} if "tides" in drop else {"status": "ok", "station": {"id": "8656483", "name": "Beaufort"},
                  "events": [{"t": day.timestamp() * 1000, "type": "H", "v": 3.1}]},
        "forecast": {"status": "unavailable"} if "forecast" in drop else {"status": "ok", "updated": (now - timedelta(hours=2)).isoformat(),
                     "periods": [{"pop": 10, "short": "Sunny", "tempF": 64}, {"pop": 0, "short": "Clear", "tempF": 50}]},
        "marine": {"status": "unavailable", "zone": zone or r["marine"]["zone"]} if "marine" in drop else
                  {"status": "ok", "zone": zone or r["marine"]["zone"], "updated": (now - timedelta(hours=3)).isoformat(),
                   "periods": [{"name": "Today", "text": "NE winds 10 to 15 kt. Seas 3 to 4 ft."}]},
        "alerts": {"status": "unavailable", "items": []} if "alerts" in drop else {"status": "ok", "items": []},
    }


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patches = [
            mock.patch.object(brief, "STORE", Path(self.tmp.name) / "briefs"),
            mock.patch.object(brief, "_trend", lambda *a, **k: None),
            mock.patch.object(brief, "enabled_regions", lambda include_fresh=None: ["crystal-coast", "hatteras"]),
            mock.patch.dict(os.environ, {"MORNING_BRIEF_ARCHIVE_URL": ""}),
        ]
        for p in self.patches:
            p.start()
        os.environ.pop("MORNING_BRIEF_AUTO_UNTIL", None)
        brief._mem.clear(); brief._last_error.clear(); brief._arch_cache.clear()
        self.clock = et(2026, 11, 14, 5, 15)
        self.calls = []
        self.fail = set()
        self.opts = {}

        def assemble(rid):
            self.calls.append(rid)
            if rid in self.fail:
                raise RuntimeError("source down")
            return fake_payload(rid, self.clock, **self.opts.get(rid, {}))
        self.patches.append(mock.patch.object(conditions, "assemble", assemble))
        self.patches[-1].start()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        brief._mem.clear(); brief._last_error.clear(); brief._arch_cache.clear()
        self.tmp.cleanup()


class Validation(Base):
    def test_normal_build_passes_all_checks(self):
        for rid in ("crystal-coast", "hatteras"):
            b = brief.build(rid, "scheduled", self.clock)
            self.assertEqual(b["issueDate"], "2026-11-14")
            self.assertEqual(b["marineZone"], CFG[rid]["marine"]["zone"])
            self.assertEqual(b["validation"]["status"], "ok")
            self.assertEqual(b["missing"], [])
            self.assertIn("Sat Nov 14, 5:15 AM ET", b["issuedEt"])

    def test_wrong_zone_is_critical(self):
        self.opts["hatteras"] = {"zone": "AMZ999"}
        with self.assertRaises(brief.BriefInvalid) as cm:
            brief.build("hatteras", "scheduled", self.clock)
        self.assertIn("marine zone", str(cm.exception))
        self.assertIsNone(brief._stored("hatteras"))

    def test_no_forecast_at_all_is_critical(self):
        self.opts["crystal-coast"] = {"drop": ("marine", "forecast")}
        with self.assertRaises(brief.BriefInvalid):
            brief.build("crystal-coast", "scheduled", self.clock)

    def test_majority_of_core_missing_is_critical(self):
        self.opts["crystal-coast"] = {"drop": ("wind", "seas", "waterTemp", "tides")}
        with self.assertRaises(brief.BriefInvalid):
            brief.build("crystal-coast", "scheduled", self.clock)

    def test_wrong_date_or_timestamp_is_critical(self):
        b = brief.compose("hatteras", "scheduled", self.clock)
        errs, _ = brief.validate({**b, "issueDate": "2026-11-13"}, "hatteras", self.clock)
        self.assertTrue(any("issue date" in e for e in errs))
        errs, _ = brief.validate(b, "hatteras", self.clock + timedelta(hours=2))
        self.assertTrue(errs)
        errs, _ = brief.validate({**b, "region": {**b["region"], "name": "Elsewhere"}}, "hatteras", self.clock)
        self.assertTrue(any("name" in e for e in errs))
        errs, _ = brief.validate({**b, "region": {**b["region"], "anchor": {"lat": 0, "lon": 0}}}, "hatteras", self.clock)
        self.assertTrue(any("location" in e for e in errs))

    def test_individual_missing_and_stale_readings_are_named_not_substituted(self):
        self.opts["hatteras"] = {"drop": ("swell",), "stale": ("wind",)}
        b = brief.build("hatteras", "scheduled", self.clock)
        self.assertEqual(b["validation"]["status"], "partial")
        self.assertIn("swell", b["missing"])
        self.assertTrue(any(m.startswith("wind (stale: last report") and "not used" in m for m in b["missing"]))
        self.assertNotIn("Wind", [k for k, _ in b["items"]])
        self.assertIn("Not available at issue time", brief.page(b))

    def test_old_marine_forecast_is_not_used(self):
        def assemble(rid):
            st, d = fake_payload(rid, self.clock)
            d["marine"]["updated"] = (self.clock - timedelta(hours=30)).isoformat()
            return st, d
        with mock.patch.object(conditions, "assemble", assemble):
            b = brief.build("hatteras", "scheduled", self.clock)
        self.assertNotIn("Marine forecast", [k for k, _ in b["items"]])
        self.assertTrue(any(m.startswith("marine forecast (stale") for m in b["missing"]))


class Serving(Base):
    def test_critical_failure_keeps_last_valid_brief_clearly_dated(self):
        prev = brief.build("hatteras", "scheduled", et(2026, 11, 13, 5, 15))
        self.clock = et(2026, 11, 14, 5, 40)
        self.opts["hatteras"] = {"zone": "AMZ999"}
        st, b = brief.get("hatteras", now=self.clock)
        self.assertEqual(st, 200)
        self.assertEqual(b["issueDate"], "2026-11-13")
        self.assertIs(b["current"], False)
        self.assertIn("did not pass the data checks", b["staleNotice"])
        self.assertIn(prev["issuedEt"], b["staleNotice"])
        self.assertIn("mb-stale-note", brief.page(b))

    def test_critical_failure_without_previous_is_unavailable(self):
        self.opts["hatteras"] = {"drop": ("marine", "forecast")}
        st, b = brief.get("hatteras", now=self.clock)
        self.assertEqual(st, 503)
        self.assertIn("unavailable", b["error"])

    def test_one_region_failing_does_not_block_the_other_wake(self):
        self.fail = {"crystal-coast"}
        r = brief.wake(now=self.clock, background=False)
        self.assertEqual(r["building"], 2)
        self.assertEqual(brief._stored("hatteras")["issueDate"], "2026-11-14")
        self.assertIsNone(brief._stored("crystal-coast"))
        self.assertTrue(r["regions"]["hatteras"]["today"])
        self.assertIn("source down", r["regions"]["crystal-coast"]["lastError"])

    def test_one_region_failing_does_not_block_the_other_scheduler(self):
        self.fail = {"hatteras"}
        t = [self.clock]

        def sleep(s):
            t[0] += timedelta(seconds=s)
            self.clock = t[0]
        res = brief.run_window(now_fn=lambda: t[0], sleep_fn=sleep)
        self.assertEqual(res, {"crystal-coast": "ok", "hatteras": "failed"})
        self.assertEqual(brief._stored("crystal-coast")["reason"], "scheduled")
        self.assertLess(t[0], et(2026, 11, 14, 5, 33))  # stops retrying by 5:30

    def test_scheduler_skips_complete_briefs_and_keeps_better(self):
        brief.build("crystal-coast", "scheduled", self.clock)
        n = len(self.calls)
        self.opts["hatteras"] = {"drop": ("swell",)}
        t = [self.clock]

        def sleep(s):
            t[0] += timedelta(seconds=s)
            self.clock = t[0]
        brief.run_window(now_fn=lambda: t[0], sleep_fn=sleep)
        self.assertNotIn("crystal-coast", self.calls[n:])  # not rebuilt
        self.assertIn("swell", brief._stored("hatteras")["missing"])

    def test_wake_before_515_builds_nothing(self):
        r = brief.wake(now=et(2026, 11, 14, 4, 50), background=False)
        self.assertEqual(r["building"], 0)
        self.assertIn("waiting", r)
        self.assertEqual(self.calls, [])

    def test_builds_once_per_region_per_day(self):
        brief.wake(now=self.clock, background=False)
        brief.wake(now=self.clock + timedelta(minutes=1), background=False)
        brief.get("hatteras", now=self.clock + timedelta(minutes=2))
        self.assertEqual(sorted(self.calls), ["crystal-coast", "hatteras"])

    def test_concurrent_requests_share_one_build(self):
        slow = conditions.assemble

        def assemble(rid):
            time.sleep(0.3)
            return slow(rid)
        with mock.patch.object(conditions, "assemble", assemble):
            ths = [threading.Thread(target=brief.get, args=("hatteras",), kwargs={"now": self.clock}) for _ in range(4)]
            [x.start() for x in ths]; [x.join() for x in ths]
        self.assertEqual(self.calls.count("hatteras"), 1)


class Window(Base):
    def test_default_window_is_nov_20(self):
        self.assertEqual(brief.auto_until(), "2026-11-20")
        self.assertTrue(brief.auto_active(et(2026, 11, 20, 23, 59)))
        self.assertFalse(brief.auto_active(et(2026, 11, 21, 0, 0)))
        with mock.patch.dict(os.environ, {"MORNING_BRIEF_AUTO_UNTIL": "2026-11-27"}):
            self.assertTrue(brief.auto_active(et(2026, 11, 21, 5, 15)))
        with mock.patch.dict(os.environ, {"MORNING_BRIEF_AUTO_UNTIL": "garbage"}):
            self.assertEqual(brief.auto_until(), "2026-11-20")

    def test_after_window_nothing_new_is_built_and_last_brief_stays(self):
        self.clock = et(2026, 11, 20, 5, 15)
        last = brief.build("crystal-coast", "scheduled", self.clock)
        n = len(self.calls)
        self.clock = et(2026, 11, 21, 6, 0)
        self.assertEqual(brief.wake(now=self.clock, background=False)["building"], 0)
        self.assertEqual(brief.run_window(now_fn=lambda: et(2026, 11, 21, 5, 15), sleep_fn=lambda s: None), {})
        st, b = brief.get("crystal-coast", now=self.clock)
        self.assertEqual(st, 200)
        self.assertEqual(b["issueDate"], "2026-11-20")
        self.assertEqual(b["issuedAt"], last["issuedAt"])
        self.assertIn("paused", b["staleNotice"])
        self.assertIn("Nov 20, 2026", b["staleNotice"])
        st, b = brief.get("hatteras", now=self.clock)
        self.assertEqual(st, 503)
        self.assertEqual(len(self.calls), n)  # no new builds of any kind

    def test_before_515_on_nov_21_still_serves_nov_20_brief(self):
        self.clock = et(2026, 11, 20, 5, 15)
        last = brief.build("hatteras", "scheduled", et(2026, 11, 20, 5, 15))
        st, b = brief.get("hatteras", now=et(2026, 11, 21, 3, 0))
        self.assertEqual((st, b["issuedAt"]), (200, last["issuedAt"]))
        self.assertNotIn("staleNotice", b)


class Archive(Base):
    def test_restart_uses_todays_archived_brief_instead_of_rebuilding(self):
        b = brief.build("hatteras", "scheduled", self.clock)
        d = Path(self.tmp.name) / "arch"; d.mkdir()
        (d / "hatteras.json").write_text(json.dumps(b))
        brief._mem.clear()
        for f in (Path(self.tmp.name) / "briefs").glob("*.json"):
            f.unlink()
        n = len(self.calls)
        with mock.patch.dict(os.environ, {"MORNING_BRIEF_ARCHIVE_URL": d.as_uri() + "/%s.json"}):
            st, got = brief.get("hatteras", now=self.clock + timedelta(hours=3))
            self.assertEqual((st, got["issuedAt"]), (200, b["issuedAt"]))
            self.assertEqual(len(self.calls), n)
            # Bad archive content is ignored.
            (d / "crystal-coast.json").write_text(json.dumps({"ok": True, "regionId": "hatteras"}))
            self.assertIsNone(brief._archived("crystal-coast"))


def load_helper():
    spec = importlib.util.spec_from_file_location("morning_brief", ROOT / ".github" / "scripts" / "morning_brief.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class Workflow(unittest.TestCase):
    def setUp(self):
        self.m = load_helper()

    def test_guard_est_and_edt(self):
        d = self.m.decide
        # EST (Nov): 09:35/09:50/10:16 UTC act; 08:35/08:50/09:16 UTC skip.
        for hh, mm, go in ((8, 35, False), (8, 50, False), (9, 16, False), (9, 35, True), (9, 50, True), (10, 16, True)):
            self.assertEqual(d("schedule", datetime(2026, 11, 14, hh, mm, tzinfo=timezone.utc))[0], go, (hh, mm))
        # EDT (summer): 08:35/08:50/09:16/09:35/09:50/10:16 UTC all act (4:35-6:16 AM EDT).
        for hh, mm in ((8, 35), (8, 50), (9, 16), (9, 35), (9, 50), (10, 16)):
            self.assertTrue(d("schedule", datetime(2026, 7, 14, hh, mm, tzinfo=timezone.utc), "2026-12-31")[0], (hh, mm))
        # A cron delayed into the afternoon or evening does nothing.
        self.assertFalse(d("schedule", et(2026, 11, 14, 13, 0))[0])

    def test_guard_window_end(self):
        self.assertTrue(self.m.decide("schedule", et(2026, 11, 20, 4, 35))[0])
        self.assertFalse(self.m.decide("schedule", et(2026, 11, 21, 4, 35))[0])
        self.assertFalse(self.m.decide("workflow_dispatch", et(2026, 11, 21, 5, 20))[0])

    def _brief(self, rid, day="2026-11-14", at="2026-11-14T10:15:20+00:00", **kw):
        return {"ok": True, "regionId": rid, "issueDate": day, "issuedAt": at, "issuedEt": "x", "reason": "scheduled",
                "items": [], "missing": [], "validation": {"status": "ok"}, **kw}

    def test_verify_checks_every_region_before_failing(self):
        seen = []

        def http(path, **k):
            rid = path.split("=")[1]
            seen.append(rid)
            if rid == "crystal-coast":
                return 503, {"ok": False, "error": "unavailable"}
            return 200, self._brief(rid)
        with tempfile.TemporaryDirectory() as td, \
                mock.patch.object(self.m, "http", http), mock.patch.object(self.m, "now", lambda: et(2026, 11, 14, 5, 31)), \
                mock.patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": td + "/s.md", "RESULTS": td + "/r.json"}):
            rc = self.m.cmd_verify()
            md = Path(td, "s.md").read_text()
        self.assertEqual(rc, 1)
        self.assertEqual(seen, ["crystal-coast", "hatteras", "falls-lake"])
        self.assertIn("NOT PUBLISHED", md)
        self.assertIn("published on time", md)

    def test_verify_flags_late_and_old(self):
        with mock.patch.object(self.m, "now", lambda: et(2026, 11, 14, 6, 0)):
            with mock.patch.object(self.m, "http", lambda p, **k: (200, self._brief("hatteras", at="2026-11-14T10:41:00+00:00"))):
                ok, row, _ = self.m.check("hatteras", "2026-11-14")
                self.assertTrue(ok); self.assertIn("LATE", row["result"])
            with mock.patch.object(self.m, "http", lambda p, **k: (200, self._brief("hatteras", day="2026-11-13", staleNotice="old"))):
                ok, row, _ = self.m.check("hatteras", "2026-11-14")
                self.assertFalse(ok)

    def test_archive_writes_only_todays_valid_briefs(self):
        def http(path, **k):
            rid = path.split("=")[1]
            if rid == "hatteras":
                return 200, self._brief(rid, day="2026-11-13", staleNotice="old")
            return 200, self._brief(rid)
        with tempfile.TemporaryDirectory() as td, \
                mock.patch.object(self.m, "http", http), mock.patch.object(self.m, "now", lambda: et(2026, 11, 14, 5, 32)):
            self.m.cmd_archive(td)
            files = sorted(str(p.relative_to(td)) for p in Path(td).rglob("*.json"))
        self.assertEqual(files, ["archive/2026-11-14/crystal-coast.json", "archive/2026-11-14/falls-lake.json",
                                 "latest/crystal-coast.json", "latest/falls-lake.json"])

    def test_run_keeps_awake_then_wakes_after_516(self):
        t = [et(2026, 11, 14, 4, 50)]
        hits = []

        def http(path, **k):
            hits.append((path, self.m.et(t[0]).strftime("%H:%M")))
            if path == "/api/brief/wake":
                return 200, {"ok": True, "regions": {"crystal-coast": {"today": True}, "hatteras": {"today": True}}}
            return 200, {"ok": True}

        def sleep(s):
            t[0] += timedelta(seconds=s)
        with mock.patch.object(self.m, "http", http), mock.patch.object(self.m, "now", lambda: t[0]), \
                mock.patch.object(self.m.time, "sleep", sleep):
            self.assertEqual(self.m.cmd_run(), 0)
        health = [h for p, h in hits if p == "/api/health"]
        wake = [h for p, h in hits if p == "/api/brief/wake"]
        self.assertGreaterEqual(len(health), 6)
        self.assertTrue(all(h < "05:16" for h in health))
        self.assertEqual(wake[0], "05:16")
        gaps = [(datetime.strptime(b, "%H:%M") - datetime.strptime(a, "%H:%M")).seconds for a, b in zip(health, health[1:])]
        self.assertTrue(all(g <= 240 for g in gaps))


if __name__ == "__main__":
    unittest.main()
