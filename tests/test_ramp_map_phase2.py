"""Ramp Finder Phase 2, steps 1-2 (Ed t556u): map data file, private preview route, flag gating,
Ed's five decisions as far as steps 1-2 reach, and the location-privacy and honesty rules."""
import json
import os
import re
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path

import launch_flags
import ramp_map
import ramp_map_data as rmd

ROOT = Path(__file__).resolve().parent.parent
KEY = "local-test-key-phase2-map-not-production"
SW = json.loads(rmd.STATEWIDE.read_text())
DOC = json.loads(rmd.OUT.read_text())
BY = {r["id"]: r for r in DOC["records"]}
JS = ramp_map.JS_PATH.read_text()
CSS = ramp_map.CSS_PATH.read_text()


class MapData(unittest.TestCase):
    def test_file_is_current_with_statewide(self):
        self.assertEqual(rmd.OUT.read_text(), rmd.dumps(rmd.build(SW)))

    def test_every_directory_record_is_carried(self):
        self.assertEqual(len(DOC["records"]), len(SW["records"]))
        self.assertEqual(len(DOC["records"]), 285)
        self.assertEqual(set(BY), {r["id"] for r in SW["records"]})

    def test_pin_counts(self):
        m = DOC["meta"]
        self.assertEqual((m["total"], m["pins"], m["exact"], m["approx"], m["address_only"]), (285, 281, 271, 10, 4))
        self.assertEqual({r["id"] for r in DOC["records"] if r["pr"] == "none"},
                         {"usace-jordan-poes-ridge", "local-newbern-glenburnie", "local-newbern-lawson-creek-1", "local-newbern-lawson-creek-2"})
        for r in DOC["records"]:
            if r["pr"] == "none":
                self.assertIsNone(r["la"]); self.assertIsNone(r["lo"])
            else:
                self.assertTrue(33.5 < r["la"] < 36.7 and -84.5 < r["lo"] < -75.3, r["id"])

    def test_approximate_points_are_exactly_the_state_parks_access_points(self):
        oc = json.loads((ROOT / "preview" / "ramp-finder" / "official_coordinates.json").read_text())
        approx = {r["id"] for r in DOC["records"] if r["pr"] == "approx"}
        self.assertEqual(approx, set(oc["records"]))
        for rid in approx:
            r = BY[rid]
            self.assertEqual((r["la"], r["lo"]), (oc["records"][rid]["lat"], oc["records"][rid]["lon"]))
            self.assertIn("State Parks", r["cs"])
            self.assertTrue(r["ad"], rid)  # directions by street address

    def test_exact_pins_use_the_records_official_coordinates(self):
        for s in SW["records"]:
            d = s["directions"]
            if d["mode"] == "coordinates":
                r = BY[s["id"]]
                self.assertEqual((r["pr"], r["la"], r["lo"]), ("exact", d["latitude"], d["longitude"]))

    def test_type_and_status_stay_separate_and_counts_match(self):
        from collections import Counter
        self.assertEqual(Counter(r["ty"] for r in DOC["records"]), {"trailer": 263, "paddle": 11, "limited": 7, "needs_review": 4})
        self.assertEqual(Counter(r["st"] for r in DOC["records"]),
                         {"listed_open": 261, "not_stated": 15, "temporarily_closed": 6, "conflicting": 2, "partially_open": 1})
        for s in SW["records"]:
            self.assertEqual(BY[s["id"]]["ty"], s["type_dimension"])
            self.assertEqual(BY[s["id"]]["st"], s["access_status"]["code"])

    def test_status_and_restriction_text_never_truncated(self):
        for s in SW["records"]:
            r = BY[s["id"]]
            self.assertEqual(r["sd"], s["access_status"]["detail"], s["id"])
            self.assertEqual(r["stf"], s["access_status"]["label"], s["id"])
            if s["type_dimension"] in ("limited", "needs_review"):
                self.assertEqual(r["rx"], s["restriction_notes"], s["id"])
                self.assertTrue(r["rx"].strip(), s["id"])

    def test_limited_label_and_facility_fields(self):
        self.assertEqual(rmd.TYPE_LABELS["limited"], "Limited access")
        for r in DOC["records"]:
            self.assertIn(r["fee"], ("free_stated", "fee_applies", "camping_only", "not_stated"))
            self.assertIsInstance(r["ada"], list)
            for f in r["ada"]:
                self.assertTrue(f.startswith("ADA "), f)
            self.assertNotIn("fishing_pier", r)

    def test_size_budget(self):
        import gzip
        self.assertLessEqual(len(gzip.compress(rmd.OUT.read_bytes(), 9)), 30 * 1024)

    def test_build_script_check_mode(self):
        import subprocess, sys
        r = subprocess.run([sys.executable, str(ROOT / "scripts" / "build_ramp_map_data.py"), "--check"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


class ScriptAndPage(unittest.TestCase):
    def test_no_location_request_storage_or_transmission(self):
        # Phase 2 (Ed t558u): location may be requested, but only once, only inside the explicit
        # "Use my location" tap handler, and the position is never stored, sent or put in the URL.
        for bad in ("watchPosition", "sendBeacon", "XMLHttpRequest", "pushState", "location.hash",
                    "location.href =", "sessionStorage", "document.cookie", "indexedDB", "WebSocket", "EventSource"):
            self.assertNotIn(bad, JS, bad)
        self.assertEqual(JS.count("getCurrentPosition"), 1)
        self.assertEqual(JS.count("navigator.geolocation"), 1)
        handler = JS[JS.index('$("#pre-go").addEventListener("click"'):]
        handler = handler[:handler.index("\n});") + 4]
        self.assertIn("navigator.geolocation.getCurrentPosition", handler)
        self.assertIn("enableHighAccuracy: false", handler)
        # the only fetches are our own data and geography files, none of which carry a position
        self.assertEqual(re.findall(r"fetch\(([^,)]*)", JS), ['BASE + "/geo-hi.json"', 'BASE + ".json"', 'BASE + "/geo-lo.json"'])
        self.assertEqual(set(re.findall(r'localStorage\.\w+\("([^"]+)"', JS)), {"coastalBrief.theme"})
        # the URL is written in exactly one place, from search and filters only
        self.assertEqual(JS.count("replaceState"), 1)
        fn = JS[JS.index("function urlFromState()"):JS.index("function readURL()")]
        self.assertIn("history.replaceState", fn)
        for loc in ("NEAR", "coords", "pos.", ".lat", ".lon", "latitude", "longitude"):
            self.assertNotIn(loc, fn, loc)
        self.assertIn('var URLKEYS = ["q", "in", "type", "status", "fac", "fee"];', JS)
        # the position lives in one in-memory variable and is cleared on exit and page hide
        self.assertIn('addEventListener("pagehide", function () { NEAR = null; });', JS)
        self.assertIn("function exitNear() { NEAR = null;", JS)

    def test_no_demo_point_or_placeholders(self):
        for bad in ("Demo position", "DEMO", "35.1085", "Future field", "coming soon", "Coming soon", "TODO"):
            self.assertNotIn(bad, JS + CSS + ramp_map.render_html(), bad)

    def test_no_truncation_styles_and_honest_labels(self):
        self.assertNotIn("line-clamp", CSS)
        self.assertNotIn("text-overflow", CSS)
        self.assertIn("ADA features listed", JS)
        self.assertNotIn("ADA access", JS)
        self.assertNotIn("fishing", JS.lower())
        self.assertIn("Approximate location", JS)
        self.assertIn("Limited access", JS + ramp_map.render_html())
        self.assertIn("Needs review", JS)

    def test_pages_use_only_our_own_assets(self):
        for public in (False, True):
            h = ramp_map.render_html(public=public)
            self.assertNotRegex(h, r"(src|href)=\"(https?:)?//")
            self.assertIn("/vendor/leaflet/leaflet.js", h)
            self.assertIn("/wind/coast.js", h)
        # the only outside URLs are the two directions apps, opened by the user with a destination only
        self.assertEqual(sorted(set(re.findall(r'"(https?://[^"]*)"', JS))),
                         ["https://maps.apple.com/?daddr=", "https://www.google.com/maps/dir/?api=1&destination="])
        self.assertEqual(len(re.findall(r"https?://", JS)), 2)
        self.assertIn("noindex", ramp_map.render_html(public=False))
        self.assertIn('base: "/wind/coast-"', JS)

    def test_44px_controls(self):
        self.assertRegex(CSS, r"\.theme button\{min-height:44px")
        self.assertIn(".panel .x{width:44px;height:44px", CSS)
        self.assertIn("width:44px;height:44px;line-height:44px", CSS)
        self.assertIn('iconSize: [44, 44]', JS)


class Routes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import server
        cls.server = server
        cls.httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.port = cls.httpd.server_address[1]
        cls.ck = "%s=%s" % (server.PREVIEW_COOKIE, server._preview_cookie_value(KEY))

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown(); cls.httpd.server_close()

    def setUp(self):
        self.saved = {k: os.environ.get(k) for k in (launch_flags.PUBLIC_RAMPS, launch_flags.PUBLIC_RAMP_MAP, "PREVIEW_KEY")}
        os.environ["PREVIEW_KEY"] = KEY

    def tearDown(self):
        for k, v in self.saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def req(self, path, cookie=None):
        c = HTTPConnection("127.0.0.1", self.port, timeout=15)
        c.request("GET", path, headers={"Cookie": cookie} if cookie else {})
        r = c.getresponse(); body = r.read(); h = {k.lower(): v for k, v in r.getheaders()}; c.close()
        return r.status, body, h

    PRIVATE = ["/preview/ramps-statewide/map", "/preview/ramps-statewide/map.css",
               "/preview/ramps-statewide/map.js", "/preview/ramps-statewide/map.json",
               "/preview/ramps-statewide/map/geo-lo.json", "/preview/ramps-statewide/map/geo-hi.json"]
    PUBLIC = ["/ramps/map", "/ramps/map/", "/ramps/map.css", "/ramps/map.js", "/ramps/map.json", "/ramps.json",
              "/ramps/map/geo-lo.json", "/ramps/map/geo-hi.json"]

    def test_private_preview_is_cookie_gated(self):
        for p in self.PRIVATE:
            self.assertEqual(self.req(p)[0], 404, p)
            st, body, h = self.req(p, self.ck)
            self.assertEqual(st, 200, p)
            self.assertIn("no-store", h.get("cache-control", ""), p)
        st, body, _ = self.req("/preview/ramps-statewide/map.json", self.ck)
        self.assertEqual(json.loads(body)["meta"]["total"], 285)

    def test_public_map_404_with_flag_off_even_with_cookie(self):
        os.environ.pop(launch_flags.PUBLIC_RAMP_MAP, None)
        for ramps in ("1", "0"):
            os.environ[launch_flags.PUBLIC_RAMPS] = ramps
            for p in self.PUBLIC:
                self.assertEqual(self.req(p)[0], 404, (ramps, p))
                self.assertEqual(self.req(p, self.ck)[0], 404, (ramps, p))

    def test_flag_on_serves_the_phase2_map_publicly(self):
        os.environ[launch_flags.PUBLIC_RAMP_MAP] = "1"
        st, body, _ = self.req("/ramps/map")
        self.assertEqual(st, 200)
        self.assertIn(b'data-base="/ramps/map"', body)
        self.assertNotIn(b"Private preview", body)
        st, body, _ = self.req("/ramps/map.json")
        self.assertEqual((st, json.loads(body)["meta"]["pins"]), (200, 281))
        self.assertEqual(self.req("/ramps/map.css")[0], 200)
        self.assertEqual(self.req("/ramps/map.js")[0], 200)
        self.assertEqual(self.req("/ramps/map/geo-lo.json")[0], 200)
        self.assertEqual(self.req("/ramps/map/geo-hi.json")[0], 200)
        self.assertEqual(self.req("/ramps.json")[0], 404)

    def test_sitemap_unchanged_with_flag_off(self):
        os.environ.pop(launch_flags.PUBLIC_RAMP_MAP, None)
        os.environ[launch_flags.PUBLIC_RAMPS] = "1"
        st, body, _ = self.req("/sitemap.xml")
        self.assertNotIn(b"/ramps/map", body)
        self.assertNotIn(b"ramps-statewide", body)


    def test_preview_hub_lists_the_private_map(self):
        st, body, h = self.req("/preview", self.ck)
        self.assertEqual(st, 200)
        self.assertIn(b'noindex, nofollow', body)
        self.assertIn(b'href="/preview/ramps-statewide/map"', body)
        self.assertIn(b'Statewide map (Phase 2, private)', body)
        self.assertEqual(self.req("/preview")[0], 404)
        st, sm, _ = self.req("/sitemap.xml")
        self.assertEqual(st, 200)
        self.assertNotIn(b"/preview/ramps-statewide", sm)
        self.assertNotIn(b"/ramps/map", sm)

    def test_directory_records_and_detail_pages_unchanged(self):
        os.environ[launch_flags.PUBLIC_RAMPS] = "1"
        self.assertEqual(self.req("/ramps")[0], 200)
        self.assertEqual(self.req("/ramps/parks-jordan-seaforth")[0], 200)
        self.assertEqual(self.req("/preview/ramps-statewide/parks-jordan-seaforth", self.ck)[0], 200)


if __name__ == "__main__":
    unittest.main()
