"""Private preview Morning Briefs for Jordan Lake and the Neuse River.

They are behind the cb_preview cookie at /preview/brief/<id>, never on /brief, never in
brief.enabled_regions(), and never stored or archived. Public /brief?region=jordan-lake
and /brief?region=neuse-river stay 404.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import sys
import threading
import unittest
from datetime import datetime, timezone
from http.client import HTTPConnection
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import brief  # noqa: E402
import brief_preview  # noqa: E402
import freshwater  # noqa: E402

FRESH = ["jordan-lake", "neuse-river"]
KEY = "preview-test-key-24-chars-ok"
NOW = datetime(2026, 11, 15, 15, 0, tzinfo=timezone.utc)
T = "2026-11-15T14:20:00+00:00"


def _obs(value, stale=False, time=T):
    return {"value": value, "time": time, "ageH": 0.7, "stale": stale}


def _jordan_payload():
    return {
        "ok": True,
        "region": {
            "id": "jordan-lake",
            "name": "Jordan Lake",
            "area": "Cape Fear basin · Chatham & Wake counties",
            "anchor": freshwater.regions()["jordan-lake"]["anchor"],
            "waterType": "freshwater",
            "instrumentSet": "freshwater-lake",
        },
        "lake": {
            "kind": "observed", "usgs": "02098197", "siteName": "B. EVERETT JORDAN LAKE AT DAM NR MONCURE, NC",
            "url": "https://waterdata.usgs.gov/monitoring-location/02098197/",
            "elevation": _obs(212.23), "datum": "NGVD29", "navd88": _obs(211.46),
            "guideCurveFt": 216.0, "guideCurveDatum": "NGVD29 (USACE ft-msl)",
            "vsGuideFt": -3.77, "change24hFt": -0.04, "datumOffsetFt": 0.77,
        },
        "waterTemp": {"kind": "observed", "status": "unavailable", "c": None, "f": None, "time": None, "stale": None,
                      "note": "No USGS water-temperature sensor at Jordan Lake dam (02098197)."},
        "rain": {"kind": "observed", "usgs": "02098197", "status": "ok", "last24In": 0.00, "time": T, "stale": False,
                 "qpf": {"status": "ok", "kind": "forecast", "next24In": 0.12}},
        "release": {"usgs": "02098206", "label": "Haw River near Moncure (release plus local runoff)",
                    "kind": "observed", "flowCfs": _obs(245.0), "stageFt": _obs(2.02),
                    "note": "Dam release plus local runoff, not the official gate outflow. About 1.6 miles below the dam, above the Deep River confluence.",
                    "band": {"key": "normal", "label": "Normal"}},
        "inflows": [{"usgs": "02096960", "label": "Haw River near Bynum (inflow above the lake)",
                     "kind": "observed", "flowCfs": _obs(77.4), "stageFt": _obs(2.62),
                     "band": {"key": "below", "label": "Below normal"}}],
        "river": [],
        "forecast": {"status": "ok", "periods": [{"name": "This Afternoon", "tempF": 68, "short": "Sunny",
                                                 "windDir": "SW", "windMph": "5 mph"}]},
        "alerts": {"status": "ok", "items": []},
    }


def _neuse_payload(forecast=True):
    clay_nwps = {"lid": "CLYN7", "status": "ok", "floodStages": {"action": 8, "minor": 9, "moderate": 13, "major": 16}}
    if forecast:
        clay_nwps["forecast"] = {"issued": "2026-11-15T12:00:00+00:00", "crestStage": 1.4,
                                 "crestTime": "2026-11-16T00:00:00+00:00", "category": "no_flooding"}
    return {
        "ok": True,
        "region": {
            "id": "neuse-river",
            "name": "Neuse River (Falls Dam to Goldsboro)",
            "area": "Wake, Johnston & Wayne counties",
            "anchor": freshwater.regions()["neuse-river"]["anchor"],
            "waterType": "freshwater",
            "instrumentSet": "freshwater-river",
        },
        "lake": None,
        "waterTemp": {"kind": "observed", "status": "unavailable", "c": None, "f": None, "time": None, "stale": None,
                      "note": "No active USGS water-temperature sensor on the Neuse main stem (checked 13 Nov 2026)."},
        "rain": None,
        "release": None,
        "inflows": [],
        "river": [
            {"usgs": "02087183", "label": "Neuse River below Falls Dam", "kind": "observed", "regulated": True,
             "flowCfs": _obs(60.0), "stageFt": _obs(0.94),
             "nwps": {"lid": "NEUN7", "status": "ok", "floodStages": {"action": 5, "minor": 6, "moderate": 7, "major": 8}}},
            {"usgs": "02087500", "label": "Neuse River near Clayton", "kind": "observed", "regulated": True,
             "flowCfs": _obs(217.0), "stageFt": _obs(1.22), "nwps": clay_nwps,
             "band": {"key": "normal", "label": "Normal"}},
            {"usgs": "02087570", "label": "Neuse River at Smithfield", "kind": "observed", "regulated": True,
             "stageOnly": True, "flowCfs": None, "stageFt": _obs(4.45),
             "flowNote": "USGS stopped publishing discharge here; stage only.",
             "floodStages": {"action": 14, "minor": 15, "moderate": 18, "major": 20},
             "nwps": {"lid": "SMFN7", "status": "ok", "floodStages": {"action": 14, "minor": 15, "moderate": 18, "major": 20}}},
            {"usgs": "02089000", "label": "Neuse River near Goldsboro", "kind": "observed", "regulated": True,
             "flowCfs": _obs(319.0), "stageFt": _obs(2.69),
             "nwps": {"lid": "GLDN7", "status": "ok", "floodStages": {"action": 17, "minor": 18, "moderate": 20, "major": 24}}},
        ],
        "forecast": {"status": "ok", "periods": [{"name": "This Afternoon", "tempF": 64, "short": "Partly cloudy",
                                                 "windDir": "SW", "windMph": "6 mph"}]},
        "alerts": {"status": "ok", "items": []},
    }


def _assemble(rid, now=None):
    if rid == "jordan-lake":
        return 200, _jordan_payload()
    if rid == "neuse-river":
        return 200, _neuse_payload()
    return 404, {"ok": False, "error": "Unknown freshwater region."}


class Unchanged(unittest.TestCase):
    def test_enabled_regions_still_only_falls_for_freshwater(self):
        self.assertEqual(brief.enabled_regions(False), ["crystal-coast", "hatteras"])
        self.assertEqual(brief.enabled_regions(True), ["crystal-coast", "hatteras", "falls-lake"])
        for rid in FRESH:
            self.assertNotIn(rid, brief.enabled_regions(True))
            self.assertNotIn(rid, brief.enabled_regions(False))

    def test_public_get_stays_404(self):
        for rid in FRESH:
            self.assertEqual(brief.get(rid, include_fresh=True)[0], 404, rid)
            self.assertEqual(brief.get(rid, include_fresh=False)[0], 404, rid)

    def test_available(self):
        for rid in FRESH:
            self.assertTrue(brief_preview.available(rid), rid)
        self.assertFalse(brief_preview.available("falls-lake"))
        self.assertFalse(brief_preview.available("bogus"))


class Compose(unittest.TestCase):
    def test_never_stores_or_archives(self):
        with patch.object(freshwater, "assemble", side_effect=_assemble), \
             patch.object(brief, "_save") as save, patch.object(brief, "build") as build, \
             patch.object(brief, "compose") as pub_compose:
            before = dict(brief._mem)
            jb = brief_preview.compose("jordan-lake", NOW)
            nb = brief_preview.compose("neuse-river", NOW)
            save.assert_not_called()
            build.assert_not_called()
            pub_compose.assert_not_called()
            self.assertEqual(brief._mem, before)
        self.assertTrue(jb["preview"] and nb["preview"])
        self.assertEqual(jb["reason"], "preview")
        self.assertEqual(nb["waterType"], "freshwater")

    def test_jordan_wording_and_unavailable_temp(self):
        with patch.object(freshwater, "assemble", side_effect=_assemble):
            b = brief_preview.compose("jordan-lake", NOW)
        d = dict(b["items"])
        self.assertIn("212.23 ft (NGVD29)", d["Lake level"])
        self.assertIn("3.77 ft below the 216.0 ft guide curve", d["Lake level"])
        self.assertIn("release plus local runoff", d["Release plus runoff"].lower())
        self.assertIn("not the official gate outflow", d["Release plus runoff"])
        self.assertIn("02098206", d["Release plus runoff"])
        self.assertIn("Haw River near Bynum", d["Inflow"])
        self.assertIn("02096960", d["Inflow"])
        self.assertNotIn("Water temp", d)
        self.assertNotIn("water temp", b["missing"])
        self.assertIn(("Water temp", "No USGS water-temperature sensor at Jordan Lake dam (02098197)."), b["unavailable"])
        blob = " ".join(v for _, v in b["items"]) + " " + " ".join(b["take"])
        self.assertNotIn("Falls Dam", blob)
        self.assertNotIn("Falls Lake", blob)
        self.assertNotIn("at the dam sensor", blob)
        self.assertTrue(any("below its guide curve" in t for t in b["take"]))
        self.assertTrue(any("3.8 ft below" in t for t in b["take"]))

    def test_neuse_stage_not_depth_smithfield_no_flow_no_temp(self):
        with patch.object(freshwater, "assemble", side_effect=_assemble):
            b = brief_preview.compose("neuse-river", NOW)
        d = dict(b["items"])
        self.assertNotIn("Lake level", d)
        self.assertNotIn("lake level", b["missing"])
        self.assertIn("0.94 ft stage", d["Neuse River below Falls Dam"])
        self.assertIn("60 cfs (regulated)", d["Neuse River below Falls Dam"])
        self.assertIn("1.22 ft stage", d["Neuse River near Clayton"])
        self.assertIn("NWS forecast (NWPS CLYN7)", d["Neuse River near Clayton"])
        self.assertIn("crest 1.4 ft", d["Neuse River near Clayton"])
        self.assertIn("4.45 ft stage", d["Neuse River at Smithfield"])
        self.assertIn("stage only", d["Neuse River at Smithfield"].lower())
        self.assertNotIn("cfs", d["Neuse River at Smithfield"])
        self.assertNotIn("298", d["Neuse River at Smithfield"])
        self.assertIn("2.69 ft stage", d["Neuse River near Goldsboro"])
        self.assertNotIn("Water temp", d)
        self.assertIn("No active USGS water-temperature sensor on the Neuse main stem", dict(b["unavailable"])["Water temp"])
        blob = " ".join(v for _, v in b["items"]).lower()
        self.assertNotIn("depth", blob)
        self.assertNotRegex(" ".join(v for _, v in b["items"]), r"\d+°F at the dam")

    def test_page_is_private_and_labeled(self):
        with patch.object(freshwater, "assemble", side_effect=_assemble):
            html = brief_preview.page(brief_preview.compose("jordan-lake", NOW))
            nhtml = brief_preview.page(brief_preview.compose("neuse-river", NOW))
        for doc, rid in ((html, "jordan-lake"), (nhtml, "neuse-river")):
            self.assertIn("Private preview · not published", doc)
            self.assertIn('content="noindex, nofollow"', doc)
            self.assertIn("Unavailable in this area", doc)
            self.assertIn('href="/preview/brief/jordan-lake"', doc)
            self.assertIn('href="/preview/brief/neuse-river"', doc)
            self.assertNotIn('href="/brief?region=%s"' % rid, doc)
            self.assertIn("/preview/brief/%s" % rid, doc)
        self.assertIn("not the official gate outflow", html)
        self.assertIn("stage only", nhtml.lower())
        self.assertNotIn("depth", nhtml.lower())


class Gate(unittest.TestCase):
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
        cls.httpd.shutdown(); cls.httpd.server_close()

    def setUp(self):
        self._saved = os.environ.get("PREVIEW_KEY")
        os.environ["PREVIEW_KEY"] = KEY
        brief_preview._cache.clear()
        p = patch.object(freshwater, "assemble", side_effect=_assemble)
        p.start()
        self.addCleanup(p.stop)

    def tearDown(self):
        if self._saved is None:
            os.environ.pop("PREVIEW_KEY", None)
        else:
            os.environ["PREVIEW_KEY"] = self._saved
        brief_preview._cache.clear()

    def _get(self, path, cookie=None):
        c = HTTPConnection("127.0.0.1", self.port, timeout=10)
        c.request("GET", path, headers={"Cookie": cookie} if cookie else {})
        r = c.getresponse(); body = r.read(); hdrs = {k.lower(): v for k, v in r.getheaders()}; c.close()
        return r.status, body.decode("utf-8", "replace"), hdrs

    def test_404_without_cookie(self):
        for rid in FRESH:
            self.assertEqual(self._get("/preview/brief/" + rid)[0], 404, rid)
            self.assertEqual(self._get("/preview/brief/" + rid, "cb_preview=wrong")[0], 404, rid)

    def test_404_when_no_key_configured(self):
        os.environ.pop("PREVIEW_KEY", None)
        self.assertEqual(self._get("/preview/brief/jordan-lake", self.cookie)[0], 404)

    def test_200_with_cookie(self):
        for rid in FRESH:
            st, body, h = self._get("/preview/brief/" + rid, self.cookie)
            self.assertEqual(st, 200, rid)
            self.assertIn("Private preview", body)
            self.assertEqual(h.get("x-robots-tag"), "noindex, nofollow")
            self.assertIn("no-store", h.get("cache-control", ""))

    def test_falls_and_unknown_still_404_even_with_cookie(self):
        for rid in ("falls-lake", "bogus", ""):
            self.assertEqual(self._get("/preview/brief/" + rid, self.cookie)[0], 404, rid)

    def test_public_brief_routes_stay_404(self):
        for rid in FRESH:
            for ck in (None, self.cookie):
                self.assertEqual(self._get("/brief?region=" + rid, ck)[0], 404, rid)
                self.assertEqual(self._get("/api/brief?region=" + rid, ck)[0], 404, rid)
                self.assertEqual(self._get("/%s/brief" % rid, ck)[0], 404, rid)

    def test_hub_lists_fresh_preview_briefs(self):
        st, body, _ = self._get("/preview", self.cookie)
        self.assertEqual(st, 200)
        for rid in FRESH:
            self.assertIn('href="/preview/brief/%s"' % rid, body)

    def test_sitemap_has_no_preview_or_public_fresh_briefs(self):
        st, body, _ = self._get("/sitemap.xml")
        self.assertNotIn("/preview/brief", body)
        self.assertNotIn("/brief?region=jordan-lake", body)
        self.assertNotIn("/brief?region=neuse-river", body)


if __name__ == "__main__":
    unittest.main()
