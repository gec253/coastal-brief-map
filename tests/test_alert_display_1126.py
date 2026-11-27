"""Public NWS alert display accuracy (Ed t487u, Nov 26, 2026).

1. Morning Brief "Status now": the 5:15 AM list stays as issued; each issued product is reconciled
   against the current official feed (replacedBy / references / VTEC event), never dropped, and
   shown as "Status unconfirmed — check NWS" when the check cannot be completed.
2. Nags Head shows the NC Wakefield marine zones ANZ633 / ANZ658 / ANZ688, named as NWS names
   them, without Virginia-only zones.
3. Issued-but-not-yet-effective warnings read UPCOMING with the official start time in ET.
4. A Coastal Flood Warning adds a note beside predicted tides; NOAA predicted values are untouched.

Fixture: real api.weather.gov records read together at 11:58 AM ET on Nov 26, 2026, plus the
5:15 AM production briefs (tests/fixtures/nws-alerts-2026-11-26.json).
"""
from __future__ import annotations

import ast
import copy
import json
import subprocess
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import alert_status as A  # noqa: E402
import brief  # noqa: E402
import conditions  # noqa: E402
import sprint_home  # noqa: E402

FIX = json.loads((ROOT / "tests" / "fixtures" / "nws-alerts-2026-11-26.json").read_text())
REGIONS = {r["id"]: r for r in json.loads((ROOT / "data" / "regions.json").read_text())["regions"]}
NOON = datetime(2026, 11, 26, 16, 58, tzinfo=timezone.utc)      # 11:58 AM ET, when the fixture was read
AT_0750 = datetime(2026, 11, 26, 12, 50, tzinfo=timezone.utc)   # 7:50 AM ET
PROD = "f4b091c"


def ts(h, m=0, day=26):
    """ET wall clock on Nov <day>, 2026 (EST = UTC-5) as a UTC datetime."""
    return datetime(2026, 11, day, h + 5 if h + 5 < 24 else h + 5 - 24, m, tzinfo=timezone.utc) if h + 5 < 24 else \
        datetime(2026, 11, day + 1, h + 5 - 24, m, tzinfo=timezone.utc)


def feat(aid, event, ugc, vtec=None, sent="2026-11-26T05:00:00-05:00", onset=None, ends=None, expires=None,
         effective=None, msg="Alert", refs=(), replaced_by=None, area=None, sender="NWS Newport/Morehead City NC"):
    p = {"id": aid, "event": event, "geocode": {"UGC": list(ugc)}, "sent": sent, "status": "Actual",
         "messageType": msg, "onset": onset, "ends": ends, "expires": expires or ends, "effective": effective or sent,
         "parameters": {"VTEC": list(vtec or [])}, "references": [{"identifier": r} for r in refs],
         "areaDesc": area if area is not None else "; ".join(ugc), "senderName": sender, "severity": "Severe"}
    if replaced_by:
        p["replacedBy"] = "https://api.weather.gov/alerts/" + replaced_by
    return {"id": "https://api.weather.gov/alerts/" + aid, "properties": p}


def feed(*features):
    return {"type": "FeatureCollection", "features": list(features)}


def row(event, ids, ugc, onset, ends):
    return {"event": event, "onset": onset, "ends": ends, "localUgc": list(ugc), "ugc": list(ugc),
            "products": [{"id": i, "ugc": list(ugc)} for i in ids], "kind": "warning"}


def fetcher(active=None, lookups=None, history=None, fail=()):
    """fetch(url) over fixtures. `fail` lists URL substrings that return None (failed read)."""
    lookups = lookups or {}

    def fetch(url):
        if any(f in url for f in fail):
            return None
        if "/alerts/active" in url:
            return copy.deepcopy(active)
        if url.startswith("https://api.weather.gov/alerts?"):
            return copy.deepcopy(history) if history is not None else None
        aid = url.rsplit("/", 1)[-1]
        f = lookups.get(aid)
        return copy.deepcopy(f) if f is not None else None
    return fetch


def brief_rows(rid):
    hz = FIX["briefs"][rid]["hazards"]
    return list(hz["current"]) + list(hz["upcoming"])


def live_status(rid, now=NOON, **kw):
    zones = REGIONS[rid]["alertZones"]
    f = fetcher(FIX["active"], FIX["lookups"], FIX["history"], **kw)
    return A.status_now(brief_rows(rid), "https://api.weather.gov/alerts/active?status=actual&zone=" + ",".join(zones),
                        f, now=now, zones=zones, history_url="https://api.weather.gov/alerts?zone=x&start=y")


def by_event(rid, st, event):
    return [rc for r, rc in zip(brief_rows(rid), st["issued"]) if r["event"] == event]


VT_SR = "/O.%s.KMHX.SR.W.0004.000000T0000Z-261126T1500Z/"
VT_GL = "/O.%s.KMHX.GL.W.0033.000000T0000Z-261128T0000Z/"
VT_HU_NEW = "/O.NEW.KMHX.HU.W.1001.000000T0000Z-000000T0000Z/"


# ---------------------------------------------------------------- 1. replacement chains

