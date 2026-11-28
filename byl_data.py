"""Before You Launch (Phase 3B, private preview): reviewed station data layer for the 79 pilot ramps.

Rules (Ed t566u / t569u):
- Only stations with publishable=true in stations/ramp_stations.json are ever fetched or shown.
- Every value carries a label (Observed, Forecast, Predicted, Related station, Computed, Stale,
  Unavailable), its source and its time. Missing data is shown as Unavailable, never filled.
- Nothing here says conditions are safe. Access status is the recorded status, never live.
- Each source has its own cache TTL, timeout, concurrency limit and failure backoff, and fails alone.
- NWS forecasts and alerts do not depend on the water class, so they still show on pilot ramps whose
  water classification is unresolved; water readings are withheld there.
"""
from __future__ import annotations

import json
import math
import re
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, wait as _wait
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import brief_astro

ROOT = Path(__file__).resolve().parent
ET = ZoneInfo("America/New_York")
UA = "TheCoastalBrief/1.0 (thecoastalbrief.com; Before You Launch preview)"

# Seconds one .json response waits for its sources. Slower sources keep running in the background, fill the shared
# cache, and are reported as "pending" so the page asks again instead of timing out (production USGS took 16-22 s).
BUDGET = 9.0

# ttl: seconds a good response is reused; timeout: per request; backoff: first wait after a failure (doubles, capped)
# lkg: how long a last-known-good response may be served when the source fails (0 = never; alerts must be current)
SOURCES = {
    "nws_forecast": {"ttl": 1800, "timeout": 8, "backoff": 60, "backoff_max": 900, "concurrency": 4, "lkg": 36 * 3600},
    "nws_alerts": {"ttl": 300, "timeout": 8, "backoff": 30, "backoff_max": 300, "concurrency": 4, "lkg": 0},
    "nws_obs": {"ttl": 600, "timeout": 8, "backoff": 60, "backoff_max": 900, "concurrency": 3, "lkg": 3 * 3600},
    "nws_marine": {"ttl": 1800, "timeout": 8, "backoff": 60, "backoff_max": 900, "concurrency": 2, "lkg": 24 * 3600},
    "usgs": {"ttl": 600, "timeout": 25, "backoff": 60, "backoff_max": 900, "concurrency": 2, "lkg": 24 * 3600},
    "usgs_hist": {"ttl": 3600, "timeout": 45, "backoff": 120, "backoff_max": 1800, "concurrency": 1, "lkg": 24 * 3600},
    "usace": {"ttl": 6 * 3600, "timeout": 10, "backoff": 120, "backoff_max": 3600, "concurrency": 1, "lkg": 7 * 86400},
    "coops": {"ttl": 6 * 3600, "timeout": 8, "backoff": 120, "backoff_max": 1800, "concurrency": 3, "lkg": 24 * 3600},
    "coops_obs": {"ttl": 600, "timeout": 8, "backoff": 60, "backoff_max": 900, "concurrency": 3, "lkg": 3 * 3600},
}
# Age at which a reading is labelled Stale, and age past which it is not shown at all.
STALE = {"usgs": (3 * 3600, 24 * 3600), "usace": (36 * 3600, 7 * 86400), "nws_forecast": (12 * 3600, 36 * 3600),
         "wind_obs": (90 * 60, 3 * 3600), "coops_obs": (90 * 60, 6 * 3600), "nws_marine": (9 * 3600, 24 * 3600)}
KT = 0.868976
# What each number is measured against. Gauge height and lake elevation are never water depth.
DATUM = {"62614": "NGVD29", "62615": "NAVD88", "00065": "gauge datum (local; not depth)", "00060": "measured discharge", "MLLW": "MLLW"}
GUIDE = {"SAW-FALLS": 251.5, "SAW-JORDAN": 216.0}  # USACE dsslake.txt header: constant every day of the year
COASTAL = {}
MARINE_EVENT = re.compile(r"marine|small craft|gale|storm warning|hurricane force|special marine|rip current|"
                          r"beach hazard|coastal flood|high surf|brisk wind|hazardous seas|low water", re.I)
LABELS = {"obs": "Observed", "fcst": "Forecast", "pred": "Predicted", "rel": "Related station", "comp": "Computed",
          "stale": "Stale", "unav": "Unavailable", "rec": "Recorded status"}
FRESH_CLASSES = ("reservoir", "natural_lake", "river")


class SourceDown(Exception):
    pass


