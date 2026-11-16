"""Private preview Morning Briefs for regions that do not have a public brief yet.

Coastal previews (Wilmington, Nags Head, Emerald Isle, Topsail) reuse brief.build_salt.
Freshwater previews (Jordan Lake, Neuse River, Cape Fear River) are based on the Falls Lake brief and
assembled from the same official USGS / USACE / NWPS / NWS feeds as /api/freshwater.
Coastal previews run brief.validate as a read-only check. Jordan Lake, Neuse River and
Cape Fear River previews use river_gate (a freshwater-only quality gate) for the banner; brief.validate
is left unchanged and is not used to accept or reject these previews. They are:

- served only at /preview/brief/<region-id> to a browser holding the cb_preview cookie (404 otherwise);
- built in memory on request and kept in this module's own short cache, never in brief._mem,
  cache/briefs/ or the brief-archive branch;
- never part of brief.enabled_regions(), the 5:15 AM schedule, /api/brief/wake, or /brief.

Public /brief?region=jordan-lake, /brief?region=neuse-river and /brief?region=cape-fear-river stay 404. Falls Lake keeps
its public brief; it has no preview twin.

Readings a region has no honest sensor for are shown as "unavailable" with the region's own
note, the same wording the region dashboards use. Nothing is substituted. Old observations
are never presented as current. Stage is never called depth. Lake elevation is compared only
to the USACE guide curve (NGVD29). NWPS forecasts are labeled as forecasts.
"""
from __future__ import annotations

import html
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import brief
import brief_strings
import conditions
import preview_alerts
import preview_copy

REGIONS = ("wilmington", "nags-head", "emerald-isle", "topsail", "carolina-kure", "corolla-duck")
FRESH_REGIONS = ("jordan-lake", "neuse-river", "cape-fear-river")
TTL_S = 15 * 60
_cache: dict[str, tuple[float, dict]] = {}
_locks = {rid: threading.Lock() for rid in REGIONS + FRESH_REGIONS}

# brief.build_salt names missing items in lower case; map them to region reading kinds.
_MISS_KIND = {"wind": "wind", "seas": "seas", "swell": "swell", "pressure": "pressure"}  # water temp: handled above

_FRESH_NAV = (("jordan-lake", "Jordan Lake"), ("neuse-river", "Neuse River"), ("cape-fear-river", "Cape Fear River"))


def available(rid: str) -> bool:
    """A preview brief exists for this id, and it is not already a real /brief region."""
    if rid in REGIONS:
        cfg = next((r for r in conditions.load_regions().get("regions") or [] if r.get("id") == rid), None)
        return bool(cfg) and conditions._servable(cfg, preview=True) and cfg.get("brief") is not True \
            and rid not in brief.enabled_regions(False)
    if rid in FRESH_REGIONS:
        try:
            import freshwater
            r = freshwater.regions().get(rid) or {}
        except Exception:
            return False
        return bool(r.get("previewReady")) and rid not in brief.enabled_regions(True) \
            and rid not in brief.enabled_regions(False)
    return False


def _cfg(rid: str) -> dict:
    return next((r for r in conditions.load_regions().get("regions") or [] if r.get("id") == rid), {}) or {}


def _no_sensor(spec: dict | None) -> bool:
    return bool(spec) and not (spec.get("sources") or [])


def compose(rid: str, now: datetime | None = None) -> dict:
    """Build a preview brief in memory. Never stores, archives or raises BriefInvalid."""
    now = now or datetime.now(timezone.utc)
    if rid in FRESH_REGIONS:
        return _compose_fresh(rid, now)
    return _compose_salt(rid, now)


_ASSEMBLE_GATE = threading.Lock()


def _compose_salt(rid: str, now: datetime) -> dict:
    # brief.build_salt calls conditions.assemble(rid) without preview=True, which
    # 404s cookie-gated regions. Wrap assemble for this build only.
    with _ASSEMBLE_GATE:
        orig = conditions.assemble

        def _preview_assemble(region_id=None, preview=False):
            if region_id and (preview or conditions.is_preview_salt_region(region_id)):
                return orig(region_id, preview=True)
            return orig(region_id, preview=preview)

        conditions.assemble = _preview_assemble
        try:
            body = brief.build_salt(rid, now)
            st, payload = conditions.assemble(rid, preview=True)
        finally:
            conditions.assemble = orig
    cfg = _cfg(rid)
    if st != 200:
        payload = {}
    body = preview_copy.relabel_salt(rid, body, payload or {}, cfg)
    take = preview_copy.captains_take(rid, body, payload or {}, cfg, body.get("issuedEt") or brief._et(now).strftime("%a %b %-d, %-I:%M %p ET"), now=now)
    body["captainsTake"] = take
    body["summary"] = preview_copy.take_text(take)
    body["readingSources"] = preview_copy.reading_sources(rid, payload or {}, body, cfg, now)
    body["stageNote"] = False
    return _finish(rid, now, body, body["items"], body["missing"], body.get("unavailable") or [])


