"""Launch audit Nov 19 2026, Phase 2 repairs (Ed approved items 1-11, t334u).

Offline: fake source data, injected clocks, temp stores, a local test server with network-bound
calls patched out. Nothing is published, archived, or sent."""
import copy
import json
import os
import re
import threading
import unittest
import urllib.error
import urllib.request
from datetime import timedelta
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

import brief
import conditions
import site_chrome
from tests.test_brief_automation import Base, et
from tests import test_hatteras_wind_backup as hw

ROOT = Path(__file__).resolve().parents[1]


# ------------------------------------------------------------------ item 1: no overwrite after a deploy
class NoRebuildAfterDeploy(Base):
    def _archive(self, *briefs):
        d = Path(self.tmp.name) / "arch"
        d.mkdir(exist_ok=True)
        for b in briefs:
            (d / ("%s.json" % b["regionId"])).write_text(json.dumps(b))
        return d.as_uri() + "/%s.json"

    def _wipe(self):  # a deploy: memory and the ephemeral cache/briefs are gone
        brief._mem.clear(); brief._arch_cache.clear()
        for f in (Path(self.tmp.name) / "briefs").glob("*.json"):
            f.unlink()

    def test_wake_after_deploy_reuses_todays_archived_515_brief(self):
        cc = brief.build("crystal-coast", "scheduled", self.clock)
        ht = brief.build("hatteras", "scheduled", self.clock)
        url = self._archive(cc, ht)
        self._wipe()
        n = len(self.calls)
        with mock.patch.dict(os.environ, {"MORNING_BRIEF_ARCHIVE_URL": url}):
            out = brief.wake(now=et(2026, 11, 14, 6, 13), background=False)
            self.assertEqual(out["building"], 0)
            self.assertEqual(len(self.calls), n, "nothing may be rebuilt")
            for rid, orig in (("crystal-coast", cc), ("hatteras", ht)):
                self.assertTrue(out["regions"][rid]["today"])
                self.assertEqual(out["regions"][rid]["reason"], "scheduled")
                st, got = brief.get(rid, now=et(2026, 11, 14, 6, 14))
                self.assertEqual((st, got["reason"], got["issuedAt"]), (200, "scheduled", orig["issuedAt"]))

    def test_ensure_after_deploy_returns_archived_brief(self):
        cc = brief.build("crystal-coast", "scheduled", self.clock)
        url = self._archive(cc)
        self._wipe()
        n = len(self.calls)
        with mock.patch.dict(os.environ, {"MORNING_BRIEF_ARCHIVE_URL": url}):
            got = brief._ensure("crystal-coast", "on-request", et(2026, 11, 14, 6, 13), "2026-11-14")
        self.assertEqual((got["reason"], got["issuedAt"], len(self.calls)), ("scheduled", cc["issuedAt"], n))

    def test_wake_still_builds_when_archive_has_only_yesterday(self):
        old = brief.build("crystal-coast", "scheduled", et(2026, 11, 13, 5, 15))
        url = self._archive(old)
        self._wipe()
        with mock.patch.dict(os.environ, {"MORNING_BRIEF_ARCHIVE_URL": url}):
            out = brief.wake(now=et(2026, 11, 14, 6, 13), background=False)
        self.assertEqual(out["building"], 2)
        self.assertEqual(brief._stored("crystal-coast")["issueDate"], "2026-11-14")
        self.assertEqual(brief._stored("crystal-coast")["reason"], "on-request")

    def test_in_window_retry_still_runs_for_partial_archived_brief(self):
        self.opts["hatteras"] = {"drop": ("swell",)}
        partial = brief.build("hatteras", "scheduled", self.clock)
        self.assertTrue(partial["missing"])
        url = self._archive(partial)
        self._wipe()
        self.opts["hatteras"] = {}
        clock = {"t": et(2026, 11, 14, 5, 18)}
        with mock.patch.dict(os.environ, {"MORNING_BRIEF_ARCHIVE_URL": url}):
            res = brief.run_window(now_fn=lambda: clock["t"], sleep_fn=lambda s: clock.update(t=clock["t"] + timedelta(seconds=s)),
                                   regions_fn=lambda: ["hatteras"])
        self.assertEqual(res, {"hatteras": "ok"})
        self.assertEqual(brief._stored("hatteras")["missing"], [])  # the complete retry replaced the partial one


