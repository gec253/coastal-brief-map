"""/wind coastline (Ed t353u): our own U.S. Census Bureau 2025 cartographic boundary land (1:500,000)
replaces Esri tiles on /wind in day and night. Data integrity, land/water alignment at known points,
projection parity with Leaflet's EPSG:3857, no Esri on /wind, theme palettes with >= 3:1 contrast for
every legend colour, reduced motion, and tile-by-tile zoom/pan redraw."""
import json
import math
import re
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NODE = shutil.which("node")
LO = json.loads((ROOT / "wind-coast" / "lo.json").read_text())
HI = json.loads((ROOT / "wind-coast" / "hi.json").read_text())

# (lat, lon, is_land)
KNOWN = {
    "Cape Hatteras Light": (35.2507, -75.5288, True),
    "Bodie Island Light": (35.8186, -75.5633, True),
    "Ocracoke village": (35.1146, -75.9810, True),
    "Shackleford Banks": (34.672, -76.600, True),
    "Emerald Isle (Bogue Banks)": (34.664, -77.030, True),
    "Morehead City": (34.722, -76.726, True),
    "Raleigh": (35.78, -78.64, True),
    "Oregon Inlet": (35.7712, -75.5310, False),
    "Hatteras Inlet": (35.1990, -75.7570, False),
    "Ocracoke Inlet": (35.0700, -76.0150, False),
    "Beaufort Inlet": (34.692, -76.670, False),
    "Pamlico Sound": (35.30, -75.90, False),
    "Albemarle Sound": (36.05, -76.20, False),
    "Currituck Sound": (36.35, -75.88, False),
    "Core Sound": (34.85, -76.40, False),
    "Bogue Sound": (34.70, -76.95, False),
    "Atlantic off Cape Lookout": (34.50, -76.40, False),
}


def decode(doc):
    q = doc["q"]
    polys = []
    for p in doc["polys"]:
        rings = []
        for a in p["r"]:
            x = y = 0
            pts = []
            for i in range(0, len(a), 2):
                x += a[i]; y += a[i + 1]
                pts.append((x / q, y / q))
            rings.append(pts)
        polys.append({"b": [v / q for v in p["b"]], "r": rings})
    return polys


def in_land(polys, lon, lat):
    for p in polys:
        b = p["b"]
        if not (b[0] <= lon <= b[2] and b[1] <= lat <= b[3]):
            continue
        inside = False
        for r in p["r"]:
            j = len(r) - 1
            for i in range(len(r)):
                (xi, yi), (xj, yj) = r[i], r[j]
                if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / (yj - yi) + xi:
                    inside = not inside
                j = i
        if inside:
            return True
    return False


