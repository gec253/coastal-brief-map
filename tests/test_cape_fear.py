"""Private Cape Fear River preview: cookie gate, brief, river_gate, and unchanged public lakes."""
from __future__ import annotations

import copy
import hashlib
import hmac
import json
import os
import re
import sys
import threading
import unittest
from datetime import datetime, timedelta, timezone
from http.client import HTTPConnection
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import brief  # noqa: E402
import brief_preview  # noqa: E402
import brief_strings  # noqa: E402
import freshwater  # noqa: E402
import preview_alerts  # noqa: E402
import preview_copy  # noqa: E402
import preview_zones  # noqa: E402
import river_gate  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
KEY = "preview-test-key-24-chars-ok"
NOW = datetime(2026, 11, 15, 15, 0, tzinfo=timezone.utc)
T = "2026-11-15T14:20:00+00:00"
RID = "cape-fear-river"
HUSKE_NOTE = (
    "Please subtract 32.09 ft from the AHPS levels to match the reports "
    "from the USGS location number 02105500."
)
ALERT_NAMES = preview_zones.format_alert_areas(preview_alerts.zone_ids(rid="cape-fear-river"))

def _county_names(phrase: str) -> list[str]:
    s = re.sub(r"\bcounties\b|\bcounty\b", "", phrase or "", flags=re.I)
    s = s.replace("&", " and ")
    return [p.strip().lower() for p in re.split(r",| and ", s) if p.strip()]
ZONE_RE = re.compile(r"\b(?:NCZ|NCC)\d+\b")
FORECAST_FLOWS = {"02102500": 8888, "02104000": 7777, "02105500": 6666, "02105769": 5555}


def _obs(value, hours_ago=0.7, stale=False, time=None):
    if time is None:
        time = (NOW - timedelta(hours=hours_ago)).isoformat()
    return {"value": value, "time": time, "ageH": hours_ago, "stale": stale or hours_ago > river_gate.USGS_FRESH_H}


def _fc(hours_ago=3.0, crest=9.4, lid_time_hours=-3, flow=615):
    return {
        "issued": (NOW - timedelta(hours=hours_ago)).isoformat(),
        "crestStage": crest,
        "crestTime": (NOW - timedelta(hours=lid_time_hours)).isoformat(),
        "category": "no_flooding",
        "crestFlowCfs": flow,
    }


def _block(usgs, lid, label, stage, flow, hours=0.7, forecast=None, **extra):
    nw = {"lid": lid, "status": "ok"}
    if forecast:
        nw["forecast"] = forecast
    out = {"usgs": usgs, "label": label, "kind": "observed", "regulated": True,
           "stageFt": _obs(stage, hours) if stage is not None else None,
           "flowCfs": _obs(flow, hours) if flow is not None else None,
           "url": "https://waterdata.usgs.gov/monitoring-location/%s/" % usgs,
           "nwps": nw}
    out.update(extra)
    return out


def _cape(hours=0.7, forecast_h=3.0, alerts="ok", water_temp=None):
    fay_fc = _fc(forecast_h, 9.4) if forecast_h is not None else None
    payload = {
        "ok": True,
        "generatedAt": NOW.isoformat(),
        "region": {
            "id": RID,
            "name": "Cape Fear River (Lillington to Lock 1)",
            "area": "Harnett, Cumberland & Bladen counties",
            "anchor": freshwater.regions()[RID]["anchor"],
            "waterType": "freshwater",
            "instrumentSet": "freshwater-river",
        },
        "lake": None,
        "waterTemp": water_temp or {
            "kind": "observed", "status": "unavailable", "c": None, "f": None,
            "time": None, "stale": None,
            "note": "No current USGS water-temperature observation on the Cape Fear main stem.",
        },
        "rain": None,
        "release": None,
        "inflows": [],
        "river": [
            _block("02102500", "LLLN7", "Cape Fear River at Lillington", 1.50, 295.0, hours),
            _block("02104000", "FAYN7", "Cape Fear River at Fayetteville", 9.44, 416.0, hours, forecast=fay_fc),
            _block("02105500", "STPN7", "Cape Fear River at W.O. Huske Lock near Tarheel", 0.98, 541.0, hours,
                   forecast=_fc(forecast_h, 33.1) if forecast_h is not None else None,
                   note=HUSKE_NOTE, nwpsMinusUsgsFt=32.09),
            _block("02105769", "CPFN7", "Cape Fear River at Lock 1 near Kelly", 14.60, 528.0, hours),
        ],
        "forecast": {"status": "ok", "updated": (NOW - timedelta(hours=1)).isoformat(),
                     "periods": [{"name": "Today", "tempF": 62, "short": "Sunny",
                                  "windDir": "NW", "windMph": "5 mph"}]},
        "alerts": preview_alerts.ok_coverage(RID) if alerts == "ok" else {"status": alerts, "items": [], "coverage": []},
    }
    return payload


