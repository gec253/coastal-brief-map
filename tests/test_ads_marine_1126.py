"""t483u: marine ad-pause evaluator (zone feeds, VTEC, fail-closed).

No live NWS calls. Does not enable ads or touch tropical storm mode.
"""
from __future__ import annotations

import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError

import server

ET = timezone(timedelta(hours=-5))
NOW = datetime(2026, 11, 26, 8, 0, tzinfo=ET)  # 8:00 AM ET, Storm Warning still in effect
ROOT = Path(__file__).resolve().parents[1]

# Official VTEC / eventCode samples from the 26 Nov 2026 NWS feed.
VTEC_GALE = "/O.CON.KMHX.GL.W.0033.000000T0000Z-261127T2200Z/"
VTEC_STORM = "/O.CON.KMHX.SR.W.0004.000000T0000Z-261126T1500Z/"
VTEC_SCA = "/O.CON.KMHX.SC.Y.0101.000000T0000Z-261128T0600Z/"
VTEC_AKQ_STORM = "/O.CON.KAKQ.SR.W.0002.000000T0000Z-261126T1800Z/"
VTEC_CAN_GALE = "/O.CAN.KMHX.GL.W.0033.000000T0000Z-261127T2200Z/"
VTEC_NEW_GALE = "/O.NEW.KMHX.GL.W.0034.261126T1300Z-261127T2200Z/"
VTEC_TRW = "/O.NEW.KMHX.TR.W.0001.261126T1200Z-261127T0000Z/"


def _feat(
    event,
    vtec,
    zones,
    *,
    status="Actual",
    message_type="Update",
    onset="2026-11-26T06:08:00-05:00",
    ends="2026-11-27T17:00:00-05:00",
    expires="2026-11-26T18:15:00-05:00",
    ident="urn:oid:example:1",
    replaced_by=None,
    headline=None,
    description="",
    event_code=None,
    area="NC waters",
    severity="Severe",
):
    if event_code is None and vtec:
        # GL.W -> GLW
        m = server._VTEC_RE.search(vtec)
        event_code = (m.group("phen") + m.group("sig")) if m else None
    geocode = {"UGC": list(zones)}
    affected = ["https://api.weather.gov/zones/forecast/%s" % z for z in zones]
    props = {
        "id": ident,
        "event": event,
        "status": status,
        "messageType": message_type,
        "severity": severity,
        "headline": headline or ("%s issued by NWS" % event),
        "description": description,
        "onset": onset,
        "ends": ends,
        "expires": expires,
        "areaDesc": area,
        "geocode": geocode,
        "affectedZones": affected,
        "parameters": {"VTEC": [vtec] if vtec else []},
        "eventCode": {"NationalWeatherService": [event_code] if event_code else []},
        "replacedBy": replaced_by,
        "senderName": "NWS",
    }
    return {"id": ident, "properties": props}


def _collection(*features):
    return json.dumps({"type": "FeatureCollection", "features": list(features)}).encode("utf-8")


def _empty():
    return _collection()


def _urls():
    return server.ads_required_feed_urls()


def _eval(mapping, existing=None, now=NOW):
    urls = _urls()

    def fake_fetch(url, tries=4, timeout=45, backoff=None):
        if url not in mapping and not any(k in url for k in mapping):
            # Unmapped required URL: treat as empty-valid so tests can override one batch.
            if url in urls:
                return 200, "application/json", _empty()
        val = mapping.get(url)
        if val is None:
            for key, item in mapping.items():
                if key != "default" and key in url:
                    val = item
                    break
        if val is None:
            val = mapping.get("default", (200, "application/json", _empty()))
        if isinstance(val, Exception):
            # fetch_url catches these; mimic its (502, text, body) return
            return 502, "text/plain; charset=utf-8", b"upstream error: timeout"
        return val

    with patch("server.fetch_url", side_effect=fake_fetch):
        return server.evaluate_ads(existing, now=now)


