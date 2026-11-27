"""Private /preview/helm-tools Marine & Water Tools variant (Ed t542u).

Preview-only: public routes must stay identical to production. Cookie-gated,
noindex, no-store. Does not loosen any existing guard.
"""
from __future__ import annotations

import os
import re
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

import test_signature_helm_preview as helm

ROOT = Path(__file__).resolve().parents[1]
KEY = helm.KEY
ROUTE = "/preview/helm-tools"
COVERED = ("crystal-coast", "emerald-isle", "falls-lake", "jordan-lake", "neuse-river")
UNCOVERED = ("hatteras", "wilmington", "nags-head", "topsail")
FRESH = ("falls-lake", "jordan-lake", "neuse-river")
NOTES = {
    "emerald-isle": "Emerald Isle ramps are in the Crystal Coast list.",
    "neuse-river": "The Neuse list includes tidal lower-river launches, not only Falls Dam to Goldsboro.",
    "hatteras": "Ramps are not yet listed for this area",
    "wilmington": "Ramps are not yet listed for this area",
    "nags-head": "Ramps are not yet listed for this area",
    "topsail": "Ramps are not yet listed for this area",
}
CREDITS = {
    "salt": "Photo: Ingrid Lemme (public domain)",
    "falls-lake": "Photo: Sergiy Galyonkin, CC BY-SA 2.0 (cropped from the original)",
    "jordan-lake": "Photo: Gerry Dincher, CC BY-SA 2.0",
    "neuse-river": "Photo: Fredlyfish4, CC BY-SA 4.0",
}


def _tools(html: str) -> str:
    m = re.search(r'<section class="mwt" id="tools".*?</section>', html, re.S)
    return m.group(0) if m else ""


