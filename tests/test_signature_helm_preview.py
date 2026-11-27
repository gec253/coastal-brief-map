"""Signature Helm private homepage preview (Ed t529u). Cookie-gated /preview/helm; public routes untouched."""
from __future__ import annotations

import os
import re
import subprocess
import threading
import unittest
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
KEY = "h" * 32
NOW = datetime(2026, 11, 27, 17, 30, tzinfo=timezone.utc)   # 12:30 PM ET
MS = lambda dt: dt.timestamp() * 1000
BASELINE = "21824b4370af06963f945bd3b4e08ca23ffe1670"
FROZEN = ("wind.html", "wind-viewer.js", "wind.css", "wind-lab.js", "wind-coast.js", "data/wind-labels.json",
          "radar.html", "radar-viewer.js", "radar.css", "radar-player.js", "radarview.py", "data/ads.json", "index.html",
          "sprint_home.py", "homepage_boot.py", "conditions.py", "freshwater.py")


def _iso(dt):
    return dt.isoformat()


def _rd(values, sid="CLKN7", name="Cape Lookout", status="ok", age=timedelta(minutes=20)):
    return {"status": status, "values": values, "station": {"id": sid, "name": name}, "time": _iso(NOW - age)}


def salt_payload(alerts=None, seas_status="ok", wind_status="ok", tide_ok=True):
    curve = [[MS(NOW + timedelta(minutes=6 * i - 240)), round(1.5 + 1.5 * __import__("math").sin(i / 20), 3)] for i in range(240)]
    events = [{"t": MS(NOW + timedelta(hours=3, minutes=36)), "v": 0.1, "type": "L"},
              {"t": MS(NOW + timedelta(hours=9, minutes=31)), "v": 3.1, "type": "H"}]
    return {
        "ok": True, "generatedAt": _iso(NOW),
        "region": {"id": "crystal-coast", "name": "Morehead City · Beaufort",
                   "anchor": {"label": "Beaufort Inlet", "lat": 34.695, "lon": -76.668}},
        "readings": {
            "wind": _rd({"speedKt": 19, "gustKt": 29, "dirDeg": 247.5, "dirCompass": "WSW"}, status=wind_status),
            "seas": _rd({"heightFt": 11.8, "dominantPeriodS": 9, "meanDirCompass": "S"}, "41159", "Onslow Bay Outer", status=seas_status),
            "swell": _rd({"heightFt": 3.0, "periodS": 11, "dirCompass": "S"}, "41159", "Onslow Bay Outer"),
            "waterTemp": _rd({"f": 60}, "8656483", "Beaufort, Duke Marine Lab"),
            "airTemp": _rd({"f": 51}, "8656483", "Beaufort, Duke Marine Lab"),
            "pressure": _rd({"inHg": 29.83, "trend": "steady", "change3hInHg": -0.01}, "8656483", "Beaufort, Duke Marine Lab"),
        },
        "tides": ({"status": "ok", "kind": "predicted", "station": {"id": "8656483", "name": "Beaufort, Duke Marine Lab"},
                   "datum": "MLLW", "events": events, "curve": curve} if tide_ok else {"status": "unavailable"}),
        "marine": {"status": "ok", "office": "NWS Newport/Morehead City (MHX)", "zone": "AMZ158", "updated": _iso(NOW - timedelta(hours=7)),
                   "periods": [{"name": "Today", "text": "W winds 25 to 30 kt. Seas 8 to 11 ft."}]},
        "alerts": alerts if alerts is not None else {"status": "ok", "zones": [], "items": [
            {"event": "High Surf Advisory", "ends": _iso(NOW + timedelta(hours=4))},
            {"event": "Gale Warning", "ends": _iso(NOW + timedelta(hours=10))}]},
    }


def lake_payload(elev=245.71, stale=False):
    t = _iso(NOW - timedelta(minutes=30))
    return {
        "ok": True, "generatedAt": _iso(NOW),
        "region": {"id": "falls-lake", "name": "Falls Lake", "anchor": {"label": "Falls Lake Dam (USGS 02087182)", "lat": 35.9411, "lon": -78.5833}},
        "lake": {"usgs": "02087182", "elevation": ({"value": elev, "time": t, "stale": stale} if elev is not None else None),
                 "datum": "NGVD29", "guideCurveFt": 251.5, "vsGuideFt": (round(elev - 251.5, 2) if elev is not None else None),
                 "change24hFt": 0.41, "change7dFt": 0.95},
        "release": {"usgs": "02087183", "label": "Neuse River below Falls Dam (release)", "regulated": True,
                    "flowCfs": {"value": 29.4, "time": t}},
        "inflows": [{"usgs": "02085070", "label": "Eno River near Durham", "flowCfs": {"value": 64, "time": t}}],
        "waterTemp": {"status": "ok", "f": 56, "time": t},
        "rain": {"status": "ok", "last24In": 0.05, "time": t, "qpf": {"status": "ok", "next24In": 0.0}},
        "forecast": {"status": "ok", "office": "NWS Raleigh (RAH)", "updated": t, "periods": [{"name": "Today", "detail": "Mostly cloudy."}]},
        "alerts": {"status": "ok", "items": []},
    }