def _thanksgiving_features():
    return [
        _feat(
            "Storm Warning",
            VTEC_STORM,
            ["AMZ150", "AMZ152", "AMZ154"],
            ends="2026-11-26T10:00:00-05:00",
            expires="2026-11-26T10:00:00-05:00",
            ident="oid:mhx-storm-inshore",
            area="S of Currituck Beach Light NC to Ocracoke Inlet NC out 20 NM",
        ),
        _feat(
            "Storm Warning",
            VTEC_STORM,
            ["AMZ180", "AMZ182", "AMZ184"],
            ends="2026-11-26T10:00:00-05:00",
            ident="oid:mhx-storm-offshore",
            area="Waters from Currituck Beach Light to Ocracoke Inlet NC 20 to 60 NM",
        ),
        _feat(
            "Gale Warning",
            VTEC_GALE,
            ["AMZ135"],
            ends="2026-11-27T17:00:00-05:00",
            ident="oid:mhx-gale-pamlico",
            area="Pamlico Sound",
        ),
        _feat(
            "Gale Warning",
            VTEC_GALE,
            ["AMZ156", "AMZ158"],
            ends="2026-11-27T19:00:00-05:00",
            ident="oid:mhx-gale-crystal",
            area="Ocracoke Inlet to Surf City out 20 NM",
        ),
        _feat(
            "Small Craft Advisory",
            VTEC_SCA,
            ["AMZ136", "AMZ137"],
            ends="2026-11-28T01:00:00-05:00",
            ident="oid:mhx-sca-rivers",
            area="Pamlico and Pungo Rivers; Neuse and Bay Rivers",
            severity="Moderate",
        ),
        _feat(
            "Storm Warning",
            VTEC_AKQ_STORM,
            ["ANZ633"],
            ends="2026-11-26T13:00:00-05:00",
            ident="oid:akq-storm-sound",
            area="Currituck Sound",
        ),
        _feat(
            "Storm Warning",
            VTEC_AKQ_STORM,
            ["ANZ658", "ANZ688"],
            ends="2026-11-26T16:00:00-05:00",
            ident="oid:akq-storm-nearshore",
            area="Coastal waters from NC VA border to Currituck Beach Light NC",
        ),
    ]


class ZoneCoverage(unittest.TestCase):
    def test_required_urls_use_zone_query_not_statewide_marine(self):
        urls = _urls()
        self.assertEqual(len(urls), 3)
        self.assertTrue(urls[0].startswith("https://api.weather.gov/alerts/active?status=actual&zone="))
        self.assertTrue(urls[1].startswith("https://api.weather.gov/alerts/active?status=actual&zone="))
        self.assertEqual(urls[2], "https://api.weather.gov/alerts/active?area=NC&status=actual")
        self.assertNotIn("area=NC&status=actual", urls[0])
        joined = ",".join(urls)
        for z in ("AMZ150", "AMZ135", "AMZ158", "AMZ250", "AMZ280", "ANZ633", "ANZ658", "ANZ688"):
            self.assertIn(z, joined)
        # Virginia-only Wakefield waters stay out.
        self.assertNotIn("ANZ654", joined)
        self.assertNotIn("ANZ656", joined)

    def test_marine_url_matches_conditions_pattern(self):
        url = server.ads_marine_alerts_url(["AMZ154", "AMZ152"])
        self.assertEqual(url, "https://api.weather.gov/alerts/active?status=actual&zone=AMZ154,AMZ152")