class Fetcher:
    """Per-source cache, timeout, concurrency limit and exponential backoff. Thread-safe."""

    def __init__(self, opener=None, clock=time.time):
        self.cache = {}
        self.fail = {}
        self.lock = threading.Lock()
        self.sem = {k: threading.BoundedSemaphore(v["concurrency"]) for k, v in SOURCES.items()}
        self.opener = opener or self._open
        self.clock = clock
        self.calls = []
        self.lkg_used = set()
        self.inflight = {}

    @staticmethod
    def _open(url, timeout):
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/geo+json, application/json, text/plain"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()

    def get(self, source, url, parse=json.loads):
        cfg = SOURCES[source]
        now = self.clock()
        with self.lock:
            hit = self.cache.get(url)
            if hit and now - hit[0] < cfg["ttl"]:
                self.lkg_used.discard(url)
                return hit[1]
            f = self.fail.get(source)
            if f and now < f[1]:
                return self._lkg(source, url, now, "%s backing off after a failure" % source)
            ev = self.inflight.get(url)
            mine = ev is None
            if mine:
                ev = self.inflight[url] = threading.Event()
        if not mine:
            # The same URL is already being fetched (for example by warm()): wait for that one request.
            ev.wait(cfg["timeout"] + 1)
            with self.lock:
                hit = self.cache.get(url)
                if hit and self.clock() - hit[0] < cfg["ttl"]:
                    return hit[1]
                return self._lkg(source, url, now, "%s did not answer" % source)
        try:
            return self._fetch(source, url, parse, cfg, now)
        finally:
            with self.lock:
                self.inflight.pop(url, None)
            ev.set()

    def _fetch(self, source, url, parse, cfg, now):
        if not self.sem[source].acquire(timeout=cfg["timeout"]):
            raise SourceDown("%s busy" % source)
        try:
            self.calls.append((source, url))
            body = self.opener(url, cfg["timeout"])
            val = parse(body if parse is json.loads else body.decode("utf-8", "replace"))
        except Exception as e:
            with self.lock:
                n = (self.fail.get(source) or (0, 0, 0))[2] + 1
                wait = min(cfg["backoff"] * 2 ** (n - 1), cfg["backoff_max"])
                self.fail[source] = (now, now + wait, n)
            return self._lkg(source, url, now, "%s failed: %s" % (source, type(e).__name__))
        finally:
            self.sem[source].release()
        with self.lock:
            self.cache[url] = (now, val)
            self.fail.pop(source, None)
            self.lkg_used.discard(url)
        return val

    def _lkg(self, source, url, now, why):
        """Last known good: the previous good response, only within the source's lkg window. Observation
        times inside it still drive the Stale label and the hide threshold, so old data is never shown as current."""
        hit = self.cache.get(url)
        if hit and SOURCES[source]["lkg"] and now - hit[0] <= SOURCES[source]["lkg"]:
            self.lkg_used.add(url)
            return hit[1]
        raise SourceDown(why)


FETCH = Fetcher()


def load_sites():
    d = json.loads((ROOT / "stations/ramp_stations.json").read_text())
    return {e["id"]: e for e in d["sites"] if e["pilot"]}


def load_records():
    return {r["id"]: r for r in json.loads((ROOT / "preview/ramp-finder/map-data.json").read_text())["records"]}


def publishable(site, *types):
    return [c for c in site["stations"] if c["publishable"] and c["type"] in types]


def water_ok(site):
    return site["review"]["status"] == "reviewed" and site["water_class"] != "unresolved"


def _age(ts, now):
    return (now - ts).total_seconds()


def freshness(source, ts, now):
    """'fresh', 'stale' or 'too_old' for an observation time."""
    stale, reject = STALE[source]
    a = _age(ts, now)
    return "too_old" if a > reject else "stale" if a > stale else "fresh"


def _fmt(dt):
    return dt.astimezone(ET).strftime("%-I:%M %p").replace(":00 ", " ") if dt else ""


def _fmt_day(dt):
    return dt.astimezone(ET).strftime("%b %-d, %-I:%M %p")


def _card(key, label, kind, source, when="", note="", **vals):
    return {"key": key, "label": label, "kind": kind, "tag": LABELS[kind], "source": source, "when": when, "note": note, **vals}


def _unav(key, label, why, source=""):
    return _card(key, label, "unav", source, note=why)


