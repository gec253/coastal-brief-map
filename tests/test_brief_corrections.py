"""Preview-only brief corrections: summary, labels, alerts, stage note, professional strings.

Live brief.py, brief.validate, automation, archive and .github stay untouched.
"""
from __future__ import annotations

import subprocess
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
import river_gate  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 11, 15, 15, 0, tzinfo=timezone.utc)  # 10:00 AM ET
ORIGIN = "origin/main"


def _git_show(path: str) -> bytes:
    return subprocess.check_output(["git", "show", "%s:%s" % (ORIGIN, path)], cwd=ROOT)


class LiveBriefUntouched(unittest.TestCase):
    def test_brief_py_matches_origin_main(self):
        self.assertEqual((ROOT / "brief.py").read_bytes(), _git_show("brief.py"))

    def test_validate_still_the_origin_function(self):
        # The file is byte-identical, so validate is unchanged. Also call it.
        self.assertTrue(callable(brief.validate))
        b = {
            "ok": True, "regionId": "crystal-coast", "issueDate": "2026-11-15",
            "issuedAt": NOW.isoformat(), "items": [("Wind", "10 kt from the N at a pier.")],
            "missing": [], "take": ["No advisories and no big overnight changes in the readings."],
            "freshness": [], "waterType": "saltwater",
            "region": {"id": "crystal-coast", "name": "Crystal Coast", "area": "x",
                       "anchor": {"lat": 34.7, "lon": -76.7}},
        }
        errs, summary = brief.validate(b, "crystal-coast", NOW)
        # Same contract as origin: a tuple of (errors list, summary dict)
        self.assertIsInstance(errs, list)
        self.assertIsInstance(summary, dict)

    def test_live_page_output_byte_identical_for_same_input(self):
        b = {
            "ok": True, "regionId": "crystal-coast", "issueDate": "Sun Nov 15",
            "issuedAt": NOW.isoformat(), "issuedEt": "Sun Nov 15, 10:00 AM ET",
            "reason": "manual", "words": 12, "waterType": "saltwater",
            "region": {"id": "crystal-coast", "name": "Crystal Coast", "area": "Morehead City, NC",
                       "anchor": {"lat": 34.7, "lon": -76.7}},
            "items": [("Advisories", "Could not check NWS advisories at issue time."),
                      ("Wind", "10 kt from the N, gusting 14, at a pier.")],
            "missing": ["seas"],
            "take": ["No advisories and no big overnight changes in the readings."],
            "freshness": [{"label": "Wind", "time": "9:00 AM ET", "station": "CLKN7", "stale": False}],
        }
        a = brief.page(b, include_fresh=False, public=True, ads_on=False)
        c = brief.page(b, include_fresh=False, public=True, ads_on=False)
        self.assertEqual(a, c)
        # Live output still uses brief.py wording, not the preview rewrite.
        self.assertIn("Could not check NWS advisories at issue time.", a)
        self.assertNotIn('class="mb-summary"', a)
        self.assertNotIn('class="mb-stage-note"', a)
        self.assertNotIn("Private preview", a)


class Strings(unittest.TestCase):
    def test_templates(self):
        self.assertEqual(brief_strings.not_available("Wind"), "Wind: Not available at issue time.")
        self.assertEqual(
            brief_strings.not_reported("Wind", "NOAA NDBC", "41064", "8:00 AM ET"),
            "Wind: Not reported. NOAA NDBC 41064 has not reported since 8:00 AM ET.",
        )
        self.assertEqual(
            brief_strings.not_reported("Wind", "NOAA NDBC", "41064"),
            "Wind: Not reported. NOAA NDBC 41064 has not reported.",
        )
        self.assertEqual(
            brief_strings.not_used("Wind", "8:00 AM ET", 2),
            "Wind: Not used. The last report, at 8:00 AM ET, is older than the 2-hour limit.",
        )
        self.assertEqual(
            brief_strings.nws_forecast_unavailable("Marine forecast"),
            "Marine forecast: NWS forecast not available at issue time.",
        )
        self.assertEqual(brief_strings.TIDE_PREDICTIONS_UNAVAILABLE,
                         "Tide predictions: Not available from NOAA CO-OPS at issue time.")
        self.assertEqual(
            brief_strings.observed_water_level_not_measured("Bogue Inlet"),
            "Observed water level: Not measured here. Tide times are NOAA predictions for Bogue Inlet.",
        )
        self.assertEqual(
            brief_strings.not_measured("Water temp"),
            "Water temp: Not measured. No official sensor in this area.",
        )
        self.assertEqual(
            brief_strings.stage_only("Neuse River at Smithfield"),
            "Neuse River at Smithfield: Not published. USGS reports stage only at this gauge.",
        )
        self.assertEqual(brief_strings.ALERTS_CHECK_FAILED,
                         "Alerts: Could not be checked at issue time. See weather.gov for current alerts.")
        self.assertEqual(
            brief_strings.alerts_none("Wake, Johnston and Wayne counties"),
            "Alerts: No active NWS alerts for Wake, Johnston and Wayne counties.",
        )
        self.assertEqual(brief_strings.HEADING_NOT_AVAILABLE, "Not available at issue time")
        self.assertEqual(brief_strings.HEADING_NOT_MEASURED, "Not measured in this area")
        self.assertEqual(brief_strings.PLACEHOLDER, "Not available")
        self.assertIn("not water depth", brief_strings.STAGE_NOTE)