class ThanksgivingScenario(unittest.TestCase):
    def test_storm_and_gale_including_wakefield_pause_ads(self):
        mhx, akq, land = _urls()
        feats = _thanksgiving_features()
        mhx_body = _collection(*[f for f in feats if not str(f["properties"]["id"]).startswith("oid:akq")])
        akq_body = _collection(*[f for f in feats if str(f["properties"]["id"]).startswith("oid:akq")])
        out = _eval({
            mhx: (200, "application/json", mhx_body),
            akq: (200, "application/json", akq_body),
            land: (200, "application/json", _empty()),
        })
        self.assertFalse(out["adsOn"])
        self.assertTrue(out["hardPause"])
        self.assertEqual(out["mode"], "paused")
        self.assertTrue(out["fetchOk"])
        self.assertTrue(out["coverageComplete"])
        self.assertIsNone(out["settledSince"])
        events = {a["event"] for a in out["alerts"]}
        self.assertIn("Storm Warning", events)
        self.assertIn("Gale Warning", events)
        zones = {z for a in out["alerts"] for z in a["zones"]}
        self.assertTrue({"AMZ150", "AMZ135", "AMZ156", "ANZ633", "ANZ658", "ANZ688"} <= zones)
        # Non-tropical Storm Warning is not tagged tropical and does not imply storm mode.
        storms = [a for a in out["alerts"] if a["event"] == "Storm Warning"]
        self.assertTrue(storms)
        self.assertTrue(all(a.get("tropical") is False for a in storms))
        self.assertTrue(all("SR.W" in a.get("vtec") for a in storms))
        self.assertNotIn("stormMode", out)
        self.assertNotIn("tropicalStormMode", out)

    def test_non_tropical_storm_warning_does_not_set_storm_mode(self):
        mhx, akq, land = _urls()
        feat = _feat("Storm Warning", VTEC_STORM, ["AMZ154"], ends="2026-11-26T10:00:00-05:00", ident="oid:srw")
        out = _eval({mhx: (200, "application/json", _collection(feat))})
        self.assertTrue(out["hardPause"])
        self.assertFalse(out["alerts"][0]["tropical"])
        self.assertEqual(out["alerts"][0]["vtec"], ["SR.W"])
        # evaluate_ads must not write or flip any storm-mode switch.
        self.assertTrue(set(out).isdisjoint({"stormMode", "tropicalStormMode", "storm_mode"}))
        chunk = Path(server.__file__).read_text().split("def evaluate_ads")[1].split("def _to_et")[0]
        self.assertNotIn("storm_mode", chunk)
        self.assertNotIn("stormMode", chunk)


class WarningLifecycle(unittest.TestCase):
    def test_warning_begins_then_ends_then_twelve_hour_hold(self):
        mhx, _akq, _land = _urls()
        before = NOW - timedelta(hours=2)
        empty = _eval({}, existing=None, now=before)
        self.assertTrue(empty["adsOn"])
        self.assertFalse(empty["hardPause"])

        start = NOW
        gale = _feat("Gale Warning", VTEC_NEW_GALE, ["AMZ135"], onset=start.isoformat(),
                     ends=(start + timedelta(hours=6)).isoformat(), ident="oid:gale-live")
        paused = _eval({mhx: (200, "application/json", _collection(gale))}, existing=empty, now=start)
        self.assertFalse(paused["adsOn"])
        self.assertTrue(paused["hardPause"])
        self.assertIsNone(paused["settledSince"])

        ended_at = start + timedelta(hours=6, minutes=1)
        # Product gone from the active feed (expired / ended).
        hold = _eval({}, existing=paused, now=ended_at)
        self.assertFalse(hold["adsOn"])
        self.assertFalse(hold["hardPause"])
        self.assertEqual(hold["mode"], "paused")
        self.assertIsNotNone(hold["settledSince"])
        self.assertEqual(hold["resumeAfter"], server.iso(ended_at + server.RESUME_AFTER))

        still = _eval({}, existing=hold, now=ended_at + timedelta(hours=11, minutes=59))
        self.assertFalse(still["adsOn"])
        self.assertEqual(still["settledSince"], hold["settledSince"])

        done = _eval({}, existing=hold, now=ended_at + timedelta(hours=12, minutes=1))
        self.assertTrue(done["adsOn"])
        self.assertFalse(done["hardPause"])
        self.assertEqual(done["mode"], "full")
        self.assertIsNone(done["settledSince"])
        self.assertIsNone(done["resumeAfter"])

    def test_twelve_hour_hold_length_unchanged(self):
        self.assertEqual(server.RESUME_AFTER, timedelta(hours=12))


