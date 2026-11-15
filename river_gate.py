"""Quality gate for private freshwater preview Morning Briefs.

Used only by brief_preview for Jordan Lake and the Neuse River. It does not change
brief.validate, the public Falls Lake brief, coastal briefs, the 5:15 AM schedule,
or the archive.

Limits (hours) and why
----------------------
USGS_FRESH_H = 3. USGS instantaneous values are 15-minute data and typically land
on the wire within about an hour (the freshwater pages already describe an ~1 h
transmit delay). Three hours is the same stale threshold those pages already use:
two missed hourly transmits plus margin, without treating a half-day-old point as
current for a core check.

USGS_REJECT_H = 24. Same reject window as freshwater.py: a point older than this
is not a current observation (this is what stops a 1991 USGS "latest" discharge
from counting). The gate treats that as missing, not stale.

NWPS_FORECAST_FRESH_H = 18. SERFC / NWS river forecasts are issued a few times a
day, not every hour. Eighteen hours still accepts this morning's issuance late in
the evening, and last evening's issuance if the morning cycle is late, but it
rejects yesterday morning's forecast.

Alerts have no stale window. They are fetched live from the NWS alerts API (short
cache). The check is success vs failed-fetch; an empty list of events is a pass.

Statuses used on each check: pass, stale, missing, failed-fetch, n/a, optional.
n/a is never a failure. optional missing/stale is never a failure. Core stale,
missing, or failed-fetch fails the gate.

Jordan: Moncure (USGS 02098206) recommendation
----------------------------------------------
Count it as a labeled dam-release *equivalent* for this preview gate, not as
official gate outflow. It is about 1.6 miles below B. Everett Jordan Dam and
above the Deep River confluence, so the major named tributary is not in the
number, but local runoff is (the station note already says "release plus runoff").
The official tailrace gauge (USGS 02098198) is discontinued, and the USACE daily
outflow report can lag, so it is not a trustworthy live source. Every reason
string must say "Haw River flow at Moncure, not official dam discharge."
"""
from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import preview_alerts

ET = ZoneInfo("America/New_York")

USGS_FRESH_H = 3.0
USGS_REJECT_H = 24.0
NWPS_FORECAST_FRESH_H = 18.0

# Main-stem gauges that must supply both stage and flow. Two of these three
# must be fresh for the Neuse gate to pass.
NEUSE_FLOW_GAUGES = (
    {"usgs": "02087183", "nwps": "NEUN7", "label": "Neuse River below Falls Dam",
     "regulated": True, "routine_forecast": False},
    {"usgs": "02087500", "nwps": "CLYN7", "label": "Neuse River near Clayton",
     "regulated": True, "routine_forecast": True},
    {"usgs": "02089000", "nwps": "GLDN7", "label": "Neuse River near Goldsboro",
     "regulated": True, "routine_forecast": True},
)
NEUSE_STAGE_ONLY = {"usgs": "02087570", "nwps": "SMFN7", "label": "Neuse River at Smithfield",
                    "regulated": True, "routine_forecast": True}
# Lids that issue a routine year-round NWPS forecast on this reach.
NEUSE_FORECAST_LIDS = ("CLYN7", "SMFN7", "GLDN7")

JORDAN_LAKE_USGS = "02098197"
JORDAN_MONCURE_USGS = "02098206"
JORDAN_MONCURE_LABEL = "Haw River flow at Moncure, not official dam discharge"


def _parse(iso) -> datetime | None:
    if iso is None:
        return None
    if isinstance(iso, datetime):
        return iso if iso.tzinfo else iso.replace(tzinfo=timezone.utc)
    try:
        return datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _age_h(iso, now: datetime) -> float | None:
    t = _parse(iso)
    if t is None:
        return None
    return round((now - t).total_seconds() / 3600, 2)


def _et(iso) -> str | None:
    t = _parse(iso)
    if t is None:
        return None
    return t.astimezone(ET).strftime("%-I:%M %p ET")


def _kind_obs(regulated: bool = False, extra: str = "") -> str:
    bits = ["observed"]
    if regulated:
        bits.append("regulated flow")
    if extra:
        bits.append(extra)
    return ", ".join(bits)


def _check(check_id, label, status, reason, *, core=True, value=None, time=None,
           age_h=None, station=None, kind=None) -> dict:
    return {"id": check_id, "label": label, "status": status, "reason": reason, "core": core,
            "value": value, "time": time, "timeEt": _et(time), "ageH": age_h,
            "station": station, "kind": kind}