# ---------- NWS
def nws_forecast(site, f=FETCH, now=None):
    now = now or datetime.now(timezone.utc)
    p = site.get("nws_point")
    if not p:
        return _unav("forecast", "Forecast", "No NWS forecast point: this listing has no official coordinates.")
    try:
        d = f.get("nws_forecast", p["url"])
        props = d["properties"]
        upd = datetime.fromisoformat(props.get("updateTime") or props.get("generatedAt"))
        per = props["periods"][:4]
    except SourceDown:
        return _unav("forecast", "Forecast", "The NWS forecast could not be reached just now.", "NWS")
    except Exception:
        return _unav("forecast", "Forecast", "The NWS forecast response was not usable.", "NWS")
    fr = freshness("nws_forecast", upd, now)
    if fr == "too_old" or not per:
        return _unav("forecast", "Forecast", "The latest NWS forecast is too old to show.", "NWS")
    periods = [{"name": x["name"], "temp": x.get("temperature"), "unit": x.get("temperatureUnit"), "wind": "%s %s" % (x.get("windDirection") or "", x.get("windSpeed") or ""),
                "short": x.get("shortForecast")} for x in per]
    return _card("forecast", "Forecast near the ramp", "stale" if fr == "stale" else "fcst",
                 "NWS point forecast · %s" % p["office"], "updated " + _fmt_day(upd), periods=periods)


def nws_alerts(site, rec, f=FETCH):
    if rec.get("la") is None:
        return _unav("alerts", "Weather alerts", "No coordinates, so point alerts cannot be checked.", "NWS")
    url = "https://api.weather.gov/alerts/active?point=%.4f,%.4f" % (rec["la"], rec["lo"])
    try:
        feats = f.get("nws_alerts", url).get("features", [])
    except SourceDown:
        return _unav("alerts", "Weather alerts", "NWS alerts could not be checked just now. Check weather.gov before you go.", "NWS")
    fresh = site["water_class"] in FRESH_CLASSES
    out = []
    for x in feats:
        pr = x.get("properties") or {}
        ev = pr.get("event") or ""
        zones = " ".join(pr.get("affectedZones") or []) + " " + " ".join((pr.get("geocode") or {}).get("UGC") or [])
        if fresh and (MARINE_EVENT.search(ev) or "/zones/marine/" in zones or re.search(r"\bAM[ZS]\d|\bAN[ZS]\d", zones)):
            continue  # no marine advisories on freshwater pages
        out.append({"event": ev, "headline": pr.get("headline") or ev, "severity": pr.get("severity"),
                    "ends": pr.get("ends") or pr.get("expires"), "sender": pr.get("senderName") or "NWS", "id": pr.get("@id") or x.get("id")})
    return _card("alerts", "Weather alerts", "fcst" if out else "obs", "NWS active alerts for this point", "checked " + _fmt(datetime.now(timezone.utc)), alerts=out, link="https://forecast.weather.gov/MapClick.php?lat=%.4f&lon=%.4f" % (rec["la"], rec["lo"]),
                 note="" if out else "No NWS alert is listed for this point right now. An empty list is not an all-clear.")


# ---------- USGS
_ALL = {}


def all_usgs(types=None):
    """Every reviewed, publishable USGS station on a reviewed pilot ramp: one shared request serves every page."""
    key = ("usgs", types)
    if key not in _ALL:
        ids = set()
        for e in load_sites().values():
            if water_ok(e):
                ids |= {c["id"] for c in e["stations"] if c["publishable"] and c["source"] == "USGS" and (types is None or c["type"] in types)}
        _ALL[key] = sorted(ids)
    return _ALL[key]


def _parse_iv(d):
    out = {}
    for ts in d["value"]["timeSeries"]:
        sid = ts["sourceInfo"]["siteCode"][0]["value"]
        pc = ts["variable"]["variableCode"][0]["value"]
        vals = [v for v in ts["values"][0]["value"] if v.get("value") not in (None, "", "-999999")]
        if vals:
            out[(sid, pc)] = [(datetime.fromisoformat(v["dateTime"]), float(v["value"])) for v in vals]
    return out


def usgs_hist(f=FETCH):
    """14 days of lake elevation for the reviewed lake gauges (one shared request), thinned to 6-hourly points."""
    ids = all_usgs(("lake_elevation",))
    d = f.get("usgs_hist", "https://waterservices.usgs.gov/nwis/iv/?format=json&period=P14D&parameterCd=62614,62615&sites=" + ",".join(ids))
    out = {}
    for k, s in _parse_iv(d).items():
        thin, last = [], None
        for t, v in s:
            if last is None or (t - last).total_seconds() >= 6 * 3600:
                thin.append((t, v)); last = t
        if thin[-1][0] != s[-1][0]:
            thin.append(s[-1])
        out[k] = thin
    return out


