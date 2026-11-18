"""Hatteras Morning Brief wind backup (Ed approved plan item 2, t322u, Nov 18 2026).

Diamond Shoals buoy 41025 stays the primary wind source. USCG Station Hatteras (NOAA CO-OPS 8654467,
already fetched as "harborWind") is used only when the primary is stale or missing under the existing
staleness rule, and only when it is itself fresh. Both stale: no wind is shown and both are named.
Everything is offline with fake readings; nothing is published."""
from __future__ import annotations

import copy
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import brief  # noqa: E402

NOW = datetime(2026, 11, 18, 10, 15, tzinfo=timezone.utc)  # 5:15 AM ET
BUOY = {"id": "41025", "name": "Diamond Shoals"}
SHORE = {"id": "8654467", "name": "USCG Station Hatteras"}


def _iso(minutes_ago):
    return (NOW - timedelta(minutes=minutes_ago)).isoformat()


def _wind(status, station, minutes_ago, speed=16.0, gust=19.0, d="NNE"):
    r = {"status": status, "kind": "observed", "time": _iso(minutes_ago), "ageMin": minutes_ago, "station": dict(station),
         "values": {"speedKt": speed, "gustKt": gust, "dirCompass": d}}
    r["staleAfterMin"] = 75 if station["id"] == "41025" else 45
    return r


def _payload(wind, harbor):
    ok = lambda sid, name, v: {"status": "ok", "time": _iso(20), "ageMin": 20, "staleAfterMin": 90,
                               "station": {"id": sid, "name": name}, "values": v}
    R = {
        "wind": wind,
        "seas": ok("41120", "Cape Hatteras East (CDIP 250)", {"heightFt": 3.0, "dominantPeriodS": 9.0, "meanDirCompass": "NE"}),
        "pressure": ok("8654467", "USCG Station Hatteras", {"inHg": 30.40, "hPa": 1029.5, "trend": "steady"}),
        "waterTemp": ok("8654467", "USCG Station Hatteras", {"f": 60.0}),
        "waterTempOffshore": ok("41120", "Cape Hatteras East (CDIP 250)", {"f": 66.0}),
    }
    if harbor is not None:
        R["harborWind"] = harbor
    return {"ok": True, "region": {"id": "hatteras", "name": "Hatteras Island"}, "readings": R,
            "alerts": {"status": "ok", "items": []},
            "marine": {"status": "ok", "zone": "AMZ154", "updated": _iso(120),
                       "periods": [{"name": "Today", "text": "N winds 10 to 15 kt. Seas 3 ft."}]},
            "forecast": {"status": "ok", "updated": _iso(120),
                         "periods": [{"pop": 0, "short": "Sunny", "tempF": 62}, {"pop": 0, "short": "Clear", "tempF": 48}]},
            "tides": {"status": "unavailable"}}


def _build(payload, rid="hatteras"):
    with patch("conditions.assemble", return_value=(200, copy.deepcopy(payload))), \
         patch.object(brief, "_trend", return_value=None):
        return brief.build_salt(rid, NOW)


class PrimaryFresh(unittest.TestCase):
    def test_buoy_used_when_fresh_even_if_shore_is_fresh(self):
        b = _build(_payload(_wind("ok", BUOY, 35), _wind("ok", SHORE, 6, speed=10.0, gust=12.0)))
        line = dict(b["items"])["Wind"]
        self.assertTrue(line.startswith("16 kt from the NNE, gusting 19, at Diamond Shoals (offshore buoy 41025, observed "), line)
        self.assertNotIn("USCG", line)
        self.assertNotIn("backup", line.lower())
        self.assertEqual(b["windSource"]["role"], "primary")
        self.assertEqual(b["windSource"]["station"], "41025")
        self.assertFalse([m for m in b["missing"] if "wind" in m])
        self.assertEqual([f["station"] for f in b["freshness"] if f["label"].startswith("Wind")], ["41025"])
        cell = [c for c in brief._glance({**b, "regionId": "hatteras"}) if c["tone"] == "wind"][0]
        self.assertEqual(cell["key"], "Wind")
        self.assertEqual(cell["sub"], "from NNE · offshore buoy 41025")


