"""Morning Brief: a short daily summary per enabled region, built only from verified readings.

On by default for saltwater regions. Set MORNING_BRIEF_ENABLED to 0, false, or off to disable
(a kill switch). The Falls Lake brief stays private (FRESHWATER_ENABLED or a preview cookie).
Never includes market data. The Captain's take is produced by fixed
rules from the numbers in the brief; nothing is invented.

Schedule: an in-process thread prepares every enabled region at 05:15 ET and retries failed sections
until 05:30 ET. If the service was asleep, the first request after 05:15 builds the brief on demand
(and says so). Briefs are kept in memory and in cache/briefs/ (ephemeral on Render: a restart loses them,
and the next request rebuilds the current one, labeled as rebuilt).
"""
from __future__ import annotations

import html
import json
import os
import re
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import conditions

ET = ZoneInfo("America/New_York")
ROOT = Path(__file__).resolve().parent
STORE = ROOT / "cache" / "briefs"
PREP = (5, 15)
PUBLISH_BY = (5, 30)
_lock = threading.Lock()
_mem: dict[str, dict] = {}
_thread = None


def flag_on() -> bool:
    """Saltwater briefs are on unless MORNING_BRIEF_ENABLED is explicitly 0, false, or off."""
    v = (os.environ.get("MORNING_BRIEF_ENABLED") or "").strip().lower()
    return v not in ("0", "false", "off")


