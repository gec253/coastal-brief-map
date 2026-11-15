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
LIFE2 = {"id": sprint_home.LIFE2_PHOTO_ID, "category": "life", "location": "Rx Chicken & Oysters", "caption": "",
         "region": "Wilmington · Wrightsville Beach", "name": "", "w": 1095, "h": 1436, "src": {"800": "/m/e/800.webp"}}
FRESH = {"id": sprint_home.FRESH_PHOTO_ID, "category": "fishing", "location": "Weldon", "name": "",
         "w": 4032, "h": 3024, "src": {"800": "/m/f/800.webp"}}
ALL_PHOTOS = PHOTOS + [LIFE2, FRESH]


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
        ph = "/preview/sprint-home/photos/bodie-sunrise-800.avif"
        self.assertEqual(self._get(ph)[0], 404)
        self.assertEqual(self._get(ph, key=self.KEY)[0], 404)
        self.assertEqual(self._get(ph, key=self.KEY, cookie=True)[0], 200)


class Render(unittest.TestCase):
    def test_conditions_before_any_photo(self):
        for v in sprint_home.CONCEPTS:
            h = render(v, salt("wilmington"))
            body = h[h.index("<body"):]
            cg = body.index("data-conditions")
            self.assertIn("<img", body)
            self.assertLess(cg, body.index("<img"), v)
            if "<picture" in body:
                self.assertLess(cg, body.index("<picture"), v)

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
        credit_re = re.compile(r'<(?:span|p) class="(?:ph-credit|mz-credit|hz-c)">([^<]+)</(?:span|p)>')
        ok_credit = re.compile(r"^(Community photo · (Catch Wall|Coastal Life)|"
                               r"Photo: National Park Service, Cape Hatteras National Seashore \(public domain\))$")
        for v in sprint_home.CONCEPTS:
            h = render(v, salt("wilmington"))
            body = h[h.index("<main"):]
            imgs = [m.start() for m in re.finditer(r"<img ", body)]
            self.assertGreaterEqual(len(imgs), 2, v)
            for i in imgs:
                # each image's own container closes with a credit before the next image starts
                nxt = min([j for j in imgs if j > i] + [len(body)])
                m = credit_re.search(body, i, nxt)
                self.assertTrue(m, (v, body[i:i + 160]))
                self.assertRegex(m.group(1), ok_credit)
                self.assertRegex(body[i:body.index(">", i)], r'width="\d+" height="\d+"')
            if v == "hybrid":
                self.assertNotIn("Awaiting real material", h)
            else:
                self.assertIn("Awaiting real material", h)

    def test_no_photos_gives_honest_slots(self):
        h = render("editorial", salt("wilmington"), photos=[])
        self.assertNotIn("<img", h)
        self.assertGreaterEqual(h.count(sprint_home.AWAITING), 3)
        with mock.patch.object(sprint_home, "PHOTO_DIR", Path("/nonexistent")):
            h = render("hybrid", salt("wilmington"), photos=[])
        self.assertNotIn("<img", h)
        self.assertNotIn("Awaiting real material", h)   # hybrid hides empty slots entirely
        self.assertIn('class="mz-grid mz-loose mz-n0"', h)
        self.assertIn("Share yours on the Catch Wall", h)

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


def alerts(*events, status="ok", ends_in_min=120):
    return {"status": status, "zones": ["AMZ158"], "items": [
        {"event": e, "ends": iso(-ends_in_min)} for e in events]}


