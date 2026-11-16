"""Nov 16b refinements: homepage instruments, character band, Catch Wall empty states, feedback."""
from __future__ import annotations

import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))

import feedback
import photo_rotation
import sprint_home
from test_sprint_home_preview import OFF, ok, render, salt, tile


class Instruments(unittest.TestCase):
    def test_wind_compass_and_gust_secondary(self):
        h = render("hybrid", salt("wilmington"))
        w = tile(h, "wind")
        self.assertIn('class="t-dial"', w)
        self.assertIn('class="d-mark"', w)
        self.assertIn('class="d-n"', w)
        self.assertIn('class="t-gust"', w)
        self.assertIn("Gust", w)
        self.assertIn("17", w)
        self.assertIn(">kt<", w)
        self.assertNotIn("Gust 17 kt", w)  # moved out of the old sub line into the secondary value

    def test_gust_only_still_has_no_invented_sustained_speed(self):
        h = render("hybrid", salt("wilmington", readings={
            "wind": ok({"speedKt": None, "gustKt": 22.0, "dirDeg": 40.0, "dirCompass": "NE"}, "8658163", "Wrightsville Beach"),
        }))
        w = tile(h, "wind")
        self.assertIn("gusting 22 kt (sustained speed not reported)", w)
        self.assertNotIn('class="t-gust"', w)

    def test_inshore_and_offshore_water_are_distinct(self):
        off = ok({"f": 68.2}, "41159", "Onslow Bay Outer")
        off["station"].update({"distanceMi": 36, "bearingFromAnchor": "ESE", "anchor": "Ocean City Fishing Pier"})
        h = render("hybrid", salt("wilmington", readings={
            "waterTemp": ok({"f": 60.0}, "8656483", "Beaufort, Duke Marine Lab"),
            "waterTempOffshore": off,
        }))
        w = tile(h, "water")
        # Data's label contract (main 9352476): rendered as given, never reworded.
        self.assertIn("Inshore water · Beaufort, Duke Marine Lab", w)
        self.assertIn('class="t-offread"', w)
        self.assertIn("Offshore water · buoy 41159, 36 mi ESE of Ocean City Fishing Pier", w)
        self.assertIn("68", w)
        self.assertNotIn("is-offshore", w)  # inshore is still the primary tile
        # never relabel one as the other
        self.assertTrue(w.index("Inshore water") < w.index("t-offread") < w.index("Offshore water"))

    def test_offshore_only_still_unmistakable(self):
        off = ok({"f": 68.2}, "41159", "Onslow Bay Outer")
        off["station"].update({"distanceMi": 36, "bearingFromAnchor": "ESE", "anchor": "Ocean City Fishing Pier"})
        h = render("hybrid", salt("topsail", readings={"waterTemp": OFF, "waterTempOffshore": off}))
        w = tile(h, "water")
        self.assertIn("is-offshore", w)
        self.assertIn("Offshore buoy", w)
        self.assertIn("Buoy 41159 · 36 mi ESE of Ocean City Fishing Pier", w)

    def test_tide_now_marker_and_readings_unchanged(self):
        h = render("hybrid", salt("wilmington"))
        w = tile(h, "tide")
        self.assertIn('class="s-now"', w)
        self.assertIn('class="s-nowdot"', w)
        self.assertIn('class="s-nowring"', w)
        self.assertIn('class="s-k s-k-now"', w)
        self.assertIn("Observed 2.9 ft, +0.6 vs predicted", w)
        self.assertIn("3.4 ft MLLW", w)

    def test_motto_and_brand_line_once(self):
        h = render("hybrid", salt("wilmington"))
        self.assertEqual(h.count("From the rivers to the sounds to the sea"), 1)
        self.assertEqual(h.count("Know the Water. Live the Coast."), 1)
        self.assertIn('class="wave-settle"', h)
        self.assertIn('class="mh-rule-heavy"', h)
        self.assertIn('NWS details', h)  # slim NWS strip still present
        self.assertIn('al-clear', h)


