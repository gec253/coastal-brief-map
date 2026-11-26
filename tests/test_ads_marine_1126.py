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
    sent="2026-11-26T06:08:00-05:00",
    effective=None,
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
        "sent": sent,
        "effective": effective or sent,
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
        if url not in mapping and not any(k in url for k in mapping if k not in ("default",)):
            # Unmapped required or history URL: empty-valid so tests can override one batch.
            if url in urls or url.startswith("https://api.weather.gov/alerts"):
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

        official_end = start + timedelta(hours=6)
        ended_at = official_end + timedelta(minutes=1)
        # Product gone from the active feed (expired / ended).
        hold = _eval({}, existing=paused, now=ended_at)
        self.assertFalse(hold["adsOn"])
        self.assertFalse(hold["hardPause"])
        self.assertEqual(hold["mode"], "paused")
        self.assertEqual(hold["pauseReason"], "hold")
        self.assertEqual(hold["settledSince"], server.iso(official_end))
        self.assertEqual(hold["resumeAfter"], server.iso(official_end + server.RESUME_AFTER))
        self.assertEqual(hold["holdUntil"], hold["resumeAfter"])

        still = _eval({}, existing=hold, now=official_end + timedelta(hours=11, minutes=59))
        self.assertFalse(still["adsOn"])
        self.assertEqual(still["settledSince"], hold["settledSince"])

        done = _eval({}, existing=hold, now=official_end + timedelta(hours=12, minutes=1))
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
            "lastGoodEvaluatedAt": server.iso(NOW - timedelta(minutes=6)),
            "pauseReason": None, "knownWarnings": [], "outageStartedAt": None,
        }
        out = _eval({mhx: URLError("timed out"), akq: (200, "application/json", _empty()),
                     land: (200, "application/json", _empty())}, existing=previous, now=NOW)
        self.assertFalse(out["adsOn"])
        self.assertEqual(out["mode"], "paused")
        self.assertFalse(out["fetchOk"])
        self.assertFalse(out["coverageComplete"])
        self.assertFalse(out["hardPause"])
        self.assertEqual(out["pauseReason"], "outage")
        self.assertIsNone(out["settledSince"])
        self.assertIsNone(out["resumeAfter"])
        self.assertIsNotNone(out["outageStartedAt"])
        self.assertEqual(out["knownWarnings"], [])
        self.assertEqual(out["lastGoodEvaluatedAt"], previous["evaluatedAt"])

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
    def test_short_outage_without_known_warning_recovers_without_hold(self):
        previous_on = {
            "adsOn": True, "mode": "full", "hardPause": False, "settledSince": None,
            "fetchOk": True, "coverageComplete": True,
            "evaluatedAt": server.iso(NOW - timedelta(minutes=3)),
            "lastGoodEvaluatedAt": server.iso(NOW - timedelta(minutes=3)),
            "pauseReason": None, "knownWarnings": [],
        }
        failed = _eval({url: (502, "text/plain", b"timeout") for url in _urls()}, existing=previous_on, now=NOW)
        self.assertFalse(failed["adsOn"])
        self.assertEqual(failed["mode"], "paused")
        self.assertEqual(failed["pauseReason"], "outage")
        self.assertIsNone(failed["settledSince"])
        self.assertIsNone(failed["resumeAfter"])
        self.assertEqual(failed["knownWarnings"], [])

        recovered = _eval({}, existing=failed, now=NOW + timedelta(minutes=5))
        self.assertTrue(recovered["adsOn"])
        self.assertFalse(recovered["hardPause"])
        self.assertIn(recovered["mode"], {"full", "reduced"})
        self.assertIsNone(recovered["resumeAfter"])
        self.assertIsNone(recovered["pauseReason"])


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


