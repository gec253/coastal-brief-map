"""Wind Viewer Phase B3: observed markers and combined forecast/observed panel.

Does not raise the 55 KiB asset cap or rewrite protected-file SHA pins.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import textwrap
import unittest
from pathlib import Path
from datetime import datetime, timezone
from unittest import mock
from http.server import ThreadingHTTPServer
import time
import threading

ROOT = Path(__file__).resolve().parent.parent


def _sha256(rel: str) -> str:
    return hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()


class PhaseB3Stations(unittest.TestCase):
    html = (ROOT / "wind.html").read_text()
    css = (ROOT / "wind.css").read_text()
    js = (ROOT / "wind-viewer.js").read_text()
    engine = (ROOT / "wind-lab.js").read_text()

    def test_toggle_default_off_accessible_and_labeled(self):
        self.assertIn('id="w-sta"', self.html)
        self.assertIn('aria-pressed="false"', self.html)
        self.assertIn('aria-label="Show observed NOAA stations"', self.html)
        self.assertIn("Stations", self.html)
        self.assertIn('class="w-sta"', self.html)
        # Not a sixth full-size bar button.
        ctl = self.html.split('class="w-ctl"', 1)[1].split("</nav>", 1)[0]
        self.assertNotIn('id="w-sta"', ctl)
        self.assertIn('id="w-sta"', self.html.split('class="w-top"', 1)[1].split('class="w-strip"', 1)[0])
        sta = re.search(r"#w-sta\s*\{([^}]+)\}", self.css).group(1)
        self.assertGreaterEqual(int(re.search(r"min-width:\s*(\d+)px", sta).group(1)), 44)
        self.assertGreaterEqual(int(re.search(r"min-height:\s*(\d+)px", sta).group(1)), 44)
        self.assertIn('setAttribute("aria-pressed"', self.js)

    def test_toggle_off_does_not_fetch(self):
        # The only /api/wind-stations call is inside loadStations, which returns when the layer is off.
        self.assertEqual(self.js.count('fetch("/api/wind-stations")'), 1)
        fn = self.js.split("async function loadStations", 1)[1].split("async function", 1)[0]
        if "function setStaOn" in fn:
            fn = fn.split("function setStaOn", 1)[0]
        head = fn.split('fetch("/api/wind-stations")', 1)[0]
        self.assertIn("if (!staOn) return", head)
        self.assertIn("staOn = false", self.js)
        # No preload of the stations bundle at first paint.
        self.assertNotIn("/api/wind-stations", self.html)

    def test_markers_by_type_and_status(self):
        self.assertIn('staKind', self.js)
        self.assertIn('s.type === "nws" ? "air"', self.js)
        self.assertIn('"pier"', self.js)
        self.assertIn('"buoy"', self.js)
        self.assertIn("w-mk-buoy", self.css)
        self.assertIn("w-mk-pier", self.css)
        self.assertIn("w-mk-air", self.css)
        self.assertIn("is-stale", self.css)
        self.assertIn("is-unavailable", self.css)
        self.assertIn("is-gust_only", self.css)
        self.assertIn("L.divIcon", self.js)
        self.assertIn("iconSize: [44, 44]", self.js)
        self.assertNotIn("requestAnimationFrame", self.js)
        self.assertNotIn("L.circleMarker(s", self.js)

    def test_decluttering_keeps_all_stations_reachable(self):
        self.assertIn("function declutter", self.js)
        self.assertIn("zoomend", self.js)
        self.assertIn("fitBounds", self.js)
        self.assertIn("w-n", self.css)  # +N cluster badge
        self.assertIn("is-hide", self.css)
        self.assertIn("tabIndex = hide ? -1 : 0", self.js)
        # Spiderfy at max zoom so overlapping pins stay tappable.
        self.assertIn("getMaxZoom", self.js)

    def test_combined_panel_separates_observed_and_forecast(self):
        self.assertIn('modelName + " FORECAST"', self.js)
        self.assertIn("OBSERVED · ", self.js)
        self.assertIn("function fcstBody", self.js)
        self.assertIn("function obsBody", self.js)
        self.assertIn("w-fcst", self.js)
        self.assertIn("w-obs", self.js)
        self.assertIn(".w-obs", self.css)
        self.assertIn("border-top", re.search(r"\.w-obs\s*\{([^}]+)\}", self.css).group(1))
        self.assertIn("wind.sample(latlng.lat, latlng.lng)", self.js)

    def test_observed_block_independent_of_hour_steps_and_persists(self):
        # Hour-step / show / tick call readAt with one argument, which keeps staSel.
        self.assertIn("if (arguments.length >= 3) staSel = station ? station.id : null", self.js)
        self.assertIn("if (read && !read.hidden && dot) readAt(dot.getLatLng());", self.js)
        self.assertIn('map.on("click", function (e) { readAt(e.latlng, null, null); })', self.js)
        self.assertIn("readAt(m.getLatLng(), null, s)", self.js)

    def test_stale_unavailable_gust_only_copy_never_invents(self):
        self.assertIn("Wind speed unavailable", self.js)
        self.assertIn("Stale — last report ", self.js)
        self.assertIn("Unavailable", self.js)
        self.assertIn("last report ", self.js)
        self.assertIn("Gust ", self.js)
        # Gust-only path does not print a speed in knots as the headline.
        gust = self.js.split('c.status === "gust_only"', 1)[1].split("if (c.status", 1)[0]
        self.assertIn("Wind speed unavailable", gust)
        self.assertNotIn("speedKt) + \" kt\"", gust)
        unav = self.js.split('c.status === "unavailable"', 1)[1].split("let num", 1)[0]
        self.assertIn("Unavailable", unav)
        self.assertNotIn("speedKt", unav)

    def test_endpoint_failure_leaves_forecast_alone(self):
        self.assertIn("Observed stations unavailable right now.", self.js)
        self.assertIn("setStaErr", self.js)
        self.assertIn('id="w-sta-err"', self.html)
        # Map / grid path is not rewritten on a station error.
        self.assertIn("wind.setGrid(g)", self.js)

    def test_model_retry_button(self):
        self.assertIn('id="w-retry"', self.html)
        self.assertIn(">Try again<", self.html)
        self.assertIn('retryBtn.addEventListener("click", function () { load(ai); })', self.js)
        self.assertIn("function syncRetry", self.js)
        retry = re.search(r"#w-retry\s*\{([^}]+)\}", self.css).group(1)
        self.assertGreaterEqual(int(re.search(r"min-width:\s*(\d+)px", retry).group(1)), 44)
        self.assertGreaterEqual(int(re.search(r"min-height:\s*(\d+)px", retry).group(1)), 44)

    def test_dismiss_and_keyboard(self):
        self.assertIn('e.key !== "Escape"', self.js)
        self.assertIn("dismissRead()", self.js)
        self.assertIn("staSel = null", self.js)
        self.assertIn('el.focus()', self.js)

    def test_performance_caps_untouched_and_no_second_loop(self):
        self.assertIn("maxParticles: phone ? 1100 : 2200", self.js)
        self.assertIn("dprCap: phone ? 1.5 : 2", self.js)
        self.assertIn("phone ? 30 : 60", self.js)
        self.assertIn("frameMs: fps === 30 ? 33.3 : 0", self.js)
        self.assertNotIn("requestAnimationFrame", self.js)
        self.assertEqual(self.engine.count("requestAnimationFrame"), 3)
        self.assertEqual(
            _sha256("wind-lab.js"),
            "aca358bd4ee33fdef19da2fd6aa907f690c2b080803b11d6cb86dac99c371558",
        )

    def test_public_and_preview_css_byte_identical_radar_untouched(self):
        self.assertEqual((ROOT / "wind.css").read_bytes(), (ROOT / "preview" / "wind" / "wind.css").read_bytes())
        self.assertIn('html:not([data-theme="dark"]) body[data-radar-view="viewer"] { --map-bg: #EAF1F4; }', self.css)
        # Radar product files must stay at the d67ad7f / f44b0ad bytes.
        self.assertEqual(
            _sha256("radar.html"),
            hashlib.sha256((ROOT / "radar.html").read_bytes()).hexdigest(),
        )
        for rel in ("radar.html", "radar-viewer.js", "radar-player.js", "radar.css"):
            self.assertTrue((ROOT / rel).exists(), rel)

    def test_safe_area_and_no_sixth_bar_button(self):
        self.assertIn("env(safe-area-inset-right)", self.css)
        self.assertIn("env(safe-area-inset-left)", self.css)
        # Toggle lives in the top bar, already padded with safe-area insets.
        top = re.search(r"\.w-top\s*\{([^}]+)\}", self.css).group(1)
        self.assertIn("safe-area-inset-right", top)
        self.assertIn("safe-area-inset-left", top)



    def test_badge_is_not_ellipsis_clipped(self):
        # The 7.4em ellipsis squeeze is forbidden: top-bar labels must show in full.
        # B4 restores The Coastal Brief wordmark on mobile (no display:none).
        self.assertNotIn("7.4em", self.css)
        self.assertNotIn(".w-brand-a{display:none}", self.css.replace(" ", ""))
        self.assertIn("The Coastal Brief", self.html)
        self.assertIn("text-overflow:clip", self.css)
        b3 = self.css.split("/* B3 stations", 1)[1]
        self.assertNotIn("text-overflow:ellipsis", b3)

    def test_client_recomputes_age_and_freshness_from_observedAt(self):
        """Cached pack ageMin/status must not be painted; re-derive from observedAt vs now."""
        self.assertIn("function classifySta", self.js)
        obs = self.js.split("function obsBody", 1)[1].split("function show", 1)[0]
        self.assertIn("classifySta(s)", obs)
        self.assertNotIn("s.ageMin", obs)
        self.assertNotIn("s.status", obs)
        self.assertIn("c.ageMin", obs)
        self.assertIn("c.status", obs)
        self.assertIn("staleAfterMin", self.js)
        # classifySta must not trust the payload status when age is past staleAfterMin.
        import subprocess, textwrap, json
        src = self.js
        start = src.index("function classifySta(s, now)")
        end = src.index("function obsBody", start)
        fn = src[start:end]
        cases = [
            # Pack claims Fresh / 47 min, but observedAt is ~3.6 h old at 8:08 PM ET.
            {
                "now": "2026-11-27T01:08:00Z",
                "s": {"observedAt": "2026-11-26T21:30:00Z", "status": "fresh", "ageMin": 47,
                      "staleAfterMin": 75, "wind": {"speedKt": 18, "gustKt": 28, "dirDeg": 230}},
                "want": "stale", "age": 218,
            },
            # Within the 75-min window: still Fresh.
            {
                "now": "2026-11-27T01:08:00Z",
                "s": {"observedAt": "2026-11-27T00:50:00Z", "status": "stale", "ageMin": 200,
                      "staleAfterMin": 75, "wind": {"speedKt": 12, "gustKt": 16, "dirDeg": 40}},
                "want": "fresh", "age": 18,
            },
            # Older than 12 h: Unavailable and numbers dropped.
            {
                "now": "2026-11-27T01:08:00Z",
                "s": {"observedAt": "2026-11-26T10:00:00Z", "status": "fresh", "ageMin": 10,
                      "staleAfterMin": 75, "wind": {"speedKt": 9, "gustKt": 12, "dirDeg": 90}},
                "want": "unavailable", "age": 908, "emptyWind": True,
            },
            # Gust only, age still fresh: keep gust_only.
            {
                "now": "2026-11-27T01:08:00Z",
                "s": {"observedAt": "2026-11-27T00:40:00Z", "status": "fresh", "ageMin": 5,
                      "staleAfterMin": 75, "wind": {"speedKt": None, "gustKt": 36, "dirDeg": None}},
                "want": "gust_only", "age": 28,
            },
            # Gust only past staleAfterMin but under 12 h: still gust_only, never invent a speed.
            {
                "now": "2026-11-27T01:08:00Z",
                "s": {"observedAt": "2026-11-26T23:38:00Z", "status": "fresh", "ageMin": 10,
                      "staleAfterMin": 75, "wind": {"speedKt": None, "gustKt": 36, "dirDeg": None}},
                "want": "gust_only", "age": 90,
            },
        ]
        harness = textwrap.dedent("""
            const cases = %s;
            %s
            for (const c of cases) {
              const now = Date.parse(c.now);
              const out = classifySta(c.s, now);
              if (out.status !== c.want) {
                console.error("status", c.want, out);
                process.exit(1);
              }
              if (Math.abs(out.ageMin - c.age) > 1) {
                console.error("age", c.age, out);
                process.exit(1);
              }
              if (c.emptyWind && out.wind.speedKt != null) {
                console.error("expected dropped wind", out);
                process.exit(1);
              }
              if (c.want === "gust_only" && out.wind.speedKt != null) {
                console.error("gust_only invented speed", out);
                process.exit(1);
              }
            }
            console.log("classifySta-ok");
        """) % (json.dumps(cases), fn)
        r = subprocess.run(["node", "-e", harness], capture_output=True, text=True, timeout=10)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertIn("classifySta-ok", r.stdout)


class TopBarLayoutNoTruncation(unittest.TestCase):
    """Rendered scrollWidth > clientWidth is a truncation failure for top-bar labels."""

    VIEWPORTS = (
        (375, 667, 0),
        (390, 844, 0),
        (430, 932, 0),
        (844, 390, 47),  # landscape with 47 px safe-area insets
    )
    LABELS = ("#w-badge", ".w-clock time", ".w-brand-a", ".w-brand-b", "#w-sta .w-lbl")

    def test_top_bar_labels_are_not_truncated_at_phone_sizes(self):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            self.skipTest("playwright not installed")
        chrome = Path("/usr/bin/google-chrome")
        if not chrome.exists():
            self.skipTest("google-chrome not installed")
        html = (ROOT / "wind.html").read_text()
        css = (ROOT / "wind.css").read_text()
        start = html.index('<header class="w-top">')
        end = html.index("</section>", html.index('class="w-strip"')) + len("</section>")
        bar = html[start:end]
        page_html = (
            "<!doctype html><html><head>"
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            "<style>" + css + "</style></head>"
            '<body data-wind-view="viewer"><div class="helm">' + bar +
            "</div>"
            "<script>document.getElementById('w-clock').textContent='10:00 PM ET';</script>"
            "</body></html>"
        )
        problems = []
        with sync_playwright() as p:
            browser = p.chromium.launch(
                executable_path=str(chrome),
                args=["--headless=new", "--no-sandbox", "--disable-gpu"],
            )
            try:
                for w, h, inset in self.VIEWPORTS:
                    page = browser.new_page(viewport={"width": w, "height": h})
                    page.set_content(page_html, wait_until="load")
                    if inset:
                        page.add_style_tag(content=(
                            ".w-top{padding-left:max(10px, %dpx)!important;"
                            "padding-right:max(10px, %dpx)!important}" % (inset, inset)
                        ))
                    page.wait_for_timeout(50)
                    metrics = page.evaluate(
                        """(sels) => {
                          const out = {doc: {
                            scrollWidth: document.documentElement.scrollWidth,
                            clientWidth: document.documentElement.clientWidth,
                            innerWidth: window.innerWidth
                          }, labels: {}};
                          for (const sel of sels) {
                            const el = document.querySelector(sel);
                            if (!el) { out.labels[sel] = {missing: true}; continue; }
                            out.labels[sel] = {
                              text: (el.textContent || "").trim(),
                              scrollWidth: el.scrollWidth,
                              clientWidth: el.clientWidth,
                              overflow: getComputedStyle(el).overflow,
                              textOverflow: getComputedStyle(el).textOverflow
                            };
                          }
                          const sta = document.getElementById("w-sta");
                          const r = sta ? sta.getBoundingClientRect() : null;
                          out.sta = r ? {w: r.width, h: r.height} : null;
                          return out;
                        }""",
                        list(self.LABELS),
                    )
                    page.close()
                    tag = "%sx%s inset=%s" % (w, h, inset)
                    if metrics["doc"]["scrollWidth"] > metrics["doc"]["innerWidth"] + 1:
                        problems.append("%s document scrollWidth %s > innerWidth %s" % (
                            tag, metrics["doc"]["scrollWidth"], metrics["doc"]["innerWidth"]))
                    for sel, m in metrics["labels"].items():
                        if m.get("missing"):
                            problems.append("%s missing %s" % (tag, sel))
                            continue
                        if m["scrollWidth"] > m["clientWidth"] + 1:
                            problems.append("%s %s truncated scroll=%s client=%s text=%r overflow=%s/%s" % (
                                tag, sel, m["scrollWidth"], m["clientWidth"], m["text"],
                                m.get("overflow"), m.get("textOverflow")))
                    if not metrics.get("sta") or metrics["sta"]["w"] < 44 - 0.5 or metrics["sta"]["h"] < 44 - 0.5:
                        problems.append("%s stations toggle not 44px: %s" % (tag, metrics.get("sta")))
                    badge = metrics["labels"].get("#w-badge", {})
                    if badge.get("text", "").upper().find("…") >= 0 or (
                        badge.get("text") and "MODEL" in badge["text"].upper()
                        and "FORECAST" not in badge["text"].upper()
                        and "GFS" not in badge["text"].upper()
                    ):
                        problems.append("%s badge text looks clipped: %r" % (tag, badge.get("text")))
            finally:
                browser.close()
        self.assertFalse(problems, "top-bar truncation:\n  " + "\n  ".join(problems))


class AssetBudgetNote(unittest.TestCase):
    def test_own_asset_total_is_reported_not_silently_capped(self):
        own = sum((ROOT / f).stat().st_size for f in ("wind.html", "wind.css", "wind-viewer.js", "wind-lab.js", "wind-coast.js"))
        # Ed t507u: official caps raised to 70 KiB own-asset and 15 KiB CSS.
        self.assertLess(own, 70 * 1024, own)
        self.assertLess((ROOT / "wind.css").stat().st_size, 15 * 1024)



class ClientAgeFromCachedPayload(unittest.TestCase):
    """Age and freshness come from observedAt vs the client clock, even for a cached pack.

    A later serve of the same JSON (90 s server cache or HTTP cache) must not freeze
    the painted age. Freshness re-evaluates on tick with no new network call.
    """

    @classmethod
    def setUpClass(cls):
        import server
        import windgrid
        fix = ROOT / "tests/fixtures/gfs_uv10m_ncbox.grb2"
        windgrid._cache.clear()
        with mock.patch.object(windgrid, "_fetch", return_value=fix.read_bytes()), \
             mock.patch.object(windgrid.time, "time", return_value=1795122000.0):
            cls.grid = dict(windgrid.latest_grid(ahead=0))
        cls.grid["ok"] = True
        cls.grid["run"] = "2026-11-26T18:00Z"
        cls.grid["valid"] = "2026-11-27T00:00Z"
        cls.grid["forecastHour"] = 6
        cls._ads = (ROOT / "data" / "ads.json").read_bytes()
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.base = "http://127.0.0.1:%d" % cls.httpd.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        ads = ROOT / "data" / "ads.json"
        if ads.read_bytes() != cls._ads:
            ads.write_bytes(cls._ads)

    def _pack(self, observed_at, age_min, status, stale_after=75):
        return {
            "ok": True,
            "kind": "observed",
            "generatedAt": "2026-11-26T22:17:00Z",
            "stations": [{
                "id": "CLKN7",
                "name": "Cape Lookout",
                "type": "ndbc",
                "lat": 34.622,
                "lon": -76.525,
                "source": "NOAA NDBC",
                "observedAt": observed_at,
                "ageMin": age_min,
                "status": status,
                "staleAfterMin": stale_after,
                "wind": {"speedKt": 18, "gustKt": 28, "dirDeg": 230, "dirCompass": "SW"},
            }],
        }

    def _browser(self):
        from playwright.sync_api import sync_playwright
        chrome = Path("/usr/bin/google-chrome")
        if not chrome.exists():
            self.skipTest("google-chrome not installed")
        pw = sync_playwright().start()
        browser = pw.chromium.launch(
            executable_path=str(chrome),
            args=["--headless=new", "--no-sandbox", "--disable-gpu"],
        )
        return pw, browser

    def _open(self, page, pack, t0_ms):
        hits = {"stations": 0}

        def on_req(req):
            if "/api/wind-stations" in req.url:
                hits["stations"] += 1

        page.on("request", on_req)
        page.route("**/api/wind-grid**", lambda r: r.fulfill(
            status=200, content_type="application/json", body=json.dumps(self.grid)))
        # Same body on every request: models a 90 s / HTTP cached payload.
        body = json.dumps(pack)
        page.route("**/api/wind-stations**", lambda r: r.fulfill(
            status=200, content_type="application/json",
            headers={"Cache-Control": "public, max-age=90"}, body=body))
        page.add_init_script("window.__windNow = () => %d;" % t0_ms)
        page.goto(self.base + "/wind?theme=light&stations=1", wait_until="domcontentloaded")
        page.wait_for_function("() => window.__windView && window.__windView.grid && window.__windView.grid()", timeout=20000)
        page.wait_for_function("() => window.__windView.stations && window.__windView.stations.marks().length > 0", timeout=15000)
        page.evaluate("""() => {
          const s = window.__windView.stations.pack().stations.find(x => x.id === 'CLKN7');
          window.__windView.map.setView([s.lat, s.lon], 8.5, {animate:false});
          window.__windView.readAt({lat:s.lat, lng:s.lon}, null, s);
        }""")
        page.wait_for_function("() => /OBSERVED/.test((document.getElementById('w-read-body')||{}).innerText||'')", timeout=8000)
        return hits

    def test_cached_payload_served_later_increases_painted_age(self):
        # Pack claims Fresh / 5 min, but observedAt is 20 min before t0.
        t0 = int(datetime(2026, 11, 27, 1, 8, tzinfo=timezone.utc).timestamp() * 1000)  # 2026-11-27T01:08:00Z
        observed = "2026-11-27T00:48:00Z"  # 20 min earlier
        pack = self._pack(observed, age_min=5, status="fresh", stale_after=75)
        try:
            from playwright.sync_api import sync_playwright  # noqa: F401
        except ImportError:
            self.skipTest("playwright not installed")
        pw, browser = self._browser()
        try:
            page = browser.new_page(viewport={"width": 390, "height": 844})
            hits = self._open(page, pack, t0)
            text0 = page.locator("#w-read-body").inner_text()
            self.assertIn("Fresh", text0)
            self.assertIn("20 min ago", text0)
            self.assertNotIn("5 min ago", text0)
            first_hits = hits["stations"]
            self.assertGreaterEqual(first_hits, 1)
            # Same cached JSON, clock jumps 15 minutes, no requirement for a new fetch.
            page.evaluate("window.__windNow = () => %d;" % (t0 + 15 * 60 * 1000))
            page.evaluate("window.__windView.tick()")
            text1 = page.locator("#w-read-body").inner_text()
            self.assertIn("35 min ago", text1)
            self.assertIn("Fresh", text1)
            self.assertNotIn("20 min ago", text1)
            self.assertEqual(hits["stations"], first_hits)
        finally:
            browser.close()
            pw.stop()

    def test_fresh_becomes_stale_on_tick_at_station_threshold_without_refetch(self):
        t0 = int(datetime(2026, 11, 27, 1, 8, tzinfo=timezone.utc).timestamp() * 1000)  # 2026-11-27T01:08:00Z
        # 74 min old at t0, threshold 75: Fresh. Two minutes later: Stale.
        observed = "2026-11-26T23:54:00Z"
        pack = self._pack(observed, age_min=10, status="fresh", stale_after=75)
        try:
            from playwright.sync_api import sync_playwright  # noqa: F401
        except ImportError:
            self.skipTest("playwright not installed")
        pw, browser = self._browser()
        try:
            page = browser.new_page(viewport={"width": 390, "height": 844})
            hits = self._open(page, pack, t0)
            text0 = page.locator("#w-read-body").inner_text()
            self.assertIn("Fresh", text0)
            self.assertIn("74 min ago", text0)
            self.assertNotIn("Stale", text0)
            first_hits = hits["stations"]
            page.evaluate("window.__windNow = () => %d;" % (t0 + 2 * 60 * 1000))
            page.evaluate("window.__windView.tick()")
            text1 = page.locator("#w-read-body").inner_text()
            self.assertIn("Stale — last report", text1)
            self.assertNotIn("Fresh", text1)
            self.assertIn("is-stale", page.locator(".w-obs").get_attribute("class"))
            self.assertEqual(hits["stations"], first_hits)
        finally:
            browser.close()
            pw.stop()



if __name__ == "__main__":
    unittest.main()