class CharacterBand(unittest.TestCase):
    def test_line_once_below_conditions_with_credited_rotation_photo(self):
        h = render("hybrid", salt("wilmington"))
        self.assertEqual(h.count("More than the forecast. It's a way of life."), 1)
        body = h[h.index("<main"):]
        self.assertLess(body.index('id="conditions"'), body.index('id="cb-life-h"'))
        self.assertLess(body.index('id="cb-life-h"'), body.index('class="hz') if 'class="hz' in body else body.index("bl-t"))
        # photo from the licensed rotation, credited, not today's horizon
        m = re.search(r'<figure class="cb-life-fig" data-photo="([^"]+)" data-category="([^"]+)"', h)
        self.assertIsNotNone(m)
        pid, cat = m.group(1), m.group(2)
        self.assertNotEqual(cat, "freshwater")
        self.assertIn('class="cb-life-cr"', h)
        # not the same id as the horizon
        hz = re.search(r'data-photo="([^"]+)"', h[h.find("hz-rot"):h.find("hz-rot") + 400] if "hz-rot" in h else "")
        if hz:
            self.assertNotEqual(pid, hz.group(1))

    def test_salt_character_band_never_uses_freshwater_or_inland_photos(self):
        h = render("hybrid", salt("wilmington"))
        m = re.search(r'<figure class="cb-life-fig" data-photo="([^"]+)"', h)
        self.assertIsNotNone(m)
        man = photo_rotation.active()
        entry = next(e for e in man["photos"] if e["id"] == m.group(1))
        self.assertTrue(photo_rotation.salt_eligible(entry))
        self.assertFalse(photo_rotation.is_inland(entry))

    def test_bodie_rights_are_in_the_manifest(self):
        man = photo_rotation.active()
        bodie = next(e for e in man["photos"] if e["id"] == "bodie-sunrise")
        self.assertTrue(bodie.get("approved"))
        self.assertIn("public domain", (bodie.get("license") or "").lower() + (bodie.get("credit") or "").lower())
        self.assertIn("National Park Service", bodie.get("credit") or "")
        self.assertTrue((bodie.get("source_url") or "").startswith("https://npgallery.nps.gov/"))


class CatchWallEmpty(unittest.TestCase):
    def test_empty_section_is_honest_and_credits_stay_stored(self):
        import catch_wall_preview as cw
        salt_p = {"id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "category": "fishing",
                  "water_type": "saltwater", "species": "Red Drum", "location": "New Bern",
                  "name": "", "w": 1600, "h": 1200, "src": {"800": "/m/s/800.webp"},
                  "status": "approved"}
        html, order = cw.body_html([salt_p], show_empty=True)
        self.assertIn("No freshwater catches on the wall yet.", html)
        self.assertIn('class="cw-empty"', html)
        self.assertIn("Community photo · Catch Wall", html)
        self.assertIn("Red Drum", html)
        # chips for both waters
        self.assertIn("chip-salt", html)
        self.assertIn("chip-fresh", html)
        self.assertIn("Catch Wall · Fishing photographs", html)
        self.assertIn("Coastal Life photographs stay on Coastal Life", html)


class FeedbackStore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        self.tmp.close()
        os.unlink(self.tmp.name)
        feedback.set_store(feedback.JsonFileStore(Path(self.tmp.name)))
        feedback.reset_rate()

    def tearDown(self):
        feedback.set_store(None)
        feedback.reset_rate()
        for p in (self.tmp.name, self.tmp.name + ".tmp"):
            if os.path.exists(p):
                os.unlink(p)

    def test_requires_one_field_and_caps_length(self):
        st, p = feedback.submit({"like": "", "confusing": "  "}, "1.1.1.1")
        self.assertEqual(st, 400)
        self.assertIn("at least one field", p["error"])
        st, p = feedback.submit({"email": "not-an-email", "like": "ok"}, "1.1.1.1")
        self.assertEqual(st, 400)
        st, p = feedback.submit({"like": "x" * 5000, "email": "ed@example.com"}, "1.1.1.1")
        self.assertEqual(st, 200)
        items = feedback.store().list()
        self.assertEqual(len(items[0]["like"]), feedback.MAX_FIELD)
        self.assertEqual(items[0]["email"], "ed@example.com")

    def test_honeypot_looks_like_success_and_is_dropped(self):
        st, p = feedback.submit({"like": "spam", "website": "http://bots.example"}, "2.2.2.2")
        self.assertEqual(st, 200)
        self.assertTrue(p["ok"])
        self.assertEqual(feedback.store().list(), [])

    def test_rate_limit_per_ip(self):
        for i in range(feedback.RATE_PER_HOUR):
            st, p = feedback.submit({"like": "ok %d" % i}, "3.3.3.3")
            self.assertEqual(st, 200, p)
        st, p = feedback.submit({"like": "one too many"}, "3.3.3.3")
        self.assertEqual(st, 429)
        st, p = feedback.submit({"like": "other ip"}, "4.4.4.4")
        self.assertEqual(st, 200)

    def test_admin_list_and_embed_markup(self):
        feedback.submit({"bugs": "tide typo", "page": "/"}, "5.5.5.5")
        listing = feedback.admin_list()
        self.assertTrue(listing["ok"])
        self.assertEqual(listing["items"][0]["bugs"], "tide typo")
        html = feedback.embed_html()
        self.assertIn("What do you like?", html)
        self.assertIn("What’s confusing?", html)
        self.assertIn("What’s missing?", html)
        self.assertIn("Bugs or wrong information", html)
        self.assertIn('name="website"', html)
        self.assertIn("/api/feedback", html)
        sent = feedback.page_html(sent=True).decode()
        self.assertIn(feedback.SENT, sent)