class Refinement(unittest.TestCase):
    def test_flag_mapping_exact_event_names(self):
        f = sprint_home.flag_for
        self.assertEqual(f(alerts("Small Craft Advisory")), "pennant")
        self.assertEqual(f(alerts("Gale Warning")), "pennant2")
        self.assertEqual(f(alerts("Storm Warning")), "square")
        self.assertEqual(f(alerts("Tropical Storm Warning")), "square")
        self.assertEqual(f(alerts("Hurricane Warning")), "square2")
        self.assertEqual(f(alerts("Hurricane Force Wind Warning")), "square2")
        self.assertEqual(f(alerts("Tropical Storm Warning", "Hurricane Force Wind Warning")), "square2")
        self.assertEqual(f(alerts("Small Craft Advisory", "Gale Warning")), "pennant2")  # highest wins
        for e in ("Tropical Storm Watch", "Winter Storm Warning", "Hurricane Force Wind Watch", "Hurricane Watch",
                  "tropical storm warning", "Tropical Storm Warning (test)", "Extreme Wind Warning", "High Wind Warning",
                  "Gale Watch", "Storm Watch", "Hazardous Seas Warning", "Special Marine Warning", "Rip Current Statement",
                  "Coastal Flood Advisory", "small craft advisory", "Brisk Wind Advisory"):
            self.assertIsNone(f(alerts(e)), e)
        self.assertIsNone(f(alerts("Gale Warning", ends_in_min=-30)))     # already ended
        self.assertIsNone(f(alerts("Gale Warning", status="unavailable")))  # not verified
        self.assertIsNone(f(None))

    def test_flag_renders_only_for_matching_alert(self):
        h = render("hybrid", salt("wilmington", alerts=alerts("Gale Warning")))
        self.assertIn('aria-label="Coastal warning display: two red pennants"', h)
        self.assertEqual(h.count('class="al-flag"'), 1)
        h = render("hybrid", salt("wilmington", alerts=alerts("Tropical Storm Warning")))
        self.assertIn('aria-label="Coastal warning display: a square red flag with a black center"', h)
        h = render("hybrid", salt("wilmington", alerts=alerts("Hurricane Force Wind Warning")))
        self.assertIn('aria-label="Coastal warning display: two square red flags with black centers"', h)
        for e in ("Tropical Storm Watch", "Rip Current Statement"):
            h = render("hybrid", salt("wilmington", alerts=alerts(e)))
            self.assertIn(e, h)
            self.assertNotIn('class="al-flag"', h)
        h = render("hybrid", salt("wilmington"))
        self.assertNotIn('class="al-flag"', h)

    def test_offshore_water_is_unmistakable(self):
        off = ok({"f": 68.2}, "41159", "Onslow Bay Outer")
        off["station"].update({"distanceMi": 36, "bearingFromAnchor": "ESE", "anchor": "Ocean City Fishing Pier"})
        h = render("hybrid", salt("topsail", readings={"waterTemp": OFF, "waterTempOffshore": off}))
        w = tile(h, "water")
        self.assertIn("is-offshore", w)
        self.assertIn("Offshore buoy", w)
        self.assertIn("Buoy 41159 · 36 mi ESE of Ocean City Fishing Pier", w)
        self.assertIn('class="t-buoy"', w)
        nodist = ok({"f": 68.2}, "41159", "Onslow Bay Outer")
        nodist["station"].pop("distanceMi")
        h = render("hybrid", salt("topsail", readings={"waterTemp": OFF, "waterTempOffshore": nodist}))
        self.assertIn("Buoy 41159 · distance offshore not recorded", tile(h, "water"))
        h = render("hybrid", salt("wilmington"))
        self.assertNotIn("is-offshore", tile(h, "water"))

    def test_hybrid_has_no_toggles_and_shows_forecast(self):
        h = render("hybrid", salt("wilmington"))
        cg = h[h.index("data-conditions"):h.index("</section>", h.index("data-conditions"))]
        self.assertNotIn("<details", cg)
        self.assertIn("N winds 10 to 15 kt", cg)
        self.assertLess(cg.index('class="fc"'), cg.index('class="cg-more"'))
        self.assertIn('<nav class="rr" aria-label="Choose your water">', h)
        groups = [("Saltwater", [("wilmington", "Wilmington", True)]), ("Freshwater", [("jordan-lake", "Jordan Lake", False)])]
        with mock.patch.object(sprint_home, "region_groups", return_value=groups):
            rr = sprint_home.region_rail("wilmington")
        self.assertIn(">Saltwater<", rr)
        self.assertIn(">Freshwater<", rr)
        self.assertIn('aria-current="page"', rr)

    def test_motto_once_and_water_attribute(self):
        h = render("hybrid", salt("wilmington"))
        body = h[h.index("<body"):]
        self.assertEqual(body.count("From the rivers to the sounds to the sea"), 1)
        self.assertIn('data-water="salt"', h)
        h = render("hybrid", fresh_jordan(), fresh=True)
        self.assertIn('data-water="fresh"', h)

    def test_bodie_is_the_saltwater_horizon(self):
        h = render("hybrid", salt("wilmington"))
        hz = h[h.index('<section class="hz"'):]
        self.assertIn("/preview/sprint-home/photos/bodie-sunrise-800.webp", hz[:2000])
        self.assertIn('width="1600" height="1200"', hz[:2000])
        self.assertIn("Photo: National Park Service, Cape Hatteras National Seashore (public domain)", hz[:2500])
        self.assertTrue((sprint_home.DIR / "CREDITS.md").is_file())

    def test_mosaic_full_set_has_no_placeholders_and_unique_captions(self):
        h = render("hybrid", salt("wilmington"), photos=ALL_PHOTOS)
        mz = h[h.index('<section class="mzs"'):]
        mz = mz[:mz.index("</section>")]
        self.assertIn('<div class="mz-grid">', mz)
        self.assertNotIn("mz-loose", mz)
        self.assertNotIn("Awaiting", mz)
        self.assertNotIn("mz-slot", mz)
        self.assertEqual(mz.count('<figure class="mz '), 5)
        caps = re.findall(r'<span class="mz-cap">([^<]+)</span>', mz)
        self.assertEqual(len(caps), len(set(caps)), caps)
        self.assertIn("At Rx Chicken &amp; Oysters", caps)
        self.assertEqual(mz.count("Share yours on the Catch Wall"), 1)
        # the override is presentation only: the record itself is untouched
        self.assertEqual(LIFE2["caption"], "")
        self.assertEqual(LIFE2["location"], "Rx Chicken & Oysters")

    def test_mosaic_partial_set_falls_back_to_loose_grid(self):
        h = render("hybrid", salt("wilmington"), photos=PHOTOS)
        self.assertIn("mz-loose", h)
        self.assertNotIn("Awaiting", h[h.index('<section class="mzs"'):])

    def test_photo_path_is_strict(self):
        self.assertIsNotNone(sprint_home.photo_path("/preview/sprint-home/photos/bodie-sunrise-800.avif"))
        for bad in ("../server.py", "bodie-sunrise-800.png", "BODIE-800.avif", "x/../../a-800.webp"):
            self.assertIsNone(sprint_home.photo_path("/preview/sprint-home/photos/" + bad), bad)


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