def enabled_regions(include_fresh: bool | None = None) -> list[str]:
    cfg = conditions.load_regions()
    out = [r["id"] for r in cfg.get("regions") or [] if conditions._servable(r)]
    try:  # freshwater regions only when their own flag is on (or for a preview browser)
        import freshwater
        if freshwater.flag_on() if include_fresh is None else include_fresh:
            out += [rid for rid, r in freshwater.regions().items() if r.get("previewReady")]
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
def build_salt(rid: str, now: datetime) -> dict:
    st, d = conditions.assemble(rid)
    if st != 200 or not d.get("ok"):
        raise RuntimeError("conditions unavailable")
    R = d["readings"]
    ok = lambda k: R.get(k, {}).get("status") == "ok"
    items, fresh, take, missing = [], [], [], []

    def fr(label, r):
        if r and r.get("time"):
            age = r.get("ageMin")
            fresh.append({"label": label, "time": _t(r["time"]), "station": (r.get("station") or {}).get("id"), "stale": bool(age is not None and r.get("staleAfterMin") and age > r["staleAfterMin"])})

    # advisories first
    al = d.get("alerts") or {}
    if al.get("status") == "ok":
        if al["items"]:
            adv = "; ".join("%s until %s" % (a["event"], _t(a["ends"])) if a.get("ends") else a["event"] for a in al["items"])
            items.append(("Advisories", adv + "."))
        else:
            items.append(("Advisories", "No NWS marine advisories for this area."))
    else:
        items.append(("Advisories", "Could not check NWS advisories at issue time."))
        missing.append("advisories")

    wind_tr = seas_tr = pres_tr = None
    if ok("wind"):
        w = R["wind"]; v = w["values"]; fr("Wind", w)
        wind_tr = _trend(w["station"]["id"], "WSPD", now, conditions.MS_TO_KT)
        line = "%d kt from the %s, gusting %d, at %s" % (round(v["speedKt"]), v["dirCompass"], round(v["gustKt"] or v["speedKt"]), w["station"]["name"])
        if wind_tr:
            line += "; %s from %d kt %d h earlier" % ("up" if wind_tr["now"] - wind_tr["then"] > 2 else "down" if wind_tr["then"] - wind_tr["now"] > 2 else "about steady", round(wind_tr["then"]), wind_tr["hours"])
            pres_tr = _trend(w["station"]["id"], "PRES", now)
        items.append(("Wind", line + "."))
    else:
        missing.append("wind")
    if ok("seas"):
        s = R["seas"]; v = s["values"]; fr("Seas", s)
        seas_tr = _trend(s["station"]["id"], "WVHT", now, conditions.M_TO_FT)
        line = "%.1f ft every %d s from the %s at %s" % (v["heightFt"], round(v["dominantPeriodS"]), v["meanDirCompass"], s["station"]["name"])
        if seas_tr:
            dlt = seas_tr["now"] - seas_tr["then"]
            line += "; %s from %.1f ft %d h earlier" % ("building" if dlt > 0.5 else "easing" if dlt < -0.5 else "little changed", seas_tr["then"], seas_tr["hours"])
        items.append(("Seas", line + "."))
    else:
        missing.append("seas")
    if ok("swell"):
        sw = R["swell"]["values"]
        items.append(("Swell", "%.1f ft at %.0f s from the %s (split from the buoy spectrum)." % (sw["heightFt"], sw["periodS"], sw["dirCompass"])))
    if ok("pressure"):
        p = R["pressure"]; fr("Barometer", p)
        line = "%.2f inHg, %s" % (p["values"]["inHg"], p["values"]["trend"])
        if pres_tr:
            line += ", %s hPa over %d h at %s" % (_dir_word(pres_tr["now"] - pres_tr["then"], "", "up", "down", "steady", 0.4), pres_tr["hours"], pres_tr["station"])
        items.append(("Pressure", line + "."))
    mar = d.get("marine") or {}
    if mar.get("status") == "ok" and mar.get("periods"):
        first = re.split(r"(?<=\.)\s", mar["periods"][0]["text"].strip())[0]
        items.append(("Marine forecast", "%s: %s (NWS %s)" % (mar["periods"][0]["name"], first, mar.get("zone"))))
    else:
        missing.append("marine forecast")
    fc = d.get("forecast") or {}
    if fc.get("status") == "ok" and fc.get("periods"):
        ps = fc["periods"][:2]
        rain = max(p.get("pop") or 0 for p in ps)
        items.append(("Rain", "%d%% chance through tonight; %s, high %s°F." % (rain, ps[0]["short"].lower(), ps[0]["tempF"])))
    t = d.get("tides") or {}
    if t.get("status") == "ok":
        day = _et(now).date()
        evs = [e for e in t["events"] if datetime.fromtimestamp(e["t"] / 1000, timezone.utc).astimezone(ET).date() == day]
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

    # ---- Captain's take: fixed rules over the numbers above ----
    if al.get("status") == "ok" and al["items"]:
        a = al["items"][0]
        until = " until " + _t(a["ends"]) if a.get("ends") else ""
        if a["event"] == "Small Craft Advisory":
            take.append("NWS rates conditions hazardous to small craft%s." % until)
        else:
            take.append("A %s is in effect%s." % (a["event"], until))
    if wind_tr:
        dlt = wind_tr["now"] - wind_tr["then"]
        if dlt <= -4:
            take.append("Wind has eased %d kt over the past %d h." % (round(-dlt), wind_tr["hours"]))
        elif dlt >= 4:
            take.append("Wind has built %d kt over the past %d h." % (round(dlt), wind_tr["hours"]))
    if ok("seas") and R["seas"]["values"]["dominantPeriodS"] < 7 and R["seas"]["values"]["heightFt"] >= 3:
        take.append("Seas are short-period wind chop, so expect a steep, close-together ride.")
    if mar.get("status") == "ok" and mar.get("periods") and re.search(r"diminish|subsid", mar["periods"][0]["text"], re.I):
        take.append("The NWS marine forecast has wind or seas easing later today.")
    elif mar.get("status") == "ok" and mar.get("periods") and re.search(r"increas|build", mar["periods"][0]["text"], re.I):
        take.append("The NWS marine forecast has wind or seas building later today.")
    if ok("waterTemp") and ok("waterTempOffshore"):
        gap = R["waterTempOffshore"]["values"]["f"] - R["waterTemp"]["values"]["f"]
        if abs(gap) >= 3:
            take.append("Offshore water is %d°F %s than inshore." % (round(abs(gap)), "warmer" if gap > 0 else "cooler"))
    if not take:
        take.append("No advisories and no big overnight changes in the readings.")
    return {"region": d["region"], "waterType": "saltwater", "items": items, "freshness": fresh, "take": take[:4], "missing": missing,
            "sources": "NOAA NDBC, NOAA CO-OPS, NWS (api.weather.gov)"}


