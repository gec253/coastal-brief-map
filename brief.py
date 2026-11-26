"""Morning Brief: a short daily summary per enabled region, built only from verified readings.

On by default for saltwater regions. Set MORNING_BRIEF_ENABLED to 0, false, or off to disable
(a kill switch). The Falls Lake brief is public when freshwater is on (the default);
Jordan Lake and Neuse River do not have briefs.
Never includes market data. The Captain's take is produced by fixed
rules from the numbers in the brief; nothing is invented.

Schedule: an in-process thread prepares every enabled region at 05:15 ET and retries failed sections
until 05:30 ET. A GitHub Actions workflow keeps the service awake from about 4:35 AM ET, calls
/api/brief/wake after 05:15, verifies both saltwater briefs, and archives them to the brief-archive
branch (see docs/MORNING_BRIEF_AUTOMATION.md). If the service was asleep, the first request after 05:15
builds the brief on demand (and says so). Briefs are kept in memory and in cache/briefs/ (ephemeral on
Render); after a restart the latest archived copy is used before anything is rebuilt.

Every new brief is validated before it is stored or shown (region, location, issue date, timestamp,
marine zone, forecast age, core readings). A brief that fails a critical check is never published;
the last valid brief is shown with its date and a notice, or an unavailable message.

Automatic publication is authorized through AUTO_PUBLISH_UNTIL (ET calendar date; override with the
MORNING_BRIEF_AUTO_UNTIL env var). After that date no new briefs are built, by the schedule, the wake
endpoint, or page views; the last published brief stays up, clearly dated, with a paused notice.
"""
from __future__ import annotations

import html
import json
import os
import re
import sys
import threading
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import brief_astro
import brief_format
import conditions

ET = ZoneInfo("America/New_York")
ROOT = Path(__file__).resolve().parent
STORE = ROOT / "cache" / "briefs"
PREP = (5, 15)
PUBLISH_BY = (5, 30)
# Ed authorized unattended publication for Nov 14-20, 2026 (ET). Extend only with his OK: change this
# date (and AUTO_UNTIL in .github/workflows/morning-brief-wake.yml), or set MORNING_BRIEF_AUTO_UNTIL.
AUTO_PUBLISH_UNTIL = "2026-11-30"
MAX_FORECAST_AGE_H = 24  # an NWS marine or point forecast older than this is not used
ARCHIVE_URL = "https://raw.githubusercontent.com/gec253/coastal-brief-map/brief-archive/latest/%s.json"
_lock = threading.Lock()
_mem: dict[str, dict] = {}
_rlocks: dict[str, threading.Lock] = {}
_last_error: dict[str, dict] = {}
_arch_cache: dict[str, tuple[float, dict | None]] = {}
_thread = None


class BriefInvalid(RuntimeError):
    """A new brief failed a critical check and must not be published."""

    def __init__(self, errors):
        super().__init__("; ".join(errors))
        self.errors = list(errors)


def auto_until() -> str:
    v = (os.environ.get("MORNING_BRIEF_AUTO_UNTIL") or "").strip()
    return v if re.fullmatch(r"\d{4}-\d{2}-\d{2}", v) else AUTO_PUBLISH_UNTIL


def auto_active(now: datetime | None = None) -> bool:
    """True while new briefs may be built without Ed: the ET calendar date is on or before auto_until()."""
    now = now or datetime.now(timezone.utc)
    return _et(now).strftime("%Y-%m-%d") <= auto_until()


def _region_lock(rid: str) -> threading.Lock:
    with _lock:
        return _rlocks.setdefault(rid, threading.Lock())


def flag_on() -> bool:
    """Saltwater briefs are on unless MORNING_BRIEF_ENABLED is explicitly 0, false, or off."""
    v = (os.environ.get("MORNING_BRIEF_ENABLED") or "").strip().lower()
    return v not in ("0", "false", "off")


def enabled_regions(include_fresh: bool | None = None) -> list[str]:
    """Regions that get a Morning Brief (build, wake, validation, archive, /brief).

    A saltwater region needs to be public (enabled, not draft) AND carry "brief": true in
    data/regions.json. Today that is only Crystal Coast and Hatteras, the two regions Ed
    authorized for automatic publication. Making a region public on the map does not give
    it a brief; adding one needs Ed's OK and the workflow's REGIONS list updated too."""
    cfg = conditions.load_regions()
    out = [r["id"] for r in cfg.get("regions") or [] if conditions._servable(r) and r.get("brief") is True]
    try:  # freshwater regions only when their own flag is on (or for a preview browser)
        import freshwater
        if freshwater.flag_on() if include_fresh is None else include_fresh:
            # Only Falls Lake has a Morning Brief. Jordan and Neuse are lake/river pages only.
            out += [rid for rid, r in freshwater.regions().items()
                    if r.get("previewReady") and rid == "falls-lake"]
    except Exception:
        pass
    return out


def _et(dt: datetime) -> datetime:
    return dt.astimezone(ET)


def _t(iso_or_dt) -> str:
    d = iso_or_dt if isinstance(iso_or_dt, datetime) else datetime.fromisoformat(str(iso_or_dt).replace("Z", "+00:00"))
    s = _et(d).strftime("%-I:%M %p") + " ET"
    if _et(d).date() != datetime.now(ET).date():
        s = _et(d).strftime("%a ") + s
    return s


def _issue_date(now: datetime) -> str:
    """The brief 'day' an instant belongs to: before 05:15 ET it is still yesterday's brief."""
    e = _et(now)
    if (e.hour, e.minute) < PREP:
        e -= timedelta(days=1)
    return e.strftime("%Y-%m-%d")


# ------------------------------------------------------------------ overnight trends
def _trend(sid: str, key: str, now: datetime, scale: float = 1.0):
    """Value now and about 10 h ago (8-12 h window) from an NDBC realtime2 file."""
    rows, url = conditions.ndbc_rows(sid)
    if not rows:
        return None
    cur = next((r for r in rows if conditions.num(r, key) is not None), None)
    if not cur:
        return None
    target = cur["_dt"] - timedelta(hours=10)
    cands = [r for r in rows if conditions.num(r, key) is not None and timedelta(hours=8) <= cur["_dt"] - r["_dt"] <= timedelta(hours=12)]
    if not cands:
        return None
    old = min(cands, key=lambda r: abs((r["_dt"] - target).total_seconds()))
    return {"now": conditions.num(cur, key) * scale, "then": conditions.num(old, key) * scale,
            "tNow": cur["_dt"], "tThen": old["_dt"], "hours": round((cur["_dt"] - old["_dt"]).total_seconds() / 3600), "station": sid, "url": url}


def _dir_word(delta, unit, up="up", down="down", flat="steady", eps=0.0):
    if delta is None:
        return ""
    if abs(delta) <= eps:
        return flat
    return ("%s %s %s" % (up if delta > 0 else down, ("%.1f" % abs(delta)).rstrip("0").rstrip("."), unit)).strip()


# ------------------------------------------------------------------ saltwater brief
# Brief-only wind backup (Ed approved plan item 2, t322u, Nov 18 2026). The region's configured wind
# reading stays the primary (Hatteras: Diamond Shoals buoy 41025, offshore). Only when the primary is
# not "ok" under the existing staleness rule (conditions.STALE_MIN / staleAfterMin) does the brief use
# the shore station's wind, which conditions.assemble already fetches as "harborWind", and only if
# that reading is itself "ok" under its own rule (45 min). The backup is labeled as a coastal (shore)
# observation with its station and time, the stale buoy is still named as not used, and the two are
# never blended. The map's wind tile is unchanged.
# Canonical config and freshness check live in conditions.py so the dashboard
# and homepage use the same backup-source rule as this brief.
WIND_BACKUP = conditions.WIND_BACKUP
SHORE_WIND_NOTE = conditions.SHORE_WIND_NOTE


def _wind_backup(rid: str, R: dict):
    """The configured backup wind reading for this region when it is fresh, else None."""
    return conditions.wind_backup_ok(rid, R)


def _primary_state(r: dict | None) -> str:
    """'stale since 12:30 AM ET' or 'not reporting', for an unusable primary wind reading."""
    if r and r.get("status") == "stale" and r.get("time"):
        return "stale since %s" % _t(r["time"])
    if r and r.get("lastReport"):
        return "stale since %s" % _t(r["lastReport"])
    return "not reporting"


def _no_inshore_sensor(rid: str) -> bool:
    """True when the region config lists no inshore water-temp source at all (data/regions.json)."""
    try:
        cfg = next((r for r in conditions.load_regions().get("regions") or [] if r.get("id") == rid), None) or {}
        spec = (cfg.get("readings") or {}).get("waterTemp")
        return isinstance(spec, dict) and not (spec.get("sources") or [])
    except Exception:
        return False


def _is_ndbc(sid: str) -> bool:
    try:
        return ((conditions.load_regions().get("stations") or {}).get(sid) or {}).get("type") == "ndbc"
    except Exception:
        return False


def _swell_at_seas_time(R: dict) -> dict:
    """The swell reading, taken from the same NDBC spectral row as the seas observation when the two
    come from one buoy and that row has swell fields; otherwise the swell reading unchanged (it then
    carries its own observation time). Height, period and direction always come from one row."""
    sw, se = R.get("swell") or {}, R.get("seas") or {}
    sid = (sw.get("station") or {}).get("id")
    if not (sid and se.get("status") == "ok" and (se.get("station") or {}).get("id") == sid
            and se.get("time") and sw.get("time") != se.get("time")):
        return sw
    try:
        rows, _url = conditions.ndbc_rows(sid, "spec")
        want = datetime.fromisoformat(str(se["time"]).replace("Z", "+00:00"))
        rec = next((r for r in rows or [] if r.get("_dt") == want), None)
        if not rec:
            return sw
        swh, swp = conditions.num(rec, "SwH"), conditions.num(rec, "SwP")
        swd = rec.get("SwD") if rec.get("SwD") not in (None, "MM", "N/A") else None
        if swh is None or swp is None or not swd:
            return sw
        vals = dict(sw.get("values") or {})
        vals.update({"heightFt": conditions.r1(swh * conditions.M_TO_FT), "periodS": conditions.r1(swp), "dirCompass": swd})
        return {**sw, "time": se["time"], "values": vals}
    except Exception:
        return sw


def _official_alerts(block: dict | None, url: str | None, fetch) -> dict:
    """The brief's own alert list from the raw NWS feed (t448u).

    conditions/freshwater (protected public files) collapse alerts that share an event name and end
    time. The brief re-reads the same api.weather.gov URL through the same cached fetcher, so
    normally no extra request is made, and keeps every distinct alert with its full official text.
    If the raw feed cannot be read, the shared block is used as before."""
    block = dict(block or {})
    if block.get("status") != "ok" or not url:
        return block
    try:
        raw = fetch(url)
    except Exception:
        raw = None
    if not isinstance(raw, dict) or not isinstance(raw.get("features"), list):
        return block
    block["items"] = brief_format.nws_alert_items(raw["features"])
    block["source"] = "nws-raw"
    return block