def usgs_batch(ids=None, f=FETCH):
    ids = all_usgs() if ids is None or set(ids) <= set(all_usgs()) else sorted(set(ids))
    url = ("https://waterservices.usgs.gov/nwis/iv/?format=json&period=PT25H&parameterCd=00060,00065,62614,62615,00010&sites="
           + ",".join(ids))
    d = f.get("usgs", url)
    out = {}
    for ts in d["value"]["timeSeries"]:
        sid = ts["sourceInfo"]["siteCode"][0]["value"]
        pc = ts["variable"]["variableCode"][0]["value"]
        vals = [v for v in ts["values"][0]["value"] if v.get("value") not in (None, "", "-999999")]
        if vals:
            out[(sid, pc)] = [(datetime.fromisoformat(v["dateTime"]), float(v["value"])) for v in vals]
    return out


def _usgs_card(key, label, c, series, pcs, unit, now, kind="obs", note="", conv=None):
    for pc in pcs:
        s = series.get((c["id"], pc))
        if not s:
            continue
        t, v = s[-1]
        fr = freshness("usgs", t, now)
        if fr == "too_old":
            return _unav(key, label, "The latest reading is more than 24 hours old.", "USGS %s" % c["id"])
        v0 = next((vv for tt, vv in s if _age(tt, t) <= 6.5 * 3600), None)
        trend = None
        if v0 is not None and len(s) > 1 and pc != "00010":
            dv = v - v0
            trend = "steady" if abs(dv) < (0.05 if pc != "00060" else max(5, 0.03 * v0)) else ("rising" if dv > 0 else "falling")
        val = conv(v) if conv else v
        spark, last = [], None
        for tt, vv in s:
            if _age(tt, t) <= 24 * 3600 and (last is None or (tt - last).total_seconds() >= 3600):
                spark.append([tt.isoformat(), round(conv(vv) if conv else vv, 2)]); last = tt
        return _card(key, label, "stale" if fr == "stale" else kind, "USGS %s · %s" % (c["id"], c.get("name", "").title()),
                     _fmt(t), note=note, value=round(val, 2 if pc in ("62614", "62615", "00065") else 0), unit=unit, param=pc,
                     trend=trend, trend_kind="comp" if trend else None, spark=spark if pc != "00010" and len(spark) > 2 else None,
                     datum=DATUM.get(pc))
    return _unav(key, label, "This gauge has no current value for this reading.", "USGS %s" % c["id"])


# ---------- USACE
def usace_lakes(f=FETCH):
    txt = f.get("usace", "https://epec.saw.usace.army.mil/dsslake.txt", parse=lambda s: s)
    rows = [l.split() for l in txt.splitlines() if re.match(r"^\d{2}[A-Z]{3}\d{4}\s", l)]
    if not rows:
        raise SourceDown("usace: no rows")
    last = rows[-1]
    day = datetime.strptime(last[0], "%d%b%Y").replace(tzinfo=ET)
    # columns: Kerr elev, Kerr guide, Philpott elev, Philpott guide, Jordan, Falls, W. Kerr Scott
    def num(i):
        try:
            v = float(last[i])
        except (IndexError, ValueError):
            return None
        return None if v <= -99 else v
    return {"SAW-JORDAN": (day, num(5), 216.0), "SAW-FALLS": (day, num(6), 251.5)}


def usace_card(c, now, f=FETCH):
    try:
        lakes = usace_lakes(f)
    except SourceDown:
        return _unav("usace", "Official lake level", "The USACE lake report could not be reached just now.", "USACE Wilmington District")
    day, elev, guide = lakes.get(c["id"], (None, None, None))
    if elev is None:
        return _unav("usace", "Official lake level", "USACE did not list a level for this lake.", "USACE Wilmington District")
    fr = freshness("usace", day, now)
    if fr == "too_old":
        return _unav("usace", "Official lake level", "Not shown: the USACE midnight report's latest row is %s, more than a week old." % day.strftime("%b %-d"), "USACE Wilmington District")
    return _card("usace", "Official lake level", "stale" if fr == "stale" else "obs", "USACE Wilmington District · midnight report",
                 day.strftime("%b %-d"), value=round(elev, 2), unit="ft", guide=guide, vs_guide=round(elev - guide, 2),
                 note="Feet above mean sea level (NGVD29). The guide curve is the USACE target pool level (constant every day of the year for Falls and Jordan), not a safety line.")