# ------------------------------------------------------------------ freshwater brief (preview regions only)
def build_fresh(rid: str, now: datetime) -> dict:
    import freshwater
    st, d = freshwater.assemble(rid)
    if st != 200:
        raise RuntimeError("freshwater unavailable")
    L = d["lake"]; items, fresh, take, missing = [], [], [], []
    al = d.get("alerts") or {}
    items.append(("Alerts", "; ".join("%s until %s" % (a["event"], _t(a["ends"])) if a.get("ends") else a["event"] for a in al.get("items", [])) + "." if al.get("items") else "No NWS alerts at the dam." if al.get("status") == "ok" else "Could not check NWS alerts."))
    if L.get("elevation"):
        e = L["elevation"]; fresh.append({"label": "Lake level", "time": _t(e["time"]), "station": L["usgs"], "stale": e.get("stale")})
        items.append(("Lake level", "%.2f ft (NGVD29), %.2f ft %s the %.1f ft guide curve; %s ft in 24 h." % (e["value"], abs(L["vsGuideFt"]), "below" if L["vsGuideFt"] < 0 else "above", L["guideCurveFt"], ("%+.2f" % L["change24hFt"]) if L.get("change24hFt") is not None else "n/a")))
    else:
        missing.append("lake level")
    rel = d.get("release") or {}
    if rel.get("flowCfs"):
        items.append(("Dam release", "%d cfs below Falls Dam (regulated)%s." % (round(rel["flowCfs"]["value"]), ", " + rel["band"]["label"].lower() if rel.get("band") else "")))
    inf = [i for i in d.get("inflows") or [] if i.get("flowCfs")]
    if inf:
        items.append(("Inflows", "; ".join("%s %s cfs%s" % (i["label"], ("%.1f" % i["flowCfs"]["value"]).rstrip("0").rstrip("."), ", " + i["band"]["label"].lower() if i.get("band") else "") for i in inf) + "."))
    wt = d.get("waterTemp") or {}
    if wt.get("status") == "ok":
        fresh.append({"label": "Water temp", "time": _t(wt["time"]), "station": wt["usgs"], "stale": wt.get("stale")})
        items.append(("Water temp", "%.0f°F at the dam sensor." % wt["f"]))
    rn = d.get("rain") or {}
    if rn.get("status") == "ok":
        q = rn.get("qpf") or {}
        items.append(("Rain", "%.2f in last 24 h at the dam; NWS forecast %s in next 24 h." % (rn["last24In"], ("%.2f in" % q["next24In"]) if q.get("status") == "ok" else "unavailable")))
    fc = d.get("forecast") or {}
    if fc.get("status") == "ok" and fc.get("periods"):
        p = fc["periods"][0]; items.append(("Weather", "%s, high %s°F, wind %s %s." % (p["short"], p["tempF"], p["windDir"], p["windMph"])))
    if L.get("vsGuideFt") is not None and L["vsGuideFt"] <= -3:
        take.append("The lake is %.1f ft below its guide curve, so more shoreline is exposed than usual; check NCWRC ramp notices before launching." % abs(L["vsGuideFt"]))
    if rel.get("band") and rel["band"].get("key") in ("record-low", "much-below"):
        take.append("Flow below the dam is very low for the date.")
    if al.get("items"):
        take.append("Check the %s before an early start." % al["items"][0]["event"])
    if not take:
        take.append("Lake and river readings are close to normal for the date.")
    return {"region": d["region"], "waterType": "freshwater", "items": items, "freshness": fresh, "take": take[:4], "missing": missing,
            "sources": "USGS, USACE Wilmington District, NWS"}