class ConfigAndUnchanged(unittest.TestCase):
    def test_cape_fear_is_private_preview_ready(self):
        r = freshwater.regions()[RID]
        self.assertTrue(r["previewReady"])
        self.assertFalse(r["enabled"])
        self.assertFalse(r["draft"])
        self.assertEqual(r["instrumentSet"], "freshwater-river")
        self.assertTrue(freshwater.is_preview_region(RID))
        self.assertFalse(freshwater.is_preview_region("falls-lake"))
        self.assertFalse(freshwater.is_preview_region("jordan-lake"))
        self.assertFalse(freshwater.is_preview_region("neuse-river"))

    def test_huske_note_and_gauges(self):
        r = freshwater.regions()[RID]
        ids = [s["usgs"] for s in r["river"]]
        self.assertEqual(ids, ["02102500", "02104000", "02105500", "02105769"])
        self.assertNotIn("02103770", ids)  # Cross Creek tributary
        huske = next(s for s in r["river"] if s["usgs"] == "02105500")
        self.assertEqual(huske["note"], HUSKE_NOTE)
        self.assertEqual(huske["nwpsMinusUsgsFt"], 32.09)
        self.assertEqual(huske["nwps"], "STPN7")
        self.assertEqual(r["alertZones"], ["NCZ077", "NCZ088", "NCZ096"])

    def test_falls_jordan_neuse_still_public(self):
        for rid in ("falls-lake", "jordan-lake", "neuse-river"):
            r = freshwater.regions()[rid]
            self.assertTrue(r["enabled"], rid)
            self.assertTrue(r["previewReady"], rid)
            self.assertFalse(r.get("draft"), rid)
        self.assertEqual(brief.enabled_regions(True), ["crystal-coast", "hatteras", "falls-lake"])
        self.assertNotIn(RID, brief.enabled_regions(True))
        self.assertNotIn(RID, brief.enabled_regions(False))


    def test_header_counties_match_alert_checked_counties(self):
        """The /lake and brief header names the same counties the alert check covers."""
        area = freshwater.regions()[RID]["area"]
        alert_phrase = preview_zones.format_alert_areas(preview_alerts.zone_ids(rid=RID))
        self.assertEqual(_county_names(area), _county_names(alert_phrase))
        self.assertEqual(_county_names(area), ["harnett", "cumberland", "bladen"])
        self.assertNotIn("columbus", " ".join(_county_names(area)))
        self.assertEqual(area, "Harnett, Cumberland & Bladen counties")
        self.assertEqual(alert_phrase, ALERT_NAMES)

    def test_public_pickers_omit_cape_fear(self):
        for rel in ("lake.html", "region-nav.js", "dashboard.js"):
            text = (ROOT / rel).read_text()
            self.assertNotIn("cape-fear-river", text, rel)
            self.assertIn("neuse-river", text, rel)


