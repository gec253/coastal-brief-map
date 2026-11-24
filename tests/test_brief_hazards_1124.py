"""Morning Brief hazard rows (t448u, Nov 24, 2026).

Regression for the Nov 24 5:15 AM briefs: Hatteras omitted the Pamlico Sound Small Craft
Advisory (AMZ135) and Crystal Coast's Coastal Flood Watch omitted West Carteret (NCZ195).
Root cause: conditions.alerts_block (and freshwater.alerts_point) drop any alert whose
(event, end time) matches an earlier one, so a second NWS product with the same end time
vanished. Those files are protected public files, so the brief re-reads the same raw NWS feed
(same URL, same cache) and keeps every distinct alert (brief._official_alerts).
"""
from __future__ import annotations

import copy
import json
import re
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import brief
import brief_format
import conditions
from test_brief_refine_1123 import _salt_payload

FIX = json.loads((ROOT / "tests" / "fixtures" / "nws-alerts-2026-11-24.json").read_text())
ISSUE = datetime(2026, 11, 24, 10, 15, tzinfo=timezone.utc)   # Tue 5:15 AM ET
VIEW = datetime(2026, 11, 24, 11, 30, tzinfo=timezone.utc)    # Tue 6:30 AM ET
ZONES = {"crystal-coast": ["AMZ158", "AMZ156", "NCZ195", "NCZ196"],
         "hatteras": ["AMZ154", "AMZ152", "AMZ135", "NCZ205"]}


def _feed(zones):
    """What api.weather.gov returns for ?zone=...: every alert touching any listed zone."""
    feats = [f for f in FIX["features"] if set(f["properties"]["geocode"]["UGC"]) & set(zones)]
    return {"type": "FeatureCollection", "features": copy.deepcopy(feats)}


def _shared_block(rid):
    """What conditions.alerts_block hands the brief today (protected file, unchanged)."""
    with patch("conditions.nws_json", return_value=_feed(ZONES[rid])):
        return conditions.alerts_block(ZONES[rid])


def _block(rid):
    """The brief's own alert list from the same raw feed."""
    shared = _shared_block(rid)
    with patch("conditions.nws_json", return_value=_feed(ZONES[rid])) as m:
        out = brief._official_alerts(shared, "https://api.weather.gov/alerts/active?status=actual&zone=" + ",".join(ZONES[rid]),
                                     lambda u: conditions.nws_json(u, conditions.TTL_ALERTS))
    return out


def _rows(hz):
    return (hz.get("current") or []) + (hz.get("upcoming") or [])


