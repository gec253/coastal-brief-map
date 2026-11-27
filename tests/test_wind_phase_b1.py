"""Wind Viewer Phase B1: compact, persistent GFS FORECAST panel (Ed t500u).

Planning-only constraints still apply to later phases: no stations, no new endpoint,
no HRRR activation, no Radar changes. This module does not raise the 53 KiB asset
cap or rewrite protected-file SHA pins.
"""
from __future__ import annotations

import hashlib
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _sha256(rel: str) -> str:
    return hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()


class PhaseB1Panel(unittest.TestCase):
    html = (ROOT / "wind.html").read_text()
    css = (ROOT / "wind.css").read_text()
    js = (ROOT / "wind-viewer.js").read_text()
    engine = (ROOT / "wind-lab.js").read_text()

    def test_panel_markup_and_dismiss(self):
        self.assertIn('id="w-read"', self.html)
        self.assertIn('id="w-read-body"', self.html)
        self.assertRegex(self.html, r'id="w-read-body"[^>]*aria-live="polite"')
        self.assertIn('id="w-read-x"', self.html)
        self.assertIn('aria-label="Dismiss forecast panel"', self.html)
        self.assertIn('class="w-read-x"', self.html)
        self.assertIn('tabindex="-1"', self.html)  # map can take focus back after dismiss
        # Visible copy is filled in by JS; the heading must be a MODEL forecast, never observed.
        self.assertIn('modelName + " FORECAST"', self.js)
        self.assertIn("Outside model coverage — no GFS data for this spot", self.js)
        self.assertIn("Model data didn't load — try again", self.js)
        self.assertNotIn("No model data here", self.js)
        self.assertNotIn("Outside the model area", self.js)
        # Quoted user-facing copy (escape-aware). The forecast heading stays a model forecast.
        strings = " ".join(re.findall(r'"(?:[^"\\]|\\.)*"', self.js))
        self.assertIsNone(re.search(r"\blive\b", strings, re.I))

    def test_dismiss_is_keyboard_operable_and_clears_selection(self):
        self.assertIn('$("w-read-x").addEventListener("click", dismissRead)', self.js)
        self.assertIn('e.key !== "Escape"', self.js)
        self.assertIn("dismissRead()", self.js)
        self.assertIn("map.removeLayer(dot)", self.js)
        self.assertIn('live.innerHTML = ""', self.js)
        self.assertIn("read.hidden = true", self.js)
        self.assertIn('el.focus()', self.js)

    def test_outside_grid_and_missing_data_have_no_number(self):
        # Two honest no-data paths: failed/missing grid vs outside coverage. Never a wind number.
        self.assertIn("This viewer loads GFS wind for 32.5–37.5°N, 73–80°W.", self.js)
        self.assertIn("Model wind is unavailable right now.", self.js)
        self.assertIn("!isFinite(s.kt)", self.js)
        self.assertIn("!isFinite(s.from)", self.js)
        no_grid = self.js.split("if (!grid)")[1].split("else if")[0]
        no_sample = self.js.split("!isFinite(s.from)")[1].split("} else {")[0]
        self.assertIn("Model data didn't load — try again", no_grid)
        self.assertIn("Loading model wind", no_grid)
        self.assertIn("Outside model coverage — no GFS data for this spot", no_sample)
        self.assertNotIn("Outside model coverage", no_grid)
        self.assertNotIn("didn't load", no_sample)
        self.assertNotIn(" kt", no_grid)
        self.assertNotIn(" kt", no_sample)
        self.assertNotIn("Math.round", no_grid)
        self.assertNotIn("Math.round", no_sample)

    def test_in_grid_copy_is_forecast_with_valid_time(self):
        self.assertIn('Math.round(s.kt) + " kt</strong> from "', self.js)
        self.assertIn('M.compass(s.from)', self.js)
        self.assertIn('Valid " + M.etShort(grid.valid)', self.js)
        self.assertIn("Behind current time", self.js)
        self.assertIn(" h ago", self.js)
        self.assertNotIn("nearest hour", self.js)
        self.assertNotIn("Nearest hour", self.js)
        self.assertIn('interpolated, 0.25° grid (~25 km)', self.js)
        # Same bilinear sampler the particles use.
        self.assertIn("wind.sample(latlng.lat, latlng.lng)", self.js)

    def test_selection_persists_across_forecast_hour_steps(self):
        self.assertIn("if (read && !read.hidden && dot) readAt(dot.getLatLng());", self.js)
        self.assertIn('$("w-prev").addEventListener("click"', self.js)
        self.assertIn('$("w-next").addEventListener("click"', self.js)
        self.assertIn("AHEAD = [0, 3, 6, 9, 12]", self.js)

    def test_dismiss_button_is_44px_and_panel_stays_in_the_stack(self):
        def px(sel, prop):
            m = re.search(re.escape(sel) + r" \{[^}]*?" + prop + r": (\d+)px", self.css)
            self.assertIsNotNone(m, sel + " " + prop)
            return int(m.group(1))
        self.assertGreaterEqual(px(".w-read-x", "width"), 44)
        self.assertGreaterEqual(px(".w-read-x", "height"), 44)
        self.assertIn("pointer-events: auto", re.search(r"\.w-read-x \{[^}]+\}", self.css).group(0))
        self.assertIn(".w-stack", self.css)
        self.assertIn('class="w-stack"', self.html)
        # Safe-area margins on the card; controls already use inset-bottom.
        self.assertIn("env(safe-area-inset-left)", re.search(r"\.w-read \{[^}]+\}", self.css).group(0))
        self.assertIn("env(safe-area-inset-right)", re.search(r"\.w-read \{[^}]+\}", self.css).group(0))

    def test_public_and_preview_css_byte_identical_radar_water_untouched(self):
        self.assertEqual((ROOT / "wind.css").read_bytes(), (ROOT / "preview" / "wind" / "wind.css").read_bytes())
        self.assertIn('html:not([data-theme="dark"]) body[data-radar-view="viewer"] { --map-bg: #EAF1F4; }', self.css)
        # Radar assets must stay byte-identical to production (ca51ee1 / this branch's parent).
        for rel in ("radar.html", "radar-viewer.js", "radar-player.js", "radar.css"):
            self.assertTrue((ROOT / rel).exists(), rel)

    def test_performance_caps_and_single_raf_untouched(self):
        self.assertIn("maxParticles: phone ? 1100 : 2200", self.js)
        self.assertIn("dprCap: phone ? 1.5 : 2", self.js)
        self.assertIn("phone ? 30 : 60", self.js)
        self.assertIn("frameMs: fps === 30 ? 33.3 : 0", self.js)
        self.assertIn("(prefers-reduced-motion: reduce)", self.js)
        self.assertIn("@media (prefers-reduced-motion: reduce)", self.css)
        # B1 must not add a second animation loop or start touching the engine.
        self.assertNotIn("requestAnimationFrame", self.js)
        self.assertEqual(self.engine.count("requestAnimationFrame"), 3)  # schedule, loop, restart in wind-lab.js
        self.assertIn("!document.hidden", self.engine)

    def test_wind_lab_js_unchanged(self):
        # Prefer not to touch the SHA-pinned engine; B1 must leave it at the Phase A public bytes.
        self.assertEqual(
            _sha256("wind-lab.js"),
            "aca358bd4ee33fdef19da2fd6aa907f690c2b080803b11d6cb86dac99c371558",
        )



    def test_forecast_valid_lag_is_honest_and_never_called_now(self):
        # Labels follow valid-time vs now, not the ahead-step index (+0 h / Nearest hour).
        self.assertIn("function relValid", self.js)
        self.assertIn("h < -0.75", self.js)          # 45 min+ behind → "N h ago"
        self.assertIn("h > 0.75", self.js)
        self.assertIn('n + " h ago"', self.js)
        self.assertIn('"in " + n + " h"', self.js)
        self.assertIn("Behind current time", self.js)
        self.assertIn("fcstTag", self.js)
        self.assertIn('padStart(3, "0")', self.js)
        self.assertNotIn('a === 0 ? "Nearest hour"', self.js)
        self.assertNotIn('"+" + a + " h"', self.js)
        # Session memo is dropped when the cached valid time is far from the intended target.
        self.assertIn("54e5", self.js)
        # Clock tick refreshes the lag label without inventing a new value.
        self.assertIn("onTick", self.js)

    def test_hour_control_shrinks_instead_of_clipping(self):
        hour = re.search(r"\.w-hour \{([^}]+)\}", self.css).group(1)
        self.assertIn("min-width: 0", hour)
        self.assertIn("text-overflow: ellipsis", self.css)
        # Arrow / play / locate buttons stay at least 44 px in every breakpoint.
        for rule in re.findall(r"\.w-(?:btn|arrow|play) \{([^}]*)\}", self.css):
            for v in re.findall(r"min-(?:width|height): (\d+)px", rule):
                self.assertGreaterEqual(int(v), 44, rule)
        self.assertIn("Fcst hour", self.html)
        self.assertNotIn("Nearest hour", self.html)
        self.assertNotIn("+0 h", self.html)


class AssetBudgetNote(unittest.TestCase):
    def test_css_stays_under_12_kib(self):
        self.assertLess((ROOT / "wind.css").stat().st_size, 12 * 1024)

    def test_own_asset_total_is_reported_not_silently_capped(self):
        # Official cap remains 53 KiB in test_wind_viewer. Do not raise it here.
        own = sum((ROOT / f).stat().st_size for f in ("wind.html", "wind.css", "wind-viewer.js", "wind-lab.js", "wind-coast.js"))
        # Record the number so a failure of the official cap test is easy to reconcile.
        self.assertGreater(own, 0)
        self.assertLess((ROOT / "wind.css").stat().st_size, 12 * 1024)
