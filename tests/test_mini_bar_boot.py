"""The mobile mini-bar must be filled even when glance is already in the boot HTML."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DASH = (ROOT / "dashboard.js").read_text(encoding="utf-8")


class MiniBarBoot(unittest.TestCase):
    def test_render_always_calls_render_header_bits(self) -> None:
        start = DASH.index("function render(d, opts)")
        end = DASH.index("function showError(", start)
        render = DASH[start:end]
        self.assertIn("renderGlance(d)", render)
        self.assertIn("renderAlerts(d.alerts, d.marine)", render)
        # The LCP skip must not swallow the mini-bar fill.
        stripped, n = re.subn(
            r"if\s*\(\s*!already\s*\)\s*\{[^{}]*\}",
            "",
            render,
            count=1,
        )
        self.assertEqual(n, 1, "expected a single if (!already) block in render()")
        self.assertNotIn("renderGlance(d)", stripped)
        self.assertIn("renderHeaderBits(d)", stripped)
        self.assertIn('if ($("mini-wind")) $("mini-wind").textContent = mini.wind;', DASH)


class GlanceObserver(unittest.TestCase):
    def test_dashboard_hooks_glance_io_on_skip_repaint(self):
        src = (Path(__file__).resolve().parents[1] / "dashboard.js").read_text(encoding="utf-8")
        self.assertIn("function hookGlanceIO()", src)
        # Called from render() even when homepage_boot already painted glance.
        render = src[src.find("function render(d, opts)"): src.find("function showError")]
        self.assertIn("hookGlanceIO()", render)
        self.assertGreater(render.find("hookGlanceIO()"), render.find("if (!already)"))