# ------------------------------------------------------------------ item 2: pressure attribution
class PressureAttribution(unittest.TestCase):
    def _payload(self, pressure_station):
        p = hw._payload(hw._wind("ok", hw.BUOY, 35), hw._wind("ok", hw.SHORE, 6))
        p["readings"]["pressure"]["station"] = dict(pressure_station)
        return p

    def test_coops_value_never_gets_the_buoy_trend_or_name(self):
        seen = []

        def trend(sid, key, now, scale=1.0):
            seen.append((sid, key))
            return {"now": 1030.3, "then": 1031.8, "hours": 10, "station": sid, "tNow": now, "tThen": now, "url": ""}
        with mock.patch("conditions.assemble", return_value=(200, copy.deepcopy(self._payload(hw.SHORE)))), \
             mock.patch.object(brief, "_trend", trend):
            b = brief.build_salt("hatteras", hw.NOW)
        line = dict(b["items"])["Pressure"]
        self.assertEqual(line, "30.40 inHg, steady.")
        self.assertNotIn("41025", line)
        self.assertNotIn(("41025", "PRES"), seen)
        self.assertNotIn(("8654467", "PRES"), seen)  # CO-OPS has no NDBC overnight file
        self.assertEqual([f["station"] for f in b["freshness"] if f["label"] == "Barometer"], ["8654467"])

    def test_ndbc_value_uses_its_own_station_trend(self):
        with mock.patch("conditions.assemble", return_value=(200, copy.deepcopy(self._payload(hw.BUOY)))), \
             mock.patch.object(brief, "_trend", lambda sid, key, now, scale=1.0:
                               {"now": 1030.3, "then": 1031.8, "hours": 10, "station": sid, "tNow": now, "tThen": now, "url": ""}):
            b = brief.build_salt("hatteras", hw.NOW)
        self.assertEqual(dict(b["items"])["Pressure"], "30.40 inHg, steady, down 1.5 hPa over 10 h at 41025.")


# ------------------------------------------------------------------ item 3a: swell from the stated row
class SwellRow(unittest.TestCase):
    def _payload(self):
        p = hw._payload(hw._wind("ok", hw.BUOY, 35), None)
        seas = p["readings"]["seas"]
        seas["time"] = "2026-11-18T09:56:00+00:00"
        p["readings"]["swell"] = {"status": "ok", "time": "2026-11-18T09:26:00+00:00", "station": dict(seas["station"]),
                                  "values": {"heightFt": 0.3, "periodS": 11.0, "dirCompass": "E"}}
        return p

    def _rows(self, with_match):
        from datetime import datetime, timezone
        rows = [{"_dt": datetime(2026, 11, 18, 9, 26, tzinfo=timezone.utc), "SwH": "0.1", "SwP": "11.0", "SwD": "E"}]
        if with_match:
            rows.insert(0, {"_dt": datetime(2026, 11, 18, 9, 56, tzinfo=timezone.utc), "SwH": "0.1", "SwP": "11.1", "SwD": "ENE"})
        return rows, "u"

    def _build(self, with_match):
        with mock.patch("conditions.assemble", return_value=(200, copy.deepcopy(self._payload()))), \
             mock.patch.object(brief, "_trend", return_value=None), \
             mock.patch.object(conditions, "ndbc_rows", lambda sid, ext="txt": self._rows(with_match)):
            return brief.build_salt("hatteras", hw.NOW)

    def test_swell_uses_the_seas_observation_row(self):
        line = dict(self._build(True)["items"])["Swell"]
        self.assertEqual(line, "0.3 ft at 11 s from the ENE (split from the buoy spectrum).")

    def test_swell_from_another_row_shows_its_own_time(self):
        b = self._build(False)
        line = dict(b["items"])["Swell"]
        self.assertIn("from the E", line)
        self.assertIn("observed 4:26 AM ET", line.replace("Wed ", ""))
        self.assertTrue([f for f in b["freshness"] if f["label"] == "Swell"])


