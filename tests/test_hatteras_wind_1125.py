"""Hatteras conditions/homepage wind selection (Ed t474u, Nov 25 2026).

The dashboard and homepage must use the same freshness threshold and backup-source
rule as the Morning Brief: Diamond Shoals 41025 stays primary when fresh; a stale
or missing primary yields the USCG Hatteras coastal backup when that reading is
fresh; both unusable yields unavailable. Nothing is invented. Archived briefs are
not rewritten. Offline fixtures only.
"""
from __future__ import annotations

import copy
import unittest
from datetime import datetime, timedelta, timezone

import brief
import conditions
import homepage_boot
import sprint_home

NOW = datetime(2026, 11, 25, 14, 10, tzinfo=timezone.utc)  # 9:10 AM ET
BUOY = {"id": "41025", "name": "Diamond Shoals"}
SHORE = {"id": "8654467", "name": "USCG Station Hatteras"}


def _iso(minutes_ago, now=NOW):
    return (now - timedelta(minutes=minutes_ago)).isoformat().replace("+00:00", "Z")


def _wind(status, station, minutes_ago, speed=27.0, gust=33.0, d="ENE", now=NOW):
    r = {
        "status": status,
        "kind": "observed",
        "time": _iso(minutes_ago, now),
        "ageMin": minutes_ago,
        "station": dict(station),
        "values": {"speedKt": speed, "gustKt": gust, "dirCompass": d, "dirDeg": 70.0},
    }
    r["staleAfterMin"] = 75 if station["id"] == "41025" else 45
    if status == "unavailable":
        r.pop("time", None)
        r.pop("values", None)
        r["lastReport"] = _iso(minutes_ago, now) if minutes_ago is not None else None
    return r


def _payload(wind, harbor, rid="hatteras"):
    R = {"wind": wind}
    if harbor is not None:
        R["harborWind"] = harbor
    return {
        "ok": True,
        "region": {"id": rid, "name": "Hatteras Island" if rid == "hatteras" else rid},
        "readings": R,
        "alerts": {"status": "ok", "items": [{"event": "Coastal Flood Warning", "ends": _iso(-60)}]},
        "generatedAt": NOW.isoformat().replace("+00:00", "Z"),
    }


