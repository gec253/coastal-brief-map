"""Phase 3B Before You Launch (private): data integrity, freshness, cache, per-source failure, privacy."""
import json
import math
import re
import threading
import unittest
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import byl_data as B
import byl_page as P

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 11, 28, 17, 0, tzinfo=timezone.utc)
SITES, RECS = B.load_sites(), B.load_records()
FALLS, UNION, CEDAR, EMERALD = "parks-falls-rolling-view", "local-newbern-union-point", "baa-gordon-s-myers-at-cedar-point", "baa-emerald-isle"


def iso(dt):
    return dt.isoformat()


def usgs_payload(age_h=0.5, ids=None):
    t = NOW - timedelta(hours=age_h)
    ts = []
    for sid in ids or ["02087182", "02087183"]:
        for pc, v in (("62614", 245.8), ("00010", 13.3), ("00060", 30.0), ("00065", 4.2)):
            ts.append({"sourceInfo": {"siteCode": [{"value": sid}]}, "variable": {"variableCode": [{"value": pc}]},
                       "values": [{"value": [{"dateTime": iso(t - timedelta(hours=6)), "value": str(v)}, {"dateTime": iso(t), "value": str(v)}]}]})
    return {"value": {"timeSeries": ts}}


def src_of(url):
    if "alerts" in url:
        return "nws_alerts"
    if "tgftp" in url:
        return "nws_marine"
    if "/stations/" in url:
        return "nws_obs"
    if "weather.gov" in url:
        return "nws_forecast"
    if "usgs" in url:
        return "usgs"
    if "usace" in url:
        return "usace"
    if re.search(r"product=(wind|water_temperature|water_level)", url):
        return "coops_obs"
    return "coops"


MARINE_TXT = """Expires:202611290515;;088680
AMZ137-290515-
Neuse and Bay Rivers-
1112 AM EST Sat Nov 28 2026

.REST OF TODAY...W winds 10 to 15 kt. Waves a moderate chop.
.TONIGHT...W winds 5 to 10 kt. Waves light chop.
$$
"""


def fake(down=(), timeout=(), usgs_age=0.5, usace_day="27NOV2026", alerts=None, obs_age=0.3, marine_issued="1112 AM EST Sat Nov 28 2026"):
    calls = []

    def opener(url, t):
        calls.append(url)
        src = src_of(url)
        if src in down:
            raise OSError("down")
        if src in timeout:
            raise TimeoutError("timed out")
        if src == "nws_forecast":
            per = [{"name": "Today", "startTime": iso(NOW + timedelta(hours=i)), "temperature": 62, "temperatureUnit": "F", "windDirection": "SW",
                    "windSpeed": "%d mph" % (5 + i), "shortForecast": "Sunny"} for i in range(12)]
            return json.dumps({"properties": {"updateTime": iso(NOW - timedelta(hours=2)), "periods": per}}).encode()
        if src == "nws_alerts":
            return json.dumps({"features": alerts or []}).encode()
        if src == "nws_obs":
            return json.dumps({"features": [{"properties": {"timestamp": iso(NOW - timedelta(hours=obs_age)), "windSpeed": {"value": 18.5}, "windGust": {"value": 27.8},
                                                            "windDirection": {"value": 250}}}]}).encode()
        if src == "nws_marine":
            return MARINE_TXT.replace("1112 AM EST Sat Nov 28 2026", marine_issued).encode()
        if src == "usgs":
            return json.dumps(usgs_payload(usgs_age)).encode()
        if src == "usace":
            return ("Date Elev\n%s  300.1 302.0 973.9 973.5 216.07 251.90 1029.9\n" % usace_day).encode()
        if src == "coops_obs":
            t = (NOW - timedelta(hours=obs_age)).strftime("%Y-%m-%d %H:%M")
            if "product=wind" in url:
                return json.dumps({"data": [{"t": t, "s": "9.0", "d": "250", "g": "14.0"}]}).encode()
            return json.dumps({"data": [{"t": (NOW - timedelta(hours=h)).strftime("%Y-%m-%d %H:%M"), "v": "%.2f" % (2 + h / 10)} for h in range(6, -1, -1)]}).encode()
        if "interval=h&" in url:
            return json.dumps({"predictions": [{"t": (NOW.astimezone(B.ET) + timedelta(hours=h - 5)).strftime("%Y-%m-%d %H:00"), "v": "%.2f" % (1 + math.sin(h / 2))}
                                               for h in range(30)]}).encode()
        return json.dumps({"predictions": [{"t": "2026-11-28 15:00", "type": "H", "v": "2.1"}, {"t": "2026-11-28 21:10", "type": "L", "v": "0.2"}]}).encode()
    f = B.Fetcher(opener=opener, clock=lambda: 1000.0)
    return f, calls