class AlertSource(unittest.TestCase):
    def test_shared_block_still_collapses_root_cause_documented(self):
        # Documents the root cause in the protected shared fetcher (left unchanged on this branch).
        sca = [a for a in _shared_block("hatteras")["items"] if a["event"] == "Small Craft Advisory"]
        self.assertEqual(len(sca), 1)
        cfw = [a for a in _shared_block("crystal-coast")["items"] if a["event"] == "Coastal Flood Watch"]
        self.assertEqual(len(cfw), 1)
        self.assertNotIn("West Carteret", cfw[0]["areas"])

    def test_raw_feed_unavailable_falls_back_to_shared_block(self):
        shared = _shared_block("hatteras")
        out = brief._official_alerts(shared, "u", lambda u: None)
        self.assertEqual(out["items"], shared["items"])
        out = brief._official_alerts({"status": "unavailable", "items": []}, "u", lambda u: {"features": []})
        self.assertEqual(out["status"], "unavailable")

    def test_hatteras_keeps_pamlico_sound_sca(self):
        items = _block("hatteras")["items"]
        sca = [a for a in items if a["event"] == "Small Craft Advisory"]
        self.assertEqual(len(sca), 2)
        self.assertTrue(any("AMZ135" in a["ugc"] and a["areas"] == "Pamlico Sound" for a in sca))

    def test_crystal_keeps_west_carteret_flood_watch(self):
        items = _block("crystal-coast")["items"]
        cfw = [a for a in items if a["event"] == "Coastal Flood Watch"]
        self.assertEqual(len(cfw), 2)
        self.assertTrue(any("NCZ195" in a["ugc"] and "West Carteret" in a["areas"] for a in cfw))

    def test_replaced_alert_is_skipped_but_its_replacement_stays(self):
        items = _block("crystal-coast")["items"]
        self.assertFalse(any("has been replaced" in (a.get("headline") or "") for a in items))
        self.assertTrue(any(a["event"] == "Gale Warning" for a in items))

    def test_only_actual_and_exact_duplicates_dropped(self):
        feed = _feed(ZONES["hatteras"])
        dup = copy.deepcopy(feed["features"][0])
        test = copy.deepcopy(feed["features"][1]); test["properties"]["status"] = "Test"; test["properties"]["id"] = "x-test"
        feed["features"] += [dup, test]
        items = brief_format.nws_alert_items(feed["features"])
        ids = [a["id"] for a in items]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertNotIn("x-test", ids)

    def test_full_official_text_is_kept(self):
        a = _block("hatteras")["items"][0]
        for k in ("headline", "description", "id", "ugc", "severity"):
            self.assertTrue(a.get(k), k)

    def test_falls_lake_brief_reads_raw_point_feed(self):
        feed = _feed(["AMZ135"])
        feed["features"] += copy.deepcopy(_feed(["AMZ152"])["features"])
        seen = []
        def fake(url, ttl):
            seen.append(url)
            return feed
        shared = {"status": "ok", "items": [{"event": "Small Craft Advisory", "ends": "x"}]}
        out = brief._official_alerts(shared, "https://api.weather.gov/alerts/active?status=actual&point=35.9411,-78.5833",
                                     lambda u: fake(u, 300))
        self.assertEqual(len([a for a in out["items"] if a["event"] == "Small Craft Advisory"]), 2)
        self.assertTrue(all(a.get("onset") for a in out["items"]))
        self.assertIn("point=35.9411,-78.5833", seen[0])


class Grouping(unittest.TestCase):
    def test_hatteras_rows(self):
        hz = brief_format.format_hazards(_block("hatteras"), ISSUE)
        rows = _rows(hz)
        sca = [r for r in rows if r["event"] == "Small Craft Advisory"]
        # Same event, same onset and end: one row, union of areas, both products' full text.
        self.assertEqual(len(sca), 1)
        self.assertIn("Pamlico Sound", sca[0]["areas"])
        self.assertIn("S of Oregon Inlet NC to Cape Hatteras NC out to 20 NM", sca[0]["areas"])
        self.assertIn("AMZ135", sca[0]["ugc"])
        self.assertIn("Pamlico Sound", sca[0]["local"])
        self.assertEqual(len(sca[0]["products"]), 2)
        self.assertEqual(sca[0]["status"], "current")
        # Different end times stay separate rows.
        gw = [r for r in rows if r["event"] == "Gale Watch"]
        self.assertEqual(len(gw), 2)
        self.assertIn("Pamlico Sound", hz["line"])
        self.assertIn("Small Craft Advisory now in effect until Wed 4:00 PM ET", hz["line"])

    def test_crystal_flood_watch_includes_west_carteret(self):
        hz = brief_format.format_hazards(_block("crystal-coast"), ISSUE)
        cfw = [r for r in _rows(hz) if r["event"] == "Coastal Flood Watch"]
        self.assertEqual(len(cfw), 1)
        self.assertIn("West Carteret", cfw[0]["areas"])
        self.assertIn("East Carteret", cfw[0]["areas"])
        self.assertEqual(set(cfw[0]["localUgc"]), {"NCZ195", "NCZ196"})
        self.assertIn("West Carteret", hz["line"])

    def test_no_distinct_alert_lost(self):
        for rid in ZONES:
            block = _block(rid)
            hz = brief_format.format_hazards(block, ISSUE)
            covered = set()
            for r in _rows(hz):
                covered |= {p["id"] for p in r["products"]}
            self.assertEqual(covered, {a["id"] for a in block["items"]}, rid)

    def test_warnings_sort_first(self):
        hz = brief_format.format_hazards(_block("crystal-coast"), ISSUE)
        self.assertEqual(hz["upcoming"][0]["event"], "Gale Warning")

    def test_kind(self):
        self.assertEqual(brief_format.hazard_kind("Gale Warning"), "warning")
        self.assertEqual(brief_format.hazard_kind("Coastal Flood Watch"), "watch")
        self.assertEqual(brief_format.hazard_kind("Small Craft Advisory"), "advisory")
        self.assertEqual(brief_format.hazard_kind("Special Marine Warning"), "warning")
        self.assertEqual(brief_format.hazard_kind("Rip Current Statement"), "statement")


