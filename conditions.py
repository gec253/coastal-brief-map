"""Live 'Conditions at a glance' data for the Coastal Brief dashboard.

Reads data/regions.json, fetches each reading from its own station (NDBC,
NOAA CO-OPS, NWS), converts units, and reports the station, source, and
observation time with every value. Nothing is filled in or estimated: a
missing or old report comes back as unavailable or stale with its time.

Standard library only. Uses the server's disk cache helpers.
"""
from __future__ import annotations

import json
import math
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
ROOT = Path(__file__).resolve().parent
REGIONS_PATH = ROOT / "data" / "regions.json"
APP = "CoastalBrief"

# Upstream cache lifetimes, seconds.
TTL_OBS = 6 * 60
TTL_NDBC = 8 * 60
TTL_FORECAST = 30 * 60
TTL_MARINE = 30 * 60
TTL_ALERTS = 5 * 60
TTL_TIDES = 6 * 60 * 60
ASSEMBLED_TTL = 90

# When a reading counts as stale (shown dimmed, with its time) and when it is
# too old to show at all (shown as unavailable, with the last report time).
STALE_MIN = {
    "wind": 75, "harborWind": 45, "seas": 120, "swell": 120,
    "waterTemp": 90, "waterTempOffshore": 180, "airTemp": 90, "pressure": 90,
}
MAX_AGE_H = 12

COMPASS16 = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
             "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]

MS_TO_KT = 1.0 / 0.514444
M_TO_FT = 3.28084
HPA_TO_INHG = 0.0295300
MPH_TO_KT = 0.868976

_ASM_LOCK = threading.Lock()
_ASSEMBLED: dict[str, tuple[float, dict]] = {}
_POOL = ThreadPoolExecutor(max_workers=8)

# Hooks set by server.py so this module shares its cache and fetcher.
_hooks = {"cache_get": None, "cache_get_any": None, "cache_put_ttl": None, "fetch": None}


def install(cache_get, cache_get_any, cache_put_ttl, fetch):
    _hooks.update(cache_get=cache_get, cache_get_any=cache_get_any, cache_put_ttl=cache_put_ttl, fetch=fetch)


# ---------- helpers ----------

def compass(deg):
    if deg is None:
        return None
    return COMPASS16[int((float(deg) % 360) / 22.5 + 0.5) % 16]


def c_to_f(c):
    return c * 9.0 / 5.0 + 32.0


def r1(v):
    return None if v is None else round(v + 0.0, 1)


def iso(dt):
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z") if dt else None


def miles_bearing(lat1, lon1, lat2, lon2):
    R = 3958.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    dist = 2 * R * math.asin(math.sqrt(a))
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    brg = (math.degrees(math.atan2(y, x)) + 360) % 360
    return dist, brg


def load_regions() -> dict:
    try:
        return json.loads(REGIONS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"regions": [], "stations": {}}


def public_regions() -> dict:
    cfg = load_regions()
    out = []
    for r in cfg.get("regions") or []:
        if not r.get("enabled"):
            continue
        out.append({"id": r["id"], "name": r["name"], "area": r.get("area"), "map": r.get("map")})
    return {"ok": True, "default": cfg.get("default"), "regions": out}


def get_json(url: str, ttl: int, accept: str = "application/json"):
    """Cached GET. Falls back to the last cached copy if the upstream fails,
    which is safe because every reading keeps its own observation time."""
    body = None
    cached = _hooks["cache_get"](url)
    if cached and cached[0] == 200:
        body = cached[2]
    else:
        status, _ct, raw = _hooks["fetch"](url)
        if status == 200 and raw:
            _hooks["cache_put_ttl"](url, ttl, raw)
            body = raw
        else:
            old = _hooks["cache_get_any"](url)
            if old:
                body = old[2]
    return body


# ---------- NDBC ----------