# ---------- CO-OPS
def coops_card(c, now, f=FETCH):
    d0 = now.astimezone(ET).date()
    url = ("https://api.tidesandcurrents.noaa.gov/api/prod/datagetter?product=predictions&application=thecoastalbrief&datum=MLLW"
           "&time_zone=lst_ldt&units=english&interval=hilo&format=json&station=%s&begin_date=%s&end_date=%s"
           % (c["id"], d0.strftime("%Y%m%d"), (d0 + timedelta(days=1)).strftime("%Y%m%d")))
    try:
        p = f.get("coops", url).get("predictions") or []
    except SourceDown:
        return _unav("tide", "Tide predictions", "NOAA tide predictions could not be reached just now.", "NOAA CO-OPS %s" % c["id"])
    ev = []
    for x in p:
        t = datetime.strptime(x["t"], "%Y-%m-%d %H:%M").replace(tzinfo=ET)
        ev.append({"type": "High" if x["type"] == "H" else "Low", "time": _fmt(t), "day": t.strftime("%a"), "ft": round(float(x["v"]), 1) + 0.0, "ts": t.isoformat()})  # + 0.0: never "-0.0"
    upcoming = [e for e in ev if datetime.fromisoformat(e["ts"]) >= now][:4]
    all_events = [e for e in ev if abs((datetime.fromisoformat(e["ts"]) - now).total_seconds()) <= 20 * 3600]
    if not upcoming:
        return _unav("tide", "Tide predictions", "No upcoming predictions were returned.", "NOAA CO-OPS %s" % c["id"])
    return _card("tide", "Tide predictions", "pred", "NOAA CO-OPS %s · %s (%s)" % (c["id"], c.get("name", ""), c["relation"].replace("_", " ")),
                 "", events=upcoming, all_events=all_events, note="Astronomical predictions (feet above MLLW). Wind and pressure can shift actual water level and timing.")


# ---------- computed
def sun_moon(rec, on=None):
    if rec.get("la") is None:
        return _unav("sun", "Sun & moon", "No coordinates for this listing, so times are not computed.")
    on = on or datetime.now(ET).date()
    st = brief_astro.sun_times(rec["la"], rec["lo"], on)
    m = brief_astro.moon_illumination(datetime.combine(on, datetime.min.time(), ET).replace(hour=12))
    if not st or not m:
        return _unav("sun", "Sun & moon", "Could not compute times for this date.")
    rise, set_ = st.get("sunrise"), st.get("sunset")
    frac = m.get("fraction")
    return _card("sun", "Sun & moon", "comp", "Computed for the ramp coordinates (NOAA solar equations; Meeus lunar phase)", on.strftime("%b %-d"),
                 sunrise=_fmt(rise) if rise else None, sunset=_fmt(set_) if set_ else None,
                 moon_pct=round(frac * 100) if frac is not None else None, moon_phase=brief_astro.phase_name(frac, m.get("waxing", True)) if frac is not None else None)


# ---------- coastal (Phase 3C reviewed instruments: stations/byl_coastal_review.json)
def load_coastal():
    if "c" not in COASTAL:
        d = json.loads((ROOT / "stations/byl_coastal_review.json").read_text())
        COASTAL["c"] = {x["id"]: x for x in d["sites"]}
    return COASTAL["c"]


def accepted(rows, typ=None):
    return [x for x in rows or [] if x.get("decision") == "accepted" and (typ is None or x.get("type") == typ)]


def _compass(deg):
    if deg is None:
        return ""
    return ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"][int((deg % 360) / 22.5 + .5) % 16]


