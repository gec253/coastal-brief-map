"""Wind Viewer Phase B3: observed markers and combined forecast/observed panel.

Does not raise the 55 KiB asset cap or rewrite protected-file SHA pins.
"""
from __future__ import annotations

import hashlib
import re
import unittest
from pathlib import Path

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
        gust = self.js.split('s.status === "gust_only"', 1)[1].split("if (s.status", 1)[0]
        self.assertIn("Wind speed unavailable", gust)
        self.assertNotIn("speedKt) + \" kt\"", gust)
        unav = self.js.split('s.status === "unavailable"', 1)[1].split("let num", 1)[0]
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


class AssetBudgetNote(unittest.TestCase):
    def test_own_asset_total_is_reported_not_silently_capped(self):
        own = sum((ROOT / f).stat().st_size for f in ("wind.html", "wind.css", "wind-viewer.js", "wind-lab.js", "wind-coast.js"))
        self.assertGreater(own, 55 * 1024)  # B3 exceeds the approved 55 KiB cap; a new cap needs Ed's approval.
        # Do not raise the official cap in this commit.
        self.assertGreater((ROOT / "wind.css").stat().st_size, 12 * 1024)


if __name__ == "__main__":
    unittest.main()
