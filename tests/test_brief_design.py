"""Presentation-only checks for the Morning Brief page."""
import json
import unittest
from pathlib import Path

import brief

ROOT = Path(__file__).resolve().parents[1]
BRIEFS = ROOT / "cache" / "briefs"


def _load(name):
    p = BRIEFS / ("%s.json" % name)
    if not p.exists():
        raise unittest.SkipTest("no cached brief for %s" % name)
    return json.loads(p.read_text())


class BriefPage(unittest.TestCase):
    def test_disclaimers_and_interpretation_label(self):
        b = _load("hatteras")
        html = brief.page(b, include_fresh=True)
        low = html.lower()
        self.assertIn("interpretation", low)
        self.assertIn("not a fishing report", low)
        self.assertIn("not endorsed by noaa", low)
        self.assertIn("not an observation", low)
        self.assertIn("og:image", html)
        self.assertIn('rel="stylesheet" href="/brief.css"', html)
        self.assertIn("@media print", Path(ROOT / "brief.css").read_text())

    def test_does_not_relabel_swell_as_seas(self):
        b = _load("hatteras")
        cells = {c["key"]: c for c in brief._glance(b)}
        self.assertIn("Seas", cells)
        self.assertIn("Swell", cells)
        self.assertEqual(cells["Seas"]["kind"], "observed")
        self.assertEqual(cells["Swell"]["kind"], "observed")
        self.assertNotEqual(cells["Seas"]["value"], cells["Swell"]["value"] or "same-check")
        html = brief.page(b)
        # Swell cell keeps its own label; seas wording stays in the seas row.
        self.assertIn('mb-gk">Swell<', html)
        self.assertIn('mb-gk">Seas<', html)
        self.assertIn("predicted", html.lower())  # tide next

    def test_tide_next_is_predicted_and_after_issue(self):
        b = _load("hatteras")
        cells = [c for c in brief._glance(b) if c["key"].startswith("Tide") or "tide" in c["key"].lower()]
        self.assertTrue(cells)
        self.assertEqual(cells[0]["kind"], "predicted")
        self.assertEqual(cells[0]["key"], "Tide next")
        self.assertIn("6:03", cells[0]["value"])

    def test_freshwater_brief_keeps_observed_vs_forecast(self):
        b = _load("falls-lake")
        html = brief.page(b, include_fresh=True)
        self.assertIn('data-water="freshwater"', html)
        kinds = {c["key"]: c["kind"] for c in brief._glance(b)}
        self.assertEqual(kinds.get("Lake level"), "observed")
        self.assertEqual(kinds.get("Rain, 24 h"), "observed")
        self.assertEqual(kinds.get("Air high"), "forecast")
        self.assertIn("Frost Advisory", html)

    def test_falls_lake_link_only_when_fresh_enabled(self):
        b = _load("hatteras")
        self.assertNotIn("/brief?region=falls-lake", brief.page(b, include_fresh=False))
        self.assertIn("/brief?region=falls-lake", brief.page(b, include_fresh=True))

    def test_wording_unchanged_from_stored_items(self):
        b = _load("hatteras")
        html = brief.page(b)
        for k, v in b["items"]:
            if k in ("Advisories", "Alerts"):
                self.assertIn(v, html)
            else:
                self.assertIn(v, html)
        for sentence in b["take"]:
            self.assertIn(sentence, html)

    def test_phone_collapses_detail_sections(self):
        b = _load("hatteras")
        html = brief.page(b)
        css = Path(ROOT / "brief.css").read_text()
        self.assertIn('<details class="mb-details" id="mb-details">', html)
        self.assertIn("<summary>Full readings", html)
        # Closed by default in the markup; JS opens on 601px+ and for print.
        self.assertNotIn('<details class="mb-details" id="mb-details" open', html)
        self.assertIn("<dl class=\"mb-body\">", html)
        self.assertIn("mb-body", html.split('id="mb-details"', 1)[1].split("</details>", 1)[0])
        self.assertIn("@media (min-width: 601px)", css)
        self.assertIn(".mb-details[open] > summary", css)
        self.assertIn(".mb-details > summary", css)
        # Print hides the summary; beforeprint in the page script opens the section.
        self.assertIn(".mb-details > summary { display: none !important; }", " ".join(css.split()))
        self.assertIn("beforeprint", html)
        self.assertIn("min-width: 601px", html)


if __name__ == "__main__":
    unittest.main()