def wind_obs(st, now, f=FETCH):
    key, label = "wind_obs", "Wind now (observed)"
    src = "%s %s · %s, %.1f mi" % (st["source"], st["id"], st["name"], st["distance_mi"])
    try:
        if st["source"] == "NOAA CO-OPS":
            url = ("https://api.tidesandcurrents.noaa.gov/api/prod/datagetter?product=wind&date=latest&station=%s&units=english&time_zone=gmt"
                   "&format=json&application=thecoastalbrief" % st["id"])
            x = f.get("coops_obs", url)["data"][-1]
            t = datetime.strptime(x["t"], "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
            kt, gkt, deg = float(x["s"]), float(x["g"]) if x.get("g") not in (None, "") else None, (float(x["d"]) if x.get("d") not in (None, "") else None)
        else:
            # Recent observations: the newest one that actually carries a wind value (some reports omit it).
            url = "https://api.weather.gov/stations/%s/observations?limit=6" % st["id"]
            feats = f.get("nws_obs", url).get("features") or []
            p = next((x["properties"] for x in feats if ((x.get("properties") or {}).get("windSpeed") or {}).get("value") is not None), None)
            if p is None:
                return _unav(key, label, "The station's recent reports carry no wind value.", src)
            t = datetime.fromisoformat(p["timestamp"])
            ws, wg, wd = (p.get("windSpeed") or {}).get("value"), (p.get("windGust") or {}).get("value"), (p.get("windDirection") or {}).get("value")
            kt, gkt, deg = ws * 0.539957, (wg * 0.539957 if wg is not None else None), wd
    except SourceDown:
        return _unav(key, label, "The wind station could not be reached just now.", src)
    except Exception:
        return _unav(key, label, "The wind station response was not usable.", src)
    fr = freshness("wind_obs", t, now)
    if fr == "too_old":
        return _unav(key, label, "The latest wind report is more than 3 hours old.", src)
    note = "Measured at the station, not at the ramp." + (" Ocean pier: more exposed than sound-side water." if st.get("exposure") == "ocean_pier" else "") + \
           (" Airport anemometer over land." if st.get("exposure") == "airport" else "")
    return _card(key, label, "stale" if fr == "stale" else "rel", src, _fmt(t), note=note, kt=round(kt), mph=round(kt / KT),
                 gust_kt=round(gkt) if gkt is not None else None, gust_mph=round(gkt / KT) if gkt is not None else None,
                 deg=round(deg) if deg is not None else None, dir=_compass(deg), calm=kt < 1)


def coops_obs(st, now, f=FETCH):
    typ = st["type"]
    key, label = ("coastal_temp", "Water temperature") if typ == "water_temp" else ("water_level", "Water level (observed)")
    src = "NOAA CO-OPS %s · %s, %.1f mi" % (st["id"], st["name"], st["distance_mi"])
    product = "water_temperature" if typ == "water_temp" else "water_level"
    url = ("https://api.tidesandcurrents.noaa.gov/api/prod/datagetter?product=%s&range=24&station=%s&units=english&time_zone=gmt&datum=MLLW"
           "&format=json&application=thecoastalbrief" % (product, st["id"]))
    try:
        rows = [x for x in f.get("coops_obs", url).get("data") or [] if x.get("v") not in (None, "")]
    except SourceDown:
        return _unav(key, label, "NOAA could not be reached just now.", src)
    if not rows:
        return _unav(key, label, "The station returned no recent values.", src)
    pts = [(datetime.strptime(x["t"], "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc), float(x["v"])) for x in rows]
    t, v = pts[-1]
    fr = freshness("coops_obs", t, now)
    if fr == "too_old":
        return _unav(key, label, "The latest value is more than 6 hours old.", src)
    spark, last = [], None
    for tt, vv in pts:
        if last is None or (tt - last).total_seconds() >= 3600:
            spark.append([tt.isoformat(), round(vv, 2)]); last = tt
    if typ == "water_temp":
        return _card(key, label, "stale" if fr == "stale" else "obs", src, _fmt(t), note="Measured at the NOAA station on the same water, not at the ramp.",
                     value=round(v), unit="°F")
    return _card(key, label, "stale" if fr == "stale" else "obs", src, _fmt(t), value=round(v, 2), unit="ft", datum="MLLW", spark=spark,
                 note="Feet above MLLW (mean lower low water) at the station. This is not water depth at the ramp.")


def marine_zone(z, now, f=FETCH):
    key = "marine"
    ocean = z["kind"] == "ocean_beyond_inlet"
    label = "Ocean beyond the inlet (NWS marine forecast)" if ocean else "Marine forecast for this water"
    src = "NWS Newport/Morehead City · zone %s %s" % (z["id"], z["name"])
    url = "https://tgftp.nws.noaa.gov/data/forecasts/marine/coastal/am/%s.txt" % z["id"].lower()
    try:
        txt = f.get("nws_marine", url, parse=lambda b: b)
    except SourceDown:
        return _unav(key, label, "The NWS marine forecast could not be reached just now.", src)
    m = re.search(r"^(\d{3,4}) (AM|PM) (E[SD]T) \w{3} (\w{3}) (\d{1,2}) (\d{4})$", txt, re.M)
    try:
        hm = m.group(1).zfill(4)
        issued = datetime.strptime("%s %s %s %s %s" % (hm, m.group(2), m.group(4), m.group(5), m.group(6)), "%I%M %p %b %d %Y").replace(tzinfo=ET)
    except Exception:
        return _unav(key, label, "The NWS marine forecast text was not usable.", src)
    fr = freshness("nws_marine", issued, now)
    if fr == "too_old":
        return _unav(key, label, "The latest NWS marine forecast is too old to show.", src)
    heads = [h.strip(". ").title() for h in re.findall(r"^\.\.\.(.+?)\.\.\.$", txt, re.M)]
    per = []
    for name, body in re.findall(r"^\.([A-Z][A-Z ]+?)\.\.\.(.+?)(?=^\.[A-Z]|^\$\$|\Z)", txt, re.M | re.S):
        per.append({"name": name.title(), "text": re.sub(r"\s+", " ", body).strip()})
    if not per:
        return _unav(key, label, "The NWS marine forecast text was not usable.", src)
    note = ("For the open ocean beyond the inlet, out to 20 NM. Not a forecast for the sound or waterway at this ramp." if ocean else "")
    return _card(key, label, "stale" if fr == "stale" else "fcst", src, "issued " + _fmt_day(issued), note=note, headlines=heads, periods=per[:4])


def tide_curve(c, now, f=FETCH):
    """NOAA CO-OPS 6-minute tide predictions (MLLW) from 6 h ago to 18 h ahead, for the curve.

    Only harmonic stations publish 6-minute predictions. Subordinate stations publish official
    highs and lows only; for those this returns None and the page shows the high/low schedule.
    Nothing is interpolated between NOAA's points. One request per station and hour, shared by
    every ramp that uses the station."""
    d0 = now.astimezone(ET)
    url = ("https://api.tidesandcurrents.noaa.gov/api/prod/datagetter?product=predictions&application=thecoastalbrief&datum=MLLW"
           "&time_zone=lst_ldt&units=english&interval=6&format=json&station=%s&begin_date=%s&range=30"
           % (c["id"], (d0 - timedelta(hours=6)).strftime("%Y%m%d%%20%H:00")))
    try:
        p = f.get("coops", url).get("predictions") or []
    except SourceDown:
        return None
    pts = [[datetime.strptime(x["t"], "%Y-%m-%d %H:%M").replace(tzinfo=ET).isoformat(), round(float(x["v"]), 2)] for x in p]
    lo, hi = (now - timedelta(hours=6)), (now + timedelta(hours=18))
    pts = [x for x in pts if lo <= datetime.fromisoformat(x[0]) <= hi]
    return {"pts": pts, "interval_min": 6} if len(pts) >= 120 else None


def nws_hourly(site, f=FETCH, now=None):
    p = site.get("nws_point")
    if not p:
        return None
    try:
        per = f.get("nws_forecast", p["url"] + "/hourly")["properties"]["periods"]
    except Exception:
        return None
    out = []
    for x in per:
        t = datetime.fromisoformat(x["startTime"])
        if now and t < now - timedelta(hours=1):
            continue
        m = re.findall(r"\d+", x.get("windSpeed") or "")
        if not m:
            continue
        out.append({"t": t.isoformat(), "mph": int(m[-1]), "dir": x.get("windDirection") or ""})
        if len(out) >= 12:
            break
    return out or None


_BG = ThreadPoolExecutor(max_workers=2)


def soon(fn, wait):
    """Run fn, but give up waiting after `wait` seconds; the request keeps running and fills the shared cache
    for the next page view. Used for history charts so slow history never delays current readings."""
    fu = _BG.submit(fn)
    try:
        return fu.result(timeout=wait)
    except Exception:
        return None


def warm(f=FETCH):
    """Fill the shared station caches in the background (one USGS request serves every pilot page)."""
    for fn in (lambda: usgs_batch(None, f), lambda: usgs_hist(f)):
        _BG.submit(fn)


# ---------- assemble
def assemble(site_id, f=FETCH, now=None, sites=None, records=None, coastal=None, budget=None):
    sites = sites or load_sites()
    records = records or load_records()
    coastal = load_coastal() if coastal is None else coastal
    site, rec = sites[site_id], records[site_id]
    now = now or datetime.now(timezone.utc)
    cards = {"sun": sun_moon(rec, now.astimezone(ET).date())}
    cz = coastal.get(site_id) or {}
    jobs = {"forecast": lambda: nws_forecast(site, f, now), "alerts": lambda: nws_alerts(site, rec, f)}
    hourly = {}
    jobs["_hourly"] = lambda: hourly.setdefault("h", nws_hourly(site, f, now))
    # Atmospheric and forecast instruments do not depend on the water class.
    w = accepted(cz.get("wind"))
    if w:
        jobs["wind_obs"] = lambda: wind_obs(w[0], now, f)
    z = cz.get("marine_zone") or {}
    if z.get("decision") == "accepted":
        jobs["marine"] = lambda: marine_zone(z, now, f)
    withheld = None
    if water_ok(site):
        guide = next((GUIDE.get(c["id"]) for c in site["stations"] if c["publishable"] and c["source"] == "USACE"), None)

        def usgs_cards():
            out = []
            try:
                series = usgs_batch(None, f)
            except SourceDown:
                series = None
            hist = None
            for c in publishable(site, "lake_elevation", "river_stage_flow", "water_temp", "downstream_river_flow"):
                if c["source"] != "USGS":
                    continue
                key = {"lake_elevation": "lake", "river_stage_flow": "river:" + c["id"], "water_temp": "temp", "downstream_river_flow": "below_dam"}[c["type"]]
                if series is None:
                    out.append(_unav(key, "Gauge reading", "USGS water data could not be reached just now.", "USGS %s" % c["id"])); continue
                if c["type"] == "lake_elevation":
                    pcs = ("62614", "62615") if c.get("datum") != "NAVD88" else ("62615",)
                    card = _usgs_card(key, "Lake elevation", c, series, pcs, "ft", now)
                    if card["kind"] != "unav":
                        dname = DATUM[card["param"]]
                        card["note"] = "Feet above %s at the gauge on this lake. Lake elevation is not water depth." % dname
                        if guide is not None and card["param"] == "62614":
                            card.update(guide=guide, vs_guide=round(card["value"] - guide, 2),
                                        guide_note="Guide curve %.1f ft (USACE, same datum: USACE midnight values match this gauge's NGVD29 readings)." % guide)
                        hist = hist if hist is not None else soon(lambda: usgs_hist(f), 3)
                        h = (hist or {}).get((c["id"], card["param"]))
                        if h and len(h) > 8:
                            card["hist"] = [[t.isoformat(), v] for t, v in h]
                    out.append(card)
                elif c["type"] == "water_temp":
                    out.append(_usgs_card(key, "Water temperature", c, series, ("00010",), "°F", now, note="Measured at the gauge on the same water, not at the ramp.", conv=lambda v: v * 9 / 5 + 32))
                elif c["type"] == "downstream_river_flow":
                    out.append(_usgs_card(key, "River flow below the dam (measured)", c, series, ("00060",), "cfs", now,
                                          note="Measured discharge on the river downstream of the dam, in cubic feet per second. A different water body from the lake, and not a reported dam release."))
                else:
                    rel = c["relation"].replace("same_river_", "")
                    kind = "obs" if (c.get("distance_mi") or 0) <= 1.0 else "rel"
                    card = _usgs_card(key, "River gauge · %s" % rel, c, series, ("00065", "00060"), "", now, kind=kind,
                                      note="Same river, %s mi %s, no dam between." % (c.get("distance_mi"), rel))
                    if card["kind"] != "unav":
                        card["unit"] = "ft" if card["param"] == "00065" else "cfs"
                        card["note"] += " Gauge height is measured against the gauge's own datum and is not water depth." if card["param"] == "00065" else " Measured discharge."
                    out.append(card)
            return out
        if publishable(site, "lake_elevation", "river_stage_flow", "water_temp", "downstream_river_flow"):
            jobs["usgs"] = usgs_cards
        for c in publishable(site, "lake_elevation"):
            if c["source"] == "USACE":
                jobs["usace"] = (lambda c=c: usace_card(c, now, f))
        tide = publishable(site, "tide_predictions")
        if site["tide_policy"] == "predictions" and tide:
            def tide_job():
                card = coops_card(tide[0], now, f)
                if card["kind"] != "unav":
                    card["curve"] = tide_curve(tide[0], now, f)
                    card["now"] = now.isoformat()
                return card
            jobs["tide"] = tide_job
        for i, st in enumerate(accepted(cz.get("water"))):
            jobs["coops_%d" % i] = (lambda st=st: coops_obs(st, now, f))
    else:
        withheld = ("Water readings are withheld for this ramp until its water classification is confirmed (%s). Forecasts and alerts do not depend on it."
                    % site["class_basis"])
    # Wait at most `budget` seconds in total. Unfinished jobs are not cancelled: they keep running, fill the shared
    # cache, and are listed in "pending" so the page asks again. Nothing is filled in for them.
    ex = ThreadPoolExecutor(max_workers=len(jobs))
    futs = {k: ex.submit(fn) for k, fn in jobs.items()}
    _wait(list(futs.values()), timeout=BUDGET if budget is None else budget)
    ex.shutdown(wait=False)
    pending = []
    for k, fu in futs.items():
        if not fu.done():
            if k != "_hourly":
                pending.append(k)
            continue
        try:
            r = fu.result()
        except Exception:
            r = None if k == "_hourly" else _unav(k, k.title(), "This source did not answer in time.")
        if k == "_hourly" or r is None:
            continue
        for c in (r if isinstance(r, list) else [r]):
            cards[c["key"]] = c
    if hourly.get("h") and cards.get("forecast", {}).get("kind") in ("fcst", "stale"):
        cards["forecast"]["hourly"] = hourly["h"]
    lkg = sorted(u for u in f.lkg_used)
    return {"id": site_id, "generated": now.isoformat(), "water_class": site["water_class"], "tide_policy": site["tide_policy"],
            "withheld": withheld, "cards": cards, "last_known_good": bool(lkg), "pending": sorted(pending)}