class GateFixtures(unittest.TestCase):
    def test_fresh_four_gauges_passes(self):
        g = river_gate.evaluate(RID, _cape(), NOW)
        self.assertTrue(g["ok"], g["errors"])
        self.assertIn(ALERT_NAMES, " ".join(c["reason"] for c in g["checks"]))

    def test_two_of_four_passes(self):
        p = _cape()
        p["river"][2]["stageFt"] = p["river"][2]["flowCfs"] = None
        p["river"][3]["stageFt"] = p["river"][3]["flowCfs"] = None
        g = river_gate.evaluate(RID, p, NOW)
        self.assertTrue(g["ok"], g["errors"])

    def test_only_one_gauge_fails(self):
        p = _cape()
        for b in p["river"][1:]:
            b["stageFt"] = b["flowCfs"] = None
        g = river_gate.evaluate(RID, p, NOW)
        self.assertFalse(g["ok"])

    def test_full_alert_coverage_passes(self):
        p = _cape()
        p["alerts"] = preview_alerts.ok_coverage(RID)
        g = river_gate.evaluate(RID, p, NOW)
        self.assertTrue(g["ok"], g["errors"])
        c = next(x for x in g["checks"] if x["id"] == "alerts")
        self.assertEqual(c["status"], "pass")
        self.assertIn(ALERT_NAMES, c["reason"])

    def test_partial_alert_coverage_fails(self):
        p = _cape()
        p["alerts"] = preview_alerts.failed_coverage(RID, ["NCC017"])
        g = river_gate.evaluate(RID, p, NOW)
        self.assertFalse(g["ok"])
        c = next(x for x in g["checks"] if x["id"] == "alerts")
        self.assertEqual(c["status"], "failed-fetch")
        self.assertIn("Bladen County (NCC017)", c["reason"])
        self.assertIn(ALERT_NAMES, c["reason"])
        self.assertIn("NCZ077", c["reason"])
        self.assertTrue(any("Bladen County (NCC017)" in e for e in g["errors"]))

    def test_missing_coverage_fails(self):
        p = _cape()
        p["alerts"] = {"status": "ok", "items": [], "coverage": []}
        g = river_gate.evaluate(RID, p, NOW)
        self.assertFalse(g["ok"])
        self.assertIn("Harnett County (NCZ077)", next(x for x in g["checks"] if x["id"] == "alerts")["reason"])

    def test_water_temp_na_is_not_a_failure(self):
        g = river_gate.evaluate(RID, _cape(), NOW)
        c = next(x for x in g["checks"] if x["id"] == "water-temp")
        self.assertEqual(c["status"], "n/a")
        self.assertTrue(g["ok"], g["errors"])

    def test_neuse_and_jordan_gates_still_pass(self):
        import tests.test_river_gate as tg
        ng = river_gate.evaluate("neuse-river", tg._neuse(), tg.NOW)
        jg = river_gate.evaluate("jordan-lake", tg._jordan(), tg.NOW)
        self.assertTrue(ng["ok"], ng["errors"])
        self.assertTrue(jg["ok"], jg["errors"])


