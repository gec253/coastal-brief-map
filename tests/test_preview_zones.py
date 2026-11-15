"""Official NWS alert-area names and the no-alerts calm tint on preview briefs."""
from __future__ import annotations

import re
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import brief  # noqa: E402
import brief_preview  # noqa: E402
import brief_strings  # noqa: E402
import conditions  # noqa: E402
import preview_alerts  # noqa: E402
import preview_copy  # noqa: E402
import preview_zones  # noqa: E402

NOW = datetime(2026, 11, 14, 15, 0, tzinfo=timezone.utc)
ZONE_RE = re.compile(r"\b(?:AMZ|NCZ|NCC)\d+\b")

# Official display phrases, from names fetched 15 Nov 2026.
EXPECTED = {
    "wilmington": "Coastal waters from Surf City to Cape Fear NC out 20 nm; Coastal New Hanover",
    "nags-head": (
        "S of Currituck Beach Light NC to Oregon Inlet NC out to 20 nm; "
        "Northern Outer Banks; Croatan and Roanoke Sounds"
    ),
    "emerald-isle": "S of Cape Lookout NC to Surf City NC out to 20 nm; West Carteret",
    "topsail": (
        "Coastal Onslow; Coastal Pender; S of Cape Lookout NC to Surf City NC out to 20 nm; "
        "Coastal waters from Surf City to Cape Fear NC out 20 nm"
    ),
    "neuse-river": "Wake, Johnston and Wayne counties",
    "jordan-lake": "Chatham and Durham counties",
    "cape-fear": "Harnett, Cumberland and Bladen counties",
}

# New preview regions: derive the alerts phrase so a later grouping/casing
# change in format_alert_areas does not require a hardcoded rewrite here.
NEW_COASTAL = ("carolina-kure", "corolla-duck")
COASTAL_RIDS = ("wilmington", "nags-head", "emerald-isle", "topsail") + NEW_COASTAL


def _phrase(rid: str) -> str:
    if rid in EXPECTED:
        return EXPECTED[rid]
    return preview_zones.format_alert_areas(_codes(rid))

CAPE_FEAR_ZONES = ["NCZ077", "NCC085", "NCZ088", "NCC051", "NCZ096", "NCC017"]


def _codes(rid: str) -> list[str]:
    if rid == "cape-fear":
        return list(CAPE_FEAR_ZONES)
    ids = preview_alerts.zone_ids(rid=rid)
    if ids:
        return ids
    cfg = next(r for r in conditions.load_regions()["regions"] if r["id"] == rid)
    return list(cfg.get("alertZones") or [])


def _adv(html: str):
    m = re.search(
        r'<section class="mb-adv is-([^"]+)"[^>]*>.*?<p class="mb-adv-t">(.*?)</p>',
        html, flags=re.S,
    )
    return (m.group(1), m.group(2)) if m else (None, None)


def _sources_blob(html: str) -> str:
    bits = []
    m = re.search(r'<details class="mb-sources" id="mb-sources">.*?</details>', html, flags=re.S)
    if m:
        bits.append(m.group(0))
    m = re.search(r'<script type="application/json" id="cb-reading-sources">.*?</script>', html, flags=re.S)
    if m:
        bits.append(m.group(0))
    return "\n".join(bits)


def _take_alert_text(html: str) -> str:
    m = re.search(r'<section class="mb-summary mb-take"[^>]*>(.*?)</section>', html, flags=re.S)
    if not m:
        return ""
    hits = [p for p in re.findall(r"<p[^>]*>(.*?)</p>", m.group(1), flags=re.S)
            if "NWS alert" in p or "Alerts:" in p or "is in effect" in p]
    return re.sub(r"<[^>]+>", "", " ".join(hits))