def _finish(rid: str, now: datetime, body: dict, items: list, missing: list, unavailable: list,
            glance=None, payload=None) -> dict:
    words = len(" ".join([v for _, v in items] + body["take"]).split())
    b = {"ok": True, "regionId": rid, "issueDate": brief._issue_date(now), "issuedAt": now.isoformat(),
         "issuedEt": brief._et(now).strftime("%a %b %-d, %-I:%M %p ET"), "reason": "preview", "words": words,
         **body, "items": items, "missing": missing, "unavailable": unavailable, "preview": True}
    if glance is not None:
        b["glance"] = glance
    if rid in FRESH_REGIONS:
        import river_gate
        gate = river_gate.evaluate(rid, payload, now)
        b["gate"] = gate
        b["validation"] = river_gate.as_validation(gate)
    else:
        errs, summary = brief.validate(b, rid, now)  # read-only: reports, never gates or stores
        b["validation"] = {**summary, "errors": errs}
    return b


# ------------------------------------------------------------------ freshwater previews (Jordan Lake, Neuse River)

def _cfs(v) -> str:
    s = ("%.1f" % v).rstrip("0").rstrip(".")
    return s + " cfs"


def _fresh_add(fresh: list, label: str, reading: dict | None, station: str | None) -> None:
    if not reading or not reading.get("time"):
        return
    fresh.append({"label": label, "time": brief._t(reading["time"]), "station": station,
                  "stale": bool(reading.get("stale"))})


def _band(block: dict) -> str:
    b = block.get("band") or {}
    return (", " + b["label"].lower()) if b.get("label") else ""


def _nwps_forecast(block: dict) -> str:
    """Label an NWPS stage forecast as a forecast, or return empty if none was issued.

    Stage only. An NWPS crest-flow (cfs) estimate is never shown; observed
    USGS discharge stays on the gauge line.
    """
    nw = block.get("nwps") or {}
    fc = nw.get("forecast") if nw.get("status") == "ok" else None
    if not fc or fc.get("crestStage") is None:
        return ""
    lid = nw.get("lid") or ""
    when = (" at " + brief._t(fc["crestTime"])) if fc.get("crestTime") else ""
    issued = (" issued " + brief._t(fc["issued"])) if fc.get("issued") else ""
    cat = (fc.get("category") or "").replace("_", " ").strip()
    if not cat or cat in ("no flooding", "noflooding"):
        flood = "no flooding forecast"
    else:
        flood = cat
    issued_bit = ("," + issued) if issued else ""
    datum = ""
    if block.get("nwpsMinusUsgsFt") is not None:
        datum = " (AHPS level, not USGS gage height)"
    word = "highest stage, no rise forecast;" if preview_copy.crest_is_start(fc) else "crest"   # no crest named when NWPS forecasts no rise
    return " NWS forecast (NWPS %s): %s %.1f ft%s%s, %s%s." % (lid, word, fc["crestStage"], datum, when, flood, issued_bit)


def _vs_action(block: dict) -> str:
    stage = (block.get("stageFt") or {}).get("value")
    fl = ((block.get("nwps") or {}).get("floodStages") if (block.get("nwps") or {}).get("status") == "ok" else None) \
        or block.get("floodStages") or {}
    action = fl.get("action")
    minor = fl.get("minor")
    offset = block.get("nwpsMinusUsgsFt")
    if offset:
        # NWPS flood stages at Huske are AHPS levels, not USGS gage height.
        action = (action - offset) if action is not None else None
        minor = (minor - offset) if minor is not None else None
    if stage is None or action is None:
        return ""
    if minor is not None and stage >= minor:
        return " Stage is at or above the NWS minor flood stage (%.1f ft USGS gage height)." % minor
    if stage >= action:
        return " Stage is at or above the NWS action stage (%.1f ft USGS gage height)." % action
    return ""


def _river_item(block: dict) -> tuple[str, str]:
    label = block.get("label") or ("USGS " + (block.get("usgs") or ""))
    bits = []
    stage, flow = block.get("stageFt"), block.get("flowCfs")
    if stage:
        bits.append("%.2f ft stage" % stage["value"])
    if flow and not (block.get("stageOnly") or block.get("flowNote")):
        bits.append(_cfs(flow["value"]) + (" (regulated)" if block.get("regulated") else "") + _band(block))
    elif not stage:
        bits.append("not available from USGS right now")
    text = "%s at USGS %s." % (", ".join(bits), block.get("usgs") or "")
    if block.get("stageOnly") or (block.get("flowNote") and not flow):
        text += " USGS does not publish discharge at this gauge (stage only)."
    if block.get("note"):
        text += " " + block["note"]
    text += _vs_action(block)
    text += _nwps_forecast(block)
    return label, text


def _alert_item(d: dict, place: str) -> tuple[str, str]:
    al = d.get("alerts") or {}
    if al.get("items"):
        text = "; ".join("%s until %s" % (a["event"], brief._t(a["ends"])) if a.get("ends") else a["event"]
                         for a in al["items"]) + "."
    elif al.get("status") == "ok":
        text = "No NWS alerts %s." % place
    else:
        text = "Could not check NWS alerts."
    return "Alerts", text