GRID = {"ok": True, "run": "2026-11-27T12:00Z", "valid": "2026-11-27T18:00Z", "forecastHour": 6,
        "nx": 2, "ny": 2, "la1": 37.0, "lo1": -80.0, "dx": 3.0, "dy": 3.0, "scan": 0,
        "u": [5.0, 5.0, 5.0, 5.0], "v": [2.0, 2.0, 2.0, 2.0]}


class Render(unittest.TestCase):
    def setUp(self):
        import server  # noqa: F401  (installs the cache hooks other modules expect)
        import signature_helm
        import sprint_home
        self.sh = signature_helm
        self.p = mock.patch.object(sprint_home, "_now_ms", lambda: MS(NOW))
        self.p.start()
        self.q = mock.patch.object(sprint_home, "_raw_alert_records", lambda a: {})
        self.q.start()

    def tearDown(self):
        self.p.stop()
        self.q.stop()

    def salt(self, **kw):
        return self.sh.build("crystal-coast", now=NOW, salt_payload=salt_payload(**kw), fetch=False)

    def test_labels_and_swell_inside_seas(self):
        h = self.salt()
        for lab in ("OBSERVED", "PREDICTED", "FORECAST"):
            self.assertIn(lab, h)
        seas = re.search(r'<div class="cell seas".*?</div>\s*<div class="cell water"', h, re.S).group(0)
        self.assertIn('id="swell-in-seas"', seas)
        self.assertIn("3.0 ft", seas)
        self.assertNotRegex(h, r'<span class="lk">SWELL')
        self.assertEqual(h.count('id="swell-in-seas"'), 1)
        self.assertIn("MOON PHASE", h)
        self.assertIn("TIDE &amp; LIGHT", h)
        self.assertIn("More than the forecast. It’s a way of life.", h)

    def test_warnings_listed_before_advisories(self):
        h = self.salt()
        self.assertLess(h.index("Gale Warning"), h.index("High Surf Advisory"))
        self.assertLess(h.index(">WARNING<"), h.index(">ADVISORY<"))
        self.assertIn("two red pennants", h)

    def test_gateways_are_labelled_illustrations_without_live_times(self):
        h = self.salt()
        gates = re.search(r'<section class="gates".*?</section>', h, re.S).group(0)
        self.assertEqual(gates.count("Illustration · not live data"), 2)
        for bad in ("OBSERVED", "shown live", "DATA AGE", "GFS RUN", "VALID", " ET<"):
            self.assertNotIn(bad, gates)
        self.assertIn('href="/wind"', gates)
        self.assertIn('href="/radar"', gates)
        self.assertIn("data-feedback-open", gates)   # Feedback only after the instruments
        # The visible Feedback chip sits after the instruments; the only earlier Feedback entry is inside the
        # collapsed All-sections menu (in flow, never floating over content).
        self.assertLess(h.index('id="helm"'), h.index('class="fb-open fb-chip"'))
        menu = re.search(r'<details class="allnav">.*?</details>', h, re.S).group(0)
        self.assertLess(h.index("data-feedback-open"), h.index('id="helm"'))
        self.assertIn("data-feedback-open", menu)
        self.assertNotIn("position:fixed", re.sub(r"\s", "", h.split('<style id="helm-css">')[1].split("</style>")[0]).replace(".fb-fab{position:fixed", ""))

    def test_hazards_compact_warnings_never_collapsed(self):
        """t532u: every warning event stays visible (several zones share one row); only lower tiers collapse."""
        items = [{"event": "Small Craft Advisory", "tag": "In effect", "meta": "until Sat 9:00 AM ET"}]
        items += [{"event": "Gale Warning", "tag": "In effect", "meta": "until %d PM" % i, "area": "Zone %d" % i} for i in range(4)]
        items += [{"event": "Coastal Flood Warning", "tag": "In effect", "meta": "until 3:00 PM ET"}]
        h = self.sh.hazards_html({"state": "active", "items": items}, None)
        low = re.search(r'<details class="haz-more">.*?</details>', h, re.S).group(0)
        visible = h.replace(low, "")
        for ev in ("Gale Warning", "Coastal Flood Warning"):
            self.assertIn(ev, visible)
            self.assertNotIn(ev, low)
        self.assertIn("4 areas", visible)
        for i in range(4):
            self.assertIn("Zone %d" % i, h)               # zone detail kept, one tap away
        self.assertIn("+1", low)
        self.assertIn("Small Craft Advisory", low.split("</summary>")[0])   # named in the summary, not hidden
        self.assertLess(h.index("Coastal Flood Warning"), h.index("Small Craft Advisory"))
        # advisories alone are the top tier: shown in full, nothing collapsed
        only = self.sh.hazards_html({"state": "active", "items": items[:1]}, None)
        self.assertNotIn("haz-more", only)
        self.assertIn("Small Craft Advisory", only)

    def test_all_sections_menu_reaches_every_destination(self):
        h = self.salt()
        menu = re.search(r'<details class="allnav">.*?</details>', h, re.S).group(0)
        for href in ("/wind", "/radar", "/reports", "#regs", "/catch-wall", "/coastal-life", "/photos", "#tools", "#rp", "/brief?region="):
            self.assertIn('href="%s' % href, menu)
        self.assertIn('id="tools"', h)
        self.assertIn('id="rp"', h)
        self.assertIn("All sections", menu)

    def test_reports_dated_and_older_marked(self):
        h = self.sh.reports_html("crystal-coast", False, NOW)
        if "reps" in h:
            self.assertIn("Report dated", h)
            self.assertRegex(h, r"\d+ days? old|today")
        when, age = self.sh.report_age("2026-11-15", NOW)
        self.assertEqual(age, 12)
        r = self.sh.report_rows({"reports": [{"source_name": "Pier", "source_url": "https://example.org/r", "as_of": "2026-11-15"},
                                             {"source_name": "Shop", "source_url": "https://example.org/s", "as_of": "2026-11-26"},
                                             {"source_name": "", "source_url": "https://example.org/x", "as_of": "2026-11-26"},
                                             {"source_name": "No date", "source_url": "https://example.org/n"}]}, NOW)
        self.assertIn("OLDER REPORT", r.split("Shop")[0])
        self.assertIn("1 day old", r)
        self.assertNotIn("example.org/x", r)               # unattributed reports are never shown
        self.assertIn("DATE NOT STATED", r)
        for bad in ("current", "Current", "latest conditions", "right now"):
            self.assertNotIn(bad, r)
        self.assertNotIn("Fisherman", h)
        fl = self.sh.reports_html("falls-lake", True, NOW)
        self.assertNotIn("Jordan", fl)
        self.assertIn("Falls Lake", fl)

    def test_lake_gauge_marks_current_level(self):
        g = self.sh.GAUGES["falls-lake"]
        self.assertIn('class="g-now"', self.sh.gauge_svg("245.76", g))
        self.assertIn('class="g-now"', self.sh.gauge_svg("1,245.76".replace("1,", ""), g))
        self.assertNotIn('class="g-now"', self.sh.gauge_svg(None, g))       # missing reading: no marker, never a guess
        self.assertNotIn('class="g-now"', self.sh.gauge_svg("—", g))

    def test_today_photo_has_alt_and_credit(self):
        h = self.salt()
        today = re.search(r'<figure class="today".*?</figure>', h, re.S)
        self.assertIsNotNone(today)
        self.assertRegex(today.group(0), r'alt="[^"]+"')
        self.assertIn('loading="lazy"', today.group(0))
        for img in re.findall(r"<img [^>]*>", h):
            self.assertIn("alt=", img)

    def test_reports_and_regulations_prominent(self):
        h = self.salt()
        self.assertIn('id="regs"', h)
        self.assertIn("NC Division of Marine Fisheries", h)
        self.assertLess(h.index("Fishing Reports</b>"), h.index("The Coast</h2>"))

    def test_unavailable_never_shown_as_safe(self):
        h = self.salt(alerts={"status": "unavailable", "items": []}, seas_status="unavailable", tide_ok=False)
        self.assertNotIn("No NWS alerts right now", h)
        self.assertIn("Alerts unavailable", h)
        seas = re.search(r'<div class="cell seas".*?</div>\s*<div class="cell water"', h, re.S).group(0)
        self.assertIn("UNAVAILABLE", seas)
        self.assertNotIn("11.8", seas)
        self.assertIn("Tide predictions are unavailable", h)

    def test_no_payload_is_unavailable(self):
        with mock.patch.object(self.sh, "_salt", lambda rid: None):
            h = self.sh.build("crystal-coast", now=NOW)
        self.assertIn("Alerts unavailable", h)
        self.assertNotIn("No NWS alerts right now", h)

    def test_stale_badge(self):
        h = self.salt(wind_status="stale")
        self.assertIn('class="k stale">STALE', h)

    def test_freshwater_lake_has_no_tide_and_forecast_wind(self):
        with mock.patch.object(self.sh, "valid_region", lambda r: r):
            h = self.sh.build("falls-lake", now=NOW, fresh_payload=lake_payload(), grid=GRID, fetch=False)
        self.assertIn("No tide on a lake", h)
        self.assertNotIn("TIDE &amp; LIGHT", h)
        self.assertNotIn('class="tline"', h)
        self.assertIn("SUN &amp; MOON", h)
        dial = re.search(r'<div class="dial-wrap".*?</div>\s*<div class="side">', h, re.S).group(0)
        self.assertIn(">FORECAST<", dial)
        self.assertNotIn("OBSERVED", dial)
        self.assertIn("GFS", dial)
        self.assertIn("valid Fri 1:00 PM ET", dial)
        self.assertIn("run Fri 7:00 AM ET", dial)
        self.assertIn("245.71", h)
        self.assertIn("NGVD29", h)
        self.assertIn("GUIDE 251.5", h)
        self.assertIn("236.5", h)
        self.assertIn("264.8", h)

    def test_lake_level_missing_shows_unavailable(self):
        with mock.patch.object(self.sh, "valid_region", lambda r: r):
            h = self.sh.build("falls-lake", now=NOW, fresh_payload=lake_payload(elev=None), grid={"ok": False}, fetch=False)
        lake = re.search(r'<div class="cell lake".*?</div>\s*<div class="cell water"', h, re.S).group(0)
        self.assertIn("UNAVAILABLE", lake)
        self.assertNotIn("g-fill", lake)
        self.assertIn("Model wind is unavailable", h)

    def test_jordan_gauge_is_not_falls(self):
        self.assertEqual(self.sh.GAUGES["jordan-lake"]["guide"], 216.0)
        self.assertEqual(self.sh.GAUGES["falls-lake"]["guide"], 251.5)