class ReplacementChains(unittest.TestCase):
    def test_con_same_product_still_active(self):
        f = feat("a1", "Gale Warning", ["AMZ135"], [VT_GL % "CON"], ends="2026-11-27T17:00:00-05:00")
        st = A.status_now([row("Gale Warning", ["a1"], ["AMZ135"], "2026-11-26T00:39:00-05:00", "2026-11-27T17:00:00-05:00")],
                          "https://api.weather.gov/alerts/active?zone=AMZ135", fetcher(feed(f)), now=NOON, zones=["AMZ135"])
        self.assertEqual(st["issued"][0]["state"], "in_effect")
        self.assertEqual(st["issued"][0]["tag"], "In effect")

    def test_ext_six_oh_eight_replacement_seen_at_7_50(self):
        """This morning: the 5:15 AM brief listed the Storm Warning until 6:00 AM; NWS extended it to
        10:00 AM (5:59 / 6:08 AM). At 7:50 AM it must read as in effect until 10:00, not ended."""
        con_608 = next(f for f in FIX["history"]["features"]
                       if f["properties"]["event"] == "Storm Warning" and f["properties"]["sent"].startswith("2026-11-26T06:08")
                       and f["properties"]["parameters"]["VTEC"][0].startswith("/O.CON.") and "AMZ152" in f["properties"]["geocode"]["UGC"])
        con_608 = copy.deepcopy(con_608)
        con_608["properties"].pop("replacedBy", None)   # as the active feed showed it at 7:50 AM
        issued = brief_rows("hatteras")
        storm = next(r for r in issued if r["event"] == "Storm Warning")
        old_id = storm["products"][0]["id"]
        old = copy.deepcopy(FIX["lookups"][old_id])
        old["properties"].pop("replacedBy", None)   # chain as it stood before the 9:41 AM cancel
        st = A.status_now([storm], "https://api.weather.gov/alerts/active?x", fetcher(feed(con_608), {old_id: old}),
                          now=AT_0750, zones=REGIONS["hatteras"]["alertZones"])
        rc = st["issued"][0]
        self.assertEqual(rc["state"], "updated", rc)
        self.assertIn("NWS update 6:08 AM ET", rc["detail"])
        self.assertIn("until 10:00 AM ET", rc["detail"])
        self.assertEqual([r["event"] for r in st["current"]], ["Storm Warning"])

    def test_exa_extends_area_same_event_matches(self):
        old = feat("o1", "Gale Warning", ["AMZ156"], [VT_GL % "NEW"], ends="2026-11-27T19:00:00-05:00")
        new = feat("n1", "Gale Warning", ["AMZ150", "AMZ156"], [VT_GL % "EXA"], sent="2026-11-26T11:38:00-05:00",
                   ends="2026-11-27T19:00:00-05:00")
        st = A.status_now([row("Gale Warning", ["o1"], ["AMZ156"], None, "2026-11-27T19:00:00-05:00")], "u/alerts/active",
                          fetcher(feed(new), {"o1": old}), now=NOON, zones=["AMZ156", "AMZ150"])
        self.assertEqual(st["issued"][0]["state"], "in_effect")
        self.assertIn("NWS update 11:38 AM ET", st["issued"][0]["detail"])

    def test_upg_gale_upgraded_to_storm(self):
        old = feat("g1", "Gale Warning", ["AMZ152"], ["/O.UPG.KMHX.GL.W.0033.000000T0000Z-261127T2200Z/"],
                   ends="2026-11-27T17:00:00-05:00", replaced_by="s1")
        old_v0 = feat("g0", "Gale Warning", ["AMZ152"], [VT_GL % "NEW"], ends="2026-11-27T17:00:00-05:00", replaced_by="g1")
        new = feat("s1", "Storm Warning", ["AMZ152"], ["/O.NEW.KMHX.SR.W.0005.000000T0000Z-261127T2200Z/"],
                   sent="2026-11-26T08:00:00-05:00", ends="2026-11-27T17:00:00-05:00", refs=("g1",))
        st = A.status_now([row("Gale Warning", ["g0"], ["AMZ152"], None, "2026-11-27T17:00:00-05:00")], "u/alerts/active",
                          fetcher(feed(new), {"g0": old_v0, "g1": old, "s1": new}), now=NOON, zones=["AMZ152"])
        rc = st["issued"][0]
        self.assertEqual(rc["state"], "upgraded")
        self.assertIn("Upgraded by NWS 8:00 AM ET: Storm Warning", rc["detail"])

    def test_multi_hop_replaced_by_chain(self):
        v1 = feat("v1", "Gale Warning", ["AMZ135"], [VT_GL % "NEW"], ends="2026-11-26T18:00:00-05:00", replaced_by="v2")
        v2 = feat("v2", "Gale Warning", ["AMZ135"], [VT_GL % "EXT"], ends="2026-11-27T12:00:00-05:00", replaced_by="v3")
        v3 = feat("v3", "Gale Warning", ["AMZ135"], [VT_GL % "EXT"], sent="2026-11-26T10:00:00-05:00",
                  ends="2026-11-27T17:00:00-05:00")
        st = A.status_now([row("Gale Warning", ["v1"], ["AMZ135"], None, "2026-11-26T18:00:00-05:00")], "u/alerts/active",
                          fetcher(feed(v3), {"v1": v1, "v2": v2, "v3": v3}), now=NOON, zones=["AMZ135"])
        self.assertEqual(st["issued"][0]["state"], "updated")
        self.assertIn("until Fri 5:00 PM ET", st["issued"][0]["detail"])

    def test_live_hatteras_gale_continued_by_1138_update(self):
        rc = by_event("hatteras", live_status("hatteras"), "Gale Warning")[0]
        self.assertEqual(rc["state"], "in_effect")
        self.assertIn("NWS update 11:38 AM ET", rc["detail"])


# ---------------------------------------------------------------- 2. cancellations and expirations