class SelectWind(unittest.TestCase):
    def test_fresh_primary_keeps_diamond_shoals(self):
        prim = _wind("ok", BUOY, 20, speed=27.0, gust=33.0)
        harbor = _wind("ok", SHORE, 6, speed=14.0, gust=20.0, d="NE")
        readings = {"wind": prim, "harborWind": harbor}
        orig = copy.deepcopy(readings)
        sel = conditions.select_wind("hatteras", readings)
        self.assertEqual(sel["role"], "primary")
        self.assertIs(sel["reading"], prim)
        self.assertEqual(sel["reading"]["station"]["id"], "41025")
        self.assertEqual(sel["reading"]["values"]["speedKt"], 27.0)
        self.assertFalse(sel["partial"])
        self.assertEqual(readings, orig)  # never mutate stored readings

    def test_stale_primary_uses_coastal_backup(self):
        prim = _wind("stale", BUOY, 140, speed=27.0, gust=33.0)
        harbor = _wind("ok", SHORE, 12, speed=14.0, gust=20.0, d="NE")
        readings = {"wind": prim, "harborWind": harbor}
        orig_harbor = copy.deepcopy(harbor)
        sel = conditions.select_wind("hatteras", readings)
        self.assertEqual(sel["role"], "backup")
        self.assertTrue(sel["partial"])
        r = sel["reading"]
        self.assertEqual(r["station"]["id"], "8654467")
        self.assertEqual(r["station"]["name"], "USCG Station Hatteras")
        self.assertEqual(r["values"]["speedKt"], 14.0)
        self.assertEqual(r["status"], "ok")
        self.assertEqual(r["time"], harbor["time"])  # real observation time
        self.assertEqual(r["sourceType"], "coastal")
        self.assertIn("Coastal backup, USCG Station Hatteras", r["note"])
        self.assertIn("shore station at Hatteras Inlet", r["note"])
        self.assertIn("Offshore buoy 41025 stale since", r["note"])
        self.assertIn("not used", r["note"])
        self.assertIn(conditions.et_clock(prim["time"]), r["note"])
        self.assertNotIn("27", r["note"])  # stale primary values are not blended
        self.assertEqual(sel["primaryUnused"]["station"], "41025")
        self.assertEqual(sel["primaryUnused"]["time"], prim["time"])
        self.assertEqual(readings["harborWind"], orig_harbor)  # source reading unchanged

    def test_missing_primary_uses_coastal_backup(self):
        prim = {"status": "unavailable", "kind": "observed", "tried": [{"id": "41025", "result": "no report"}],
                "station": dict(BUOY)}
        harbor = _wind("ok", SHORE, 8, speed=14.0, gust=20.0, d="NE")
        sel = conditions.select_wind("hatteras", {"wind": prim, "harborWind": harbor})
        self.assertEqual(sel["role"], "backup")
        self.assertEqual(sel["reading"]["values"]["speedKt"], 14.0)
        self.assertIn("not reporting", sel["reading"]["note"])
        self.assertIn("not used", sel["reading"]["note"])

    def test_both_missing_is_unavailable(self):
        prim = {"status": "unavailable", "kind": "observed", "station": dict(BUOY)}
        harbor = {"status": "unavailable", "kind": "observed", "station": dict(SHORE)}
        sel = conditions.select_wind("hatteras", {"wind": prim, "harborWind": harbor})
        self.assertEqual(sel["role"], "none")
        r = sel["reading"]
        self.assertEqual(r["status"], "unavailable")
        self.assertNotIn("values", r)
        self.assertIn("neither used", r["note"])
        self.assertIn("41025", r["note"])
        self.assertIn("USCG Station Hatteras", r["note"])

    def test_both_stale_is_unavailable(self):
        prim = _wind("stale", BUOY, 200, speed=27.0)
        harbor = _wind("stale", SHORE, 90, speed=14.0)
        sel = conditions.select_wind("hatteras", {"wind": prim, "harborWind": harbor})
        self.assertEqual(sel["role"], "none")
        self.assertEqual(sel["reading"]["status"], "unavailable")
        self.assertIsNone((sel["reading"].get("values") or {}).get("speedKt"))
        self.assertIn("stale: last report", sel["reading"]["note"])
        self.assertIn(conditions.et_clock(prim["time"]), sel["reading"]["note"])
        self.assertIn(conditions.et_clock(harbor["time"]), sel["reading"]["note"])

    def test_recovered_primary_returns_to_diamond_shoals(self):
        stale = _wind("stale", BUOY, 140, speed=27.0)
        harbor = _wind("ok", SHORE, 8, speed=14.0, gust=20.0, d="NE")
        first = conditions.select_wind("hatteras", {"wind": stale, "harborWind": harbor})
        self.assertEqual(first["role"], "backup")
        recovered = _wind("ok", BUOY, 15, speed=22.0, gust=28.0, d="ENE")
        second = conditions.select_wind("hatteras", {"wind": recovered, "harborWind": harbor})
        self.assertEqual(second["role"], "primary")
        self.assertEqual(second["reading"]["station"]["id"], "41025")
        self.assertEqual(second["reading"]["values"]["speedKt"], 22.0)
        self.assertFalse(second["partial"])
        self.assertIs(second["reading"], recovered)

    def test_wrong_harbor_station_is_not_used(self):
        prim = _wind("stale", BUOY, 140)
        other = _wind("ok", {"id": "8658163", "name": "Wrightsville Beach"}, 6)
        sel = conditions.select_wind("hatteras", {"wind": prim, "harborWind": other})
        self.assertEqual(sel["role"], "none")

    def test_other_region_keeps_stale_primary(self):
        prim = _wind("stale", {"id": "CLKN7", "name": "Cape Lookout"}, 140, speed=16.0)
        harbor = _wind("ok", {"id": "8656483", "name": "Beaufort"}, 6, speed=9.0)
        sel = conditions.select_wind("crystal-coast", {"wind": prim, "harborWind": harbor})
        self.assertEqual(sel["role"], "primary")
        self.assertIs(sel["reading"], prim)
        self.assertEqual(sel["reading"]["status"], "stale")