class PrimaryStaleBackupFresh(unittest.TestCase):
    def _check_backup(self, b, state):
        line = dict(b["items"])["Wind"]
        self.assertIn("Coastal backup, USCG Station Hatteras (shore station at Hatteras Inlet), observed ", line)
        self.assertIn("10 kt from the NNE, gusting 12.", line)
        self.assertIn("Offshore buoy 41025 %s, not used." % state, line)
        self.assertIn(brief.SHORE_WIND_NOTE, line)
        self.assertNotIn("16 kt", line)  # never blended with the stale buoy value
        self.assertEqual(b["windSource"]["role"], "backup")
        self.assertEqual(b["windSource"]["type"], "coastal")
        self.assertEqual(b["windSource"]["station"], "8654467")
        self.assertTrue(any(m.startswith("offshore wind, offshore buoy 41025") and "coastal backup shown" in m for m in b["missing"]))
        fr = [f for f in b["freshness"] if f["label"].startswith("Wind")]
        self.assertEqual(fr, [{"label": "Wind (coastal backup)", "time": brief._t(_iso(6)), "station": "8654467", "stale": False}])
        cell = [c for c in brief._glance({**b, "regionId": "hatteras"}) if c["tone"] == "wind"][0]
        self.assertEqual(cell["key"], "Wind · coastal backup")
        self.assertEqual(cell["value"], "10")
        self.assertEqual(cell["sub"], "from NNE · USCG Hatteras (shore)")

    def test_stale_buoy_uses_labeled_shore_backup(self):
        b = _build(_payload(_wind("stale", BUOY, 285), _wind("ok", SHORE, 6, speed=10.0, gust=12.0)))
        self._check_backup(b, "stale since %s" % brief._t(_iso(285)))

    def test_missing_buoy_uses_labeled_shore_backup(self):
        b = _build(_payload({"status": "unavailable", "kind": "observed", "tried": [{"id": "41025", "result": "no report"}]},
                            _wind("ok", SHORE, 6, speed=10.0, gust=12.0)))
        self._check_backup(b, "not reporting")

    def test_backup_shows_on_page_and_print(self):
        b = _build(_payload(_wind("stale", BUOY, 285), _wind("ok", SHORE, 6, speed=10.0, gust=12.0)))
        full = {**b, "ok": True, "regionId": "hatteras", "issueDate": "2026-11-18", "issuedAt": NOW.isoformat(),
                "issuedEt": "Wed Nov 18, 5:15 AM ET", "reason": "scheduled", "words": 100}
        html = brief.page(full)
        self.assertIn("Coastal backup, USCG Station Hatteras", html)
        self.assertIn("Wind · coastal backup", html)
        self.assertIn("Wind (coastal backup)", html)
        self.assertIn("Not available at issue time: offshore wind, offshore buoy 41025", html)

    def test_validation_result_unchanged_partial(self):
        # Ed's call pending: a valid backup keeps the brief "partial" (the stale buoy is still listed),
        # so validation semantics and the 5:15-5:30 retry for the buoy are unchanged.
        b = _build(_payload(_wind("stale", BUOY, 285), _wind("ok", SHORE, 6, speed=10.0, gust=12.0)))
        full = {**b, "ok": True, "regionId": "hatteras", "issueDate": brief._issue_date(NOW), "issuedAt": NOW.isoformat()}
        with patch.object(brief, "_region_cfg", return_value={"name": "Hatteras Island", "marine": {"zone": "AMZ154"}}):
            errs, summary = brief.validate(full, "hatteras", NOW)
        self.assertEqual(errs, [])
        self.assertEqual(summary["status"], "partial")

    def test_stale_backup_station_check(self):
        # A harborWind reading from some other station is never used as the Hatteras backup.
        other = _wind("ok", {"id": "8658163", "name": "Wrightsville Beach"}, 6)
        b = _build(_payload(_wind("stale", BUOY, 285), other))
        self.assertNotIn("Wind", dict(b["items"]))


class BothStale(unittest.TestCase):
    def test_both_stale_shows_no_wind_and_names_both(self):
        b = _build(_payload(_wind("stale", BUOY, 285), _wind("stale", SHORE, 120)))
        self.assertNotIn("Wind", dict(b["items"]))
        self.assertFalse([f for f in b["freshness"] if f["label"].startswith("Wind")])
        m = [x for x in b["missing"] if x.startswith("wind (")]
        self.assertEqual(len(m), 1)
        self.assertIn("offshore buoy 41025 stale: last report %s" % brief._t(_iso(285)), m[0])
        self.assertIn("coastal backup USCG Station Hatteras stale: last report %s" % brief._t(_iso(120)), m[0])
        self.assertIn("neither used", m[0])
        self.assertEqual(b["windSource"], {"role": "none", "state": "unavailable"})
        self.assertFalse([c for c in brief._glance({**b, "regionId": "hatteras"}) if c["tone"] == "wind"])

    def test_both_missing(self):
        b = _build(_payload({"status": "unavailable"}, {"status": "unavailable"}))
        self.assertNotIn("Wind", dict(b["items"]))
        self.assertTrue(any(x.startswith("wind (offshore buoy 41025 not reporting; coastal backup USCG Station Hatteras not reporting")
                            for x in b["missing"]))


class OtherRegionsUnchanged(unittest.TestCase):
    def test_crystal_coast_has_no_backup_and_same_text(self):
        p = _payload({"status": "stale", "time": _iso(285), "station": {"id": "CLKN7", "name": "Cape Lookout"},
                      "values": {"speedKt": 12.0, "gustKt": 16.0, "dirCompass": "NE"}},
                     _wind("ok", {"id": "8656483", "name": "Beaufort"}, 6))
        p["region"] = {"id": "crystal-coast", "name": "Morehead City · Beaufort"}
        b = _build(p, rid="crystal-coast")
        self.assertNotIn("Wind", dict(b["items"]))
        self.assertIn("wind (stale: last report %s, not used)" % brief._t(_iso(285)), b["missing"])
        self.assertNotIn("windSource", b)
        p2 = copy.deepcopy(p); p2["readings"]["wind"] = _wind("ok", {"id": "CLKN7", "name": "Cape Lookout"}, 20)
        b2 = _build(p2, rid="crystal-coast")
        self.assertEqual(dict(b2["items"])["Wind"], "16 kt from the NNE, gusting 19, at Cape Lookout.")


if __name__ == "__main__":
    unittest.main()
