"""Nov 16 visual pass: featured catch, daily-photo landscape
filter, masthead/instrument navigation. Presentation only."""
from __future__ import annotations

import json
import re
import sys
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import catch_wall_preview as cwp  # noqa: E402
import photo_rotation as R  # noqa: E402
import sprint_home  # noqa: E402
from test_catch_wall_preview import APPROVED, NOT_SHOWN, main_part, render as cw_render  # noqa: E402
from test_photo_rotation import entry, write_manifest  # noqa: E402
from test_sprint_home_preview import render, salt, fresh_jordan  # noqa: E402


class FeaturedCatch(unittest.TestCase):
    def test_deterministic_per_day_and_order_independent(self):
        d = date(2026, 11, 16)
        a = cwp.featured_catch(APPROVED, d)
        self.assertEqual(a["id"], cwp.featured_catch(list(reversed(APPROVED)), d)["id"])
        self.assertEqual(a["id"], cwp.featured_catch(APPROVED, d)["id"])
        ids = sorted(p["id"] for p in APPROVED)
        self.assertEqual(a["id"], ids[d.toordinal() % len(ids)])
        seen = {cwp.featured_catch(APPROVED, date.fromordinal(d.toordinal() + k))["id"] for k in range(len(APPROVED))}
        self.assertEqual(seen, set(ids))   # every approved catch gets its day

    def test_approved_only(self):
        for k in range(10):
            p = cwp.featured_catch(APPROVED + NOT_SHOWN, date.fromordinal(739000 + k))
            self.assertIn(p["id"], {x["id"] for x in APPROVED})
        self.assertIsNone(cwp.featured_catch(NOT_SHOWN, date(2026, 11, 16)))
        self.assertIsNone(cwp.featured_catch([], date(2026, 11, 16)))

    def test_rendered_once_with_stored_caption_and_label_only(self):
        d = date(2026, 11, 16)
        f = cwp.featured_catch(APPROVED, d)
        body, _ = cwp.body_html(cwp.catch_photos(APPROVED + NOT_SHOWN), d)
        self.assertEqual(body.count('data-featured="1"'), 1)
        self.assertEqual(body.count("Featured catch"), 1)
        fig = re.search(r'<figure class="pl pl-f"[^>]*data-featured="1">.*?</figure>', body, re.S).group(0)
        self.assertIn(f["id"], fig)
        self.assertIn(cwp.title(f), fig)
        self.assertIn(cwp.credit(f), fig)
        # each approved photo appears once as a plate (featured is not duplicated)
        self.assertEqual(len(re.findall(r'<figure class="pl ', body)), len(APPROVED))
        # contribution card is in the mosaic and uses the existing submit link only
        self.assertEqual(body.count('class="pl pl-join"'), 1)
        self.assertIn('href="/catch-wall"', re.search(r'<aside class="pl pl-join".*?</aside>', body, re.S).group(0))

    def test_no_upload_form_on_preview(self):
        doc = cw_render()
        self.assertNotIn('type="file"', doc)
        self.assertNotIn("/api/photos/submit", doc)


class LandscapeOnly(unittest.TestCase):
    def test_portrait_entries_never_rotate(self):
        with tempfile.TemporaryDirectory() as d:
            man = R.load(write_manifest([entry(1, "heritage"), entry(2, "saltwater", width=1200, height=1600),
                                         entry(3, "freshwater", width=1200, height=1200)], Path(d)))
            ids = [p["id"] for p in man["photos"]]
            self.assertEqual(ids, ["p1", "p3"])
            self.assertIn(("p2", "portrait"), man["skipped"])

    def test_live_manifest_is_landscape(self):
        man = R.active()
        self.assertTrue(man and man["photos"])
        for p in man["photos"]:
            self.assertLessEqual(p["height"], p["width"], p["id"])

    def test_caption_does_not_repeat_location(self):
        p = R.featured(photo_id="falls-lake-pier", approved=[])
        hz = R.horizon_html(p)
        text = re.sub(r"<[^>]+>", " ", hz)
        self.assertEqual(text.count("Falls Lake"), 1, text)
        self.assertIn("Today\u2019s photograph", hz)


class Navigation(unittest.TestCase):
    def test_chart_radar_links_point_at_real_targets(self):
        h = render("hybrid", salt("wilmington"))
        nav = re.search(r'<nav class="cg-tools".*?</nav>', h, re.S).group(0)
        for anchor in ("#map-chart", "#map-radar", "#tide-search"):
            self.assertIn('href="/dashboard?region=wilmington%s"' % anchor, nav)
        index = (Path(sprint_home.ROOT) / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="tide-search"', index)
        self.assertIn('id="map-section"', index)
        for chip in ("chart", "radar"):
            self.assertIn('data-chip="%s"' % chip, index)
        app = (Path(sprint_home.ROOT) / "app.js").read_text(encoding="utf-8")
        self.assertIn("#map-(chart|radar|wind|waves|sst)", app.replace("\\", ""))
        # never a link back to the Hybrid page itself as "Full dashboard"
        self.assertNotIn('href="/?region=wilmington">Full dashboard', h)
        self.assertNotRegex(h, r"<details[^>]*>\s*<summary>[^<]*(Wind|Seas|Water|Tide)")

    def test_fresh_tools_link_lake_page(self):
        h = render("hybrid", fresh_jordan(), fresh=True)
        nav = re.search(r'<nav class="cg-tools".*?</nav>', h, re.S).group(0)
        self.assertIn('href="/lake?region=jordan-lake"', nav)
        self.assertNotIn("#map-radar", nav)

    def test_masthead_newspaper_and_wave_rule(self):
        h = render("hybrid", salt("wilmington"))
        self.assertIn('class="mh-ear"', h)
        self.assertIn('class="mh-rule-heavy"', h)
        self.assertEqual(h.count('class="wave-settle"'), 1)
        self.assertEqual(h.count("From the rivers to the sounds to the sea"), 1)
        self.assertEqual(h.count("Know the Water. Live the Coast."), 1)


if __name__ == "__main__":
    unittest.main()
