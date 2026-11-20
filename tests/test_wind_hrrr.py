"""Private HRRR prototype for /wind (?model=hrrr, Ed t358u).

Decode of a real NOMADS HRRR sub-region (Lambert conformal 3.30, simple packing), true-north rotation
against a pyproj reference, regrid bounds, run selection, labelled GFS fallback (never blended),
gating and an unchanged GFS default."""
import datetime as dt
import json
import math
import os
import re
import secrets
import sys
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "tests" / "fixtures" / "hrrr_uv10m_ncbox.grb2"   # real NOMADS HRRR 10 m U/V, 2026-11-19 23Z f01, 32-38N 80.5-72.5W
sys.path.insert(0, str(ROOT))
import hrrrgrid  # noqa: E402
import windgrid  # noqa: E402

# Native grid points (j, i) from the fixture: lat/lon and grid-relative U/V read with ecCodes 2.50, and
# earth-relative U/V rotated with pyproj's meridian convergence for the HRRR projection
# (lcc, lat_1=lat_2=lat_0=38.5, lon_0=-97.5, R=6371229). Independent of hrrrgrid.py.
REF = [  # j, i, lat, lon, u_grid, v_grid, u_earth, v_earth
    (0, 0, 32.21534, -81.76852, -2.3130, -3.3856, -2.8551, -2.9429),
    (100, 150, 34.04825, -76.41462, -3.8130, -10.0106, -5.9867, -8.8832),
    (271, 287, 37.54924, -70.54996, 3.8120, -0.1981, 3.5926, -1.2900),
    (200, 40, 37.30980, -79.27786, -1.4380, 1.6769, -1.0801, 1.9270),
    (50, 250, 32.09622, -73.69103, -10.3130, -5.0106, -11.2516, -2.2057),
]
NOW = dt.datetime(2026, 11, 20, 0, 10, tzinfo=dt.timezone.utc).timestamp()   # 7:10 PM ET Nov 19


def _gfs(ahead=0):
    return {"ok": True, "kind": "model forecast", "source": "NOAA NCEP GFS 0.25°", "run": "2026-11-19T18:00Z",
            "valid": "2026-11-20T00:00Z", "forecastHour": 6, "ahead": ahead, "units": "m/s", "nx": 2, "ny": 2,
            "la1": 37.5, "lo1": -80.0, "dx": 0.25, "dy": 0.25, "scan": 0, "u": [1, 2, 3, 4], "v": [0, 0, 0, 0]}


