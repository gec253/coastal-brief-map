"""First-paint homepage conditions come from the same assemble() payload."""
import json
import unittest
from pathlib import Path

import homepage_boot

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = Path("/tmp/cb-shot/cond.json")


class HomepageBoot(unittest.TestCase):
    def test_render_matches_dashboard_shape(self):
        if not FIXTURE.is_file():
            # Fall back to a tiny synthetic payload so the suite can run offline.
            d = {
                "ok": True,
                "generatedAt": "2026-11-14T14:18:42Z",
                "region": {"id": "crystal-coast", "name": "Morehead City · Beaufort", "area": "Crystal Coast, North Carolina"},
                "readings": {
                    "wind": {"status": "ok", "values": {"speedKt": 13.0, "gustKt": 17.1, "dirCompass": "NNW"}},
                    "seas": {"status": "ok", "values": {"heightFt": 4.6, "dominantPeriodS": 5.0, "meanDirCompass": "N"}},
                    "waterTemp": {"status": "ok", "values": {"f": 62.4}},
                },
                "tides": {"status": "ok", "events": [{"t": 1794671880000, "v": 3.5, "type": "H"}]},
                "alerts": {
                    "status": "ok",
                    "items": [{
                        "event": "Freeze Warning",
                        "ends": "2026-11-15T09:00:00-05:00",
                        "areas": "Beaufort; Carteret",
                    }],
                },
            }
        else:
            d = json.loads(FIXTURE.read_text())
        glance = homepage_boot.render_glance_html(d)
        self.assertIn('id="glance-strip"' if False else 'class="gs-cell', glance)
        self.assertIn('href="#i-wind"', glance)
        self.assertIn('href="#i-seas"', glance)
        self.assertIn("°F", glance)
        inner, cls = homepage_boot.render_alerts_html(d.get("alerts"))
        if (d.get("alerts") or {}).get("items"):
            self.assertEqual(cls, "is-active")
            self.assertIn("al-meta", inner)
            self.assertIn("until ", inner)
            self.assertIn(" ET", inner)
        self.assertIn("NWS details", inner)
        self.assertEqual(homepage_boot.et_time("2026-11-15T09:00:00-05:00"), "Sun 9:00 AM ET")

    def test_inject_adds_boot_json_and_replaces_skeleton(self):
        src = (ROOT / "index.html").read_bytes()
        d = {
            "ok": True,
            "generatedAt": "2026-11-14T14:18:42Z",
            "region": {"id": "crystal-coast", "name": "Morehead City · Beaufort", "area": "Crystal Coast, North Carolina"},
            "readings": {
                "wind": {"status": "ok", "values": {"speedKt": 13.0, "gustKt": 17.1, "dirCompass": "NNW"}},
                "seas": {"status": "ok", "values": {"heightFt": 4.6, "dominantPeriodS": 5.0, "meanDirCompass": "N"}},
                "waterTemp": {"status": "ok", "values": {"f": 62.4}},
            },
            "tides": {"status": "ok", "events": [{"t": 1794671880000, "v": 3.5, "type": "H"}]},
            "alerts": {
                "status": "ok",
                "items": [{
                    "event": "Freeze Warning",
                    "ends": "2026-11-15T09:00:00-05:00",
                    "areas": "Beaufort; Carteret",
                }],
            },
        }
        listed = {"ok": True, "default": "crystal-coast", "regions": [{"id": "crystal-coast", "name": "Morehead City · Beaufort"}]}
        # Patch assemble/listed for a hermetic inject.
        real_listed = homepage_boot.conditions.listed_regions
        real_assemble = homepage_boot.conditions.assemble
        homepage_boot.conditions.listed_regions = lambda preview=False: listed
        homepage_boot.conditions.assemble = lambda region_id=None, preview=False: (200, d)
        try:
            out = homepage_boot.inject(src, "crystal-coast", preview=False)
        finally:
            homepage_boot.conditions.listed_regions = real_listed
            homepage_boot.conditions.assemble = real_assemble
        self.assertIn(b'id="cb-boot-conditions"', out)
        self.assertIn(b'id="cb-boot-regions"', out)
        self.assertIn(b"Freeze Warning", out)
        self.assertIn(b"until Sun 9:00 AM ET", out)
        self.assertIn(b"NNW 13 kt", out)
        self.assertIn(b"Updated 9:18 AM ET", out)
        self.assertNotIn(b"Checking NWS alerts", out)
        self.assertNotIn(b"Loading readings", out)
        self.assertNotIn(b"is-booting", out)
        self.assertNotIn(b"<!--boot-json-->", out)