def _weather_item(d: dict, missing: list) -> tuple[str, str] | None:
    fc = d.get("forecast") or {}
    if fc.get("status") == "ok" and fc.get("periods"):
        p = fc["periods"][0]
        return ("Weather", "%s, high %s°F, wind %s %s (NWS forecast)." % (p["short"], p["tempF"], p["windDir"], p["windMph"]))
    missing.append("weather forecast")
    return None


def _water_temp_unavailable(d: dict, cfg: dict) -> tuple[str, str]:
    note = ((d.get("waterTemp") or {}).get("note")
            or (cfg.get("waterTemp") or {}).get("note")
            or "No USGS water-temperature sensor at this location.")
    return "Water temp", note


def _compose_jordan(d: dict, cfg: dict, now: datetime) -> tuple[list, list, list, list, list]:
    items, fresh, take, missing, unavailable = [], [], [], [], []
    items.append(_alert_item(d, "at the dam"))
    L = d.get("lake") or {}
    e = L.get("elevation")
    if e:
        _fresh_add(fresh, "Lake level", e, L.get("usgs"))
        vs = L.get("vsGuideFt")
        vs_txt = "n/a vs the %.1f ft guide curve" % L["guideCurveFt"] if vs is None else (
            "%.2f ft %s the %.1f ft guide curve" % (abs(vs), "below" if vs < 0 else "above", L["guideCurveFt"]))
        ch = L.get("change24hFt")
        ch_txt = ("%+.2f" % ch) if ch is not None else "n/a"
        items.append(("Lake level",
                      "%.2f ft (NGVD29), %s; %s ft in 24 h. %s" % (e["value"], vs_txt, ch_txt, preview_copy.JORDAN_GUIDE_NOTE)))
    else:
        missing.append("lake level")
    rel = d.get("release") or {}
    if rel.get("flowCfs"):
        _fresh_add(fresh, "Haw River at Moncure", rel["flowCfs"], rel.get("usgs"))
        if rel.get("stageFt") and rel["stageFt"].get("time") != rel["flowCfs"].get("time"):
            _fresh_add(fresh, "Stage at Moncure", rel["stageFt"], rel.get("usgs"))
        stage_bit = (", %.2f ft stage" % rel["stageFt"]["value"]) if rel.get("stageFt") else ""
        note = rel.get("note") or "Dam release plus local runoff, not the official gate outflow."
        items.append((preview_copy.MONCURE_LABEL,
                      "%s at Haw River near Moncure (USGS %s)%s%s. %s" % (
                          _cfs(rel["flowCfs"]["value"]), rel.get("usgs") or "", stage_bit, _band(rel), preview_copy.MONCURE_SUB)))
    else:
        missing.append("release plus runoff")
        if rel.get("note"):
            # A missing flow is a gap at issue time, not a missing sensor.
            pass
    inf = [i for i in (d.get("inflows") or []) if i.get("flowCfs")]
    if inf:
        for i in inf:
            short = (i.get("label") or "Inflow").split("(")[0].strip()
            _fresh_add(fresh, short, i["flowCfs"], i.get("usgs"))
        items.append(("Inflow",
                      "; ".join("%s %s%s at USGS %s" % (
                          i.get("label") or "Inflow", _cfs(i["flowCfs"]["value"]), _band(i), i.get("usgs") or "")
                          for i in inf) + "."))
    unavailable.append(_water_temp_unavailable(d, cfg))
    rn = d.get("rain") or {}
    if rn.get("status") == "ok":
        _fresh_add(fresh, "Rain", {"time": rn.get("time"), "stale": rn.get("stale")}, rn.get("usgs"))
        q = rn.get("qpf") or {}
        if q.get("status") == "ok":
            qpf = "NWS forecast %.2f in over the next 24 h" % q["next24In"]
        else:
            qpf = "NWS 24-hour forecast unavailable"
        last = rn.get("last24In")
        last_txt = ("%.2f in" % last) if last is not None else "unavailable"
        items.append(("Rain", "%s last 24 h at the dam; %s." % (last_txt, qpf)))
    elif rn is None:
        pass
    else:
        missing.append("rain")
    wx = _weather_item(d, missing)
    if wx:
        items.append(wx)
    vs = (d.get("lake") or {}).get("vsGuideFt")
    if vs is not None and vs <= -3:
        take.append("The lake is %.1f ft below its guide curve, so more shoreline is exposed than usual; check NCWRC ramp notices before launching." % abs(vs))
    al = d.get("alerts") or {}
    if al.get("items"):
        take.append("Check the %s before an early start." % al["items"][0]["event"])
    if not take:
        none = preview_alerts.alert_line(al, "jordan-lake")
        none = none[len("Alerts: "):] if none.startswith("Alerts: ") else none
        if vs is not None and abs(vs) < 0.5:
            take.append("The lake is close to its 216.0 ft guide curve. " + none)
        elif vs is not None:
            take.append("The lake is %.1f ft %s its 216.0 ft guide curve. %s"
                        % (abs(vs), "below" if vs < 0 else "above", none))
        else:
            take.append(none)
    return items, fresh, take[:4], missing, unavailable


