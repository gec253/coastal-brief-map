"""Concept B, Balanced Nautical (Ed t390u): styling only, real homepage stylesheet."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / "preview/sprint-home/hybrid.css").read_text(encoding="utf-8")


def rule(sel):
    m = re.findall(r"(?:^|[}\n])[ \t]*" + re.escape(sel) + r"\{([^}]*)\}", CSS)
    assert m, sel
    return "\n".join(m)


class Tokens(unittest.TestCase):
    def test_rf_tokens_defined_day_and_night(self):
        for t in ("--rf-surface-warm", "--rf-surface-tile", "--rf-tile-edge", "--rf-edge-strong", "--rf-shadow-1",
                  "--rf-shadow-2", "--rf-brass", "--rf-brass-hair", "--rf-brass-ink", "--rf-active-fill",
                  "--rf-active-ink", "--rf-focus-ring", "--rf-grid"):
            self.assertGreaterEqual(CSS.count(t + ":"), 1, t)
        dark = CSS[CSS.index("Balanced Nautical (Concept B"):]
        dark = dark[dark.index("@media (prefers-color-scheme:dark)"):]
        self.assertIn("--rf-active-fill:#F3E6D0", dark[:1200])


class MarineSection(unittest.TestCase):
    def test_forecast_is_warm_with_one_brass_hairline(self):
        self.assertIn("background:var(--rf-surface-warm)", rule(".cg-hybrid .fc"))
        self.assertIn("var(--rf-brass)", rule(".cg-hybrid .fc-h"))

    def test_also_observed_is_four_defined_tiles_with_bottom_source(self):
        sx = rule(".sx")
        for k in ("display:flex", "flex-direction:column", "border-radius:6px", "border-top:2px solid var(--rf-rule)",
                  "background:var(--rf-surface-tile)"):
            self.assertIn(k, sx)
        self.assertIn("gap:6px", rule(".cg-strip"))
        self.assertIn("margin-top:auto", rule(".sx-src"))
        self.assertNotIn(".sx:nth-of-type(odd){border-right", CSS)


class Instruments(unittest.TestCase):
    def test_brass_only_on_featured_wind_and_seas(self):
        self.assertIn("var(--rf-brass-hair)", rule(".cg-hybrid .t-wind,.cg-hybrid .t-seas"))
        self.assertIn("display:none", rule(".cg-hybrid .t::before"))
        for other in (".t-water", ".t-tide", ".t-swell"):
            self.assertNotRegex(CSS, re.escape(".cg-hybrid " + other) + r"[^{]*\{[^}]*rf-brass")


class Controls(unittest.TestCase):
    def test_selected_uses_fill_weight_and_check_not_brass_alone(self):
        sel = rule(".rr-l a[aria-current]")
        self.assertIn("background:var(--rf-active-fill)", sel)
        self.assertIn("font-weight:700", sel)
        self.assertIn("transform:rotate(45deg)", rule(".rr-l a[aria-current]::before"))
        self.assertIn("min-height:44px", rule(".rr-l a"))
        self.assertIn("min-height:44px", rule(".cg-tool"))
        for s in (".rr-l a:focus-visible", ".cg-tool:focus-visible", ".cg-hybrid .al-link:focus-visible"):
            self.assertIn("var(--rf-focus-ring)", rule(s))


class Texture(unittest.TestCase):
    def test_grid_is_css_only_behind_opaque_faces(self):
        g = rule(".cg-hybrid::before")
        self.assertNotIn("url(", g)
        self.assertIn("z-index:-1", g)
        self.assertIn("repeating-linear-gradient", g)
        self.assertRegex(CSS, r"--rf-grid:rgba\(7,28,41,\.0[0-4]\d*\)")
        for s in (".sx", ".cg-hybrid .fc"):
            self.assertIn("background:var(--rf-surface", rule(s))

    def test_showcase_and_other_pages_untouched(self):
        self.assertNotIn("--rf-", (ROOT / "showcase.css").read_text(encoding="utf-8"))
        self.assertNotIn("--rf-", (ROOT / "folio-chrome.css").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