class Surfaces(unittest.TestCase):
    def test_homepage_and_glance_use_backup_and_keep_alerts(self):
        payload = _payload(_wind("stale", BUOY, 140, speed=27.0, gust=33.0),
                           _wind("ok", SHORE, 12, speed=14.0, gust=20.0, d="NE"))
        payload["windSelection"] = conditions.select_wind("hatteras", payload["readings"])
        model = sprint_home.salt_model(payload)
        wind = model["tiles"][0]
        self.assertEqual(wind["name"], "Wind · coastal backup")
        self.assertEqual(wind["num"], "14")
        self.assertEqual(wind["dir"], "NE")
        self.assertEqual(wind["state"], "ok")
        self.assertEqual(wind["badge"], "PARTIAL")
        self.assertIn("USCG Station Hatteras", wind["src"])
        self.assertIn("8654467", wind["src"])
        self.assertIn(sprint_home.et_time(payload["readings"]["harborWind"]["time"]), wind["when"])
        self.assertIn("Coastal backup", wind["note"])
        self.assertIn("41025", wind["note"])
        self.assertIn("not used", wind["note"])
        self.assertNotIn("27", wind["num"])
        # Do not also repeat the harbor station as a secondary wind tile.
        self.assertFalse(any(t.get("id") == "harbor" for t in model["more"]))
        # Official warnings are untouched.
        self.assertEqual(model["alerts"]["state"], "active")
        self.assertEqual(model["alerts"]["items"][0]["event"], "Coastal Flood Warning")

        html = sprint_home.tile_html(wind)
        self.assertIn("Wind · coastal backup", html)
        self.assertIn("PARTIAL", html)
        self.assertIn("14", html)
        self.assertNotIn("<span>Offshore buoy</span>", html)
        self.assertNotIn("t-offtag", html)

        glance = homepage_boot.render_glance_html(payload)
        self.assertIn("Wind · coastal backup", glance)
        self.assertIn("PARTIAL", glance)
        self.assertIn("NE 14 kt", glance)
        self.assertNotIn("27 kt", glance)
        self.assertNotIn("is-stale", glance)

    def test_homepage_recovers_to_primary(self):
        payload = _payload(_wind("ok", BUOY, 15, speed=22.0, gust=28.0),
                           _wind("ok", SHORE, 8, speed=14.0, gust=20.0, d="NE"))
        payload["windSelection"] = conditions.select_wind("hatteras", payload["readings"])
        wind = sprint_home.salt_model(payload)["tiles"][0]
        self.assertEqual(wind["name"], "Wind")
        self.assertEqual(wind["num"], "22")
        self.assertIsNone(wind.get("badge"))
        self.assertIn("Diamond Shoals", wind["src"])
        glance = homepage_boot.render_glance_html(payload)
        self.assertIn("ENE 22 kt", glance)
        self.assertNotIn("coastal backup", glance)

    def test_homepage_both_missing_is_unavailable(self):
        payload = _payload({"status": "unavailable", "station": dict(BUOY)},
                           {"status": "unavailable", "station": dict(SHORE)})
        payload["windSelection"] = conditions.select_wind("hatteras", payload["readings"])
        wind = sprint_home.salt_model(payload)["tiles"][0]
        self.assertEqual(wind["state"], "off")
        self.assertFalse(wind.get("num"))
        self.assertIn("neither used", wind["note"])

    def test_brief_still_agrees_with_select_wind(self):
        """Same decision as the brief; brief wording and archives are unchanged."""
        self.assertIs(brief.WIND_BACKUP, conditions.WIND_BACKUP)
        readings = {
            "wind": _wind("stale", BUOY, 140, speed=27.0),
            "harborWind": _wind("ok", SHORE, 12, speed=14.0, gust=20.0, d="NE"),
        }
        sel = conditions.select_wind("hatteras", readings)
        cfg, bk = brief._wind_backup("hatteras", readings)
        self.assertEqual(sel["role"], "backup")
        self.assertIs(bk, readings["harborWind"])
        self.assertEqual(cfg["station"], "8654467")


if __name__ == "__main__":
    unittest.main()
