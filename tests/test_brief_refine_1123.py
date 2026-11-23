"""Morning Brief refinement (t440u): hazards, take, daytime high, tides, astro."""
from __future__ import annotations

import copy
import json
import sys
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import brief
import brief_astro
import brief_format

ET = ZoneInfo("America/New_York")
NOW = datetime(2026, 11, 23, 10, 15, tzinfo=timezone.utc)  # 5:15 AM ET
LATER = datetime(2026, 11, 23, 16, 0, tzinfo=timezone.utc)  # 11:00 AM ET, after 6:09 AM tide
EVENING = datetime(2026, 11, 23, 23, 30, tzinfo=timezone.utc)  # 6:30 PM ET


def _ok(sid, name, values, time="2026-11-23T09:50:00+00:00"):
    return {"status": "ok", "time": time, "ageMin": 10, "staleAfterMin": 90,
            "station": {"id": sid, "name": name}, "values": values}


def _salt_payload(alerts=None, marine_periods=None, forecast_periods=None, tides=True):
    R = {
        "wind": _ok("CLKN7", "Cape Lookout", {"speedKt": 5.0, "gustKt": 8.0, "dirCompass": "N"}),
        "seas": _ok("41159", "Onslow Bay Outer (CDIP 217)",
                    {"heightFt": 5.6, "dominantPeriodS": 10.0, "meanDirCompass": "ESE"}),
        "swell": _ok("41159", "Onslow Bay Outer (CDIP 217)",
                     {"heightFt": 1.6, "periodS": 11.0, "dirCompass": "ESE"}),
        "pressure": _ok("8656483", "Beaufort", {"inHg": 29.91, "hPa": 1012.0, "trend": "steady"}),
        "waterTemp": _ok("8656483", "Beaufort, Duke Marine Lab", {"f": 62.0}),
        "waterTempOffshore": _ok("41159", "Onslow Bay Outer (CDIP 217)", {"f": 74.0}),
    }
    evs = [
        {"type": "H", "t": int(datetime(2026, 11, 23, 11, 9, tzinfo=timezone.utc).timestamp() * 1000), "v": 4.1},
        {"type": "L", "t": int(datetime(2026, 11, 23, 17, 37, tzinfo=timezone.utc).timestamp() * 1000), "v": 0.1},
        {"type": "H", "t": int(datetime(2026, 11, 23, 23, 25, tzinfo=timezone.utc).timestamp() * 1000), "v": 3.1},
    ]
    return {
        "ok": True,
        "region": {"id": "crystal-coast", "name": "Morehead City · Beaufort",
                   "area": "Crystal Coast, North Carolina",
                   "anchor": {"label": "Beaufort Inlet", "lat": 34.695, "lon": -76.668}},
        "readings": R,
        "alerts": {"status": "ok", "items": alerts or []},
        "marine": {"status": "ok", "zone": "AMZ158", "updated": "2026-11-23T09:14:00+00:00",
                   "periods": marine_periods or [
                       {"name": "Today", "text": "N winds 5 to 10 kt, diminishing to around 5 kt late. Seas 3 to 5 ft."},
                       {"name": "Tonight", "text": "NW winds around 5 kt, becoming N 15 to 20 kt after midnight."},
                       {"name": "Tuesday", "text": "N winds 20 to 25 kt, becoming NE 25 to 30 kt in the afternoon. Seas 5 to 7 ft, building to 6 to 9 ft."},
                   ]},
        "forecast": {"status": "ok", "updated": "2026-11-23T10:00:00+00:00",
                     "periods": forecast_periods or [
                         {"name": "Overnight", "isDaytime": False, "tempF": 54, "short": "Patchy Fog", "pop": 6,
                          "windDir": "NW", "windMph": "1 mph"},
                         {"name": "Today", "isDaytime": True, "tempF": 71, "short": "Mostly Cloudy", "pop": 6,
                          "windDir": "N", "windMph": "3 mph"},
                         {"name": "Tonight", "isDaytime": False, "tempF": 51, "short": "Mostly Cloudy", "pop": 9},
                     ]},
        "tides": {"status": "ok", "station": {"id": "8656483", "name": "Beaufort, Duke Marine Lab"},
                  "events": evs} if tides else {"status": "unavailable"},
    }


