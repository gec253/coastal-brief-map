"""Private homepage sprint concepts: /preview/home-heritage, -editorial, -hybrid."""
from __future__ import annotations

import os
import re
import sys
import threading
import time
import unittest
from http.client import HTTPConnection
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import sprint_home  # noqa: E402

ROUTES = ("/preview/home-heritage", "/preview/home-editorial", "/preview/home-hybrid")
NOW = time.time()


def iso(mins_ago):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(NOW - mins_ago * 60))


def st(sid, name, dist=2):
    return {"id": sid, "name": name, "distanceMi": dist, "bearingFromAnchor": "N"}


def ok(values, sid="X1", name="Test station", age=10):
    return {"kind": "observed", "status": "ok", "time": iso(age), "station": st(sid, name), "values": values}


OFF = {"kind": "observed", "status": "unavailable", "tried": [], "note": "No sensor here."}


def tides(curve=True, observed=True):
    t0 = NOW * 1000
    out = {
        "status": "ok", "kind": "predicted", "datum": "MLLW", "station": st("8658163", "Wrightsville Beach"),
        "events": [{"t": t0 + 3600e3, "v": 3.4, "type": "H"}, {"t": t0 + 7 * 3600e3, "v": 0.6, "type": "L"}],
    }
    if curve:
        out["curve"] = [[t0 + (i - 30) * 360e3, 1 + (i % 40) / 20.0] for i in range(200)]
    if observed:
        out["observed"] = {"status": "ok", "time": iso(5), "latest": {"v": 2.9, "predicted": 2.3, "diff": 0.6}}
    return out


def salt(region_id, **kw):
    R = {
        "wind": ok({"speedKt": 12.4, "gustKt": 17.0, "dirDeg": 40.0, "dirCompass": "NE"}, "8658163", "Wrightsville Beach"),
        "harborWind": ok({"speedKt": 9.0, "gustKt": None, "dirDeg": 30.0, "dirCompass": "NNE"}, "8658163", "Wrightsville Beach"),
        "seas": ok({"heightFt": 3.1, "dominantPeriodS": 8.0, "meanDirCompass": "E"}, "41110", "Masonboro Inlet"),
        "swell": ok({"heightFt": 1.2, "periodS": 11.0, "dirCompass": "ESE"}, "41110", "Masonboro Inlet"),
        "waterTemp": ok({"f": 63.4}, "8658163", "Wrightsville Beach"),
        "waterTempOffshore": ok({"f": 68.2}, "41110", "Masonboro Inlet"),
        "airTemp": ok({"f": 55.1}),
        "pressure": ok({"inHg": 30.21, "change3hInHg": -0.04, "trend": "falling"}),
    }
    R.update(kw.pop("readings", {}))
    p = {
        "ok": True, "generatedAt": iso(1), "region": {"id": region_id, "name": region_id.title()},
        "readings": R, "tides": kw.pop("tides", tides()),
        "marine": {"status": "ok", "office": "NWS MHX", "zone": "AMZ158", "updated": iso(30),
                   "periods": [{"name": "Tonight", "text": "N winds 10 to 15 kt. Seas 2 to 3 ft."}]},
        "alerts": {"status": "ok", "items": [], "zones": ["AMZ158"]},
    }
    p.update(kw)
    return p


def fresh_jordan():
    t = "2026-11-15T13:45:00-05:00"
    return {
        "ok": True, "generatedAt": iso(1), "region": {"id": "jordan-lake", "name": "Jordan Lake"},
        "lake": {"usgs": "02098197", "datum": "NGVD29", "elevation": {"value": 212.12, "time": t, "stale": False},
                 "guideCurveFt": 216.0, "vsGuideFt": -3.88, "change24hFt": -0.05, "change7dFt": -0.3},
        "waterTemp": {"status": "unavailable", "f": None, "note": "No USGS water-temperature sensor at Jordan Lake dam (02098197)."},
        "rain": {"status": "ok", "last24In": 0.0, "time": t, "stale": False, "qpf": {"status": "ok", "next24In": 0.1}},
        "release": {"usgs": "02098206", "label": "Haw River near Moncure", "tileTitle": "Release plus local runoff",
                    "flowCfs": {"value": 206.0, "time": t, "stale": False}, "stageFt": {"value": 2.05, "time": t, "stale": False},
                    "band": {"label": "Below normal"},
                    "nwps": {"forecast": {"crestFlowCfs": 9999, "crestStage": 3.0}}},
        "inflows": [{"usgs": "02096960", "label": "Haw River near Bynum", "flowCfs": {"value": 75.3, "time": t, "stale": False}}],
        "river": [],
        "forecast": {"status": "ok", "office": "NWS Raleigh (RAH)", "updated": iso(40),
                     "periods": [{"name": "Tonight", "detail": "Clear, with a low around 37."}]},
        "alerts": {"status": "ok", "items": []},
    }