def run(sid, **kw):
    f, calls = fake(**kw)
    return B.assemble(sid, f=f, now=NOW, sites=SITES, records=RECS), calls


class Integrity(unittest.TestCase):
    def test_only_reviewed_publishable_stations_are_requested(self):
        reviewed_usgs = set(B.all_usgs())
        cz = B.load_coastal()
        for sid in SITES:
            d, calls = run(sid)
            pub = {c["id"] for c in SITES[sid]["stations"] if c["publishable"]}
            pub |= {x["id"] for x in B.accepted((cz.get(sid) or {}).get("wind")) + B.accepted((cz.get(sid) or {}).get("water"))}
            for u in calls:
                m = re.search(r"sites=([\d,]+)", u)
                if m:
                    self.assertTrue(set(m.group(1).split(",")) <= reviewed_usgs, sid)
                m = re.search(r"station=(\w+)", u) or re.search(r"/stations/(\w+)/", u)
                if m:
                    self.assertIn(m.group(1), pub, sid)
            shown = {c["source"].split(" · ")[0].split()[-1] for c in d["cards"].values() if c.get("source", "").startswith(("USGS", "NOAA CO-OPS", "NWS ASOS"))}
            self.assertTrue(shown <= pub, (sid, shown - pub))

    def test_unresolved_water_gets_forecast_but_no_water_readings(self):
        unresolved = [s for s, e in SITES.items() if e["water_class"] == "unresolved"]
        self.assertEqual(len(unresolved), 10)
        for sid in unresolved:
            d, calls = run(sid)
            self.assertTrue(d["withheld"])
            self.assertIn("forecast", d["cards"])
            self.assertEqual(d["cards"]["forecast"]["kind"], "fcst")
            self.assertFalse(set(d["cards"]) - {"forecast", "alerts", "sun", "wind_obs", "marine"}, sid)
            self.assertFalse([u for u in calls if "usgs" in u or "product=predictions" in u or "water_level" in u or "water_temperature" in u or "usace" in u])

    def test_no_tide_on_wind_driven_or_freshwater(self):
        for sid, e in SITES.items():
            d, _ = run(sid)
            if e["tide_policy"] != "predictions":
                self.assertNotIn("tide", d["cards"], sid)

    def test_no_marine_alert_on_freshwater(self):
        al = [{"properties": {"event": "Small Craft Advisory", "affectedZones": ["https://api.weather.gov/zones/forecast/AMZ136"]}},
              {"properties": {"event": "Wind Advisory", "affectedZones": ["https://api.weather.gov/zones/forecast/NCZ041"]}}]
        d, _ = run(FALLS, alerts=al)
        self.assertEqual([a["event"] for a in d["cards"]["alerts"]["alerts"]], ["Wind Advisory"])
        d, _ = run(CEDAR, alerts=al)
        self.assertEqual(len(d["cards"]["alerts"]["alerts"]), 2)

    def test_empty_alerts_is_not_an_all_clear(self):
        d, _ = run(FALLS)
        self.assertIn("not an all-clear", P.card_html(d["cards"]["alerts"]))

    def test_downstream_flow_label_never_dam_release(self):
        d, _ = run(FALLS)
        c = d["cards"]["below_dam"]
        self.assertEqual(c["label"], "River flow below the dam (measured)")
        html = P.render(FALLS, SITES, RECS) + json.dumps(P.fragments(d))
        self.assertNotIn("dam release", html.lower().replace("not a reported dam release", ""))
        self.assertIn("not a reported dam release", c["note"])

    def test_no_safe_language(self):
        for sid in (FALLS, UNION, CEDAR, EMERALD):
            d, _ = run(sid)
            txt = (P.render(sid, SITES, RECS) + json.dumps(P.fragments(d))).lower()
            for w in ("safe to launch", "good to go", "conditions are good", "all clear", "open now", "is open"):
                self.assertNotIn(w, txt, sid)

    def test_access_is_recorded_not_live(self):
        h = P.render(UNION, SITES, RECS)
        self.assertIn("Recorded status", h)
        self.assertIn("not a live check", h)
        self.assertIn('class="ico unc"', h)

    def test_unresolved_jurisdiction_shows_both_regs_and_explains(self):
        h = P.render(UNION, SITES, RECS)
        self.assertIn("NCDMF", h); self.assertIn("NCWRC", h); self.assertIn("official boundary map", h)
        h = P.render(FALLS, SITES, RECS)
        self.assertIn("NCWRC", h); self.assertNotIn("official boundary map", h)

    def test_union_point_and_cedar_point_reconciliation(self):
        d, _ = run(UNION)
        self.assertEqual(set(d["cards"]), {"forecast", "alerts", "sun", "wind_obs", "marine"})
        self.assertIn("KEWN", d["cards"]["wind_obs"]["source"])
        self.assertIn("AMZ137", d["cards"]["marine"]["source"])
        self.assertIn("No reviewed water gauge", P.render(UNION, SITES, RECS))
        d, _ = run(CEDAR)
        self.assertEqual(set(d["cards"]), {"forecast", "alerts", "sun", "tide", "wind_obs", "marine"})
        self.assertIn("8656613", d["cards"]["tide"]["source"])
        self.assertIn("Ocean beyond the inlet", d["cards"]["marine"]["label"])

    def test_no_operator_readings(self):
        for sid in SITES:
            d, calls = run(sid)
            self.assertFalse([u for u in calls if re.search(r"duke|dominion|tva|cube", u, re.I)])

    def test_page_shell_has_no_third_party_scripts_and_bar_padding(self):
        h = P.render(FALLS, SITES, RECS)
        self.assertFalse(re.findall(r'<script[^>]+src="https?://', h))
        self.assertIn('name="robots" content="noindex, nofollow"', h)
        css = (ROOT / "preview/before-you-launch/byl.css").read_text()
        self.assertIn("padding-bottom:calc(var(--barh", css)
        self.assertIn("safe-area-inset-bottom", css)
        self.assertIn("prefers-reduced-motion", css)
        self.assertIn("min-height:44px", css)