GALE = {
    "event": "Gale Watch",
    "onset": "2026-11-24T11:00:00+00:00",  # Tue 6:00 AM ET
    "ends": "2026-11-25T09:00:00+00:00",   # Wed 4:00 AM ET
    "areas": "S of Cape Lookout NC to Surf City NC out to 20 NM",
    "headline": "Gale Watch issued November 23",
}
SCA_NOW = {
    "event": "Small Craft Advisory",
    "onset": "2026-11-23T05:56:00+00:00",  # 12:56 AM ET
    "ends": "2026-11-23T17:00:00+00:00",   # 12:00 PM ET
    "areas": "S of Cape Hatteras NC to Ocracoke Inlet NC out to 20 NM",
}
SCA_SOUND = {
    "event": "Small Craft Advisory",
    "onset": "2026-11-24T06:00:00+00:00",  # Tue 1:00 AM ET
    "ends": "2026-11-25T23:00:00+00:00",   # Wed 6:00 PM ET
    "areas": "Pamlico Sound",
}


def _build(payload, now=NOW):
    with patch("conditions.assemble", return_value=(200, copy.deepcopy(payload))), \
         patch.object(brief, "_trend", return_value=None):
        return brief.build_salt("crystal-coast", now)


class FutureHazards(unittest.TestCase):
    def test_upcoming_gale_has_onset_and_is_not_current(self):
        b = _build(_salt_payload(alerts=[GALE, SCA_NOW, SCA_SOUND]))
        line = dict(b["items"])["Advisories"]
        self.assertIn("UPCOMING:", line)
        self.assertIn("CURRENT:", line)
        self.assertIn("Gale Watch begins Tue 6:00 AM ET until Wed 4:00 AM ET", line)
        self.assertIn("Cape Lookout", line)
        self.assertIn("Pamlico Sound", line)
        self.assertIn("begins Tue 1:00 AM ET until Wed 6:00 PM ET", line)
        self.assertIn("Small Craft Advisory now in effect until Mon 12:00 PM ET", line)
        self.assertNotIn("Gale Watch now in effect", line)
        self.assertNotIn("Gale Watch until Wed", line)
        hz = b["hazards"]
        events_up = [r["event"] for r in hz["upcoming"]]
        events_now = [r["event"] for r in hz["current"]]
        self.assertIn("Gale Watch", events_up)
        self.assertIn("Small Craft Advisory", events_up)
        self.assertIn("Small Craft Advisory", events_now)

    def test_take_does_not_say_easing_when_deterioration_is_forecast(self):
        b = _build(_salt_payload(alerts=[GALE]))
        take = " ".join(b["take"])
        self.assertNotIn("easing later today", take.lower())
        self.assertNotIn("is in effect until", take.lower())
        self.assertIn("Gale Watch begins Tue 6:00 AM ET", take)

    def test_outlook_includes_tonight_and_tuesday(self):
        b = _build(_salt_payload(alerts=[GALE]))
        outlook = dict(b["items"])["Outlook"]
        self.assertIn("Tonight:", outlook)
        self.assertIn("Tuesday:", outlook)
        self.assertIn("AMZ158", outlook)
        self.assertNotIn("easing later today", " ".join(b["take"]).lower())
        html = brief.page({**b, "regionId": "crystal-coast", "issuedAt": NOW.isoformat(),
                           "issuedEt": "Mon Nov 23, 5:15 AM ET"}, view_now=NOW)
        # Outlook is outside the collapsed Full readings section.
        before, after = html.split('id="mb-details"', 1)
        self.assertIn("Outlook", before)
        self.assertIn('class="mb-outlook-p"', before)
        self.assertIn("Tonight", before)
        self.assertIn("Tuesday", before)
        self.assertIn('class="mb-outlook-src"', before)
        self.assertIn("AMZ158", before)


class DaytimeHigh(unittest.TestCase):
    def test_picks_today_not_overnight_period(self):
        b = _build(_salt_payload())
        rain = dict(b["items"])["Rain"]
        self.assertIn("high 71°F", rain)
        self.assertNotIn("high 54°F", rain)
        self.assertIn("mostly cloudy", rain.lower())

    def test_after_six_pm_uses_next_daytime_period(self):
        periods = [
            {"name": "Tonight", "isDaytime": False, "tempF": 51, "short": "Mostly Cloudy", "pop": 10},
            {"name": "Tuesday", "isDaytime": True, "tempF": 61, "short": "Partly Sunny", "pop": 8},
        ]
        picked = brief_format.daytime_period(periods, EVENING)
        self.assertIsNotNone(picked)
        self.assertEqual(picked["tempF"], 61)
        self.assertEqual(picked["name"], "Tuesday")
        payload = _salt_payload(forecast_periods=periods)
        b = _build(payload, now=EVENING)
        self.assertIn("high 61°F", dict(b["items"])["Rain"])