def build_salt(rid: str, now: datetime) -> dict:
    st, d = conditions.assemble(rid)
    if st != 200 or not d.get("ok"):
        raise RuntimeError("conditions unavailable")
    R = d["readings"]
    ok = lambda k: R.get(k, {}).get("status") == "ok"
    items, fresh, take, missing = [], [], [], []

    def miss(name, r):
        # Never substitute: a stale or absent reading is listed as not used, with its last time if known.
        if r and r.get("status") == "stale" and r.get("time"):
            missing.append("%s (stale: last report %s, not used)" % (name, _t(r["time"])))
        else:
            missing.append(name)

    def fc_age_h(block):
        try:
            u = datetime.fromisoformat(str(block.get("updated")).replace("Z", "+00:00"))
            return (now - u).total_seconds() / 3600, u
        except (TypeError, ValueError):
            return None, None

    def fr(label, r):
        if r and r.get("time"):
            age = r.get("ageMin")
            fresh.append({"label": label, "time": _t(r["time"]), "station": (r.get("station") or {}).get("id"), "stale": bool(age is not None and r.get("staleAfterMin") and age > r["staleAfterMin"])})

    # advisories first — current vs upcoming, with start, end, and affected waters
    al = d.get("alerts") or {}
    if al.get("zones"):
        # Same URL conditions.alerts_block used, read through the same cache.
        al = _official_alerts(al, "https://api.weather.gov/alerts/active?status=actual&zone=" + ",".join(al["zones"]),
                              lambda u: conditions.nws_json(u, conditions.TTL_ALERTS))
    hazards = brief_format.format_hazards(al, now, al.get("zones"))
    items.append(("Advisories", hazards["line"]))
    if hazards["status"] == "unknown":
        missing.append("advisories")

    wind_tr = seas_tr = pres_tr = None
    parsed_outlook = None
    wind_src = None
    if ok("wind"):
        w = R["wind"]; v = w["values"]; fr("Wind", w)
        wind_tr = _trend(w["station"]["id"], "WSPD", now, conditions.MS_TO_KT)
        line = "%d kt from the %s, gusting %d, at %s" % (round(v["speedKt"]), v["dirCompass"], round(v["gustKt"] or v["speedKt"]), w["station"]["name"])
        if rid in WIND_BACKUP:  # name the offshore buoy and its observation time, so primary and backup read differently
            line += " (offshore buoy %s, observed %s)" % (w["station"].get("id"), _t(w["time"]))
        if wind_tr:
            line += "; %s from %d kt %d h earlier" % ("up" if wind_tr["now"] - wind_tr["then"] > 2 else "down" if wind_tr["then"] - wind_tr["now"] > 2 else "about steady", round(wind_tr["then"]), wind_tr["hours"])
        items.append(("Wind", line + "."))
        if rid in WIND_BACKUP:
            wind_src = {"role": "primary", "type": "offshore", "station": w["station"].get("id"), "name": w["station"].get("name"),
                        "observed": w["time"]}
    else:
        bcfg, bk = _wind_backup(rid, R)
        prim = R.get("wind")
        if bk:
            # Primary stale or missing, shore station fresh: show the shore reading, labeled as such.
            v = bk["values"]; state = _primary_state(prim)
            fresh.append({"label": "Wind (coastal backup)", "time": _t(bk["time"]), "station": bcfg["station"], "stale": False})
            line = ("Coastal backup, %s (%s), observed %s: %d kt from the %s, gusting %d. %s %s, not used. %s"
                    % (bcfg["name"], bcfg["setting"], _t(bk["time"]), round(v["speedKt"]), v["dirCompass"],
                       round(v.get("gustKt") or v["speedKt"]), bcfg["primaryName"][0].upper() + bcfg["primaryName"][1:], state, SHORE_WIND_NOTE))
            items.append(("Wind", line))
            # Validation is unchanged: the stale primary is still listed, so the brief stays "partial"
            # and the 5:15-5:30 retries keep trying for the buoy (a retry with the buoy back wins).
            missing.append("offshore wind, %s (%s, not used; coastal backup shown)" % (bcfg["primaryName"], state.replace("stale since", "stale: last report")))
            wind_src = {"role": "backup", "type": "coastal", "station": bcfg["station"], "name": bcfg["name"], "observed": bk["time"],
                        "primary": {"station": ((prim or {}).get("station") or {}).get("id") or bcfg["primaryName"].split()[-1],
                                    "state": state, "lastReport": (prim or {}).get("time") or (prim or {}).get("lastReport")}}
        elif bcfg and bcfg["reading"] in R:
            # Both stale or missing: no wind is shown; say why for each source.
            b_r = R.get(bcfg["reading"]) or {}
            b_state = _primary_state(b_r)
            missing.append("wind (%s %s; coastal backup %s %s; neither used)"
                           % (bcfg["primaryName"], _primary_state(prim).replace("stale since", "stale: last report"),
                              bcfg["name"], b_state.replace("stale since", "stale: last report")))
            wind_src = {"role": "none", "state": "unavailable"}
        else:
            miss("wind", prim)
    if ok("seas"):
        s = R["seas"]; v = s["values"]; fr("Seas", s)
        seas_tr = _trend(s["station"]["id"], "WVHT", now, conditions.M_TO_FT)
        line = "%.1f ft every %d s from the %s at %s" % (v["heightFt"], round(v["dominantPeriodS"]), v["meanDirCompass"], s["station"]["name"])
        if seas_tr:
            dlt = seas_tr["now"] - seas_tr["then"]
            line += "; %s from %.1f ft %d h earlier" % ("building" if dlt > 0.5 else "easing" if dlt < -0.5 else "little changed", seas_tr["then"], seas_tr["hours"])
        items.append(("Seas", line + "."))
    else:
        miss("seas", R.get("seas"))
    if ok("swell"):
        swr = _swell_at_seas_time(R)
        sw = swr["values"]; fr("Swell", swr)
        line = "%.1f ft at %.0f s from the %s (split from the buoy spectrum" % (sw["heightFt"], sw["periodS"], sw["dirCompass"])
        if swr.get("time") and (not ok("seas") or swr.get("time") != R["seas"].get("time")):
            line += ", observed %s" % _t(swr["time"])  # different row than the seas: give its own time
        items.append(("Swell", line + ")."))
    elif "swell" in R:
        miss("swell", R["swell"])
    if "pressure" in R and not ok("pressure"):
        miss("pressure", R["pressure"])
    if ok("pressure"):
        p = R["pressure"]; fr("Barometer", p)
        # Value, 3-hour trend and overnight trend all come from the station that produced the
        # reading, and only that station is named (Nov 19: the value was CO-OPS 8654467 but the
        # overnight trend and the name came from the wind buoy 41025).
        pst = p.get("station") or {}
        psid = pst.get("id")
        if psid and _is_ndbc(psid):
            pres_tr = _trend(psid, "PRES", now)
        # A buoy barometer may have no 3-hour change; say so instead of printing "None".
        # CO-OPS has no NDBC overnight file: the reading's own 3-hour trend stands alone.
        line = "%.2f inHg, %s" % (p["values"]["inHg"], p["values"].get("trend") or "3-hour trend not reported")
        if pres_tr and pres_tr["station"] == psid:
            line += ", %s hPa over %d h at %s" % (_dir_word(pres_tr["now"] - pres_tr["then"], "", "up", "down", "steady", 0.4), pres_tr["hours"], psid)
        items.append(("Pressure", line + "."))
    mar = d.get("marine") or {}
    mar_age, mar_upd = fc_age_h(mar)
    if mar.get("status") == "ok" and mar.get("periods") and mar_age is not None and mar_age > MAX_FORECAST_AGE_H:
        missing.append("marine forecast (stale: NWS issued %s, not used)" % _t(mar_upd))
        mar = {**mar, "status": "stale"}
    elif mar.get("status") == "ok" and mar.get("periods"):
        first = re.split(r"(?<=\.)\s", mar["periods"][0]["text"].strip())[0]
        items.append(("Marine forecast", "%s: %s (NWS %s)" % (mar["periods"][0]["name"], first, mar.get("zone"))))
        parsed_outlook = brief_format.outlook_periods(mar)
        outlook = brief_format.format_outlook(mar)
        if outlook:
            items.append(("Outlook", outlook))
    else:
        missing.append("marine forecast")
    fc = d.get("forecast") or {}
    fc_age, fc_upd = fc_age_h(fc)
    if fc.get("status") == "ok" and fc.get("periods") and fc_age is not None and fc_age > MAX_FORECAST_AGE_H:
        missing.append("rain forecast (stale: NWS issued %s, not used)" % _t(fc_upd))
    elif fc.get("status") != "ok" or not fc.get("periods"):
        missing.append("rain forecast")
    else:
        ps = fc["periods"][:2]
        rain = max(p.get("pop") or 0 for p in ps)
        day = brief_format.daytime_period(fc.get("periods") or [], now)
        if day and day.get("tempF") is not None:
            short = (day.get("short") or "").lower() or "forecast"
            items.append(("Rain", "%d%% chance through tonight; %s, high %s°F." % (rain, short, day["tempF"])))
        else:
            items.append(("Rain", "%d%% chance through tonight. Today's high is unavailable." % rain))
    t = d.get("tides") or {}
    if t.get("status") != "ok":
        missing.append("tides")
    if t.get("status") == "ok":
        day = _et(now).date()
        evs = [e for e in t["events"] if datetime.fromtimestamp(e["t"] / 1000, timezone.utc).astimezone(ET).date() == day]
        if not evs:
            missing.append("tides")
        if evs:
            items.append(("Tides", ", ".join("%s %s (%.1f ft)" % ("high" if e["type"] == "H" else "low", _t(datetime.fromtimestamp(e["t"] / 1000, timezone.utc)), e["v"]) for e in evs) + " at %s, MLLW." % t["station"]["name"]))
        ob = t.get("observed") or {}
        if ob.get("status") == "ok" and ob.get("latest"):
            fresh.append({"label": "Water level", "time": _t(datetime.fromtimestamp(ob["latest"]["t"] / 1000, timezone.utc)), "station": t["station"]["id"], "stale": False})
    if ok("waterTemp"):
        wt = R["waterTemp"]; fr("Water temp", wt)
        line = "%.0f°F inshore (%s)" % (wt["values"]["f"], wt["station"]["name"])
        if ok("waterTempOffshore"):
            line += ", %.0f°F offshore (buoy %s)" % (R["waterTempOffshore"]["values"]["f"], R["waterTempOffshore"]["station"]["id"])
        items.append(("Water temp", line + "."))
    elif ok("waterTempOffshore") and _no_inshore_sensor(rid):
        # No inshore sensor exists in this region (not a sensor that is down): show the offshore
        # buoy, labeled offshore, and say inshore is unavailable. Nothing is substituted.
        wo = R["waterTempOffshore"]; fr("Offshore water temp", wo)
        items.append(("Water temp", "Inshore unavailable (no sensor in this area); %.0f°F offshore at %s."
                      % (wo["values"]["f"], (wo.get("station") or {}).get("name") or (wo.get("station") or {}).get("id"))))
    else:
        miss("water temp", R.get("waterTemp"))

    for i, (k, v) in enumerate(items):
        if k in ("Seas", "Swell") and "not a beach surf height" not in v.lower():
            items[i] = (k, v.rstrip(".") + ". Offshore buoy observation, not a beach surf height.")

    # ---- Captain's take: fixed rules over the numbers above ----
    # Upcoming or current official hazards, with start/end/area. Never "is in effect"
    # for a watch whose onset is still in the future.
    if hazards.get("status") == "active":
        # Lead with the most serious official hazard (warning > watch > advisory), current first.
        rank = {"warning": 0, "watch": 1, "advisory": 2, "statement": 3}
        sig = sorted((hazards.get("current") or []) + (hazards.get("upcoming") or []),
                     key=lambda r: (rank.get(r.get("kind") or brief_format.hazard_kind(r.get("event") or ""), 9),
                                    0 if r.get("status") == "current" else 1))
        if sig:
            take.append(sig[0]["text"])
    if wind_tr:
        dlt = wind_tr["now"] - wind_tr["then"]
        if dlt <= -4:
            take.append("Wind has eased %d kt over the past %d h." % (round(-dlt), wind_tr["hours"]))
        elif dlt >= 4:
            take.append("Wind has built %d kt over the past %d h." % (round(dlt), wind_tr["hours"]))
    if ok("seas") and R["seas"]["values"]["dominantPeriodS"] < 7 and R["seas"]["values"]["heightFt"] >= 3:
        take.append("Seas are short-period wind chop, so expect a steep, close-together ride.")
    easing_ok = brief_format.take_easing_allowed(al.get("items") or [], mar, now)
    if (mar.get("status") == "ok" and mar.get("periods")
            and re.search(r"diminish|subsid", mar["periods"][0]["text"], re.I)
            and easing_ok):
        take.append("The NWS marine forecast has wind or seas easing later today.")
    elif mar.get("status") == "ok" and mar.get("periods") and re.search(r"increas|build", mar["periods"][0]["text"], re.I):
        take.append("The NWS marine forecast has wind or seas building later today.")
    if ok("waterTemp") and ok("waterTempOffshore"):
        gap = R["waterTempOffshore"]["values"]["f"] - R["waterTemp"]["values"]["f"]
        if abs(gap) >= 3:
            take.append("Offshore water is %d°F %s than inshore." % (round(abs(gap)), "warmer" if gap > 0 else "cooler"))
    if not take:
        take.append("No advisories and no big overnight changes in the readings.")
    out = {"region": d["region"], "waterType": "saltwater", "items": items, "freshness": fresh, "take": take[:4], "missing": missing,
            "hazards": hazards,
            "marineZone": (d.get("marine") or {}).get("zone"), "marineUpdated": (d.get("marine") or {}).get("updated"),
            "forecastUpdated": fc.get("updated"),
            "sources": "NOAA NDBC, NOAA CO-OPS, NWS (api.weather.gov)"}
    if parsed_outlook:
        out["outlookPeriods"] = parsed_outlook
    if wind_src:
        out["windSource"] = wind_src
    return out