class Attribution(unittest.TestCase):
    def test_computed_distances_and_honest_place_words(self):
        cfg = conditions.load_regions()
        stations = cfg["stations"]
        regions = {r["id"]: r for r in cfg["regions"]}

        ei = regions["emerald-isle"]["anchor"]
        loc = preview_copy.where("41064", stations["41064"], ei, role="Onslow Bay buoy, ~32 mi offshore", kind="wind")
        self.assertIn("41064", loc)
        self.assertIn("Onslow Bay Outer", loc)
        self.assertIn("32 mi SSE of Bogue Inlet", loc)
        self.assertIn("(offshore)", loc)

        loc = preview_copy.where("41159", stations["41159"], ei, role="Offshore seas, Onslow Bay", kind="seas")
        self.assertIn("41159", loc)
        self.assertIn("32 mi SSE of Bogue Inlet", loc)
        self.assertIn("(offshore)", loc)

        loc = preview_copy.where("KNJM", stations["KNJM"], ei, role="Air at Bogue Field, ~5 mi", kind="airTemp")
        self.assertIn("KNJM", loc)
        self.assertIn("5 mi NE of Bogue Inlet", loc)
        self.assertIn("sound-side", loc)
        self.assertNotIn("offshore", loc)

        wb = regions["wilmington"]["anchor"]
        loc = preview_copy.where("41110", stations["41110"], wb, role="Nearshore seas, Masonboro Inlet", kind="seas")
        self.assertIn("41110", loc)
        self.assertIn("6 mi SE of Johnnie Mercer's Pier", loc)
        self.assertIn("(nearshore)", loc)
        self.assertNotIn("offshore", loc.lower().replace("nearshore", ""))

        loc = preview_copy.where("8658163", stations["8658163"], wb, role="Wind at Johnnie Mercer's Pier")
        self.assertIn("8658163", loc)
        self.assertNotIn(" mi ", loc)  # local to the anchor

        nh = regions["nags-head"]["anchor"]
        loc = preview_copy.where("44086", stations["44086"], nh, role="Offshore seas, Nags Head", kind="seas")
        self.assertIn("44086", loc)
        self.assertIn("11 mi ENE of Jennette's Pier", loc)
        self.assertIn("(offshore)", loc)

        loc = preview_copy.where("8651370", stations["8651370"], nh, role="Duck Pier", kind="wind")
        self.assertIn("8651370", loc)
        self.assertIn("21 mi NNW of Jennette's Pier", loc)
        self.assertNotIn("offshore", loc)

        ts = regions["topsail"]["anchor"]
        loc = preview_copy.where("41064", stations["41064"], ts, role="Onslow Bay buoy, ~35 mi offshore", kind="wind")
        self.assertIn("35 mi ESE of Ocean City Fishing Pier", loc)
        self.assertIn("(offshore)", loc)
        loc = preview_copy.where("41159", stations["41159"], ts, role="Offshore seas, Onslow Bay", kind="seas")
        self.assertIn("36 mi ESE of Ocean City Fishing Pier", loc)


    def test_relabel_does_not_call_masonboro_offshore(self):
        rid = "wilmington"
        cfg = next(r for r in conditions.load_regions()["regions"] if r["id"] == rid)
        payload = {
            "ok": True,
            "region": {"id": rid, "anchor": cfg["anchor"]},
            "readings": {
                "seas": {"status": "ok", "values": {"heightFt": 2.3, "dominantPeriodS": 6, "meanDirCompass": "E"},
                         "station": {"id": "41110", "name": "Masonboro Inlet (CDIP 150)"}},
                "waterTemp": {"status": "ok", "values": {"f": 64},
                              "station": {"id": "8658163", "name": "Wrightsville Beach, Johnnie Mercer's Pier"}},
                "waterTempOffshore": {"status": "ok", "values": {"f": 66},
                                      "station": {"id": "41110", "name": "Masonboro Inlet (CDIP 150)"}},
            },
            "alerts": {"status": "ok", "items": []},
            "tides": {"status": "ok", "events": [], "station": {"id": "8658163", "name": "Wrightsville Beach, Johnnie Mercer's Pier"}},
        }
        body = {"items": [], "missing": [], "freshness": [], "take": []}
        out = preview_copy.relabel_salt(rid, body, payload, cfg)
        seas = dict(out["items"])["Seas"]
        self.assertIn("Combined seas", seas)
        self.assertIn("41110", seas)
        self.assertIn("nearshore", seas)
        self.assertNotIn("offshore", seas)
        wt = dict(out["items"])["Water temp"]
        self.assertIn("inshore", wt)
        self.assertIn("nearshore", wt)
        self.assertNotIn("°F offshore", wt)


    def test_relabel_emerald_offshore_and_predictions_only(self):
        rid = "emerald-isle"
        cfg = next(r for r in conditions.load_regions()["regions"] if r["id"] == rid)
        payload = {
            "ok": True,
            "region": {"id": rid, "anchor": cfg["anchor"]},
            "readings": {
                "wind": {"status": "ok", "values": {"speedKt": 12, "gustKt": 16, "dirCompass": "NW"},
                         "station": {"id": "41064", "name": "Onslow Bay Outer (LEJ3)"}},
                "seas": {"status": "ok", "values": {"heightFt": 3.3, "dominantPeriodS": 6, "meanDirCompass": "NE"},
                         "station": {"id": "41159", "name": "Onslow Bay Outer (CDIP 217)"}},
                "swell": {"status": "ok", "values": {"heightFt": 0.7, "periodS": 10, "dirCompass": "ENE"},
                          "station": {"id": "41159", "name": "Onslow Bay Outer (CDIP 217)"}},
                "waterTempOffshore": {"status": "ok", "values": {"f": 63},
                                      "station": {"id": "41159", "name": "Onslow Bay Outer (CDIP 217)"}},
            },
            "alerts": {"status": "ok", "items": []},
            "tides": {"status": "ok", "station": {"id": "TEC2837", "name": "Bogue Inlet"},
                      "events": [{"t": int(NOW.timestamp() * 1000) + 3600_000, "v": 4.4, "type": "H"}]},
        }
        body = {"items": [], "missing": [], "freshness": [], "take": []}
        out = preview_copy.relabel_salt(rid, body, payload, cfg)
        d = dict(out["items"])
        self.assertIn("41064", d["Wind"])
        self.assertIn("32 mi SSE", d["Wind"])
        self.assertIn("offshore", d["Wind"])
        self.assertIn("Combined seas", d["Seas"])
        self.assertIn("41159", d["Seas"])
        self.assertIn("Swell 0.7 ft", d["Swell"])
        self.assertIn("not combined seas", d["Swell"])
        self.assertIn("Not measured", d["Water temp"])
        self.assertIn("Offshore water temperature", d["Water temp"])
        self.assertIn("63°F", d["Water temp"])
        self.assertTrue(any(k == "Observed water level" for k, _ in out["unavailable"]))
        self.assertIn("NOAA predictions for", dict(out["unavailable"])["Observed water level"])