class Freshness(unittest.TestCase):
    def test_usgs_fresh_stale_too_old(self):
        self.assertEqual(run(FALLS, usgs_age=1)[0]["cards"]["lake"]["kind"], "obs")
        self.assertEqual(run(FALLS, usgs_age=4)[0]["cards"]["lake"]["kind"], "stale")
        c = run(FALLS, usgs_age=25)[0]["cards"]["lake"]
        self.assertEqual(c["kind"], "unav"); self.assertNotIn("value", c)

    def test_usace_stale_and_old(self):
        self.assertEqual(run(FALLS, usace_day="27NOV2026")[0]["cards"]["usace"]["kind"], "obs")
        self.assertEqual(run(FALLS, usace_day="26NOV2026")[0]["cards"]["usace"]["kind"], "stale")
        self.assertEqual(run(FALLS, usace_day="22OCT2026")[0]["cards"]["usace"]["kind"], "unav")

    def test_stale_card_says_stale(self):
        d = run(FALLS, usgs_age=4)[0]
        self.assertIn("Stale", P.card_html(d["cards"]["lake"]))

    def test_water_temp_converted_and_labelled(self):
        c = run(FALLS)[0]["cards"]["temp"]
        self.assertEqual(c["unit"], "°F"); self.assertAlmostEqual(c["value"], 56, delta=1)