# ------------------------------------------------------------------ build, store, serve
def build(rid: str, reason: str, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    fw = rid in ("falls-lake", "neuse-river", "jordan-lake")
    body = build_fresh(rid, now) if fw else build_salt(rid, now)
    words = len(" ".join([v for _, v in body["items"]] + body["take"]).split())
    b = {"ok": True, "regionId": rid, "issueDate": _issue_date(now), "issuedAt": now.isoformat(), "issuedEt": _et(now).strftime("%a %b %-d, %-I:%M %p ET"),
         "reason": reason, "words": words, **body}
    with _lock:
        _mem[rid] = b
    try:
        STORE.mkdir(parents=True, exist_ok=True)
        (STORE / ("%s.json" % rid)).write_text(json.dumps(b))
    except OSError:
        pass
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


def wake(include_fresh: bool = False) -> dict:
    """Build today's brief for every region that lacks one, in the background. Returns no brief content."""
    now = datetime.now(timezone.utc)
    want = _issue_date(now)
    e = _et(now)
    on_time = PREP <= (e.hour, e.minute) <= (PUBLISH_BY[0], PUBLISH_BY[1] + 15)
    todo = [rid for rid in enabled_regions(include_fresh) if not ((_stored(rid) or {}).get("issueDate") == want)]

    def run():
        for rid in todo:
            try:
                build(rid, "scheduled" if on_time else "on-request")
            except Exception:
                pass
    if todo:
        threading.Thread(target=run, name="brief-wake", daemon=True).start()
    return {"ok": True, "issueDate": want, "building": len(todo)}


def get(rid: str, now: datetime | None = None, include_fresh: bool | None = None) -> tuple[int, dict]:
    if rid not in enabled_regions(include_fresh):
        return 404, {"ok": False, "error": "No brief for this region."}
    now = now or datetime.now(timezone.utc)
    want = _issue_date(now)
    b = _stored(rid)
    if b and b.get("issueDate") == want:
        return 200, b
    # Scheduled build missing (service asleep or restarted): build now and say so.
    try:
        return 200, build(rid, "on-request" if b is None or b.get("issueDate") != want else "rebuilt", now)
    except Exception:
        if b:
            return 200, {**b, "staleNotice": "Today's brief could not be built; this is the brief from %s." % b["issuedEt"]}
        return 503, {"ok": False, "error": "The morning brief is unavailable right now. Live readings are on the conditions page."}


def _scheduler():
    while True:
        e = datetime.now(ET)
        nxt = e.replace(hour=PREP[0], minute=PREP[1], second=0, microsecond=0)
        if nxt <= e:
            nxt += timedelta(days=1)
        time.sleep(max(5, (nxt - e).total_seconds()))
        deadline = datetime.now(ET).replace(hour=PUBLISH_BY[0], minute=PUBLISH_BY[1])
        pending = enabled_regions()
        while pending and datetime.now(ET) < deadline:
            for rid in list(pending):
                try:
                    b = build(rid, "scheduled")
                    if not b["missing"]:
                        pending.remove(rid)
                except Exception:
                    pass
            if pending:
                time.sleep(180)


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
    if m:
        cells.append({"key": "Wind", "kind": "observed", "value": m.group(1), "unit": "kt", "sub": "from " + m.group(2), "tone": "wind"})
    seas = _item(b, "Seas")
    m = re.search(r"([\d.]+)\s*ft every (\d+)\s*s from the (\w+)", seas)
    if m:
        cells.append({"key": "Seas", "kind": "observed", "value": m.group(1), "unit": "ft", "sub": "every %s s · from %s" % (m.group(2), m.group(3)), "tone": "seas"})
    swell = _item(b, "Swell")
    m = re.search(r"([\d.]+)\s*ft at ([\d.]+)\s*s from the (\w+)", swell)
    if m:
        per = m.group(2).rstrip("0").rstrip(".") if "." in m.group(2) else m.group(2)
        cells.append({"key": "Swell", "kind": "observed", "value": m.group(1), "unit": "ft", "sub": "%s s · from %s" % (per, m.group(3)), "tone": "swell"})
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


def page(b: dict, include_fresh: bool = False, public: bool = False, ads_on: bool = False) -> str:
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
    adv = _advisory(b)
    if adv:
        adv_html = ('<section class="mb-adv is-%s" aria-label="%s"><span class="mb-adv-dot" aria-hidden="true"></span>'
                    '<div><p class="mb-adv-k">%s</p><p class="mb-adv-t">%s</p></div></section>'
                    % (esc(adv["kind"]), esc(adv["label"]), esc(adv["label"]), esc(adv["text"])))
    else:
        adv_html = ""
    glance_cells = []
    for c in _glance(b):
        glance_cells.append(
            '<div class="mb-gc tone-%s kind-%s"><span class="mb-gk">%s</span>'
            '<span class="mb-gv"><b>%s</b><span class="mb-gu">%s</span></span>'
            '<span class="mb-gs">%s</span><span class="mb-gkind">%s</span></div>'
            % (esc(c["tone"]), esc(c["kind"]), esc(c["key"]), esc(c["value"]), esc(c["unit"]), esc(c["sub"]), esc(c["kind"]))
        )
    glance = ('<section class="mb-glance" aria-label="At a glance">%s</section>' % "".join(glance_cells)) if glance_cells else ""
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
    # Region switcher: saltwater briefs always; Falls Lake only when freshwater is in this preview.
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
<meta name="theme-color" content="#0B2A3D">
<title>Morning Brief · %(name)s — The Coastal Brief</title>
<meta name="description" content="%(desc)s">
<meta property="og:title" content="%(og_title)s">
<meta property="og:description" content="%(desc)s">
<meta property="og:url" content="%(og_url)s">
<meta property="og:type" content="article">
<meta property="og:image" content="https://thecoastalbrief.com/branding/og-preview.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="Coastal Brief wordmark over a breaking teal wave on a navy background, with the line North Carolina fishing, surfing, and boating conditions.">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="%(og_title)s">
<meta name="twitter:description" content="%(desc)s">
<meta name="twitter:image" content="https://thecoastalbrief.com/branding/og-preview.png">
<link rel="icon" href="/branding/favicon.svg" type="image/svg+xml">
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
        "glance": glance,
        "rows": rows_html,
        "miss": miss,
        "take": take_ps,
        "src": esc(b.get("sources") or ""),
    }