def ndbc_rows(station_id: str, ext: str = "txt"):
    url = "https://www.ndbc.noaa.gov/data/realtime2/%s.%s" % (station_id.upper(), ext)
    body = get_json(url, TTL_NDBC)
    if not body:
        return None, url
    try:
        text = body.decode("utf-8", "replace")
    except Exception:
        return None, url
    lines = text.splitlines()
    if not lines or not lines[0].startswith("#"):
        return None, url
    head = lines[0].lstrip("#").split()
    rows = []
    for ln in lines[2:200]:
        parts = ln.split()
        if len(parts) != len(head):
            continue
        rec = dict(zip(head, parts))
        try:
            dt = datetime(int(rec["YY"]), int(rec["MM"]), int(rec["DD"]), int(rec["hh"]), int(rec["mm"]), tzinfo=timezone.utc)
        except (KeyError, ValueError):
            continue
        rec["_dt"] = dt
        rows.append(rec)
    return rows, url


def num(rec, key):
    v = rec.get(key)
    if v is None or v == "MM":
        return None
    try:
        return float(v)
    except ValueError:
        return None


def first_row(rows, key):
    for rec in rows or []:
        if num(rec, key) is not None:
            return rec
    return None


def ndbc_reading(kind: str, sid: str):
    if kind == "swell":
        rows, url = ndbc_rows(sid, "spec")
        rec = None
        for r in rows or []:
            if num(r, "SwH") is not None:
                rec = r
                break
        if not rec:
            return None
        swh, swp = num(rec, "SwH"), num(rec, "SwP")
        wwh, wwp = num(rec, "WWH"), num(rec, "WWP")
        swd = rec.get("SwD") if rec.get("SwD") not in (None, "MM", "N/A") else None
        wwd = rec.get("WWD") if rec.get("WWD") not in (None, "MM", "N/A") else None
        return {
            "time": rec["_dt"], "url": url,
            "values": {
                "heightFt": r1(swh * M_TO_FT) if swh is not None else None,
                "periodS": r1(swp), "dirCompass": swd,
                "windWaveFt": r1(wwh * M_TO_FT) if wwh is not None else None,
                "windWavePeriodS": r1(wwp), "windWaveDirCompass": wwd,
                "steepness": rec.get("STEEPNESS") if rec.get("STEEPNESS") not in ("MM", "N/A") else None,
            },
            "raw": {"SwH_m": swh, "SwP_s": swp, "SwD": swd, "WWH_m": wwh, "WWP_s": wwp, "WWD": wwd},
            "rawUnits": "meters, seconds; direction is NDBC's 16-point compass",
        }
    rows, url = ndbc_rows(sid, "txt")
    if not rows:
        return None
    if kind == "wind":
        rec = first_row(rows, "WSPD")
        if not rec:
            return None
        w, g, d = num(rec, "WSPD"), num(rec, "GST"), num(rec, "WDIR")
        return {
            "time": rec["_dt"], "url": url,
            "values": {"speedKt": r1(w * MS_TO_KT), "gustKt": r1(g * MS_TO_KT) if g is not None else None,
                       "dirDeg": d, "dirCompass": compass(d)},
            "raw": {"WSPD_ms": w, "GST_ms": g, "WDIR_degT": d},
            "rawUnits": "m/s, degrees true (direction the wind comes from)",
        }
    if kind == "seas":
        rec = first_row(rows, "WVHT")
        if not rec:
            return None
        h, dpd, apd, mwd = num(rec, "WVHT"), num(rec, "DPD"), num(rec, "APD"), num(rec, "MWD")
        return {
            "time": rec["_dt"], "url": url,
            "values": {"heightFt": r1(h * M_TO_FT), "dominantPeriodS": dpd, "averagePeriodS": apd,
                       "meanDirDeg": mwd, "meanDirCompass": compass(mwd)},
            "raw": {"WVHT_m": h, "DPD_s": dpd, "APD_s": apd, "MWD_degT": mwd},
            "rawUnits": "meters, seconds, degrees true (direction waves come from)",
        }
    if kind in ("waterTemp", "waterTempOffshore"):
        rec = first_row(rows, "WTMP")
        if not rec:
            return None
        c = num(rec, "WTMP")
        return {"time": rec["_dt"], "url": url, "values": {"f": r1(c_to_f(c)), "c": c},
                "raw": {"WTMP_C": c}, "rawUnits": "degrees Celsius"}
    if kind == "airTemp":
        rec = first_row(rows, "ATMP")
        if not rec:
            return None
        c = num(rec, "ATMP")
        return {"time": rec["_dt"], "url": url, "values": {"f": r1(c_to_f(c)), "c": c},
                "raw": {"ATMP_C": c}, "rawUnits": "degrees Celsius"}
    if kind == "pressure":
        rec = first_row(rows, "PRES")
        if not rec:
            return None
        p = num(rec, "PRES")
        # PTDY is NDBC's own 3-hour tendency. Use it only if reported within an hour of the reading.
        ptdy = None
        for r in rows:
            if num(r, "PTDY") is not None and abs((rec["_dt"] - r["_dt"]).total_seconds()) <= 3600:
                ptdy = num(r, "PTDY")
                break
        return {"time": rec["_dt"], "url": url,
                "values": pressure_values(p, ptdy, "NDBC 3-hour tendency (PTDY)"),
                "raw": {"PRES_hPa": p, "PTDY_hPa": ptdy}, "rawUnits": "hPa"}
    return None


