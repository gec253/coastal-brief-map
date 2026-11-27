"""Wind Viewer Phase B4 (Chart Helm): labels, compass, branding, attribution, types.

Does not raise official cap numbers or rewrite protected-file SHA pins.
Approved implementation ceilings (Ed t510u): 80 KiB own-asset, 18 KiB CSS.
Gazetteer size is reported and tested separately.
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
import time
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent

REQUIRED_PLACES = {
    "Atlantic Ocean", "Outer Banks", "Crystal Coast", "Cape Hatteras", "Cape Lookout", "Cape Fear",
    "Currituck Sound", "Albemarle Sound", "Pamlico Sound", "Core Sound", "Bogue Sound",
    "Onslow Bay", "Raleigh Bay", "Neuse River", "Pamlico River",
    "Oregon Inlet", "Hatteras Inlet", "Ocracoke Inlet", "Drum Inlet", "Beaufort Inlet", "Bogue Inlet",
    "New River Inlet", "New Topsail Inlet", "Masonboro Inlet", "Shallotte Inlet",
    "Corolla", "Duck", "Nags Head", "Rodanthe", "Hatteras", "Ocracoke", "Oriental", "New Bern",
    "Beaufort", "Morehead City", "Atlantic Beach", "Emerald Isle", "Surf City", "Wrightsville Beach",
    "Wilmington", "Southport", "Calabash",
}

# Physical types verified from NDBC station pages, 26 Nov 2026.
NDBC_KIND = {
    "41013": "buoy", "41025": "buoy", "41038": "buoy", "41064": "buoy",
    "CLKN7": "pier", "MBNN7": "pier", "MBIN7": "pier",
}

GAZETTEER_CAP = 8 * 1024
OWN_CAP = 80 * 1024
CSS_CAP = 18 * 1024
OWN_FILES = ("wind.html", "wind.css", "wind-viewer.js", "wind-lab.js", "wind-coast.js")


def _rel_luminance(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    r, g, b = [int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]

    def f(c):
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    R, G, B = f(r), f(g), f(b)
    return 0.2126 * R + 0.7152 * G + 0.0722 * B


def _contrast(a: str, b: str) -> float:
    l1, l2 = _rel_luminance(a), _rel_luminance(b)
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


def _blend(fg: str, bg: str, a: float) -> str:
    def ch(h):
        h = h.lstrip("#")
        return [int(h[i:i + 2], 16) for i in (0, 2, 4)]

    f, b = ch(fg), ch(bg)
    out = [round(f[i] * a + b[i] * (1 - a)) for i in range(3)]
    return "#%02X%02X%02X" % tuple(out)


class GazetteerSchemaAndSize(unittest.TestCase):
    def setUp(self):
        self.raw = (ROOT / "data" / "wind-labels.json").read_bytes()
        self.doc = json.loads(self.raw)

    def test_size_under_cap_and_not_empty(self):
        self.assertLessEqual(len(self.raw), GAZETTEER_CAP, len(self.raw))
        self.assertGreater(len(self.raw), 2000)

    def test_schema_and_required_places(self):
        self.assertEqual(self.doc.get("v"), 1)
        places = self.doc["places"]
        sources = self.doc["sources"]
        self.assertIsInstance(sources, dict)
        self.assertTrue(sources)
        names = [p["n"] for p in places]
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(set(names), REQUIRED_PLACES)
        for p in places:
            for k in ("n", "k", "la", "lo", "z0", "z1", "p", "s"):
                self.assertIn(k, p, p)
            self.assertIn(p["s"], sources, p)
            self.assertGreaterEqual(p["la"], 33.5)
            self.assertLessEqual(p["la"], 37.0)
            self.assertGreaterEqual(p["lo"], -79.0)
            self.assertLessEqual(p["lo"], -74.5)
            self.assertLessEqual(p["z0"], p["z1"])
            self.assertGreaterEqual(p["p"], 1)

    def test_region_anchors_are_not_the_misleading_wikipedia_points(self):
        by = {p["n"]: p for p in self.doc["places"]}
        # Wikipedia Atlantic Ocean is (0, -25); must be in-extent.
        self.assertGreater(by["Atlantic Ocean"]["la"], 33)
        self.assertLess(by["Atlantic Ocean"]["lo"], -74)
        # Wikipedia Outer Banks coincides with Cape Hatteras; mid-chain instead.
        hat = by["Cape Hatteras"]
        obx = by["Outer Banks"]
        self.assertGreater(abs(obx["la"] - hat["la"]) + abs(obx["lo"] - hat["lo"]), 0.15)
        # Crystal Coast on / along Bogue Banks / Carteret coast, not a town mid-sound.
        cc = by["Crystal Coast"]
        self.assertTrue(34.62 <= cc["la"] <= 34.78)
        self.assertTrue(-77.15 <= cc["lo"] <= -76.65)


class AssetBudgetB4(unittest.TestCase):
    def test_approved_ceilings_and_gazetteer_separate(self):
        own = sum((ROOT / f).stat().st_size for f in OWN_FILES)
        css = (ROOT / "wind.css").stat().st_size
        gaz = (ROOT / "data" / "wind-labels.json").stat().st_size
        self.assertLess(own, OWN_CAP, own)
        self.assertLess(css, CSS_CAP, css)
        self.assertLessEqual(gaz, GAZETTEER_CAP, gaz)
        # Gazetteer is not counted in the five-file own-asset cap.
        self.assertLess(own + gaz, OWN_CAP + GAZETTEER_CAP)

    def test_public_preview_css_identical_engine_untouched(self):
        self.assertEqual((ROOT / "wind.css").read_bytes(), (ROOT / "preview" / "wind" / "wind.css").read_bytes())
        self.assertEqual(
            hashlib.sha256((ROOT / "wind-lab.js").read_bytes()).hexdigest(),
            "aca358bd4ee33fdef19da2fd6aa907f690c2b080803b11d6cb86dac99c371558",
        )
        js = (ROOT / "wind-viewer.js").read_text()
        self.assertNotIn("requestAnimationFrame", js)
        self.assertIn("maxParticles: phone ? 1100 : 2200", js)
        self.assertIn("dprCap: phone ? 1.5 : 2", js)


class ClockBrandingAttrib(unittest.TestCase):
    html = (ROOT / "wind.html").read_text()
    css = (ROOT / "wind.css").read_text()
    js = (ROOT / "wind-viewer.js").read_text()

    def test_clock_lives_in_the_instrument_strip(self):
        top = self.html.split('<header class="w-top">', 1)[1].split("</header>", 1)[0]
        strip = self.html.split('class="w-strip"', 1)[1].split("</section>", 1)[0]
        self.assertNotIn('id="w-clock"', top)
        self.assertIn('id="w-clock"', strip)
        self.assertIn("w-clock", strip)
        self.assertIn(">Now<", strip)

    def test_wordmark_and_monogram_on_mobile(self):
        self.assertIn("The Coastal Brief", self.html)
        self.assertIn('class="w-mono"', self.html)
        self.assertIn("/branding/favicon.svg", self.html)
        self.assertNotIn(".w-brand-a{display:none}", self.css.replace(" ", ""))

    def test_compact_attrib_and_full_disclosures_in_i_panel(self):
        self.assertIn(
            '<a id="w-src" href="https://www.nco.ncep.noaa.gov/pmb/products/gfs/" rel="noopener">NOAA NCEP GFS</a> <span id="w-src-res">0.25° model forecast</span>',
            self.html,
        )
        self.assertIn("not endorsed by the Census Bureau", self.html)
        self.assertIn("U.S. Census Bureau, 2025 cartographic boundary file, 1:500,000", self.html)
        self.assertIn("These data were collected and made freely available by NOAA/NDBC", self.html)
        self.assertIn("NOAA / NOS / CO-OPS", self.html)
        about = self.html.split('class="w-about-body"', 1)[1]
        self.assertIn("check the National Weather Service", about)
        self.assertIn('id="w-disc"', self.html)
        attrib = self.html.split('class="w-attrib"', 1)[1].split("</p>", 1)[0]
        self.assertIn("not endorsed", attrib)


class StationsDefaultAndTypes(unittest.TestCase):
    html = (ROOT / "wind.html").read_text()
    css = (ROOT / "wind.css").read_text()
    js = (ROOT / "wind-viewer.js").read_text()

    def test_stations_default_off_and_persist(self):
        self.assertIn('aria-pressed="false"', self.html)
        self.assertIn('coastalBrief.windStations', self.js)
        self.assertIn("localStorage.getItem(STA_STORE)", self.js)
        self.assertIn('localStorage.setItem(STA_STORE, staOn ? "on" : "off")', self.js)
        self.assertIn("/[?&]stations=1\\b/.test(q)", self.js)
        # First-time path is off unless storage or query says on.
        self.assertIn("let staOn = false", self.js)

    def test_legend_and_verified_type_table(self):
        self.assertIn("STA_KIND", self.js)
        m = re.search(r"const STA_KIND = \{([^}]+)\}", self.js)
        self.assertIsNotNone(m)
        table = {}
        for k, v in re.findall(r"([A-Za-z0-9]+):\"(buoy|pier|air)\"", m.group(1)):
            table[k] = v
        self.assertEqual(table, NDBC_KIND)
        self.assertIn('s.type === "nws" ? "air"', self.js)
        self.assertIn("w-sta-leg", self.html)
        self.assertIn("Buoy", self.html)
        self.assertIn("Coastal", self.html)
        self.assertIn("Airport", self.html)
        self.assertIn("C-MAN", self.html)

    def test_compass_single_needle_default_on(self):
        self.assertIn("coastalBrief.windCompass", self.js)
        self.assertIn("let cmpOn = true", self.js)
        self.assertIn('localStorage.getItem(CMP_STORE) === "off"', self.js)
        self.assertIn('st.mode === "observed" ? "OBSERVED" : "FORECAST"', self.js)
        self.assertIn('d.textContent = "FROM "', self.js)
        self.assertIn('"°T"', self.js)
        self.assertIn("id=\"w-cmp-needle\"", self.html)
        self.assertEqual(self.html.count('id="w-cmp-needle"'), 1)
        self.assertIn("function cmpState", self.js)
        # One source of direction: observed wins only when a station is selected and has dirDeg.
        fn = self.js.split("function cmpState", 1)[1].split("function syncCmp", 1)[0]
        self.assertIn('mode: "observed"', fn)
        self.assertIn('mode: "forecast"', fn)
        self.assertIn("staSel", fn)


class BrassContrast(unittest.TestCase):
    css = (ROOT / "wind.css").read_text()

    def _var(self, block: str, name: str) -> str:
        m = re.search(r"--" + re.escape(name) + r":\s*(#[0-9A-Fa-f]{6})", block)
        self.assertIsNotNone(m, name + " in " + block[:80])
        return m.group(1)

    def test_gust_meets_wcag_aa_in_both_themes(self):
        root = self.css.split(":root {", 1)[1].split("html[data-theme", 1)[0]
        dark = self.css.split('html[data-theme="dark"] {', 1)[1].split("html:not", 1)[0]
        light_gust = self._var(root, "gust")
        dark_gust = self._var(dark, "gust")
        # Viewer light overrides.
        self.assertIn("--surf: #F8FBFC", self.css)
        self.assertIn("--surf-2: #E6EEF2", self.css)
        light_surf, light_surf2, light_map = "#F8FBFC", "#E6EEF2", "#CDDCE6"
        dark_surf, dark_surf2, dark_map = self._var(dark, "surf"), self._var(dark, "surf-2"), self._var(dark, "map-bg")
        # --glass is 0.9 over the map in both themes (white / #102D46-ish).
        light_glass = _blend("#FFFFFF", light_map, 0.9)
        dark_glass = _blend("#102D46", dark_map, 0.9)
        cases = {
            "light gust on surf": _contrast(light_gust, light_surf),
            "light gust on surf-2": _contrast(light_gust, light_surf2),
            "light gust on glass": _contrast(light_gust, light_glass),
            "dark gust on surf": _contrast(dark_gust, dark_surf),
            "dark gust on surf-2": _contrast(dark_gust, dark_surf2),
            "dark gust on glass": _contrast(dark_gust, dark_glass),
        }
        failed = {k: round(v, 2) for k, v in cases.items() if v < 4.5}
        self.assertFalse(failed, failed)
        self.assertIn(".w-gust", self.css)
        self.assertIn("color: var(--gust)", self.css)


class LabelsRoute(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import server
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.base = "http://127.0.0.1:%d" % cls.httpd.server_address[1]
        time.sleep(0.05)

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def test_labels_json_is_cached_and_matches_file(self):
        import urllib.request
        req = urllib.request.Request(self.base + "/wind/labels.json")
        with urllib.request.urlopen(req, timeout=5) as r:
            body = r.read()
            cache = r.headers.get("Cache-Control", "")
            ctype = r.headers.get("Content-Type", "")
        self.assertEqual(body, (ROOT / "data" / "wind-labels.json").read_bytes())
        self.assertIn("max-age=86400", cache)
        self.assertIn("json", ctype)


def _chrome():
    chrome = Path("/usr/bin/google-chrome")
    if not chrome.exists():
        return None
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None
    return chrome


class LiveLayoutAndBehavior(unittest.TestCase):
    """Playwright checks for clock, persistence, compass, collisions, truncation."""

    VIEWPORTS = (
        (375, 667, "375"),
        (390, 844, "390"),
        (430, 932, "430"),
        (375, 500, "375-short"),
        (844, 390, "landscape"),
    )

    @classmethod
    def setUpClass(cls):
        import server
        import windgrid
        fix = ROOT / "tests/fixtures/gfs_uv10m_ncbox.grb2"
        if not fix.exists():
            cls.grid = None
        else:
            windgrid._cache.clear()
            with mock.patch.object(windgrid, "_fetch", return_value=fix.read_bytes()), \
                 mock.patch.object(windgrid.time, "time", return_value=1795122000.0):
                cls.grid = dict(windgrid.latest_grid(ahead=0))
            cls.grid["ok"] = True
            cls.grid["run"] = "2026-11-26T18:00Z"
            cls.grid["valid"] = "2026-11-27T02:00Z"
            cls.grid["forecastHour"] = 8
        cls._ads = (ROOT / "data" / "ads.json").read_bytes()
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.base = "http://127.0.0.1:%d" % cls.httpd.server_address[1]
        cls.pack = {
            "ok": True, "kind": "observed", "generatedAt": "2026-11-27T02:00:00Z",
            "stations": [{
                "id": "CLKN7", "name": "Cape Lookout", "type": "ndbc",
                "lat": 34.622, "lon": -76.525, "source": "NOAA NDBC",
                "observedAt": "2026-11-27T01:50:00Z", "ageMin": 10, "status": "fresh",
                "staleAfterMin": 75,
                "wind": {"speedKt": 20, "gustKt": 31, "dirDeg": 240, "dirCompass": "WSW"},
            }],
        }

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        ads = ROOT / "data" / "ads.json"
        if ads.exists() and ads.read_bytes() != cls._ads:
            ads.write_bytes(cls._ads)

    def _browser(self):
        chrome = _chrome()
        if not chrome:
            self.skipTest("playwright or chrome missing")
        from playwright.sync_api import sync_playwright
        pw = sync_playwright().start()
        browser = pw.chromium.launch(
            executable_path=str(chrome),
            args=["--headless=new", "--no-sandbox", "--disable-gpu"],
        )
        return pw, browser

    def _route(self, page):
        if self.grid:
            page.route("**/api/wind-grid**", lambda r: r.fulfill(
                status=200, content_type="application/json", body=json.dumps(self.grid)))
        page.route("**/api/wind-stations**", lambda r: r.fulfill(
            status=200, content_type="application/json", body=json.dumps(self.pack)))

    def test_no_truncation_clock_in_strip_wordmark_visible(self):
        pw, browser = self._browser()
        problems = []
        try:
            for w, h, tag in self.VIEWPORTS:
                page = browser.new_page(viewport={"width": w, "height": h}, device_scale_factor=2)
                self._route(page)
                page.goto(self.base + "/wind?theme=light", wait_until="domcontentloaded")
                page.wait_for_timeout(400)
                metrics = page.evaluate(
                    """() => {
                      const sels = [".w-brand-a", ".w-brand-b", "#w-badge", "#w-sta .w-lbl", ".w-clock time"];
                      const out = {doc:{sw:document.documentElement.scrollWidth, iw:window.innerWidth}, labels:{}, clockInStrip:false, mono:false, wordmark:""};
                      const clock = document.getElementById("w-clock");
                      out.clockInStrip = !!(clock && clock.closest(".w-strip") && !clock.closest(".w-top"));
                      const mono = document.querySelector(".w-mono");
                      out.mono = !!(mono && mono.getBoundingClientRect().width >= 16);
                      for (const sel of sels) {
                        const el = document.querySelector(sel);
                        if (!el) { out.labels[sel] = {missing:true}; continue; }
                        const cs = getComputedStyle(el);
                        out.labels[sel] = {
                          text: (el.textContent||"").trim(),
                          sw: el.scrollWidth, cw: el.clientWidth,
                          display: cs.display, visibility: cs.visibility
                        };
                      }
                      const sta = document.getElementById("w-sta");
                      const r = sta ? sta.getBoundingClientRect() : null;
                      out.sta = r ? {w:r.width,h:r.height} : null;
                      const brandA = document.querySelector(".w-brand-a");
                      out.wordmark = brandA ? brandA.textContent.trim() : "";
                      return out;
                    }"""
                )
                page.close()
                if metrics["doc"]["sw"] > metrics["doc"]["iw"] + 1:
                    problems.append("%s scrollWidth %s > innerWidth %s" % (tag, metrics["doc"]["sw"], metrics["doc"]["iw"]))
                if not metrics.get("clockInStrip"):
                    problems.append("%s clock not in strip" % tag)
                if not metrics.get("mono"):
                    problems.append("%s monogram missing or too small" % tag)
                if metrics.get("wordmark") != "The Coastal Brief":
                    problems.append("%s wordmark %r" % (tag, metrics.get("wordmark")))
                for sel, m in metrics["labels"].items():
                    if m.get("missing") or m.get("display") == "none":
                        problems.append("%s missing/hidden %s" % (tag, sel))
                    elif m.get("sw", 0) > m.get("cw", 0) + 1:
                        problems.append("%s %s truncated sw=%s cw=%s text=%r" % (tag, sel, m.get("sw"), m.get("cw"), m.get("text")))
                if not metrics.get("sta") or metrics["sta"]["w"] < 43.5 or metrics["sta"]["h"] < 43.5:
                    problems.append("%s stations toggle not 44px: %s" % (tag, metrics.get("sta")))
        finally:
            browser.close()
            pw.stop()
        self.assertFalse(problems, "layout:\n  " + "\n  ".join(problems))

    def test_stations_persistence_and_query(self):
        pw, browser = self._browser()
        try:
            page = browser.new_page(viewport={"width": 390, "height": 844})
            self._route(page)
            page.goto(self.base + "/wind?theme=light", wait_until="domcontentloaded")
            page.wait_for_function("() => window.__windView && window.__windView.stations", timeout=20000)
            on = page.evaluate("() => window.__windView.stations.on()")
            self.assertFalse(on)
            stored = page.evaluate("() => localStorage.getItem('coastalBrief.windStations')")
            # Boot may persist the default as "off"; either null or off is a first-time off.
            self.assertIn(stored, (None, "off"))
            page.evaluate("() => window.__windView.stations.set(true)")
            self.assertEqual(page.evaluate("() => localStorage.getItem('coastalBrief.windStations')"), "on")
            page.reload(wait_until="domcontentloaded")
            page.wait_for_function("() => window.__windView && window.__windView.stations", timeout=20000)
            self.assertTrue(page.evaluate("() => window.__windView.stations.on()"))
            page.evaluate("() => window.__windView.stations.set(false)")
            page.reload(wait_until="domcontentloaded")
            page.wait_for_function("() => window.__windView && window.__windView.stations", timeout=20000)
            self.assertFalse(page.evaluate("() => window.__windView.stations.on()"))
            page.goto(self.base + "/wind?theme=light&stations=1", wait_until="domcontentloaded")
            page.wait_for_function("() => window.__windView && window.__windView.stations", timeout=20000)
            self.assertTrue(page.evaluate("() => window.__windView.stations.on()"))
        finally:
            browser.close()
            pw.stop()

    def test_compass_observed_vs_forecast_single_needle(self):
        pw, browser = self._browser()
        try:
            page = browser.new_page(viewport={"width": 390, "height": 844})
            self._route(page)
            page.goto(self.base + "/wind?theme=light&stations=1", wait_until="domcontentloaded")
            page.wait_for_function("() => window.__windView && window.__windView.grid && window.__windView.grid()", timeout=20000)
            page.wait_for_function("() => window.__windView.stations && window.__windView.stations.marks().length > 0", timeout=15000)
            # Map click: forecast compass, no station.
            page.evaluate("""() => {
              const ll = window.__windView.map.getCenter();
              window.__windView.readAt(ll, null, null);
            }""")
            page.wait_for_timeout(200)
            st = page.evaluate("""() => {
              const c = window.__windView.compass();
              const el = document.getElementById('w-cmp-needle');
              const tr = (el && el.getAttribute('transform')) || '';
              const m = /rotate\(\s*([-0-9.]+)/.exec(tr);
              return {on:c.on, mode:c.mode, dir:c.dirDeg, needles: document.querySelectorAll('.w-cmp-needle').length,
                label: (document.getElementById('w-cmp-k')||{}).textContent,
                text: (document.getElementById('w-cmp-d')||{}).textContent,
                hidden: document.getElementById('w-cmp').hidden,
                rot: m ? Number(m[1]) : null, dataDir: el && el.getAttribute('data-dir')};
            }""")
            self.assertTrue(st["on"])
            self.assertEqual(st["needles"], 1)
            self.assertEqual(st["mode"], "forecast")
            self.assertEqual(st["label"], "FORECAST")
            self.assertFalse(st["hidden"])
            self.assertIsNotNone(st["dir"])
            self.assertAlmostEqual(st["rot"], st["dir"], places=4)
            self.assertEqual(st["text"], "FROM %d°T" % round(st["dir"]))
            # Select Cape Lookout: observed compass, same dir as the reading (240).
            page.evaluate("""() => {
              const s = window.__windView.stations.pack().stations.find(x => x.id === 'CLKN7');
              window.__windView.readAt({lat:s.lat, lng:s.lon}, null, s);
            }""")
            page.wait_for_timeout(200)
            st = page.evaluate("""() => {
              const c = window.__windView.compass();
              const el = document.getElementById('w-cmp-needle');
              const tr = (el && el.getAttribute('transform')) || '';
              const m = /rotate\(\s*([-0-9.]+)/.exec(tr);
              return {on:c.on, mode:c.mode, dir:c.dirDeg, needles: document.querySelectorAll('.w-cmp-needle').length,
                label: (document.getElementById('w-cmp-k')||{}).textContent,
                text: (document.getElementById('w-cmp-d')||{}).textContent,
                rot: m ? Number(m[1]) : null, dataDir: el && el.getAttribute('data-dir')};
            }""")
            self.assertEqual(st["mode"], "observed")
            self.assertEqual(st["label"], "OBSERVED")
            self.assertEqual(st["needles"], 1)
            self.assertEqual(round(st["dir"]), 240)
            self.assertAlmostEqual(st["rot"], 240, places=4)
            self.assertAlmostEqual(st["rot"], st["dir"], places=4)
            self.assertEqual(st["text"], "FROM 240°T")
        finally:
            browser.close()
            pw.stop()

    def test_panel_side_by_side_except_when_cramped(self):
        pw, browser = self._browser()
        # Side-by-side at 390, 430, and landscape; stack at 375 and short 375.
        cases = (
            (390, 844, False, "390"),
            (430, 932, False, "430"),
            (844, 390, False, "landscape"),
            (375, 667, True, "375"),
            (375, 500, True, "375-short"),
        )
        problems = []
        try:
            for w, h, want_stack, tag in cases:
                page = browser.new_page(viewport={"width": w, "height": h})
                self._route(page)
                page.goto(self.base + "/wind?theme=light&stations=1", wait_until="domcontentloaded")
                page.wait_for_function("() => window.__windView && window.__windView.grid && window.__windView.grid()", timeout=20000)
                page.wait_for_function("() => window.__windView.stations && window.__windView.stations.marks().length > 0", timeout=15000)
                page.evaluate("""() => {
                  const s = window.__windView.stations.pack().stations.find(x => x.id === 'CLKN7');
                  window.__windView.readAt({lat:s.lat, lng:s.lon}, null, s);
                }""")
                page.wait_for_timeout(200)
                # Long name must remain readable in the painted observed block.
                page.evaluate("""() => {
                  const k = document.querySelector('.w-obs .w-k');
                  if (k) k.textContent = "OBSERVED · Wrightsville Beach, Johnnie Mercer's Pier  8658163";
                  const sub = document.querySelector('.w-obs .w-sub');
                  if (sub) sub.textContent = "Stale — last report Thu 9:50 PM ET";
                }""")
                geo = page.evaluate("""() => {
                  const body = document.getElementById('w-read-body');
                  const fcst = document.querySelector('.w-fcst');
                  const obs = document.querySelector('.w-obs');
                  const gust = document.querySelector('.w-gust');
                  const strong = obs && obs.querySelector('strong');
                  const cs = body ? getComputedStyle(body).gridTemplateColumns : '';
                  const fr = fcst ? fcst.getBoundingClientRect() : null;
                  const or_ = obs ? obs.getBoundingClientRect() : null;
                  const k = document.querySelector('.w-obs .w-k');
                  return {
                    cols: cs, colCount: cs.trim() ? cs.trim().split(/\s+/).filter(Boolean).length : 0,
                    fcst: fr && {t:fr.top,b:fr.bottom,l:fr.left,r:fr.right,w:fr.width,h:fr.height},
                    obs: or_ && {t:or_.top,b:or_.bottom,l:or_.left,r:or_.right,w:or_.width,h:or_.height},
                    k: k && {text:k.textContent, sw:k.scrollWidth, cw:k.clientWidth, ch:k.clientHeight, sh:k.scrollHeight},
                    gustOn: !!(gust && getComputedStyle(gust).color),
                    strongPx: strong ? parseFloat(getComputedStyle(strong).fontSize) : 0
                  };
                }""")
                page.close()
                stacked = False
                if geo.get("fcst") and geo.get("obs"):
                    stacked = geo["obs"]["t"] >= geo["fcst"]["b"] - 2
                    side = geo["obs"]["l"] >= geo["fcst"]["r"] - 2 and abs(geo["obs"]["t"] - geo["fcst"]["t"]) < 24
                else:
                    problems.append("%s missing fcst/obs boxes: %s" % (tag, geo))
                    continue
                if want_stack and not stacked:
                    problems.append("%s expected stack, cols=%s fcst=%s obs=%s" % (tag, geo.get("cols"), geo.get("fcst"), geo.get("obs")))
                if not want_stack and not side:
                    problems.append("%s expected side-by-side, cols=%s fcst=%s obs=%s" % (tag, geo.get("cols"), geo.get("fcst"), geo.get("obs")))
                k = geo.get("k") or {}
                # Wrapped text is taller than one line; clipped text has scrollWidth >> clientWidth with no height growth.
                if k.get("ch", 0) < 8:
                    problems.append("%s long name not visible: %s" % (tag, k))
                if k.get("sw", 0) > k.get("cw", 0) + 2 and k.get("sh", 0) <= k.get("ch", 0) + 1:
                    problems.append("%s long name clipped: %s" % (tag, k))
                if not geo.get("gustOn"):
                    problems.append("%s gust accent missing" % tag)
                if geo.get("strongPx", 0) < 14:
                    problems.append("%s sustained speed too small: %s" % (tag, geo.get("strongPx")))
        finally:
            browser.close()
            pw.stop()
        self.assertFalse(problems, "panel layout:\n  " + "\n  ".join(problems))

    def test_labels_do_not_collide_with_chrome_or_selection(self):
        pw, browser = self._browser()
        try:
            page = browser.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2)
            self._route(page)
            page.goto(self.base + "/wind?theme=light&stations=1", wait_until="domcontentloaded")
            page.wait_for_function("() => window.__windView && window.__windView.labels && window.__windView.labels() && window.__windView.labels().data", timeout=20000)
            page.wait_for_timeout(500)
            # Select CLKN7 so the selected marker is reserved.
            page.evaluate("""() => {
              const s = window.__windView.stations.pack().stations[0];
              if (s) window.__windView.readAt({lat:s.lat, lng:s.lon}, null, s);
            }""")
            page.wait_for_timeout(300)
            hits = page.evaluate(
                """() => {
                  const stage = document.getElementById('w-stage').getBoundingClientRect();
                  function box(el, pad){
                    const r = el.getBoundingClientRect();
                    return {l:r.left-stage.left-pad, t:r.top-stage.top-pad, r:r.right-stage.left+pad, b:r.bottom-stage.top+pad, name: el.id || el.className};
                  }
                  function hit(a,b){ return a.l < b.r && a.r > b.l && a.t < b.b && a.b > b.t; }
                  const reserved = [];
                  ['.w-legend','#w-sta-leg','.w-about summary','#w-read','.w-attrib','#w-status','.w-mk.on'].forEach(sel => {
                    document.querySelectorAll(sel).forEach(el => {
                      if (el.hidden || el.hasAttribute('hidden')) return;
                      const r = el.getBoundingClientRect();
                      if (r.width < 2 || r.height < 2) return;
                      reserved.push(box(el, 2));
                    });
                  });
                  const labels = [];
                  document.querySelectorAll('.w-lab').forEach(el => {
                    if (el.style.visibility === 'hidden') return;
                    labels.push({n: el.textContent, b: box(el, 0)});
                  });
                  const collisions = [];
                  labels.forEach(L => {
                    reserved.forEach(R => { if (hit(L.b, R)) collisions.push(L.n + ' x ' + R.name); });
                  });
                  // labels vs each other
                  for (let i=0;i<labels.length;i++) for (let j=i+1;j<labels.length;j++) {
                    if (hit(labels[i].b, labels[j].b)) collisions.push(labels[i].n + ' x ' + labels[j].n);
                  }
                  return {n: labels.length, names: labels.map(x=>x.n), collisions};
                }"""
            )
            self.assertGreater(hits["n"], 0, hits)
            self.assertFalse(hits["collisions"], hits)
        finally:
            browser.close()
            pw.stop()


if __name__ == "__main__":
    unittest.main()