def _segments_cross(a, b, c, d):
    def o(p, q, r):
        v = (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
        return (v > 0) - (v < 0)
    return o(a, b, c) * o(a, b, d) < 0 and o(c, d, a) * o(c, d, b) < 0


class DataIntegrity(unittest.TestCase):
    def test_source_and_metadata(self):
        for doc in (LO, HI):
            self.assertIn("U.S. Census Bureau, 2025 Cartographic Boundary File", doc["source"])
            self.assertIn("cb_2025_us_state_500k", doc["source"])
            self.assertEqual(doc["q"], 10000)
            self.assertEqual(doc["clip"], [-85.0, 29.0, -68.0, 41.0])
        self.assertEqual(LO["zoom"][1], 7.99)
        self.assertEqual(HI["zoom"][0], 8)
        self.assertLess(LO["simplify_deg"], 0.005)
        self.assertLessEqual(HI["simplify_deg"], 0.0005)          # ~50 m, finer than 1:500,000 shows

    def test_bounds_rings_and_bbox(self):
        for doc in (LO, HI):
            polys = decode(doc)
            self.assertGreater(len(polys), 20)                    # mainland + barrier islands
            for p in polys:
                xs = [x for r in p["r"] for x, _ in r]
                ys = [y for r in p["r"] for _, y in r]
                self.assertGreaterEqual(min(xs), -85.0); self.assertLessEqual(max(xs), -68.0)
                self.assertGreaterEqual(min(ys), 29.0); self.assertLessEqual(max(ys), 41.0)
                # stored bbox covers the outer ring (1e-4 rounding)
                self.assertLessEqual(p["b"][0], min(xs) + 1e-4); self.assertGreaterEqual(p["b"][2], max(xs) - 1e-4)
                self.assertLessEqual(p["b"][1], min(ys) + 1e-4); self.assertGreaterEqual(p["b"][3], max(ys) - 1e-4)
                for r in p["r"]:
                    self.assertGreaterEqual(len(r), 4)
                    self.assertEqual(r[0], r[-1])                 # closed

    def test_outer_rings_do_not_self_intersect_near_coast(self):
        # Valid-geometry spot check on the sounds/Outer Banks window (full check is in the build with shapely).
        for doc in (LO, HI):
            for p in decode(doc):
                for r in p["r"]:
                    seg = [(r[i], r[i + 1]) for i in range(len(r) - 1)
                           if -76.8 <= r[i][0] <= -75.4 and 34.6 <= r[i][1] <= 36.0]
                    if len(seg) > 1500:
                        seg = seg[:1500]
                    for i in range(len(seg)):
                        for j in range(i + 2, len(seg)):
                            if seg[i][0] == seg[j][1] or seg[j][0] == seg[i][1]:
                                continue
                            self.assertFalse(_segments_cross(seg[i][0], seg[i][1], seg[j][0], seg[j][1]))

    def test_size_budget(self):
        lo, hi = (ROOT / "wind-coast" / "lo.json").stat().st_size, (ROOT / "wind-coast" / "hi.json").stat().st_size
        self.assertLess(lo, 40 * 1024, lo)
        self.assertLess(hi, 110 * 1024, hi)


class Alignment(unittest.TestCase):
    def test_known_points_land_or_water_both_lods(self):
        for doc in (LO, HI):
            polys = decode(doc)
            for name, (lat, lon, land) in KNOWN.items():
                self.assertEqual(in_land(polys, lon, lat), land, "%s (%s)" % (name, doc["simplify_deg"]))

    @unittest.skipUnless(NODE, "node not installed")
    def test_browser_matches_python_and_leaflet_projection(self):
        pts = [[lat, lon] for lat, lon, _ in KNOWN.values()]
        out = subprocess.run([NODE, "-e",
            "const C=require('./wind-coast.js'),fs=require('fs');const hi=C.decode(JSON.parse(fs.readFileSync('wind-coast/hi.json')));"
            "const pts=%s;console.log(JSON.stringify({land:pts.map(p=>C.pointInLand(hi,p[1],p[0])),"
            "proj:pts.map(p=>[C.project(p[1],p[0],7),C.project(p[1],p[0],9.5)]),"
            "inv:pts.map(p=>{const a=C.project(p[1],p[0],9);return C.unproject(a[0],a[1],9)})}))" % json.dumps(pts)],
            cwd=ROOT, capture_output=True, text=True, timeout=30)
        self.assertEqual(out.returncode, 0, out.stderr)
        r = json.loads(out.stdout)
        self.assertEqual(r["land"], [v[2] for v in KNOWN.values()])
        # Leaflet L.CRS.EPSG3857: SphericalMercator (R = 6378137) + Transformation(0.5/(pi R), 0.5, -0.5/(pi R), 0.5), scale 256*2^z
        R = 6378137
        for (lat, lon), (p7, p95), inv in zip(pts, r["proj"], r["inv"]):
            for z, got in ((7, p7), (9.5, p95)):
                s = 256 * 2 ** z
                x, y = R * math.radians(lon), R * math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))
                k = 0.5 / (math.pi * R)
                self.assertAlmostEqual(got[0], s * (k * x + 0.5), places=6)
                self.assertAlmostEqual(got[1], s * (-k * y + 0.5), places=6)
            self.assertAlmostEqual(inv[0], lon, places=9)
            self.assertAlmostEqual(inv[1], lat, places=9)


def _lum(c):
    f = lambda v: v / 255 / 12.92 if v / 255 <= 0.03928 else ((v / 255 + 0.055) / 1.055) ** 2.4
    r, g, b = (f(x) for x in c)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _cr(a, b):
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def _hex(s):
    return [int(s[i:i + 2], 16) for i in (1, 3, 5)]