class Summary(unittest.TestCase):
    def test_coastal_fresh(self):
        rid = "emerald-isle"
        cfg = next(r for r in conditions.load_regions()["regions"] if r["id"] == rid)
        payload = {
            "ok": True, "region": {"id": rid, "anchor": cfg["anchor"]},
            "readings": {
                "wind": {"status": "ok", "values": {"speedKt": 12, "gustKt": 16, "dirCompass": "NW"},
                         "station": {"id": "41064", "name": "Onslow Bay Outer (LEJ3)"}},
                "seas": {"status": "ok", "values": {"heightFt": 3.3, "dominantPeriodS": 6, "meanDirCompass": "NE"},
                         "station": {"id": "41159"}},
                "swell": {"status": "ok", "values": {"heightFt": 0.7, "periodS": 10, "dirCompass": "ENE"},
                          "station": {"id": "41159"}},
                "waterTempOffshore": {"status": "ok", "values": {"f": 63}, "station": {"id": "41159"}},
            },
            "alerts": {"status": "ok", "items": []},
            "tides": {"status": "ok", "station": {"id": "TEC2837", "name": "Bogue Inlet"},
                      "events": [{"t": int(NOW.timestamp() * 1000) + 3600_000, "v": 4.4, "type": "H"}]},
        }
        body = preview_copy.relabel_salt(rid, {"items": [
            ("Rain", "0% chance through tonight; sunny, high 56°F."),
            ("Marine forecast", "Today: NW winds 10 to 15 kt. (NWS AMZ158)"),
        ], "missing": [], "freshness": [], "take": []}, payload, cfg)
        model = preview_copy.captains_take(rid, body, payload, cfg, now=NOW)
        text = preview_copy.take_text(model)
        self.assertLessEqual(len(model["sentences"]), 3)
        self.assertIn("12 kt", text)
        self.assertIn("41064", text)
        self.assertIn("combined seas", text.lower())
        self.assertIn("swell", text.lower())
        self.assertIn("offshore buoy", text)
        self.assertNotIn("at Offshore buoy", text)
        self.assertTrue("next high" in text or "next low" in text or "tide" in text.lower())
        self.assertNotIn("0% chance", text)
        self.assertNotIn("chance of rain", text)
        self.assertIn("sunny, high 56°F", text)
        self.assertIn("Alerts:", text)
        self.assertLess(len(text.split()), 180)
        html = preview_copy._render_captains_take(model)
        self.assertIn("data-kind=", html)
        self.assertIn("<span data-kind=", html)  # mixed water/tide/forecast+alert

    def test_coastal_missing_and_stale(self):
        rid = "emerald-isle"
        cfg = next(r for r in conditions.load_regions()["regions"] if r["id"] == rid)
        payload = {
            "ok": True, "region": {"id": rid, "anchor": cfg["anchor"]},
            "readings": {
                "wind": {"status": "stale", "time": NOW.isoformat(), "values": {"speedKt": 12},
                         "station": {"id": "41064"}, "stale": True},
                "seas": {"status": "unavailable"},
            },
            "alerts": {"status": "failed"},
        }
        body = preview_copy.relabel_salt(rid, {"items": [], "missing": ["seas"], "freshness": [], "take": []}, payload, cfg)
        model = preview_copy.captains_take(rid, body, payload, cfg, now=NOW)
        text = preview_copy.take_text(model)
        self.assertLessEqual(len(model["sentences"]), 3)
        self.assertIn("Not used.", text)
        self.assertIn("older than the 2-hour limit", text)
        self.assertIn("Combined seas: Not available at issue time", text)
        self.assertIn("Could not be checked at issue time", text)

    def test_jordan_and_neuse_summaries(self):
        import tests.test_fresh_brief_preview as fp
        with patch("preview_alerts.fetch_coverage", side_effect=lambda rid: preview_alerts.ok_coverage(rid)), \
             patch.object(__import__("freshwater"), "assemble", side_effect=fp._assemble):
            jb = brief_preview.compose("jordan-lake", NOW)
            nb = brief_preview.compose("neuse-river", NOW)
        js, ns = jb["summary"], nb["summary"]
        self.assertIn("212.23 ft NGVD29", js)
        self.assertIn("guide curve", js)
        self.assertIn("Chatham and Durham counties", js)
        self.assertNotIn("n/a", js)
        self.assertIn("Clayton", ns)
        self.assertIn("1.22 ft stage", ns)
        self.assertIn("NWS forecasts a crest", ns)
        self.assertIn("Wake, Johnston and Wayne counties", ns)
        self.assertIn("mb-summary", brief_preview.page(jb))
        for sent in jb["captainsTake"]["sentences"]:
            self.assertIn(sent["text"].rstrip("."), brief_preview.page(jb))
        self.assertIn(brief_strings.STAGE_NOTE, brief_preview.page(nb))
        self.assertIn("mb-stage-note", brief_preview.page(nb))
        # Lake elevation is not called stage
        self.assertNotIn("mb-stage-note", brief_preview.page(jb).split("Lake level")[0] + "Lake level")
        # Jordan has stage on the Moncure release line
        self.assertIn("mb-stage-note", brief_preview.page(jb))
        for html in (brief_preview.page(jb), brief_preview.page(nb)):
            self.assertEqual(preview_copy.informal_hits(html), [])
            self.assertIn("Not measured in this area", html)