class Decode(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.msgs = hrrrgrid.decode(FIX.read_bytes())

    def test_lambert_grid_and_values(self):
        u, v = self.msgs
        g = u["grid"]
        self.assertEqual((u["cat"], u["num"], v["num"]), (2, 2, 3))
        self.assertEqual((g["nx"], g["ny"], g["dx"], g["dy"]), (288, 272, 3000.0, 3000.0))
        self.assertEqual((g["lad"], g["latin1"], g["latin2"], g["lov"]), (38.5, 38.5, 38.5, 262.5))
        self.assertTrue(g["flags"] & 0x08)                  # grid-relative winds
        self.assertEqual(g["scan"], 0x40)                   # south row first
        self.assertEqual((u["ref"].isoformat(), u["fhour"]), ("2026-11-19T23:00:00+00:00", 1))
        for j, i, _, _, ug, vg, _, _ in REF:
            k = j * g["nx"] + i
            self.assertAlmostEqual(u["values"][k], ug, delta=0.001)
            self.assertAlmostEqual(v["values"][k], vg, delta=0.001)

    def test_chunked_unpack_matches_bitwise(self):
        import random
        rnd = random.Random(1)
        for bits in (1, 7, 8, 9, 12, 16):
            for n in (1, 7, 8, 9, 63):
                vals = [rnd.randrange(1 << bits) for _ in range(n)]
                acc = 0
                for x in vals:
                    acc = (acc << bits) | x
                pad = (-n * bits) % 8
                raw = (acc << pad).to_bytes((n * bits + pad) // 8, "big")
                self.assertEqual(hrrrgrid.unpack(raw, n, bits), vals, (bits, n))

    def test_projection_locates_native_points(self):
        lam = hrrrgrid.Lambert(self.msgs[0]["grid"])
        for j, i, lat, lon, *_ in REF:
            fi, fj = lam.ij(lat, lon)
            self.assertAlmostEqual(fi, i, delta=0.01)
            self.assertAlmostEqual(fj, j, delta=0.01)

    def test_rotation_matches_reference_within_001(self):
        lam = hrrrgrid.Lambert(self.msgs[0]["grid"])
        for j, i, lat, lon, ug, vg, ue, ve in REF:
            u2, v2 = hrrrgrid.to_earth(ug, vg, lam.alpha(lon))
            self.assertLess(abs(u2 - ue), 0.01, (j, i))
            self.assertLess(abs(v2 - ve), 0.01, (j, i))
            self.assertAlmostEqual(math.hypot(u2, v2), math.hypot(ug, vg), places=9)   # speed preserved

    def test_rejects_unsupported(self):
        with self.assertRaises(ValueError):
            hrrrgrid.decode(FIX.read_bytes()[:5000])           # truncated
        gfs = (ROOT / "tests" / "fixtures" / "gfs_uv10m_ncbox.grb2").read_bytes()
        with self.assertRaises(ValueError):
            hrrrgrid.decode(gfs)                               # lat/lon grid, not 3.30


class Regrid(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.g = hrrrgrid.build(FIX.read_bytes())

    def test_bounds_and_shape_match_viewer_box(self):
        g = self.g
        self.assertEqual((g["nx"], g["ny"], g["la1"], g["lo1"], g["dx"], g["dy"], g["scan"]), (281, 201, 37.5, -80.0, 0.025, 0.025, 0))
        self.assertAlmostEqual(g["lo1"] + (g["nx"] - 1) * g["dx"], -73.0)
        self.assertAlmostEqual(g["la1"] - (g["ny"] - 1) * g["dy"], 32.5)
        self.assertEqual(len(g["u"]), 281 * 201)
        self.assertNotIn(None, g["u"])                         # the wide fetch covers every corner
        self.assertTrue(all(-80 < x < 80 for x in g["u"] + g["v"]))

    def test_payload_shape_matches_gfs_engine_contract(self):
        g = self.g
        for k in ("ok", "kind", "source", "run", "valid", "forecastHour", "units", "nx", "ny", "la1", "lo1", "dx", "dy", "scan", "u", "v"):
            self.assertIn(k, g)
        self.assertEqual((g["model"], g["kind"], g["units"], g["run"], g["valid"]), ("hrrr", "model forecast", "m/s", "2026-11-19T23:00Z", "2026-11-20T00:00Z"))
        self.assertIn("HRRR", g["source"])

    def test_regridded_value_near_native_point(self):
        # Native point (100,150) is 34.048N 76.415W; the regridded cell nearest it should be close (smooth field).
        g = self.g
        ii, jj = round((-76.41462 + 80) / 0.025), round((37.5 - 34.04825) / 0.025)
        k = jj * g["nx"] + ii
        self.assertLess(math.hypot(g["u"][k] - -5.9867, g["v"][k] - -8.8832), 1.0)

    def test_sanity_checks(self):
        self.assertIsNone(hrrrgrid.sane([1.0, -2.0], [3.0, 4.0], 0))
        self.assertEqual(hrrrgrid.sane([1.0, 95.0], [0.0, 0.0], 0), "wind out of range")
        self.assertEqual(hrrrgrid.sane([0.0] * 100, [0.0] * 100, 1), "grid does not cover the box")


class Selection(unittest.TestCase):
    def setUp(self):
        hrrrgrid._cache.clear()

    def test_candidates_skip_unposted_hour_and_respect_age_and_length(self):
        c = [(r.strftime("%d%HZ"), fh) for r, fh in hrrrgrid.candidates(NOW, 0)]
        self.assertEqual(c, [("1923Z", 1), ("1922Z", 2), ("1921Z", 3)])     # 00Z not posted at 00:10
        later = NOW + 50 * 60                                                   # 01:00Z, 00Z now ~60 min old
        self.assertEqual(hrrrgrid.candidates(later, 0)[0][0].hour, 0)
        # +12 h from 23Z needs f13 (<=18 ok); a non-synoptic run never offers beyond f18
        self.assertEqual(hrrrgrid.candidates(NOW, 12)[0][1], 13)
        far = [fh for _, fh in hrrrgrid.candidates(NOW + 6 * 3600, 12)]
        self.assertTrue(all(fh <= 48 for fh in far))
        self.assertLessEqual(len(c), hrrrgrid.MAX_RUN_AGE_H)

    def test_latest_grid_fetches_nomads_filter_and_caches(self):
        urls = []

        def fake(url):
            urls.append(url)
            return FIX.read_bytes()
        with mock.patch.object(hrrrgrid, "_fetch", side_effect=fake), \
             mock.patch.object(windgrid, "latest_grid", side_effect=AssertionError("no GFS needed")):
            g = hrrrgrid.latest_grid(now=NOW)
            hrrrgrid.latest_grid(now=NOW + 60)                    # cached
        self.assertEqual(len(urls), 1)
        self.assertIn("filter_hrrr_2d.pl", urls[0])
        self.assertIn("dir=%2Fhrrr.20261119%2Fconus", urls[0])
        self.assertIn("file=hrrr.t23z.wrfsfcf01.grib2", urls[0])
        self.assertIn("lev_10_m_above_ground=on", urls[0])
        self.assertEqual((g["model"], g["ahead"], g["forecastHour"]), ("hrrr", 0, 1))
        self.assertNotIn("fallback", g)

    def test_falls_back_to_labelled_gfs_and_caches_failure(self):
        calls = []

        def boom(url):
            calls.append(url)
            raise urllib.error.HTTPError(url, 404, "nf", {}, None)
        with mock.patch.object(hrrrgrid, "_fetch", side_effect=boom), \
             mock.patch.object(windgrid, "latest_grid", side_effect=_gfs):
            g = hrrrgrid.latest_grid(now=NOW, ahead=3)
            hrrrgrid.latest_grid(now=NOW + 60, ahead=3)           # failure cached, no new requests
        self.assertEqual(len(calls), 3)                            # at most MAX_RUN_AGE_H tries
        self.assertEqual((g["model"], g["requested"], g["fallback"], g["ahead"]), ("gfs", "hrrr", "HRRR unavailable", 3))
        self.assertEqual(g["u"], _gfs()["u"])                      # the GFS frame as-is: one model, never blended

    def test_bad_data_falls_back(self):
        with mock.patch.object(hrrrgrid, "_fetch", return_value=FIX.read_bytes()[:9000]), \
             mock.patch.object(windgrid, "latest_grid", side_effect=_gfs):
            g = hrrrgrid.latest_grid(now=NOW)
        self.assertEqual(g["fallback"], "HRRR unavailable")

    def test_unknown_ahead_treated_as_zero(self):
        with mock.patch.object(hrrrgrid, "_fetch", return_value=FIX.read_bytes()):
            self.assertEqual(hrrrgrid.latest_grid(now=NOW, ahead=5)["ahead"], 0)


class Labels(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.js = (ROOT / "wind-viewer.js").read_text()
        cls.html = (ROOT / "wind.html").read_text()

    def test_model_name_in_existing_labels_only(self):
        self.assertIn('wantHrrr = /[?&]model=hrrr\\b/.test(q)', self.js)
        self.assertIn('wantHrrr ? "model=hrrr" : ""', self.js)
        self.assertIn('"HRRR run" : "GFS run"', self.js)
        self.assertIn('"0.25° (HRRR unavailable)"', self.js)
        self.assertIn('"3 km model forecast"', self.js)
        self.assertIn('modelName + " model forecast"', self.js)
        # same cells and badge as before: text only, no new layout
        self.assertIn('<span class="w-k" id="w-run-k">Model run</span>', self.html)
        self.assertIn('<span class="w-badge" id="w-badge">Model forecast</span>', self.html)
        self.assertIn('<a id="w-src" href="https://www.nco.ncep.noaa.gov/pmb/products/gfs/" rel="noopener">NOAA NCEP GFS</a> <span id="w-src-res">0.25° model forecast</span>', self.html)

    def test_default_page_never_requests_hrrr(self):
        # Attribution is only rewritten when the page asked for HRRR; the payload decides which model is named.
        self.assertIn("if (!wantHrrr) return;", self.js)
        self.assertIn('const hrrr = g.model === "hrrr";', self.js)
        # HRRR name is set during parse (no post-paint reflow), only for ?model=hrrr.
        # The location readout is stacked above the attribution in .w-stack; the early script follows that wrapper.
        self.assertIn('class="w-stack"', self.html)
        self.assertRegex(self.html, r'</p>\n    </div>\n    <script>[^<]*if\(/\[\?&\]model=hrrr\\b/\.test\(location\.search\)\)\{[^<]*"3 km model forecast"')


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
        cls.httpd.shutdown(); cls.httpd.server_close()

    def _get(self, path, cookie=None):
        req = urllib.request.Request(self.base + path, headers={"Cookie": cookie} if cookie else {})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status, dict(r.headers), r.read()
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers), e.read()

    def test_hrrr_404_without_cookie(self):
        key = secrets.token_hex(16)
        with mock.patch.dict(os.environ, {"WIND_PARTICLES_ENABLED": "", "PREVIEW_KEY": key}), \
             mock.patch.object(hrrrgrid, "latest_grid", side_effect=AssertionError("must not fetch")):
            for p in ("/wind?model=hrrr", "/api/wind-grid?model=hrrr", "/api/wind-grid?model=hrrr&ahead=3"):
                self.assertEqual(self._get(p)[0], 404, p)
                self.assertEqual(self._get(p, "cb_preview=nope")[0], 404, p)
            for p in ("/hrrrgrid.py", "/tests/fixtures/hrrr_uv10m_ncbox.grb2"):
                self.assertEqual(self._get(p)[0], 404, p)

    def test_cookie_selects_hrrr_and_default_stays_gfs(self):
        key = secrets.token_hex(16)
        ck = "%s=%s" % (self.server.PREVIEW_COOKIE, self.server._preview_cookie_value(key))
        h_calls, g_calls = [], []

        def fake_h(ahead=0):
            h_calls.append(ahead)
            return {"ok": True, "model": "hrrr", "ahead": ahead}

        def fake_g(ahead=0):
            g_calls.append(ahead)
            return _gfs(ahead)
        with mock.patch.dict(os.environ, {"WIND_PARTICLES_ENABLED": "", "PREVIEW_KEY": key}), \
             mock.patch.object(hrrrgrid, "latest_grid", side_effect=fake_h), \
             mock.patch.object(windgrid, "latest_grid", side_effect=fake_g):
            self.assertEqual(json.loads(self._get("/api/wind-grid?model=hrrr&ahead=6", ck)[2])["model"], "hrrr")
            self._get("/api/wind-grid?model=hrrr&ahead=7", ck)
            body = self._get("/api/wind-grid?ahead=6", ck)[2]
            self._get("/api/wind-grid?model=gfs", ck)
            self.assertEqual(self._get("/wind?model=hrrr", ck)[0], 200)
        self.assertEqual(h_calls, [6, 0])
        self.assertEqual(g_calls, [6, 0])
        self.assertEqual(json.loads(body), _gfs(6))                # default payload unchanged: no model fields


if __name__ == "__main__":
    unittest.main()