# ------------------------------------------------------------------ freshwater brief (Falls Lake)
def build_fresh(rid: str, now: datetime) -> dict:
    import freshwater
    st, d = freshwater.assemble(rid)
    if st != 200:
        raise RuntimeError("freshwater unavailable")
    L = d["lake"]; items, fresh, take, missing = [], [], [], []
    al = d.get("alerts") or {}
    rcfg = (freshwater.regions() or {}).get(rid) or {}
    pt = rcfg.get("alertPoint") or [(rcfg.get("anchor") or {}).get("lat"), (rcfg.get("anchor") or {}).get("lon")]
    if pt and None not in pt:
        # Same URL freshwater.alerts_point used, read through the same cache.
        al = _official_alerts(al, "https://api.weather.gov/alerts/active?status=actual&point=%.4f,%.4f" % (pt[0], pt[1]),
                              lambda u: freshwater._get_json(u, 300))
    hazards = brief_format.format_fresh_alerts(al, now)
    items.append(("Alerts", hazards["line"]))
    if L.get("elevation"):
        e = L["elevation"]; fresh.append({"label": "Lake level", "time": _t(e["time"]), "station": L["usgs"], "stale": e.get("stale")})
        items.append(("Lake level", "%.2f ft (NGVD29), %.2f ft %s the %.1f ft guide curve; %s ft in 24 h." % (e["value"], abs(L["vsGuideFt"]), "below" if L["vsGuideFt"] < 0 else "above", L["guideCurveFt"], ("%+.2f" % L["change24hFt"]) if L.get("change24hFt") is not None else "n/a")))
    else:
        missing.append("lake level")
    rel = d.get("release") or {}
    if rel.get("flowCfs"):
        items.append(("Dam release", "%d cfs below Falls Dam (regulated)%s." % (round(rel["flowCfs"]["value"]), ", " + rel["band"]["label"].lower() if rel.get("band") else "")))
    else:
        missing.append("dam release")
    inf = [i for i in d.get("inflows") or [] if i.get("flowCfs")]
    if inf:
        items.append(("Inflows", "; ".join("%s %s cfs%s" % (i["label"], ("%.1f" % i["flowCfs"]["value"]).rstrip("0").rstrip("."), ", " + i["band"]["label"].lower() if i.get("band") else "") for i in inf) + "."))
    wt = d.get("waterTemp") or {}
    if wt.get("status") == "ok":
        fresh.append({"label": "Water temp", "time": _t(wt["time"]), "station": wt["usgs"], "stale": wt.get("stale")})
        items.append(("Water temp", "%.0f°F at the dam sensor." % wt["f"]))
    else:
        missing.append("water temp")
    rn = d.get("rain") or {}
    if rn.get("status") == "ok":
        q = rn.get("qpf") or {}
        items.append(("Rain", "%.2f in last 24 h at the dam; NWS forecast %s in next 24 h." % (rn["last24In"], ("%.2f in" % q["next24In"]) if q.get("status") == "ok" else "unavailable")))
    fc = d.get("forecast") or {}
    if fc.get("status") == "ok" and fc.get("periods"):
        p = brief_format.daytime_period(fc.get("periods") or [], now)
        if p and p.get("tempF") is not None:
            items.append(("Weather", "%s, high %s°F, wind %s %s." % (p.get("short") or "Forecast", p["tempF"], p.get("windDir") or "", p.get("windMph") or "")))
        else:
            items.append(("Weather", "Today's high is unavailable."))
    else:
        missing.append("weather forecast")
    if L.get("vsGuideFt") is not None and L["vsGuideFt"] <= -3:
        take.append("The lake is %.1f ft below its guide curve, so more shoreline is exposed than usual; check NCWRC ramp notices before launching." % abs(L["vsGuideFt"]))
    if rel.get("band") and rel["band"].get("key") in ("record-low", "much-below"):
        take.append("Flow below the dam is very low for the date.")
    if al.get("items"):
        take.append("Check the %s before an early start." % al["items"][0]["event"])
    if not take:
        take.append("Lake and river readings are close to normal for the date.")
    return {"region": d["region"], "waterType": "freshwater", "items": items, "freshness": fresh, "take": take[:4], "missing": missing,
            "hazards": hazards, "sources": "USGS, USACE Wilmington District, NWS"}


# ------------------------------------------------------------------ validate
SALT_CORE = ("Advisories", "Wind", "Seas", "Marine forecast", "Tides", "Water temp")
FRESH_CORE = ("Lake level", "Dam release", "Water temp", "Weather")


def _region_cfg(rid: str, fw: bool) -> dict | None:
    try:
        if fw:
            import freshwater
            return freshwater.regions().get(rid)
        return next((r for r in conditions.load_regions().get("regions") or [] if r.get("id") == rid), None)
    except Exception:
        return None


def validate(b: dict, rid: str, now: datetime) -> tuple[list[str], dict]:
    """Critical checks before a new brief may be published. Returns (errors, summary).

    Any error means the brief is not stored or shown. Individual missing or stale readings are not
    errors; they are listed in b["missing"] and shown as not available."""
    errs: list[str] = []
    fw = b.get("waterType") == "freshwater"
    cfg = _region_cfg(rid, fw)
    reg = b.get("region") or {}
    if not cfg:
        errs.append("region %s is not configured" % rid)
    else:
        if b.get("regionId") != rid or reg.get("id") != rid:
            errs.append("region id mismatch (%s)" % reg.get("id"))
        if reg.get("name") != cfg.get("name"):
            errs.append("region name does not match the configuration")
        if cfg.get("anchor") and reg.get("anchor") != cfg.get("anchor"):
            errs.append("location does not match the configuration")
        if not fw:
            zone = (cfg.get("marine") or {}).get("zone")
            if b.get("marineZone") != zone:
                errs.append("marine zone %s is not the configured zone %s" % (b.get("marineZone"), zone))
    if b.get("issueDate") != _issue_date(now):
        errs.append("issue date %s is not today's (%s)" % (b.get("issueDate"), _issue_date(now)))
    try:
        issued = datetime.fromisoformat(str(b.get("issuedAt")))
        if issued.tzinfo is None or abs((issued - now).total_seconds()) > 600:
            errs.append("issue timestamp is not current")
    except ValueError:
        errs.append("issue timestamp is missing or invalid")
    labels = {k for k, _ in b.get("items") or []}
    core = FRESH_CORE if fw else SALT_CORE
    missing_core = [c for c in core if c not in labels or (c == "Advisories" and "advisories" in (b.get("missing") or []))]
    if not fw and "Marine forecast" not in labels and "Rain" not in labels:
        errs.append("no NWS forecast at all")
    if len(missing_core) * 2 > len(core):
        errs.append("most core readings are missing (%s)" % ", ".join(missing_core).lower())
    summary = {"status": "failed" if errs else ("partial" if b.get("missing") else "ok"),
               "checkedAt": now.isoformat(), "missingCore": [c.lower() for c in missing_core],
               "checks": ["region", "location", "issue date", "timestamp"] + ([] if fw else ["marine zone", "forecast age"]) + ["core readings"]}
    return errs, summary