def _compose_neuse(d: dict, cfg: dict, now: datetime) -> tuple[list, list, list, list, list]:
    items, fresh, take, missing, unavailable = [], [], [], [], []
    items.append(_alert_item(d, "at Clayton"))
    river = d.get("river") or []
    if not river:
        missing.append("river gauges")
    for block in river:
        label, text = _river_item(block)
        items.append((label, text))
        stage, flow = block.get("stageFt"), block.get("flowCfs")
        name = block.get("label") or "Gauge"
        if stage and flow and stage.get("time") == flow.get("time"):
            _fresh_add(fresh, name, {"time": stage["time"], "stale": bool(stage.get("stale") or flow.get("stale"))},
                       block.get("usgs"))
        else:
            if stage:
                _fresh_add(fresh, name + " (stage)", stage, block.get("usgs"))
            if flow:
                _fresh_add(fresh, name + " (flow)", flow, block.get("usgs"))
    unavailable.append(_water_temp_unavailable(d, cfg))
    wx = _weather_item(d, missing)
    if wx:
        items.append(wx)
    al = d.get("alerts") or {}
    if al.get("items"):
        take.append("Check the %s before an early start." % al["items"][0]["event"])
    flood = [b for b in river if _vs_action(b)]
    if flood:
        take.append("Stage is at or above the NWS action stage at %s." %
                    ", ".join(b.get("label") or b.get("usgs") for b in flood))
    low = [b for b in river if (b.get("band") or {}).get("key") in ("record-low", "much-below")]
    if low:
        take.append("Flow is very low for the date at %s (regulated by Falls Dam)." %
                    ", ".join(b.get("label") or b.get("usgs") for b in low))
    if not take:
        take.append(preview_alerts.alert_line(al, "neuse-river")[len("Alerts: "):] + " The gauges are not at action stage.")
    return items, fresh, take[:4], missing, unavailable



def _compose_cape_fear(d: dict, cfg: dict, now: datetime) -> tuple[list, list, list, list, list]:
    items, fresh, take, missing, unavailable = [], [], [], [], []
    items.append(_alert_item(d, "at Fayetteville"))
    river = d.get("river") or []
    if not river:
        missing.append("river gauges")
    for block in river:
        label, text = _river_item(block)
        items.append((label, text))
        stage, flow = block.get("stageFt"), block.get("flowCfs")
        name = block.get("label") or "Gauge"
        if stage and flow and stage.get("time") == flow.get("time"):
            _fresh_add(fresh, name, {"time": stage["time"], "stale": bool(stage.get("stale") or flow.get("stale"))},
                       block.get("usgs"))
        else:
            if stage:
                _fresh_add(fresh, name + " (stage)", stage, block.get("usgs"))
            if flow:
                _fresh_add(fresh, name + " (flow)", flow, block.get("usgs"))
    wt = d.get("waterTemp") or {}
    if wt.get("status") == "ok" and wt.get("f") is not None:
        _fresh_add(fresh, "Water temp", wt, wt.get("usgs"))
        items.append(("Water temp", "%.0f°F (%.1f °C) at USGS %s." % (wt["f"], wt["c"], wt.get("usgs") or "")))
    else:
        unavailable.append(_water_temp_unavailable(d, cfg))
    wx = _weather_item(d, missing)
    if wx:
        items.append(wx)
    al = d.get("alerts") or {}
    if al.get("items"):
        take.append("Check the %s before an early start." % al["items"][0]["event"])
    flood = [b for b in river if _vs_action(b)]
    if flood:
        take.append("Stage is at or above the NWS action stage at %s." %
                    ", ".join(b.get("label") or b.get("usgs") for b in flood))
    low = [b for b in river if (b.get("band") or {}).get("key") in ("record-low", "much-below")]
    if low:
        take.append("Flow is very low for the date at %s (regulated by Jordan Lake and the locks)." %
                    ", ".join(b.get("label") or b.get("usgs") for b in low))
    if not take:
        line = preview_alerts.alert_line(al, "cape-fear-river")
        line = line[len("Alerts: "):] if line.startswith("Alerts: ") else line
        take.append(line + " The gauges are not at action stage.")
    return items, fresh, take[:4], missing, unavailable


