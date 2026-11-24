"""Shared NWS alert fetchers keep every distinct alert (t449u, Nov 24, 2026).

conditions.alerts_block feeds the homepage hybrid alert box (sprint_home / homepage_boot first
paint), the Full Dashboard alert panel (dashboard.js renderAlerts via /api/conditions), the tiles
lab, and the Morning Brief fallback. freshwater.alerts_point feeds the freshwater region pages
(lake.js). Both keyed on (event, ends) and dropped the Pamlico Sound Small Craft Advisory (AMZ135)
and the West Carteret Coastal Flood Watch (NCZ195) on Nov 24. Fixture: the real Nov 24 feed.
"""
from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import conditions
import freshwater
import homepage_boot
import sprint_home

FIX = json.loads((ROOT / "tests" / "fixtures" / "nws-alerts-2026-11-24.json").read_text())
REGIONS = {r["id"]: r for r in json.loads((ROOT / "data" / "regions.json").read_text())["regions"]}


def _feed(zones):
    feats = [f for f in FIX["features"] if set(f["properties"]["geocode"]["UGC"]) & set(zones)]
    return {"type": "FeatureCollection", "features": copy.deepcopy(feats)}


def _block(rid):
    zones = REGIONS[rid]["alertZones"]
    with patch("conditions.nws_json", return_value=_feed(zones)):
        return conditions.alerts_block(zones)


def _ev(block, event):
    return [a for a in block["items"] if a["event"] == event]


class SharedBlock(unittest.TestCase):
    def test_hatteras_keeps_pamlico_sound_sca(self):
        sca = _ev(_block("hatteras"), "Small Craft Advisory")
        areas = "; ".join(a["areas"] for a in sca)
        self.assertIn("Pamlico Sound", areas)
        self.assertIn("S of Oregon Inlet NC to Cape Hatteras NC out to 20 NM", areas)

    def test_crystal_coast_cfw_includes_west_carteret(self):
        cfw = _ev(_block("crystal-coast"), "Coastal Flood Watch")
        areas = "; ".join(a["areas"] for a in cfw)
        self.assertIn("West Carteret", areas)
        self.assertIn("East Carteret", areas)

    def test_merge_only_when_event_onset_end_match(self):
        # Hatteras Gale Watches end at different times: two rows, never merged.
        gw = _ev(_block("hatteras"), "Gale Watch")
        self.assertEqual(len(gw), 2)
        self.assertEqual(len({a["ends"] for a in gw}), 2)
        for b in (_block("hatteras"), _block("crystal-coast")):
            keys = [(a["event"], a["onset"], a["ends"]) for a in b["items"]]
            self.assertEqual(len(keys), len(set(keys)))

    def test_every_actual_unreplaced_area_is_listed(self):
        for rid in ("hatteras", "crystal-coast"):
            b = _block(rid)
            for f in _feed(REGIONS[rid]["alertZones"])["features"]:
                p = f["properties"]
                if conditions._nws_replaced(p):
                    continue
                rows = [a for a in b["items"] if a["event"] == p["event"] and a["ends"] == (p.get("ends") or p.get("expires"))]
                for part in p["areaDesc"].split(";"):
                    self.assertTrue(any(part.strip() in a["areas"] for a in rows), (rid, p["event"], part))

    def test_replaced_gale_watch_skipped_and_warning_kept(self):
        b = _block("crystal-coast")
        self.assertFalse(any("has been replaced" in (a["headline"] or "") for a in b["items"]))
        self.assertEqual(len(_ev(b, "Gale Warning")), 1)

    def test_status_actual_filter_kept(self):
        zones = REGIONS["hatteras"]["alertZones"]
        feed = _feed(zones)
        for f in feed["features"]:
            f["properties"]["status"] = "Test"
        with patch("conditions.nws_json", return_value=feed):
            self.assertEqual(conditions.alerts_block(zones)["items"], [])

    def test_output_fields_unchanged(self):
        for a in _block("hatteras")["items"]:
            self.assertEqual(set(a), {"event", "headline", "severity", "areas", "onset", "ends", "sender"})

    def test_unavailable_unchanged(self):
        with patch("conditions.nws_json", return_value=None):
            self.assertEqual(conditions.alerts_block(["AMZ135"]), {"status": "unavailable", "items": []})


class Consumers(unittest.TestCase):
    def test_homepage_first_paint_and_dashboard_box_show_both(self):
        html, cls = homepage_boot.render_alerts_html(_block("hatteras"))
        self.assertIn("is-active", cls)
        self.assertIn("Pamlico Sound", html)
        html, _ = homepage_boot.render_alerts_html(_block("crystal-coast"))
        self.assertIn("West Carteret", html)

    def test_hybrid_alert_box_rows_and_flag(self):
        a = sprint_home._alerts(_block("hatteras"))
        self.assertEqual(a["state"], "active")
        self.assertIn("Small Craft Advisory", [i["event"] for i in a["items"]])
        # Flag logic unchanged: Gale Warning still the highest flag.
        with patch("sprint_home._ended", return_value=False):
            self.assertEqual(sprint_home.flag_for(_block("hatteras")), "pennant2")

    def test_freshwater_point_keeps_distinct_products(self):
        feed = _feed(["AMZ150", "AMZ152", "AMZ135", "NCZ195", "NCZ196"])
        with patch("freshwater._get_json", return_value=feed):
            out = freshwater.alerts_point(35.0, -76.0)
        self.assertEqual(out["status"], "ok")
        areas = "; ".join(a["areas"] for a in out["items"])
        self.assertIn("Pamlico Sound", areas)
        self.assertIn("West Carteret", areas)
        for a in out["items"]:
            self.assertEqual(set(a), {"event", "severity", "areas", "ends", "headline"})
        with patch("freshwater._get_json", return_value=None):
            self.assertEqual(freshwater.alerts_point(35.0, -76.0), {"status": "unavailable", "items": []})


if __name__ == "__main__":
    unittest.main()