# ------------------------------------------------------------------ build, store, serve
def compose(rid: str, reason: str, now: datetime | None = None) -> dict:
    """Build and validate a brief without storing it. Raises BriefInvalid on a critical failure."""
    now = now or datetime.now(timezone.utc)
    fw = rid in ("falls-lake", "neuse-river", "jordan-lake")
    body = build_fresh(rid, now) if fw else build_salt(rid, now)
    if rid in brief_astro.REGIONS:
        body["astro"] = brief_astro.for_brief(rid, _et(now).date())
    words = len(" ".join([v for _, v in body["items"]] + body["take"]).split())
    b = {"ok": True, "regionId": rid, "issueDate": _issue_date(now), "issuedAt": now.isoformat(), "issuedEt": _et(now).strftime("%a %b %-d, %-I:%M %p ET"),
         "reason": reason, "words": words, **body}
    errs, summary = validate(b, rid, now)
    if errs:
        raise BriefInvalid(errs)
    b["validation"] = summary
    return b


def _save(rid: str, b: dict) -> None:
    with _lock:
        _mem[rid] = b
        _last_error.pop(rid, None)
    try:
        STORE.mkdir(parents=True, exist_ok=True)
        (STORE / ("%s.json" % rid)).write_text(json.dumps(b))
    except OSError:
        pass


def _fail(rid: str, now: datetime, e: Exception) -> None:
    with _lock:
        _last_error[rid] = {"at": now.isoformat(), "error": "; ".join(getattr(e, "errors", None) or [str(e) or type(e).__name__])}


def build(rid: str, reason: str, now: datetime | None = None) -> dict:
    """Compose, validate, and store a brief. Raises if it cannot be built or fails validation."""
    now = now or datetime.now(timezone.utc)
    try:
        b = compose(rid, reason, now)
    except Exception as e:
        _fail(rid, now, e)
        raise
    _save(rid, b)
    return b


def _stored(rid: str):
    with _lock:
        if rid in _mem:
            return _mem[rid]
    try:
        b = json.loads((STORE / ("%s.json" % rid)).read_text())
        with _lock:
            _mem[rid] = b
        return b
    except (OSError, ValueError):
        return None


def _archived(rid: str):
    """Latest brief the workflow archived to the brief-archive branch, for use after a restart.

    Read-only, short timeout, cached 10 minutes. Off when MORNING_BRIEF_ARCHIVE_URL is set to empty."""
    url = os.environ.get("MORNING_BRIEF_ARCHIVE_URL", ARCHIVE_URL)
    if not url:
        return None
    hit = _arch_cache.get(rid)
    if hit and time.time() - hit[0] < 600:
        return hit[1]
    b = None
    try:
        req = urllib.request.Request(url % rid if "%s" in url else url, headers={"User-Agent": "TheCoastalBrief/1.0"})
        with urllib.request.urlopen(req, timeout=6) as r:
            cand = json.loads(r.read(500_000).decode("utf-8"))
        if (isinstance(cand, dict) and cand.get("ok") is True and cand.get("regionId") == rid and not cand.get("staleNotice")
                and re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(cand.get("issueDate"))) and isinstance(cand.get("items"), list)
                and isinstance(cand.get("issuedEt"), str)):
            b = cand
    except Exception:
        b = None
    _arch_cache[rid] = (time.time(), b)
    return b


def _previous(rid: str):
    return _stored(rid) or _archived(rid)


def _today(rid: str, want: str):
    """Today's published brief for a region, or None.

    Checks memory and the local cache first, then the brief-archive copy (the same source get()
    uses after a restart). A deploy wipes memory and cache/briefs, so without the archive check a
    later wake or page view would rebuild today's 5:15 brief as "on-request" and the workflow would
    archive that copy over the scheduled one (Nov 16 and Nov 19). An archived brief for today is
    adopted as the stored brief, so it is served and never rebuilt."""
    b = _stored(rid)
    if b and b.get("issueDate") == want:
        return b
    a = _archived(rid)
    if a and a.get("issueDate") == want:
        with _lock:
            cur = _mem.get(rid)
            if cur and cur.get("issueDate") == want:
                return cur
            _mem[rid] = a
        try:
            STORE.mkdir(parents=True, exist_ok=True)
            (STORE / ("%s.json" % rid)).write_text(json.dumps(a))
        except OSError:
            pass
        return a
    return None


def _ensure(rid: str, reason: str, now: datetime, want: str) -> dict:
    """Build today's brief once per region per day: concurrent callers wait, then reuse it.

    "Already built today" includes a brief archived before a restart or deploy."""
    with _region_lock(rid):
        b = _today(rid, want)
        if b:
            return b
        return build(rid, reason, now)