def _glance_jordan(items: list) -> list[dict]:
    cells: list[dict] = []
    d = dict(items)
    lake = d.get("Lake level") or ""
    m = re.search(r"([\d.]+)\s*ft", lake)
    vs = re.search(r"([\d.]+)\s*ft\s+(below|above)", lake)
    if m:
        sub = (vs.group(1) + " ft " + vs.group(2) + " guide") if vs else "NGVD29"
        cells.append({"key": "Lake level", "kind": "observed", "value": m.group(1), "unit": "ft", "sub": sub, "tone": "lake"})
    rel = d.get(preview_copy.MONCURE_LABEL) or d.get("Release plus runoff") or ""
    rel_obs = re.split(r"\s+NWS forecast\b", rel, maxsplit=1)[0]
    m = re.search(r"([\d.]+)\s*cfs", rel_obs)
    if m:
        cells.append({"key": "Haw River at Moncure", "kind": "observed", "value": m.group(1).rstrip("0").rstrip(".") if "." in m.group(1) else m.group(1),
                      "unit": "cfs", "sub": "USGS 02098206 · not official discharge", "tone": "lake"})
    rain = d.get("Rain") or ""
    m = re.search(r"([\d.]+)\s*in last 24 h", rain)
    if m:
        cells.append({"key": "Rain, 24 h", "kind": "observed", "value": m.group(1), "unit": "in", "sub": "at the dam", "tone": "lake"})
    wx = d.get("Weather") or ""
    m = re.search(r"high\s+(\d+)°F", wx, re.I)
    if m:
        short = (re.split(r",\s*high", wx, maxsplit=1)[0] or "").strip()
        cells.append({"key": "Air high", "kind": "forecast", "value": m.group(1), "unit": "°F", "sub": short or "NWS forecast", "tone": "air"})
    return cells


def _glance_neuse(items: list) -> list[dict]:
    cells: list[dict] = []
    d = dict(items)
    clay = d.get("Neuse River near Clayton") or ""
    clay_obs = re.split(r"\s+NWS forecast\b", clay, maxsplit=1)[0]
    m = re.search(r"([\d.]+)\s*ft stage", clay_obs)
    if m:
        cells.append({"key": "Clayton stage", "kind": "observed", "value": m.group(1), "unit": "ft", "sub": "USGS 02087500", "tone": "lake"})
    m = re.search(r"([\d.]+)\s*cfs", clay_obs)
    if m:
        val = m.group(1).rstrip("0").rstrip(".") if "." in m.group(1) else m.group(1)
        cells.append({"key": "Clayton flow", "kind": "observed", "value": val, "unit": "cfs", "sub": "regulated", "tone": "lake"})
    falls = d.get("Neuse River below Falls Dam") or ""
    falls_obs = re.split(r"\s+NWS forecast\b", falls, maxsplit=1)[0]
    m = re.search(r"([\d.]+)\s*cfs", falls_obs)
    if m:
        val = m.group(1).rstrip("0").rstrip(".") if "." in m.group(1) else m.group(1)
        cells.append({"key": "Below Falls Dam", "kind": "observed", "value": val, "unit": "cfs", "sub": "regulated release", "tone": "lake"})
    wx = d.get("Weather") or ""
    m = re.search(r"high\s+(\d+)°F", wx, re.I)
    if m:
        short = (re.split(r",\s*high", wx, maxsplit=1)[0] or "").strip()
        cells.append({"key": "Air high", "kind": "forecast", "value": m.group(1), "unit": "°F", "sub": short or "NWS forecast", "tone": "air"})
    return cells



def _glance_cape_fear(items: list) -> list[dict]:
    cells: list[dict] = []
    d = dict(items)
    fay = d.get("Cape Fear River at Fayetteville") or ""
    fay_obs = re.split(r"\s+NWS forecast\b", fay, maxsplit=1)[0]
    m = re.search(r"([\d.]+)\s*ft stage", fay_obs)
    if m:
        cells.append({"key": "Fayetteville stage", "kind": "observed", "value": m.group(1), "unit": "ft", "sub": "USGS 02104000", "tone": "lake"})
    m = re.search(r"([\d.]+)\s*cfs", fay_obs)
    if m:
        val = m.group(1).rstrip("0").rstrip(".") if "." in m.group(1) else m.group(1)
        cells.append({"key": "Fayetteville flow", "kind": "observed", "value": val, "unit": "cfs", "sub": "regulated", "tone": "lake"})
    lil = d.get("Cape Fear River at Lillington") or ""
    lil_obs = re.split(r"\s+NWS forecast\b", lil, maxsplit=1)[0]
    m = re.search(r"([\d.]+)\s*cfs", lil_obs)
    if m:
        val = m.group(1).rstrip("0").rstrip(".") if "." in m.group(1) else m.group(1)
        cells.append({"key": "Lillington flow", "kind": "observed", "value": val, "unit": "cfs", "sub": "regulated", "tone": "lake"})
    wx = d.get("Weather") or ""
    m = re.search(r"high\s+(\d+)°F", wx, re.I)
    if m:
        short = (re.split(r",\s*high", wx, maxsplit=1)[0] or "").strip()
        cells.append({"key": "Air high", "kind": "forecast", "value": m.group(1), "unit": "°F", "sub": short or "NWS forecast", "tone": "air"})
    return cells