class CancelAndExpire(unittest.TestCase):
    def test_live_storm_warning_cancelled_at_9_41_for_hatteras(self):
        rc = by_event("hatteras", live_status("hatteras"), "Storm Warning")[0]
        self.assertEqual(rc["state"], "cancelled", rc)
        self.assertIn("Cancelled by NWS 9:41 AM ET", rc["detail"])

    def test_live_storm_warning_cancelled_at_6_08_for_crystal_coast(self):
        rc = by_event("crystal-coast", live_status("crystal-coast"), "Storm Warning")[0]
        self.assertEqual(rc["state"], "cancelled", rc)
        self.assertIn("6:08 AM ET", rc["detail"])

    def test_live_flood_watch_zones_removed_reads_cancelled_not_silently_gone(self):
        rc = by_event("crystal-coast", live_status("crystal-coast"), "Flood Watch")[0]
        self.assertEqual(rc["state"], "cancelled", rc)
        self.assertIn("11:47 AM ET", rc["detail"])

    def test_live_high_wind_warning_expired_with_exp_message(self):
        rc = by_event("hatteras", live_status("hatteras"), "High Wind Warning")[0]
        self.assertEqual(rc["state"], "ended")
        self.assertIn("Ended (NWS 10:03 AM ET)", rc["detail"])

    def test_cancel_message_in_chain(self):
        v1 = feat("c1", "Storm Warning", ["AMZ154"], [VT_SR % "EXT"], ends="2026-11-26T10:00:00-05:00", replaced_by="c2")
        v2 = feat("c2", "Storm Warning", ["AMZ154"], [VT_SR % "CAN"], msg="Cancel", sent="2026-11-26T09:41:00-05:00",
                  ends="2026-11-26T10:00:00-05:00")
        st = A.status_now([row("Storm Warning", ["c1"], ["AMZ154"], None, "2026-11-26T10:00:00-05:00")], "u/alerts/active",
                          fetcher(feed(), {"c1": v1, "c2": v2}), now=ts(9, 50), zones=["AMZ154"])
        self.assertEqual(st["issued"][0]["state"], "cancelled")
        self.assertEqual(st["current"], [])

    def test_cancel_record_in_active_feed_is_not_a_hazard(self):
        c = feat("x2", "Gale Warning", ["AMZ135"], [VT_GL % "CAN"], msg="Cancel", ends="2026-11-27T17:00:00-05:00")
        fd = A.read_feed(feed(c), ["AMZ135"])
        self.assertEqual(A.current_records(fd, NOON), [])

    def test_expired_without_replacement_after_complete_check(self):
        v1 = feat("e1", "Small Craft Advisory", ["AMZ135"], ["/O.CON.KMHX.SC.Y.0100.000000T0000Z-261126T1500Z/"],
                  ends="2026-11-26T10:00:00-05:00")
        st = A.status_now([row("Small Craft Advisory", ["e1"], ["AMZ135"], None, "2026-11-26T10:00:00-05:00")], "u/alerts/active",
                          fetcher(feed(), {"e1": v1}), now=NOON, zones=["AMZ135"])
        self.assertEqual(st["issued"][0]["state"], "ended")
        self.assertIn("no current NWS replacement found", st["issued"][0]["detail"])

    def test_expired_with_replacement_is_not_ended(self):
        v1 = feat("e1", "Gale Warning", ["AMZ135"], [VT_GL % "CON"], ends="2026-11-26T10:00:00-05:00")
        v2 = feat("e2", "Gale Warning", ["AMZ135"], [VT_GL % "EXT"], sent="2026-11-26T09:30:00-05:00",
                  ends="2026-11-27T17:00:00-05:00")   # new id, no link back, same VTEC event
        st = A.status_now([row("Gale Warning", ["e1"], ["AMZ135"], None, "2026-11-26T10:00:00-05:00")], "u/alerts/active",
                          fetcher(feed(v2), {"e1": v1}), now=NOON, zones=["AMZ135"])
        self.assertEqual(st["issued"][0]["state"], "updated")


# ---------------------------------------------------------------- 3. failed or incomplete checks

class FailedChecks(unittest.TestCase):
    ISSUED = row("Storm Warning", ["f1"], ["AMZ152"], None, "2026-11-26T06:00:00-05:00")
    OLD = feat("f1", "Storm Warning", ["AMZ152"], [VT_SR % "EXT"], ends="2026-11-26T06:00:00-05:00")

    def test_failed_record_lookup_is_unconfirmed_not_ended(self):
        st = A.status_now([self.ISSUED], "u/alerts/active", fetcher(feed(), {}), now=NOON, zones=["AMZ152"])
        self.assertEqual(st["issued"][0]["state"], "unconfirmed")
        self.assertIn("Status unconfirmed — check NWS", st["issued"][0]["detail"])

    def test_lookup_raises_is_unconfirmed(self):
        def boom(url):
            if "/alerts/active" in url:
                return feed()
            raise TimeoutError("slow")
        st = A.status_now([self.ISSUED], "u/alerts/active", boom, now=NOON, zones=["AMZ152"])
        self.assertEqual(st["issued"][0]["state"], "unconfirmed")

    def test_active_feed_unavailable_everything_unconfirmed(self):
        st = live_status("hatteras", fail=("/alerts/active",))
        self.assertFalse(st["ok"])
        self.assertEqual({rc["state"] for rc in st["issued"]}, {"unconfirmed"})
        self.assertEqual(len(st["issued"]), len(brief_rows("hatteras")))

    def test_malformed_record_in_feed_blocks_ended_claims(self):
        bad = {"properties": {"id": "zz", "event": "Gale Warning", "geocode": {"UGC": "AMZ152"}}}
        st = A.status_now([self.ISSUED], "u/alerts/active", fetcher(feed(bad), {"f1": self.OLD}), now=NOON, zones=["AMZ152"])
        self.assertFalse(st["trusted"])
        self.assertEqual(st["issued"][0]["state"], "unconfirmed")

    def test_chain_loop_and_overlong_chain_are_incomplete(self):
        a = feat("l1", "Storm Warning", ["AMZ152"], [VT_SR % "EXT"], ends="2026-11-26T06:00:00-05:00", replaced_by="l2")
        b = feat("l2", "Storm Warning", ["AMZ152"], [VT_SR % "EXT"], ends="2026-11-26T06:00:00-05:00", replaced_by="l1")
        res = A.lookup_chains(["l1"], fetcher(None, {"l1": a, "l2": b}))
        self.assertFalse(res["l1"]["ok"])
        many = {"m%d" % i: feat("m%d" % i, "Storm Warning", ["AMZ152"], [VT_SR % "EXT"], replaced_by="m%d" % (i + 1))
                for i in range(10)}
        self.assertFalse(A.lookup_chains(["m0"], fetcher(None, many))["m0"]["ok"])

    def test_lookup_budget_exceeded_is_incomplete(self):
        import time

        def slow(url):
            time.sleep(0.5)
            return self.OLD
        self.assertFalse(A.lookup_chains(["f1"], slow, budget_s=0.05)["f1"]["ok"])

    def test_wrong_id_in_lookup_body_is_untrusted(self):
        other = feat("other", "Storm Warning", ["AMZ152"], [VT_SR % "EXT"])
        self.assertFalse(A.lookup_chains(["f1"], fetcher(None, {"f1": other}))["f1"]["ok"])

    def test_not_ended_and_missing_from_feed_is_unconfirmed(self):
        old = feat("f2", "Gale Warning", ["AMZ152"], [VT_GL % "CON"], ends="2026-11-27T17:00:00-05:00")
        st = A.status_now([row("Gale Warning", ["f2"], ["AMZ152"], None, "2026-11-27T17:00:00-05:00")], "u/alerts/active",
                          fetcher(feed(), {"f2": old}), now=NOON, zones=["AMZ152"])
        self.assertEqual(st["issued"][0]["state"], "unconfirmed")

    def test_page_keeps_every_issued_row_when_unconfirmed(self):
        b = FIX["briefs"]["hatteras"]
        st = live_status("hatteras", fail=("/alerts/active",))
        html = brief.page(b, view_now=NOON, status_now=st)
        self.assertEqual(html.count('class="mb-hz-row '), len(brief_rows("hatteras")))
        self.assertEqual(html.count(">UNCONFIRMED</span>"), len(brief_rows("hatteras")))
        self.assertIn("Could not reach the National Weather Service", html)
        self.assertNotIn(">ENDED</span>", html)

    def test_status_now_for_never_raises(self):
        b = FIX["briefs"]["hatteras"]
        with patch("alert_status.status_now", side_effect=RuntimeError("bug")):
            st = brief.status_now_for(b, lambda u: None, now=NOON)
        self.assertFalse(st["ok"])
        self.assertEqual({x["state"] for x in st["issued"]}, {"unconfirmed"})


