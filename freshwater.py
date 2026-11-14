"""Freshwater (lake and river) conditions for the private preview.

Off unless FRESHWATER_ENABLED=1. Production never sets it, so every route that
uses this module returns 404 there. Only freshwater regions from
data/regions.json with previewReady are served, and they stay enabled=false/draft=true.
Falls Lake, Jordan Lake and the Neuse River (Falls Dam to Goldsboro) are preview-ready.

Every value carries its source, station id and observation time. Nothing is
estimated: if a reading is missing or stale, the payload says so. Instantaneous
values older than REJECT_H hours are dropped (so a 1991 USGS "latest" discharge
is never shown as current).

Datums: USGS 62614 is lake elevation above NGVD 1929 and 62615 above NAVD 1988.
USACE Wilmington District reports Falls and Jordan in "ft-msl", which matches
USGS 62614, so each guide curve is compared with 62614 only.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import conditions

TTL_IV = 600          # USGS instantaneous values publish every 15 min
TTL_STAT = 86400      # daily statistics change once a year
TTL_NWPS = 900
TTL_NWS = 900
TTL_USACE = 6 * 3600
STALE_H = 3           # a USGS reading older than this is labelled stale
REJECT_H = 24         # older than this is treated as missing, not current
ASSEMBLED_TTL = 300

_POOL = ThreadPoolExecutor(max_workers=8)
_LOCK = threading.Lock()
_ASSEMBLED: dict[str, tuple[float, dict]] = {}


def flag_on() -> bool:
    return (os.environ.get("FRESHWATER_ENABLED") or "").strip().lower() in ("1", "true", "on", "yes")


def regions() -> dict:
    cfg = conditions.load_regions()
    return {r["id"]: r for r in cfg.get("regions") or [] if r.get("waterType") == "freshwater"}


def _get_json(url, ttl):
    body = conditions.get_json(url, ttl)
    if not body:
        return None
    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None


def _get_text(url, ttl):
    body = conditions.get_json(url, ttl, accept="*/*")
    if not body:
        return None
    try:
        return body.decode("utf-8", "replace")
    except Exception:
        return None


def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f <= -999990 or f != f:  # USGS sentinel -999999 / NaN
        return None
    return f


def _parse_t(s):
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None


def _age_h(t, now):
    return None if t is None else round((now - t).total_seconds() / 3600, 2)


# ---------- USGS instantaneous values ----------

def usgs_iv(sites, params, period="P1D"):
    """{(site, param): [(datetime, value), ...]} for the period, oldest first."""
    q = urlencode({"format": "json", "sites": ",".join(sorted(set(sites))),
                   "parameterCd": ",".join(sorted(set(params))), "period": period, "siteStatus": "all"})
    d = _get_json("https://waterservices.usgs.gov/nwis/iv/?" + q, TTL_IV)
    out, names = {}, {}
    for ts in ((d or {}).get("value") or {}).get("timeSeries") or []:
        site = ts["sourceInfo"]["siteCode"][0]["value"]
        names[site] = ts["sourceInfo"].get("siteName")
        p = ts["variable"]["variableCode"][0]["value"]
        pts = []
        for blk in ts.get("values") or []:
            for v in blk.get("value") or []:
                val, t = _num(v.get("value")), _parse_t(v.get("dateTime"))
                if val is not None and t is not None:
                    pts.append((t, val))
        if pts:
            pts.sort(key=lambda x: x[0])
            # several method blocks can exist for one parameter; keep the longest
            if len(pts) > len(out.get((site, p), [])):
                out[(site, p)] = pts
    return out, names


def latest(series, now, max_age_h=REJECT_H):
    """Newest point whose own timestamp is within max_age_h. Older points are
    rejected so a decades-old USGS IV value cannot appear as a current reading.
    Points between STALE_H and max_age_h are returned with stale=True."""
    if not series:
        return None
    for t, v in reversed(series):
        age = _age_h(t, now)
        if age is not None and age > max_age_h:
            continue
        return {"value": v, "time": t.isoformat(), "ageH": age, "stale": age is not None and age > STALE_H}
    return None


def change_over(series, hours):
    if not series:
        return None
    t_end, v_end = series[-1]
    target = t_end - timedelta(hours=hours)
    best = min(series, key=lambda p: abs((p[0] - target).total_seconds()))
    if abs((best[0] - target).total_seconds()) > 3600:
        return None
    return round(v_end - best[1], 2)


# ---------- USGS daily statistics (flow percentiles) ----------

def usgs_daily_stats(site, day):
    q = urlencode({"format": "rdb", "sites": site, "statReportType": "daily", "statTypeCd": "all", "parameterCd": "00060"})
    txt = _get_text("https://waterservices.usgs.gov/nwis/stat/?" + q, TTL_STAT)
    if not txt:
        return None
    head = None
    for line in txt.splitlines():
        if line.startswith("#") or not line.strip():
            continue
        cols = line.split("\t")
        if head is None:
            head = cols
            continue
        if cols[0].endswith("s") and cols[0][:-1].isdigit():
            continue  # rdb format row
        row = dict(zip(head, cols))
        if row.get("month_nu") == str(day.month) and row.get("day_nu") == str(day.day):
            def g(k):
                return _num(row.get(k))
            return {"years": "%s–%s" % (row.get("begin_yr"), row.get("end_yr")), "count": row.get("count_nu"),
                    "min": g("min_va"), "p10": g("p10_va"), "p25": g("p25_va"), "p50": g("p50_va"),
                    "p75": g("p75_va"), "p90": g("p90_va"), "max": g("max_va")}
    return None


def flow_band(cfs, st):
    """USGS WaterWatch classes against daily-mean percentiles for this date."""
    if cfs is None or not st or st.get("p10") is None:
        return None
    if st.get("min") is not None and cfs < st["min"]:
        label, key = "Below lowest daily mean for this date", "record-low"
    elif cfs < st["p10"]:
        label, key = "Much below normal", "much-below"
    elif st.get("p25") is not None and cfs < st["p25"]:
        label, key = "Below normal", "below"
    elif st.get("p75") is not None and cfs <= st["p75"]:
        label, key = "Normal", "normal"
    elif st.get("p90") is not None and cfs <= st["p90"]:
        label, key = "Above normal", "above"
    else:
        label, key = "Much above normal", "much-above"
    return {"key": key, "label": label}


# ---------- NWS NWPS ----------

def nwps(lid):
    g = _get_json("https://api.water.noaa.gov/nwps/v1/gauges/%s" % lid, TTL_NWPS)
    if not g:
        return {"lid": lid, "status": "unavailable"}
    cats = ((g.get("flood") or {}).get("categories")) or {}
    stages = {k: _num((cats.get(k) or {}).get("stage")) for k in ("action", "minor", "moderate", "major")}
    st = g.get("status") or {}
    obs, fc = st.get("observed") or {}, st.get("forecast") or {}
    out = {"lid": lid, "status": "ok", "name": g.get("name"), "floodStages": stages,
           "observedCategory": obs.get("floodCategory"),
           "url": "https://water.noaa.gov/gauges/%s" % lid.lower()}
    if _num(fc.get("primary")) is not None:
        sf = _get_json("https://api.water.noaa.gov/nwps/v1/gauges/%s/stageflow/forecast" % lid, TTL_NWPS) or {}
        data = sf.get("data") or []
        pts = [(d.get("validTime"), _num(d.get("primary")), _num(d.get("secondary"))) for d in data]
        pts = [p for p in pts if p[1] is not None]
        if pts:
            crest = max(pts, key=lambda p: p[1])
            out["forecast"] = {"issued": sf.get("issuedTime"), "units": [sf.get("primaryUnits"), sf.get("secondaryUnits")],
                               "crestStage": crest[1], "crestTime": crest[0],
                               "crestFlowCfs": round(crest[2] * 1000) if crest[2] is not None and (sf.get("secondaryUnits") == "kcfs") else None,
                               "category": fc.get("floodCategory"), "end": pts[-1][0],
                               "series": [[p[0], p[1]] for p in pts]}
    return out


# ---------- NWS forecast, QPF, alerts ----------

def qpf_block(fcfg, now):
    d = _get_json("https://api.weather.gov/gridpoints/%s/%d,%d" % (fcfg["gridId"], fcfg["gridX"], fcfg["gridY"]), TTL_NWS)
    props = (d or {}).get("properties") or {}
    q = props.get("quantitativePrecipitation") or {}
    vals = q.get("values") or []
    if not vals:
        return {"status": "unavailable", "kind": "forecast"}
    mm_per = 1.0 if (q.get("uom") or "").endswith("mm") else None
    if mm_per is None:
        return {"status": "unavailable", "kind": "forecast"}
    tot = {24: 0.0, 72: 0.0}
    covered = {24: 0.0, 72: 0.0}
    for v in vals:
        m = re.match(r"(.+)/P(?:T(\d+)H|(\d+)D(?:T(\d+)H)?)", v.get("validTime") or "")
        if not m:
            continue
        start = _parse_t(m.group(1))
        hours = int(m.group(2) or 0) + 24 * int(m.group(3) or 0) + int(m.group(4) or 0)
        if start is None or hours <= 0 or v.get("value") is None:
            continue
        end = start + timedelta(hours=hours)
        for h in (24, 72):
            w0, w1 = now, now + timedelta(hours=h)
            ov = (min(end, w1) - max(start, w0)).total_seconds() / 3600
            if ov > 0:
                tot[h] += float(v["value"]) * ov / hours   # spread evenly inside the NWS period
                covered[h] += ov
    return {"status": "ok", "kind": "forecast", "updated": props.get("updateTime"),
            "next24In": round(tot[24] / 25.4, 2), "next72In": round(tot[72] / 25.4, 2),
            "coverage24H": round(covered[24], 1), "coverage72H": round(covered[72], 1),
            "note": "NWS gridded QPF for the dam grid cell. Where an NWS period crosses the window edge its total is split evenly by hours.",
            "sourceUrl": "https://forecast.weather.gov/MapClick.php?lat=%s&lon=%s&FcstType=graphical" % (fcfg["lat"], fcfg["lon"])}


def alerts_point(lat, lon):
    d = _get_json("https://api.weather.gov/alerts/active?point=%.4f,%.4f" % (lat, lon), 300)
    if d is None:
        return {"status": "unavailable", "items": []}
    items, seen = [], set()
    for f in d.get("features") or []:
        p = f.get("properties") or {}
        key = (p.get("event"), p.get("ends") or p.get("expires"))
        if key in seen:
            continue
        seen.add(key)
        items.append({"event": p.get("event"), "severity": p.get("severity"), "areas": p.get("areaDesc"),
                      "ends": p.get("ends") or p.get("expires"), "headline": p.get("headline")})
    return {"status": "ok", "items": items, "sourceUrl": "https://alerts.weather.gov/"}


# ---------- USACE guide curve check ----------

def usace_guide_check(expected):
    """Confirms the configured guide curve against the USACE home page table.
    The table's column headers have been seen out of order, so the value is
    matched by number, not by column label."""
    txt = _get_text("https://epec.saw.usace.army.mil/", TTL_USACE)
    if not txt:
        return {"status": "unavailable"}
    i = txt.find("Guide Curve")
    if i < 0:
        return {"status": "unavailable"}
    seg = re.sub(r"<[^>]+>", " ", txt[i:i + 4000])
    vals = [float(x) for x in re.findall(r"\b(\d{3,4}\.\d{2})\b", seg)[:5]]
    return {"status": "ok", "matches": any(abs(v - expected) < 0.005 for v in vals), "values": vals,
            "url": "https://epec.saw.usace.army.mil/"}


# ---------- assemble ----------

def _flow_station(spec, iv, now, stats_day):
    site = spec["usgs"]
    stage_only = spec.get("flow") is False
    # Stage-only gauges (Smithfield) must never expose discharge, even if IV still
    # returns a historical 00060 value.
    q = None if stage_only else latest(iv.get((site, "00060")), now)
    h = latest(iv.get((site, "00065")), now)
    out = {"usgs": site, "label": spec.get("label"), "kind": "observed", "regulated": bool(spec.get("regulated")),
           "url": "https://waterdata.usgs.gov/monitoring-location/%s/" % site,
           "flowCfs": q, "stageFt": h}
    if spec.get("tileTitle"):
        out["tileTitle"] = spec["tileTitle"]
    if spec.get("note"):
        out["note"] = spec["note"]
    if spec.get("floodStages"):
        out["floodStages"] = dict(spec["floodStages"])
    if stage_only:
        out["stageOnly"] = True
        out["flowCfs"] = None
        out["flowNote"] = spec.get("flowNote") or "Discharge not published at this gauge. Stage only."
    if out["flowCfs"] and not out["flowCfs"]["stale"]:
        st = usgs_daily_stats(site, stats_day)
        out["stats"] = st
        out["band"] = flow_band(out["flowCfs"]["value"], st)
    return out


def _attach_nwps(spec, block, nw):
    if spec.get("nwps"):
        block["nwps"] = nw.get(spec["nwps"])
    # Prefer live NWPS flood stages; fall back to the documented NWS values.
    live = ((block.get("nwps") or {}).get("floodStages") if (block.get("nwps") or {}).get("status") == "ok" else None)
    if not live or all(v is None for v in live.values()):
        if spec.get("floodStages"):
            if block.get("nwps"):
                merged = dict(block["nwps"])
                merged["floodStages"] = dict(spec["floodStages"])
                block["nwps"] = merged
            block.setdefault("floodStages", dict(spec["floodStages"]))
    return block


def assemble(rid):
    regs = regions()
    if rid not in regs:
        return 404, {"ok": False, "error": "Unknown freshwater region."}
    r = regs[rid]
    inst = r.get("instrumentSet")
    if not r.get("previewReady"):
        return 404, {"ok": False, "error": "This freshwater view is not built yet."}
    if inst == "freshwater-lake":
        if not r.get("lake"):
            return 404, {"ok": False, "error": "This freshwater view is not built yet."}
    elif inst == "freshwater-river":
        if not r.get("river"):
            return 404, {"ok": False, "error": "This freshwater view is not built yet."}
    else:
        return 404, {"ok": False, "error": "This freshwater view is not built yet."}
    with _LOCK:
        hit = _ASSEMBLED.get(rid)
        if hit and time.time() - hit[0] < ASSEMBLED_TTL:
            return 200, hit[1]
    now = datetime.now(timezone.utc)
    et_today = (now - timedelta(hours=5)).date()  # stats are keyed by calendar day; ET is close enough
    lake = r.get("lake")
    river = r.get("river") or []
    inflows = r.get("inflows") or []
    rel = r.get("release")
    sites = [s["usgs"] for s in river + inflows] + ([rel["usgs"]] if rel else [])
    if lake:
        sites = [lake["usgs"]] + sites

    f_iv7 = None
    if lake:
        lake_params = [lake["elevNgvd29"], lake["elevNavd88"]]
        if lake.get("waterTemp"):
            lake_params.append(lake["waterTemp"])
        if lake.get("rain"):
            lake_params.append(lake["rain"])
        f_iv7 = _POOL.submit(usgs_iv, [lake["usgs"]], lake_params, "P7D")
    f_ivq = _POOL.submit(usgs_iv, sites, ["00060", "00065"], "P1D") if sites else None
    f_fc = _POOL.submit(conditions.forecast_block, r["forecast"]) if r.get("forecast") else None
    f_qpf = _POOL.submit(qpf_block, r["forecast"], now) if lake and r.get("forecast") else None
    alert_pt = r.get("alertPoint") or [r["anchor"]["lat"], r["anchor"]["lon"]]
    f_al = _POOL.submit(alerts_point, *alert_pt)
    f_guide = _POOL.submit(usace_guide_check, lake["guideCurveFt"]) if lake and lake.get("guideCurveFt") is not None else None
    lids = [s["nwps"] for s in river + ([rel] if rel else []) if s.get("nwps")]
    if lake and lake.get("nwps"):
        lids.append(lake["nwps"])
    f_nwps = {lid: _POOL.submit(nwps, lid) for lid in lids}

    names = {}
    iv7 = {}
    if f_iv7 is not None:
        iv7, names = f_iv7.result()
    ivq = {}
    if f_ivq is not None:
        ivq, names2 = f_ivq.result()
        names.update(names2)

    lake_out = None
    water = {"kind": "observed", "status": "unavailable", "c": None, "f": None, "time": None, "stale": None,
             "note": (r.get("waterTemp") or {}).get("note") or "No active USGS water-temperature sensor at this location."}
    rain = None
    if lake:
        elev_s = iv7.get((lake["usgs"], lake["elevNgvd29"]))
        navd_s = iv7.get((lake["usgs"], lake["elevNavd88"]))
        temp_s = iv7.get((lake["usgs"], lake["waterTemp"])) if lake.get("waterTemp") else None
        rain_s = iv7.get((lake["usgs"], lake["rain"])) if lake.get("rain") else None

        elev = latest(elev_s, now)
        lake_out = {"kind": "observed", "usgs": lake["usgs"], "siteName": names.get(lake["usgs"]),
                    "url": "https://waterdata.usgs.gov/monitoring-location/%s/" % lake["usgs"],
                    "elevation": elev, "datum": "NGVD29", "navd88": latest(navd_s, now),
                    "guideCurveFt": lake["guideCurveFt"], "guideCurveDatum": lake["guideCurveDatum"],
                    "guideCurveSource": lake["guideCurveSource"], "guideCurveChecked": lake["guideCurveChecked"],
                    "guideCurveNote": lake.get("guideCurveNote"), "usacePage": lake.get("usacePage"),
                    "change24hFt": change_over(elev_s, 24) if elev else None,
                    "change7dFt": change_over(elev_s, 24 * 7) if elev and elev_s and len(elev_s) > 10 else None}
        if lake.get("floodStages"):
            lake_out["floodStages"] = dict(lake["floodStages"])
        if elev and lake.get("guideCurveFt") is not None:
            lake_out["vsGuideFt"] = round(elev["value"] - lake["guideCurveFt"], 2)
            if lake_out["navd88"]:
                lake_out["datumOffsetFt"] = round(elev["value"] - lake_out["navd88"]["value"], 2)
        if elev_s:
            # hourly points for the 7-day chart
            hourly, last_h = [], None
            for t, v in elev_s:
                k = t.replace(minute=0, second=0, microsecond=0)
                if k != last_h:
                    hourly.append([t.isoformat(), v])
                    last_h = k
            lake_out["series7d"] = hourly
        if lake.get("waterTemp"):
            temp = latest(temp_s, now)
            water = {"kind": "observed", "usgs": lake["usgs"], "status": "ok" if temp else "unavailable",
                     "c": temp["value"] if temp else None, "f": round(temp["value"] * 9 / 5 + 32, 1) if temp else None,
                     "time": temp["time"] if temp else None, "stale": temp["stale"] if temp else None,
                     "note": "USGS sensor at the dam. Surface temperatures elsewhere on the lake can differ."}
        else:
            water = {"kind": "observed", "status": "unavailable", "c": None, "f": None, "time": None, "stale": None,
                     "note": (r.get("waterTemp") or {}).get("note") or "No USGS water-temperature sensor at the dam."}

        rain = {"kind": "observed", "usgs": lake["usgs"], "status": "unavailable"}
        if rain_s:
            t_end = rain_s[-1][0]
            age = _age_h(t_end, now)
            if age is None or age <= REJECT_H:
                def total(h):
                    span = [v for t, v in rain_s if t > t_end - timedelta(hours=h)]
                    have_h = (t_end - rain_s[0][0]).total_seconds() / 3600
                    return round(sum(span), 2) if have_h >= h - 0.5 else None
                rain.update(status="ok", last24In=total(24), last7dIn=total(24 * 7), time=t_end.isoformat(),
                            stale=age is not None and age > STALE_H,
                            note="USGS rain gauge at the dam (one point; rain varies across the basin).")
        if f_qpf is not None:
            rain["qpf"] = f_qpf.result()

    nw = {lid: f.result() for lid, f in f_nwps.items()}
    release = _attach_nwps(rel, _flow_station(rel, ivq, now, et_today), nw) if rel else None
    river_out = [_attach_nwps(s, _flow_station(s, ivq, now, et_today), nw) for s in river]
    inflow_out = [_flow_station(s, ivq, now, et_today) for s in inflows]
    if lake_out is not None and lake:
        lake_out = _attach_nwps(lake, lake_out, nw)

    payload = {"ok": True, "private": True, "generatedAt": now.isoformat(),
               "region": {k: r.get(k) for k in ("id", "name", "area", "anchor", "waterType", "instrumentSet")},
               "lake": lake_out, "waterTemp": water, "rain": rain, "release": release,
               "inflows": inflow_out, "river": river_out,
               "forecast": f_fc.result() if f_fc is not None else {"status": "unavailable"},
               "alerts": f_al.result(), "guideCheck": f_guide.result() if f_guide is not None else None,
               "links": r.get("links") or [], "staleRuleH": STALE_H}
    with _LOCK:
        _ASSEMBLED[rid] = (time.time(), payload)
    return 200, payload
