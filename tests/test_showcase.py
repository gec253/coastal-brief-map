"""Private Wind & Radar homepage showcase (design preview): gate, placement, labels, lazy/static loading."""
import os
import re
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import showcase  # noqa: E402

PAGE = ('<html><head><meta name="robots" content="index, follow"></head><body><main>'
        '<section class="cg cg-hybrid" id="conditions"><div class="al">Small Craft Advisory</div>'
        '<section class="inner">x</section></section><aside class="cb-life">life</aside>'
        '<section class="hz">photo</section></main></body></html>').encode()
META = (200, {"ok": True, "attribution": "Radar: NOAA/NSSL MRMS; Source: Météo-France & co.", "disclaimer": "Radar is for general information only."})


def env(**kv):
    base = {k: v for k, v in os.environ.items() if k not in ("RENDER", "RENDER_SERVICE_ID", "HOME_SHOWCASE")}
    base.update(kv)
    return mock.patch.dict(os.environ, base, clear=True)


class Gate(unittest.TestCase):
    def test_local_flag_and_query_required(self):
        with env(HOME_SHOWCASE="1"):
            self.assertEqual(showcase.variant({"showcase": ["a"]}, None), "A")
            self.assertEqual(showcase.variant({"showcase": ["B"]}, "crystal-coast"), "B")
            self.assertIsNone(showcase.variant({"showcase": ["C"]}, None))
            self.assertIsNone(showcase.variant({}, None))
            self.assertIsNone(showcase.variant({"showcase": ["A"]}, "hatteras"))
        with env():
            self.assertIsNone(showcase.variant({"showcase": ["A"]}, None))

    def test_production_can_never_enable(self):
        for extra in ({"RENDER": "true"}, {"RENDER_SERVICE_ID": "srv-x"}):
            with env(HOME_SHOWCASE="1", **extra):
                self.assertFalse(showcase.enabled())
                self.assertIsNone(showcase.variant({"showcase": ["A"]}, None))

    def test_assets_not_served_statically(self):
        import server
        for p in ("/showcase.js", "/showcase.css", "/showcase.py"):
            self.assertFalse(server._static_allowed(p), p)


class Inject(unittest.TestCase):
    def test_after_conditions_before_rest_and_content_intact(self):
        for v in ("A", "B"):
            out = showcase.inject(PAGE, v, radar_meta=lambda: META).decode()
            i_cond, i_sc, i_life = out.find('id="conditions"'), out.find('id="showcase"'), out.find('class="cb-life"')
            self.assertTrue(0 < i_cond < out.find("Small Craft Advisory") < i_sc < i_life)
            self.assertIn('class="sc sc-%s"' % v.lower(), out)
            for keep in ("Small Craft Advisory", "life", "photo"):
                self.assertIn(keep, out)
            self.assertIn('content="noindex, nofollow"', out)
            self.assertNotIn("index, follow", out)
            self.assertEqual(out.count('<script src="/showcase.js" defer>'), 1)

    def test_labels_credits_and_links(self):
        out = showcase.inject(PAGE, "A", radar_meta=lambda: META).decode()
        self.assertIn("Model forecast · GFS", out)
        self.assertIn(">Observed<", out)
        self.assertNotIn("Forecast</span>", out.split('class="sc-inst sc-radar"')[1].split("</a>")[0])
        self.assertIn(showcase.GFS_CREDIT, out)
        self.assertIn("Radar: NOAA/NSSL MRMS; Source: Météo-France &amp; co.", out)  # verbatim (escaped)
        self.assertIn("Radar is for general information only.", out)
        self.assertIn('href="/wind"', out)
        self.assertIn('href="/radar"', out)

    def test_meta_failure_still_renders(self):
        def boom():
            raise RuntimeError("x")
        self.assertIn('id="showcase"', showcase.inject(PAGE, "B", radar_meta=boom).decode())


class Client(unittest.TestCase):
    js = (ROOT / "showcase.js").read_text(encoding="utf-8")
    css = (ROOT / "showcase.css").read_text(encoding="utf-8")

    def test_lazy_static_latest_observed_only(self):
        self.assertIn("IntersectionObserver", self.js)
        self.assertNotIn("requestAnimationFrame", self.js)  # no animation loop
        self.assertIn('f.type === "observed"', self.js)
        self.assertNotIn("nowcast", re.sub(r"/\*.*?\*/", "", self.js, flags=re.S).replace("never forecast", ""))
        self.assertIn("obs[obs.length - 1]", self.js)
        self.assertIn('timeZone: "America/New_York"', self.js)
        self.assertIn("/api/wind-grid", self.js)

    def test_tap_targets_and_reduced_motion(self):
        self.assertIn("min-height:44px", self.css)
        self.assertIn("prefers-reduced-motion:reduce", self.css)
        self.assertIn("aspect-ratio:4/3", self.css)  # reserved space: no layout shift


    def test_a_layout_and_legible_credits(self):
        self.assertIn("@media (min-width:700px){.sc-a .sc-grid{grid-template-columns:1fr 1fr}}", self.css)
        self.assertIn("aspect-ratio:4/3", self.css)
        self.assertIn("font-size:.7rem", self.css)
        self.assertNotIn("display:none", self.css.replace(".sc-pv{position:absolute;left:-9999px}", "").replace(".sc-b .sc-read small{display:none}", "").replace(".sc-b .sc-age i{display:none}", ""))
        html = showcase.section("A", "Radar: credit.", "Radar is for general information only.")
        self.assertNotIn("<details", html)
        credit = html[html.find("sc-credit"):]
        self.assertNotIn(" hidden", credit)
        self.assertIn("Crystal Coast", html)
        self.assertIn(showcase.GFS_CREDIT, html)
        self.assertIn("Radar: credit.", html)
        self.assertIn("Radar is for general information only.", html)
        self.assertIn("Cape Lookout", self.js)
        self.assertIn("34.605", self.js)
        self.assertIn("-76.536", self.js)
        self.assertIn("No precipitation in view", self.js)
        self.assertIn('nm + " nm"', self.js)


if __name__ == "__main__":
    unittest.main()