class Routes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import server
        cls.server = server
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.base = "http://127.0.0.1:%d" % cls.httpd.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def _get(self, path, cookie=None):
        req = urllib.request.Request(self.base + path, headers={"Cookie": cookie} if cookie else {})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return r.status, r.headers, r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            return e.code, e.headers, e.read().decode("utf-8", "replace")

    def test_gated_404_without_or_with_bad_cookie(self):
        with mock.patch.dict(os.environ, {"PREVIEW_KEY": KEY}):
            self.assertEqual(self._get("/preview/helm")[0], 404)
            self.assertEqual(self._get("/preview/helm?region=falls-lake")[0], 404)
            self.assertEqual(self._get("/preview/helm", "cb_preview=nope")[0], 404)
        with mock.patch.dict(os.environ, {"PREVIEW_KEY": ""}):
            self.assertEqual(self._get("/preview/helm")[0], 404)

    def test_with_cookie_noindex_nostore(self):
        import signature_helm
        ck = "%s=%s" % (self.server.PREVIEW_COOKIE, self.server._preview_cookie_value(KEY))
        with mock.patch.dict(os.environ, {"PREVIEW_KEY": KEY}), \
                mock.patch.object(signature_helm, "build", lambda rid, **kw: "<!DOCTYPE html><html><head><meta name=\"robots\" content=\"noindex, nofollow\"></head><body><header class=\"bridge\"><div class=\"cbm-tools\"></div></header></body></html>"):
            st, h, body = self._get("/preview/helm?region=crystal-coast", ck)
        self.assertEqual(st, 200)
        self.assertIn("noindex", h.get("X-Robots-Tag", ""))
        self.assertIn("no-store", h.get("Cache-Control", ""))
        self.assertEqual(h.get("Vary"), "Cookie")
        self.assertIn('content="noindex, nofollow"', body)

    def test_not_in_sitemap_or_public_pages(self):
        st, _, sm = self._get("/sitemap.xml")
        self.assertNotIn("/preview/helm", sm)
        self.assertNotIn("/preview/helm", self._get("/robots.txt")[2])
        for path in ("/styles.css", "/app.js"):
            self.assertNotIn("preview/helm", self._get(path)[2])
        self.assertEqual(self._get("/preview/helm/helm.css")[0], 404)
        self.assertEqual(self._get("/signature_helm.py")[0], 404)


class Frozen(unittest.TestCase):
    def test_frozen_and_public_files_unchanged_from_baseline(self):
        try:
            subprocess.run(["git", "cat-file", "-e", BASELINE], cwd=ROOT, check=True, capture_output=True)
        except Exception:
            self.skipTest("baseline commit not available")
        out = subprocess.run(["git", "diff", "--name-only", BASELINE, "HEAD", "--", *FROZEN], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(out.stdout.strip(), "")


if __name__ == "__main__":
    unittest.main()
