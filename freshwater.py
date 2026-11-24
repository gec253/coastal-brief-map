"""Freshwater (lake and river) conditions.

On by default for Falls Lake, Jordan Lake and the Neuse River (Falls Dam to
Goldsboro). Set FRESHWATER_ENABLED to 0, false, or off to disable (a kill switch).
Only freshwater regions from data/regions.json with previewReady are assembled.

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
# A cached page older than ASSEMBLED_TTL but younger than this is served at once while a background
# refresh runs, so a visitor never waits on slow USGS calls. Every reading keeps its own observation time.
ASSEMBLED_SERVE_MAX = 1200
WARM_EVERY = 240
# Freshwater-only fetch bound (installed from server.py). Saltwater fetch_url stays 45s / 4 tries.
# Chosen from the t460u Render-host distribution (cb-fw-v3-test-37227f, 24 Nov 2026):
#   usgs_iv   p50 11.5s, p90 30.1s, max 31.0s (n=24, all ok)
#   usgs_stat p50 8.5s,  p90 20.8s, max 42.4s (n=43, 4 HTTP 502 in ~4s)
# FETCH 45s covers the observed IV max with ~14s of margin and the observed stats max.
# RESULT 50s covers one full 45s try plus a little pool slack. The visitor-facing
# wait stays 8s and never cancels an in-flight request. Daily-stats are not on
# the result-budget critical path: readings publish without waiting on percentiles.
FETCH_TIMEOUT = 45
FETCH_TRIES = 1
FETCH_BACKOFF = 0.5
RESULT_TIMEOUT = 50
# Visitor-facing API wait. The in-flight assemble is not cancelled when this expires.
USER_DEADLINE = 8
# Complete upstream failure is not stored in the 5-minute success cache.
# A short backoff avoids hammering USGS/NWS; a later retry still joins an in-flight assemble.
FAIL_BACKOFF = 45
PARTIAL_BACKOFF = 45  # NWS-only / timed-out USGS: displayable, not a 5-minute success
# Cap concurrent USGS HTTP calls so a 0.15 CPU instance is not thrashed when
# several regions assemble at once. NWS/NWPS/USACE are not under this cap.
USGS_CONCURRENCY = 4
# One immediate retry for USGS daily-stats HTTP 502/503 only (those failed in ~4s on Render).
STAT_RETRY_STATUS = frozenset({502, 503})
STAT_EXTRA_TRIES = 1

_POOL = ThreadPoolExecutor(max_workers=16)


def _pool():
    global _POOL
    if _POOL is None or getattr(_POOL, "_shutdown", False):
        _POOL = ThreadPoolExecutor(max_workers=16)
    return _POOL
_LOCK = threading.Lock()
_USGS_SEM = threading.Semaphore(USGS_CONCURRENCY)
_USGS_INFLIGHT = 0
_USGS_INFLIGHT_PEAK = 0
_KEY_FLIGHT: dict = {}  # key -> (Event, [result, error])
_FETCH_COUNTS: dict[str, int] = {}
_ASSEMBLED: dict[str, tuple[float, dict]] = {}
_REFRESHING: set = set()
_FLIGHT: dict[str, threading.Event] = {}
_FAILED: dict[str, float] = {}  # rid -> time of last complete upstream failure
_PARTIAL: dict[str, float] = {}  # rid -> time of last incomplete (USGS missing/timed out) refresh
_COMPLETE: dict[str, bool] = {}  # rid -> last cached assemble was a complete USGS refresh
_EPOCH = 0  # bumped on test reset so a late in-flight build cannot write into the next run
_FETCH = None  # optional (url, timeout=, tries=) -> (status, ctype, raw)


def flag_on() -> bool:
    """Freshwater pages are on unless FRESHWATER_ENABLED is explicitly 0, false, or off."""
    v = (os.environ.get("FRESHWATER_ENABLED") or "").strip().lower()
    return v not in ("0", "false", "off")


def regions() -> dict:
    cfg = conditions.load_regions()
    return {r["id"]: r for r in cfg.get("regions") or [] if r.get("waterType") == "freshwater"}


def is_preview_region(rid: str | None) -> bool:
    """True if this freshwater region is built but not public (cookie-gated).

    Public Falls, Jordan and Neuse stay enabled. A preview-ready region with
    enabled=false is served only to a browser holding the preview cookie, the
    same way not-yet-public saltwater dashboards are gated.
    """
    if not rid:
        return False
    r = regions().get(rid) or {}
    return bool(r.get("previewReady")) and not r.get("enabled") and not r.get("draft")


def install_fetch(fn):
    """Install a freshwater-only fetch wrapper. Called from server.py; not used by saltwater."""
    global _FETCH
    _FETCH = fn


def _source_label(url: str) -> str:
    """Short source name for logs. Never returns a URL, query string, or credential."""
    u = url or ""
    if "waterservices.usgs.gov/nwis/iv" in u:
        return "usgs_iv"
    if "waterservices.usgs.gov/nwis/stat" in u:
        return "usgs_stat"
    if "api.weather.gov/gridpoints" in u:
        return "nws_forecast"
    if "api.weather.gov/alerts" in u:
        return "nws_alerts"
    if "api.weather.gov" in u:
        return "nws"
    if "water.noaa.gov" in u or "/nwps/" in u:
        return "nwps"
    if "usace.army.mil" in u:
        return "usace"
    return "upstream"


def _log_upstream(source, duration, outcome, detail=""):
    """Log one upstream attempt. No URLs, secrets, or keys."""
    import sys
    line = "freshwater upstream %s %.3fs %s" % (source, duration, outcome)
    if detail:
        line += " %s" % detail
    sys.stderr.write(line + "\n")


def _cached_body(cached):
    """Unwrap a cache hook value into raw bytes. hooks.cache_get returns (status, ctype, body)."""
    if cached is None:
        return None
    if isinstance(cached, (bytes, bytearray)):
        return bytes(cached)
    if isinstance(cached, tuple) and len(cached) >= 3:
        status, raw = cached[0], cached[2]
        if status == 200 and raw:
            return raw if isinstance(raw, (bytes, bytearray)) else None
        return None
    return None


def _count_fetch(source, outcome):
    with _LOCK:
        _FETCH_COUNTS[source] = _FETCH_COUNTS.get(source, 0) + 1
        key = "%s:%s" % (source, outcome)
        _FETCH_COUNTS[key] = _FETCH_COUNTS.get(key, 0) + 1
        _FETCH_COUNTS["http"] = _FETCH_COUNTS.get("http", 0) + 1


def fetch_counts():
    """Snapshot of actual upstream HTTP attempts (leaders only; not cache or joined flights)."""
    with _LOCK:
        return dict(_FETCH_COUNTS), _USGS_INFLIGHT_PEAK


def _usgs_acquire():
    global _USGS_INFLIGHT, _USGS_INFLIGHT_PEAK
    _USGS_SEM.acquire()
    with _LOCK:
        _USGS_INFLIGHT += 1
        if _USGS_INFLIGHT > _USGS_INFLIGHT_PEAK:
            _USGS_INFLIGHT_PEAK = _USGS_INFLIGHT


def _usgs_release():
    global _USGS_INFLIGHT
    with _LOCK:
        _USGS_INFLIGHT = max(0, _USGS_INFLIGHT - 1)
    _USGS_SEM.release()


def _is_usgs_url(url):
    u = url or ""
    return "waterservices.usgs.gov" in u


def _is_usgs_stat_url(url):
    u = url or ""
    return "waterservices.usgs.gov" in u and "/nwis/stat" in u


def _keyed_single_flight(key, fn, wait_s=None):
    """Run fn once for key; concurrent callers share the result or error."""
    if wait_s is None:
        wait_s = FETCH_TIMEOUT + 5
    with _LOCK:
        slot = _KEY_FLIGHT.get(key)
        if slot is None:
            ev, box = threading.Event(), [None, None]
            _KEY_FLIGHT[key] = (ev, box)
            lead = True
        else:
            ev, box = slot
            lead = False
    if not lead:
        ev.wait(timeout=wait_s)
        if box[1] is not None:
            raise box[1]
        return box[0]
    try:
        box[0] = fn()
        return box[0]
    except Exception as e:
        box[1] = e
        raise
    finally:
        ev.set()
        with _LOCK:
            cur = _KEY_FLIGHT.get(key)
            if cur is not None and cur[0] is ev:
                _KEY_FLIGHT.pop(key, None)


def _get_body(url, ttl, accept="application/json"):
    """Cache then fetch. Uses the bounded freshwater fetch when installed, else conditions.get_json.

    Concurrent callers for the same URL share one in-flight request. USGS IV and
    daily-stats calls also take a concurrency slot (USGS_CONCURRENCY).
    """
    if _FETCH is None:
        def _via_conditions():
            source = _source_label(url)
            use_sem = _is_usgs_url(url)
            if use_sem:
                _usgs_acquire()
            t0 = time.time()
            try:
                body = conditions.get_json(url, ttl, accept=accept)
            except Exception as e:
                _count_fetch(source, "error")
                _log_upstream(source, time.time() - t0, "error", type(e).__name__)
                return None
            finally:
                if use_sem:
                    _usgs_release()
            _count_fetch(source, "ok" if body else "fail")
            _log_upstream(source, time.time() - t0, "ok" if body else "fail")
            return body
        return _keyed_single_flight(("get", url, ttl, accept), _via_conditions)

    hooks = conditions._hooks

    def _do():
        cg = hooks.get("cache_get")
        if cg:
            raw = _cached_body(cg(url))
            if raw is not None:
                return raw
        source = _source_label(url)
        use_sem = _is_usgs_url(url)
        attempts = 1 + (STAT_EXTRA_TRIES if _is_usgs_stat_url(url) else 0)
        status, raw, err_name = 0, None, ""
        for attempt in range(attempts):
            if use_sem:
                _usgs_acquire()
            t0 = time.time()
            try:
                status, _ct, raw = _FETCH(url, timeout=FETCH_TIMEOUT, tries=FETCH_TRIES)
            except Exception as e:
                status, raw, err_name = 0, None, type(e).__name__
                _count_fetch(source, "error")
                _log_upstream(source, time.time() - t0, "error", err_name)
            else:
                dur = time.time() - t0
                if status == 200 and raw:
                    _count_fetch(source, "ok")
                    _log_upstream(source, dur, "ok")
                else:
                    kind = "timeout" if (err_name == "TimeoutError" or (raw and b"timed out" in raw[:80])) else "fail"
                    detail = err_name or ("HTTP %s" % status)
                    if raw and not isinstance(raw, (bytes, bytearray)):
                        raw = None
                    elif raw and isinstance(raw, (bytes, bytearray)) and b"timed out" in raw[:80]:
                        kind = "timeout"
                    _count_fetch(source, kind)
                    _log_upstream(source, dur, kind, detail)
                    if kind == "timeout":
                        # A timeout is not a brief 502; do not retry it.
                        attempts = attempt + 1
            finally:
                if use_sem:
                    _usgs_release()
            if status == 200 and raw:
                break
            if not (_is_usgs_stat_url(url) and status in STAT_RETRY_STATUS and attempt + 1 < attempts):
                break
        if status == 200 and raw:
            put = hooks.get("cache_put_ttl")
            if put:
                put(url, ttl, raw)
            return raw
        anyg = hooks.get("cache_get_any")
        if anyg:
            return _cached_body(anyg(url))
        return None

    return _keyed_single_flight(("get", url, ttl, accept), _do)


def _get_json(url, ttl):
    body = _get_body(url, ttl)
    if not body:
        return None
    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None


def _get_text(url, ttl):
    body = _get_body(url, ttl, accept="*/*")
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

def _shared_corridor_sites():
    """USGS site ids that appear on both Falls (release/river) and the Neuse page."""
    regs = regions()
    falls, neuse = set(), set()
    fr = regs.get("falls-lake") or {}
    for s in list(fr.get("river") or []) + ([fr["release"]] if fr.get("release") else []):
        if s and s.get("usgs"):
            falls.add(s["usgs"])
    nr = regs.get("neuse-river") or {}
    for s in list(nr.get("river") or []) + ([nr["release"]] if nr.get("release") else []):
        if s and s.get("usgs"):
            neuse.add(s["usgs"])
    return falls & neuse


def _iv_flow_groups(sites, params, period="P1D"):
    """Split a region's flow/stage site list into reusable canonical groups.

    Falls and Neuse share the lower-Neuse corridor gauges; giving them the
    same (sites, params, period) means one in-flight IV request is reused.
    """
    shared = _shared_corridor_sites()
    sites = [s for s in sites if s]
    corridor = sorted(set(s for s in sites if s in shared))
    rest = sorted(set(s for s in sites if s not in shared))
    params = list(sorted(set(params)))
    groups = []
    if corridor:
        groups.append((corridor, params, period))
    if rest:
        groups.append((rest, params, period))
    return groups


def usgs_iv(sites, params, period="P1D"):
    """{(site, param): [(datetime, value), ...]} for the period, oldest first."""
    key = ("iv", tuple(sorted(set(sites or []))), tuple(sorted(set(params or []))), period)
    return _keyed_single_flight(key, lambda: _usgs_iv_fetch(sites, params, period),
                                wait_s=FETCH_TIMEOUT + 5)


def _usgs_iv_fetch(sites, params, period="P1D"):
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
    key = ("stat", site, str(getattr(day, "month", "")), str(getattr(day, "day", "")))
    return _keyed_single_flight(key, lambda: _usgs_daily_stats_fetch(site, day),
                                wait_s=FETCH_TIMEOUT + 5)


def _usgs_daily_stats_fetch(site, day):
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
            # Stage only: NWPS forecast flow (a rating-curve estimate) is not passed on (stage-only rule).
            out["forecast"] = {"kind": "forecast", "issued": sf.get("issuedTime"), "units": [sf.get("primaryUnits")],
                               "crestStage": crest[1], "crestTime": crest[0],
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
    d = _get_json("https://api.weather.gov/alerts/active?status=actual&point=%.4f,%.4f" % (lat, lon), 300)
    if d is None:
        return {"status": "unavailable", "items": []}
    items, seen = [], {}
    for f in d.get("features") or []:
        p = f.get("properties") or {}
        if (p.get("status") or "Actual") != "Actual":
            continue  # skip NWS test/exercise messages
        if conditions._nws_replaced(p):
            continue  # NWS marked this one replaced/cancelled; its replacement is in the feed
        # t449u: same rule as conditions.alerts_block; distinct products are never dropped.
        key = (p.get("event"), p.get("onset"), p.get("ends") or p.get("expires"))
        if key in seen:
            seen[key]["areas"] = conditions._union_areas(seen[key]["areas"], p.get("areaDesc"))
            continue
        it = {"event": p.get("event"), "severity": p.get("severity"), "areas": p.get("areaDesc"),
              "ends": p.get("ends") or p.get("expires"), "headline": p.get("headline")}
        seen[key] = it
        items.append(it)
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

def _flow_station(spec, iv, now, stats_day, stats_lookup=None):
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
    if spec.get("regulatedNote"):
        out["regulatedNote"] = spec["regulatedNote"]
    if spec.get("nwpsMinusUsgsFt") is not None:
        out["nwpsMinusUsgsFt"] = spec["nwpsMinusUsgsFt"]
    if spec.get("floodStages"):
        out["floodStages"] = dict(spec["floodStages"])
    if stage_only:
        out["stageOnly"] = True
        out["flowCfs"] = None
        out["flowNote"] = spec.get("flowNote") or "Discharge not published at this gauge. Stage only."
    if out["flowCfs"] and not out["flowCfs"]["stale"]:
        if stats_lookup is not None:
            st = stats_lookup.get(site)
        else:
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


def _wait(fut, fallback, timeout=RESULT_TIMEOUT):
    """Wait on a future with a bound. Timed-out or failed work becomes fallback, never invented data."""
    if fut is None:
        return fallback
    try:
        return fut.result(timeout=timeout)
    except Exception:
        return fallback


def _wait_from(fut, fallback, started, budget=RESULT_TIMEOUT):
    """Same bound measured from when the wave of futures was submitted, so parallel work is not stacked."""
    rem = budget - (time.time() - started)
    if rem <= 0:
        if fut is not None and getattr(fut, "done", lambda: False)():
            return _wait(fut, fallback, timeout=0.05)
        return fallback
    return _wait(fut, fallback, timeout=rem)


def empty_payload(rid):
    """Honest unavailable shell for a region. No numerals, no substitute readings. Not cached."""
    r = regions().get(rid) or {"id": rid, "name": rid}
    inst = r.get("instrumentSet")
    lake_out = None
    if inst == "freshwater-lake" and r.get("lake"):
        lake = r["lake"]
        lake_out = {"kind": "observed", "usgs": lake.get("usgs"), "elevation": None,
                    "guideCurveFt": lake.get("guideCurveFt"), "datum": "NGVD29"}
    rel = None
    if r.get("release"):
        rel = {"usgs": r["release"].get("usgs"), "label": r["release"].get("label"),
               "tileTitle": r["release"].get("tileTitle"), "kind": "observed",
               "flowCfs": None, "stageFt": None}
    inflows = [{"usgs": s.get("usgs"), "label": s.get("label"), "kind": "observed",
                "flowCfs": None, "stageFt": None} for s in (r.get("inflows") or [])]
    river = []
    for s in (r.get("river") or []):
        block = {"usgs": s.get("usgs"), "label": s.get("label"), "kind": "observed",
                 "flowCfs": None, "stageFt": None}
        if s.get("flow") is False:
            block["stageOnly"] = True
            block["flowNote"] = s.get("flowNote") or "Discharge not published at this gauge. Stage only."
        river.append(block)
    rain = {"status": "unavailable"} if (r.get("lake") or {}).get("rain") else None
    return {"ok": True, "generatedAt": None, "partial": True,
            "region": {k: r.get(k) for k in ("id", "name", "area", "anchor", "waterType", "instrumentSet")},
            "lake": lake_out,
            "waterTemp": {"kind": "observed", "status": "unavailable", "c": None, "f": None},
            "rain": rain, "release": rel, "inflows": inflows, "river": river,
            "forecast": {"status": "unavailable"},
            "alerts": {"status": "unavailable", "items": []},
            "links": r.get("links") or [], "staleRuleH": STALE_H}


def _point_ok(pt):
    return isinstance(pt, dict) and pt.get("value") is not None


def _iso(pt):
    if isinstance(pt, dict):
        return pt.get("time") or ""
    return ""


def _newer_point(new, old):
    """True when new is a verified point that should replace old (not older than the one we have)."""
    if not _point_ok(new):
        return False
    if not _point_ok(old):
        return True
    nt, ot = _iso(new), _iso(old)
    if not nt or not ot:
        return True
    return nt >= ot


def has_verified_data(payload) -> bool:
    """True if at least one official source returned a usable result. Never treats empty as success."""
    if not payload:
        return False
    lake = payload.get("lake") or {}
    if _point_ok(lake.get("elevation")) or _point_ok(lake.get("navd88")):
        return True
    wt = payload.get("waterTemp") or {}
    if wt.get("status") == "ok" and wt.get("f") is not None:
        return True
    rain = payload.get("rain") or {}
    if rain.get("status") == "ok" and rain.get("last24In") is not None:
        return True
    for block in [payload.get("release")] + list(payload.get("inflows") or []) + list(payload.get("river") or []):
        if not block:
            continue
        if _point_ok(block.get("flowCfs")) or _point_ok(block.get("stageFt")):
            return True
    fc = payload.get("forecast") or {}
    if fc.get("status") == "ok" and (fc.get("periods") or []):
        return True
    al = payload.get("alerts") or {}
    if al.get("status") == "ok":
        return True
    return False


def has_verified_usgs(payload) -> bool:
    """True if at least one official USGS observation is present. NWS-only is not USGS success."""
    if not payload:
        return False
    lake = payload.get("lake") or {}
    if _point_ok(lake.get("elevation")) or _point_ok(lake.get("navd88")):
        return True
    wt = payload.get("waterTemp") or {}
    if wt.get("status") == "ok" and wt.get("f") is not None:
        return True
    rain = payload.get("rain") or {}
    if rain.get("status") == "ok" and rain.get("last24In") is not None:
        return True
    for block in [payload.get("release")] + list(payload.get("inflows") or []) + list(payload.get("river") or []):
        if not block:
            continue
        if _point_ok(block.get("flowCfs")) or _point_ok(block.get("stageFt")):
            return True
    return False


def missing_expected_usgs(payload) -> bool:
    """True when a configured USGS source did not return a usable result."""
    rid = (payload.get("region") or {}).get("id")
    r = regions().get(rid) or {}
    if r.get("lake"):
        if not _point_ok((payload.get("lake") or {}).get("elevation")):
            return True
        if r["lake"].get("waterTemp"):
            wt = payload.get("waterTemp") or {}
            if wt.get("status") != "ok" or wt.get("f") is None:
                return True
        if r["lake"].get("rain"):
            rain = payload.get("rain") or {}
            if rain.get("status") != "ok" or rain.get("last24In") is None:
                return True
        if r.get("release"):
            rel = payload.get("release") or {}
            if not _point_ok(rel.get("flowCfs")) and not _point_ok(rel.get("stageFt")):
                return True
        got_in = {s.get("usgs"): s for s in (payload.get("inflows") or []) if s}
        for spec in r.get("inflows") or []:
            block = got_in.get(spec.get("usgs")) or {}
            if not _point_ok(block.get("flowCfs")) and not _point_ok(block.get("stageFt")):
                return True
    got_rv = {s.get("usgs"): s for s in (payload.get("river") or []) if s}
    for spec in r.get("river") or []:
        block = got_rv.get(spec.get("usgs")) or {}
        if spec.get("flow") is False:
            if not _point_ok(block.get("stageFt")):
                return True
        elif not _point_ok(block.get("flowCfs")) and not _point_ok(block.get("stageFt")):
            return True
    return False


def usgs_refresh_complete(payload) -> bool:
    """True when every configured USGS source in this payload returned a usable result."""
    return bool(payload) and not missing_expected_usgs(payload)


def missing_expected(payload) -> bool:
    """True when a configured official source did not return a usable result (retry is appropriate)."""
    rid = (payload.get("region") or {}).get("id")
    r = regions().get(rid) or {}
    if r.get("lake"):
        if not _point_ok((payload.get("lake") or {}).get("elevation")):
            return True
        if r["lake"].get("waterTemp"):
            wt = payload.get("waterTemp") or {}
            if wt.get("status") != "ok" or wt.get("f") is None:
                return True
        if r["lake"].get("rain"):
            rain = payload.get("rain") or {}
            if rain.get("status") != "ok" or rain.get("last24In") is None:
                return True
        if r.get("release"):
            rel = payload.get("release") or {}
            if not _point_ok(rel.get("flowCfs")) and not _point_ok(rel.get("stageFt")):
                return True
        got_in = {s.get("usgs"): s for s in (payload.get("inflows") or []) if s}
        for spec in r.get("inflows") or []:
            block = got_in.get(spec.get("usgs")) or {}
            if not _point_ok(block.get("flowCfs")) and not _point_ok(block.get("stageFt")):
                return True
    got_rv = {s.get("usgs"): s for s in (payload.get("river") or []) if s}
    for spec in r.get("river") or []:
        block = got_rv.get(spec.get("usgs")) or {}
        if spec.get("flow") is False:
            if not _point_ok(block.get("stageFt")):
                return True
        elif not _point_ok(block.get("flowCfs")) and not _point_ok(block.get("stageFt")):
            return True
    if r.get("forecast"):
        fc = payload.get("forecast") or {}
        if fc.get("status") != "ok" or not (fc.get("periods") or []):
            return True
    al = payload.get("alerts") or {}
    if al.get("status") != "ok":
        return True
    return False


def _merge_station(old, new):
    if not old:
        return new
    if not new:
        return old
    out = dict(new)
    if not _newer_point(new.get("flowCfs"), old.get("flowCfs")) and _point_ok(old.get("flowCfs")):
        out["flowCfs"] = old["flowCfs"]
        for k in ("stats", "band"):
            if k in old:
                out[k] = old[k]
    if not _newer_point(new.get("stageFt"), old.get("stageFt")) and _point_ok(old.get("stageFt")):
        out["stageFt"] = old["stageFt"]
    return out


def _merge_block(old, new, ok):
    if ok(old) and not ok(new):
        return old
    return new if new is not None else old


def _qpf_ok(w):
    q = (w or {}).get("qpf") or {}
    return q.get("status") == "ok" and q.get("next24In") is not None


def _merge_rain(old, new):
    """Merge 24h rain and the NWS QPF subfield independently.

    A verified QPF is kept when last24In is missing, and a new official 24h
    total does not drop a previously verified QPF if the new block omitted it.
    """
    if not old:
        return new
    if not new:
        return old
    new_obs = new.get("status") == "ok" and new.get("last24In") is not None
    old_obs = old.get("status") == "ok" and old.get("last24In") is not None
    if new_obs:
        out = dict(new)
    elif old_obs:
        out = dict(old)
    else:
        out = dict(new)
    if _qpf_ok(new):
        out["qpf"] = new["qpf"]
    elif _qpf_ok(old):
        out["qpf"] = old["qpf"]
    return out


def merge_verified(old, new):
    """Keep previously verified official readings when a later fetch is missing or older.

    Never introduces numerals that were not in either official payload. Does not
    replace a valid reading with an unavailable placeholder, and does not replace
    a newer official timestamp with an older one. Alerts: a failed re-check never
    drops official warnings we already have; a successful re-check (including
    'no alerts') replaces the previous official set.
    """
    if not old:
        return new
    if not new:
        return old
    out = dict(new)
    old_lake, new_lake = old.get("lake") or {}, new.get("lake") or {}
    if old_lake or new_lake:
        lake = dict(new_lake or old_lake)
        take_new_el = _newer_point(new_lake.get("elevation"), old_lake.get("elevation"))
        if not take_new_el and _point_ok(old_lake.get("elevation")):
            for k in ("elevation", "navd88", "vsGuideFt", "change24hFt", "change7dFt",
                      "series7d", "datumOffsetFt"):
                if k in old_lake:
                    lake[k] = old_lake[k]
        out["lake"] = lake

    def wt_ok(w):
        w = w or {}
        return w.get("status") == "ok" and w.get("f") is not None

    def fc_ok(w):
        w = w or {}
        return w.get("status") == "ok" and bool(w.get("periods"))

    def al_ok(w):
        return (w or {}).get("status") == "ok"

    out["waterTemp"] = _merge_block(old.get("waterTemp"), new.get("waterTemp"), wt_ok)
    if old.get("rain") or new.get("rain"):
        out["rain"] = _merge_rain(old.get("rain"), new.get("rain"))
    if old.get("release") or new.get("release"):
        out["release"] = _merge_station(old.get("release"), new.get("release"))
    old_in = {s.get("usgs"): s for s in (old.get("inflows") or []) if s}
    new_in = list(new.get("inflows") or [])
    if new_in or old_in:
        merged_in = []
        seen = set()
        for block in new_in:
            uid = block.get("usgs")
            merged_in.append(_merge_station(old_in.get(uid), block))
            seen.add(uid)
        for uid, block in old_in.items():
            if uid not in seen:
                merged_in.append(block)
        out["inflows"] = merged_in
    old_rv = {s.get("usgs"): s for s in (old.get("river") or []) if s}
    new_rv = list(new.get("river") or [])
    if new_rv or old_rv:
        merged_rv = []
        seen = set()
        for block in new_rv:
            uid = block.get("usgs")
            merged_rv.append(_merge_station(old_rv.get(uid), block))
            seen.add(uid)
        for uid, block in old_rv.items():
            if uid not in seen:
                merged_rv.append(block)
        out["river"] = merged_rv
    out["forecast"] = _merge_block(old.get("forecast"), new.get("forecast"), fc_ok)
    out["alerts"] = _merge_block(old.get("alerts"), new.get("alerts"), al_ok)
    if old.get("guideCheck") and (new.get("guideCheck") or {}).get("status") != "ok":
        out["guideCheck"] = old["guideCheck"]
    return out


def backoff_remaining(rid) -> float:
    now = time.time()
    left = 0.0
    with _LOCK:
        fail = _FAILED.get(rid)
        part = _PARTIAL.get(rid)
    if fail is not None:
        left = max(left, FAIL_BACKOFF - (now - fail))
    if part is not None:
        left = max(left, PARTIAL_BACKOFF - (now - part))
    return left if left > 0 else 0.0


def _is_complete(rid) -> bool:
    """True when the cached payload was a complete USGS refresh, or was seeded without a flag."""
    with _LOCK:
        if rid in _COMPLETE:
            return bool(_COMPLETE[rid])
        return rid in _ASSEMBLED


def reset_caches():
    """Drop assembled cache, failure backoff, and in-flight bookkeeping.

    Increments _EPOCH so a build that started before the reset cannot write
    a payload into the next caller's cache.
    """
    global _EPOCH
    global _USGS_INFLIGHT, _USGS_INFLIGHT_PEAK
    with _LOCK:
        _EPOCH += 1
        evs = list(_FLIGHT.values())
        key_evs = [slot[0] for slot in _KEY_FLIGHT.values()]
        _ASSEMBLED.clear()
        _FAILED.clear()
        _PARTIAL.clear()
        _COMPLETE.clear()
        _FLIGHT.clear()
        _REFRESHING.clear()
        _KEY_FLIGHT.clear()
        _FETCH_COUNTS.clear()
        _USGS_INFLIGHT = 0
        _USGS_INFLIGHT_PEAK = 0
    for ev in evs:
        ev.set()
    for ev in key_evs:
        ev.set()


def peek_age(rid):
    """Return (payload, age_s) when a cached assemble is still servable, else (None, age or None)."""
    with _LOCK:
        hit = _ASSEMBLED.get(rid)
    if not hit:
        return None, None
    age = time.time() - hit[0]
    if age < ASSEMBLED_SERVE_MAX:
        return hit[1], age
    return None, age


def peek(rid):
    payload, _age = peek_age(rid)
    return payload


def _begin_flight(rid):
    with _LOCK:
        ev = _FLIGHT.get(rid)
        if ev is not None:
            return ev, False
        ev = threading.Event()
        _FLIGHT[rid] = ev
        _REFRESHING.add(rid)
        return ev, True


def _end_flight(rid, ev):
    with _LOCK:
        if _FLIGHT.get(rid) is ev:
            _FLIGHT.pop(rid, None)
        _REFRESHING.discard(rid)
    ev.set()


def _in_flight(rid) -> bool:
    with _LOCK:
        return rid in _FLIGHT


def _view(rid, body):
    """Copy of a payload with pending/complete flags for callers. Does not mutate the cache."""
    out = dict(body or {})
    out["complete"] = _is_complete(rid) and bool(body)
    out["pending"] = _in_flight(rid)
    left = backoff_remaining(rid)
    if left > 0 and not out.get("retryAfterS"):
        out["retryAfterS"] = int(left + 0.999)
    return out


def ensure_refresh(rid):
    """Start or join a single in-flight assemble for this region. Returns the Event.

    A complete upstream failure starts a short backoff: a later caller joins an
    in-flight assemble if one exists, otherwise it does not start a new fetch.
    """
    ev, lead = _begin_flight(rid)
    if not lead:
        return ev
    if backoff_remaining(rid) > 0:
        _end_flight(rid, ev)
        return ev

    def run():
        try:
            _assemble_build(rid)
        except Exception as e:  # never let a refresh crash the server
            import sys
            sys.stderr.write("freshwater refresh %s failed: %s\n" % (rid, type(e).__name__))
        finally:
            _end_flight(rid, ev)

    threading.Thread(target=run, daemon=True, name="fw-refresh-%s" % rid).start()
    return ev

def assemble(rid, force=False, wait=USER_DEADLINE):
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
    if not force:
        hit, age = peek_age(rid)
        complete = _is_complete(rid)
        if hit is not None and complete and age is not None and age < ASSEMBLED_TTL:
            return 200, _view(rid, hit)
        if hit is not None and complete and age is not None and age < ASSEMBLED_SERVE_MAX:
            if backoff_remaining(rid) <= 0:
                ensure_refresh(rid)
            return 200, _view(rid, hit)
        if hit is not None and not complete:
            if backoff_remaining(rid) <= 0:
                ev = ensure_refresh(rid)
                if wait:
                    ev.wait(timeout=wait)
                    hit, _age = peek_age(rid)
            return 200, _view(rid, hit or empty_payload(rid))
        if backoff_remaining(rid) > 0:
            body = empty_payload(rid)
            return 200, _view(rid, body)
    elif backoff_remaining(rid) > 0:
        # Retry during backoff: do not start a new upstream attempt unless one is already in flight.
        ev = _FLIGHT.get(rid)
        if ev is not None:
            ev.wait(timeout=None if wait is None else wait)
            hit, _age = peek_age(rid)
            if hit is not None:
                return 200, _view(rid, hit)
        hit, _age = peek_age(rid)
        return 200, _view(rid, hit or empty_payload(rid))
    ev = ensure_refresh(rid)
    ev.wait(timeout=None if wait is None else wait)
    hit, _age = peek_age(rid)
    if hit is not None:
        return 200, _view(rid, hit)
    return 200, _view(rid, empty_payload(rid))


def _stats_sites(specs, iv, now):
    sites = []
    for spec in specs:
        if not spec or spec.get("flow") is False:
            continue
        q = latest(iv.get((spec["usgs"], "00060")), now)
        if q and not q["stale"]:
            if spec["usgs"] not in sites:
                sites.append(spec["usgs"])
    return sites


def _apply_stats(payload, stats_lookup):
    """Attach daily-stats / flow bands to stations already in payload. Never changes timestamps."""
    if not payload or not stats_lookup:
        return payload
    for block in [payload.get("release")] + list(payload.get("inflows") or []) + list(payload.get("river") or []):
        if not block:
            continue
        q = block.get("flowCfs")
        if not q or q.get("stale") or q.get("value") is None:
            continue
        st = stats_lookup.get(block.get("usgs"))
        if not st:
            continue
        block["stats"] = st
        block["band"] = flow_band(q["value"], st)
    return payload


def _assemble_build(rid):
    """Build and cache one region's payload. Per-source waits are bounded; nothing is invented."""
    with _LOCK:
        epoch = _EPOCH
    r = regions()[rid]
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
        f_iv7 = _pool().submit(usgs_iv, [lake["usgs"]], lake_params, "P7D")
    wt_cfg = r.get("waterTemp") or {}
    wt_sites = [s for s in (wt_cfg.get("sites") or []) if s]
    iv_params = ["00060", "00065"]
    if wt_sites:
        iv_params.append("00010")
    # Lake P7D already covers the dam site; flow/stage groups exclude it so the
    # shared lower-Neuse corridor can be a single in-flight request for Falls and Neuse.
    flow_sites = [s for s in sites if not (lake and s == lake["usgs"])]
    f_ivq_parts = [_pool().submit(usgs_iv, gs, gp, gper)
                   for gs, gp, gper in _iv_flow_groups(flow_sites, iv_params, "P1D")]
    f_fc = _pool().submit(conditions.forecast_block, r["forecast"]) if r.get("forecast") else None
    f_qpf = _pool().submit(qpf_block, r["forecast"], now) if lake and r.get("forecast") else None
    alert_pt = r.get("alertPoint") or [r["anchor"]["lat"], r["anchor"]["lon"]]
    f_al = _pool().submit(alerts_point, *alert_pt)
    f_guide = _pool().submit(usace_guide_check, lake["guideCurveFt"]) if lake and lake.get("guideCurveFt") is not None else None
    lids = [s["nwps"] for s in river + ([rel] if rel else []) if s.get("nwps")]
    if lake and lake.get("nwps"):
        lids.append(lake["nwps"])
    f_nwps = {lid: _pool().submit(nwps, lid) for lid in lids}

    wave0 = time.time()
    names = {}
    iv7 = {}
    if f_iv7 is not None:
        got = _wait_from(f_iv7, ({}, {}), wave0)
        if isinstance(got, tuple) and len(got) == 2:
            iv7, names = got
    ivq = {}
    for fut in f_ivq_parts:
        got = _wait_from(fut, ({}, {}), wave0)
        if isinstance(got, tuple) and len(got) == 2:
            part, names2 = got
            ivq.update(part or {})
            names.update(names2 or {})

    # Daily-stats are non-critical percentiles. Submit them now but do not block
    # publishing official IV readings on their completion.
    need = _stats_sites(river + inflows + ([rel] if rel else []), ivq, now)
    f_stats = {site: _pool().submit(usgs_daily_stats, site, et_today) for site in need}
    stats_started = time.time()
    stats_lookup = {}
    for site, fut in f_stats.items():
        if fut.done():
            stats_lookup[site] = _wait(fut, None, timeout=0.05)

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
            rain["qpf"] = _wait_from(f_qpf, {"status": "unavailable", "kind": "forecast"}, wave0)

    nw = {lid: _wait_from(f, {"lid": lid, "status": "unavailable"}, wave0) for lid, f in f_nwps.items()}
    release = _attach_nwps(rel, _flow_station(rel, ivq, now, et_today, stats_lookup), nw) if rel else None
    river_out = [_attach_nwps(s, _flow_station(s, ivq, now, et_today, stats_lookup), nw) for s in river]
    inflow_out = [_flow_station(s, ivq, now, et_today, stats_lookup) for s in inflows]
    if wt_sites and lake_out is None:
        # River pages: only show a water temperature if a current USGS 00010 exists.
        # A discontinued or stale series (Lillington 00010 ended in 2024) is not used.
        best = None
        for site in wt_sites:
            pt = latest(ivq.get((site, "00010")), now)
            if not pt:
                continue
            if best is None or pt["time"] > best["time"]:
                best = dict(pt)
                best["usgs"] = site
        if best:
            water = {"kind": "observed", "usgs": best["usgs"], "status": "ok",
                     "c": best["value"], "f": round(best["value"] * 9 / 5 + 32, 1),
                     "time": best["time"], "stale": best["stale"],
                     "note": "USGS parameter 00010 at %s, provisional. Surface temperatures elsewhere on the river can differ." % best["usgs"]}
    if lake_out is not None and lake:
        lake_out = _attach_nwps(lake, lake_out, nw)

    fresh = {"ok": True, "generatedAt": now.isoformat(),
               "region": {k: r.get(k) for k in ("id", "name", "area", "anchor", "waterType", "instrumentSet")},
               "lake": lake_out, "waterTemp": water, "rain": rain, "release": release,
               "inflows": inflow_out, "river": river_out,
               "forecast": _wait_from(f_fc, {"status": "unavailable"}, wave0) if f_fc is not None else {"status": "unavailable"},
               "alerts": _wait_from(f_al, {"status": "unavailable", "items": []}, wave0),
               "guideCheck": _wait_from(f_guide, {"status": "unavailable"}, wave0) if f_guide is not None else None,
               "links": r.get("links") or [], "staleRuleH": STALE_H}
    old, old_age = peek_age(rid)
    payload = merge_verified(old, fresh) if old else fresh
    usgs_ok = usgs_refresh_complete(fresh)
    own = has_verified_data(fresh)
    with _LOCK:
        if epoch != _EPOCH:
            return 200, payload
        if usgs_ok:
            # A complete official USGS refresh earns the 5-minute success TTL.
            _ASSEMBLED[rid] = (time.time(), payload)
            _COMPLETE[rid] = True
            _FAILED.pop(rid, None)
            _PARTIAL.pop(rid, None)
        elif own or old:
            # NWS-only or partial USGS: show what we have, keep previously
            # verified observations with their original timestamps, but do not
            # treat this as a 5-minute success. Short backoff before the next
            # full upstream attempt.
            prev = _ASSEMBLED.get(rid)
            if prev:
                # Keep the original cache stamp so we do not relabel older
                # observations as a fresh successful refresh.
                _ASSEMBLED[rid] = (prev[0], payload)
            else:
                _ASSEMBLED[rid] = (time.time(), payload)
            # A partial or NWS-only refresh does not earn a 5-minute success stamp.
            _COMPLETE[rid] = False
            _PARTIAL[rid] = time.time()
            _FAILED.pop(rid, None)
        else:
            # Complete failure: do not write a 5-minute success cache. Keep any
            # previously verified payload and its original timestamp.
            _FAILED[rid] = time.time()
            _PARTIAL.pop(rid, None)
    # Official IV (and NWS) are already published. Attach daily-stats if they
    # arrive, without restamping generatedAt or observation times.
    if f_stats:
        more = {}
        for site, fut in f_stats.items():
            if stats_lookup.get(site):
                continue
            rem = (FETCH_TIMEOUT + 2) - (time.time() - stats_started)
            got = _wait(fut, None, timeout=max(0.05, rem))
            if got:
                more[site] = got
        if more:
            with _LOCK:
                if epoch == _EPOCH:
                    hit = _ASSEMBLED.get(rid)
                    target = hit[1] if hit else payload
                    _apply_stats(target, more)
                    if target is not payload:
                        _apply_stats(payload, more)
    return 200, payload


def _refresh(rid):
    ev = ensure_refresh(rid)
    ev.wait()


def warm_ids() -> list:
    """Regions worth keeping warm: public ones, plus the preview-only ones."""
    out = []
    for rid, r in regions().items():
        if r.get("previewReady") and not r.get("draft"):
            out.append(rid)
    return out


def start_warmer():
    """Keep every freshwater page assembled in the background so the Freshwater tab opens instantly."""
    def loop():
        while True:
            for rid in warm_ids():
                hit, age = peek_age(rid)
                if hit is not None and _is_complete(rid) and age is not None and age < ASSEMBLED_TTL:
                    continue
                if backoff_remaining(rid) > 0:
                    continue
                ev = ensure_refresh(rid)
                ev.wait()
            time.sleep(WARM_EVERY)
    threading.Thread(target=loop, name="freshwater-warmer", daemon=True).start()
