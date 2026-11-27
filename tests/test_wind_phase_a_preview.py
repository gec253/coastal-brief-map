"""Private Phase A wind preview (Ed t480u). Public /wind stays on production assets."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
PROD = "58a376c"
KEY = "a" * 32
NODE = shutil.which("node")


def _cookie():
    import server
    return "%s=%s" % (server.PREVIEW_COOKIE, server._preview_cookie_value(KEY))


class PhaseAPreview(unittest.TestCase):
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
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status, dict(r.headers), r.read()
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers), e.read()

    def test_unauthenticated_preview_is_404(self):
        with mock.patch.dict(os.environ, {"PREVIEW_KEY": KEY, "WIND_PARTICLES_ENABLED": ""}):
            for p in ("/preview/wind", "/preview/wind/engine.js", "/preview/wind/wind.css"):
                st, _, body = self._get(p)
                self.assertEqual(st, 404, p)
                self.assertIn(b"not found", body.lower())
            self.assertEqual(self._get("/preview/wind", "cb_preview=nope")[0], 404)

    def test_authenticated_preview_serves_phase_a_assets(self):
        ck = _cookie()
        with mock.patch.dict(os.environ, {"PREVIEW_KEY": KEY, "WIND_PARTICLES_ENABLED": ""}):
            st, h, body = self._get("/preview/wind", ck)
            self.assertEqual(st, 200)
            self.assertIn("private, no-store", (h.get("Cache-Control") or h.get("cache-control") or "").lower())
            self.assertIn("noindex", (h.get("X-Robots-Tag") or h.get("x-robots-tag") or "").lower())
            self.assertIn(b'href="/preview/wind/wind.css"', body)
            self.assertIn(b'src="/preview/wind/engine.js"', body)
            self.assertNotIn(b'href="/wind.css"', body)
            self.assertNotIn(b'src="/wind/engine.js"', body)
            self.assertIn(b"Model forecast", body)
            self.assertIn(b"NOAA NCEP GFS", body)

            st, h, css = self._get("/preview/wind/wind.css", ck)
            self.assertEqual(st, 200)
            self.assertIn("text/css", h.get("Content-Type") or h.get("content-type") or "")
            self.assertIn("private, no-store", (h.get("Cache-Control") or h.get("cache-control") or "").lower())
            self.assertIn(b"--map-bg: #CDDCE6", css)
            self.assertEqual(css, (ROOT / "preview" / "wind" / "wind.css").read_bytes())

            st, h, js = self._get("/preview/wind/engine.js", ck)
            self.assertEqual(st, 200)
            self.assertIn("javascript", h.get("Content-Type") or h.get("content-type") or "")
            self.assertIn("private, no-store", (h.get("Cache-Control") or h.get("cache-control") or "").lower())
            self.assertIn(b"[75, 156, 211]", js)
            self.assertEqual(js, (ROOT / "preview" / "wind" / "engine.js").read_bytes())

            # Hub lists the preview entry once the cookie is set.
            st, _, hub = self._get("/preview", ck)
            self.assertEqual(st, 200)
            self.assertIn(b'href="/preview/wind"', hub)
            self.assertIn(b"Wind viewer \xc2\xb7 Phase A", hub)

    def test_public_wind_serves_phase_a_without_preview_paths(self):
        with mock.patch.dict(os.environ, {"PREVIEW_KEY": KEY, "WIND_PARTICLES_ENABLED": ""}):
            st, _, html = self._get("/wind")
            self.assertEqual(st, 200)
            self.assertIn(b'href="/wind.css"', html)
            self.assertIn(b'src="/wind/engine.js"', html)
            self.assertNotIn(b"/preview/wind/", html)

            st, _, css = self._get("/wind.css")
            self.assertEqual(st, 200)
            self.assertEqual(css, (ROOT / "wind.css").read_bytes())
            self.assertEqual(css, (ROOT / "preview" / "wind" / "wind.css").read_bytes())
            self.assertIn(b"--map-bg: #CDDCE6", css)
            # Radar keeps the previous light water when wind.css is shared.
            self.assertIn(b'body[data-radar-view="viewer"] { --map-bg: #EAF1F4; }', css)

            st, _, js = self._get("/wind/engine.js")
            self.assertEqual(st, 200)
            self.assertEqual(js, (ROOT / "wind-lab.js").read_bytes())
            self.assertIn(b"[75, 156, 211]", js)   # Carolina blue
            self.assertNotIn(b"[240, 95, 95]", js)  # old rainbow tip

        # Ed t507u: wind.html and wind-viewer.js pinned to the reviewed B3 commit 02fbe50.
        B3 = "02fbe50b28499188ad7948badb99671d81d43c16"
        for rel in ("wind.html", "wind-viewer.js"):
            current = (ROOT / rel).read_bytes()
            baseline = subprocess.check_output(["git", "show", "%s:%s" % (B3, rel)], cwd=ROOT)
            self.assertEqual(current, baseline, rel)

    def test_preview_engine_respawns_in_field_not_only_at_edges(self):
        eng = (ROOT / "preview" / "wind" / "engine.js").read_text()
        # Phase A coverage fix: mid-life respawn is uniform in the viewport, not edge-only.
        self.assertNotIn("e === 0 ? 0 : e === 1 ? w - 1", eng)
        self.assertIn("Math.random() * w", eng)
        self.assertIn("uvAt(latY[yi], lonX[xi], tmp)", eng)  # prefer real grid U/V
        self.assertIn("maxParticles: phone ? 1100 : 2200", (ROOT / "wind-viewer.js").read_text())
        self.assertIn("FRAME_MS ? 78 : 130", eng)
        pub = (ROOT / "wind-lab.js").read_text()
        # Public /wind now uses the same valid-cell respawn as the approved preview.
        self.assertNotIn("e === 0 ? 0 : e === 1 ? w - 1", pub)
        self.assertIn("uvAt(latY[yi], lonX[xi], tmp)", pub)
        self.assertIn("for (let t = 0; t < 8; t++)", pub)
        self.assertIn("FRAME_MS ? 78 : 130", pub)
        self.assertIn("maxParticles: phone ? 1100 : 2200", (ROOT / "wind-viewer.js").read_text())

    @unittest.skipUnless(NODE, "node not installed")
    def test_spawn_places_particles_only_in_valid_uv_cells(self):
        """Behavioral check of spawn() in the preview and public engines: retry until uvAt sees real grid U/V.

        uvAt is the same 'inside the model grid' test used by public /wind. Spawn
        never invents U/V. With most of the viewport on-grid, every particle lands
        in a valid cell. A leftover invalid placement can only happen if all 8
        attempts miss (rare when coverage is high); the next frame respawns it
        and does not advect a fabricated vector.
        """
        script = r"""