def pressure_values(hpa, change3h, basis):
    trend = None
    if change3h is not None:
        if change3h >= 1.0:
            trend = "rising"
        elif change3h <= -1.0:
            trend = "falling"
        else:
            trend = "steady"
    return {"inHg": round(hpa * HPA_TO_INHG, 2), "hPa": hpa,
            "change3hHPa": change3h, "change3hInHg": round(change3h * HPA_TO_INHG, 2) if change3h is not None else None,
            "trend": trend, "trendBasis": basis if change3h is not None else None}


# ---------- CO-OPS ----------

def coops_url(station, product, extra):
    return ("https://api.tidesandcurrents.noaa.gov/api/prod/datagetter?product=%s&application=%s"
            "&station=%s&time_zone=gmt&units=english&format=json&%s" % (product, APP, station, extra))


def coops_data(station, product, extra="date=latest"):
    url = coops_url(station, product, extra)
    body = get_json(url, TTL_OBS)
    if not body:
        return None, url
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, url
    return payload.get("data") or None, url


def coops_time(t):
    try:
        return datetime.strptime(t, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def fnum(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def coops_reading(kind, sid):
    page = "https://tidesandcurrents.noaa.gov/stationhome.html?id=%s" % sid
    if kind in ("wind", "harborWind"):
        data, url = coops_data(sid, "wind")
        if not data:
            return None
        row = data[-1]
        s, g, d = fnum(row.get("s")), fnum(row.get("g")), fnum(row.get("d"))
        if s is None:
            return None
        return {"time": coops_time(row.get("t")), "url": url, "page": page,
                "values": {"speedKt": r1(s), "gustKt": r1(g), "dirDeg": d, "dirCompass": compass(d) if d is not None else None},
                "raw": {"s_kt": s, "g_kt": g, "d_degT": d}, "rawUnits": "knots, degrees true (CO-OPS English units)"}
    if kind in ("waterTemp", "waterTempOffshore", "airTemp"):
        prod = "air_temperature" if kind == "airTemp" else "water_temperature"
        data, url = coops_data(sid, prod)
        if not data:
            return None
        row = data[-1]
        f = fnum(row.get("v"))
        if f is None:
            return None
        return {"time": coops_time(row.get("t")), "url": url, "page": page,
                "values": {"f": r1(f), "c": r1((f - 32) * 5 / 9)}, "raw": {"v_F": f},
                "rawUnits": "degrees Fahrenheit (CO-OPS English units)"}
    if kind == "pressure":
        data, url = coops_data(sid, "air_pressure", "range=4")
        if not data:
            return None
        pts = [(coops_time(r.get("t")), fnum(r.get("v"))) for r in data]
        pts = [p for p in pts if p[0] and p[1] is not None]
        if not pts:
            return None
        t_last, p_last = pts[-1]
        change = None
        target = t_last - timedelta(hours=3)
        best = None
        for t, v in pts:
            if abs((t - target).total_seconds()) <= 15 * 60:
                if best is None or abs((t - target).total_seconds()) < abs((best[0] - target).total_seconds()):
                    best = (t, v)
        if best:
            change = round(p_last - best[1], 1)
        return {"time": t_last, "url": url, "page": page,
                "values": pressure_values(p_last, change, "Change over the last 3 hours at this station"),
                "raw": {"v_mb": p_last, "v_mb_3h_ago": best[1] if best else None}, "rawUnits": "millibars (hPa)"}
    return None


# ---------- NWS observations ----------

def nws_reading(kind, sid):
    if kind != "airTemp":
        return None
    url = "https://api.weather.gov/stations/%s/observations/latest" % sid
    body = get_json(url, TTL_OBS)
    if not body:
        return None
    try:
        p = json.loads(body.decode("utf-8")).get("properties") or {}
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    c = (p.get("temperature") or {}).get("value")
    t = p.get("timestamp")
    if c is None or not t:
        return None
    try:
        dt = datetime.fromisoformat(t.replace("Z", "+00:00"))
    except ValueError:
        return None
    return {"time": dt, "url": url, "values": {"f": r1(c_to_f(c)), "c": c},
            "raw": {"temperature_C": c}, "rawUnits": "degrees Celsius"}


def fetch_one(kind, sid, stations):
    meta = stations.get(sid) or {}
    typ = meta.get("type")
    try:
        if typ == "ndbc":
            return ndbc_reading(kind, sid)
        if typ == "coops":
            return coops_reading(kind, sid)
        if typ == "nws":
            return nws_reading(kind, sid)
    except Exception:  # never let one bad feed break the page
        return None
    return None


def station_info(sid, meta, anchor):
    info = {"id": sid, "name": meta.get("name"), "network": meta.get("network"), "agency": meta.get("agency"),
            "lat": meta.get("lat"), "lon": meta.get("lon"), "setting": meta.get("setting"), "url": meta.get("url")}
    if anchor and meta.get("lat") is not None:
        d, b = miles_bearing(anchor["lat"], anchor["lon"], meta["lat"], meta["lon"])
        info["distanceMi"] = round(d) if d >= 2 else round(d, 1)
        info["bearingFromAnchor"] = compass(b)
        info["anchor"] = anchor.get("label")
    return info


def resolve_reading(kind, spec, stations, anchor, now):
    stale_min = STALE_MIN.get(kind, 90)
    tried = []
    candidates = []
    for sid in spec.get("sources") or []:
        res = fetch_one(kind, sid, stations)
        if not res or not res.get("time"):
            tried.append({"id": sid, "result": "no report"})
            continue
        age_min = (now - res["time"]).total_seconds() / 60.0
        res["_sid"] = sid
        res["_age"] = age_min
        if age_min <= stale_min:
            return build(kind, spec, res, stations, anchor, "ok", tried)
        tried.append({"id": sid, "result": "last report " + (("%d min" % round(age_min)) if age_min < 180 else ("%d h" % round(age_min / 60)) if age_min < 2880 else ("%d days" % round(age_min / 1440))) + " old"})
        candidates.append(res)
    usable = [c for c in candidates if c["_age"] <= MAX_AGE_H * 60]
    if usable:
        return build(kind, spec, usable[0], stations, anchor, "stale", tried)
    out = {"kind": spec.get("kind", "observed"), "role": spec.get("role"), "status": "unavailable",
           "tried": tried, "staleAfterMin": stale_min}
    if candidates:
        c = max(candidates, key=lambda x: x["time"])
        out["lastReport"] = iso(c["time"])
        out["station"] = station_info(c["_sid"], stations.get(c["_sid"]) or {}, anchor)
    elif spec.get("sources"):
        sid = spec["sources"][0]
        out["station"] = station_info(sid, stations.get(sid) or {}, anchor)
    return out


def build(kind, spec, res, stations, anchor, status, tried):
    sid = res["_sid"]
    meta = stations.get(sid) or {}
    return {
        "kind": spec.get("kind", "observed"), "role": spec.get("role"), "status": status,
        "time": iso(res["time"]), "ageMin": round(res["_age"]),
        "staleAfterMin": STALE_MIN.get(kind, 90),
        "station": station_info(sid, meta, anchor),
        "values": res["values"], "raw": res.get("raw"), "rawUnits": res.get("rawUnits"),
        "dataUrl": res.get("url"), "tried": tried,
    }


# ---------- Tides ----------

def et_ymd(d):
    return d.strftime("%Y%m%d")


def tide_preds(station, begin, end, interval):
    url = ("https://api.tidesandcurrents.noaa.gov/api/prod/datagetter?product=predictions&application=%s"
           "&begin_date=%s&end_date=%s&datum=MLLW&station=%s&time_zone=lst_ldt&units=english&interval=%s&format=json"
           % (APP, begin, end, station, interval))
    body = get_json(url, TTL_TIDES)
    if not body:
        return None
    try:
        return json.loads(body.decode("utf-8")).get("predictions")
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None


def local_epoch_ms(t):
    dt = datetime.strptime(t, "%Y-%m-%d %H:%M").replace(tzinfo=ET)
    return int(dt.timestamp() * 1000)


OBS_WL_STALE_MIN = 30      # CO-OPS posts 6-minute water levels, usually 6-15 min behind
OBS_WL_MAX_MIN = 6 * 60    # older than this: not shown at all


def observed_water_level(sid, curve_pts, now):
    """CO-OPS observed (preliminary) water level, MLLW feet, last ~10 hours.
    Returns the trace plus the latest value and the prediction at that same minute."""
    url = coops_url(sid, "water_level", "range=10&datum=MLLW")
    body = get_json(url, TTL_OBS)
    base = {"kind": "observed", "dataUrl": url, "staleAfterMin": OBS_WL_STALE_MIN,
            "sourceUrl": "https://tidesandcurrents.noaa.gov/waterlevels.html?id=%s" % sid}
    if not body:
        base["status"] = "unavailable"
        return base
    try:
        data = json.loads(body.decode("utf-8")).get("data") or []
    except (UnicodeDecodeError, json.JSONDecodeError):
        data = []
    pts = []
    for r in data:
        t = coops_time(r.get("t"))
        v = fnum(r.get("v"))
        if t is None or v is None:
            continue
        pts.append([int(t.timestamp() * 1000), round(v, 3)])
    if not pts:
        base["status"] = "unavailable"
        return base
    last_t, last_v = pts[-1]
    age = (now.timestamp() * 1000 - last_t) / 60000.0
    base.update(lastReport=iso(datetime.fromtimestamp(last_t / 1000, timezone.utc)), ageMin=round(age))
    if age > OBS_WL_MAX_MIN:
        base["status"] = "unavailable"
        return base
    pred = None
    for i in range(1, len(curve_pts)):
        a0, a1 = curve_pts[i - 1], curve_pts[i]
        if a0[0] <= last_t <= a1[0]:
            pred = a0[1] + (a1[1] - a0[1]) * (last_t - a0[0]) / float(a1[0] - a0[0] or 1)
            break
    base.update(
        status="ok" if age <= OBS_WL_STALE_MIN else "stale",
        time=base["lastReport"], points=pts,
        latest={"t": last_t, "v": round(last_v, 2),
                "predicted": round(pred, 2) if pred is not None else None,
                "diff": round(last_v - pred, 2) if pred is not None else None},
        quality="preliminary",
    )
    return base


def tides_block(tcfg, stations, anchor, now):
    sid = tcfg["station"]
    today = now.astimezone(ET).date()
    b = et_ymd(today - timedelta(days=1))
    e = et_ymd(today + timedelta(days=2))
    hilo = tide_preds(sid, b, e, "hilo")
    # Yesterday through tomorrow so the graph window (about 9 h back to 21 h ahead) is always covered.
    curve = tide_preds(sid, b, et_ymd(today + timedelta(days=1)), "6")
    meta = stations.get(sid) or {}
    info = station_info(sid, meta, anchor)
    if not hilo or not curve:
        return {"status": "unavailable", "kind": "predicted", "station": info}
    try:
        events = [{"t": local_epoch_ms(p["t"]), "v": round(float(p["v"]), 2), "type": p.get("type")} for p in hilo]
        pts = [[local_epoch_ms(p["t"]), round(float(p["v"]), 3)] for p in curve]
    except (KeyError, ValueError, TypeError):
        return {"status": "unavailable", "kind": "predicted", "station": info}
    now_ms = now.timestamp() * 1000
    full = pts
    pts = [p for p in pts if now_ms - 9.5 * 3600e3 <= p[0] <= now_ms + 21.5 * 3600e3]
    try:
        observed = observed_water_level(sid, full, now)
    except Exception:
        observed = {"kind": "observed", "status": "unavailable"}
    return {"status": "ok", "kind": "predicted", "station": info, "datum": "MLLW", "units": "ft",
            "events": events, "curve": pts, "interval": "6 min", "observed": observed,
            "sourceUrl": "https://tidesandcurrents.noaa.gov/noaatidepredictions.html?id=%s" % sid}


# ---------- NWS forecast, marine, alerts ----------

def nws_json(url, ttl):
    body = get_json(url, ttl)
    if not body:
        return None
    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None


def mph_to_kt_text(s):
    import re
    if not s:
        return None
    nums = [int(x) for x in re.findall(r"\d+", s)]
    if not nums:
        return None
    kts = [int(round(n * MPH_TO_KT)) for n in nums]
    return ("%d–%d kt" % (kts[0], kts[1])) if len(kts) >= 2 else ("%d kt" % kts[0])


def forecast_block(fcfg):
    url = "https://api.weather.gov/gridpoints/%s/%d,%d/forecast" % (fcfg["gridId"], fcfg["gridX"], fcfg["gridY"])
    d = nws_json(url, TTL_FORECAST)
    props = (d or {}).get("properties") or {}
    periods = props.get("periods") or []
    if not periods:
        return {"status": "unavailable", "kind": "forecast", "label": fcfg.get("label"), "office": fcfg.get("office")}
    out = []
    for p in periods[:14]:
        out.append({
            "name": p.get("name"), "start": p.get("startTime"), "isDaytime": p.get("isDaytime"),
            "tempF": p.get("temperature") if p.get("temperatureUnit") == "F" else None,
            "windMph": p.get("windSpeed"), "windKt": mph_to_kt_text(p.get("windSpeed")),
            "windDir": p.get("windDirection"), "short": p.get("shortForecast"),
            "pop": ((p.get("probabilityOfPrecipitation") or {}).get("value")),
        })
    return {"status": "ok", "kind": "forecast", "label": fcfg.get("label"), "office": fcfg.get("office"),
            "updated": props.get("updateTime") or props.get("generatedAt"), "periods": out,
            "sourceUrl": "https://forecast.weather.gov/MapClick.php?lat=%s&lon=%s" % (fcfg["lat"], fcfg["lon"])}


def marine_block(mcfg):
    zone = mcfg["zone"]
    url = "https://api.weather.gov/zones/coastal/%s/forecast" % zone
    d = nws_json(url, TTL_MARINE)
    props = (d or {}).get("properties") or {}
    periods = props.get("periods") or []
    base = {"kind": "forecast", "zone": zone, "zoneName": mcfg.get("zoneName"), "office": mcfg.get("office"),
            "sourceUrl": "https://forecast.weather.gov/shmrn.php?mz=%s" % zone.lower()}
    if not periods:
        base["status"] = "unavailable"
        return base
    base.update(status="ok", updated=props.get("updated"),
                periods=[{"name": p.get("name"), "text": p.get("detailedForecast")} for p in periods[:3]])
    return base


def alerts_block(zones):
    url = "https://api.weather.gov/alerts/active?zone=" + ",".join(zones)
    d = nws_json(url, TTL_ALERTS)
    if d is None:
        return {"status": "unavailable", "items": []}
    items = []
    seen = set()
    for f in d.get("features") or []:
        p = f.get("properties") or {}
        key = (p.get("event"), p.get("ends") or p.get("expires"))
        if key in seen:
            continue
        seen.add(key)
        items.append({"event": p.get("event"), "headline": p.get("headline"), "severity": p.get("severity"),
                      "areas": p.get("areaDesc"), "onset": p.get("onset"), "ends": p.get("ends") or p.get("expires"),
                      "sender": p.get("senderName")})
    return {"status": "ok", "items": items, "zones": zones,
            "sourceUrl": "https://alerts.weather.gov/"}


# ---------- assemble ----------

def assemble(region_id: str | None) -> tuple[int, dict]:
    cfg = load_regions()
    regions = {r["id"]: r for r in cfg.get("regions") or [] if r.get("enabled")}
    rid = region_id if region_id in regions else cfg.get("default")
    if rid not in regions:
        return 404, {"ok": False, "error": "Unknown region."}
    with _ASM_LOCK:
        hit = _ASSEMBLED.get(rid)
        if hit and time.time() - hit[0] < ASSEMBLED_TTL:
            return 200, hit[1]
    region = regions[rid]
    stations = cfg.get("stations") or {}
    anchor = region.get("anchor")
    now = datetime.now(timezone.utc)
    futures = {}
    for kind, spec in (region.get("readings") or {}).items():
        futures[kind] = _POOL.submit(resolve_reading, kind, spec, stations, anchor, now)
    f_tide = _POOL.submit(tides_block, region["tide"], stations, anchor, now)
    f_fc = _POOL.submit(forecast_block, region["forecast"])
    f_mar = _POOL.submit(marine_block, region["marine"])
    f_al = _POOL.submit(alerts_block, region.get("alertZones") or [region["marine"]["zone"]])
    readings = {}
    for kind, fut in futures.items():
        try:
            readings[kind] = fut.result(timeout=60)
        except Exception:
            readings[kind] = {"status": "unavailable", "kind": "observed"}

    def safe(fut, fallback):
        try:
            return fut.result(timeout=60)
        except Exception:
            return fallback

    payload = {
        "ok": True,
        "region": {"id": rid, "name": region["name"], "area": region.get("area"),
                   "anchor": anchor, "map": region.get("map")},
        "generatedAt": iso(now),
        "readings": readings,
        "tides": safe(f_tide, {"status": "unavailable", "kind": "predicted"}),
        "forecast": safe(f_fc, {"status": "unavailable", "kind": "forecast"}),
        "marine": safe(f_mar, {"status": "unavailable", "kind": "forecast"}),
        "alerts": safe(f_al, {"status": "unavailable", "items": []}),
        "staleRule": "A reading is marked stale when it is older than its station's normal reporting gap (shown per reading). Readings older than %d hours are not shown." % MAX_AGE_H,
    }
    with _ASM_LOCK:
        _ASSEMBLED[rid] = (time.time(), payload)
    return 200, payload