def _compose_fresh(rid: str, now: datetime) -> dict:
    import freshwater
    st, d = freshwater.assemble(rid)
    if st != 200:
        raise RuntimeError((d or {}).get("error") or "freshwater readings were not available")
    d = preview_alerts.apply_coverage(rid, d)
    cfg = freshwater.regions().get(rid) or {}
    if rid == "jordan-lake":
        items, fresh, take, missing, unavailable = _compose_jordan(d, cfg, now)
        items, missing, unavailable = preview_copy.polish_fresh_items(rid, items, missing, unavailable, d)
        glance = _glance_jordan(items)
        sources = "USGS, USACE Wilmington District, NWS"
    elif rid == "cape-fear-river":
        items, fresh, take, missing, unavailable = _compose_cape_fear(d, cfg, now)
        items, missing, unavailable = preview_copy.polish_fresh_items(rid, items, missing, unavailable, d)
        glance = _glance_cape_fear(items)
        sources = "USGS, NWS"
    else:
        items, fresh, take, missing, unavailable = _compose_neuse(d, cfg, now)
        items, missing, unavailable = preview_copy.polish_fresh_items(rid, items, missing, unavailable, d)
        glance = _glance_neuse(items)
        sources = "USGS, NWS"
    issued = brief._et(now).strftime("%a %b %-d, %-I:%M %p ET")
    body_tmp = {"items": items, "missing": missing, "issuedEt": issued}
    take_model = preview_copy.captains_take(rid, body_tmp, d, cfg, issued, now=now)
    body = {"region": d.get("region") or {"id": rid, "name": cfg.get("name"), "area": cfg.get("area"),
                                          "anchor": cfg.get("anchor")},
            "waterType": "freshwater", "items": items, "freshness": fresh, "take": take,
            "missing": missing, "sources": sources,
            "captainsTake": take_model, "summary": preview_copy.take_text(take_model),
            "readingSources": preview_copy.reading_sources(rid, d, body_tmp, cfg, now),
            "stageNote": preview_copy.has_stage(items)}
    return _finish(rid, now, body, items, missing, unavailable, glance=glance, payload=d)


def get(rid: str, now: datetime | None = None) -> tuple[int, dict]:
    if not available(rid):
        return 404, {"ok": False, "error": "No preview brief for this region."}
    with _locks[rid]:
        hit = _cache.get(rid)
        if hit and time.time() - hit[0] < TTL_S and now is None:
            return 200, hit[1]
        try:
            b = compose(rid, now)
        except Exception as e:
            return 503, {"ok": False, "error": brief_strings.not_available("Morning Brief") + " (%s)." % (str(e) or type(e).__name__)}
        _cache[rid] = (time.time(), b)
        return 200, b


def _names(rid: str = "") -> list[tuple[str, str]]:
    if rid in FRESH_REGIONS:
        return list(_FRESH_NAV)
    out = []
    for i in REGIONS:
        out.append((i, _cfg(i).get("name") or i))
    return out


def _glance_html(cells: list[dict]) -> str:
    esc = html.escape
    if not cells:
        return ""
    out = []
    for c in cells:
        out.append(
            '<div class="mb-gc tone-%s kind-%s"><span class="mb-gk">%s</span>'
            '<span class="mb-gv"><b>%s</b><span class="mb-gu">%s</span></span>'
            '<span class="mb-gs">%s</span><span class="mb-gkind">%s</span></div>'
            % (esc(c["tone"]), esc(c["kind"]), esc(c["key"]), esc(c["value"]), esc(c["unit"]), esc(c["sub"]), esc(c["kind"]))
        )
    return '<section class="mb-glance" aria-label="At a glance">%s</section>' % "".join(out)


def banner_check(b: dict) -> str:
    """Banner sentence for data checks. Freshwater previews use river_gate; coastal previews use brief.validate."""
    v = b.get("validation") or {}
    rid = b.get("regionId") or ""
    if rid in FRESH_REGIONS and v.get("gate") == "freshwater-preview":
        if v.get("errors"):
            return "Data checks: would NOT pass (%s)." % "; ".join(v["errors"])
        return "Data checks: would pass (%s)." % ("; ".join(v.get("notes") or []) or "all core checks present")
    if v.get("errors"):
        return "Data checks: would NOT pass (%s)." % "; ".join(v["errors"])
    bits = []
    if v.get("status") == "partial":
        bits.append("some readings missing at issue time")
    if b.get("unavailable"):
        bits.append("some readings have no local sensor, listed below")
    return "Data checks: would pass (%s)." % ("; ".join(bits) or "all core readings present")