class PreviewStrings(unittest.TestCase):
    def test_salt_preview_html_has_no_informal_strings(self):
        rid = "nags-head"
        cfg = next(r for r in conditions.load_regions()["regions"] if r["id"] == rid)
        payload = {
            "ok": True, "region": {"id": rid, "anchor": cfg["anchor"]},
            "readings": {
                "waterTempOffshore": {"status": "ok", "values": {"f": 63.1},
                                      "time": "2026-11-14T14:50:00+00:00",
                                      "station": {"id": "44086", "name": "Nags Head offshore"}},
            },
            "alerts": {"status": "ok", "items": []},
        }
        body = {
            "region": {"id": rid, "name": cfg["name"], "area": cfg.get("area"), "anchor": cfg["anchor"]},
            "waterType": "saltwater",
            "items": [("Advisories", "No NWS marine advisories for this area."),
                      ("Wind", "10 kt from the N, gusting 14, at Duck Pier."),
                      ("Seas", "2.0 ft every 6 s from the E at Nags Head offshore (CDIP 243)."),
                      ("Pressure", "30.03 inHg, 3-hour trend not reported."),
                      ("Marine forecast", "Today: N winds 10 kt. (NWS AMZ150)"),
                      ("Tides", "high 10:31 AM ET (4.3 ft) at Jennette's Pier, MLLW."),
                      ("Water temp", "Inshore unavailable (no sensor in this area); 63°F offshore at Nags Head offshore (CDIP 243).")],
            "freshness": [], "take": ["No advisories and no big overnight changes in the readings."],
            "missing": [], "sources": "NOAA",
        }
        with patch.object(brief, "build_salt", return_value=body), \
             patch("conditions.assemble", return_value=(200, payload)):
            b = brief_preview.compose("nags-head", NOW)
            html = brief_preview.page(b)
        self.assertEqual(preview_copy.informal_hits(html), [])
        self.assertIn("Not measured", html)
        self.assertIn("63°F", html)
        self.assertIn("mb-summary", html)
        self.assertIn("No active NWS alerts", dict(b["items"])["Alerts"])
        self.assertFalse(dict(b["items"])["Alerts"].startswith("Alerts:"))


    def test_stage_note_not_applied_to_lake_elevation_label(self):
        self.assertFalse(preview_copy.has_stage([("Lake level", "212.23 ft (NGVD29), 3.77 ft below the 216.0 ft guide curve.")]))
        self.assertTrue(preview_copy.has_stage([("Release plus runoff", "245 cfs at Haw River near Moncure, 2.02 ft stage.")]))
        self.assertTrue(preview_copy.has_stage([("Neuse River near Clayton", "1.22 ft stage, 217 cfs (regulated).")]))