class Page(unittest.TestCase):
    def _page(self, rid, view=VIEW):
        payload = _salt_payload()
        payload["alerts"] = _shared_block(rid)  # exactly what conditions.assemble returns
        with patch("conditions.assemble", return_value=(200, payload)), patch.object(brief, "_trend", return_value=None), \
             patch("conditions.nws_json", return_value=_feed(ZONES[rid])):
            b = brief.build_salt("crystal-coast", ISSUE)
        b.update({"regionId": rid, "issuedEt": "Tue Nov 24, 5:15 AM ET", "issuedAt": ISSUE.isoformat()})
        return b, brief.page(b, view_now=view)

    def test_rows_on_page_with_status_times_area_and_details(self):
        b, html = self._page("hatteras")
        sec = html[html.index('<section class="mb-adv is-active'):html.index("</section>", html.index('<section class="mb-adv is-active'))]
        rows = re.findall(r'<li class="mb-hz-row k-(\w+) s-(\w+)">', sec)
        self.assertEqual(len(rows), 5)
        self.assertIn(("advisory", "current"), rows)
        self.assertIn(("warning", "current"), rows)  # Gale Warning began 6:00 AM; page viewed 6:30 AM
        self.assertIn(">Warning</span>", sec)
        self.assertIn(">CURRENT</span>", sec)
        self.assertIn(">UPCOMING</span>", sec)
        self.assertIn("Pamlico Sound", sec)
        self.assertIn("Wed 4:00 PM ET", sec)
        self.assertEqual(sec.count("<details>"), 5)
        self.assertIn("* WHAT...", sec)
        self.assertIn("showsigwx.php?warnzone=", sec)
        self.assertNotIn("has been replaced", sec)
        sca = re.search(r'Small Craft Advisory</span>.*?</summary>', sec, re.S).group(0)
        self.assertIn("Pamlico Sound", sca)
        self.assertIn("Tue 4:22 AM", sca)
        self.assertIn('class="mb-adv-stored"', sec)

    def test_crystal_page_names_west_carteret_in_summary(self):
        _, html = self._page("crystal-coast")
        m = re.search(r'Coastal Flood Watch</span>.*?</summary>', html, re.S)
        self.assertIn("West Carteret", m.group(0))
        self.assertIn("East Carteret", m.group(0))

    def test_hazards_precede_glance_outlook_astro(self):
        _, html = self._page("hatteras")
        a = html.index('class="mb-adv'); g = html.index('class="mb-glance')
        self.assertLess(a, g)

    def test_ended_rows_marked_not_dropped(self):
        later = datetime(2026, 11, 25, 22, 0, tzinfo=timezone.utc)  # Wed 5:00 PM ET, SCA ended 4:00 PM
        _, html = self._page("hatteras", view=later)
        self.assertRegex(html, r'k-advisory s-ended">.*?Small Craft Advisory')
        self.assertIn(">ENDED</span>", html)

    def test_legacy_snapshot_rows_still_render(self):
        legacy = json.loads((ROOT / "tests" / "fixtures" / "brief-hatteras-sample.json").read_text())
        legacy["hazards"] = {"status": "active", "current": [{
            "event": "Small Craft Advisory", "status": "current", "onset": "2026-11-24T04:22:00-05:00",
            "ends": "2026-11-25T16:00:00-05:00", "areas": "S of Oregon Inlet NC to Cape Hatteras NC out to 20 NM",
            "text": "Small Craft Advisory now in effect until Wed 4:00 PM ET."}], "upcoming": [], "line": "x"}
        html = brief.page(legacy, view_now=VIEW)
        self.assertIn("mb-hz-row k-advisory s-current", html)
        self.assertIn("Small Craft Advisory now in effect until Wed 4:00 PM ET.", html)


if __name__ == "__main__":
    unittest.main()