# ------------------------------------------------------------------ item 3b: whole m/s buoys
class WholeMsWind(unittest.TestCase):
    def _rows(self, vals):
        from datetime import datetime, timezone
        return [{"_dt": datetime(2026, 11, 19, 15 - i, 8, tzinfo=timezone.utc), "WSPD": w, "GST": g, "WDIR": "70"}
                for i, (w, g) in enumerate(vals)], "u"

    def test_whole_ms_buoy_reads_whole_knots(self):
        rows = self._rows([("10.0", "13.0"), ("9.0", "12.0"), ("10.0", "12.0"), ("11.0", "14.0")])
        with mock.patch.object(conditions, "ndbc_rows", lambda sid, ext="txt": rows):
            v = conditions.ndbc_reading("wind", "41064")["values"]
        self.assertEqual((v["speedKt"], v["gustKt"], v["decimals"]), (19.0, 25.0, 0))

    def test_tenth_ms_station_unchanged(self):
        rows = self._rows([("6.7", "8.2"), ("6.0", "7.9"), ("6.2", "8.0")])
        with mock.patch.object(conditions, "ndbc_rows", lambda sid, ext="txt": rows):
            v = conditions.ndbc_reading("wind", "CLKN7")["values"]
        self.assertEqual((v["speedKt"], v["gustKt"]), (13.0, 15.9))
        self.assertNotIn("decimals", v)

    def test_dashboard_uses_decimals_hint_and_hides_duplicate_harbor(self):
        js = (ROOT / "dashboard.js").read_text()
        self.assertIn("fmt(v.speedKt, ktDec)", js)
        self.assertIn("hw.station.id === wsid", js)


# ------------------------------------------------------------------ items 4, 5, 6, 7, 8, 9, 10, 11
class BriefTargets(unittest.TestCase):
    def test_targets(self):
        with mock.patch.object(site_chrome, "public_brief_regions", lambda: ["crystal-coast", "hatteras", "falls-lake"]):
            self.assertEqual(site_chrome.brief_target("hatteras"), ("hatteras", True))
            self.assertEqual(site_chrome.brief_target("falls-lake"), ("falls-lake", True))
            self.assertEqual(site_chrome.brief_target("wilmington"), ("crystal-coast", False))
            self.assertEqual(site_chrome.brief_target("nags-head"), ("hatteras", False))
            self.assertEqual(site_chrome.brief_target("jordan-lake"), ("falls-lake", False))
            self.assertEqual(site_chrome.brief_target("nope"), ("crystal-coast", False))
        with mock.patch.object(site_chrome, "public_brief_regions", lambda: ["crystal-coast", "hatteras"]):
            self.assertEqual(site_chrome.brief_target("neuse-river"), ("crystal-coast", False))



class Css(unittest.TestCase):
    def test_phone_nav_keeps_map_and_chips_fade(self):
        css = (ROOT / "preview" / "sprint-home" / "hybrid.css").read_text()
        self.assertNotIn(".mh-hybrid .mh-sec a.mh-maps{display:none}", css)
        self.assertIn(".mh-maps-x{display:none}", css)
        self.assertRegex(css, r"\.rr-l\{-webkit-mask-image:linear-gradient")

    def test_feedback_tab_on_phones(self):
        import feedback
        self.assertIn("writing-mode:vertical-rl", feedback.CSS)
        self.assertIn('class="fb-fab"', feedback.embed_html())


def _fake_assemble(region_id=None, preview=False):
    cfg = conditions.load_regions()
    ok = {r["id"] for r in cfg["regions"] if conditions._servable(r, preview=preview)}
    rid = region_id or cfg["default"]
    if rid not in ok:
        return 404, {"ok": False, "error": "Unknown region."}
    return 200, {"ok": True, "region": {"id": rid, "name": rid}, "readings": {}, "alerts": {"status": "ok", "items": []},
                 "marine": {"status": "unavailable"}, "forecast": {"status": "unavailable"}, "tides": {"status": "unavailable"},
                 "generatedAt": "2026-11-19T16:00:00Z"}