class ThanksgivingSequence(unittest.TestCase):
    def test_full_storm_outage_recovery_hold_sequence(self):
        mhx, _akq, _land = _urls()
        storm_end = NOW + timedelta(hours=2)
        storm = _feat(
            "Storm Warning", VTEC_STORM, ["AMZ154"],
            onset=NOW.isoformat(), ends=storm_end.isoformat(), ident="oid:storm-live",
        )
        # 1. Storm Warning active -> immediate pause. Ads logic does not
        # consult observations; no NDBC/station URL is fetched.
        fetched = []

        def track(mapping):
            def fake(url, tries=4, timeout=45, backoff=None):
                fetched.append(url)
                if url in mapping:
                    return mapping[url]
                if url.startswith("https://api.weather.gov/alerts"):
                    return 200, "application/json", _empty()
                raise AssertionError("unexpected URL %s" % url)
            return fake

        mapping = {mhx: (200, "application/json", _collection(storm))}
        with __import__("unittest.mock", fromlist=["patch"]).patch("server.fetch_url", side_effect=track(mapping)):
            active = server.evaluate_ads(None, now=NOW)
        self.assertTrue(active["hardPause"])
        self.assertFalse(active["adsOn"])
        self.assertEqual(active["pauseReason"], "warning")
        self.assertEqual(active["knownWarnings"][0]["id"], "oid:storm-live")
        self.assertTrue(all("api.weather.gov/alerts" in u for u in fetched))
        self.assertFalse(any("ndbc" in u or "tidesandcurrents" in u or "waterservices" in u for u in fetched))

        # 2. NWS feed fails -> stay paused, retain the verified warning, no hold reset.
        t_out = NOW + timedelta(minutes=20)
        outage = _eval({url: (502, "text/plain", b"timeout") for url in _urls()}, existing=active, now=t_out)
        self.assertFalse(outage["adsOn"])
        self.assertTrue(outage["hardPause"])
        self.assertEqual(outage["pauseReason"], "warning")
        self.assertEqual([w["id"] for w in outage["knownWarnings"]], ["oid:storm-live"])
        self.assertEqual(outage["knownWarnings"][0]["zones"], ["AMZ154"])
        self.assertEqual(outage["knownWarnings"][0]["ends"], storm_end.isoformat())
        self.assertIsNotNone(outage["outageStartedAt"])
        self.assertIsNone(outage["settledSince"])

        # 3. Feed recovers, warning still active -> paused, no hold started, no reset.
        t_back = t_out + timedelta(minutes=10)
        still = _eval({mhx: (200, "application/json", _collection(storm))}, existing=outage, now=t_back)
        self.assertTrue(still["hardPause"])
        self.assertFalse(still["adsOn"])
        self.assertEqual(still["pauseReason"], "warning")
        self.assertIsNone(still["settledSince"])
        self.assertIsNone(still["outageStartedAt"])
        self.assertTrue(still["coverageComplete"])

        # 4. Warning ends -> 12-hour hold starts at the official end, not at recovery.
        t_ended = storm_end + timedelta(minutes=5)
        hold = _eval({}, existing=still, now=t_ended)
        self.assertFalse(hold["adsOn"])
        self.assertFalse(hold["hardPause"])
        self.assertEqual(hold["pauseReason"], "hold")
        self.assertEqual(hold["settledSince"], server.iso(storm_end))
        self.assertEqual(hold["resumeAfter"], server.iso(storm_end + server.RESUME_AFTER))

        # 5. Still paused just before the hold expires; ads allowed after.
        almost = _eval({}, existing=hold, now=storm_end + server.RESUME_AFTER - timedelta(minutes=1))
        self.assertFalse(almost["adsOn"])
        self.assertEqual(almost["pauseReason"], "hold")
        done = _eval({}, existing=hold, now=storm_end + server.RESUME_AFTER + timedelta(minutes=1))
        self.assertTrue(done["adsOn"])
        self.assertIsNone(done["pauseReason"])