# ---------------------------------------------------------------- 4. upcoming vs in effect

class UpcomingLabels(unittest.TestCase):
    def _wilm(self):
        return next(f for f in FIX["active"]["features"]
                    if f["properties"]["event"] == "Gale Warning" and "AMZ250" in f["properties"]["geocode"]["UGC"])

    def test_wilmington_gale_upcoming_with_official_start(self):
        r = A.record(self._wilm())
        self.assertEqual(A.start_of(r), "2026-11-26T16:00:00-05:00")
        lab = A.label_for({"start": A.start_of(r), "ends": r["ends"]}, NOON)
        self.assertEqual(lab["tag"], "Upcoming")
        self.assertEqual(lab["when"], "starts 4:00 PM ET · until Fri 1:00 PM ET")

    def test_relabels_in_effect_after_start(self):
        r = A.record(self._wilm())
        self.assertEqual(A.label_for({"start": A.start_of(r), "ends": r["ends"]}, ts(15, 59))["phase"], "upcoming")
        lab = A.label_for({"start": A.start_of(r), "ends": r["ends"]}, ts(16, 0))
        self.assertEqual((lab["phase"], lab["tag"], lab["when"]), ("in_effect", "In effect", "until Fri 1:00 PM ET"))

    def test_effective_used_when_onset_missing(self):
        f = feat("u1", "Gale Warning", ["AMZ250"], onset=None, effective="2026-11-26T16:00:00-05:00",
                 ends="2026-11-27T13:00:00-05:00")
        f["properties"]["onset"] = None
        self.assertEqual(A.phase(A.record(f), NOON), "upcoming")

    def test_no_end_time_never_ends_an_active_record(self):
        f = feat("t1", "Hurricane Warning", ["AMZ150"], [VT_HU_NEW], ends=None, expires="2026-11-26T10:00:00-05:00")
        r = A.record(f)
        self.assertEqual(A.phase(r, NOON), "in_effect")
        self.assertEqual(A.label_for({"start": A.start_of(r), "ends": None}, NOON)["when"], "no end time given by NWS")

    def _home_alerts(self, rid, now):
        zones = REGIONS[rid]["alertZones"]
        fd = {"type": "FeatureCollection", "features": [f for f in FIX["active"]["features"]
                                                       if set(f["properties"]["geocode"]["UGC"]) & set(zones)]}
        with patch("conditions.nws_json", return_value=copy.deepcopy(fd)):
            block = conditions.alerts_block(zones)
            return block, sprint_home._salt_alerts(block, now)

    def test_home_strip_wilmington_before_and_after_4pm(self):
        block, a = self._home_alerts("wilmington", NOON)
        gale = next(i for i in a["items"] if i["event"] == "Gale Warning")
        self.assertEqual((gale["tag"], gale["meta"]), ("Upcoming", "starts 4:00 PM ET · until Fri 1:00 PM ET"))
        sca = next(i for i in a["items"] if i["event"] == "Small Craft Advisory")
        self.assertEqual(sca["tag"], "In effect")
        html = sprint_home.alerts_html(a, pennants=True, raw=block)
        self.assertIn('p-upcoming"', html)
        self.assertIn('<span class="al-tag">Upcoming</span> <span class="al-meta">starts 4:00 PM ET · until Fri 1:00 PM ET</span>', html)
        _, a2 = self._home_alerts("wilmington", ts(16, 5))
        gale2 = next(i for i in a2["items"] if i["event"] == "Gale Warning")
        self.assertEqual((gale2["tag"], gale2["meta"]), ("In effect", "until Fri 1:00 PM ET"))

    def test_home_strip_keeps_every_row_and_event_name(self):
        block, a = self._home_alerts("hatteras", NOON)
        self.assertEqual([i["event"] for i in a["items"]], [i["event"] for i in block["items"]])
        self.assertEqual(len(a["items"]), len(sprint_home._alerts(block)["items"]))

    def test_brief_status_now_lists_upcoming(self):
        zones = REGIONS["wilmington"]["alertZones"]
        st = A.status_now([], "u/alerts/active", fetcher(FIX["active"]), now=NOON, zones=zones)
        g = next(r for r in st["current"] if r["event"] == "Gale Warning")
        self.assertEqual(g["label"]["tag"], "Upcoming")


# ---------------------------------------------------------------- 5. dedupe

class Dedupe(unittest.TestCase):
    def test_same_vtec_event_across_segments_is_one_row(self):
        a = feat("d1", "Gale Warning", ["AMZ250"], ["/O.CON.KILM.GL.W.0016.261126T2100Z-261127T1800Z/"],
                 onset="2026-11-26T16:00:00-05:00", ends="2026-11-27T13:00:00-05:00")
        b = feat("d2", "Gale Warning", ["AMZ252"], ["/O.CON.KILM.GL.W.0016.261126T2100Z-261127T1800Z/"],
                 onset="2026-11-26T16:00:00-05:00", ends="2026-11-27T13:00:00-05:00")
        rows = A.dedupe(A.current_records(A.read_feed(feed(a, b, copy.deepcopy(a))), NOON), ["AMZ250", "AMZ252"])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["ugc"], ["AMZ250", "AMZ252"])

    def test_same_event_different_end_stays_two_rows(self):
        a = feat("d1", "Gale Warning", ["AMZ250"], ["/O.CON.KILM.GL.W.0016.261126T2100Z-261127T1800Z/"],
                 onset="2026-11-26T16:00:00-05:00", ends="2026-11-27T13:00:00-05:00")
        b = feat("d3", "Gale Warning", ["AMZ280"], ["/O.CON.KILM.GL.W.0016.000000T0000Z-261128T0600Z/"],
                 ends="2026-11-28T01:00:00-05:00")
        self.assertEqual(len(A.dedupe(A.current_records(A.read_feed(feed(a, b)), NOON))), 2)

    def test_different_etn_same_times_not_merged(self):
        a = feat("d1", "Storm Warning", ["AMZ150"], ["/O.CON.KMHX.SR.W.0004.000000T0000Z-261126T1500Z/"], ends="2026-11-26T16:00:00-05:00")
        b = feat("d2", "Storm Warning", ["ANZ658"], ["/O.CON.KAKQ.SR.W.0005.000000T0000Z-261126T2100Z/"], ends="2026-11-26T16:00:00-05:00")
        self.assertEqual(len(A.dedupe(A.current_records(A.read_feed(feed(a, b)), NOON))), 2)

    def test_replaced_record_skipped_only_when_replacement_present(self):
        old = feat("r1", "Gale Warning", ["AMZ135"], [VT_GL % "CON"], ends="2026-11-27T17:00:00-05:00", replaced_by="r2")
        new = feat("r2", "Gale Warning", ["AMZ135"], [VT_GL % "CON"], ends="2026-11-27T17:00:00-05:00")
        self.assertEqual([r["id"] for r in A.current_records(A.read_feed(feed(old, new)), NOON)], ["r2"])
        self.assertEqual([r["id"] for r in A.current_records(A.read_feed(feed(old)), NOON)], ["r1"])

    def test_live_brief_status_now_has_no_duplicate_products(self):
        st = live_status("hatteras")
        keys = [(r["event"], tuple(r["keys"]), r["start"], r["ends"]) for r in st["current"]]
        self.assertEqual(len(keys), len(set(keys)))