class ExpiredTides(unittest.TestCase):
    def _brief_with_tides(self):
        b = _build(_salt_payload())
        b["regionId"] = "crystal-coast"
        b["issuedAt"] = NOW.isoformat()
        b["issuedEt"] = "Mon Nov 23, 5:15 AM ET"
        b["issueDate"] = "2026-11-23"
        return b

    def test_snapshot_tides_line_is_unchanged_after_view(self):
        b = self._brief_with_tides()
        stored = dict(b["items"])["Tides"]
        html = brief.page(copy.deepcopy(b), view_now=LATER)
        self.assertEqual(dict(b["items"])["Tides"], stored)
        # Issued predictions remain in Full readings.
        self.assertIn("high 6:09 AM ET (4.1 ft)", html)
        self.assertIn(stored, html)

    def test_issued_next_is_not_labeled_next_after_it_passes(self):
        b = self._brief_with_tides()
        # At issue time the glance helper (snapshot) still says next is 6:09 AM.
        cells = {c["key"]: c for c in brief._glance(b)}
        self.assertIn("Tide next", cells)
        self.assertEqual(cells["Tide next"]["value"], "6:09")
        html = brief.page(b, view_now=LATER)
        # The displayed cell must not call 6:09 the next tide.
        import re
        tide = re.search(r'id="mb-tide".*?</div>', html, re.S).group(0)
        self.assertIn("Tide next", tide)
        self.assertIn("12:37", tide)
        self.assertIn("Updated at view time from NOAA predictions", tide)
        self.assertNotIn(">6:09</b>", tide.replace(" ", ""))
        # 6:09 may still appear in the stored full list, just not as "next".
        self.assertIn("data-tides=", html)


class Astro(unittest.TestCase):
    # Frozen USNO aa.usno.navy.mil /api/rstt/oneday values for 2026-11-23, tz=-5.
    USNO = {
        "crystal-coast": {"rise": "06:48", "set": "16:58", "phase": "Waxing Gibbous", "illum": 99},
        "hatteras": {"rise": "06:45", "set": "16:52", "phase": "Waxing Gibbous", "illum": 99},
        "falls-lake": {"rise": "06:59", "set": "17:03", "phase": "Waxing Gibbous", "illum": 99},
    }

    def _mins(self, hhmm_or_ampm):
        if "M" in hhmm_or_ampm:
            t = datetime.strptime(hhmm_or_ampm, "%I:%M %p")
            return t.hour * 60 + t.minute
        h, m = hhmm_or_ampm.split(":")
        return int(h) * 60 + int(m)

    def test_matches_usno_within_two_minutes(self):
        for rid, ref in self.USNO.items():
            ours = brief_astro.for_region(rid, date(2026, 11, 23))
            self.assertEqual(ours["status"], "ok", rid)
            self.assertLessEqual(abs(self._mins(ours["sunriseEt"]) - self._mins(ref["rise"])), 2, rid)
            self.assertLessEqual(abs(self._mins(ours["sunsetEt"]) - self._mins(ref["set"])), 2, rid)
            self.assertEqual(ours["moon"]["name"], ref["phase"], rid)
            self.assertLessEqual(abs(ours["moon"]["illuminationPct"] - ref["illum"]), 2, rid)

    def test_unavailable_on_unknown_region(self):
        out = brief_astro.for_brief("jordan-lake", date(2026, 11, 23))
        self.assertEqual(out["status"], "unavailable")
        self.assertNotIn("sunriseEt", out)

    def test_page_shows_unavailable_honestly(self):
        b = _build(_salt_payload())
        b["regionId"] = "crystal-coast"
        b["issuedAt"] = NOW.isoformat()
        b["astro"] = {"status": "unavailable", "regionId": "crystal-coast"}
        html = brief.page(b, view_now=NOW)
        self.assertIn("Sunrise, sunset, and moon phase not available.", html)
        self.assertNotIn("99%", html)