class DataLabelPresentation(unittest.TestCase):
    """Fit data/audit-nov16 label fields without merging that branch or rewording strings."""

    def _water(self, **kw):
        t = sprint_home._tile(id="water", name="Water", num="63", unit="°F", note="Inshore station")
        t.update(kw)
        return sprint_home.tile_html(t)

    def test_renders_label_and_offshore_label_verbatim(self):
        lab = "Inshore water · Beaufort, Duke Marine Lab"
        off = "Offshore water · buoy 41159, 37 mi SSW of Beaufort Inlet"
        html = self._water(label=lab, offshore_label=off, off_read={"num": "66", "unit": "°F", "src": "should not appear"})
        self.assertIn(lab, html)
        self.assertIn(off, html)
        self.assertIn('class="t-label"', html)
        self.assertNotIn("Inshore station", html)
        self.assertNotIn("Offshore buoy", html)
        self.assertNotIn("should not appear", html)
        self.assertIn('class="t-off-num"', html)
        self.assertIn(">66<", html)

    def test_escapes_label_fields(self):
        html = self._water(label="Inshore water · <b>x</b>", offshore_label="Offshore water · buoy <script>")
        self.assertIn("Inshore water · &lt;b&gt;x&lt;/b&gt;", html)
        self.assertIn("buoy &lt;script&gt;", html)

    def test_falls_back_without_new_fields(self):
        html = self._water(off_read={
            "num": "68", "unit": "°F",
            "src": "Buoy 41159 · 36 mi ESE of Ocean City Fishing Pier",
            "when": "10:00 AM",
        })
        self.assertIn("Inshore station", html)
        self.assertIn("Offshore buoy", html)
        self.assertIn("Buoy 41159 · 36 mi ESE of Ocean City Fishing Pier", html)
        self.assertIn("10:00 AM", html)

    def test_stale_offshore_suffix_is_muted(self):
        html = self._water(
            label="Inshore water · Beaufort, Duke Marine Lab",
            offshore_label="Offshore water · buoy 41159, 37 mi SSW of Beaufort Inlet",
            off_read={"num": "66", "unit": "°F"},
            sub="Offshore buoy 41159 (37 mi SSW): 66°F (stale, last report 6:12 AM ET)",
        )
        self.assertIn('class="t-offread is-stale"', html)
        self.assertIn('class="t-stale"', html)
        self.assertIn("(stale, last report 6:12 AM ET)", html)
        self.assertNotIn("Offshore buoy 41159 (37 mi SSW): 66°F", html)

    def test_nags_head_tide_strings_pass_through(self):
        obs = "Observed at Duck Pier (21 mi NNW): 2.9 ft, +0.6 vs predicted there"
        src = "NOAA · 8651370 · curve from Duck Pier · 8651370"
        html = sprint_home.tile_html(sprint_home._tile(
            id="tide", name="Tide", num="2.9", unit="ft", obs=obs, src=src,
        ))
        self.assertIn(obs, html)
        self.assertIn("curve from Duck Pier · 8651370", html)
        self.assertIn('t-obs', html)

    def test_curve_from_in_legend_and_aria(self):
        now = sprint_home._now_ms()
        curve = [[now - 4 * 3600e3 + i * 6 * 60 * 1000, 2.0] for i in range(200)]
        html = sprint_home._tide_spark({"curve": curve, "events": [], "curve_from": "Duck Pier"})
        self.assertIn("Predicted · Duck Pier", html)
        self.assertIn("6-minute NOAA predictions from Duck Pier", html)
        plain = sprint_home._tide_spark({"curve": curve, "events": []})
        self.assertIn(">Predicted</span>", plain)
        self.assertNotIn("Duck Pier", plain)

    def test_long_strings_and_unknown_alert_css(self):
        css = (ROOT / "preview/sprint-home/hybrid.css").read_text()
        self.assertIn("overflow-wrap:anywhere", css)
        self.assertIn(".t-swell.is-off", css)
        self.assertIn(".al-unknown", css)
        self.assertIn(".t-stale", css)
        # unknown must not reuse the earlier advisory amber left edge as the only rule
        unknown_block = css.split("Could-not-check alerts")[1]
        self.assertIn("#6F6A60", unknown_block)
        self.assertNotIn("#B7791F", unknown_block)
        styles = (ROOT / "styles.css").read_text()
        self.assertIn(".dash-alert.is-unknown", styles)
        self.assertIn(".dash-alert.is-unknown .al-dot", styles)
        block = styles.split(".dash-alert.is-unknown")[1].split(".al-item")[0]
        self.assertIn("#8A8580", block)
        self.assertNotIn("seaglass", block)
        self.assertNotIn("--d-inst-2", block)


if __name__ == "__main__":
    unittest.main()
