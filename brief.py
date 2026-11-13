"""Morning Brief: a short daily summary per enabled region, built only from verified readings.

Off unless MORNING_BRIEF_ENABLED=1. Never includes market data. The Captain's take is produced by fixed
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
    return (os.environ.get("MORNING_BRIEF_ENABLED") or "").strip() in ("1", "true", "on")


def enabled_regions() -> list[str]:
    cfg = conditions.load_regions()
    out = [r["id"] for r in cfg.get("regions") or [] if conditions._servable(r)]
    try:  # freshwater regions only when their own preview flag is on
        import freshwater
        if freshwater.flag_on():
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


def get(rid: str, now: datetime | None = None) -> tuple[int, dict]:
    if rid not in enabled_regions():
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
def page(b: dict) -> str:
    esc = html.escape
    reason = {"scheduled": "Prepared on schedule at 5:15 AM ET.", "on-request": "Built on request because the 5:15 AM scheduled build did not run (the server was asleep or restarting).",
              "rebuilt": "Rebuilt on request after a server restart.", "manual": "Built manually for testing."}.get(b.get("reason"), "")
    fr = "".join('<li>%s <b>%s</b>%s</li>' % (esc(f["label"]), esc(f["time"]), ' <span class="mb-stale">stale</span>' if f.get("stale") else "") for f in b["freshness"])
    rows = "".join('<div class="mb-row"><dt>%s</dt><dd>%s</dd></div>' % (esc(k), esc(v)) for k, v in b["items"])
    miss = ('<p class="mb-miss">Not available at issue time: %s.</p>' % esc(", ".join(b["missing"]))) if b.get("missing") else ""
    stale = ('<p class="mb-miss">%s</p>' % esc(b["staleNotice"])) if b.get("staleNotice") else ""
    return """<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow"><title>Morning Brief (private preview) · %(name)s</title>
<script>(function(){try{var t=localStorage.getItem("coastalBrief.theme");if(t!=="light"&&t!=="dark")t=matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light";document.documentElement.setAttribute("data-theme",t)}catch(e){}})();</script>
<link rel="stylesheet" href="/styles.css"><style>
body{background:var(--d-panel);color:var(--d-ink)} .mb{max-width:640px;margin:0 auto;padding:14px 16px 40px}
.mb-badge{display:inline-block;font:700 .7rem/1.6 var(--f-ui);letter-spacing:.1em;text-transform:uppercase;color:#fff;background:#8c2f23;padding:2px 8px;border-radius:3px}
.mb h1{font:600 1.7rem/1.1 var(--f-display);margin:10px 0 2px}.mb .mb-tag{font:italic 500 1rem var(--f-display);color:var(--d-ink-2);margin:0 0 12px}
.mb-issue{border:1px solid var(--d-edge);border-radius:12px;padding:10px 12px;background:var(--d-inst);font-size:.86rem}
.mb-issue b{font-weight:700}.mb-issue ul{list-style:none;margin:6px 0 0;padding:0;display:flex;flex-wrap:wrap;gap:2px 14px;color:var(--d-ink-2)}
.mb-issue .why{color:var(--d-ink-2);margin:4px 0 0}.mb-stale{color:#B42318;font-weight:700}
.mb dl{margin:16px 0 0}.mb-row{display:grid;grid-template-columns:7.5em 1fr;gap:10px;padding:8px 0;border-bottom:1px solid var(--d-edge)}
.mb dt{font:700 .72rem/1.5 var(--f-ui);letter-spacing:.12em;text-transform:uppercase;color:var(--d-ink-2);padding-top:2px}.mb dd{margin:0;font-size:.98rem;line-height:1.42}
.mb-take{margin:18px 0 0;padding:12px 14px;border-left:3px solid var(--copper,#A9633A);background:var(--d-inst);border-radius:0 10px 10px 0}
.mb-take h2{font:700 .72rem/1 var(--f-ui);letter-spacing:.14em;text-transform:uppercase;margin:0 0 6px;color:var(--d-ink-2)}
.mb-take p{margin:0;font:500 1.02rem/1.45 var(--f-display)}.mb-take small{display:block;margin-top:6px;color:var(--d-ink-2);font:400 .8rem var(--f-ui)}
.mb-miss{color:#B42318;font-size:.86rem}.mb-foot{font-size:.8rem;color:var(--d-ink-2);margin-top:16px}
</style></head><body><main class="mb">
<span class="mb-badge">Morning Brief · private preview</span>
<h1>%(name)s</h1><p class="mb-tag">More than the forecast. It's a way of life.</p>
<section class="mb-issue" aria-label="Issue time and data freshness"><b>Issued %(issued)s</b> · %(words)d words<p class="why">%(reason)s</p><ul>%(fr)s</ul></section>
%(stale)s<dl>%(rows)s</dl>%(miss)s
<section class="mb-take"><h2>Captain's take · interpretation</h2><p>%(take)s</p><small>Generated by fixed rules from the readings above. Not an observation and not a fishing report.</small></section>
<p class="mb-foot">Sources: %(src)s. Live readings keep updating on the <a href="/">conditions page</a>; this brief does not. Not endorsed by NOAA.</p>
</main></body></html>""" % {"name": esc(b["region"]["name"]), "issued": esc(b["issuedEt"]), "words": b["words"], "reason": esc(reason), "fr": fr,
                         "stale": stale, "rows": rows, "miss": miss, "take": esc(" ".join(b["take"])), "src": esc(b["sources"])}