def _reading_status(reading, now: datetime, fresh_h=USGS_FRESH_H, reject_h=USGS_REJECT_H):
    """Classify a USGS (or similar) observation dict: (status, age_h, time)."""
    if reading is None:
        return "missing", None, None
    if not isinstance(reading, dict):
        return "missing", None, None
    if reading.get("status") in ("failed-fetch", "unavailable", "error") and reading.get("value") is None:
        return "failed-fetch", _age_h(reading.get("time"), now), reading.get("time")
    if reading.get("value") is None or not reading.get("time"):
        return "missing", None, reading.get("time")
    age = _age_h(reading.get("time"), now)
    if age is None:
        return "missing", None, reading.get("time")
    if age > reject_h:
        return "missing", age, reading.get("time")
    if age > fresh_h:
        return "stale", age, reading.get("time")
    return "pass", age, reading.get("time")


def _find_river(payload: dict, usgs: str) -> dict:
    for block in (payload.get("river") or []):
        if str(block.get("usgs")) == usgs:
            return block
    return {}


def _alerts_check(payload: dict, rid: str = "") -> dict:
    """Every listed zone must succeed; partial coverage is a failure."""
    al = payload.get("alerts")
    counties = preview_alerts.ALERT_COUNTIES.get(rid) or ()
    if al is None:
        return _check("alerts", "NWS alerts check", "failed-fetch",
                      "NWS alerts check is missing from the payload.", kind="observed")
    if counties:
        areas = preview_alerts.areas_phrase(counties)
        ids = preview_alerts.zone_ids(counties)
        cov = {c.get("id"): c for c in (al.get("coverage") or [])}
        failed = []
        for c in counties:
            for zid in (c["id"], c.get("ncc")):
                if not zid:
                    continue
                entry = cov.get(zid)
                if not entry or entry.get("status") != "ok":
                    failed.append("%s (%s)" % (c["name"], zid))
        if failed:
            reason = (
                "NWS alerts check failed for %s; checked %s (%s)."
                % (", ".join(failed), areas, ", ".join(ids))
            )
            return _check("alerts", "NWS alerts check", "failed-fetch", reason, kind="observed")
        n = len(al.get("items") or [])
        return _check("alerts", "NWS alerts check", "pass",
                      "NWS alerts check succeeded for %s (%s)." % (
                          areas, "no active alerts" if n == 0 else "%d active" % n),
                      kind="observed")
    status = al.get("status")
    if status == "ok":
        n = len(al.get("items") or [])
        return _check("alerts", "NWS alerts check", "pass",
                      "NWS alerts check succeeded (%s)." % ("no active alerts" if n == 0 else "%d active" % n),
                      kind="observed")
    return _check("alerts", "NWS alerts check", "failed-fetch",
                  "NWS alerts check failed (fetch did not succeed).", kind="observed")


def _water_temp_na(why: str) -> dict:
    return _check("water-temp", "Water temp", "n/a", why, core=False, kind="n/a")


def _optional_weather(payload: dict, now: datetime) -> dict:
    fc = payload.get("forecast") or {}
    if fc.get("status") == "ok" and fc.get("periods"):
        return _check("weather", "NWS point forecast", "pass",
                      "NWS point forecast is present (optional).",
                      core=False, time=fc.get("updated"), age_h=_age_h(fc.get("updated"), now),
                      kind="forecast")
    return _check("weather", "NWS point forecast", "optional",
                  "NWS point forecast was not available (optional).",
                  core=False, kind="forecast")


def _cfs(v) -> str:
    s = ("%g" % v)
    return s + " cfs"