# ---------------------------------------------------------------- 6. geography (Wakefield)

class WakefieldCoverage(unittest.TestCase):
    def test_nags_head_alert_zones_include_nc_wakefield_waters(self):
        z = REGIONS["nags-head"]["alertZones"]
        for code in ("ANZ633", "ANZ658", "ANZ688", "AMZ150", "NCZ203", "AMZ231"):
            self.assertIn(code, z)
        for va in ("ANZ654", "ANZ656", "ANZ684", "ANZ686", "ANZ634", "ANZ632"):
            self.assertNotIn(va, z)

    def test_other_regions_zones_unchanged(self):
        self.assertEqual(REGIONS["hatteras"]["alertZones"], ["AMZ154", "AMZ152", "AMZ135", "NCZ205"])
        self.assertEqual(REGIONS["crystal-coast"]["alertZones"], ["AMZ158", "AMZ156", "NCZ195", "NCZ196"])
        self.assertEqual(REGIONS["wilmington"]["alertZones"], ["AMZ250", "NCZ108"])

    def test_wakefield_storm_names_only_nc_waters(self):
        zones = REGIONS["nags-head"]["alertZones"]
        st = A.status_now([], "u/alerts/active", fetcher(FIX["active"]), now=NOON, zones=zones)
        storms = [r for r in st["current"] if r["event"] == "Storm Warning"]
        local = sorted(n for r in storms for n in r["local"])
        self.assertEqual(local, ["Coastal waters from NC VA border to Currituck Beach Light NC out 20 NM", "Currituck Sound",
                                 "Waters from NC VA border to Currituck Beach Light NC from 20 to 60 NM"])
        self.assertFalse(any("Cape Charles" in n or "Parramore" in n for n in local))

    def test_virginia_only_warning_not_shown(self):
        va = feat("va1", "Gale Warning", ["ANZ656"], ["/O.NEW.KAKQ.GL.W.0050.000000T0000Z-261127T0000Z/"],
                  ends="2026-11-27T19:00:00-05:00", sender="NWS Wakefield VA")
        self.assertEqual(A.read_feed(feed(va), REGIONS["nags-head"]["alertZones"])["records"], [])

    def test_home_strip_names_in_region_waters_for_repeated_event(self):
        zones = REGIONS["nags-head"]["alertZones"]
        fd = {"type": "FeatureCollection", "features": [f for f in FIX["active"]["features"]
                                                       if set(f["properties"]["geocode"]["UGC"]) & set(zones)]}
        with patch("conditions.nws_json", return_value=copy.deepcopy(fd)):
            block = conditions.alerts_block(zones)
            a = sprint_home._salt_alerts(block, NOON)
        storms = [i for i in a["items"] if i["event"] == "Storm Warning"]
        self.assertEqual(len(storms), 2)
        self.assertIn("Currituck Sound", [s["area"] for s in storms])
        joined = " ".join(s["area"] for s in storms)
        self.assertIn("NC VA border to Currituck Beach Light", joined)
        self.assertNotIn("Cape Charles", joined)
        self.assertNotIn("Parramore", joined)
        single = [i for i in a["items"] if i["event"] == "Coastal Flood Warning"]
        self.assertEqual(single[0]["area"], "")


# ---------------------------------------------------------------- 7. coastal flood note + tides

TIDES = {"status": "ok", "kind": "predicted", "datum": "MLLW", "station": {"id": "8652226", "name": "Jennette's Pier (ocean)"},
         "events": [{"t": 4102444800000, "type": "L", "v": -0.3}, {"t": 4102466400000, "type": "H", "v": 3.4}],
         "curve": []}