class ThemeAndPage(unittest.TestCase):
    css = (ROOT / "wind.css").read_text()
    html = (ROOT / "wind.html").read_text()
    js = (ROOT / "wind-viewer.js").read_text()
    coast = (ROOT / "wind-coast.js").read_text()
    engine = (ROOT / "wind-lab.js").read_text()

    def palette(self, dark):
        block = re.search(r'html\[data-theme="dark"\] \{(.*?)\}' if dark else r":root \{(.*?)\}", self.css, re.S).group(1)
        return {k: re.search(r"--%s: (#[0-9A-Fa-f]{6})" % k, block).group(1) for k in ("map-bg", "coast-land")}

    def ramp(self, dark):
        name = "STOPS_DARK" if dark else "STOPS_LIGHT"
        stops = json.loads(re.search(name + r" = (\[\[.*?\]\]);", self.engine).group(1))
        out = []
        for kt in [k / 2 for k in range(0, 81)]:
            for i in range(1, len(stops)):
                if kt <= stops[i][0]:
                    (a, ca), (b, cb) = stops[i - 1], stops[i]
                    t = (kt - a) / (b - a)
                    out.append([round(ca[j] + (cb[j] - ca[j]) * t) for j in range(3)])
                    break
            else:
                out.append(stops[-1][1])
        return out

    def test_legend_colours_3_to_1_on_land_and_water_day_and_night(self):
        for dark in (False, True):
            pal = self.palette(dark)
            for key in ("map-bg", "coast-land"):
                worst = min(_cr(c, _hex(pal[key])) for c in self.ramp(dark))
                self.assertGreaterEqual(worst, 3.0, (dark, key, pal[key], worst))

    def test_day_and_night_palettes_differ_and_follow_theme(self):
        day, night = self.palette(False), self.palette(True)
        self.assertEqual(day["coast-land"].upper(), "#F6F1E7")       # site oyster
        self.assertEqual(night["map-bg"].upper(), "#0C2740")
        self.assertNotEqual(day, night)
        self.assertIn('getPropertyValue("--coast-land")', self.js)
        self.assertIn('localStorage.getItem("coastalBrief.theme")', self.html)   # site preference
        self.assertIn("prefers-color-scheme: dark", self.html)

    def test_no_esri_or_third_party_tiles_on_wind(self):
        for f in ("wind.html", "wind.css", "wind-viewer.js", "wind-coast.js"):
            t = (ROOT / f).read_text()
            self.assertNotIn("arcgisonline", t, f)
            self.assertNotIn("arcgis.com", t, f)
            self.assertNotIn("tile.openstreetmap", t, f)
            self.assertNotIn("cartocdn", t, f)
        self.assertNotIn("preconnect", self.html)
        self.assertIn('<script src="/wind/coast.js" defer></script>', self.html)

    def test_tiles_drawn_one_per_task_and_redraw_on_zoom(self):
        self.assertIn("L.GridLayer.extend", self.coast)
        self.assertIn("requestAnimationFrame(pump)", self.coast)              # one tile per frame
        self.assertIn("let job = queue.shift();", self.coast)
        self.assertIn("fadeAnimation: false", self.js)
        self.assertIn('c.z >= CoastMath.HI_ZOOM ? "hi" : "lo"', self.coast)    # detailed when zoomed in
        self.assertIn("HI_ZOOM: 8", self.coast)
        self.assertIn("maxZoom: 9.5", self.js)                              # Census 1:500,000 display limit

    def test_reduced_motion_still_static_arrows(self):
        self.assertIn("!osReduce", self.js)
        self.assertIn("drawArrows", self.engine)

    def test_lab_and_dashboard_untouched(self):
        self.assertIn("arcgisonline", self.engine)          # /lab/wind keeps its Esri layer (Ed's separate decision)
        self.assertIn("arcgisonline", (ROOT / "app.js").read_text())


class Routes(unittest.TestCase):
    def test_coast_routes_gated_and_raw_files_denied(self):
        import os, threading, urllib.request, urllib.error
        from http.server import ThreadingHTTPServer
        from unittest import mock
        import server
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        base = "http://127.0.0.1:%d" % httpd.server_address[1]

        def get(p):
            try:
                with urllib.request.urlopen(base + p, timeout=20) as r:
                    return r.status, r.headers.get("Cache-Control")
            except urllib.error.HTTPError as e:
                return e.code, None
        try:
            with mock.patch.dict(os.environ, {"WIND_PARTICLES_ENABLED": "", "PREVIEW_KEY": ""}):
                for p in ("/wind/coast.js", "/wind/coast-lo.json", "/wind/coast-hi.json", "/wind-coast.js", "/wind-coast/lo.json"):
                    self.assertEqual(get(p)[0], 404, p)
            with mock.patch.dict(os.environ, {"WIND_PARTICLES_ENABLED": "1"}):
                self.assertEqual(get("/wind/coast.js")[0], 200)
                self.assertEqual(get("/wind/coast-hi.json"), (200, "private, max-age=86400"))
                self.assertEqual(get("/wind-coast/hi.json")[0], 404)
        finally:
            httpd.shutdown(); httpd.server_close()


if __name__ == "__main__":
    unittest.main()
