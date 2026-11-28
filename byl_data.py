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
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import brief_astro

ROOT = Path(__file__).resolve().parent
ET = ZoneInfo("America/New_York")
UA = "TheCoastalBrief/1.0 (thecoastalbrief.com; Before You Launch preview)"

# ttl: seconds a good response is reused; timeout: per request; backoff: first wait after a failure (doubles, capped)
SOURCES = {
    "nws_forecast": {"ttl": 1800, "timeout": 8, "backoff": 60, "backoff_max": 900, "concurrency": 4},
    "nws_alerts": {"ttl": 300, "timeout": 8, "backoff": 30, "backoff_max": 300, "concurrency": 4},
    "usgs": {"ttl": 600, "timeout": 10, "backoff": 60, "backoff_max": 900, "concurrency": 2},
    "usace": {"ttl": 6 * 3600, "timeout": 10, "backoff": 120, "backoff_max": 3600, "concurrency": 1},
    "coops": {"ttl": 6 * 3600, "timeout": 8, "backoff": 120, "backoff_max": 1800, "concurrency": 3},
}
# Age at which a reading is labelled Stale, and age past which it is not shown at all.
STALE = {"usgs": (3 * 3600, 24 * 3600), "usace": (36 * 3600, 7 * 86400), "nws_forecast": (12 * 3600, 36 * 3600)}
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
                return hit[1]
            f = self.fail.get(source)
            if f and now < f[1]:
                raise SourceDown("%s backing off after a failure" % source)
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
            raise SourceDown("%s failed: %s" % (source, type(e).__name__)) from None
        finally:
            self.sem[source].release()
        with self.lock:
            self.cache[url] = (now, val)
            self.fail.pop(source, None)
        return val


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
def usgs_batch(ids, f=FETCH):
    url = ("https://waterservices.usgs.gov/nwis/iv/?format=json&period=PT7H&parameterCd=00060,00065,62614,62615,00010&sites="
           + ",".join(sorted(set(ids))))
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
        return _card(key, label, "stale" if fr == "stale" else kind, "USGS %s · %s" % (c["id"], c.get("name", "").title()),
                     _fmt(t), note=note, value=round(val, 2 if pc in ("62614", "62615", "00065") else 0), unit=unit, param=pc,
                     trend=trend, trend_kind="comp" if trend else None)
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
        return _unav("usace", "Official lake level", "The latest USACE level is more than a week old.", "USACE Wilmington District")
    return _card("usace", "Official lake level", "stale" if fr == "stale" else "obs", "USACE Wilmington District · midnight report",
                 day.strftime("%b %-d"), value=round(elev, 2), unit="ft", guide=guide, vs_guide=round(elev - guide, 2),
                 note="Feet above mean sea level (NGVD29). The guide curve is the operator's seasonal target, not a safety line.")


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
        ev.append({"type": "High" if x["type"] == "H" else "Low", "time": _fmt(t), "day": t.strftime("%a"), "ft": round(float(x["v"]), 1), "ts": t.isoformat()})
    upcoming = [e for e in ev if datetime.fromisoformat(e["ts"]) >= now][:4]
    if not upcoming:
        return _unav("tide", "Tide predictions", "No upcoming predictions were returned.", "NOAA CO-OPS %s" % c["id"])
    return _card("tide", "Tide predictions", "pred", "NOAA CO-OPS %s · %s (%s)" % (c["id"], c.get("name", ""), c["relation"].replace("_", " ")),
                 "", events=upcoming, note="Astronomical predictions (feet above MLLW). Wind and pressure can shift actual water level and timing.")


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


# ---------- assemble
def assemble(site_id, f=FETCH, now=None, sites=None, records=None):
    sites = sites or load_sites()
    records = records or load_records()
    site, rec = sites[site_id], records[site_id]
    now = now or datetime.now(timezone.utc)
    cards = {"sun": sun_moon(rec, now.astimezone(ET).date())}
    jobs = {"forecast": lambda: nws_forecast(site, f, now), "alerts": lambda: nws_alerts(site, rec, f)}
    withheld = None
    if water_ok(site):
        usgs_ids = [c["id"] for c in site["stations"] if c["publishable"] and c["source"] == "USGS"]
        def usgs_cards():
            out = []
            try:
                series = usgs_batch(usgs_ids, f) if usgs_ids else {}
            except SourceDown:
                series = None
            for c in publishable(site, "lake_elevation", "river_stage_flow", "water_temp", "downstream_river_flow"):
                if c["source"] != "USGS":
                    continue
                key = {"lake_elevation": "lake", "river_stage_flow": "river:" + c["id"], "water_temp": "temp", "downstream_river_flow": "below_dam"}[c["type"]]
                if series is None:
                    out.append(_unav(key, "Gauge reading", "USGS water data could not be reached just now.", "USGS %s" % c["id"])); continue
                if c["type"] == "lake_elevation":
                    pcs = ("62614", "62615") if c.get("datum") != "NAVD88" else ("62615",)
                    d = "NAVD88" if pcs == ("62615",) else "NGVD29"
                    out.append(_usgs_card(key, "Lake elevation", c, series, pcs, "ft", now, note="Feet above %s at the gauge on this lake." % d))
                elif c["type"] == "water_temp":
                    out.append(_usgs_card(key, "Water temperature", c, series, ("00010",), "°F", now, note="Measured at the gauge on the same water, not at the ramp.", conv=lambda v: v * 9 / 5 + 32))
                elif c["type"] == "downstream_river_flow":
                    out.append(_usgs_card(key, "River flow below the dam (measured)", c, series, ("00060",), "cfs", now,
                                          note="Measured on the river downstream of the dam. A different water body from the lake, and not a reported dam release."))
                else:
                    rel = c["relation"].replace("same_river_", "")
                    kind = "obs" if (c.get("distance_mi") or 0) <= 1.0 else "rel"
                    card = _usgs_card(key, "River gauge · %s" % rel, c, series, ("00065", "00060"), "", now, kind=kind,
                                      note="Same river, %s mi %s, no dam between. Gauge height is not water depth at the ramp." % (c.get("distance_mi"), rel))
                    if card["kind"] != "unav":
                        card["unit"] = "ft" if card["param"] == "00065" else "cfs"
                    out.append(card)
            return out
        jobs["usgs"] = usgs_cards
        for c in publishable(site, "lake_elevation"):
            if c["source"] == "USACE":
                jobs["usace"] = (lambda c=c: usace_card(c, now, f))
        tide = publishable(site, "tide_predictions")
        if site["tide_policy"] == "predictions" and tide:
            jobs["tide"] = lambda: coops_card(tide[0], now, f)
    else:
        withheld = ("Water readings are withheld for this ramp until its water classification is confirmed (%s). Forecasts and alerts below do not depend on it."
                    % site["class_basis"])
    with ThreadPoolExecutor(max_workers=len(jobs)) as ex:
        futs = {k: ex.submit(fn) for k, fn in jobs.items()}
        for k, fu in futs.items():
            try:
                r = fu.result(timeout=SOURCES.get({"forecast": "nws_forecast", "alerts": "nws_alerts", "tide": "coops"}.get(k, k), {"timeout": 10})["timeout"] + 5)
            except Exception:
                r = _unav(k, k.title(), "This source did not answer in time.")
            for c in (r if isinstance(r, list) else [r]):
                cards[c["key"]] = c
    return {"id": site_id, "generated": now.isoformat(), "water_class": site["water_class"], "tide_policy": site["tide_policy"],
            "withheld": withheld, "cards": cards}