def page(b: dict) -> str:
    """brief.page() with a private-preview banner, preview navigation, and an Unavailable section."""
    esc = html.escape
    rid = b.get("regionId") or ""
    out = brief.page(b, include_fresh=False, public=False, ads_on=False)
    nav = "".join('<a href="/preview/brief/%s"%s>%s</a>' % (esc(i), ' aria-current="page"' if i == rid else "", esc(n))
                  for i, n in _names(rid))
    out = re.sub(r'<nav class="mb-regions" aria-label="Brief region">.*?</nav>',
                 lambda m: '<nav class="mb-regions" aria-label="Preview brief region">%s</nav>' % nav, out, count=1, flags=re.S)
    if rid in FRESH_REGIONS and b.get("glance") is not None:
        repl = _glance_html(b["glance"])
        out, n = re.subn(r'<section class="mb-glance" aria-label="At a glance">.*?</section>',
                         repl, out, count=1, flags=re.S)
        if n == 0 and repl:
            out = out.replace('<details class="mb-details" id="mb-details">', repl + '\n  <details class="mb-details" id="mb-details">', 1)
    v = b.get("validation") or {}
    check = banner_check(b)
    banner = ('<section class="mb-pv" style="margin:0 0 14px;padding:10px 12px;border:2px dashed #8c2f23;border-radius:10px">'
              '<p style="margin:0;font-weight:700;letter-spacing:.08em;text-transform:uppercase;font-size:.72rem;color:#8c2f23">'
              'Private preview · not published</p><p style="margin:4px 0 0;font-size:.88rem">Built on request from live readings for '
              'this browser only. Not on the schedule, not archived, and not linked from the site. %s</p></section>'
              % esc(check))
    out = out.replace('<main class="mb" id="brief-body">', '<main class="mb" id="brief-body">\n  ' + banner, 1)
    out = out.replace('<p class="mb-why"> · ', '<p class="mb-why">Private preview, built on request · ', 1)
    out = out.replace("<title>Morning Brief", "<title>Preview · Morning Brief", 1)
    out = out.replace("https://thecoastalbrief.com/brief?region=%s" % esc(rid), "https://thecoastalbrief.com/preview/brief/%s" % esc(rid))
    out = preview_copy.inject_page(out, b)
    return _apply_polish(out)

# Presentation-only polish for /preview/brief/* pages, applied in page() after
# brief.page() returns. Strings, data logic and values are not changed.
# Touches in this file: Path import; these helpers; a final _apply_polish()
# call at the end of page(). page() still does its existing banner, nav,
# glance, title and unavailable-section replacements first.
_POLISH_CSS = Path(__file__).resolve().parent / "preview" / "brief-polish.css"

_TOOLS_FROM = """    <div class="mb-tools">
      <button type="button" class="mb-print" onclick="window.print()">Print</button>
      <button type="button" id="theme-toggle" class="theme-toggle" aria-pressed="false" aria-label="Switch to dark mode">Dark mode</button>
    </div>"""

_TOOLS_TO = """    <div class="mb-tools" role="group" aria-label="Page tools">
      <button type="button" class="mb-print" onclick="window.print()" aria-label="Print">
        <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" focusable="false"><path fill="none" stroke="currentColor" stroke-width="1.75" stroke-linejoin="round" d="M7 8V3.5h10V8M7 17H5.5A2.5 2.5 0 0 1 3 14.5v-5A2.5 2.5 0 0 1 5.5 7h13A2.5 2.5 0 0 1 21 9.5v5A2.5 2.5 0 0 1 18.5 17H17M7 14h10v6.5H7z"/></svg>
      </button>
      <button type="button" id="theme-toggle" class="theme-toggle" aria-pressed="false" aria-label="Switch to dark mode">
        <svg class="mb-icon-moon" viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" focusable="false"><path fill="none" stroke="currentColor" stroke-width="1.75" stroke-linejoin="round" d="M15.2 3.5A8.5 8.5 0 1 0 20.5 14 7 7 0 0 1 15.2 3.5z"/></svg>
        <svg class="mb-icon-sun" viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" focusable="false"><circle cx="12" cy="12" r="3.5" fill="none" stroke="currentColor" stroke-width="1.75"/><path fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" d="M12 3v2.2M12 18.8V21M3 12h2.2M18.8 12H21M5.6 5.6l1.6 1.6M16.8 16.8l1.6 1.6M18.4 5.6l-1.6 1.6M7.2 16.8l-1.6 1.6"/></svg>
      </button>
    </div>"""

_DETAILS_SCRIPT_FROM = """    var d=document.getElementById("mb-details");
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
    window.addEventListener("afterprint", apply);"""

_DETAILS_SCRIPT_TO = """    var d=document.getElementById("mb-details");
    var src=document.getElementById("mb-sources");
    var wide=window.matchMedia("(min-width: 601px)");
    function applyOne(el){
      if(!el)return;
      if(wide.matches) el.open=true;
      else if(!el.hasAttribute("data-user")) el.open=false;
    }
    function apply(){ applyOne(d); applyOne(src); }
    apply();
    function track(el){ if(el) el.addEventListener("toggle", function(){ if(!wide.matches) el.setAttribute("data-user","1"); }); }
    track(d); track(src);
    if(wide.addEventListener) wide.addEventListener("change", apply);
    else wide.addListener(apply);
    window.addEventListener("beforeprint", function(){ if(d)d.open=true; if(src)src.open=true; });
    window.addEventListener("afterprint", apply);"""