def _gauge_stage_flow(block: dict, spec: dict, now: datetime, stage_only: bool = False) -> list[dict]:
    out = []
    usgs, label = spec["usgs"], spec["label"]
    stage = block.get("stageFt") if block else None
    flow = block.get("flowCfs") if block else None

    st_s, age_s, t_s = _reading_status(stage, now)
    if st_s == "pass":
        reason_s = "%s stage is fresh (%.2f ft, %s, %.1f h old)." % (label, stage["value"], _et(t_s), age_s or 0)
    elif st_s == "stale":
        reason_s = "%s stage is stale (%.1f h old; limit %.0f h)." % (label, age_s or 0, USGS_FRESH_H)
    elif st_s == "failed-fetch":
        reason_s = "%s stage could not be fetched from USGS." % label
    else:
        reason_s = "%s stage is missing (no current USGS observation)." % label
    out.append(_check("stage-%s" % usgs, "%s stage" % label, st_s, reason_s,
                      core=not stage_only,
                      value=(stage or {}).get("value") if isinstance(stage, dict) else None,
                      time=t_s, age_h=age_s, station=usgs, kind="observed"))

    if stage_only:
        out.append(_check("flow-%s" % usgs, "%s flow" % label, "n/a",
                          "%s is stage only: USGS does not publish discharge here (not a failure)." % label,
                          core=False, station=usgs, kind="n/a"))
        return out

    st_f, age_f, t_f = _reading_status(flow, now)
    if st_f == "pass":
        reason_f = "%s flow is fresh (%s, %s, %.1f h old, regulated)." % (
            label, _cfs(flow["value"]), _et(t_f), age_f or 0)
    elif st_f == "stale":
        reason_f = "%s flow is stale (%.1f h old; limit %.0f h, regulated flow)." % (label, age_f or 0, USGS_FRESH_H)
    elif st_f == "failed-fetch":
        reason_f = "%s flow could not be fetched from USGS (regulated flow)." % label
    else:
        reason_f = "%s flow is missing (no current USGS observation, regulated flow)." % label
    out.append(_check("flow-%s" % usgs, "%s flow" % label, st_f, reason_f,
                      core=True, value=(flow or {}).get("value") if isinstance(flow, dict) else None,
                      time=t_f, age_h=age_f, station=usgs, kind=_kind_obs(regulated=spec.get("regulated", False))))
    return out


def _neuse_forecast(payload: dict, now: datetime) -> dict:
    best = None
    failed = 0
    saw_ok = 0
    for block in (payload.get("river") or []):
        nw = block.get("nwps") or {}
        lid = nw.get("lid") or ""
        if lid not in NEUSE_FORECAST_LIDS:
            continue
        if nw.get("status") in ("failed-fetch", "unavailable", "error"):
            failed += 1
            continue
        saw_ok += 1
        fc = nw.get("forecast")
        if not fc or fc.get("issued") is None:
            continue
        age = _age_h(fc.get("issued"), now)
        if age is None:
            continue
        cand = ("stale" if age > NWPS_FORECAST_FRESH_H else "pass", age, fc, lid, block.get("label") or lid)
        if best is None or (cand[0] == "pass" and best[0] != "pass") or (cand[0] == best[0] and cand[1] < best[1]):
            best = cand
    if best and best[0] == "pass":
        _, age, fc, lid, name = best
        crest = ("%.1f" % fc["crestStage"]) if fc.get("crestStage") is not None else "n/a"
        return _check("nwps-forecast", "NWPS river forecast", "pass",
                      "NWS forecast (NWPS %s, %s) issued %s (%.1f h old), crest %s ft. Labeled forecast, not an observation."
                      % (lid, name, _et(fc.get("issued")), age, crest),
                      time=fc.get("issued"), age_h=age, station=lid, kind="forecast",
                      value=fc.get("crestStage"))
    if best and best[0] == "stale":
        _, age, fc, lid, name = best
        return _check("nwps-forecast", "NWPS river forecast", "stale",
                      "NWS forecast (NWPS %s) is stale (issued %s, %.1f h old; limit %.0f h)."
                      % (lid, _et(fc.get("issued")), age, NWPS_FORECAST_FRESH_H),
                      time=fc.get("issued"), age_h=age, station=lid, kind="forecast")
    if failed and not saw_ok:
        return _check("nwps-forecast", "NWPS river forecast", "failed-fetch",
                      "NWPS forecast fetch failed at the routine-forecast gauges (CLYN7, SMFN7, GLDN7).",
                      kind="forecast")
    return _check("nwps-forecast", "NWPS river forecast", "missing",
                  "No recent NWS NWPS forecast at Clayton, Smithfield or Goldsboro (routine-forecast gauges).",
                  kind="forecast")