class RestartPersistence(unittest.TestCase):
    def test_restart_mid_hold_keeps_hold(self):
        started = NOW
        hold = {
            "adsOn": False, "mode": "paused", "hardPause": False,
            "pauseReason": "hold",
            "settledSince": server.iso(started),
            "holdStartedAt": server.iso(started),
            "resumeAfter": server.iso(started + server.RESUME_AFTER),
            "holdUntil": server.iso(started + server.RESUME_AFTER),
            "knownWarnings": [],
            "fetchOk": True, "coverageComplete": True,
            "evaluatedAt": server.iso(started + timedelta(minutes=1)),
            "lastGoodEvaluatedAt": server.iso(started + timedelta(minutes=1)),
        }
        # Simulate a process restart: only the persisted record is available.
        mid = _eval({}, existing=hold, now=started + timedelta(hours=6))
        self.assertFalse(mid["adsOn"])
        self.assertEqual(mid["pauseReason"], "hold")
        self.assertEqual(mid["settledSince"], hold["settledSince"])
        self.assertEqual(mid["resumeAfter"], hold["resumeAfter"])

    def test_restart_with_no_state_starts_paused_on_incomplete_feed(self):
        out = _eval({url: (502, "text/plain", b"down") for url in _urls()}, existing=None, now=NOW)
        self.assertFalse(out["adsOn"])
        self.assertEqual(out["mode"], "paused")
        self.assertEqual(out["pauseReason"], "unknown")
        self.assertIsNone(out["settledSince"])
        self.assertEqual(out["knownWarnings"], [])

    def test_cold_start_without_recent_clearance_allows_ads_after_complete_eval(self):
        out = _eval({}, existing=None, now=NOW)
        self.assertTrue(out["adsOn"])
        self.assertTrue(out["coverageComplete"])
        self.assertIsNone(out["pauseReason"])

    def test_cold_start_uses_history_when_a_warning_ended_three_hours_ago(self):
        ended = NOW - timedelta(hours=3)
        hist = _feat(
            "Gale Warning", VTEC_GALE, ["AMZ135"], ident="oid:ended-gale",
            onset=(ended - timedelta(hours=6)).isoformat(),
            ends=ended.isoformat(), message_type="Update",
        )
        hist_url = server.ads_recent_marine_alerts_url(NOW - server.ADS_HISTORY_LOOKBACK)
        out = _eval(
            {hist_url: (200, "application/json", _collection(hist))},
            existing=None, now=NOW,
        )
        self.assertFalse(out["adsOn"])
        self.assertEqual(out["pauseReason"], "hold")
        self.assertEqual(out["settledSince"], server.iso(ended))
        self.assertEqual(out["resumeAfter"], server.iso(ended + server.RESUME_AFTER))

    def test_cold_start_stays_paused_if_history_is_unavailable(self):
        hist_urls = server.ads_history_feed_urls(NOW - server.ADS_HISTORY_LOOKBACK)
        out = _eval(
            {hist_urls[0]: (502, "text/plain", b"down"), hist_urls[1]: (200, "application/json", _empty())},
            existing=None, now=NOW,
        )
        self.assertFalse(out["adsOn"])
        self.assertEqual(out["pauseReason"], "unknown")
        self.assertIsNone(out["settledSince"])

    def test_untrusted_committed_ads_json_is_treated_as_no_state(self):
        committed = {
            "adsOn": True, "mode": "full", "hardPause": False,
            "evaluatedAt": "2026-11-14T13:09:38+00:00",
            "reasons": ["No gale-or-stronger warning..."],
            "fetchOk": True,
        }
        self.assertEqual(server._trusted_previous(committed), {})
        out = _eval({url: (502, "text/plain", b"down") for url in _urls()}, existing=committed, now=NOW)
        self.assertFalse(out["adsOn"])
        self.assertEqual(out["pauseReason"], "unknown")


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


# ---------------------------------------------------------------------------
# t485u final preflight: malformed records, pagination, upcoming warnings.
# ---------------------------------------------------------------------------

def _gale(ident="oid:gale-ok", zones=("AMZ135",), **kw):
    return _feat("Gale Warning", VTEC_GALE, list(zones), ident=ident, **kw)


_NULL_FEATURE = object()


def _mutated(mutator):
    """Apply a mutation; a mutator returning a value replaces the whole feature."""
    feat = _gale(ident="oid:mutated")
    out = mutator(feat)
    if out is _NULL_FEATURE:
        return None
    return feat if out is None else out


def _drop(obj, *keys):
    for key in keys:
        obj.pop(key, None)


