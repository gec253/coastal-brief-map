"""Private preview Morning Briefs for regions that do not have a public brief yet.

Coastal previews (Wilmington, Nags Head, Emerald Isle, Topsail) reuse brief.build_salt.
Freshwater previews (Jordan Lake, Neuse River) are based on the Falls Lake brief and
assembled from the same official USGS / USACE / NWPS / NWS feeds as /api/freshwater.
Both kinds run brief.validate as a read-only check, and they are:

- served only at /preview/brief/<region-id> to a browser holding the cb_preview cookie (404 otherwise);
- built in memory on request and kept in this module's own short cache, never in brief._mem,
  cache/briefs/ or the brief-archive branch;
- never part of brief.enabled_regions(), the 5:15 AM schedule, /api/brief/wake, or /brief.

Public /brief?region=jordan-lake and /brief?region=neuse-river stay 404. Falls Lake keeps
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

import brief
import conditions

REGIONS = ("wilmington", "nags-head", "emerald-isle", "topsail")
FRESH_REGIONS = ("jordan-lake", "neuse-river")
TTL_S = 15 * 60
_cache: dict[str, tuple[float, dict]] = {}
_locks = {rid: threading.Lock() for rid in REGIONS + FRESH_REGIONS}

# brief.build_salt names missing items in lower case; map them to region reading kinds.
_MISS_KIND = {"wind": "wind", "seas": "seas", "swell": "swell", "pressure": "pressure"}  # water temp: handled above

_FRESH_NAV = (("jordan-lake", "Jordan Lake"), ("neuse-river", "Neuse River"))


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


def _compose_salt(rid: str, now: datetime) -> dict:
    body = brief.build_salt(rid, now)
    cfg = _cfg(rid)
    specs = cfg.get("readings") or {}
    items = list(body["items"])
    missing = list(body["missing"])
    unavailable = []  # (label, why) shown with the dashboard's "unavailable" treatment
    # brief.build_salt already writes "Inshore unavailable" plus the offshore reading when the region
    # has no inshore sensor; list the region's note so the reader sees why.
    if _no_sensor(specs.get("waterTemp")):
        unavailable.append(("Inshore water temp", specs["waterTemp"].get("note") or "No sensor in this area."))
    # Any other missing reading the region has no sensor for gets its note, never a substitute.
    for name in list(missing):
        kind = _MISS_KIND.get(name)
        if kind and _no_sensor(specs.get(kind)):
            missing.remove(name)
            unavailable.append((name.capitalize(), specs[kind].get("note") or "No sensor in this area."))
    tide = cfg.get("tide") or {}
    if tide.get("observed") is False:
        unavailable.append(("Observed water level", "Tide times are NOAA predictions only. " + (tide.get("note") or "")))
    return _finish(rid, now, body, items, missing, unavailable)


def _finish(rid: str, now: datetime, body: dict, items: list, missing: list, unavailable: list, glance=None) -> dict:
    words = len(" ".join([v for _, v in items] + body["take"]).split())
    b = {"ok": True, "regionId": rid, "issueDate": brief._issue_date(now), "issuedAt": now.isoformat(),
         "issuedEt": brief._et(now).strftime("%a %b %-d, %-I:%M %p ET"), "reason": "preview", "words": words,
         **body, "items": items, "missing": missing, "unavailable": unavailable, "preview": True}
    if glance is not None:
        b["glance"] = glance
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
    """Label an NWPS stage forecast as a forecast, or return empty if none was issued."""
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
    extra = ""
    if fc.get("crestFlowCfs") is not None:
        extra = ", about %s (NWS estimate, not a USGS observation)" % _cfs(fc["crestFlowCfs"])
    issued_bit = ("," + issued) if issued else ""
    return " NWS forecast (NWPS %s): crest %.1f ft%s, %s%s%s." % (lid, fc["crestStage"], when, flood, extra, issued_bit)


def _vs_action(block: dict) -> str:
    stage = (block.get("stageFt") or {}).get("value")
    fl = ((block.get("nwps") or {}).get("floodStages") if (block.get("nwps") or {}).get("status") == "ok" else None) \
        or block.get("floodStages") or {}
    action = fl.get("action")
    minor = fl.get("minor")
    if stage is None or action is None:
        return ""
    if minor is not None and stage >= minor:
        return " Stage is at or above the NWS minor flood stage (%.0f ft)." % minor
    if stage >= action:
        return " Stage is at or above the NWS action stage (%.0f ft)." % action
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
                      "%.2f ft (NGVD29), %s; %s ft in 24 h." % (e["value"], vs_txt, ch_txt)))
    else:
        missing.append("lake level")
    rel = d.get("release") or {}
    if rel.get("flowCfs"):
        _fresh_add(fresh, "Release plus runoff", rel["flowCfs"], rel.get("usgs"))
        if rel.get("stageFt") and rel["stageFt"].get("time") != rel["flowCfs"].get("time"):
            _fresh_add(fresh, "Stage at Moncure", rel["stageFt"], rel.get("usgs"))
        stage_bit = (", %.2f ft stage" % rel["stageFt"]["value"]) if rel.get("stageFt") else ""
        note = rel.get("note") or "Dam release plus local runoff, not the official gate outflow."
        items.append(("Release plus runoff",
                      "%s at Haw River near Moncure (USGS %s)%s%s. %s" % (
                          _cfs(rel["flowCfs"]["value"]), rel.get("usgs") or "", stage_bit, _band(rel), note)))
    else:
        missing.append("release plus runoff")
        if rel.get("note"):
            # A missing flow is a gap at issue time, not a missing sensor.
            pass
    inf = [i for i in (d.get("inflows") or []) if i.get("flowCfs")]
    if inf:
        for i in inf:
            _fresh_add(fresh, i.get("label") or "Inflow", i["flowCfs"], i.get("usgs"))
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
        if vs is not None and abs(vs) < 0.5:
            take.append("The lake is close to its 216.0 ft guide curve, and there are no NWS alerts at the dam.")
        elif vs is not None:
            take.append("The lake is %.1f ft %s its 216.0 ft guide curve, and there are no NWS alerts at the dam."
                        % (abs(vs), "below" if vs < 0 else "above"))
        else:
            take.append("No NWS alerts at the dam.")
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
        if block.get("stageFt"):
            _fresh_add(fresh, (block.get("label") or "Stage") + " (stage)", block["stageFt"], block.get("usgs"))
        if block.get("flowCfs"):
            _fresh_add(fresh, (block.get("label") or "Flow") + " (flow)", block["flowCfs"], block.get("usgs"))
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
        take.append("No NWS alerts at Clayton, and the gauges are not at action stage.")
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
    rel = d.get("Release plus runoff") or ""
    m = re.search(r"([\d.]+)\s*cfs", rel)
    if m:
        cells.append({"key": "Release + runoff", "kind": "observed", "value": m.group(1).rstrip("0").rstrip(".") if "." in m.group(1) else m.group(1),
                      "unit": "cfs", "sub": "Haw at Moncure, not official outflow", "tone": "lake"})
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
    m = re.search(r"([\d.]+)\s*ft stage", clay)
    if m:
        cells.append({"key": "Clayton stage", "kind": "observed", "value": m.group(1), "unit": "ft", "sub": "USGS 02087500", "tone": "lake"})
    m = re.search(r"([\d.]+)\s*cfs", clay)
    if m:
        val = m.group(1).rstrip("0").rstrip(".") if "." in m.group(1) else m.group(1)
        cells.append({"key": "Clayton flow", "kind": "observed", "value": val, "unit": "cfs", "sub": "regulated", "tone": "lake"})
    falls = d.get("Neuse River below Falls Dam") or ""
    m = re.search(r"([\d.]+)\s*cfs", falls)
    if m:
        val = m.group(1).rstrip("0").rstrip(".") if "." in m.group(1) else m.group(1)
        cells.append({"key": "Below Falls Dam", "kind": "observed", "value": val, "unit": "cfs", "sub": "regulated release", "tone": "lake"})
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
        raise RuntimeError((d or {}).get("error") or "freshwater unavailable")
    cfg = freshwater.regions().get(rid) or {}
    if rid == "jordan-lake":
        items, fresh, take, missing, unavailable = _compose_jordan(d, cfg, now)
        glance = _glance_jordan(items)
        sources = "USGS, USACE Wilmington District, NWS"
    else:
        items, fresh, take, missing, unavailable = _compose_neuse(d, cfg, now)
        glance = _glance_neuse(items)
        sources = "USGS, NWS"
    body = {"region": d.get("region") or {"id": rid, "name": cfg.get("name"), "area": cfg.get("area"),
                                          "anchor": cfg.get("anchor")},
            "waterType": "freshwater", "items": items, "freshness": fresh, "take": take,
            "missing": missing, "sources": sources}
    return _finish(rid, now, body, items, missing, unavailable, glance=glance)


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
            return 503, {"ok": False, "error": "The preview brief could not be built right now (%s)." % (str(e) or type(e).__name__)}
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
    if v.get("errors"):
        check = "Data checks: would NOT pass (%s)." % "; ".join(v["errors"])
    else:
        bits = []
        if v.get("status") == "partial":
            bits.append("some readings missing at issue time")
        if b.get("unavailable"):
            bits.append("some readings have no local sensor, listed below")
        check = "Data checks: would pass (%s)." % ("; ".join(bits) or "all core readings present")
    banner = ('<section class="mb-pv" style="margin:0 0 14px;padding:10px 12px;border:2px dashed #8c2f23;border-radius:10px">'
              '<p style="margin:0;font-weight:700;letter-spacing:.08em;text-transform:uppercase;font-size:.72rem;color:#8c2f23">'
              'Private preview · not published</p><p style="margin:4px 0 0;font-size:.88rem">Built on request from live readings for '
              'this browser only. Not on the schedule, not archived, and not linked from the site. %s</p></section>'
              % esc(check))
    out = out.replace('<main class="mb" id="brief-body">', '<main class="mb" id="brief-body">\n  ' + banner, 1)
    out = out.replace('<p class="mb-why"> · ', '<p class="mb-why">Private preview, built on request · ', 1)
    out = out.replace("<title>Morning Brief", "<title>Preview · Morning Brief", 1)
    out = out.replace("https://thecoastalbrief.com/brief?region=%s" % esc(rid), "https://thecoastalbrief.com/preview/brief/%s" % esc(rid))
    if b.get("unavailable"):
        lis = "".join('<li><b>%s:</b> unavailable. %s</li>' % (esc(k), esc(w)) for k, w in b["unavailable"])
        sec = ('<section class="mb-miss mb-unavail" aria-label="Unavailable in this area"><p><b>Unavailable in this area</b> '
               '(no honest local sensor, so nothing is shown in its place):</p><ul>%s</ul></section>' % lis)
        out = out.replace('  <script>\n  (function(){\n    var d=document.getElementById("mb-details");',
                          sec + '\n  <script>\n  (function(){\n    var d=document.getElementById("mb-details");', 1)
    return out