PHOTOS = [
    {"id": sprint_home.LEAD_PHOTO_ID, "category": "fishing", "species": "Red Drum", "region": "New Bern · Neuse River",
     "name": "", "w": 3024, "h": 4032, "src": {"400": "/m/a/400.webp", "800": "/m/a/800.webp"}},
    {"id": sprint_home.WIDE_PHOTO_ID, "category": "fishing", "species": "Striped Bass", "location": "Roanoke River",
     "name": "", "w": 4032, "h": 3024, "src": {"800": "/m/b/800.webp"}},
    {"id": sprint_home.LIFE_PHOTO_ID, "category": "life", "location": "Rx Chicken& Oysters",
     "region": "Wilmington · Wrightsville Beach", "name": "", "w": 1284, "h": 1030, "src": {"800": "/m/c/800.webp"}},
]


def render(variant, payload, photos=PHOTOS, fresh=False):
    with mock.patch.object(sprint_home, "approved_photos", return_value=photos), \
         mock.patch.object(sprint_home, "region_links", return_value=[]), \
         mock.patch.object(sprint_home, "_freshwater_ids", return_value={"jordan-lake"} if fresh else set()):
        if fresh:
            import freshwater
            with mock.patch.object(freshwater, "assemble", return_value=(200, payload)):
                return sprint_home.page(variant, payload["region"]["id"]).decode("utf-8")
        with mock.patch.object(sprint_home.conditions, "assemble", return_value=(200, payload)):
            return sprint_home.page(variant, payload["region"]["id"]).decode("utf-8")


def tile(htmls, tid):
    m = re.search(r'<div class="t t-%s[^"]*".*?(?=<div class="t t-|</div></div>|<div class="fc|<details|$)' % re.escape(tid), htmls, re.S)
    return m.group(0) if m else ""


def nums(htmls):
    return re.findall(r'<span class="t-num[^"]*">([^<]*)</span>', htmls)


class Gate(unittest.TestCase):
    KEY = "sprint-test-key-24-chars-ok!"

    @classmethod
    def setUpClass(cls):
        import server
        cls.server = server
        cls.httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.port = cls.httpd.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def _get(self, path, key=None, cookie=False):
        saved = os.environ.get("PREVIEW_KEY")
        try:
            if key:
                os.environ["PREVIEW_KEY"] = key
            else:
                os.environ.pop("PREVIEW_KEY", None)
            h = {}
            if cookie:
                h["Cookie"] = "cb_preview=" + self.server._preview_cookie_value(self.KEY)
            with mock.patch.object(sprint_home, "page", return_value=b"<html>ok</html>"):
                c = HTTPConnection("127.0.0.1", self.port, timeout=10)
                c.request("GET", path, headers=h)
                r = c.getresponse()
                body = r.read()
                return r.status, dict(r.getheaders()), body
        finally:
            if saved is None:
                os.environ.pop("PREVIEW_KEY", None)
            else:
                os.environ["PREVIEW_KEY"] = saved

    def test_routes_are_cookie_gated(self):
        for p in ROUTES:
            self.assertEqual(self._get(p)[0], 404, p)
            self.assertEqual(self._get(p, key=self.KEY)[0], 404, p)
            self.assertEqual(self._get(p, key=self.KEY, cookie=True)[0], 200, p)
            s, h, _ = self._get(p + "?region=topsail", key=self.KEY, cookie=True)
            self.assertEqual(s, 200)
            self.assertIn("noindex", h.get("X-Robots-Tag", "") + h.get("x-robots-tag", ""))