MALFORMED_MUTATIONS = {
    "non_dict_feature": lambda f: "not-a-feature",
    "null_feature": lambda f: _NULL_FEATURE,
    "properties_none": lambda f: f.__setitem__("properties", None),
    "properties_list": lambda f: f.__setitem__("properties", ["x"]),
    "properties_missing": lambda f: _drop(f, "properties"),
    "parameters_none": lambda f: f["properties"].__setitem__("parameters", None),
    "parameters_string": lambda f: f["properties"].__setitem__("parameters", "VTEC"),
    "vtec_garbage": lambda f: f["properties"]["parameters"].__setitem__("VTEC", ["/garbage/"]),
    "vtec_not_list": lambda f: f["properties"]["parameters"].__setitem__("VTEC", 7),
    "vtec_item_not_str": lambda f: f["properties"]["parameters"].__setitem__("VTEC", [None]),
    "ends_unparseable": lambda f: f["properties"].__setitem__("ends", "tomorrow evening"),
    "ends_naive": lambda f: f["properties"].__setitem__("ends", "2026-11-27T17:00:00"),
    "ends_wrong_type": lambda f: f["properties"].__setitem__("ends", 1764280800),
    "onset_unparseable": lambda f: f["properties"].__setitem__("onset", "soon"),
    "sent_missing": lambda f: _drop(f["properties"], "sent"),
    "effective_missing": lambda f: _drop(f["properties"], "effective"),
    "expires_none": lambda f: f["properties"].__setitem__("expires", None),
    "event_none": lambda f: f["properties"].__setitem__("event", None),
    "event_wrong_type": lambda f: f["properties"].__setitem__("event", 42),
    "id_missing": lambda f: (_drop(f["properties"], "id"), _drop(f, "id")) and None,
    "status_missing": lambda f: _drop(f["properties"], "status"),
    "message_type_wrong_type": lambda f: f["properties"].__setitem__("messageType", ["Update"]),
    "geocode_missing": lambda f: _drop(f["properties"], "geocode"),
    "geocode_string": lambda f: f["properties"].__setitem__("geocode", "AMZ135"),
    "ugc_empty": lambda f: f["properties"]["geocode"].__setitem__("UGC", []),
    "ugc_wrong_type": lambda f: f["properties"]["geocode"].__setitem__("UGC", "AMZ135"),
    "event_code_wrong_type": lambda f: f["properties"].__setitem__("eventCode", "GLW"),
    "event_code_list_wrong": lambda f: f["properties"].__setitem__("eventCode", {"NationalWeatherService": "GLW"}),
    "headline_wrong_type": lambda f: f["properties"].__setitem__("headline", {"x": 1}),
    "affected_zones_wrong_type": lambda f: f["properties"].__setitem__("affectedZones", "AMZ135"),
    "replaced_by_wrong_type": lambda f: f["properties"].__setitem__("replacedBy", ["urn"]),
}