def _inject_polish_css(out: str) -> str:
    css = _POLISH_CSS.read_text(encoding="utf-8").replace("</", "<\\/")
    return out.replace("</head>", '<style id="brief-polish">\n%s\n</style>\n</head>' % css, 1)


def _compact_tools(out: str) -> str:
    if _TOOLS_FROM not in out:
        return out
    out = out.replace(_TOOLS_FROM, _TOOLS_TO, 1)
    out = out.replace('    btn.textContent=dark?"Light mode":"Dark mode";\n', "", 1)
    return out


def _compact_regions(out: str) -> str:
    """Replace the preview region link row with a compact labeled select.

    The original <a href="..."> links are kept inside <noscript> so existing
    tests and no-JS navigation still see them. Option labels are the same
    region names; no strings are rewritten.
    """
    m = re.search(
        r'<nav class="mb-regions" aria-label="Preview brief region">(.*?)</nav>',
        out, flags=re.S,
    )
    if not m:
        return out
    links = re.findall(r'<a href="(/preview/brief/[^"]+)"([^>]*)>([^<]*)</a>', m.group(1))
    if not links:
        return out
    opts, anchors = [], []
    for href, attrs, name in links:
        sel = " selected" if 'aria-current="page"' in attrs else ""
        opts.append('<option value="%s"%s>%s</option>' % (href, sel, name))
        anchors.append('<a href="%s"%s>%s</a>' % (href, attrs, name))
    nav = (
        '<nav class="mb-regions" aria-label="Preview brief region">'
        '<label class="mb-rv-label" for="mb-region-select">Region</label>'
        '<select id="mb-region-select" class="mb-region-select" autocomplete="off" '
        'onchange="if(this.value)location.href=this.value">'
        + "".join(opts)
        + "</select>"
        "<noscript>" + "".join(anchors) + "</noscript>"
        "</nav>"
    )
    return out[:m.start()] + nav + out[m.end():]


def _wrap_reading_times(out: str) -> str:
    """Fold the reading-times list only if Data has not already placed the
    single #mb-sources panel (full sources content + JSON).
    """
    if 'id="mb-sources"' in out:
        return out
    pat = r'<p class="mb-fresh-k">Reading times</p>\s*<ul class="mb-fresh">.*?</ul>'

    def repl(m: re.Match) -> str:
        ul = re.search(r'<ul class="mb-fresh">.*?</ul>', m.group(0), flags=re.S)
        if not ul:
            return m.group(0)
        return (
            '<details class="mb-sources" id="mb-sources">'
            "<summary>Reading times</summary>"
            + ul.group(0)
            + "</details>"
        )

    return re.sub(pat, repl, out, count=1, flags=re.S)


def _move_take_after_advisories(out: str) -> str:
    """Keep exactly one Captain's Take immediately after the advisories
    strip and before the glance cards, so the briefing reaches the fold.

    Prefers the Data component (section.mb-summary.mb-take with JSON) and
    drops the brief.page bottom take if it is still present. Text, data-kind
    and data-sources are left unchanged.
    """
    takes = list(re.finditer(
        r'\s*<section class="(?:mb-summary )?mb-take\b[^"]*"[^>]*>.*?</section>',
        out, flags=re.S,
    ))
    if not takes:
        return out
    preferred = next((m for m in takes if "mb-summary" in m.group(0) or "cb-captains-take" in m.group(0)), takes[0])
    block = preferred.group(0).strip()
    for m in reversed(takes):
        out = out[:m.start()] + out[m.end():]
    for pat in (
        r'(<section class="mb-adv\b[^"]*"[^>]*>.*?</section>)',
        r'(<section class="mb-issue\b[^"]*"[^>]*>.*?</section>)',
    ):
        n = re.search(pat, out, flags=re.S)
        if n:
            return out[:n.end()] + "\n  " + block + out[n.end():]
    g = re.search(r'<section class="mb-glance\b[^"]*"[^>]*>.*?</section>', out, flags=re.S)
    if g:
        return out[:g.start()] + "\n  " + block + "\n  " + out[g.start():]
    return out + "\n  " + block


def _apply_polish(out: str) -> str:
    out = out.replace('<body class="mb-page">', '<body class="mb-page mb-preview-brief">', 1)
    out = _inject_polish_css(out)
    out = _compact_tools(out)
    out = _compact_regions(out)
    out = _wrap_reading_times(out)
    out = _move_take_after_advisories(out)
    if _DETAILS_SCRIPT_FROM in out:
        out = out.replace(_DETAILS_SCRIPT_FROM, _DETAILS_SCRIPT_TO, 1)
    # Mark glance tiles whose value is already the locked placeholder.
    out = out.replace(
        "</body>",
        '<script>(function(){document.querySelectorAll(".mb-gv b").forEach(function(b){'
        'if((b.textContent||"").trim()==="Not available"){b.parentElement.classList.add("mb-na");}'
        "});})();</script>\n</body>",
        1,
    )
    return out