class ZoneNameMap(unittest.TestCase):
    def test_every_required_code_has_official_name_and_source(self):
        required = {
            "AMZ158", "AMZ250", "AMZ150", "AMZ231",
            "NCZ195", "NCZ108", "NCZ203", "NCZ102", "NCZ199", "NCZ106",
            "NCZ041", "NCZ042", "NCZ078", "NCZ040", "NCZ025",
            "NCZ077", "NCZ088", "NCZ096",
            "NCC183", "NCC101", "NCC191", "NCC037", "NCC063",
            "NCC085", "NCC051", "NCC017",
        }
        self.assertEqual(required, set(preview_zones.ZONE_NAMES))
        for code, rec in preview_zones.ZONE_NAMES.items():
            self.assertEqual(preview_zones.official_name(code), rec["name"])
            self.assertTrue(rec["name"], code)
            self.assertTrue(rec["source"].startswith("https://api.weather.gov/zones/"), code)
            self.assertIn(code, rec["source"], code)
            self.assertEqual(rec["fetched"], "2026-11-15", code)
            # Names are the official NWS string, not a rewritten paraphrase.
            self.assertNotIn(code, rec["name"])

    def test_display_appends_county_only_for_bare_county_names(self):
        self.assertEqual(preview_zones.display_name("NCZ041"), "Wake County")
        self.assertEqual(preview_zones.display_name("NCC183"), "Wake County")
        self.assertEqual(preview_zones.display_name("NCZ195"), "West Carteret")
        self.assertEqual(preview_zones.display_name("NCZ108"), "Coastal New Hanover")
        self.assertEqual(preview_zones.display_name("NCZ102"), "Eastern Currituck")
        self.assertEqual(preview_zones.display_name("NCZ203"), "Northern Outer Banks")
        self.assertEqual(
            preview_zones.display_name("AMZ158"),
            "S of Cape Lookout NC to Surf City NC out to 20 nm",
        )

    def test_dedupes_forecast_and_county_for_the_same_county(self):
        self.assertEqual(
            preview_zones.format_alert_areas(["NCZ041", "NCC183", "NCZ042", "NCC101", "NCZ078", "NCC191"]),
            EXPECTED["neuse-river"],
        )
        self.assertEqual(
            preview_zones.format_alert_areas(["NCZ040", "NCC037"]),
            "Chatham County",
        )
        self.assertEqual(
            preview_zones.format_alert_areas(CAPE_FEAR_ZONES),
            EXPECTED["cape-fear"],
        )

    def test_fallback_keeps_unknown_codes(self):
        self.assertEqual(preview_zones.display_name("AMZ999"), "AMZ999")
        self.assertEqual(preview_zones.official_name("AMZ999"), None)
        self.assertEqual(
            preview_zones.format_alert_areas(["AMZ158", "AMZ999", "NCZ195"]),
            "S of Cape Lookout NC to Surf City NC out to 20 nm; AMZ999; West Carteret",
        )

    def test_phrases_for_every_preview_and_cape_fear(self):
        for rid, phrase in EXPECTED.items():
            self.assertEqual(preview_zones.format_alert_areas(_codes(rid)), phrase, rid)

    def test_new_coastal_regions_use_official_names(self):
        for rid in NEW_COASTAL:
            phrase = preview_zones.format_alert_areas(_codes(rid))
            self.assertTrue(phrase, rid)
            self.assertFalse(ZONE_RE.search(phrase), (rid, phrase))
            for code in _codes(rid):
                self.assertIn(preview_zones.display_name(code), phrase, (rid, code, phrase))

    def test_empty_list_is_this_area(self):
        self.assertEqual(preview_zones.format_alert_areas([]), "this area")
        self.assertEqual(preview_zones.format_alert_areas(None), "this area")



    def test_groups_two_or_more_counties_and_keeps_a_single_county(self):
        self.assertEqual(
            preview_zones.format_alert_areas(["NCZ041", "NCC183", "NCZ042", "NCC101", "NCZ078", "NCC191"]),
            "Wake, Johnston and Wayne counties",
        )
        self.assertEqual(
            preview_zones.format_alert_areas(["NCZ077", "NCC085", "NCZ088", "NCC051", "NCZ096", "NCC017"]),
            "Harnett, Cumberland and Bladen counties",
        )
        self.assertEqual(
            preview_zones.format_alert_areas(["NCZ077", "NCZ088"]),
            "Harnett and Cumberland counties",
        )
        self.assertEqual(preview_zones.format_alert_areas(["NCZ040", "NCC037"]), "Chatham County")
        self.assertEqual(preview_zones.county_group(["Chatham"]), "Chatham County")

    def test_non_county_land_zones_keep_official_names(self):
        for code, name in (
            ("NCZ195", "West Carteret"),
            ("NCZ108", "Coastal New Hanover"),
            ("NCZ203", "Northern Outer Banks"),
            ("NCZ199", "Coastal Onslow"),
            ("NCZ106", "Coastal Pender"),
        ):
            self.assertEqual(preview_zones.official_name(code), name)
            self.assertEqual(preview_zones.display_name(code), name)
            self.assertIn(name, preview_zones.format_alert_areas([code]))
            self.assertFalse(preview_zones._is_bare_county(preview_zones.ZONE_NAMES[code]))

    def test_marine_normalizes_nm_casing_and_leaves_out_to_as_published(self):
        self.assertEqual(
            preview_zones.official_name("AMZ158"),
            "S of Cape Lookout NC to Surf City NC out to 20 NM",
        )
        self.assertEqual(
            preview_zones.normalize_marine_name(preview_zones.official_name("AMZ158")),
            "S of Cape Lookout NC to Surf City NC out to 20 nm",
        )
        self.assertIn("out to 20 nm", preview_zones.format_alert_areas(["AMZ158"]))
        self.assertNotIn("out to 20 NM", preview_zones.format_alert_areas(["AMZ158"]))
        # AMZ250 is published with lowercase nm and "out 20 nm" (no "to"). Leave it.
        self.assertEqual(
            preview_zones.official_name("AMZ250"),
            "Coastal waters from Surf City to Cape Fear NC out 20 nm",
        )
        self.assertIn("out 20 nm", preview_zones.format_alert_areas(["AMZ250"]))
        self.assertNotIn("out to 20 nm", preview_zones.format_alert_areas(["AMZ250"]))

    def test_joins_without_an_oxford_comma(self):
        self.assertEqual(preview_zones.join_names(["A", "B", "C"]), "A, B and C")
        self.assertEqual(preview_zones.join_names(["A", "B"]), "A and B")
        for rid in ("neuse-river", "cape-fear"):
            phrase = preview_zones.format_alert_areas(_codes(rid))
            self.assertNotIn(", and ", phrase, rid)
            self.assertEqual(phrase, EXPECTED[rid], rid)

    def test_mixed_items_use_semicolons_and_keep_and_in_a_name(self):
        self.assertEqual(
            preview_zones.format_alert_areas(_codes("nags-head")),
            EXPECTED["nags-head"],
        )
        self.assertIn("Croatan and Roanoke Sounds", EXPECTED["nags-head"])
        self.assertNotIn("Northern Outer Banks and Croatan", EXPECTED["nags-head"])
        # Mixed marine + bare counties + a qualified land zone: semicolons,
        # each bare county as "{Name} County", first-seen order.
        self.assertEqual(
            preview_zones.format_alert_areas(["AMZ158", "NCZ041", "NCZ195", "NCZ042"]),
            "S of Cape Lookout NC to Surf City NC out to 20 nm; Wake County; West Carteret; Johnston County",
        )
        self.assertEqual(
            preview_zones.format_alert_areas(_codes("wilmington")),
            EXPECTED["wilmington"],
        )
        self.assertIn("; ", EXPECTED["wilmington"])
        self.assertNotIn(" nm and ", EXPECTED["wilmington"])