class CoastalFloodNote(unittest.TestCase):
    def _block(self, *items):
        return {"status": "ok", "zones": ["NCZ203"], "items": list(items)}

    def test_note_on_with_active_warning(self):
        cf = sprint_home._coastal_flood(self._block({"event": "Coastal Flood Warning", "onset": "2026-11-26T05:31:00-05:00",
                                                     "ends": "2026-11-27T15:00:00-05:00"}), NOON)
        self.assertEqual(cf["phase"], "in_effect")

    def test_note_upcoming_and_off_cases(self):
        up = sprint_home._coastal_flood(self._block({"event": "Coastal Flood Warning", "onset": "2026-11-26T18:00:00-05:00",
                                                     "ends": "2026-11-27T15:00:00-05:00"}), NOON)
        self.assertEqual(up["phase"], "upcoming")
        self.assertIsNone(sprint_home._coastal_flood(self._block({"event": "Coastal Flood Advisory", "onset": None,
                                                                  "ends": "2026-11-27T15:00:00-05:00"}), NOON))
        self.assertIsNone(sprint_home._coastal_flood(self._block({"event": "Coastal Flood Warning", "onset": None,
                                                                  "ends": "2026-11-26T06:00:00-05:00"}), NOON))
        self.assertIsNone(sprint_home._coastal_flood({"status": "unavailable", "items": []}, NOON))

    def _model(self, alert_items):
        payload = {"ok": True, "region": {"id": "nags-head", "name": "Nags Head"}, "readings": {},
                   "tides": copy.deepcopy(TIDES), "alerts": self._block(*alert_items), "generatedAt": NOON.isoformat()}
        with patch("conditions.nws_json", return_value=None):
            return sprint_home.salt_model(payload)

    def test_tide_tile_values_unchanged_and_note_rendered(self):
        cfw = {"event": "Coastal Flood Warning", "onset": "2026-11-26T05:31:00-05:00", "ends": "2099-11-27T15:00:00-05:00"}
        with_cf = next(t for t in self._model([cfw])["tiles"] if t["id"] == "tide")
        without = next(t for t in self._model([])["tiles"] if t["id"] == "tide")
        self.assertIn("flood", with_cf)
        self.assertNotIn("flood", without)
        self.assertEqual({k: v for k, v in with_cf.items() if k != "flood"}, without)
        h1, h0 = sprint_home.tile_html(with_cf), sprint_home.tile_html(without)
        self.assertIn('<p class="t-flood" role="note">Coastal Flood Warning in effect. Predicted tides do not include '
                      'storm surge or other weather-driven water levels.</p>', h1)
        self.assertEqual(h1.replace(h1[h1.index('<p class="t-flood"'):h1.index("</p>", h1.index('<p class="t-flood"')) + 4], ""), h0)
        self.assertEqual(TIDES["events"][0]["v"], -0.3)

    def test_brief_tide_note_on_and_off(self):
        b = FIX["briefs"]["hatteras"]
        on = brief.page(b, view_now=NOON, status_now=live_status("hatteras"))
        self.assertIn('class="mb-tide-note" role="note"><b>Coastal Flood Warning in effect.</b> Predicted tides do not include', on)
        st = live_status("hatteras")
        st["coastalFlood"] = None
        off = brief.page(b, view_now=NOON, status_now=st)
        self.assertNotIn("mb-tide-note", off)
        # The tide glance itself is identical with or without the note.
        g = lambda h: h[h.index('class="mb-glance'):h.index("</section>", h.index('class="mb-glance'))]
        self.assertEqual(g(on), g(off))


# ---------------------------------------------------------------- 8. brief page

class BriefPage(unittest.TestCase):
    def test_issued_list_kept_and_status_now_separate(self):
        b = FIX["briefs"]["hatteras"]
        before = json.dumps(b, sort_keys=True)
        html = brief.page(b, view_now=NOON, status_now=live_status("hatteras"))
        self.assertEqual(json.dumps(b, sort_keys=True), before)   # snapshot not edited
        self.assertIn("List as issued 5:15 AM ET · status checked 11:58 AM ET", html)
        self.assertIn('<section class="mb-now" aria-labelledby="mb-now-h">', html)
        self.assertLess(html.index('class="mb-adv is-active mb-hz"'), html.index('class="mb-now"'))
        self.assertIn("this brief was issued 5:15 AM ET and does not change", html)
        self.assertIn("Thu 12:39 AM", html)          # issued times still shown as published
        self.assertIn(">CANCELLED</span>", html)
        self.assertIn("Status now: </span>Cancelled by NWS 9:41 AM ET.", html)
        self.assertEqual(html.count('class="mb-hz-row '), 6)

    def test_status_now_rows_warnings_first_with_labels(self):
        html = brief.page(FIX["briefs"]["hatteras"], view_now=NOON, status_now=live_status("hatteras"))
        sec = html[html.index('class="mb-now"'):]
        sec = sec[:sec.index("</section>")]
        self.assertIn('<span class="mb-now-tag">IN EFFECT</span>', sec)
        self.assertLess(sec.index("Gale Warning"), sec.index("Flood Watch"))
        self.assertLess(sec.index("Flood Watch"), sec.index("High Surf Advisory"))
        self.assertIn("NWS update 11:38 AM ET", sec)

    def test_without_status_now_page_is_unchanged_legacy_render(self):
        html = brief.page(FIX["briefs"]["hatteras"], view_now=NOON)
        self.assertNotIn("mb-now", html)
        self.assertNotIn("mb-tide-note", html)
        self.assertIn("· status now</p>", html)


# ---------------------------------------------------------------- 9. server fetch + guards