class ReplacedUpdatedCanceled(unittest.TestCase):
    def test_replaced_product_is_ignored_replacement_counts(self):
        mhx, _akq, _land = _urls()
        old = _feat("Gale Warning", VTEC_GALE, ["AMZ135"], ident="oid:old",
                    replaced_by="https://api.weather.gov/alerts/oid:new")
        new = _feat("Gale Warning", VTEC_GALE, ["AMZ135", "AMZ230"], ident="oid:new", message_type="Update")
        out = _eval({mhx: (200, "application/json", _collection(old, new))})
        ids = [a["id"] for a in out["alerts"]]
        self.assertIn("oid:new", ids)
        self.assertNotIn("oid:old", ids)
        self.assertTrue(out["hardPause"])

    def test_canceled_message_does_not_pause(self):
        mhx, _akq, _land = _urls()
        canceled = _feat("Gale Warning", VTEC_CAN_GALE, ["AMZ135"], ident="oid:can",
                         message_type="Cancel")
        out = _eval({mhx: (200, "application/json", _collection(canceled))})
        self.assertFalse(out["hardPause"])
        self.assertTrue(out["adsOn"])
        self.assertEqual(out["alerts"], [])

    def test_vtec_can_without_cancel_message_type_is_inactive(self):
        mhx, _akq, _land = _urls()
        canceled = _feat("Gale Warning", VTEC_CAN_GALE, ["AMZ135"], ident="oid:can2",
                         message_type="Alert")
        out = _eval({mhx: (200, "application/json", _collection(canceled))})
        self.assertFalse(out["hardPause"])
        self.assertTrue(out["adsOn"])

    def test_expired_ends_timestamp_is_ignored_even_if_still_listed(self):
        mhx, _akq, _land = _urls()
        expired = _feat("Storm Warning", VTEC_STORM, ["AMZ154"], ident="oid:ended",
                        ends="2026-11-26T06:00:00-05:00", expires="2026-11-26T06:00:00-05:00")
        out = _eval({mhx: (200, "application/json", _collection(expired))}, now=NOW)
        self.assertFalse(out["hardPause"])
        self.assertTrue(out["adsOn"])

    def test_headline_replaced_language_is_skipped(self):
        mhx, _akq, _land = _urls()
        replaced = _feat(
            "Gale Warning", VTEC_GALE, ["AMZ135"], ident="oid:head",
            headline="The Gale Warning has been replaced by a Storm Warning",
        )
        out = _eval({mhx: (200, "application/json", _collection(replaced))})
        self.assertFalse(out["hardPause"])
        self.assertTrue(out["adsOn"])