const fs = require('fs');
const src = fs.readFileSync('preview/wind/engine.js', 'utf8');
const m = src.match(/function spawn\(i, randomAge\) \{[\s\S]*?\n    \}/);
if (!m) { console.error('spawn not found'); process.exit(2); }
const w = 80, h = 60;
const lonX = new Float32Array(w), latY = new Float32Array(h);
for (let x = 0; x < w; x++) lonX[x] = -80 + (7 * x) / w;     // -80 .. -73
for (let y = 0; y < h; y++) latY[y] = 37.5 - (5 * y) / h;    // 37.5 .. 32.5
// GFS-like bbox: 32.5-37.5N, 80-73W, leaving a thin strip outside to the north/west
const WEST = -79.5, EAST = -73.2, SOUTH = 32.7, NORTH = 37.2;
const PX = new Float32Array(4000), PY = new Float32Array(4000), AGE = new Uint8Array(4000);
const tmp = [0, 0];
let writes = 0, rejects = 0;
function uvAt(lat, lon, out) {
  if (!(lon >= WEST && lon <= EAST && lat >= SOUTH && lat <= NORTH)) { rejects++; return false; }
  if (!Number.isFinite(lat) || !Number.isFinite(lon)) { rejects++; return false; }
  out[0] = 1.5; out[1] = -0.5; writes++;
  return true;
}
eval(m[0]);
for (let i = 0; i < 4000; i++) spawn(i, true);
let valid = 0, invalid = 0, edgeOnly = 0, invented = 0;
const probe = [0, 0];
for (let i = 0; i < 4000; i++) {
  const xi = PX[i] | 0, yi = PY[i] | 0;
  if (xi === 0 || yi === 0 || xi === w - 1 || yi === h - 1) edgeOnly++;
  const before0 = probe[0], before1 = probe[1];
  const ok = uvAt(latY[yi], lonX[xi], probe);
  if (ok) {
    valid++;
    if (probe[0] !== 1.5 || probe[1] !== -0.5) invented++;
  } else {
    invalid++;
    if (probe[0] !== before0 || probe[1] !== before1) invented++;
  }
  if (!(PX[i] >= 0 && PX[i] < w && PY[i] >= 0 && PY[i] < h)) invented++;
}
// Mid-size valid island (~40% of the viewport): 8 attempts should almost always hit.
const island = {valid: 0, invalid: 0};
{
  const WEST2 = -79.0, EAST2 = -74.5, SOUTH2 = 33.5, NORTH2 = 36.5;
  function uvIsland(lat, lon, out) {
    if (!(lon >= WEST2 && lon <= EAST2 && lat >= SOUTH2 && lat <= NORTH2)) return false;
    out[0] = 3; out[1] = 1; return true;
  }
  const uvAt = uvIsland;
  eval(m[0]);
  for (let i = 0; i < 1000; i++) spawn(i, false);
  for (let i = 0; i < 1000; i++) {
    if (uvIsland(latY[PY[i] | 0], lonX[PX[i] | 0], [0, 0])) island.valid++;
    else island.invalid++;
  }
}
// uvAt absent: spawn must still pick a viewport point and must not throw
{
  const uvAt = null;
  eval(m[0]);
  spawn(0, true);
}
console.log(JSON.stringify({
  valid, invalid, edgeOnly, invented, writes, rejects,
  islandValid: island.valid, islandInvalid: island.invalid,
  sampleAge: AGE[0],
  spawnSrc: m[0]
}));
"""
        for src in ("preview/wind/engine.js", "wind-lab.js"):
            with self.subTest(src=src):
                out = subprocess.run(
                    [NODE, "-e", script.replace("preview/wind/engine.js", src)],
                    cwd=ROOT, capture_output=True, text=True, timeout=30,
                )
                self.assertEqual(out.returncode, 0, out.stderr)
                res = json.loads(out.stdout)
                self.assertEqual(res["invented"], 0)
                self.assertEqual(res["invalid"], 0, res)
                self.assertEqual(res["valid"], 4000)
                # Not the old edge-only pattern: particles must appear in the interior.
                self.assertGreater(res["valid"] - res["edgeOnly"], 3000)
                self.assertIn("uvAt(latY[yi], lonX[xi], tmp)", res["spawnSrc"])
                self.assertNotIn("e === 0 ? 0 : e === 1 ? w - 1", res["spawnSrc"])
                # A ~40% valid island is strongly preferred (8 attempts beat a single random shot).
                self.assertGreater(res["islandValid"], 900)

    def test_preview_not_in_sitemap_or_public_raw_paths(self):

        with mock.patch.dict(os.environ, {"PREVIEW_KEY": KEY, "WIND_PARTICLES_ENABLED": ""}):
            st, _, sm = self._get("/sitemap.xml")
            self.assertEqual(st, 200)
            self.assertNotIn(b"/preview/wind", sm)
            for p in ("/preview/wind/engine.js", "/preview/wind/wind.css",
                      "/preview/wind/../wind.css"):
                self.assertEqual(self._get(p)[0], 404, p)


if __name__ == "__main__":
    unittest.main()