class Build(unittest.TestCase):
    def setUp(self):
        import server  # noqa: F401
        import signature_helm
        self.sh = signature_helm
        self.p = mock.patch.object(__import__("sprint_home"), "_now_ms", lambda: helm.MS(helm.NOW))
        self.p.start()
        self.q = mock.patch.object(__import__("sprint_home"), "_raw_alert_records", lambda a: {})
        self.q.start()

    def tearDown(self):
        self.p.stop()
        self.q.stop()

    def salt(self, rid="crystal-coast", ramps=True, **kw):
        env = {"PUBLIC_RAMPS": "1" if ramps else "0"}
        with mock.patch.dict(os.environ, env, clear=False):
            return self.sh.build(rid, now=helm.NOW, salt_payload=helm.salt_payload(**kw),
                                 grid=helm.GRID, fetch=False, mwt=True)

    def fresh(self, rid="falls-lake", ramps=True):
        payload = helm.lake_payload()
        if rid != "falls-lake":
            payload = dict(payload)
            payload["region"] = dict(payload["region"])
            if rid == "jordan-lake":
                payload["region"].update(id="jordan-lake", name="Jordan Lake",
                                         anchor={"label": "Jordan Lake Dam", "lat": 35.6547, "lon": -79.0683})
            else:
                payload["region"].update(id="neuse-river", name="Neuse River (Falls Dam to Goldsboro)",
                                         anchor={"label": "Clayton", "lat": 35.6472, "lon": -78.4053})
                payload.pop("lake", None)
        env = {"PUBLIC_RAMPS": "1" if ramps else "0"}
        with mock.patch.dict(os.environ, env, clear=False):
            return self.sh.build(rid, now=helm.NOW, fresh_payload=payload, grid=helm.GRID, fetch=False, mwt=True)

    def test_public_build_is_not_the_tools_variant(self):
        h = self.sh.build("crystal-coast", now=helm.NOW, salt_payload=helm.salt_payload(), fetch=False)
        self.assertNotIn('class="mwt"', h)
        self.assertNotIn("mwt-ramp", h)
        self.assertNotIn("All NC ramps", h)
        self.assertIn('id="tools"', h)  # original compact line still on the non-preview build

    def test_section_sits_above_wind_radar_gates(self):
        h = self.salt()
        self.assertLess(h.index('id="tools"'), h.index('id="gates"'))
        self.assertIn('class="mwt"', h)

    def test_all_nc_ramps_is_sibling_for_covered_regions(self):
        for rid in ("crystal-coast", "emerald-isle"):
            sec = _tools(self.salt(rid))
            self.assertIn('class="mwt-all"', sec)
            self.assertIn('href="/ramps"', sec)
            self.assertRegex(sec, r'<div class="mwt-rwrap">.*</figure>\s*<a class="mwt-all" href="/ramps">All NC ramps</a>', re.S)
            self.assertIsNone(re.search(r'<a href="[^"]+"[^>]*>[^<]*class="mwt-all"', sec))
            # not nested inside the featured card's anchor
            card = re.search(r'<figure class="mwt-ramp.*?</figure>', sec, re.S).group(0)
            self.assertNotIn("mwt-all", card)

    def test_uncovered_regions_have_no_all_nc_sibling(self):
        for rid in UNCOVERED:
            sec = _tools(self.salt(rid))
            self.assertNotIn("mwt-all", sec)
            self.assertIn('href="/ramps"', sec)
            self.assertIn(NOTES[rid], sec)

    def test_coverage_notes_exact(self):
        self.assertIn(NOTES["emerald-isle"], _tools(self.salt("emerald-isle")))
        self.assertIn(NOTES["neuse-river"], _tools(self.fresh("neuse-river")))
        self.assertNotIn("mwt-note", _tools(self.salt("crystal-coast")))
        self.assertNotIn("mwt-note", _tools(self.fresh("falls-lake")))
        self.assertNotIn("mwt-note", _tools(self.fresh("jordan-lake")))

    def test_captions_are_photo_locations_with_verbatim_credits(self):
        salt = _tools(self.salt())
        self.assertIn("Photo: Swan Quarter Landing, Hyde County · " + CREDITS["salt"], salt)
        self.assertNotIn("Crystal Coast ramp", salt.lower())
        falls = _tools(self.fresh("falls-lake"))
        self.assertIn("Photo: Falls Lake, North Carolina · " + CREDITS["falls-lake"], falls)
        self.assertNotIn("Jordan Lake", falls)
        jordan = _tools(self.fresh("jordan-lake"))
        self.assertIn("Photo: Jordan Lake State Recreation Area, Ebenezer Church area · " + CREDITS["jordan-lake"], jordan)
        self.assertNotIn("Falls Lake", jordan)
        jcap = re.search(r'<figcaption class="mwt-cr">(.*?)</figcaption>', jordan, re.S).group(1)
        self.assertNotIn("ramp", jcap.lower())
        self.assertNotIn("launch", jcap.lower())
        neuse = _tools(self.fresh("neuse-river"))
        self.assertIn("Photo: Cliffs of the Neuse State Park, North Carolina · " + CREDITS["neuse-river"], neuse)
        ncap = re.search(r'<figcaption class="mwt-cr">(.*?)</figcaption>', neuse, re.S).group(1)
        self.assertNotIn("ramp", ncap.lower())
        self.assertNotIn("launch", ncap.lower())

    def test_freshwater_has_no_tide_or_nautical_chart(self):
        for rid in FRESH:
            sec = _tools(self.fresh(rid))
            self.assertNotIn("Tide", sec)
            self.assertNotIn("tide-search", sec)
            self.assertNotIn("Nautical", sec)
            self.assertNotIn("map-chart", sec)
            self.assertIn("#fw-fc", sec)
            self.assertIn("Find a Ramp", sec)

    def test_saltwater_has_tide_forecast_and_chart(self):
        sec = _tools(self.salt())
        self.assertIn("#tide-search", sec)
        self.assertIn("#forecast", sec)
        self.assertIn("#map-chart", sec)
        self.assertIn("Nautical Charts", sec)
        self.assertIn("NOAA ENC", sec)
        self.assertIn('class="mwt-chart"', sec)

    def test_nav_has_the_three_entries(self):
        h = self.salt()
        nav = re.search(r'<details class="allnav".*?</details>', h, re.S).group(0)
        self.assertIn("Find a Ramp", nav)
        self.assertIn("Tide Charts", nav)
        self.assertIn("Forecasts", nav)
        fh = self.fresh()
        navf = re.search(r'<details class="allnav".*?</details>', fh, re.S).group(0)
        self.assertIn("Find a Ramp", navf)
        self.assertIn("Forecasts", navf)
        self.assertNotIn("Tide Charts", navf)

    def test_public_ramps_off_drops_card_and_nav_cleanly(self):
        h = self.salt(ramps=False)
        sec = _tools(h)
        self.assertTrue(sec)
        self.assertNotIn("mwt-ramp", sec)
        self.assertNotIn("All NC ramps", sec)
        self.assertNotIn("Find a Ramp", h)
        self.assertIn("Tide Charts", sec)
        self.assertIn("Forecasts", sec)
        self.assertIn('id="tools"', h)
        self.assertIn('id="gates"', h)
        nav = re.search(r'<details class="allnav".*?</details>', h, re.S).group(0)
        self.assertNotIn("Find a Ramp", nav)
        # freshwater too
        f = self.fresh(ramps=False)
        self.assertNotIn("mwt-ramp", f)
        self.assertNotIn("Find a Ramp", f)
        self.assertIn("Forecasts", _tools(f))

    def test_falls_is_never_jordan(self):
        self.assertEqual(self.sh.GAUGES["jordan-lake"]["guide"], 216.0)
        self.assertEqual(self.sh.GAUGES["falls-lake"]["guide"], 251.5)
        self.assertNotIn("Jordan Lake", _tools(self.fresh("falls-lake")))
        self.assertNotIn("Falls Lake", _tools(self.fresh("jordan-lake")))

    def test_no_fishermans_post(self):
        for html in (self.salt(), self.fresh("falls-lake"), self.fresh("jordan-lake"), self.fresh("neuse-river")):
            self.assertNotRegex(html, r"Fisherman.?s Post")


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
            self.assertEqual(self._get(ROUTE)[0], 404)
            self.assertEqual(self._get(ROUTE + "?region=falls-lake")[0], 404)
            self.assertEqual(self._get(ROUTE, "cb_preview=nope")[0], 404)
        with mock.patch.dict(os.environ, {"PREVIEW_KEY": ""}):
            self.assertEqual(self._get(ROUTE)[0], 404)

    def test_with_cookie_noindex_nostore(self):
        import signature_helm
        ck = "%s=%s" % (self.server.PREVIEW_COOKIE, self.server._preview_cookie_value(KEY))
        stub = "<!DOCTYPE html><html><head><meta name=\"robots\" content=\"noindex, nofollow\"></head><body>ok</body></html>"
        with mock.patch.dict(os.environ, {"PREVIEW_KEY": KEY}), \
                mock.patch.object(signature_helm, "page", lambda rid, **kw: stub.encode()):
            st, h, body = self._get(ROUTE + "?region=crystal-coast", ck)
        self.assertEqual(st, 200)
        self.assertIn("noindex", h.get("X-Robots-Tag", ""))
        self.assertIn("no-store", h.get("Cache-Control", ""))
        self.assertEqual(h.get("Vary"), "Cookie")
        self.assertIn('content="noindex, nofollow"', body)

    def test_not_in_sitemap_or_robots(self):
        st, _, sm = self._get("/sitemap.xml")
        self.assertEqual(st, 200)
        self.assertNotIn("/preview/helm-tools", sm)
        self.assertNotIn("/preview/helm-tools", self._get("/robots.txt")[2])
        self.assertEqual(self._get("/preview/helm/tools.css")[0], 404)

    def test_public_home_does_not_load_tools_css_or_section(self):
        st, _, body = self._get("/")
        self.assertEqual(st, 200)
        self.assertNotIn("mwt-ramp", body)
        self.assertNotIn("id=\"mwt-css\"", body)
        self.assertNotIn("All NC ramps", body)


if __name__ == "__main__":
    unittest.main()