class FeedFailures(unittest.TestCase):
    def test_timeout_fails_closed_and_does_not_keep_ads_on(self):
        mhx, akq, land = _urls()
        previous = {
            "adsOn": True, "mode": "full", "hardPause": False,
            "reducedRegions": [], "reasons": [], "settledSince": None,
            "resumeAfter": None, "alerts": [], "fetchOk": True, "coverageComplete": True,
            "evaluatedAt": server.iso(NOW - timedelta(minutes=6)),
        }
        out = _eval({mhx: URLError("timed out"), akq: (200, "application/json", _empty()),
                     land: (200, "application/json", _empty())}, existing=previous, now=NOW)
        self.assertFalse(out["adsOn"])
        self.assertEqual(out["mode"], "paused")
        self.assertFalse(out["fetchOk"])
        self.assertFalse(out["coverageComplete"])
        self.assertFalse(out["hardPause"])
        self.assertIsNotNone(out["settledSince"])
        self.assertIsNotNone(out["resumeAfter"])

    def test_malformed_json_fails_closed(self):
        mhx, _akq, _land = _urls()
        previous = {"adsOn": True, "mode": "full", "hardPause": False, "evaluatedAt": server.iso(NOW)}
        out = _eval({mhx: (200, "application/json", b"{not-json")}, existing=previous, now=NOW)
        self.assertFalse(out["adsOn"])
        self.assertFalse(out["fetchOk"])
        self.assertFalse(out["coverageComplete"])

    def test_missing_features_key_is_malformed(self):
        mhx, _akq, _land = _urls()
        out = _eval({mhx: (200, "application/json", b'{"type":"FeatureCollection"}')}, now=NOW)
        self.assertFalse(out["adsOn"])
        self.assertFalse(out["coverageComplete"])

    def test_empty_but_valid_is_all_clear(self):
        out = _eval({}, existing=None, now=NOW)
        self.assertTrue(out["adsOn"])
        self.assertFalse(out["hardPause"])
        self.assertEqual(out["mode"], "full")
        self.assertTrue(out["fetchOk"])
        self.assertTrue(out["coverageComplete"])
        self.assertEqual(out["alerts"], [])

    def test_partial_zone_coverage_fails_closed(self):
        mhx, akq, land = _urls()
        # MHX/ILM succeeded with no warnings; Wakefield batch failed.
        out = _eval({
            mhx: (200, "application/json", _empty()),
            akq: (502, "text/plain", b"upstream error"),
            land: (200, "application/json", _empty()),
        }, existing={"adsOn": True, "mode": "full", "hardPause": False}, now=NOW)
        self.assertFalse(out["adsOn"])
        self.assertFalse(out["coverageComplete"])
        self.assertFalse(out["fetchOk"])
        self.assertEqual(out["mode"], "paused")

    def test_partial_feed_still_pauses_when_a_successful_batch_has_a_gale(self):
        mhx, akq, land = _urls()
        gale = _feat("Gale Warning", VTEC_GALE, ["AMZ135"], ident="oid:g")
        out = _eval({
            mhx: (200, "application/json", _collection(gale)),
            akq: (502, "text/plain", b"upstream error"),
            land: (200, "application/json", _empty()),
        }, now=NOW)
        self.assertFalse(out["adsOn"])
        self.assertTrue(out["hardPause"])
        self.assertFalse(out["coverageComplete"])
        self.assertIsNone(out["settledSince"])

    def test_default_with_no_previous_state_is_paused_on_failure_not_ads_on(self):
        mhx, _akq, _land = _urls()
        out = _eval({mhx: (503, "text/plain", b"nope")}, existing=None, now=NOW)
        self.assertFalse(out["adsOn"])
        self.assertEqual(out["mode"], "paused")
        self.assertFalse(out.get("adsOn", True))

    def test_stale_ads_on_evaluation_is_not_safe(self):
        stale = {
            "adsOn": True, "mode": "full", "hardPause": False,
            "fetchOk": True, "coverageComplete": True,
            "evaluatedAt": server.iso(NOW - timedelta(minutes=16)),
        }
        self.assertFalse(server._ads_is_safe_on_result(stale, now=NOW))
        fresh = dict(stale, evaluatedAt=server.iso(NOW - timedelta(minutes=5)))
        self.assertTrue(server._ads_is_safe_on_result(fresh, now=NOW))


class OutageRecovery(unittest.TestCase):
    def test_recovery_after_outage_follows_twelve_hour_hold(self):
        previous_on = {"adsOn": True, "mode": "full", "hardPause": False, "settledSince": None}
        failed = _eval({url: (502, "text/plain", b"timeout") for url in _urls()}, existing=previous_on, now=NOW)
        self.assertFalse(failed["adsOn"])
        self.assertEqual(failed["mode"], "paused")

        recovered = _eval({}, existing=failed, now=NOW + timedelta(minutes=5))
        self.assertFalse(recovered["adsOn"])
        self.assertFalse(recovered["hardPause"])
        self.assertEqual(recovered["mode"], "paused")
        self.assertIsNotNone(recovered["resumeAfter"])
        # Hold starts from the fail-closed evaluation, not from recovery.
        start = server.parse_iso(failed["settledSince"])
        self.assertEqual(server.parse_iso(recovered["resumeAfter"]), start + server.RESUME_AFTER)

        after = _eval({}, existing=recovered, now=start + server.RESUME_AFTER + timedelta(minutes=1))
        self.assertTrue(after["adsOn"])
        self.assertEqual(after["mode"], "full")