class SeasLabel(unittest.TestCase):
    def test_glance_names_offshore_buoy_and_page_rejects_surf_wording(self):
        b = _build(_salt_payload())
        b["regionId"] = "crystal-coast"
        b["issuedAt"] = NOW.isoformat()
        cells = {c["key"]: c for c in brief._glance(b)}
        self.assertIn("offshore", cells["Seas"]["sub"].lower())
        self.assertIn("Onslow Bay", cells["Seas"]["sub"])
        html = brief.page(b, view_now=NOW)
        self.assertIn("not a beach surf height", html.lower())
        # Never labeled as surf conditions.
        self.assertNotIn("beach surf conditions", html.lower())
        self.assertNotIn(">Surf<", html)


class OutlookParse(unittest.TestCase):
    def test_parses_tonight_and_tuesday_from_stored_string(self):
        text = ("Tonight: NW winds around 5 kt. "
                "Tuesday: N winds 20 to 25 kt. Seas 4 to 6 ft. "
                "(NWS AMZ158, issued Mon 4:14 AM ET).")
        parsed = brief_format.parse_outlook_text(text)
        self.assertIsNotNone(parsed)
        names = [p["name"] for p in parsed["periods"]]
        self.assertEqual(names, ["Tonight", "Tuesday"])
        self.assertIn("NW winds around 5 kt", parsed["periods"][0]["text"])
        self.assertIn("20 to 25 kt", parsed["periods"][1]["text"])
        self.assertIn("AMZ158", parsed["source"])
        self.assertIn("4:14 AM ET", parsed["source"])

    def test_outlook_periods_skips_today(self):
        marine = {
            "status": "ok", "zone": "AMZ154", "updated": "2026-11-23T09:14:00+00:00",
            "periods": [
                {"name": "Today", "text": "N winds 5 to 10 kt."},
                {"name": "Tonight", "text": "N winds around 5 kt, increasing after midnight."},
                {"name": "Tuesday", "text": "N winds around 25 kt. Seas 5 to 7 ft, building."},
            ],
        }
        parsed = brief_format.outlook_periods(marine)
        self.assertEqual([p["name"] for p in parsed["periods"]], ["Tonight", "Tuesday"])
        self.assertTrue(parsed["periods"][0]["text"].startswith("N winds around 5 kt"))
        self.assertIn("AMZ154", parsed["source"])


class StationLabelWrap(unittest.TestCase):
    def test_css_does_not_ellipsize_station_labels(self):
        css = (Path(__file__).resolve().parents[1] / "brief.css").read_text()
        import re
        bodies = re.findall(r"\.mb-gs\b[^{]*\{([^}]+)\}", css)
        self.assertTrue(bodies, "expected .mb-gs rules in brief.css")
        for body in bodies:
            self.assertNotIn("text-overflow: ellipsis", body)
            for m in re.finditer(r"-webkit-line-clamp:\s*([^;]+)", body):
                self.assertEqual(m.group(1).strip(), "unset", body)
        self.assertIn("overflow-wrap: anywhere", css)

    def test_page_keeps_full_station_name_in_markup(self):
        b = _build(_salt_payload())
        b["regionId"] = "crystal-coast"
        b["issuedAt"] = NOW.isoformat()
        html = brief.page(b, view_now=NOW)
        self.assertIn("Onslow Bay Outer (CDIP 217)", html)
        self.assertNotIn("bu…", html)
        self.assertNotIn('class="ellipsis"', html)
        self.assertIn('class="mb-gs"', html)


class MobileTimestamps(unittest.TestCase):
    def test_reading_times_are_in_the_markup(self):
        import brief_preview
        b = _build(_salt_payload())
        b["regionId"] = "crystal-coast"
        b["issuedAt"] = NOW.isoformat()
        html = brief.page(b, view_now=NOW)
        self.assertIn("Reading times", html)
        self.assertIn("<time>", html)
        # Public polish folds the list into a reachable details panel; it is not removed.
        wrapped = brief_preview._wrap_reading_times(html)
        self.assertIn('id="mb-sources"', wrapped)
        self.assertIn("<summary>Reading times</summary>", wrapped)
        self.assertIn("<time>", wrapped)

    def test_mobile_css_does_not_hide_reading_times(self):
        css = (Path(__file__).resolve().parents[1] / "brief.css").read_text()
        mobile = css.split("@media (max-width: 600px)")[-1]
        self.assertIn(".mb-sources", mobile)
        self.assertNotIn(".mb-issue .mb-sources { display: none; }", css)
        self.assertNotIn(".mb-sources { display: none", mobile)
        self.assertNotIn(".mb-fresh { display: none", mobile)


if __name__ == "__main__":
    unittest.main()