class MalformedAlertRecords(unittest.TestCase):
    def test_each_malformed_record_fails_closed_without_crashing(self):
        mhx, _akq, _land = _urls()
        for name, mutator in MALFORMED_MUTATIONS.items():
            with self.subTest(name=name):
                bad = _mutated(mutator)
                if name not in ("non_dict_feature", "null_feature"):
                    self.assertIsInstance(bad, dict, name)
                self.assertIsNotNone(server._alert_record_problem(bad), name)
                out = _eval({mhx: (200, "application/json", _collection(bad))}, existing=None)
                self.assertFalse(out["adsOn"])
                self.assertEqual(out["mode"], "paused")
                self.assertFalse(out["coverageComplete"])
                self.assertFalse(out["fetchOk"])
                self.assertEqual(out["pauseReason"], "unknown")
                self.assertTrue(any("malformed alert record" in r for r in out["reasons"]))

    def test_malformed_record_in_land_feed_also_fails_closed(self):
        _mhx, _akq, land = _urls()
        bad = _mutated(MALFORMED_MUTATIONS["properties_none"])
        out = _eval({land: (200, "application/json", _collection(bad))}, existing=None)
        self.assertFalse(out["adsOn"])
        self.assertFalse(out["coverageComplete"])

    def test_malformed_record_beside_valid_gale_keeps_the_gale_pause(self):
        mhx, _akq, _land = _urls()
        good = _gale(ident="oid:gale-good")
        bad = _mutated(MALFORMED_MUTATIONS["vtec_garbage"])
        out = _eval({mhx: (200, "application/json", _collection(good, bad))}, existing=None)
        self.assertFalse(out["adsOn"])
        self.assertTrue(out["hardPause"])
        self.assertEqual(out["pauseReason"], "warning")
        self.assertFalse(out["coverageComplete"])
        self.assertEqual([w["id"] for w in out["knownWarnings"]], ["oid:gale-good"])

    def test_malformed_response_during_warning_keeps_known_warning_and_no_hold(self):
        mhx, _akq, _land = _urls()
        storm = _feat("Storm Warning", VTEC_STORM, ["AMZ154"], ident="oid:storm-known",
                      ends=(NOW + timedelta(hours=3)).isoformat())
        active = _eval({mhx: (200, "application/json", _collection(storm))})
        self.assertEqual(active["pauseReason"], "warning")
        bad = _mutated(MALFORMED_MUTATIONS["properties_none"])
        later = NOW + timedelta(minutes=10)
        out = _eval({mhx: (200, "application/json", _collection(bad))}, existing=active, now=later)
        self.assertFalse(out["adsOn"])
        self.assertTrue(out["hardPause"])
        self.assertEqual(out["pauseReason"], "warning")
        self.assertEqual([w["id"] for w in out["knownWarnings"]], ["oid:storm-known"])
        self.assertIsNone(out["settledSince"])

    def test_malformed_response_during_hold_keeps_hold_unchanged(self):
        started = NOW - timedelta(hours=2)
        hold = {
            "adsOn": False, "mode": "paused", "hardPause": False, "pauseReason": "hold",
            "settledSince": server.iso(started), "holdStartedAt": server.iso(started),
            "resumeAfter": server.iso(started + server.RESUME_AFTER), "knownWarnings": [],
            "fetchOk": True, "coverageComplete": True,
            "lastGoodEvaluatedAt": server.iso(NOW - timedelta(minutes=5)),
        }
        mhx, _akq, _land = _urls()
        bad = _mutated(MALFORMED_MUTATIONS["ends_unparseable"])
        out = _eval({mhx: (200, "application/json", _collection(bad))}, existing=hold)
        self.assertFalse(out["adsOn"])
        self.assertEqual(out["pauseReason"], "hold")
        self.assertEqual(out["settledSince"], hold["settledSince"])
        self.assertEqual(out["resumeAfter"], hold["resumeAfter"])

    def test_malformed_history_record_on_cold_start_stays_paused(self):
        bad = _mutated(MALFORMED_MUTATIONS["geocode_missing"])
        hist_url = server.ads_recent_marine_alerts_url(NOW - server.ADS_HISTORY_LOOKBACK)
        out = _eval({hist_url: (200, "application/json", _collection(bad))}, existing=None)
        self.assertFalse(out["adsOn"])
        self.assertEqual(out["pauseReason"], "unknown")
        self.assertTrue(out["coverageComplete"])  # active feeds fine; history is what failed

    def test_truncated_active_feed_is_incomplete(self):
        mhx, _akq, _land = _urls()
        body = json.dumps({"features": [], "pagination": {"next": mhx + "&cursor=abc"}}).encode()
        out = _eval({mhx: (200, "application/json", body)}, existing=None)
        self.assertFalse(out["adsOn"])
        self.assertFalse(out["coverageComplete"])

    def test_unexpected_evaluator_error_fails_closed_and_keeps_warning(self):
        mhx, _akq, _land = _urls()
        storm = _feat("Storm Warning", VTEC_STORM, ["AMZ154"], ident="oid:storm-err")
        active = _eval({mhx: (200, "application/json", _collection(storm))})
        with patch("server._alert_kind", side_effect=RuntimeError("boom")):
            out = _eval({mhx: (200, "application/json", _collection(storm))}, existing=active,
                        now=NOW + timedelta(minutes=5))
        self.assertFalse(out["adsOn"])
        self.assertTrue(out["hardPause"])
        self.assertEqual(out["pauseReason"], "warning")
        self.assertEqual([w["id"] for w in out["knownWarnings"]], ["oid:storm-err"])
        with patch("server._alert_kind", side_effect=RuntimeError("boom")):
            cold = _eval({mhx: (200, "application/json", _collection(storm))}, existing=None)
        self.assertFalse(cold["adsOn"])
        self.assertEqual(cold["pauseReason"], "unknown")

    def test_corrupted_persisted_state_does_not_crash_or_allow_ads_without_history(self):
        hist_urls = server.ads_history_feed_urls(NOW - server.ADS_HISTORY_LOOKBACK)
        for existing in (
            ["not", "a", "dict"],
            {"pauseReason": "hold", "settledSince": "garbage", "lastGoodEvaluatedAt": server.iso(NOW)},
            {"pauseReason": "warning", "hardPause": True, "knownWarnings": "oops"},
            {"pauseReason": "warning", "hardPause": True, "knownWarnings": [{"id": ["x"], "zones": 5}]},
        ):
            with self.subTest(existing=existing):
                out = _eval({hist_urls[0]: (502, "text/plain", b"down")}, existing=existing)
                self.assertFalse(out["adsOn"])

    def test_get_ads_with_non_dict_ads_json_does_not_crash(self):
        tmp = ROOT / "tests" / ".tmp-ads-marine-1126-list.json"
        self.addCleanup(lambda: tmp.exists() and tmp.unlink())
        tmp.write_text("[1, 2, 3]")
        with patch.object(server, "ADS_PATH", tmp), \
                patch("server.fetch_url", return_value=(502, "text/plain", b"timeout")), \
                patch("server.now_utc", return_value=NOW):
            out = server.get_ads(force=False)
        self.assertFalse(out["adsOn"])


def _page(features, next_url=None, pagination=Ellipsis):
    payload = {"type": "FeatureCollection", "features": list(features)}
    if pagination is not Ellipsis:
        payload["pagination"] = pagination
    elif next_url is not None:
        payload["pagination"] = {"next": next_url}
    return 200, "application/json", json.dumps(payload).encode()