class ZoneLists(unittest.TestCase):
    def test_verified_ids(self):
        self.assertEqual(
            preview_alerts.zone_ids(rid="neuse-river"),
            ["NCZ041", "NCC183", "NCZ042", "NCC101", "NCZ078", "NCC191"],
        )
        self.assertEqual(preview_alerts.areas_phrase(rid="neuse-river"), "Wake, Johnston and Wayne counties")
        self.assertEqual(preview_alerts.zone_ids(rid="jordan-lake"),
                         ["NCZ040", "NCC037", "NCZ025", "NCC063"])
        self.assertEqual(preview_alerts.areas_phrase(rid="jordan-lake"), "Chatham and Durham counties")



class CaptainsTakeAndSources(unittest.TestCase):
    def test_take_model_and_markup(self):
        import tests.test_fresh_brief_preview as fp
        with patch("preview_alerts.fetch_coverage", side_effect=lambda rid: preview_alerts.ok_coverage(rid)), \
             patch.object(__import__("freshwater"), "assemble", side_effect=fp._assemble):
            jb = brief_preview.compose("jordan-lake", NOW)
            html = brief_preview.page(jb)
        m = jb["captainsTake"]
        self.assertEqual(m["heading"], "Captain's Take")
        self.assertIn("issuedEt", m)
        self.assertTrue(m["sentences"])
        allowed = {"observed", "forecast", "missing", "alert", "predicted"}
        for s in m["sentences"]:
            kinds = s.get("kinds") or str(s.get("kind") or "").split()
            self.assertTrue(kinds and set(kinds) <= allowed, kinds)
            self.assertIn("text", s)
            self.assertIn("sources", s)
        self.assertLessEqual(len(m["sentences"]), 3)
        self.assertIn("class=\"mb-summary mb-take\"", html)
        self.assertIn("Captain's Take", html)
        self.assertIn("id=\"cb-captains-take\"", html)
        self.assertIn("mb-sources", html)
        self.assertIn("id=\"cb-reading-sources\"", html)
        self.assertIn("216.0 ft guide curve", dict(jb["items"])["Lake level"])
        self.assertIn("NGVD29", dict(jb["items"])["Lake level"])
        self.assertIn("epec.saw.usace.army.mil/dsslake.txt", dict(jb["items"])["Lake level"])
        self.assertIn("each day of the year", dict(jb["items"])["Lake level"])
        self.assertIn("Haw River flow at Moncure (USGS 02098206)", dict(jb["items"]))
        self.assertIn("1.6 miles below Jordan Lake Dam", dict(jb["items"])["Haw River flow at Moncure (USGS 02098206)"])
        # A single take: the old bottom section is gone
        self.assertEqual(html.count('<div class="mb-take-body">'), 1)
        self.assertEqual(html.count('id="cb-captains-take"'), 1)
        self.assertEqual(html.count('id="mb-sources"'), 1)
        self.assertEqual(html.count('<details class="mb-sources"'), 1)
        self.assertIn("<summary>Sources and times</summary>", html)
        adv = html.find('class="mb-adv')
        glance = html.find('class="mb-glance')
        take = html.find("mb-summary mb-take")
        self.assertTrue(0 < adv < take < glance, (adv, take, glance))
        self.assertNotIn("bite", html.lower())
        self.assertNotIn("fishing forecast", html.lower())


    def test_coastal_take_wording_and_three_sentences(self):
        cfg = {r["id"]: r for r in conditions.load_regions()["regions"]}
        rid, c = "nags-head", cfg["nags-head"]
        payload = {
            "ok": True, "region": {"id": rid, "anchor": c["anchor"]},
            "readings": {
                "wind": {"status": "ok", "values": {"speedKt": 11, "gustKt": 14, "dirCompass": "NW"},
                         "station": {"id": "8651370", "name": "Duck Pier"}},
                "seas": {"status": "ok", "values": {"heightFt": 4.3},
                         "station": {"id": "44086", "name": "Nags Head offshore (CDIP 243)"}},
                "swell": {"status": "ok", "values": {"heightFt": 0.7}, "station": {"id": "44086"}},
                "waterTempOffshore": {"status": "ok", "values": {"f": 62}, "station": {"id": "44086"}},
            },
            "alerts": {"status": "ok", "items": []},
            "tides": {"status": "ok", "station": {"id": "8652226", "name": "Jennette's Pier (ocean)"},
                      "observed": {"status": "ok", "station": {"id": "8651370"},
                                   "latest": {"t": int(NOW.timestamp() * 1000), "v": 3.50}},
                      "events": [{"t": int(NOW.timestamp() * 1000) + 3600_000, "v": 3.5, "type": "H"}]},
        }
        body = preview_copy.relabel_salt(rid, {"items": [], "missing": [], "freshness": [], "take": []}, payload, c)
        # Card labels stay prominent and capitalized
        d = dict(body["items"])
        self.assertIn("Representative observation, Duck Pier (8651370), 21 mi NNW", d["Wind"])
        self.assertIn("Offshore buoy 44086, 11 mi ENE", d["Seas"])
        self.assertIn("Inshore water temperature: Not measured", d["Water temp"])
        self.assertIn("Offshore water temperature:", d["Water temp"])
        self.assertIn("62°F", d["Water temp"])
        model = preview_copy.captains_take(rid, body, payload, c, now=NOW)
        self.assertEqual(len(model["sentences"]), 3)
        text = preview_copy.take_text(model)
        self.assertIn("NW wind 11 kt", text)
        self.assertIn("at Duck Pier (8651370), 21 mi NNW, a representative observation", text)
        self.assertNotIn("at Representative observation", text)
        self.assertIn("at offshore buoy 44086, 11 mi ENE", text)
        self.assertNotIn("at Offshore buoy", text)
        # Observed WL at Duck is not local to Jennette's — omitted from the Take
        self.assertNotIn("3.50 ft MLLW", text)
        self.assertNotIn("3.50", text)
        self.assertIn("next high", text)
        # Locked inshore-missing string stays on the card, not in the Take.
        self.assertNotIn("Not measured", text)
        self.assertNotIn("No official sensor in this area", text)
        self.assertIn("62°F observed at offshore buoy 44086", text)
        # Water/tide sentence is verified readings only (inshore-missing stays on the card).
        mid = model["sentences"][1]
        self.assertEqual(mid["kinds"], ["observed", "predicted"])
        self.assertNotIn("missing", mid["kinds"])
        html = preview_copy._render_captains_take(model)
        self.assertIn('data-kind="observed predicted"', html)
        self.assertNotIn('data-kind="missing"', html)
        self.assertIn('<span data-kind="predicted"', html)


    def test_wilmington_take_includes_local_water_level(self):
        cfg = {r["id"]: r for r in conditions.load_regions()["regions"]}
        rid, c = "wilmington", cfg["wilmington"]
        payload = {
            "ok": True, "region": {"id": rid, "anchor": c["anchor"]},
            "readings": {
                "wind": {"status": "ok", "values": {"speedKt": 7, "dirCompass": "NW"},
                         "station": {"id": "8658163", "name": "Wrightsville Beach, Johnnie Mercer's Pier"}},
                "seas": {"status": "ok", "values": {"heightFt": 2.0},
                         "station": {"id": "41110", "name": "Masonboro Inlet (CDIP 150)"}},
            },
            "alerts": {"status": "ok", "items": []},
            "tides": {"status": "ok", "station": {"id": "8658163", "name": "Wrightsville Beach, Johnnie Mercer's Pier"},
                      "observed": {"status": "ok", "latest": {"t": int(NOW.timestamp() * 1000), "v": 4.18}},
                      "events": [{"t": int(NOW.timestamp() * 1000) + 3600_000, "v": 4.1, "type": "H"}]},
        }
        body = preview_copy.relabel_salt(rid, {"items": [], "missing": [], "freshness": [], "take": []}, payload, c)
        model = preview_copy.captains_take(rid, body, payload, c, now=NOW)
        text = preview_copy.take_text(model)
        self.assertLessEqual(len(model["sentences"]), 3)
        self.assertTrue("next high" in text.lower())
        self.assertIn("observed water level is 4.18 ft MLLW", text)
        self.assertIn("nearshore buoy 41110, 6 mi SE", text)
        html = preview_copy._render_captains_take(model)
        self.assertNotIn("..", html.replace("...", ""))

    def test_offshore_lead_in_nags_and_topsail_cards(self):
        cfg = {r["id"]: r for r in conditions.load_regions()["regions"]}
        # Nags Head 44086
        rid, c = "nags-head", cfg["nags-head"]
        payload = {
            "ok": True, "region": {"id": rid, "anchor": c["anchor"]},
            "readings": {
                "wind": {"status": "ok", "values": {"speedKt": 7, "gustKt": 9, "dirCompass": "NW"},
                         "station": {"id": "8651370", "name": "Duck Pier"}},
                "seas": {"status": "ok", "values": {"heightFt": 3.3, "dominantPeriodS": 6, "meanDirCompass": "NE"},
                         "station": {"id": "44086", "name": "Nags Head offshore (CDIP 243)"}},
            },
            "alerts": {"status": "ok", "items": []},
        }
        body = preview_copy.relabel_salt(rid, {"items": [], "missing": [], "freshness": [], "take": []}, payload, c)
        d = dict(body["items"])
        self.assertIn("Offshore buoy 44086, 11 mi ENE", d["Seas"])
        self.assertIn("Representative observation, Duck Pier (8651370), 21 mi NNW", d["Wind"])
        # Topsail 41159 / 41064
        rid, c = "topsail", cfg["topsail"]
        payload = {
            "ok": True, "region": {"id": rid, "anchor": c["anchor"]},
            "readings": {
                "wind": {"status": "ok", "values": {"speedKt": 12, "gustKt": 16, "dirCompass": "N"},
                         "station": {"id": "41064", "name": "Onslow Bay Outer (LEJ3)"}},
                "seas": {"status": "ok", "values": {"heightFt": 2.6, "dominantPeriodS": 9, "meanDirCompass": "E"},
                         "station": {"id": "41159", "name": "Onslow Bay Outer (CDIP 217)"}},
            },
            "alerts": {"status": "ok", "items": []},
        }
        body = preview_copy.relabel_salt(rid, {"items": [], "missing": [], "freshness": [], "take": []}, payload, c)
        d = dict(body["items"])
        self.assertIn("Offshore buoy 41064, 35 mi ESE", d["Wind"])
        self.assertIn("Offshore buoy 41159, 36 mi ESE", d["Seas"])


    def test_carolina_kure_take_labels_and_omits_wrightsville_level(self):
        cfg = {r["id"]: r for r in conditions.load_regions()["regions"]}
        rid, c = "carolina-kure", cfg["carolina-kure"]
        payload = {
            "ok": True, "region": {"id": rid, "anchor": c["anchor"]},
            "readings": {
                "wind": {"status": "ok", "values": {"speedKt": 7, "gustKt": 10, "dirCompass": "NNW"},
                         "station": {"id": "MBIN7", "name": "Masonboro Island, south end"}},
                "seas": {"status": "ok", "values": {"heightFt": 2.0},
                         "station": {"id": "41110", "name": "Masonboro Inlet (CDIP 150)"}},
                "swell": {"status": "ok", "values": {"heightFt": 0.7}, "station": {"id": "41110"}},
                "waterTempOffshore": {"status": "ok", "values": {"f": 66}, "station": {"id": "41110"}},
            },
            "alerts": {"status": "ok", "items": []},
            "tides": {"status": "ok", "station": {"id": "8658559", "name": "Wilmington Beach"},
                      "observed": {"status": "ok", "station": {"id": "8658163", "name": "Wrightsville Beach, Johnnie Mercer's Pier"},
                                   "latest": {"t": int(NOW.timestamp() * 1000), "v": 3.96},
                                   "note": c["tide"]["observedNote"]},
                      "events": [{"t": int(NOW.timestamp() * 1000) + 3600_000, "v": 4.44, "type": "H"}]},
        }
        body = preview_copy.relabel_salt(rid, {"items": [], "missing": [], "freshness": [], "take": []}, payload, c)
        d = dict(body["items"])
        self.assertIn("Nearshore buoy 41110, 12.8 mi NE", d["Seas"])
        self.assertIn("Inshore water temperature: Not measured", d["Water temp"])
        self.assertIn("No official sensor in this area", d["Water temp"])
        model = preview_copy.captains_take(rid, body, payload, c, now=NOW)
        self.assertEqual(len(model["sentences"]), 3)
        text = preview_copy.take_text(model)
        self.assertIn("NNW wind 7 kt, gusting 10 kt", text)
        self.assertIn("MBIN7", text)
        self.assertIn("nearshore buoy 41110, 12.8 mi NE", text)
        self.assertNotIn("13 mi", text)
        self.assertIn("66°F observed at nearshore buoy 41110, 12.8 mi NE", text)
        self.assertIn("next high", text)
        self.assertIn("Wilmington Beach (8658559)", text)
        self.assertNotIn("3.96", text)
        self.assertNotIn("observed water level is 3.96", text)
        self.assertNotIn("Not measured", text)
        self.assertNotIn("No official sensor in this area", text)
        phrase = preview_zones.format_alert_areas(c["alertZones"])
        self.assertIn(phrase, text)
        self.assertIn(brief_strings.alerts_none(phrase), text)
        self.assertNotIn("AMZ250", text)
        self.assertNotIn("NCZ108", text)
        for s in model["sentences"]:
            body_txt = (s["text"] or "").rstrip(".")
            self.assertNotIn(". ", body_txt, s["text"])

    def test_corolla_duck_take_includes_local_duck_level(self):
        cfg = {r["id"]: r for r in conditions.load_regions()["regions"]}
        rid, c = "corolla-duck", cfg["corolla-duck"]
        payload = {
            "ok": True, "region": {"id": rid, "anchor": c["anchor"]},
            "readings": {
                "wind": {"status": "ok", "values": {"speedKt": 7, "dirCompass": "NW"},
                         "station": {"id": "8651370", "name": "Duck Pier"}},
                "seas": {"status": "ok", "values": {"heightFt": 3.3},
                         "station": {"id": "44056", "name": "Duck FRF (USACE waverider)"}},
                "swell": {"status": "ok", "values": {"heightFt": 0.7}, "station": {"id": "44056"}},
                "waterTempOffshore": {"status": "ok", "values": {"f": 61}, "station": {"id": "44056"}},
            },
            "alerts": {"status": "ok", "items": []},
            "tides": {"status": "ok", "station": {"id": "8651370", "name": "Duck Pier"},
                      "observed": {"status": "ok", "latest": {"t": int(NOW.timestamp() * 1000), "v": 3.23}},
                      "events": [{"t": int(NOW.timestamp() * 1000) + 3600_000, "v": 3.40, "type": "H"}]},
        }
        body = preview_copy.relabel_salt(rid, {"items": [], "missing": [], "freshness": [], "take": []}, payload, c)
        d = dict(body["items"])
        self.assertIn("Nearshore buoy 44056, 2.2 mi ENE", d["Seas"])
        self.assertIn("Inshore water temperature: Not measured", d["Water temp"])
        model = preview_copy.captains_take(rid, body, payload, c, now=NOW)
        self.assertEqual(len(model["sentences"]), 3)
        text = preview_copy.take_text(model)
        self.assertIn("Duck Pier (8651370)", text)
        self.assertIn("nearshore buoy 44056, 2.2 mi ENE", text)
        self.assertNotIn(", 2 mi ENE", text)
        self.assertIn("61°F observed at nearshore buoy 44056, 2.2 mi ENE", text)
        self.assertIn("next high", text)
        self.assertIn("observed water level is 3.23 ft MLLW", text)
        self.assertNotIn("Not measured", text)
        self.assertNotIn("No official sensor in this area", text)
        phrase = preview_zones.format_alert_areas(c["alertZones"])
        self.assertIn(phrase, text)
        self.assertIn(brief_strings.alerts_none(phrase), text)
        self.assertNotIn("AMZ150", text)
        self.assertNotIn("NCZ203", text)
        self.assertNotIn("NCZ102", text)
        self.assertNotIn("44086", text)
        self.assertNotIn("8652587", text)
        for s in model["sentences"]:
            body_txt = (s["text"] or "").rstrip(".")
            self.assertNotIn(". ", body_txt, s["text"])



    def test_take_wind_reports_sustained_or_says_only_gust(self):
        cfg = {r["id"]: r for r in conditions.load_regions()["regions"]}
        rid, c = "carolina-kure", cfg["carolina-kure"]
        def take(values):
            payload = {
                "ok": True, "region": {"id": rid, "anchor": c["anchor"]},
                "readings": {
                    "wind": {"status": "ok", "values": values,
                             "station": {"id": "MBIN7", "name": "Masonboro Island, south end"}},
                },
                "alerts": {"status": "ok", "items": []},
            }
            body = preview_copy.relabel_salt(rid, {"items": [], "missing": [], "freshness": [], "take": []}, payload, c)
            return preview_copy.take_text(preview_copy.captains_take(rid, body, payload, c, now=NOW))
        text = take({"speedKt": 8, "gustKt": 11, "dirCompass": "NNW"})
        self.assertIn("NNW wind 8 kt, gusting 11 kt", text)
        self.assertNotIn("Light", text)
        self.assertNotIn("sustained speed not reported", text)
        text = take({"gustKt": 11, "dirCompass": "NNW"})
        self.assertIn("NNW wind gusting 11 kt (sustained speed not reported)", text)
        self.assertNotIn("Light", text)
        self.assertNotIn("wind 11 kt", text)
        self.assertNotIn("Only a", text)
        # A measured 6 kt (the "Light" threshold in the old wording) is stated as a number.
        text = take({"speedKt": 6, "dirCompass": "NNW"})
        self.assertIn("NNW wind 6 kt", text)
        self.assertNotIn("Light", text)
        self.assertNotIn("gusting", text)

    def test_nonzero_rain_stays_in_the_take(self):
        cfg = next(r for r in conditions.load_regions()["regions"] if r["id"] == "emerald-isle")
        payload = {
            "ok": True, "region": {"id": "emerald-isle", "anchor": cfg["anchor"]},
            "readings": {}, "alerts": {"status": "ok", "items": []},
        }
        body = preview_copy.relabel_salt("emerald-isle", {"items": [
            ("Rain", "9% chance through tonight; sunny, high 55°F."),
            ("Marine forecast", "Today: NW winds around 15 kt. (NWS AMZ158)"),
        ], "missing": [], "freshness": [], "take": []}, payload, cfg)
        text = preview_copy.take_text(preview_copy.captains_take("emerald-isle", body, payload, cfg, now=NOW))
        self.assertIn("9% chance of rain", text)
        self.assertNotIn("0% chance", text)

    def test_existing_brief_card_distances_unchanged(self):
        cfg = {r["id"]: r for r in conditions.load_regions()["regions"]}
        rid, c = "wilmington", cfg["wilmington"]
        payload = {
            "ok": True, "region": {"id": rid, "anchor": c["anchor"]},
            "readings": {
                "seas": {"status": "ok", "values": {"heightFt": 2.0},
                         "station": {"id": "41110", "name": "Masonboro Inlet (CDIP 150)"}},
            },
            "alerts": {"status": "ok", "items": []},
        }
        body = preview_copy.relabel_salt(rid, {"items": [], "missing": [], "freshness": [], "take": []}, payload, c)
        d = dict(body["items"])
        self.assertIn("Nearshore buoy 41110, 6 mi SE", d["Seas"])
        self.assertNotIn("12.8", d["Seas"])
        text = preview_copy.take_text(preview_copy.captains_take(rid, body, payload, c, now=NOW))
        self.assertIn("nearshore buoy 41110, 6 mi SE", text)
        self.assertNotIn("12.8", text)




if __name__ == "__main__":
    unittest.main()