class Cache(unittest.TestCase):
    def test_ttl_and_backoff(self):
        t = [1000.0]
        n = {"c": 0, "fail": False}

        def op(url, to):
            n["c"] += 1
            if n["fail"]:
                raise OSError
            return b'{"ok":1}'
        f = B.Fetcher(opener=op, clock=lambda: t[0])
        f.get("usgs", "u1"); f.get("usgs", "u1")
        self.assertEqual(n["c"], 1)
        t[0] += B.SOURCES["usgs"]["ttl"] + 1
        n["fail"] = True
        self.assertEqual(f.get("usgs", "u1"), {"ok": 1})  # failed refresh: last known good (Phase 3C), still dated by its own readings
        self.assertIn("u1", f.lkg_used)
        with self.assertRaises(B.SourceDown):
            f.get("usgs", "u2")  # backing off: no request made, and nothing cached to fall back on
        self.assertEqual(n["c"], 2)
        t[0] += B.SOURCES["usgs"]["backoff"] + 1
        n["fail"] = False
        self.assertEqual(f.get("usgs", "u2"), {"ok": 1})
        self.assertEqual(n["c"], 3)

    def test_sources_fail_independently(self):
        f = B.Fetcher(opener=lambda u, t: (_ for _ in ()).throw(OSError()) if "usgs" in u else b"{}", clock=lambda: 1.0)
        with self.assertRaises(B.SourceDown):
            f.get("usgs", "https://usgs/x")
        self.assertEqual(f.get("nws_alerts", "https://api.weather.gov/alerts"), {})


class SourceFailure(unittest.TestCase):
    def check(self, mode):
        for src, keys in (("nws_forecast", ["forecast"]), ("nws_alerts", ["alerts"]), ("usgs", ["lake", "temp", "below_dam"]),
                          ("usace", ["usace"]), ("coops", ["tide"]), ("nws_obs", ["wind_obs"]), ("nws_marine", ["marine"]), ("coops_obs", ["coastal_temp", "water_level"])):
            sid = {"coops": CEDAR, "nws_obs": UNION, "nws_marine": UNION, "coops_obs": "baa-west-beaufort"}.get(src, FALLS)
            d, _ = run(sid, **{mode: (src,)})
            for k in keys:
                self.assertEqual(d["cards"][k]["kind"], "unav", (src, k))
                self.assertNotIn("value", d["cards"][k])
            others = [k for k, c in d["cards"].items() if k not in keys]
            self.assertTrue(others)
            for k in others:
                self.assertNotEqual(d["cards"][k]["kind"], "unav", (src, k))

    def test_each_source_down(self):
        self.check("down")

    def test_each_source_timeout(self):
        self.check("timeout")

    def test_unavailable_cards_carry_no_numbers(self):
        d, _ = run(FALLS, down=("usgs", "usace", "nws_forecast", "nws_alerts"))
        for k, c in d["cards"].items():
            if k != "sun":
                self.assertEqual(c["kind"], "unav")
                self.assertFalse(re.search(r"\d+(\.\d+)?\s?(ft|cfs|°F)", P.card_html(c)), k)


class Privacy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import os
        import server
        cls.server = server
        os.environ["PREVIEW_KEY"] = "localtest-byl-key-000000000001"
        cls.httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler) if hasattr(server, "Handler") else None
        if cls.httpd is None:
            raise unittest.SkipTest("no handler")
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.base = "http://127.0.0.1:%d" % cls.httpd.server_address[1]
        cls.cookie = "%s=%s" % (server.PREVIEW_COOKIE, server._preview_cookie_value("localtest-byl-key-000000000001"))

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()

    def status(self, path, cookie=None):
        req = urllib.request.Request(self.base + path, headers={"Cookie": cookie} if cookie else {})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, dict(r.headers)
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers)

    def test_404_without_cookie(self):
        for p in ("/preview/before-you-launch", "/preview/before-you-launch/", "/preview/before-you-launch/" + FALLS,
                  "/preview/before-you-launch/%s.json" % FALLS, "/preview/before-you-launch/byl.css", "/preview/before-you-launch/byl.js"):
            self.assertEqual(self.status(p)[0], 404, p)

    def test_cookie_pages_are_noindex_and_non_pilot_404(self):
        s, h = self.status("/preview/before-you-launch/" + FALLS, self.cookie)
        self.assertEqual(s, 200)
        self.assertIn("noindex", h.get("X-Robots-Tag", ""))
        self.assertEqual(h.get("Cache-Control"), "no-store")
        non_pilot = next(i for i in RECS if i not in SITES)
        self.assertEqual(self.status("/preview/before-you-launch/" + non_pilot, self.cookie)[0], 404)
        self.assertEqual(self.status("/preview/before-you-launch/../server.py", self.cookie)[0], 404)

    def test_not_in_sitemap(self):
        s, _ = self.status("/sitemap.xml")
        with urllib.request.urlopen(self.base + "/sitemap.xml", timeout=10) as r:
            self.assertNotIn(b"before-you-launch", r.read())


if __name__ == "__main__":
    unittest.main()