class Render(unittest.TestCase):
    def test_conditions_before_any_photo(self):
        for v in sprint_home.CONCEPTS:
            h = render(v, salt("wilmington"))
            body = h[h.index("<body"):]
            cg = body.index("data-conditions")
            self.assertIn("<img", body)
            self.assertLess(cg, body.index("<img"), v)
            self.assertLess(cg, body.index('class="ph '), v)

    def test_values_come_from_payload(self):
        h = render("heritage", salt("wilmington"))
        self.assertEqual(nums(tile(h, "wind")), ["12"])
        self.assertEqual(nums(tile(h, "seas")), ["3.1"])
        self.assertEqual(nums(tile(h, "swell")), ["1.2"])
        self.assertEqual(nums(tile(h, "water")), ["63"])
        self.assertIn("Combined wave height", tile(h, "seas"))
        self.assertIn("Split from the wave spectrum", tile(h, "swell"))
        self.assertIn("Predicted", h)
        self.assertIn("Observed 2.9 ft", h)

    def test_no_placeholder_numbers_when_everything_is_down(self):
        dead = salt("wilmington", readings={k: OFF for k in ("wind", "harborWind", "seas", "swell", "waterTemp",
                                                             "waterTempOffshore", "airTemp", "pressure")},
                     tides={"status": "unavailable"}, marine={"status": "error"}, alerts={"status": "error"})
        for v in sprint_home.CONCEPTS:
            h = render(v, dead)
            n = nums(h)
            self.assertTrue(n)
            self.assertTrue(all(x == "—" for x in n), (v, n))
            self.assertIn("Not reporting", h)
            self.assertIn(sprint_home.TIDE_OFF, h)
            self.assertIn(sprint_home.MARINE_OFF, h)
            self.assertIn("Alerts unavailable", h)
            self.assertNotIn("No NWS alerts right now", h)
            self.assertNotIn('<svg class="t-spark"', h)

    def test_payload_failure_says_so(self):
        with mock.patch.object(sprint_home.conditions, "assemble", side_effect=RuntimeError("down")), \
             mock.patch.object(sprint_home, "approved_photos", return_value=[]), \
             mock.patch.object(sprint_home, "region_links", return_value=[]):
            h = sprint_home.page("hybrid").decode()
        self.assertIn(sprint_home.PAYLOAD_OFF, h)
        self.assertEqual(nums(h), [])

    def test_every_image_is_credited(self):
        for v in sprint_home.CONCEPTS:
            h = render(v, salt("wilmington"))
            figs = re.findall(r"<figure class=\"ph [^\"]*\">.*?</figure>", h, re.S)
            with_img = [f for f in figs if "<img" in f]
            self.assertGreaterEqual(len(with_img), 2, v)
            self.assertEqual(h.count("<img"), len(with_img), v)
            for f in with_img:
                m = re.search(r'<span class="ph-credit">([^<]+)</span>', f)
                self.assertTrue(m, f[:200])
                self.assertRegex(m.group(1), r"^(Catch Wall|Coastal Life) community photo · ")
                self.assertIn("Photographer not recorded", m.group(1))  # nothing invented
                self.assertRegex(f, r'width="\d+" height="\d+"')
            self.assertIn(sprint_home.AWAITING, h)

    def test_no_photos_gives_honest_slots(self):
        h = render("editorial", salt("wilmington"), photos=[])
        self.assertNotIn("<img", h)
        self.assertGreaterEqual(h.count(sprint_home.AWAITING), 3)

    def test_region_degradation(self):
        cases = {
            # Wilmington: harbor wind is the same station as wind, so it is not repeated.
            "wilmington": salt("wilmington"),
            # Nags Head: no inshore water temp; offshore buoy is labelled offshore.
            "nags-head": salt("nags-head", readings={"waterTemp": OFF}),
            # Topsail: no inshore water, no air, no harbor wind, highs and lows only.
            "topsail": salt("topsail", readings={"waterTemp": OFF, "airTemp": OFF, "harborWind": None},
                            tides=tides(curve=False, observed=False)),
            # Gust-only wind degrades without inventing a sustained speed.
            "gust-only": salt("emerald-isle", readings={"wind": ok({"speedKt": None, "gustKt": 21.0, "dirCompass": "N"})}),
        }
        for v in sprint_home.CONCEPTS:
            for name, p in cases.items():
                with self.subTest(v=v, region=name):
                    h = render(v, p)
                    self.assertIn("data-conditions", h)
                    if name == "wilmington":
                        self.assertNotIn("t-harbor", h)
                    if name == "nags-head":
                        self.assertIn("Offshore buoy", tile(h, "water"))
                        self.assertEqual(nums(tile(h, "water")), ["68"])
                    if name == "topsail":
                        self.assertNotIn("t t-air", h)
                        self.assertNotIn("t-harbor", h)
                        self.assertNotIn('<svg class="t-spark"', h)
                        self.assertNotIn("Observed 2.9", h)
                        self.assertIn("Offshore buoy", h)
                    if name == "gust-only":
                        w = tile(h, "wind")
                        self.assertIn("gusting 21 kt (sustained speed not reported)", w)
                        self.assertEqual(nums(w), ["—"])

    def test_jordan_lake(self):
        for v in sprint_home.CONCEPTS:
            h = render(v, fresh_jordan(), fresh=True)
            self.assertIn("Lake level", h)
            self.assertIn("Not depth", h)
            self.assertIn("No USGS water-temperature sensor at Jordan Lake dam (02098197).", h)
            self.assertNotIn("9999", h)       # no forecast cfs
            self.assertNotIn("9,999", h)
            self.assertNotIn("Air", re.sub(r"<[^>]+>", " ", h).split("Conditions at a Glance")[1].split("Design system")[0])
            self.assertIn("/lake?region=jordan-lake", h)

    def test_intro_reuses_v5_and_rule_is_the_settle_target(self):
        import wave_intro
        h = render("hybrid", salt("wilmington"))
        self.assertIn('class="wave-settle"', h)
        self.assertIn(wave_intro._js()[:200], h)
        self.assertIn("prefers-reduced-motion", h)
        # The overlay must not hold the readings back: they are in the HTML, not fetched by script.
        self.assertNotIn("/api/conditions", h)
        self.assertIn('<span class="t-num">12</span>', h)


@unittest.skipUnless(os.environ.get("SPRINT_LIVE") == "1", "live network check; set SPRINT_LIVE=1")
class Live(unittest.TestCase):
    def test_live_regions_render(self):
        import server  # noqa: F401  (installs the same fetchers the homepage uses)
        for rid in ("wilmington", "nags-head", "topsail", "jordan-lake"):
            for v in sprint_home.CONCEPTS:
                h = sprint_home.page(v, rid).decode()
                self.assertIn("data-conditions", h)
                self.assertNotIn(sprint_home.PAYLOAD_OFF, h, (v, rid))


if __name__ == "__main__":
    unittest.main()