class NoWarningAndSoft(unittest.TestCase):
    def test_no_warning_conditions_ads_full(self):
        out = _eval({}, now=NOW)
        self.assertTrue(out["adsOn"])
        self.assertEqual(out["mode"], "full")
        self.assertFalse(out["hardPause"])

    def test_sca_only_reduces_density_on_affected_region(self):
        mhx, _akq, _land = _urls()
        sca = _feat("Small Craft Advisory", VTEC_SCA, ["AMZ136"], ident="oid:sca", severity="Moderate")
        out = _eval({mhx: (200, "application/json", _collection(sca))}, now=NOW)
        self.assertTrue(out["adsOn"])
        self.assertEqual(out["mode"], "reduced")
        self.assertEqual(out["reducedRegions"], ["central"])
        self.assertFalse(out["hardPause"])

    def test_exercise_status_is_ignored(self):
        mhx, _akq, _land = _urls()
        exercise = _feat("Gale Warning", VTEC_GALE, ["AMZ135"], ident="oid:ex", status="Exercise")
        out = _eval({mhx: (200, "application/json", _collection(exercise))}, now=NOW)
        self.assertFalse(out["hardPause"])
        self.assertTrue(out["adsOn"])

    def test_tropical_warning_on_land_pauses_without_marine_zones(self):
        _mhx, _akq, land = _urls()
        trop = _feat(
            "Tropical Storm Warning", VTEC_TRW, ["NCZ205"], ident="oid:trw",
            event_code="TRW", ends="2026-11-27T00:00:00-05:00",
        )
        out = _eval({land: (200, "application/json", _collection(trop))}, now=NOW)
        self.assertTrue(out["hardPause"])
        self.assertFalse(out["adsOn"])
        self.assertTrue(out["alerts"][0]["tropical"])
        self.assertEqual(out["alerts"][0]["vtec"], ["TR.W"])

    def test_high_wind_warning_does_not_hard_pause(self):
        mhx, _akq, land = _urls()
        # Land product on the statewide feed must not pause ads.
        hww = _feat("High Wind Warning", "/O.CON.KMHX.HW.W.0001.000000T0000Z-261126T1500Z/",
                    ["NCZ205"], ident="oid:hww", event_code="HWW")
        out = _eval({land: (200, "application/json", _collection(hww))}, now=NOW)
        self.assertFalse(out["hardPause"])
        self.assertTrue(out["adsOn"])


class GetAdsSafety(unittest.TestCase):
    def test_get_ads_does_not_write_ads_on_after_failed_fetch(self,):
        tmp = ROOT / "tests" / ".tmp-ads-marine-1126.json"
        self.addCleanup(lambda: tmp.exists() and tmp.unlink())
        tmp.write_text(json.dumps({
            "adsOn": True, "mode": "full", "hardPause": False,
            "fetchOk": True, "coverageComplete": True,
            "evaluatedAt": server.iso(NOW - timedelta(hours=2)),
            "settledSince": None, "resumeAfter": None, "alerts": [], "reasons": [],
        }))
        with patch.object(server, "ADS_PATH", tmp), \
                patch("server.fetch_url", return_value=(502, "text/plain", b"timeout")), \
                patch("server.now_utc", return_value=NOW):
            out = server.get_ads(force=True)
        self.assertFalse(out["adsOn"])
        written = json.loads(tmp.read_text())
        self.assertFalse(written["adsOn"])
        self.assertEqual(written["mode"], "paused")

    def test_fetch_url_defaults_untouched(self):
        import inspect
        sig = inspect.signature(server.fetch_url)
        self.assertEqual(sig.parameters["tries"].default, 4)
        self.assertEqual(sig.parameters["timeout"].default, 45)


if __name__ == "__main__":
    unittest.main()