class ServerFetchAndGuards(unittest.TestCase):
    def test_status_fetch_uses_fresh_cache_and_never_stale(self):
        import server
        with patch.object(server, "cache_get", return_value=(200, "application/json", b'{"features": []}')), \
                patch.object(server, "fetch_url") as f:
            self.assertEqual(server._alert_status_fetch("https://api.weather.gov/alerts/active?x"), {"features": []})
            f.assert_not_called()
        with patch.object(server, "cache_get", return_value=None), \
                patch.object(server, "cache_get_any", return_value=(200, "x", b'{"features": ["stale"]}')) as stale, \
                patch.object(server, "fetch_url", return_value=(502, "text/plain", b"")):
            self.assertIsNone(server._alert_status_fetch("https://api.weather.gov/alerts/active?x"))
            stale.assert_not_called()
        with patch.object(server, "cache_get", return_value=None), \
                patch.object(server, "cache_put_ttl") as put, \
                patch.object(server, "fetch_url", return_value=(200, "application/json", b'{"features": [1]}')) as f:
            self.assertEqual(server._alert_status_fetch("u"), {"features": [1]})
            self.assertEqual(f.call_args.kwargs, {"tries": 1, "timeout": 8})
            put.assert_called_once()

    def test_public_brief_route_renders_status_now(self):
        import io
        import server
        b = FIX["briefs"]["hatteras"]
        f = fetcher(FIX["active"], FIX["lookups"], FIX["history"])
        h = server.Handler.__new__(server.Handler)
        h.path = "/brief?region=hatteras"
        h.headers = {}
        sent = {}
        h._preview_ok = lambda: False
        h._send_private = lambda path, ctype, data, status=200, robots=None: sent.update(body=data, status=status)
        with patch.object(brief, "get", return_value=(200, copy.deepcopy(b))), \
                patch.object(server, "_alert_status_fetch", side_effect=f), \
                patch.object(brief, "flag_on", return_value=True):
            server.Handler.do_GET(h)
        body = sent["body"].decode() if isinstance(sent["body"], bytes) else sent["body"]
        self.assertEqual(sent.get("status", 200), 200)
        self.assertIn('id="mb-now-h">Status now</h2>', body)
        self.assertIn(">CANCELLED</span>", body)

    def _func_src(self, src, name):
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == name:
                return ast.get_source_segment(src, node)
        return None

    def test_ad_safeguard_code_untouched(self):
        base = subprocess.check_output(["git", "show", "%s:server.py" % PROD], cwd=ROOT).decode()
        cur = (ROOT / "server.py").read_text()
        names = [n.name for n in ast.walk(ast.parse(base)) if isinstance(n, ast.FunctionDef)
                 and ("ads" in n.name.lower() or "warning" in n.name.lower())]
        self.assertIn("evaluate_ads", names)
        for n in names:
            self.assertEqual(self._func_src(base, n), self._func_src(cur, n), n)
        for rel in ("tests/test_ads_marine_1126.py", "data/ads.json"):
            out = subprocess.run(["git", "diff", "--name-only", PROD, "--", rel], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(out.stdout.strip(), "", rel)

    def test_protected_public_files_unchanged(self):
        # Ed t489u: the three files changed for the Full Dashboard (t488u) stay protected, pinned to d5ea520.
        # Ed t497u: wind-lab.js pinned to the reviewed Phase A public engine 8f17de6
        # (SHA-256 aca358bd4ee33fdef19da2fd6aa907f690c2b080803b11d6cb86dac99c371558).
        pins = {"conditions.py": "d5ea520", "homepage_boot.py": "d5ea520", "dashboard.js": "d5ea520",
                "wind-lab.js": "8f17de6",
                "wind.html": "02fbe50b28499188ad7948badb99671d81d43c16",
                "wind-viewer.js": "02fbe50b28499188ad7948badb99671d81d43c16"}
        for rel in ("conditions.py", "homepage_boot.py", "dashboard.js", "app.js", "styles.css", "index.html",
                    "freshwater.py", "radar.html", "radar-viewer.js", "wind-lab.js", "wind.html", "wind-viewer.js",
                    "brief_preview.py", "brief_strings.py", "lake.js", "fresh-home.js"):
            out = subprocess.run(["git", "diff", "--name-only", pins.get(rel, PROD), "--", rel], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(out.stdout.strip(), "", rel)


if __name__ == "__main__":
    unittest.main()


# ---------------------------------------------------------------- t488u: Full Dashboard (/dashboard)

class _FixedDT(datetime):
    NOW = NOON

    @classmethod
    def now(cls, tz=None):
        return cls.NOW.astimezone(tz) if tz else cls.NOW.replace(tzinfo=None)


def _block_for(rid):
    z = REGIONS[rid]["alertZones"]
    feats = [f for f in FIX["active"]["features"] if set(f["properties"]["geocode"]["UGC"]) & set(z)]
    with patch.object(conditions, "nws_json", return_value={"features": copy.deepcopy(feats)}):
        return conditions.alerts_block(z, bool(REGIONS[rid].get("alertAreasInRegion"))), feats


def _render_at(block, now):
    import homepage_boot
    _FixedDT.NOW = now
    with patch.object(homepage_boot, "datetime", _FixedDT):
        return homepage_boot.render_alerts_html(block)


def _js_funcs(*names):
    src = (ROOT / "dashboard.js").read_text()
    out = []
    for n in names:
        i = src.index("  function %s(" % n)
        j = src.index("\n  }\n", i) + 4
        out.append(src[i:j])
    return "\n".join(out)


def _node(js):
    return subprocess.run(["node", "-e", js], capture_output=True, text=True, timeout=30)


VA_NAMES = ("Parramore Island", "Cape Charles Light", "Virginia-North Carolina border", "Chesapeake")


class DashboardAlertsBlock(unittest.TestCase):
    def test_nags_head_names_only_its_nc_waters(self):
        b, _ = _block_for("nags-head")
        areas = " | ".join(it["areas"] for it in b["items"])
        for va in VA_NAMES:
            self.assertNotIn(va, areas)
        self.assertIn("Currituck Sound", areas)
        self.assertIn("Coastal waters from NC VA border to Currituck Beach Light NC out 20 NM", areas)
        self.assertIn("Waters from NC VA border to Currituck Beach Light NC from 20 to 60 NM", areas)

    def test_official_fields_preserved(self):
        b, feats = _block_for("nags-head")
        storm = [it for it in b["items"] if "NC VA border" in it["areas"]][0]
        p = [f["properties"] for f in feats if "ANZ658" in f["properties"]["geocode"]["UGC"]][0]
        self.assertEqual(set(storm), {"event", "headline", "severity", "areas", "onset", "ends", "sender"})
        for k_it, k_p in (("event", "event"), ("severity", "severity"), ("sender", "senderName"),
                          ("onset", "onset"), ("headline", "headline")):
            self.assertEqual(storm[k_it], p.get(k_p))
        self.assertEqual(storm["ends"], p.get("ends") or p.get("expires"))

    def test_other_regions_keep_full_area_desc(self):
        for rid in ("hatteras", "crystal-coast", "wilmington", "corolla-duck"):
            b, feats = _block_for(rid)
            descs = {f["properties"]["areaDesc"] for f in feats}
            with patch.object(conditions, "nws_json", return_value={"features": copy.deepcopy(feats)}):
                self.assertEqual(b, conditions.alerts_block(REGIONS[rid]["alertZones"]), rid)
            for it in b["items"]:
                self.assertTrue(all(part.strip() in "; ".join(descs) for part in it["areas"].split(";")), rid)

    def test_misaligned_area_desc_is_not_trimmed(self):
        f = feat("m1", "Storm Warning", ["ANZ656", "ANZ658"], area="Some official text without a split")
        with patch.object(conditions, "nws_json", return_value=feed(f)):
            b = conditions.alerts_block(["ANZ658"], True)
        self.assertEqual(b["items"][0]["areas"], "Some official text without a split")

    def test_merge_unions_local_names(self):
        a = feat("x1", "Storm Warning", ["ANZ656", "ANZ658"], area="VA waters; NC waters near", onset="2026-11-26T00:51:00-05:00", ends="2026-11-27T13:00:00-05:00")
        c = feat("x2", "Storm Warning", ["ANZ686", "ANZ688"], area="VA far; NC waters far", onset="2026-11-26T00:51:00-05:00", ends="2026-11-27T13:00:00-05:00")
        with patch.object(conditions, "nws_json", return_value=feed(a, c)):
            b = conditions.alerts_block(["ANZ658", "ANZ688"], True)
        self.assertEqual([it["areas"] for it in b["items"]], ["NC waters near; NC waters far"])

    def test_assemble_passes_region_flag(self):
        src = (ROOT / "conditions.py").read_text()
        self.assertIn('bool(region.get("alertAreasInRegion"))', src)
        self.assertTrue(REGIONS["nags-head"].get("alertAreasInRegion"))
        self.assertFalse(any(r.get("alertAreasInRegion") for k, r in REGIONS.items() if k != "nags-head"))


class DashboardFirstPaint(unittest.TestCase):
    def test_wilmington_gale_upcoming_before_4pm_with_official_start(self):
        b, _ = _block_for("wilmington")
        html, cls = _render_at(b, NOON)
        self.assertEqual(cls, "is-active")
        gale = [p for p in html.split('<div class="al-item"') if "Gale Warning" in p][0]
        self.assertIn('<span class="al-meta">UPCOMING — starts 4:00 PM ET, until Fri 1:00 PM ET · ', gale)

    def test_wilmington_gale_in_effect_after_4pm(self):
        b, _ = _block_for("wilmington")
        html, _ = _render_at(b, ts(16, 1))
        gale = [p for p in html.split('<div class="al-item"') if "Gale Warning" in p][0]
        self.assertIn('<span class="al-meta">IN EFFECT — until Fri 1:00 PM ET · ', gale)
        self.assertNotIn("starts", gale)

    def test_nags_head_first_paint_has_no_virginia_waters(self):
        b, _ = _block_for("nags-head")
        html, _ = _render_at(b, NOON)
        for va in VA_NAMES:
            self.assertNotIn(va, html)
        self.assertIn("Currituck Sound", html)
        self.assertIn("NWS details", html)

    def test_dashboard_zone_fold_keeps_label_and_times_visible(self):
        import server
        b, _ = _block_for("wilmington")
        html, _ = _render_at(b, NOON)
        folded = server._folio_fold_alerts(html.encode()).decode()
        gale = [p for p in folded.split('<div class="al-item">') if "Gale Warning" in p][0]
        self.assertIn('<span class="al-meta">UPCOMING — starts 4:00 PM ET, until Fri 1:00 PM ET</span><details class="al-zones">', gale)

    def test_unknown_and_clear_states_unchanged(self):
        import homepage_boot
        self.assertEqual(homepage_boot.render_alerts_html(None)[1], "is-unknown")
        self.assertEqual(homepage_boot.render_alerts_html({"status": "ok", "items": [], "zones": ["AMZ158"]})[1], "is-clear")


class DashboardJs(unittest.TestCase):
    def _run(self, body):
        js = "const esc=s=>String(s);\n" + _js_funcs("isUpcoming", "coastalFlood") + "\n" + body
        r = _node(js)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip()

    def test_upcoming_relabels_when_start_passes(self):
        out = self._run("""
const it={onset:"2026-11-26T16:00:00-05:00",ends:"2026-11-27T13:00:00-05:00"};
Date.now=()=>Date.parse("2026-11-26T15:59:00-05:00"); const a=isUpcoming(it);
Date.now=()=>Date.parse("2026-11-26T16:00:00-05:00"); const b=isUpcoming(it);
console.log(a+","+b+","+isUpcoming({onset:null}));""")
        self.assertEqual(out, "true,false,false")

    def test_coastal_flood_rule_matches_homepage(self):
        out = self._run("""
Date.now=()=>Date.parse("2026-11-26T12:00:00-05:00");
const cf=(s,e,st)=>coastalFlood({status:st||"ok",items:[{event:"Coastal Flood Warning",onset:s,ends:e}]});
console.log(JSON.stringify([cf("2026-11-26T05:31:00-05:00","2026-11-26T14:00:00-05:00"),
 cf("2026-11-26T18:00:00-05:00","2026-11-27T02:00:00-05:00"),
 cf("2026-11-26T05:00:00-05:00","2026-11-26T11:00:00-05:00"),
 cf("2026-11-26T05:31:00-05:00",null),
 cf("2026-11-26T05:31:00-05:00","2026-11-26T14:00:00-05:00","error"),
 coastalFlood({status:"ok",items:[{event:"Coastal Flood Advisory",onset:"2026-11-26T05:00:00-05:00"}]})]));""")
        self.assertEqual(json.loads(out), ["Coastal Flood Warning in effect.", "Coastal Flood Warning issued (upcoming).",
                                           None, "Coastal Flood Warning in effect.", None, None])
        for ph in ("in_effect", "upcoming"):
            got = A.coastal_flood_active([{"event": "Coastal Flood Warning",
                                           "start": "2026-11-26T05:31:00-05:00" if ph == "in_effect" else "2026-11-26T18:00:00-05:00",
                                           "ends": "2026-11-27T02:00:00-05:00"}], ts(12))
            self.assertEqual(got["phase"], ph)

    def test_tide_note_wording_matches_homepage_and_values_untouched(self):
        src = (ROOT / "dashboard.js").read_text()
        i = src.index("  function renderTide(")
        body = src[i:src.index("\n  }\n", i)]
        self.assertIn(A.FLOOD_TIDE_NOTE, body)
        self.assertIn('role="note"', body)
        self.assertIn("renderTide(d.tides, d.alerts)", src)
        base = subprocess.run(["git", "show", PROD + ":dashboard.js"], cwd=ROOT, capture_output=True, text=True).stdout
        bi = base.index("  function renderTide(")
        old = base[bi:base.index("\n  }\n", bi)]
        # Only the signature and the one note line differ; every tide value expression is as in production.
        added = [ln for ln in body.splitlines() if ln not in old.splitlines()]
        removed = [ln for ln in old.splitlines() if ln not in body.splitlines()]
        self.assertEqual(len(added), 2, added)
        self.assertEqual(removed, ["  function renderTide(t) {"])

    def test_render_alerts_labels_and_relabel_hook(self):
        src = (ROOT / "dashboard.js").read_text()
        self.assertIn('(up ? "UPCOMING — starts " + esc(etTime(it.onset)) + (it.ends ? ", until " : "") : "IN EFFECT" + (it.ends ? " — until " : ""))', src)
        self.assertIn("/^UPCOMING/.test(rows[i].textContent) !== isUpcoming(it)", src)
        self.assertIn("else if (alertPhaseStale(d.alerts))", src)