def status(include_fresh: bool = False, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    want = _issue_date(now)
    out = {}
    for rid in enabled_regions(include_fresh):
        b = _stored(rid) or {}
        out[rid] = {"today": b.get("issueDate") == want, "issuedAt": b.get("issuedAt"), "reason": b.get("reason"),
                    "validation": (b.get("validation") or {}).get("status"), "lastError": (_last_error.get(rid) or {}).get("error")}
    return out


def wake(include_fresh: bool = False, now: datetime | None = None, background: bool = True) -> dict:
    """Build today's brief for every region that lacks one, in the background. Returns no brief content.

    Before 05:15 ET it builds nothing (it only wakes the service); after the authorized window it
    builds nothing. Each region is built independently, so one failure never blocks another."""
    now = now or datetime.now(timezone.utc)
    want = _issue_date(now)
    e = _et(now)
    base = {"ok": True, "issueDate": want, "autoUntil": auto_until(), "nowEt": e.strftime("%Y-%m-%d %H:%M %Z")}
    if (e.hour, e.minute) < PREP:
        return {**base, "building": 0, "waiting": "before 5:15 AM ET; nothing is built yet", "regions": status(include_fresh, now)}
    if not auto_active(now):
        return {**base, "building": 0, "paused": "automatic publication ended after %s" % auto_until(), "regions": status(include_fresh, now)}
    on_time = PREP <= (e.hour, e.minute) <= (PUBLISH_BY[0], PUBLISH_BY[1] + 15)
    # A brief already published today (in memory, the local cache, or the archive after a deploy)
    # is never rebuilt by a wake.
    todo = [rid for rid in enabled_regions(include_fresh) if not _today(rid, want)]

    def run():
        for rid in todo:
            try:
                _ensure(rid, "scheduled" if on_time else "on-request", datetime.now(timezone.utc) if background else now, want)
            except Exception:
                pass  # recorded in _last_error; the next region still runs
    if todo:
        if background:
            threading.Thread(target=run, name="brief-wake", daemon=True).start()
        else:
            run()
    return {**base, "building": len(todo), "regions": status(include_fresh, now)}


def get(rid: str, now: datetime | None = None, include_fresh: bool | None = None) -> tuple[int, dict]:
    if rid not in enabled_regions(include_fresh):
        return 404, {"ok": False, "error": "No brief for this region."}
    now = now or datetime.now(timezone.utc)
    want = _issue_date(now)
    b = _today(rid, want)  # memory/cache, or today's archived brief published before a restart
    if b:
        return 200, b
    if not auto_active(now):
        # Window over: never build a new brief. Keep the last one up, clearly dated.
        prev = _previous(rid)
        note = "Automatic Morning Brief publication is paused (the authorized period ended %s). " % datetime.strptime(auto_until(), "%Y-%m-%d").strftime("%b %-d, %Y")
        if prev:
            return 200, {**prev, "current": False, "staleNotice": note + "This is the last published brief, from %s." % prev.get("issuedEt")}
        return 503, {"ok": False, "error": note + "Live readings are on the conditions page."}
    # Scheduled build missing (service asleep or restarted): build now and say so.
    try:
        return 200, _ensure(rid, "on-request", now, want)
    except Exception as e:
        prev = _previous(rid)
        why = "it did not pass the data checks" if isinstance(e, BriefInvalid) else "the data sources did not respond"
        if prev:
            return 200, {**prev, "current": False, "staleNotice": "Today's brief could not be published because %s. This is not today's brief; it is the brief from %s." % (why, prev.get("issuedEt"))}
        return 503, {"ok": False, "error": "The morning brief is unavailable right now. Live readings are on the conditions page."}


def run_window(now_fn=lambda: datetime.now(timezone.utc), sleep_fn=time.sleep, regions_fn=None) -> dict:
    """05:15-05:30 ET: build every region, retrying ones with missing sections every 3 minutes.

    Regions are independent: an exception in one is recorded and the others continue. A retry only
    replaces an earlier brief from today when it has no more missing sections."""
    regions_fn = regions_fn or enabled_regions
    results: dict[str, str] = {}
    if not auto_active(now_fn()):
        return results
    deadline = _et(now_fn()).replace(hour=PUBLISH_BY[0], minute=PUBLISH_BY[1], second=0, microsecond=0)
    try:
        want = _issue_date(now_fn())
        # Skip regions that already have a complete brief for today (built by a wake or page view).
        # An archived brief from today counts too (restart inside the window); a PARTIAL one still retries.
        pending = [rid for rid in regions_fn()
                   if not ((_today(rid, want) or {}).get("issueDate") == want and not (_stored(rid) or {}).get("missing"))]
    except Exception:
        return results
    while pending and _et(now_fn()) < deadline:
        for rid in list(pending):
            now = now_fn()
            try:
                with _region_lock(rid):
                    new = compose(rid, "scheduled", now)
                    old = _stored(rid)
                    if old and old.get("issueDate") == new["issueDate"] and len(old.get("missing") or []) < len(new.get("missing") or []):
                        new = old  # keep the more complete brief
                    else:
                        _save(rid, new)
                results[rid] = "ok"
                if not new.get("missing"):
                    pending.remove(rid)
            except Exception as e:
                _fail(rid, now, e)
                results.setdefault(rid, "failed")
        if pending:
            sleep_fn(180)
    return results


def _scheduler():
    while True:
        try:
            e = datetime.now(ET)
            if not (PREP <= (e.hour, e.minute) < PUBLISH_BY):  # started inside the window: run now
                nxt = e.replace(hour=PREP[0], minute=PREP[1], second=0, microsecond=0)
                if nxt <= e:
                    nxt += timedelta(days=1)
                time.sleep(max(5, (nxt - e).total_seconds()))
            run_window()
            e = datetime.now(ET)
            end = e.replace(hour=PUBLISH_BY[0], minute=PUBLISH_BY[1], second=0, microsecond=0)
            time.sleep(max(60, (end - e).total_seconds() + 60))  # once per day, never a rebuild loop
        except Exception:
            time.sleep(60)


def start_scheduler():
    global _thread
    if flag_on() and _thread is None:
        _thread = threading.Thread(target=_scheduler, name="morning-brief", daemon=True)
        _thread.start()


# ------------------------------------------------------------------ page
def _item(b: dict, label: str) -> str:
    want = label.lower()
    for k, v in b.get("items") or []:
        if str(k).lower() == want:
            return v
    return ""


def _next_tide(text: str, issued_at):
    """Next predicted tide after issue time, parsed from the existing tides line."""
    evs = re.findall(r"(low|high)\s+(\d{1,2}:\d{2}\s+[AP]M)\s+ET\s+\(([-.\d]+)\s*ft\)", text or "", re.I)
    if not evs or not issued_at:
        return None
    issued = issued_at if isinstance(issued_at, datetime) else datetime.fromisoformat(str(issued_at).replace("Z", "+00:00"))
    issued = issued.astimezone(ET)
    day = issued.date()
    parsed = []
    for typ, tm, ft in evs:
        dt = datetime.strptime(tm, "%I:%M %p").replace(year=day.year, month=day.month, day=day.day, tzinfo=ET)
        parsed.append((dt, typ.lower(), ft, tm))
    future = [p for p in parsed if p[0] > issued]
    if future:
        dt, typ, ft, tm = future[0]
        return {"time": tm, "type": typ.capitalize(), "ft": ft, "when": "next"}
    dt, typ, ft, tm = parsed[-1]
    return {"time": tm, "type": typ.capitalize(), "ft": ft, "when": "last today"}


def _glance(b: dict) -> list[dict]:
    """Presentation-only values parsed from existing brief lines. Does not change wording or data."""
    cells: list[dict] = []
    if (b.get("waterType") or "saltwater") == "freshwater":
        lake = _item(b, "Lake level")
        m = re.search(r"([\d.]+)\s*ft", lake)
        vs = re.search(r"([\d.]+)\s*ft\s+(below|above)", lake)
        if m:
            sub = (vs.group(1) + " ft " + vs.group(2) + " guide") if vs else "NGVD29"
            cells.append({"key": "Lake level", "kind": "observed", "value": m.group(1), "unit": "ft", "sub": sub, "tone": "lake"})
        rel = _item(b, "Dam release")
        m = re.search(r"(\d+)\s*cfs", rel)
        if m:
            cells.append({"key": "Release", "kind": "observed", "value": m.group(1), "unit": "cfs", "sub": "below the dam", "tone": "lake"})
        wt = _item(b, "Water temp")
        m = re.search(r"([\d.]+)°F", wt)
        if m:
            cells.append({"key": "Water temp", "kind": "observed", "value": str(int(float(m.group(1)))), "unit": "°F", "sub": "at the dam sensor", "tone": "water"})
        rain = _item(b, "Rain")
        m = re.search(r"([\d.]+)\s*in last 24 h", rain)
        if m:
            cells.append({"key": "Rain, 24 h", "kind": "observed", "value": m.group(1), "unit": "in", "sub": "at the dam", "tone": "lake"})
        wx = _item(b, "Weather")
        m = re.search(r"high\s+(\d+)°F", wx, re.I)
        if m:
            short = (re.split(r",\s*high", wx, maxsplit=1)[0] or "").strip()
            cells.append({"key": "Air high", "kind": "forecast", "value": m.group(1), "unit": "°F", "sub": short or "NWS forecast", "tone": "air"})
        return cells
    wind = _item(b, "Wind")
    m = re.search(r"(\d+)\s*kt from the (\w+)", wind)
    src = b.get("windSource") or {}
    if m and src.get("role") == "backup":
        short = (WIND_BACKUP.get(b.get("regionId") or "") or {}).get("short") or src.get("name") or "shore station"
        cells.append({"key": "Wind · coastal backup", "kind": "observed", "value": m.group(1), "unit": "kt",
                      "sub": "from %s · %s" % (m.group(2), short), "tone": "wind"})
    elif m and src.get("role") == "primary" and src.get("type") == "offshore":
        cells.append({"key": "Wind", "kind": "observed", "value": m.group(1), "unit": "kt",
                      "sub": "from %s · offshore buoy %s" % (m.group(2), src.get("station") or ""), "tone": "wind"})
    elif m:
        cells.append({"key": "Wind", "kind": "observed", "value": m.group(1), "unit": "kt", "sub": "from " + m.group(2), "tone": "wind"})
    seas = _item(b, "Seas")
    m = re.search(r"([\d.]+)\s*ft every (\d+)\s*s from the (\w+)", seas)
    if m:
        sub = brief_format.seas_sub(seas, b.get("freshness") or [], "Seas")
        cells.append({"key": "Seas", "kind": "observed", "value": m.group(1), "unit": "ft", "sub": sub, "tone": "seas"})
    swell = _item(b, "Swell")
    m = re.search(r"([\d.]+)\s*ft at ([\d.]+)\s*s from the (\w+)", swell)
    if m:
        sub = brief_format.seas_sub(swell, b.get("freshness") or [], "Swell")
        cells.append({"key": "Swell", "kind": "observed", "value": m.group(1), "unit": "ft", "sub": sub, "tone": "swell"})
    nxt = _next_tide(_item(b, "Tides"), b.get("issuedAt"))
    if nxt:
        label = "Tide next" if nxt["when"] == "next" else "Last tide today"
        cells.append({"key": label, "kind": "predicted", "value": nxt["time"].replace(" AM", "").replace(" PM", ""),
                      "unit": "AM" if "AM" in nxt["time"] else "PM",
                      "sub": "%s · %s ft" % (nxt["type"], nxt["ft"]), "tone": "tide"})
    wt = _item(b, "Water temp")
    m = re.search(r"([\d.]+)°F inshore", wt)
    off = re.search(r"([\d.]+)°F offshore", wt)
    if m:
        sub = "inshore"
        if off:
            sub = "inshore · %s°F offshore" % str(int(float(off.group(1))))
        cells.append({"key": "Water temp", "kind": "observed", "value": str(int(float(m.group(1)))), "unit": "°F", "sub": sub, "tone": "water"})
    return cells


def _advisory(b: dict):
    for label in ("Advisories", "Alerts"):
        v = _item(b, label)
        if v:
            low = v.lower()
            if low.startswith("no nws"):
                kind = "clear"
            elif low.startswith("could not"):
                kind = "unknown"
            else:
                kind = "active"
            return {"label": label, "text": v, "kind": kind}
    return None



def _astro_for_page(b: dict) -> dict | None:
    """Stored astro, or a local recompute from the issued date; never fetched live."""
    astro = b.get("astro")
    if astro and astro.get("status") in ("ok", "unavailable"):
        return astro
    rid = b.get("regionId") or (b.get("region") or {}).get("id")
    if rid not in brief_astro.REGIONS:
        return None
    issued = b.get("issuedAt")
    try:
        d = datetime.fromisoformat(str(issued).replace("Z", "+00:00")).astimezone(ET).date() if issued else None
    except (TypeError, ValueError):
        d = None
    if not d:
        return {"status": "unavailable", "regionId": rid}
    return brief_astro.for_brief(rid, d)


def _moon_svg(pct: int, waxing: bool) -> str:
    """Compact northern-hemisphere moon with an elliptical terminator.

    The right limb is lit when waxing. Inexpensive inline SVG; no images.
    """
    k = max(0, min(100, int(pct))) / 100.0
    r, cx, cy = 9.0, 12.0, 12.0
    face = ('<circle cx="12" cy="12" r="9.4" fill="#E6D4A8" '
            'stroke="#A7864F" stroke-width="1.2"/>')
    if k >= 0.995:
        shade = ""
    elif k <= 0.005:
        shade = '<circle cx="12" cy="12" r="9" fill="#1A2430" fill-opacity="0.82"/>'
    else:
        # Terminator is an ellipse of horizontal radius r*|2k-1| (0 at quarter, r at new/full).
        rx = r * abs(2 * k - 1)
        north, south = (cx, cy - r), (cx, cy + r)
        if waxing:
            # Dark limb is the left; light comes from the right.
            limb = "A %.1f %.1f 0 0 0 %.1f %.1f" % (r, r, south[0], south[1])
            # Gibbous: terminator in the left half. Crescent: terminator in the right half.
            sweep = 1 if k >= 0.5 else 0
            term = "A %.1f %.1f 0 0 %d %.1f %.1f" % (rx, r, sweep, north[0], north[1])
        else:
            limb = "A %.1f %.1f 0 0 1 %.1f %.1f" % (r, r, south[0], south[1])
            sweep = 0 if k >= 0.5 else 1
            term = "A %.1f %.1f 0 0 %d %.1f %.1f" % (rx, r, sweep, north[0], north[1])
        path = "M %.1f %.1f %s %s Z" % (north[0], north[1], limb, term)
        shade = '<path d="%s" fill="#1A2430" fill-opacity="0.82"/>' % path
    return (
        '<svg class="mb-moon-svg" viewBox="0 0 24 24" width="36" height="36" '
        'aria-hidden="true" focusable="false">'
        '%s'
        '<clipPath id="mb-moon-clip"><circle cx="12" cy="12" r="9"/></clipPath>'
        '<g clip-path="url(#mb-moon-clip)">%s</g>'
        '</svg>' % (face, shade)
    )


def _astro_html(b: dict, esc) -> str:
    rid = b.get("regionId") or (b.get("region") or {}).get("id")
    if rid not in brief_astro.REGIONS:
        return ""
    astro = _astro_for_page(b)
    if not astro or astro.get("status") == "unavailable":
        return ('<section class="mb-astro is-missing" aria-label="Sun and moon">'
                "<p>Sunrise, sunset, and moon phase not available.</p></section>")
    rise = astro.get("sunriseEt")
    sett = astro.get("sunsetEt")
    moon = astro.get("moon") or {}
    sun_bits = []
    if rise:
        sun_bits.append('<div class="mb-sun-cell"><span class="mb-astro-k">Sunrise</span>'
                        '<time class="mb-astro-v">%s</time></div>' % esc(rise))
    if sett:
        sun_bits.append('<div class="mb-sun-cell"><span class="mb-astro-k">Sunset</span>'
                        '<time class="mb-astro-v">%s</time></div>' % esc(sett))
    if not sun_bits:
        sun_bits.append("<p>Sunrise and sunset not available.</p>")
    if moon and moon.get("name"):
        pct = moon.get("illuminationPct")
        moon_html = (
            '<div class="mb-moon-cell">%s'
            '<div class="mb-moon-meta"><span class="mb-astro-k">Moon</span>'
            '<span class="mb-astro-v">%s</span>'
            '<span class="mb-moon-pct">%s%% illuminated</span></div></div>'
            % (_moon_svg(int(pct or 0), bool(moon.get("waxing"))), esc(moon["name"]),
               esc(str(pct) if pct is not None else "—"))
        )
    else:
        moon_html = '<div class="mb-moon-cell"><p>Moon phase not available.</p></div>'
    return ('<section class="mb-astro" aria-label="Sunrise, sunset, and moon phase">'
            '<div class="mb-sun">%s</div>%s</section>' % ("".join(sun_bits), moon_html))


def _outlook_html(b: dict, esc) -> str:
    if (b.get("waterType") or "saltwater") == "freshwater":
        return ""
    parsed = b.get("outlookPeriods")
    if not parsed or not parsed.get("periods"):
        text = _item(b, "Outlook")
        parsed = brief_format.parse_outlook_text(text) if text else None
    if not parsed or not parsed.get("periods"):
        return ""
    rows = []
    for p in parsed["periods"]:
        rows.append(
            '<div class="mb-outlook-period">'
            '<p class="mb-outlook-p">%s</p>'
            '<p class="mb-outlook-t">%s</p></div>'
            % (esc(p.get("name") or ""), esc(p.get("text") or ""))
        )
    src = ('<p class="mb-outlook-src">%s</p>' % esc(parsed["source"])) if parsed.get("source") else ""
    return ('<section class="mb-outlook" aria-label="Marine outlook">'
            '<p class="mb-outlook-k">Outlook</p>%s%s</section>' % ("".join(rows), src))


_KIND_LABEL = {"warning": "Warning", "watch": "Watch", "advisory": "Advisory", "statement": "Statement", "other": "Alert"}


def _hz_link(row: dict, b: dict) -> tuple[str, str]:
    """Official NWS page for the row's first in-region zone (else the brief's marine zone)."""
    zones = list(row.get("ugc") or [])
    local = list(row.get("localUgc") or []) or zones
    z = (local[0] if local else None) or b.get("marineZone")
    if z and re.fullmatch(r"[A-Z]{2}Z\d{3}", z):
        if z[:2] in ("AM", "AN", "GM", "PZ", "PK", "PH", "LM", "LE", "LH", "LO", "LS", "LC", "PM", "PS"):
            return ("https://forecast.weather.gov/showsigwx.php?warnzone=%s&warncounty=marine" % z, "NWS hazard text for %s" % z)
        return ("https://forecast.weather.gov/MapClick.php?zoneid=%s" % z, "NWS forecast and hazards for %s" % z)
    return ("https://alerts.weather.gov/", "NWS active alerts")


def _nws_text(t: str) -> str:
    """NWS products hard-wrap lines; join single line breaks, keep blank-line paragraph breaks."""
    return re.sub(r"[ \t]*(?<!\n)\n(?!\n)[ \t]*", " ", (t or "").strip())


# t487u: reconciled "status now" states for rows of the issued list -> existing row classes.
_RC_CLASS = {"in_effect": "current", "updated": "current", "upgraded": "current", "replaced": "current",
             "upcoming": "upcoming", "ended": "ended", "cancelled": "ended", "unconfirmed": "unconfirmed"}


def _hz_row_html(row: dict, b: dict, view_now: datetime, esc, rc: dict | None = None) -> str:
    onset = brief_format._parse_iso(row.get("onset"))
    ends = brief_format._parse_iso(row.get("ends"))
    if ends is not None and ends <= view_now:
        st = "ended"
    elif onset is not None and onset > view_now:
        st = "upcoming"
    else:
        st = "current"
    st_label = st.upper()
    now_line = ""
    if rc:
        # The issued wording and times above stay as published; only the status chip and the
        # "Now" line come from the current NWS check (never a silent ENDED without a check).
        st = _RC_CLASS.get(rc.get("state"), "unconfirmed")
        st_label = (rc.get("tag") or "Unconfirmed").upper()
        now_line = '<span class="mb-hz-now"><span class="mb-sr">Status now: </span>%s</span>' % esc(rc.get("detail") or "")
    kind = row.get("kind") or brief_format.hazard_kind(row.get("event") or "")
    kind_label = _KIND_LABEL.get(kind, "Alert")
    start = brief_format.when_et(onset) if onset else ""
    end = brief_format.when_et(ends) if ends else ""
    if start and end:
        when = '%s <span aria-hidden="true">–</span><span class="mb-sr"> to </span> %s' % (esc(start.replace(" ET", "")), esc(end))
    elif end:
        when = "until %s" % esc(end)
    elif start:
        when = "from %s" % esc(start)
    else:
        when = "Times not given by NWS"
    all_areas = [a for a in re.split(r";\s*", row.get("areas") or "") if a]
    local = row.get("local") or []
    if local:
        extra = len([a for a in all_areas if a not in local])
        area = esc("; ".join(local)) + ((' <span class="mb-hz-more-n">+%d more</span>' % extra) if extra > 0 else "")
    else:
        area = esc("; ".join(all_areas))
    link, link_label = _hz_link(row, b)
    prods = []
    for prod in row.get("products") or []:
        bits = []
        if prod.get("headline"):
            bits.append('<p class="mb-hz-hl">%s</p>' % esc(prod["headline"]))
        meta = [x for x in (("Severity: " + prod["severity"]) if prod.get("severity") else "",
                            ("Certainty: " + prod["certainty"]) if prod.get("certainty") else "",
                            ("Areas: " + prod["areas"]) if prod.get("areas") and len(row.get("products") or []) > 1 else "") if x]
        if meta:
            bits.append('<p class="mb-hz-meta">%s</p>' % esc(" · ".join(meta)))
        if prod.get("description"):
            bits.append('<p class="mb-hz-desc">%s</p>' % esc(_nws_text(prod["description"])))
        if prod.get("instruction"):
            bits.append('<p class="mb-hz-inst"><b>NWS instructions:</b> %s</p>' % esc(_nws_text(prod["instruction"])))
        if bits:
            prods.append('<div class="mb-hz-prod">%s</div>' % "".join(bits))
    if not prods:
        prods.append('<p class="mb-hz-desc">%s</p>' % esc(row.get("text") or ""))
    more = ('<div class="mb-hz-body"><p class="mb-hz-meta"><b>All areas:</b> %s</p>%s'
            '<p class="mb-hz-src"><a href="%s" target="_blank" rel="noopener">%s</a> · issued by NWS; check for updates since this brief.</p></div>'
            % (esc("; ".join(all_areas) or "Not listed"), "".join(prods), esc(link), esc(link_label)))
    return ('<li class="mb-hz-row k-%s s-%s"><details><summary>'
            '<span class="mb-hz-l1"><span class="mb-hz-kind">%s</span> <span class="mb-hz-ev">%s</span></span>'
            '<span class="mb-hz-l2"><span class="mb-hz-when"><span class="mb-hz-st">%s</span> %s</span><span class="mb-hz-area">%s</span>%s</span>'
            '</summary>%s</details></li>'
            % (esc(kind), st, esc(kind_label), esc(row.get("event") or ""), esc(st_label), when, area, now_line, more))


def _issued_rows(b: dict) -> list:
    """Rows of the issued hazards list, in stored order (the same objects the page renders)."""
    hz = b.get("hazards") or {}
    if hz.get("status") != "active":
        return []
    return list(hz.get("current") or []) + list(hz.get("upcoming") or [])


def status_now_for(b: dict, fetch, now: datetime | None = None) -> dict | None:
    """Current official NWS alerts for this brief's area (t487u). Never raises; never edits the snapshot.

    Saltwater: the region's alert zones (same query the conditions page uses). Freshwater: the same
    point query the Falls Lake brief used. `fetch(url)` returns parsed JSON or None (no stale copies)."""
    import alert_status
    try:
        now = now or datetime.now(timezone.utc)
        rid = b.get("regionId") or (b.get("region") or {}).get("id") or ""
        fw = (b.get("waterType") or "") == "freshwater"
        cfg = _region_cfg(rid, fw) or {}
        start = brief_format._parse_iso(b.get("issuedAt"))
        start_q = start.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if start else None
        if fw:
            pt = cfg.get("alertPoint") or [(cfg.get("anchor") or {}).get("lat"), (cfg.get("anchor") or {}).get("lon")]
            if not pt or None in pt:
                return None
            q = "point=%.4f,%.4f" % (pt[0], pt[1])
            zones = None
        else:
            zones = list(cfg.get("alertZones") or [])
            if not zones:
                return None
            q = "zone=" + ",".join(zones)
        url = "https://api.weather.gov/alerts/active?status=actual&" + q
        hist = ("https://api.weather.gov/alerts?%s&start=%s" % (q, start_q)) if start_q else None
        return alert_status.status_now(_issued_rows(b), url, fetch, now=now, zones=zones, history_url=hist)
    except Exception as e:  # a bug here must not take the brief down; show "could not check" instead
        sys.stderr.write("brief status_now failed: %r\n" % (e,))
        return {"ok": False, "trusted": False, "checkedAt": (now or datetime.now(timezone.utc)).isoformat(),
                "current": [], "issued": [{"state": "unconfirmed", "tag": "Unconfirmed",
                                           "detail": "Status unconfirmed — check NWS."} for _ in _issued_rows(b)],
                "coastalFlood": None}


def _status_now_html(b: dict, sn: dict | None, esc, view_now: datetime) -> str:
    """The separate, live "Status now" section. The issued brief above it is not changed."""
    if not sn:
        return ""
    import alert_status
    checked = brief_format.when_et(sn.get("checkedAt"), always_weekday=False)
    link = '<p class="mb-hz-src"><a href="https://alerts.weather.gov/" target="_blank" rel="noopener">NWS active alerts</a> · live; this brief was issued %s and does not change.</p>' % esc(
        (b.get("issuedEt") or "").split(", ")[-1] or "earlier")
    head = ('<div class="mb-hz-head"><h2 class="mb-hz-h" id="mb-now-h">Status now</h2>'
            '<p class="mb-hz-note">Current NWS alerts · checked %s</p></div>' % esc(checked))
    if not sn.get("ok"):
        return ('<section class="mb-now is-unknown" aria-labelledby="mb-now-h">%s'
                '<p class="mb-now-warn">Could not reach the National Weather Service to check current alerts. '
                'Status unconfirmed — check NWS before heading out.</p>%s</section>' % (head, link))
    lis = []
    rank = {"warning": 0, "watch": 1, "advisory": 2, "statement": 3}
    cur = sorted(sn.get("current") or [], key=lambda r: (rank.get(brief_format.hazard_kind(r.get("event") or ""), 9),
                                                       (brief_format._parse_iso(r.get("start")) or view_now).timestamp()))
    for r in cur:
        lab = r.get("label") or alert_status.label_for(r, view_now)
        kind = brief_format.hazard_kind(r.get("event") or "")
        area = "; ".join(r.get("local") or [])
        upd = alert_status.et_clock(r.get("sent"), view_now)
        lis.append(
            '<li class="mb-now-row k-%s p-%s"><span class="mb-now-l1"><span class="mb-now-tag">%s</span> '
            '<span class="mb-hz-kind">%s</span> <span class="mb-now-ev">%s</span></span>'
            '<span class="mb-now-when">%s</span>%s%s</li>'
            % (esc(kind), esc(lab["phase"].replace("_", "-")), esc(lab["tag"].upper()), esc(_KIND_LABEL.get(kind, "Alert")),
               esc(r.get("event") or ""), esc(lab["when"]),
               ('<span class="mb-now-area">%s</span>' % esc(area)) if area else "",
               ('<span class="mb-now-upd">NWS update %s · %s</span>' % (esc(upd), esc(r.get("sender") or "NWS"))) if upd else ""))
    warn = ""
    if not sn.get("trusted"):
        warn = ('<p class="mb-now-warn">An NWS alert record could not be read. Status unconfirmed — check NWS before heading out.</p>')
    if lis:
        body = '<ul class="mb-now-list">%s</ul>' % "".join(lis)
    elif sn.get("trusted"):
        body = '<p class="mb-now-clear">No NWS watches, warnings or advisories for this area right now.</p>'
    else:
        body = ""
    return '<section class="mb-now" aria-labelledby="mb-now-h">%s%s%s%s</section>' % (head, body, warn, link)


def _flood_tide_note_html(sn: dict | None, esc) -> str:
    """Coastal Flood Warning note next to the predicted tides. Tide values are not touched."""
    import alert_status
    cf = (sn or {}).get("coastalFlood")
    if not cf:
        return ""
    lead = "Coastal Flood Warning in effect." if cf.get("phase") == "in_effect" else "Coastal Flood Warning issued (upcoming)."
    return '<p class="mb-tide-note" role="note"><b>%s</b> %s</p>' % (esc(lead), esc(alert_status.FLOOD_TIDE_NOTE))


def _hazards_html(b: dict, esc, view_now: datetime | None = None, status_now: dict | None = None) -> str:
    water = b.get("waterType") or "saltwater"
    label = "Alerts" if water == "freshwater" else "Advisories"
    stored = _item(b, label)
    hz = b.get("hazards")
    view_now = view_now or datetime.now(timezone.utc)
    if hz and hz.get("status") == "clear":
        return ('<section class="mb-adv is-clear" aria-label="%s"><span class="mb-adv-dot" aria-hidden="true"></span>'
                '<div><p class="mb-adv-k">%s</p><p class="mb-adv-t">%s</p></div></section>'
                % (esc(label), esc(label), esc(hz.get("line") or stored or "")))
    if hz and hz.get("status") == "unknown":
        return ('<section class="mb-adv is-unknown" aria-label="%s"><span class="mb-adv-dot" aria-hidden="true"></span>'
                '<div><p class="mb-adv-k">%s</p><p class="mb-adv-t">%s</p></div></section>'
                % (esc(label), esc(label), esc(hz.get("line") or stored or "")))
    rows = []
    if hz and hz.get("status") == "active":
        rows = list(hz.get("current") or []) + list(hz.get("upcoming") or [])
    if rows:
        rank = {"warning": 0, "watch": 1, "advisory": 2, "statement": 3}
        def key(r):
            k = r.get("kind") or brief_format.hazard_kind(r.get("event") or "")
            on = brief_format._parse_iso(r.get("onset"))
            return (rank.get(k, 9), on.timestamp() if on else 0)
        recon = {}
        if status_now:
            for r, rc in zip(_issued_rows(b), status_now.get("issued") or []):
                recon[id(r)] = rc
        rows.sort(key=key)
        lis = "".join(_hz_row_html(r, b, view_now, esc, recon.get(id(r)) if status_now else None) for r in rows)
        n = len(rows)
        issued = (b.get("issuedEt") or "").split(", ")[-1]
        checked = ""
        if status_now:
            checked = " · status checked %s" % brief_format.when_et(status_now.get("checkedAt"), always_weekday=False)
        # Keep the stored snapshot line in the page so archived wording still matches tests.
        hidden = ('<p class="mb-adv-stored">%s</p>' % esc(stored)) if stored else ""
        return ('<section class="mb-adv is-active mb-hz" aria-labelledby="mb-hz-h">'
                '<div class="mb-hz-head"><h2 class="mb-hz-h" id="mb-hz-h">NWS %s <span class="mb-hz-n">%d</span></h2>'
                '<p class="mb-hz-note">List as issued %s%s</p></div>'
                '<ul class="mb-hz-list">%s</ul>%s</section>'
                % ("alerts" if water == "freshwater" else "hazards", n, esc(issued or "at issue"),
                   esc(checked) if status_now else " · status now", lis, hidden))
    # Legacy stored briefs with no hazards object.
    adv = _advisory(b)
    if not adv:
        return ""
    return ('<section class="mb-adv is-%s" aria-label="%s"><span class="mb-adv-dot" aria-hidden="true"></span>'
            '<div><p class="mb-adv-k">%s</p><p class="mb-adv-t">%s</p></div></section>'
            % (esc(adv["kind"]), esc(adv["label"]), esc(adv["label"]), esc(adv["text"])))


def _glance_html(b: dict, view_now: datetime, esc, group: str = "all") -> str:
    """Glance strip, with a render-time tide adjustment that does not edit the snapshot."""
    tides_line = _item(b, "Tides")
    view = brief_format.tide_view(tides_line, b.get("issuedAt"), view_now) if tides_line else None
    evs = brief_format.parse_tide_events(tides_line, b.get("issuedAt")) if tides_line else []
    payload = json.dumps({
        "issuedAt": b.get("issuedAt"),
        "events": [{"iso": e["time"].isoformat(), "type": e["type"], "ft": e["ft"], "label": e["label"]} for e in evs],
    }, separators=(",", ":"))
    cells = []
    def _primary(c):
        k = (c.get("key") or "").lower()
        return k.startswith("tide") or k in (
            "wind", "seas", "lake level", "rain, 24 h", "rain", "air high", "release",
        )
    for c in _glance(b):
        if group == "primary" and not _primary(c):
            continue
        if group == "rest" and _primary(c):
            continue
        attrs = ""
        note = ""
        key, value, unit, sub = c["key"], c["value"], c["unit"], c["sub"]
        if "tide" in c["key"].lower():
            attrs = ' id="mb-tide" data-tides="%s"' % esc(payload)
            if view and view.get("adjusted"):
                if view.get("next"):
                    nxt = view["next"]
                    key = "Tide next"
                    tm = nxt["label"]
                    value = tm.replace(" AM", "").replace(" PM", "")
                    unit = "AM" if "AM" in tm else "PM"
                    sub = "%s · %s ft" % (nxt["type"].capitalize(), nxt["ft"])
                elif view.get("last") or view.get("passed"):
                    last = view.get("last") or (view["passed"][-1] if view.get("passed") else None)
                    if last:
                        key = "Last tide today"
                        tm = last["label"]
                        value = tm.replace(" AM", "").replace(" PM", "")
                        unit = "AM" if "AM" in tm else "PM"
                        sub = "%s · %s ft" % (last["type"].capitalize(), last["ft"])
                note = '<span class="mb-view-note">Updated at view time from NOAA predictions</span>'
        cells.append(
            '<div class="mb-gc tone-%s kind-%s"%s><span class="mb-gk">%s</span>'
            '<span class="mb-gv"><b>%s</b><span class="mb-gu">%s</span></span>'
            '<span class="mb-gs">%s</span><span class="mb-gkind">%s</span>%s</div>'
            % (esc(c["tone"]), esc(c["kind"]), attrs, esc(key), esc(value), esc(unit),
               esc(sub), esc(c["kind"]), note)
        )
    return ('<section class="mb-glance" aria-label="At a glance">%s</section>' % "".join(cells)) if cells else ""


_TIDE_JS = """
<script>
(function(){
  var el=document.getElementById("mb-tide");
  if(!el||!el.getAttribute("data-tides"))return;
  function parse(s){try{return JSON.parse(s)}catch(e){return null}}
  function fmt(d){
    // Always display and interpret clock times in America/New_York, not the browser TZ.
    var parts=new Intl.DateTimeFormat("en-US",{timeZone:"America/New_York",hour:"numeric",minute:"2-digit",hour12:true}).formatToParts(d);
    var h="",m="",ap="";
    parts.forEach(function(p){
      if(p.type==="hour") h=p.value;
      if(p.type==="minute") m=p.value;
      if(p.type==="dayPeriod") ap=p.value;
    });
    return {value:h+":"+m, unit:ap};
  }
  function apply(){
    var data=parse(el.getAttribute("data-tides"));
    if(!data||!data.events||!data.events.length)return;
    var now=Date.now();
    var evs=data.events.map(function(e){return {t:Date.parse(e.iso), type:e.type, ft:e.ft, label:e.label};});
    var issued=Date.parse(data.issuedAt);
    var issuedNext=null;
    evs.forEach(function(e){ if(issued && e.t>issued && !issuedNext) issuedNext=e; });
    var next=null, last=null;
    evs.forEach(function(e){
      if(e.t>now && !next) next=e;
      if(e.t<=now) last=e;
    });
    var changed=false;
    if(next && issuedNext && next.t!==issuedNext.t) changed=true;
    if(!next && last) changed=true;
    if(!changed) return;
    var key=el.querySelector(".mb-gk");
    var b=el.querySelector(".mb-gv b");
    var u=el.querySelector(".mb-gu");
    var sub=el.querySelector(".mb-gs");
    var ev=next||last;
    if(!ev||!key||!b||!u||!sub)return;
    var clock=fmt(new Date(ev.t));
    key.textContent=next?"Tide next":"Last tide today";
    b.textContent=clock.value;
    u.textContent=clock.unit;
    var typ=(ev.type||"").charAt(0).toUpperCase()+(ev.type||"").slice(1);
    sub.textContent=typ+" · "+ev.ft+" ft";
    if(!el.querySelector(".mb-view-note")){
      var n=document.createElement("span");
      n.className="mb-view-note";
      n.textContent="Updated at view time from NOAA predictions";
      el.appendChild(n);
    }
  }
  apply();
  setInterval(apply, 60000);
})();
</script>
"""


def page(b: dict, include_fresh: bool = False, public: bool = False, ads_on: bool = False, view_now: datetime | None = None,
         status_now: dict | None = None) -> str:
    """Render the brief page. On phones (<=600px) the prose
    sections under the at-a-glance strip start collapsed so readings
    are not shown twice above the fold; they stay open on tablet,
    desktop, and in print.

    public: indexable saltwater page (no preview-only / freshwater).
    ads_on: reserve an ad gap below advisories only when ads are active;
    otherwise leave no empty gap and never show a placeholder box.
    """
    esc = html.escape
    reason = {"scheduled": "Prepared on schedule (5:15 AM ET build, woken by the daily 5:16 AM check).",
              "on-request": "Built on request because the 5:15 AM scheduled build did not run (the server was asleep or restarting).",
              "rebuilt": "Rebuilt on request after a server restart.",
              "manual": "Built manually for testing."}.get(b.get("reason"), "")
    water = b.get("waterType") or "saltwater"
    name = b.get("region", {}).get("name") or "Morning Brief"
    area = b.get("region", {}).get("area") or ""
    rid = b.get("regionId") or b.get("region", {}).get("id") or ""
    issued = b.get("issuedEt") or ""
    fr_bits = []
    for f in b.get("freshness") or []:
        stale = ' <span class="mb-stale">stale</span>' if f.get("stale") else ""
        stn = (' <span class="mb-stn">%s</span>' % esc(f["station"])) if f.get("station") else ""
        fr_bits.append("<li><span class=\"mb-fk\">%s</span> <time>%s</time>%s%s</li>" % (esc(f["label"]), esc(f["time"]), stn, stale))
    fr = "".join(fr_bits) or "<li>No observation times were recorded at issue time.</li>"
    view_now = view_now or datetime.now(timezone.utc)
    adv_html = _hazards_html(b, esc, view_now, status_now) + _status_now_html(b, status_now, esc, view_now)
    glance = _glance_html(b, view_now, esc, group="primary") + _flood_tide_note_html(status_now, esc)
    glance_rest = _glance_html(b, view_now, esc, group="rest")
    astro_html = _astro_html(b, esc)
    outlook_html = _outlook_html(b, esc)
    rows = []
    for k, v in b.get("items") or []:
        if k in ("Advisories", "Alerts"):
            continue
        slug = re.sub(r"[^a-z]+", "-", k.lower()).strip("-")
        rows.append('<div class="mb-row tone-%s"><dt>%s</dt><dd>%s</dd></div>' % (esc(slug), esc(k), esc(v)))
    rows_html = "".join(rows)
    miss = ('<p class="mb-miss">Not available at issue time: %s.</p>' % esc(", ".join(b["missing"]))) if b.get("missing") else ""
    stale = ('<p class="mb-miss mb-stale-note">%s</p>' % esc(b["staleNotice"])) if b.get("staleNotice") else ""
    take_ps = "".join("<p>%s</p>" % esc(t) for t in (b.get("take") or []) if t)
    # Region switcher: saltwater briefs always; Falls Lake when freshwater is on (or this is a freshwater brief).
    region_links = [
        ("crystal-coast", "Morehead City · Beaufort"),
        ("hatteras", "Hatteras Island"),
    ]
    if include_fresh or water == "freshwater":
        region_links.append(("falls-lake", "Falls Lake"))
    nav = "".join(
        '<a href="/brief?region=%s"%s>%s</a>' % (esc(i), ' aria-current="page"' if i == rid else "", esc(n))
        for i, n in region_links
    )
    # Share text: issue time plus the glance numbers, no added interpretation.
    share_bits = ["Morning Brief for %s, issued %s." % (name, issued)]
    for c in _glance(b):
        share_bits.append("%s %s %s (%s), %s." % (c["key"], c["value"], c["unit"], c["kind"], c["sub"]))
    hz = b.get("hazards") or {}
    if hz.get("status") == "active" and hz.get("line"):
        share_bits.append(hz["line"])
    else:
        adv = _advisory(b)
        if adv and adv["kind"] == "active":
            share_bits.append(adv["text"])
    share_bits.append("Not a fishing report. Not endorsed by NOAA.")
    desc = esc(" ".join(share_bits)[:300].rsplit(" ", 1)[0] + ".")
    og_title = esc("Morning Brief · %s — The Coastal Brief" % name)
    og_url = esc("https://thecoastalbrief.com/brief?region=%s" % rid)
    return """<!DOCTYPE html>
<html lang="en" data-theme="light" data-water="%(water)s">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="robots" content="%(robots)s">
<meta name="theme-color" content="#071C29">
<title>Morning Brief · %(name)s — The Coastal Brief</title>
<meta name="description" content="%(desc)s">
<meta property="og:title" content="%(og_title)s">
<meta property="og:description" content="%(desc)s">
<meta property="og:url" content="%(og_url)s">
<meta property="og:type" content="article">
<meta property="og:image" content="https://thecoastalbrief.com/branding/og-masthead.jpg">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="The Coastal Brief nameplate in ivory serif on deep navy, with a faint North Carolina nautical-chart texture and the line From the rivers to the sounds to the sea.">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="%(og_title)s">
<meta name="twitter:description" content="%(desc)s">
<meta name="twitter:image" content="https://thecoastalbrief.com/branding/og-masthead.jpg">
<meta name="twitter:image:alt" content="The Coastal Brief nameplate in ivory serif on deep navy, with a faint North Carolina nautical-chart texture and the line From the rivers to the sounds to the sea.">
<link rel="icon" href="/favicon.ico?v=20261121" sizes="48x48">
<link rel="icon" href="/branding/favicon.svg?v=20261121" type="image/svg+xml">
<link rel="apple-touch-icon" href="/apple-touch-icon.png?v=20261121" sizes="180x180">
<link rel="manifest" href="/site.webmanifest?v=20261121">
<link rel="preload" href="/fonts/source-sans-3-var.woff2" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="/fonts/barlow-condensed-600.woff2" as="font" type="font/woff2" crossorigin>
<script>(function(){try{var q=new URLSearchParams(location.search).get("theme");var t=q||localStorage.getItem("coastalBrief.theme");if(t!=="light"&&t!=="dark")t=matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light";document.documentElement.setAttribute("data-theme",t)}catch(e){}})();</script>
<link rel="stylesheet" href="/brief.css">
</head>
<body class="mb-page">
<a class="skip" href="#brief-body">Skip to the brief</a>
<header class="mb-top">
  <div class="mb-top-row">
    <a class="mb-brand" href="/">
      <svg class="crest" viewBox="0 0 64 40" aria-hidden="true" focusable="false"><path class="crest-sea" d="M0 30 C10 18 18 16 28 22 S48 34 64 20 L64 40 L0 40 Z"/><path class="crest-arc" d="M14 15 C26 4 46 4 58 14 L55 17 C44 9 28 9 17 18 Z"/><path class="crest-in" d="M24 15 C32 9 44 9 52 14 L50 16.5 C42 12 33 12 26 16.8 Z"/></svg>
      <span class="wordmark">The Coastal Brief</span>
    </a>
    <div class="mb-tools">
      <button type="button" class="mb-print" onclick="window.print()">Print</button>
      <button type="button" id="theme-toggle" class="theme-toggle" aria-pressed="false" aria-label="Switch to dark mode">Dark mode</button>
    </div>
  </div>
</header>
<main class="mb" id="brief-body">
  <p class="mb-badge">Morning Brief</p>
  <p class="mb-kicker">%(water_label)s</p>
  <h1>%(name)s</h1>
  <p class="mb-tag">More than the forecast. It’s a way of life.</p>
  %(area)s
  <nav class="mb-regions" aria-label="Brief region">%(nav)s</nav>
  <section class="mb-issue" aria-label="Issue time and data freshness">
    <p class="mb-issued"><span class="mb-issued-k">Issued</span> <time>%(issued)s</time></p>
    <p class="mb-why">%(reason)s · %(words)d words</p>
    <p class="mb-fresh-k">Reading times</p>
    <ul class="mb-fresh">%(fr)s</ul>
  </section>
  %(stale)s
  %(adv)s
  %(glance)s
  %(outlook)s
  %(astro)s
  %(glance_rest)s
  <details class="mb-details" id="mb-details">
    <summary>Full readings <span class="mb-details-hint">the same observations in full</span></summary>
    <dl class="mb-body">%(rows)s</dl>
  </details>
  %(miss)s
  <script>
  (function(){
    var d=document.getElementById("mb-details");
    if(!d)return;
    var wide=window.matchMedia("(min-width: 601px)");
    function apply(){
      if(wide.matches) d.open=true;
      else if(!d.hasAttribute("data-user")) d.open=false;
    }
    apply();
    d.addEventListener("toggle", function(){ if(!wide.matches) d.setAttribute("data-user","1"); });
    if(wide.addEventListener) wide.addEventListener("change", apply);
    else wide.addListener(apply);
    window.addEventListener("beforeprint", function(){ d.open=true; });
    window.addEventListener("afterprint", apply);
  })();
  </script>
  %(tide_js)s
  %(ad)s
  <section class="mb-take">
    <p class="mb-take-k"><span>Captain’s take</span> <span class="mb-interp">Interpretation</span></p>
    <div class="mb-take-body">%(take)s</div>
    <p class="mb-take-note">Generated by fixed rules from the readings above. Not an observation and not a fishing report.</p>
  </section>
  <footer class="mb-foot">
    <p>Sources: %(src)s. Live readings keep updating on the <a href="/">conditions page</a>; this brief does not. This is not a fishing report. Not endorsed by NOAA.</p>
  </footer>
</main>
<script>
(function(){
  var root=document.documentElement, btn=document.getElementById("theme-toggle");
  function sync(){
    var dark=root.getAttribute("data-theme")==="dark";
    if(!btn)return;
    btn.setAttribute("aria-pressed", dark?"true":"false");
    btn.setAttribute("aria-label", dark?"Switch to light mode":"Switch to dark mode");
    btn.textContent=dark?"Light mode":"Dark mode";
  }
  sync();
  if(btn)btn.addEventListener("click",function(){
    var n=root.getAttribute("data-theme")==="dark"?"light":"dark";
    root.setAttribute("data-theme",n);
    try{localStorage.setItem("coastalBrief.theme",n)}catch(e){}
    sync();
  });
})();
</script>
</body>
</html>""" % {
        "robots": "index, follow" if public else "noindex, nofollow",
        "ad": '<div class="mb-ad" aria-hidden="true"></div>' if ads_on else "",
        "water": esc(water),
        "water_label": "River &amp; lake" if water == "freshwater" else "The sounds &amp; the sea",
        "name": esc(name),
        "desc": desc,
        "og_title": og_title,
        "og_url": og_url,
        "area": ('<p class="mb-area">%s</p>' % esc(area)) if area else "",
        "nav": nav,
        "issued": esc(issued),
        "reason": esc(reason),
        "words": b.get("words") or 0,
        "fr": fr,
        "stale": stale,
        "adv": adv_html,
        "glance": glance, "glance_rest": glance_rest,
        "astro": astro_html,
        "outlook": outlook_html,
        "tide_js": _TIDE_JS,
        "rows": rows_html,
        "miss": miss,
        "take": take_ps,
        "src": esc(b.get("sources") or ""),
    }