def _nws_next(url, cursor):
    """Next link in the array-parameter form NWS returns (verified 26 Nov 2026)."""
    from urllib.parse import urlparse, parse_qsl, urlencode
    q = []
    for key, value in parse_qsl(urlparse(url).query):
        if key == "start":
            q.append((key, value))
        else:
            q.extend(("%s[%d]" % (key, i), v) for i, v in enumerate(value.split(",")))
    q += [("limit", "500"), ("cursor", cursor)]
    return "https://api.weather.gov/alerts?" + urlencode(q)


class HistoryPagination(unittest.TestCase):
    def setUp(self):
        self.url = server.ads_recent_marine_alerts_url(NOW - server.ADS_HISTORY_LOOKBACK)

    def _run(self, pages):
        def fake(url, tries=4, timeout=45, backoff=None):
            if url in pages:
                return pages[url]
            raise AssertionError("unexpected URL %s" % url)
        with patch("server.fetch_url", side_effect=fake):
            return server._fetch_paginated_alerts(self.url)

    def test_valid_chain_to_terminal_page_is_complete(self):
        p2 = _nws_next(self.url, "c2")
        kind, feats = self._run({
            self.url: _page([_gale(ident="h1")], p2),
            p2: _page([_gale(ident="h2")]),  # terminal page: no pagination
        })
        self.assertEqual(kind, "ok")
        self.assertEqual([f["id"] for f in feats], ["h1", "h2"])

    def test_invalid_next_links_are_never_complete(self):
        good_q = _nws_next(self.url, "c2").split("?", 1)[1]
        cases = {
            "other_host": "https://evil.example/alerts?" + good_q,
            "http_scheme": "http://api.weather.gov/alerts?" + good_q,
            "active_path": "https://api.weather.gov/alerts/active?" + good_q,
            "other_path": "https://api.weather.gov/zones?" + good_q,
            "empty_string": "",
            "filters_dropped": "https://api.weather.gov/alerts?cursor=c2",
            "start_moved": _nws_next(self.url.replace(
                (NOW - server.ADS_HISTORY_LOOKBACK).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                (NOW - timedelta(hours=1)).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")), "c2"),
        }
        for name, nxt in cases.items():
            with self.subTest(name=name):
                kind, feats = self._run({self.url: _page([_gale(ident="h1")], nxt)})
                self.assertNotEqual(kind, "ok")
                self.assertEqual(feats, [])
        for name, pag in {"pagination_list": ["x"], "next_int": {"next": 5}, "pagination_str": "next"}.items():
            with self.subTest(name=name):
                kind, _f = self._run({self.url: _page([], pagination=pag)})
                self.assertNotEqual(kind, "ok")

    def test_looping_next_is_incomplete(self):
        p2 = _nws_next(self.url, "c2")
        kind, _f = self._run({self.url: _page([], p2), p2: _page([], p2)})
        self.assertEqual(kind, "loop")

    def test_bad_later_pages_are_incomplete(self):
        p2 = _nws_next(self.url, "c2")
        for name, resp in {
            "http_503": (503, "text/plain", b"busy"),
            "bad_json": (200, "application/json", b"{not json"),
            "no_features": (200, "application/json", b'{"type": "FeatureCollection"}'),
            "bad_record": _page([_mutated(MALFORMED_MUTATIONS["properties_none"])]),
        }.items():
            with self.subTest(name=name):
                kind, feats = self._run({self.url: _page([_gale(ident="h1")], p2), p2: resp})
                self.assertNotEqual(kind, "ok")
                self.assertEqual(feats, [])

    def test_page_cap_exhaustion_is_incomplete(self):
        pages = {}
        cur = self.url
        for i in range(server.ADS_HISTORY_MAX_PAGES + 2):
            nxt = _nws_next(self.url, "c%d" % (i + 2))
            pages[cur] = _page([], nxt)
            cur = nxt
        kind, _f = self._run(pages)
        self.assertEqual(kind, "page_cap")

    def test_cold_start_with_bad_next_link_keeps_ads_off(self):
        out = _eval({self.url: _page([], "https://evil.example/alerts?cursor=1")}, existing=None)
        self.assertFalse(out["adsOn"])
        self.assertEqual(out["pauseReason"], "unknown")

    def test_cold_start_reads_second_page_clearance(self):
        ended = NOW - timedelta(hours=2)
        p2 = _nws_next(self.url, "c2")
        hist = _gale(ident="oid:ended-p2", onset=(ended - timedelta(hours=8)).isoformat(),
                     ends=ended.isoformat())
        out = _eval({p2: _page([hist]), self.url: _page([], p2)}, existing=None)
        self.assertFalse(out["adsOn"])
        self.assertEqual(out["pauseReason"], "hold")
        self.assertEqual(out["settledSince"], server.iso(ended))


VTEC_ILM_GALE_UPCOMING = "/O.CON.KILM.GL.W.0016.261126T2100Z-261128T0600Z/"


class UpcomingWarnings(unittest.TestCase):
    def _wilmington_gale(self, **kw):
        base = dict(
            onset="2026-11-26T16:00:00-05:00", ends="2026-11-28T01:00:00-05:00",
            sent="2026-11-26T04:48:00-05:00", ident="oid:ilm-gale-upcoming",
        )
        base.update(kw)
        return _feat("Gale Warning", VTEC_ILM_GALE_UPCOMING, ["AMZ250", "AMZ252"], **base)

    def test_future_onset_is_labeled_upcoming_and_still_pauses(self):
        mhx, _akq, _land = _urls()
        out = _eval({mhx: (200, "application/json", _collection(self._wilmington_gale()))})
        # Established policy: an issued qualifying warning pauses ads from issuance.
        self.assertFalse(out["adsOn"])
        self.assertTrue(out["hardPause"])
        self.assertEqual(out["pauseReason"], "warning")
        self.assertEqual(out["warningTiming"], "upcoming")
        self.assertEqual(out["knownWarnings"][0]["timing"], "upcoming")
        self.assertEqual(out["knownWarnings"][0]["onset"], server.iso(datetime(2026, 11, 26, 21, 0, tzinfo=timezone.utc)))
        text = " ".join(out["reasons"])
        self.assertIn("upcoming, not yet in effect", text)
        self.assertIn("4:00 PM", text)
        self.assertNotIn("is in effect", text)

    def test_mixed_in_effect_and_upcoming_are_each_labeled(self):
        mhx, _akq, _land = _urls()
        storm = _feat("Storm Warning", VTEC_STORM, ["AMZ154"], ident="oid:storm-now")
        out = _eval({mhx: (200, "application/json", _collection(storm, self._wilmington_gale()))})
        self.assertEqual(out["warningTiming"], "in_effect")
        timing = {w["id"]: w["timing"] for w in out["knownWarnings"]}
        self.assertEqual(timing, {"oid:storm-now": "in_effect", "oid:ilm-gale-upcoming": "upcoming"})
        self.assertTrue(any(r.startswith("Storm Warning is in effect") for r in out["reasons"]))
        self.assertTrue(any(r.startswith("Gale Warning has been issued") for r in out["reasons"]))

    def test_vtec_begin_used_when_onset_missing(self):
        mhx, _akq, _land = _urls()
        gale = self._wilmington_gale(onset=None)
        out = _eval({mhx: (200, "application/json", _collection(gale))})
        self.assertEqual(out["knownWarnings"][0]["timing"], "upcoming")

    def test_onset_passed_is_in_effect(self):
        mhx, _akq, _land = _urls()
        at = datetime(2026, 11, 26, 16, 5, tzinfo=ET)
        out = _eval({mhx: (200, "application/json", _collection(self._wilmington_gale()))}, now=at)
        self.assertEqual(out["warningTiming"], "in_effect")
        self.assertIn("Gale Warning is in effect", " ".join(out["reasons"]))

    def test_retained_upcoming_warning_relabels_after_onset_during_outage(self):
        mhx, _akq, _land = _urls()
        first = _eval({mhx: (200, "application/json", _collection(self._wilmington_gale()))})
        down = {url: (502, "text/plain", b"down") for url in _urls()}
        before = _eval(down, existing=first, now=NOW + timedelta(hours=1))
        self.assertEqual(before["pauseReason"], "warning")
        self.assertEqual(before["warningTiming"], "upcoming")
        self.assertIn("upcoming, not yet in effect", " ".join(before["reasons"]))
        after = _eval(down, existing=before, now=datetime(2026, 11, 26, 16, 30, tzinfo=ET))
        self.assertEqual(after["warningTiming"], "in_effect")
        self.assertIn("remains in effect", " ".join(after["reasons"]))

    def test_upcoming_warning_cancelled_before_onset_starts_hold_at_cancellation(self):
        mhx, _akq, _land = _urls()
        first = _eval({mhx: (200, "application/json", _collection(self._wilmington_gale()))})
        t_cancel = NOW + timedelta(hours=2)
        out = _eval({}, existing=first, now=t_cancel)
        self.assertFalse(out["adsOn"])
        self.assertEqual(out["pauseReason"], "hold")
        self.assertEqual(out["settledSince"], server.iso(t_cancel))


VTEC_UPG_GALE = "/O.UPG.KMHX.GL.W.0033.000000T0000Z-261127T2200Z/"
VTEC_NEW_STORM = "/O.NEW.KMHX.SR.W.0005.000000T0000Z-261127T2200Z/"
VTEC_EXT_GALE = "/O.EXT.KMHX.GL.W.0033.000000T0000Z-261128T0300Z/"
VTEC_NEW_SCA = "/O.NEW.KMHX.SC.Y.0102.000000T0000Z-261127T2200Z/"
VTEC_NEW_TRW_NO_END = "/O.NEW.KMHX.TR.W.1001.000000T0000Z-000000T0000Z/"


class ReplacementChains(unittest.TestCase):
    def test_upgrade_gale_to_storm_stays_hard_paused(self):
        mhx, _akq, _land = _urls()
        upg = _feat("Storm Warning", VTEC_NEW_STORM, ["AMZ154"], ident="oid:upg")
        upg["properties"]["parameters"]["VTEC"] = [VTEC_UPG_GALE, VTEC_NEW_STORM]
        out = _eval({mhx: (200, "application/json", _collection(upg))})
        self.assertTrue(out["hardPause"])
        self.assertEqual(out["pauseReason"], "warning")
        self.assertIn("SR.W", out["knownWarnings"][0]["vtec"])

    def test_extension_replacing_known_warning_keeps_warning_without_hold(self):
        mhx, _akq, _land = _urls()
        old = _gale(ident="oid:gale-v1", ends=(NOW + timedelta(hours=1)).isoformat())
        first = _eval({mhx: (200, "application/json", _collection(old))})
        old_replaced = _gale(ident="oid:gale-v1", replaced_by="https://api.weather.gov/alerts/oid:gale-v2",
                             ends=(NOW + timedelta(hours=1)).isoformat())
        ext = _feat("Gale Warning", VTEC_EXT_GALE, ["AMZ135"], ident="oid:gale-v2",
                    ends=(NOW + timedelta(hours=20)).isoformat())
        out = _eval({mhx: (200, "application/json", _collection(old_replaced, ext))},
                    existing=first, now=NOW + timedelta(minutes=30))
        self.assertTrue(out["hardPause"])
        self.assertEqual([w["id"] for w in out["knownWarnings"]], ["oid:gale-v2"])
        self.assertIsNone(out["settledSince"])

    def test_downgrade_to_sca_starts_hold_at_cancellation(self):
        mhx, _akq, _land = _urls()
        gale = _gale(ident="oid:gale-dg", ends=(NOW + timedelta(hours=10)).isoformat())
        first = _eval({mhx: (200, "application/json", _collection(gale))})
        t = NOW + timedelta(hours=1)
        dg = _feat("Small Craft Advisory", VTEC_NEW_SCA, ["AMZ135"], ident="oid:sca-dg",
                   severity="Moderate")
        dg["properties"]["parameters"]["VTEC"] = [VTEC_CAN_GALE, VTEC_NEW_SCA]
        out = _eval({mhx: (200, "application/json", _collection(dg))}, existing=first, now=t)
        self.assertFalse(out["adsOn"])
        self.assertEqual(out["pauseReason"], "hold")
        self.assertEqual(out["settledSince"], server.iso(t))

    def test_warning_without_official_end_never_clears_at_expires(self):
        # Tropical warnings often have ends=null and expires=next advisory time.
        _mhx, _akq, land = _urls()
        trw = _feat("Tropical Storm Warning", VTEC_NEW_TRW_NO_END, ["NCZ203"], ident="oid:trw",
                    ends=None, expires=(NOW + timedelta(hours=1)).isoformat())
        first = _eval({land: (200, "application/json", _collection(trw))})
        self.assertTrue(first["hardPause"])
        self.assertIsNone(first["knownWarnings"][0]["officialEnds"])
        down = {url: (502, "text/plain", b"down") for url in _urls()}
        out1 = _eval(down, existing=first, now=NOW + timedelta(hours=3))
        self.assertEqual(out1["pauseReason"], "warning")
        t_back = NOW + timedelta(hours=6)
        out2 = _eval({}, existing=out1, now=t_back)
        self.assertEqual(out2["pauseReason"], "hold")
        # Hold from the observed removal, not from the earlier expires time.
        self.assertEqual(out2["settledSince"], server.iso(t_back))


if __name__ == "__main__":
    unittest.main()