class VisibleAlertsUseNames(unittest.TestCase):
    def test_coastal_item_and_take_use_names_not_codes(self):
        cfg = {r["id"]: r for r in conditions.load_regions()["regions"]}
        for rid in COASTAL_RIDS:
            payload = {
                "ok": True, "region": {"id": rid, "anchor": cfg[rid]["anchor"]},
                "readings": {}, "alerts": {"status": "ok", "items": []},
            }
            body = preview_copy.relabel_salt(
                rid, {"items": [], "missing": [], "freshness": [], "take": []}, payload, cfg[rid]
            )
            line = dict(body["items"])["Alerts"]
            self.assertEqual(line, brief_strings.alerts_none(_phrase(rid))[len("Alerts: "):], rid)
            self.assertFalse(ZONE_RE.search(line), (rid, line))
            take = preview_copy.take_text(preview_copy.captains_take(rid, body, payload, cfg[rid], now=NOW))
            self.assertIn(brief_strings.alerts_none(_phrase(rid)), take, rid)
            # Codes may still appear as marine-forecast attribution in the Take;
            # the alerts clause itself must use names.
            alert_clause = [s for s in take.split(". ") if "No active NWS alerts" in s]
            self.assertTrue(alert_clause, rid)
            self.assertFalse(ZONE_RE.search(alert_clause[0]), (rid, alert_clause[0]))

    def test_freshwater_alert_line_uses_official_names(self):
        none = {"status": "ok", "items": []}
        self.assertEqual(
            preview_alerts.alert_line(none, "neuse-river"),
            brief_strings.alerts_none(EXPECTED["neuse-river"]),
        )
        self.assertEqual(
            preview_alerts.alert_line(none, "jordan-lake"),
            brief_strings.alerts_none(EXPECTED["jordan-lake"]),
        )
        # Internal areas_phrase (gate reasons) is unchanged.
        self.assertEqual(
            preview_alerts.areas_phrase(rid="neuse-river"),
            "Wake, Johnston and Wayne counties",
        )
        self.assertEqual(preview_alerts.areas_phrase(rid="jordan-lake"), "Chatham and Durham counties")