class Pages(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for k in ("MORNING_BRIEF_ENABLED", "FRESHWATER_ENABLED", "PREVIEW_KEY"):
            os.environ.pop(k, None)
        import server
        cls.server = server
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.base = "http://127.0.0.1:%d" % cls.httpd.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown(); cls.httpd.server_close()

    def _get(self, path):
        try:
            with urllib.request.urlopen(self.base + path, timeout=30) as r:
                return r.status, r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8", "replace")

    def test_unknown_region_api_is_404_not_crystal_coast(self):
        with mock.patch.dict(os.environ, {"MORNING_BRIEF_ARCHIVE_URL": ""}):
            st, payload = conditions.assemble("atlantic-beach")
            self.assertEqual((st, payload.get("ok")), (404, False))
            st, payload = conditions.assemble("cape-fear-river")
            self.assertEqual(st, 404)
            st, payload = conditions.assemble("no-such-place")
            self.assertEqual(st, 404)

    def test_unknown_region_html_is_404_page_with_nav(self):
        with mock.patch.object(conditions, "assemble", _fake_assemble):
            for path in ("/?region=atlantic-beach", "/dashboard?region=bogus", "/?region=cape-fear-river"):
                st, body = self._get(path)
                self.assertEqual(st, 404, path)
                self.assertIn('class="mh-sec"', body)
                self.assertIn("Region not found", body)
                self.assertNotIn("atlantic-beach", body.replace('href="/?region=atlantic-beach"', ""))
                self.assertNotIn("Cape Fear", body)  # private preview never named

    def test_no_brief_page(self):
        st, body = self._get("/brief?region=wilmington")
        self.assertEqual(st, 404)
        self.assertIn('class="mh-sec"', body)
        self.assertIn('href="/brief?region=crystal-coast"', body)
        self.assertIn('href="/brief?region=hatteras"', body)
        self.assertIn("noindex", body)
        st, body = self._get("/brief?region=cape-fear-river")
        self.assertEqual(st, 404)
        self.assertIn("There is no Morning Brief for that area.", body)
        self.assertNotIn("Cape Fear", body)

    def test_feedback_page_has_section_nav(self):
        st, body = self._get("/feedback")
        self.assertEqual(st, 200)
        self.assertIn('<nav class="mh-sec" aria-label="Sections">', body)
        for href in ('href="/"', 'href="/catch-wall"', 'href="/dashboard"', 'href="/brief?region=crystal-coast"'):
            self.assertIn(href, body)

    def test_lake_titles(self):
        with mock.patch("freshwater.assemble", return_value=(200, {"ok": True})):
            for rid, name in (("jordan-lake", "Jordan Lake"), ("neuse-river", "Neuse River"), ("falls-lake", "Falls Lake")):
                st, body = self._get("/lake?region=" + rid)
                self.assertEqual(st, 200)
                self.assertEqual(re.search(r"<title>([^<]*)</title>", body).group(1), "%s \u00b7 The Coastal Brief" % name)

    def test_coastal_life_title(self):
        st, body = self._get("/coastal-life")
        self.assertEqual(st, 200)
        self.assertEqual(re.search(r"<title>([^<]*)</title>", body).group(1), "Coastal Life \u2014 The Coastal Brief")

    def test_home_header_brief_follows_region(self):
        import sprint_home
        with mock.patch.object(conditions, "assemble", _fake_assemble):
            for rid, want in (("hatteras", "hatteras"), ("wilmington", "crystal-coast"), ("nags-head", "hatteras")):
                html = sprint_home.page("hybrid", rid, public=True).decode("utf-8")
                self.assertIn('<a href="/brief?region=%s" id="nav-brief">' % want, html, rid)
                self.assertIn('class="mh-maps" href="/dashboard">Map<span class="mh-maps-x"> &amp; tides</span>', html)
            html = sprint_home.page("hybrid", "wilmington", public=True).decode("utf-8")
            self.assertIn('href="/brief?region=crystal-coast">Nearest Morning Brief:', html)
            html = sprint_home.page("hybrid", "hatteras", public=True).decode("utf-8")
            self.assertIn('href="/brief?region=hatteras">Today\'s Morning Brief</a>', html)


if __name__ == "__main__":
    unittest.main()