class ComposeAndTake(unittest.TestCase):
    def setUp(self):
        brief_preview._cache.clear()

    def tearDown(self):
        brief_preview._cache.clear()

    def test_never_stores_or_archives(self):
        with patch.object(freshwater, "assemble", return_value=(200, _cape())), \
                patch.object(brief, "_save") as save, patch.object(brief, "build") as build, \
                patch.object(brief, "compose") as pub:
            before = dict(brief._mem)
            b = brief_preview.compose(RID, NOW)
            save.assert_not_called()
            build.assert_not_called()
            pub.assert_not_called()
            self.assertEqual(brief._mem, before)
        self.assertTrue(b["preview"])
        self.assertEqual(b["reason"], "preview")
        self.assertTrue(brief_preview.available(RID))

    def test_huske_note_and_no_invented_temp(self):
        with patch.object(freshwater, "assemble", return_value=(200, _cape())):
            b = brief_preview.compose(RID, NOW)
        d = dict(b["items"])
        self.assertIn(HUSKE_NOTE, d["Cape Fear River at W.O. Huske Lock near Tarheel"])
        self.assertIn("AHPS", d["Cape Fear River at W.O. Huske Lock near Tarheel"])
        self.assertNotIn("Water temp", d)
        self.assertIn(("Water temp", brief_strings.not_measured("Water temp")), b["unavailable"])
        blob = " ".join(v for _, v in b["items"]).lower()
        self.assertNotIn("depth", blob.replace("it is not water depth.", ""))

    def test_take_is_three_verified_sentences(self):
        with patch.object(freshwater, "assemble", return_value=(200, _cape())):
            b = brief_preview.compose(RID, NOW)
        model = b["captainsTake"]
        self.assertEqual(model["heading"], "Captain's Take")
        self.assertLessEqual(len(model["sentences"]), 3)
        text = preview_copy.take_text(model)
        self.assertEqual(b["summary"], text)
        self.assertIn("At Fayetteville, the river is at", text)
        self.assertIn("USGS 02104000", text)
        self.assertIn("NWS forecasts a crest of 9.4 ft", text)
        self.assertIn(ALERT_NAMES, text)
        self.assertFalse(ZONE_RE.search(text), text)
        low = text.lower()
        self.assertNotIn("fish", low)
        self.assertNotIn("safe", low)
        self.assertNotIn("launch", low)
        self.assertEqual(preview_copy.informal_hits(text), [])

    def test_page_has_one_take_one_sources_panel_and_stage_note(self):
        with patch.object(freshwater, "assemble", return_value=(200, _cape())):
            html = brief_preview.page(brief_preview.compose(RID, NOW))
        self.assertEqual(html.count('id="mb-sources"'), 1)
        self.assertEqual(html.count('<details class="mb-sources"'), 1)
        self.assertIn('<details class="mb-sources" id="mb-sources">', html)
        self.assertEqual(html.count('<div class="mb-take-body">'), 1)
        self.assertEqual(html.count('class="mb-summary mb-take"'), 1)
        glance = html.find('class="mb-glance"')
        take = html.find("mb-summary mb-take")
        self.assertTrue(0 < glance < take)
        self.assertIn(brief_strings.STAGE_NOTE, html)
        self.assertIn(HUSKE_NOTE, html)
        self.assertIn("Not measured in this area", html)
        self.assertIn('href="/preview/brief/cape-fear-river"', html)
        self.assertNotIn('href="/brief?region=cape-fear-river"', html)

    def test_alerts_line_uses_official_names_and_calm_class(self):
        with patch.object(freshwater, "assemble", return_value=(200, _cape())):
            b = brief_preview.compose(RID, NOW)
            html = brief_preview.page(b)
        line = preview_alerts.alert_line({"status": "ok", "items": []}, RID)
        self.assertEqual(line, brief_strings.alerts_none(ALERT_NAMES))
        text = preview_copy.take_text(b["captainsTake"])
        self.assertIn(ALERT_NAMES, text)
        self.assertFalse(ZONE_RE.search(text), text)
        m = re.search(r'<section class="mb-adv is-([^"]+)"[^>]*>.*?<p class="mb-adv-t">(.*?)</p>', html, flags=re.S)
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), "clear")
        visible = re.sub(r"<[^>]+>", "", m.group(2))
        self.assertEqual(visible, brief_strings.alerts_none(ALERT_NAMES)[len("Alerts: "):])
        self.assertFalse(ZONE_RE.search(visible), visible)
        self.assertIn('class="mb-adv is-clear"', html)
        self.assertNotIn("is-active", html[html.find("mb-adv"):html.find("mb-adv") + 80])
        src = ""
        sm = re.search(r'<details class="mb-sources" id="mb-sources">.*?</details>', html, flags=re.S)
        if sm:
            src += sm.group(0)
        jm = re.search(r'<script type="application/json" id="cb-reading-sources">.*?</script>', html, flags=re.S)
        if jm:
            src += jm.group(0)
        for code in preview_alerts.zone_ids(rid=RID):
            self.assertIn(code, src, code)
            self.assertNotIn(code, visible, code)
            self.assertNotIn(code, text, code)

    def test_nwps_forecast_is_stage_only_observed_cfs_remains(self):
        p = copy.deepcopy(_cape())
        for b in p["river"]:
            nw = dict(b.get("nwps") or {"status": "ok"})
            fc = dict(nw.get("forecast") or _fc(crest=3.0, flow=FORECAST_FLOWS[b["usgs"]]))
            fc["crestFlowCfs"] = FORECAST_FLOWS[b["usgs"]]
            nw["forecast"] = fc
            b["nwps"] = nw
        with patch.object(freshwater, "assemble", return_value=(200, p)):
            b = brief_preview.compose(RID, NOW)
            html = brief_preview.page(b)
        take = preview_copy.take_text(b.get("captainsTake") or {})
        items = " ".join(v for _, v in b["items"])
        items_by = dict(b["items"])
        for blob, name in ((items, "items"), (take, "take"), (html, "page")):
            for val in FORECAST_FLOWS.values():
                self.assertNotIn(str(val), blob, name)
            self.assertNotIn("NWS estimate", blob, name)
            self.assertNotIn("NWS flow estimate", blob, name)
            self.assertNotIn("crestFlowCfs", blob, name)
            for m in re.finditer(r"NWS forecast \(NWPS[^)]*\):[^.]*(?:\.|$)", blob):
                self.assertNotIn("cfs", m.group(0).lower(), (name, m.group(0)))
        # Observed USGS discharge is unchanged.
        self.assertIn("416 cfs", items)
        self.assertIn("416 cfs", take)
        self.assertIn("295 cfs", items)
        self.assertIn("541 cfs", items)
        self.assertIn("528 cfs", items)
        # Stage forecast remains, including the Huske AHPS label; no forecast cfs.
        self.assertIn("NWS forecast (NWPS FAYN7)", items_by["Cape Fear River at Fayetteville"])
        self.assertIn("crest 9.4 ft", items_by["Cape Fear River at Fayetteville"])
        self.assertIn("NWS forecasts a crest of 9.4 ft", take)
        huske = items_by["Cape Fear River at W.O. Huske Lock near Tarheel"]
        self.assertIn(HUSKE_NOTE, huske)
        self.assertIn("AHPS", huske)
        self.assertIn("crest 33.1 ft", huske)
        self.assertNotIn("cfs", [s.get("text", "") for s in (b.get("captainsTake") or {}).get("sentences") or []
                                 if "forecast" in ((s.get("kind") or "") + " ".join(s.get("kinds") or []))][0])
        srcs = " ".join("%s %s" % (r.get("label") or "", r.get("station") or "")
                        for r in (b.get("readingSources") or []))
        self.assertIn("NWPS forecast (FAYN7)", srcs)
        glance_cfs = [c["value"] for c in (b.get("glance") or []) if c.get("unit") == "cfs"]
        self.assertEqual(set(glance_cfs), {"416", "295"})
        for c in b.get("glance") or []:
            if c.get("unit") == "cfs":
                self.assertEqual(c.get("kind"), "observed", c)

    def test_assemble_rejects_discontinued_lillington_temp(self):
        from datetime import datetime as dt
        old = dt(2024, 10, 10, 16, 15, tzinfo=timezone.utc)
        now = NOW

        class Frozen(dt):
            @classmethod
            def now(cls, tz=None):
                return now if tz else now.replace(tzinfo=None)

        ivq = {
            ("02102500", "00065"): [(now - timedelta(hours=0.5), 1.5)],
            ("02102500", "00060"): [(now - timedelta(hours=0.5), 295.0)],
            ("02102500", "00010"): [(old, 9.6)],
            ("02104000", "00065"): [(now - timedelta(hours=0.5), 9.44)],
            ("02104000", "00060"): [(now - timedelta(hours=0.5), 416.0)],
            ("02105500", "00065"): [(now - timedelta(hours=0.5), 0.98)],
            ("02105500", "00060"): [(now - timedelta(hours=0.5), 541.0)],
            ("02105769", "00065"): [(now - timedelta(hours=0.5), 14.6)],
            ("02105769", "00060"): [(now - timedelta(hours=0.5), 528.0)],
        }
        freshwater._ASSEMBLED.clear()
        with patch("freshwater.datetime", Frozen), \
                patch("freshwater.usgs_iv", return_value=(ivq, {})), \
                patch("freshwater.usgs_daily_stats", return_value=None), \
                patch("freshwater.nwps", return_value={"lid": "X", "status": "ok"}), \
                patch("freshwater.alerts_point", return_value={"status": "ok", "items": []}), \
                patch("conditions.forecast_block", return_value={"status": "unavailable"}):
            st, body = freshwater.assemble(RID)
        freshwater._ASSEMBLED.clear()
        self.assertEqual(st, 200)
        self.assertNotEqual(body["waterTemp"].get("status"), "ok")
        self.assertIsNone(body["waterTemp"].get("f"))
        self.assertIsNone(body["waterTemp"].get("c"))