class AdvisoryTint(unittest.TestCase):
    def test_hook_sets_clear_unknown_and_active(self):
        def box(kind, text):
            return (
                '<section class="mb-adv is-%s" aria-label="Alerts">'
                '<span class="mb-adv-dot" aria-hidden="true"></span>'
                '<div><p class="mb-adv-k">Alerts</p><p class="mb-adv-t">%s</p></div></section>'
            ) % (kind, text)

        html = preview_copy.apply_advisory_kind(
            box("active", "No active NWS alerts for West Carteret.")
        )
        self.assertIn('class="mb-adv is-clear"', html)
        self.assertNotIn("is-active", html)

        html = preview_copy.apply_advisory_kind(
            box("active", "Could not be checked at issue time. See weather.gov for current alerts.")
        )
        self.assertIn('class="mb-adv is-unknown"', html)
        self.assertNotIn("is-active", html)
        self.assertNotIn("is-clear", html)

        html = preview_copy.apply_advisory_kind(
            box("clear", "Small Craft Advisory until 5:00 PM ET.")
        )
        self.assertIn('class="mb-adv is-active"', html)
        self.assertNotIn("is-clear", html)
        self.assertNotIn("is-unknown", html)

        # Already-correct class is left alone.
        raw = box("clear", "No NWS marine advisories for this area.")
        self.assertEqual(preview_copy.apply_advisory_kind(raw), raw)

    def _coastal_page(self, rid, alerts):
        cfg = brief_preview._cfg(rid)
        payload = {
            "ok": True,
            "region": {"id": rid, "name": cfg["name"], "area": cfg.get("area"), "anchor": cfg["anchor"]},
            "readings": {},
            "alerts": alerts,
            "tides": {"status": "unavailable"},
        }
        body = {
            "region": payload["region"],
            "waterType": "saltwater",
            "items": [("Advisories", "No NWS marine advisories for this area."),
                      ("Wind", "10 kt from the N at X.")],
            "freshness": [], "take": [], "missing": [], "sources": "NOAA",
        }
        with patch.object(brief, "build_salt", return_value=body), \
             patch("conditions.assemble", return_value=(200, payload)):
            return brief_preview.page(brief_preview.compose(rid, NOW))

    def test_no_alerts_page_is_calm_and_codes_stay_in_sources(self):
        for rid in COASTAL_RIDS:
            html = self._coastal_page(rid, {"status": "ok", "items": []})
            kind, text = _adv(html)
            self.assertEqual(kind, "clear", rid)
            self.assertNotIn("is-active", html[html.find("mb-adv"):html.find("mb-adv") + 80])
            self.assertEqual(text, brief_strings.alerts_none(_phrase(rid))[len("Alerts: "):], rid)
            self.assertFalse(ZONE_RE.search(text), (rid, text))
            take = _take_alert_text(html)
            self.assertIn(_phrase(rid), take, rid)
            self.assertFalse(ZONE_RE.search(take), (rid, take))
            src = _sources_blob(html)
            for code in _codes(rid):
                self.assertIn(code, src, (rid, code))

    def test_failed_check_uses_unknown_not_warning(self):
        html = self._coastal_page("emerald-isle", {"status": "failed", "items": []})
        kind, text = _adv(html)
        self.assertEqual(kind, "unknown")
        self.assertIn("Could not be checked at issue time", text)
        self.assertNotIn('class="mb-adv is-active"', html)
        self.assertNotIn('class="mb-adv is-clear"', html)

    def test_real_alert_uses_warning_class(self):
        html = self._coastal_page("emerald-isle", {
            "status": "ok",
            "items": [{"event": "Small Craft Advisory", "ends": "2026-11-14T22:00:00+00:00"}],
        })
        kind, text = _adv(html)
        self.assertEqual(kind, "active")
        self.assertIn("Small Craft Advisory", text)
        self.assertIn('class="mb-adv is-active"', html)
        self.assertNotIn('class="mb-adv is-clear"', html)

    def test_neuse_and_jordan_no_alerts_are_calm(self):
        import tests.test_fresh_brief_preview as fp
        with patch("preview_alerts.fetch_coverage", side_effect=lambda rid: preview_alerts.ok_coverage(rid)), \
             patch.object(__import__("freshwater"), "assemble", side_effect=fp._assemble):
            for rid, phrase in (("neuse-river", EXPECTED["neuse-river"]),
                                ("jordan-lake", EXPECTED["jordan-lake"])):
                html = brief_preview.page(brief_preview.compose(rid, NOW))
                kind, text = _adv(html)
                self.assertEqual(kind, "clear", rid)
                self.assertEqual(text, brief_strings.alerts_none(phrase)[len("Alerts: "):], rid)
                self.assertFalse(ZONE_RE.search(text), (rid, text))
                src = _sources_blob(html)
                for code in _codes(rid):
                    self.assertIn(code, src, (rid, code))
                take = _take_alert_text(html)
                self.assertIn(phrase, take, rid)
                self.assertFalse(ZONE_RE.search(take), (rid, take))


if __name__ == "__main__":
    unittest.main()