def evaluate_neuse(payload: dict, now: datetime) -> list[dict]:
    checks = []
    fresh_gauges = []
    for spec in NEUSE_FLOW_GAUGES:
        block = _find_river(payload, spec["usgs"])
        parts = _gauge_stage_flow(block, spec, now, stage_only=False)
        checks.extend(parts)
        stage_ok = any(c["id"] == "stage-%s" % spec["usgs"] and c["status"] == "pass" for c in parts)
        flow_ok = any(c["id"] == "flow-%s" % spec["usgs"] and c["status"] == "pass" for c in parts)
        if stage_ok and flow_ok:
            fresh_gauges.append(spec["usgs"])
    n = len(fresh_gauges)
    if n >= 2:
        checks.append(_check("neuse-core-gauges", "Main-stem stage and flow", "pass",
                             "Fresh stage and flow (observed, regulated) at %d of 3 core gauges (%s)."
                             % (n, ", ".join(fresh_gauges)),
                             kind="observed"))
    else:
        checks.append(_check("neuse-core-gauges", "Main-stem stage and flow", "missing" if n == 0 else "stale",
                             "Only %d of 3 core gauges (02087183, 02087500, 02089000) have fresh stage and flow; need 2."
                             % n,
                             kind="observed"))
    smf = _find_river(payload, NEUSE_STAGE_ONLY["usgs"])
    smf_parts = _gauge_stage_flow(smf, NEUSE_STAGE_ONLY, now, stage_only=True)
    for c in smf_parts:
        if c["id"].startswith("stage-"):
            c["core"] = False
            if c["status"] in ("missing", "stale", "failed-fetch"):
                c["reason"] = c["reason"] + " Optional; not required for the river gate."
                c["status"] = "optional"
        checks.append(c)
    checks.append(_neuse_forecast(payload, now))
    checks.append(_alerts_check(payload, "neuse-river"))
    checks.append(_water_temp_na("No active USGS water-temperature sensor on the Neuse main stem (not a failure)."))
    checks.append(_optional_weather(payload, now))
    checks.append(_check("rain", "Rain", "n/a",
                         "No USGS rain gauge is configured on this Neuse reach (not a failure).",
                         core=False, kind="n/a"))
    checks.append(_check("nwps-neun7", "NWPS forecast at NEUN7", "n/a",
                         "NWS publishes no routine forecast at NEUN7 (below Falls Dam); not a failure.",
                         core=False, station="NEUN7", kind="n/a"))
    return checks


def evaluate_jordan(payload: dict, now: datetime) -> list[dict]:
    checks = []
    lake = payload.get("lake") or {}
    elev = lake.get("elevation")
    st, age, t = _reading_status(elev, now)
    if st == "pass":
        reason = "Lake elevation is fresh (%.2f ft NGVD29 at USGS %s, %s, %.1f h old)." % (
            elev["value"], lake.get("usgs") or JORDAN_LAKE_USGS, _et(t), age or 0)
    elif st == "stale":
        reason = "Lake elevation is stale (%.1f h old; limit %.0f h)." % (age or 0, USGS_FRESH_H)
    elif st == "failed-fetch":
        reason = "Lake elevation could not be fetched from USGS."
    else:
        reason = "Lake elevation is missing (no current USGS 62614 observation at 02098197)."
    checks.append(_check("lake-elev", "Lake elevation", st, reason, core=True,
                         value=(elev or {}).get("value") if isinstance(elev, dict) else None,
                         time=t, age_h=age, station=lake.get("usgs") or JORDAN_LAKE_USGS,
                         kind="observed"))

    rel = payload.get("release") or {}
    flow = rel.get("flowCfs")
    station = rel.get("usgs") or JORDAN_MONCURE_USGS
    st, age, t = _reading_status(flow, now)
    if st == "pass":
        reason = "Fresh flow at USGS %s (%.0f cfs, %s, %.1f h old), counted as %s." % (
            station, flow["value"], _et(t), age or 0, JORDAN_MONCURE_LABEL)
    elif st == "stale":
        reason = "Flow at USGS %s (%s) is stale (%.1f h old; limit %.0f h)." % (
            station, JORDAN_MONCURE_LABEL, age or 0, USGS_FRESH_H)
    elif st == "failed-fetch":
        reason = "Flow at USGS %s (%s) could not be fetched from USGS." % (station, JORDAN_MONCURE_LABEL)
    else:
        reason = "Flow at USGS %s (%s) is missing." % (station, JORDAN_MONCURE_LABEL)
    checks.append(_check("moncure-runoff", "Haw River flow at Moncure (USGS 02098206)", st, reason, core=True,
                         value=(flow or {}).get("value") if isinstance(flow, dict) else None,
                         time=t, age_h=age, station=station, kind=_kind_obs(False, JORDAN_MONCURE_LABEL)))

    checks.append(_alerts_check(payload, "jordan-lake"))
    checks.append(_water_temp_na("No USGS water-temperature sensor at Jordan Lake dam 02098197 (not a failure)."))
    checks.append(_optional_weather(payload, now))

    rain = payload.get("rain") or {}
    if rain.get("status") == "ok" and rain.get("last24In") is not None:
        checks.append(_check("rain", "Rain at the dam", "pass",
                             "USGS rain at the dam is present (optional): %.2f in last 24 h." % rain["last24In"],
                             core=False, time=rain.get("time"), age_h=_age_h(rain.get("time"), now),
                             station=rain.get("usgs") or JORDAN_LAKE_USGS, kind="observed",
                             value=rain.get("last24In")))
    else:
        checks.append(_check("rain", "Rain at the dam", "optional",
                             "USGS rain at the dam was not available (optional).",
                             core=False, kind="observed"))

    inf = (payload.get("inflows") or [None])[0] or {}
    flow_i = inf.get("flowCfs")
    if flow_i:
        st_i, age_i, t_i = _reading_status(flow_i, now)
        if st_i == "pass":
            msg = "Bynum inflow is fresh (%.1f cfs, %s) (optional, above the lake)." % (flow_i["value"], _et(t_i))
        else:
            msg = "Bynum inflow is %s (optional, above the lake)." % st_i
        checks.append(_check("bynum-inflow", "Haw River near Bynum (inflow)", "pass" if st_i == "pass" else "optional",
                             msg, core=False, value=flow_i.get("value"), time=t_i, age_h=age_i,
                             station=inf.get("usgs") or "02096960", kind="observed"))
    else:
        checks.append(_check("bynum-inflow", "Haw River near Bynum (inflow)", "optional",
                             "Bynum inflow was not available (optional, above the lake).",
                             core=False, station="02096960", kind="observed"))

    checks.append(_check("official-outflow", "Official gate outflow", "n/a",
                         "Official gate outflow is not used: USGS 02098198 is discontinued, and the USACE daily report can lag (not a failure).",
                         core=False, kind="n/a"))
    checks.append(_check("nwps-lake-fc", "NWPS lake-level forecast", "n/a",
                         "NWS publishes no lake-level forecast at NHPN7 (not a failure).",
                         core=False, station="NHPN7", kind="n/a"))
    return checks