class HttpGate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import server
        cls.server = server
        cls.httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.port = cls.httpd.server_address[1]
        cls.cookie = "cb_preview=" + hmac.new(KEY.encode(), b"coastal-brief-preview-v1", hashlib.sha256).hexdigest()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def setUp(self):
        self._saved = {k: os.environ.get(k) for k in ("PREVIEW_KEY", "FRESHWATER_ENABLED")}
        os.environ["PREVIEW_KEY"] = KEY
        os.environ.pop("FRESHWATER_ENABLED", None)
        brief_preview._cache.clear()
        p = patch.object(freshwater, "assemble", return_value=(200, _cape()))
        p.start()
        self.addCleanup(p.stop)

    def tearDown(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        brief_preview._cache.clear()

    def _get(self, path, cookie=None):
        c = HTTPConnection("127.0.0.1", self.port, timeout=10)
        c.request("GET", path, headers={"Cookie": cookie} if cookie else {})
        r = c.getresponse()
        body = r.read()
        hdrs = {k.lower(): v for k, v in r.getheaders()}
        c.close()
        return r.status, body.decode("utf-8", "replace"), hdrs

    def test_public_404s(self):
        for path in ("/lake?region=" + RID, "/api/freshwater?region=" + RID,
                     "/brief?region=" + RID, "/api/brief?region=" + RID,
                     "/preview/brief/" + RID, "/?region=" + RID):
            self.assertEqual(self._get(path)[0], 404, path)

    def test_cookie_unlocks_lake_api_and_preview_brief(self):
        st, body, h = self._get("/lake?region=" + RID, self.cookie)
        self.assertEqual(st, 200)
        self.assertIn("Private preview", body)
        self.assertIn("noindex", h.get("x-robots-tag", ""))
        self.assertIn("cape-fear-river", body)
        st, body, h = self._get("/api/freshwater?region=" + RID, self.cookie)
        self.assertEqual(st, 200)
        self.assertIn("no-store", h.get("cache-control", ""))
        self.assertEqual(json.loads(body)["region"]["id"], RID)
        st, body, h = self._get("/preview/brief/" + RID, self.cookie)
        self.assertEqual(st, 200)
        self.assertIn("Private preview", body)
        self.assertIn(HUSKE_NOTE, body)
        self.assertEqual(h.get("x-robots-tag"), "noindex, nofollow")

    def test_public_brief_stays_404_even_with_cookie(self):
        for path in ("/brief?region=" + RID, "/api/brief?region=" + RID):
            self.assertEqual(self._get(path, self.cookie)[0], 404, path)

    def test_home_redirects_with_cookie_only(self):
        st, _, h = self._get("/?region=" + RID, self.cookie)
        self.assertEqual(st, 303)
        self.assertEqual(h.get("location"), "/lake?region=" + RID)

    def test_hub_and_sitemap(self):
        st, body, _ = self._get("/preview", self.cookie)
        self.assertEqual(st, 200)
        self.assertIn('href="/preview/brief/cape-fear-river"', body)
        self.assertIn('href="/lake?region=cape-fear-river"', body)
        st, body, _ = self._get("/sitemap.xml")
        self.assertNotIn("cape-fear-river", body)
        self.assertNotIn("/preview/brief", body)

    def test_public_lakes_still_200(self):
        for path in ("/lake?region=falls-lake", "/lake?region=jordan-lake",
                     "/lake?region=neuse-river", "/brief?region=falls-lake"):
            self.assertEqual(self._get(path)[0], 200, path)


if __name__ == "__main__":
    unittest.main()