def _failing_core(rid: str, checks: list[dict]) -> list[dict]:
    """Core failures that fail the gate.

    On the Neuse, per-gauge stage/flow on the three discharge sites are evidence
    for the 2-of-3 summary; a single missed gauge must not fail the whole gate.
    """
    flow_ids = {s["usgs"] for s in NEUSE_FLOW_GAUGES}
    failing = []
    for c in checks:
        if not c.get("core") or c["status"] in ("pass", "n/a", "optional"):
            continue
        if rid == "neuse-river" and (c["id"].startswith("stage-") or c["id"].startswith("flow-")):
            if c["id"].split("-", 1)[-1] in flow_ids:
                continue
        failing.append(c)
    return failing


def evaluate(rid: str, payload: dict | None, now: datetime | None = None) -> dict:
    """Run the preview quality gate. Never raises; always returns a result dict."""
    now = now or datetime.now(timezone.utc)
    if not now.tzinfo:
        now = now.replace(tzinfo=timezone.utc)
    if not payload or not payload.get("ok", True):
        checks = [_check("payload", "Freshwater assemble", "failed-fetch",
                         "Freshwater payload was missing or the assemble failed.",
                         kind="observed")]
    elif rid == "neuse-river":
        checks = evaluate_neuse(payload, now)
    elif rid == "jordan-lake":
        checks = evaluate_jordan(payload, now)
    else:
        checks = [_check("region", "Region", "n/a",
                         "No freshwater preview gate for this region.",
                         core=False, kind="n/a")]

    failing = _failing_core(rid, checks)
    errors = [c["reason"] for c in failing]
    notes = []
    if not errors:
        if rid == "neuse-river":
            summary = next((c for c in checks if c["id"] == "neuse-core-gauges"), None)
            bits = []
            if summary:
                bits.append(summary["reason"].rstrip("."))
            bits.append("recent NWPS forecast")
            bits.append("alerts check ok")
            notes.append(", ".join(bits))
        elif rid == "jordan-lake":
            notes.append("all core checks present (lake elevation, %s, alerts check ok)" % JORDAN_MONCURE_LABEL)
        if any(c["id"] == "water-temp" and c["status"] == "n/a" for c in checks):
            notes.append("water temp not applicable")
    return {"ok": not errors, "regionId": rid, "checkedAt": now.isoformat(),
            "checks": checks, "errors": errors, "notes": notes,
            "gate": "freshwater-preview"}


def as_validation(gate: dict) -> dict:
    """Shape the gate result like brief.validate's summary, for the preview banner."""
    return {"status": "ok" if gate.get("ok") else "failed",
            "checkedAt": gate.get("checkedAt"),
            "errors": list(gate.get("errors") or []),
            "notes": list(gate.get("notes") or []),
            "checks": [c["id"] for c in (gate.get("checks") or [])],
            "gate": "freshwater-preview",
            "detail": gate.get("checks") or []}
