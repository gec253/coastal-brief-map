"""Signature Helm homepage: cookie-gated functional private preview (Ed t529u, Nov 27 2026).

Served only at /preview/helm (PREVIEW_KEY cookie; 404 without it; noindex; no-store). Public "/" and
every other route are untouched. Readings come from the same assemble() calls as the public homepage
(conditions.assemble / freshwater.assemble through sprint_home.salt_model / fresh_model), so every value
keeps its source, station id, observation time and OBSERVED / PREDICTED / FORECAST label. Missing data
is shown as unavailable, never as a number and never as "safe".

Freshwater wind is the NOAA NCEP GFS 0.25 deg 10 m model wind (windgrid.latest_grid, the same snapshot as
/api/home-wind), sampled at the region anchor and labelled FORECAST with its run and valid times (Ed t529u).
Lake gauges use official USACE Wilmington District pool elevations (see GAUGES). The Wind and Radar
gateway maps are illustrations, labelled "Illustration · not live data", with no observation badges or times.
"""
from __future__ import annotations

import html
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

import brief_astro
import homepage_boot
import sprint_home

ROOT = Path(__file__).resolve().parent
DIR = ROOT / "preview" / "helm"
ROUTE = "/preview/helm"
ET = homepage_boot.ET
FRESH_IDS = ("falls-lake", "jordan-lake", "neuse-river")

# Official pool elevations, feet NGVD29 (USACE "ft-msl"; matches USGS parameter 62614 within 0.06 ft on
# 22 Oct 2026). Sources: USACE Wilmington District FALLPERT.TXT and BEJPERT.TXT (Reservoir Elevations),
# guide curve from epec.saw.usace.army.mil (Falls 251.5, Jordan 216.0, every day of the year).
GAUGES = {
    "falls-lake": {"lo": 236.5, "lo_label": "Bottom of conservation pool 236.5",
                   "guide": 251.5, "hi": 264.8, "hi_label": "Top of flood-control pool 264.8",
                   "src": "USACE Wilmington District · Falls Lake pertinent data"},
    "jordan-lake": {"lo": 202.0, "lo_label": "Bottom of conservation pool 202.0",
                    "guide": 216.0, "hi": 240.0, "hi_label": "Top of flood-control pool 240.0",
                    "src": "USACE Wilmington District · B. Everett Jordan pertinent data"},
}

_esc = sprint_home._esc
_num = homepage_boot._is_num


def _e(s) -> str:
    return _esc(s)


def _a(s) -> str:
    return _esc(s, True)


def _asset(name: str) -> str:
    return (DIR / name).read_text(encoding="utf-8").strip()


# ---------------------------------------------------------------- data

def _salt(rid):
    import conditions
    status, payload = conditions.assemble(rid)
    if status == 200 and (payload or {}).get("ok"):
        return payload
    return None


def _fresh(rid):
    import freshwater
    p = freshwater.peek(rid)
    if p and p.get("ok"):
        return p
    status, p = freshwater.assemble(rid)
    return p if status == 200 and (p or {}).get("ok") else None


def _grid():
    import windgrid
    try:
        return windgrid.latest_grid(ahead=0)
    except Exception:
        return {"ok": False}


def valid_region(rid: str | None) -> str | None:
    rid = (rid or "").strip()[:40]
    if not rid:
        return None
    if rid in sprint_home.public_salt_ids():
        return rid
    try:
        import freshwater
        if rid in FRESH_IDS and freshwater.flag_on():
            return rid
    except Exception:
        pass
    return None


# ---------------------------------------------------------------- small pieces

def kind_badge(t: dict) -> str:
    st = t.get("state")
    if st == "off":
        return '<i class="k off">UNAVAILABLE</i>'
    k = (t.get("kind") or "").upper()
    cls = {"OBSERVED": "obs", "PREDICTED": "pred", "FORECAST": "fcst"}.get(k, "")
    out = ('<i class="k %s">%s</i>' % (cls, k)) if k else ""
    if st == "stale":
        out += '<i class="k stale">STALE</i>'
    return out


def _when(t: dict) -> str:
    w = t.get("when") or ""
    return w if w.startswith("·") or not w else "· " + w


def src_line(t: dict) -> str:
    bits = " ".join(x for x in (_e(t.get("src") or ""), _e(_when(t))) if x)
    return '<p class="src">%s</p>' % bits if bits else ""


def off_line(t: dict) -> str:
    sub = ('<p class="sub">%s</p>' % _e(t["sub"])) if t.get("sub") else ""
    return '<p class="offv" role="note">%s</p>%s' % (_e(t.get("off") or sprint_home.NOT_REPORTING), sub)


def moon_svg(frac: float, waxing: bool) -> str:
    c, r = 10.0, 8.5
    k = abs(1 - 2 * frac) * r
    if waxing:   # dark on the left
        first, term = 0, (0 if frac < 0.5 else 1)
    else:
        first, term = 1, (1 if frac < 0.5 else 0)
    d = "M10 1.5 A8.5 8.5 0 0 %d 10 18.5 A%.2f 8.5 0 0 %d 10 1.5Z" % (first, k, term)
    return ('<svg class="moon" viewBox="0 0 20 20" aria-hidden="true"><circle cx="10" cy="10" r="8.5" class="m-lit"/>'
            '<path d="%s" class="m-dark"/></svg>') % d


def moon(now: datetime, place: str) -> tuple[str, dict | None]:
    m = brief_astro.moon_illumination(now)
    if not m:
        return ('<div class="led"><span class="lk">MOON PHASE <i class="k off">UNAVAILABLE</i></span><b>—</b>'
                '<span class="ls">Moon phase could not be computed.</span></div>'), None
    name = brief_astro.phase_name(m["fraction"], m["waxing"])
    pct = int(round(m["fraction"] * 100))
    info = {"name": name, "pct": pct, "frac": m["fraction"], "waxing": m["waxing"]}
    return ('<div class="led" id="moon"><span class="lk">MOON PHASE</span><b>%s %s · %d%%</b>'
            '<span class="ls">Computed locally (NOAA solar / Meeus lunar equations) for %s. Not a live fetch.</span></div>'
            % (moon_svg(m["fraction"], m["waxing"]), _e(name), pct, _e(place))), info


# ---------------------------------------------------------------- compass

def _ticks() -> str:
    s = []
    for i in range(72):
        a = math.radians(i * 5)
        r2 = 55 if i % 18 == 0 else (63 if i % 2 else 59)
        s.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f"/>' % (
            80 + 68 * math.sin(a), 80 - 68 * math.cos(a), 80 + r2 * math.sin(a), 80 - r2 * math.cos(a)))
    return "".join(s)


TICKS = _ticks()


def dial_html(t: dict, label: str = "Wind") -> str:
    """Brass compass. Pointer only for a real direction; no number when the reading is missing."""
    deg = t.get("dial")
    ptr = ""
    if _num(deg) and t.get("state") != "off":
        ptr = ('<g transform="rotate(%.1f 80 80)"><path d="M80 27 L87 12 L73 12 Z" class="pointer"/>'
               '<line x1="80" y1="27" x2="80" y2="42" class="shaft"/></g>') % float(deg)
    if t.get("state") == "off":
        read = '<div class="dial-read off"><span class="big">—</span><span class="gust">%s</span></div>' % _e(t.get("off") or sprint_home.NOT_REPORTING)
    elif not t.get("num"):
        read = '<div class="dial-read"><span class="gust">%s</span></div>' % _e(t.get("sub") or "")
    else:
        gust = ('GUST <b>%s</b> kt' % _e(t["gust"])) if t.get("gust") else _e(t.get("sub") or "")
        read = ('<div class="dial-read"><span class="dir">%s</span><span class="big">%s<small>kt</small></span>'
                '<span class="gust">%s</span></div>') % (
            ("from " + _e(t["dir"])) if t.get("dir") else "&nbsp;", _e(t["num"]), gust)
    note = ('<p class="sub">%s</p>' % _e(t["note"])) if t.get("note") else ""
    return ('<div class="dial-wrap" role="group" aria-label="%s, %s">'
            '<div class="lbl"><span>%s</span>%s</div>'
            '<div class="dial-box"><svg class="dial" viewBox="0 0 160 160" aria-hidden="true"><defs><radialGradient id="face" cx="50%%" cy="38%%" r="62%%">'
            '<stop offset="0" class="f1"/><stop offset="1" class="f2"/></radialGradient></defs>'
            '<circle cx="80" cy="80" r="76" class="bezel"/><circle cx="80" cy="80" r="68" fill="url(#face)"/><g class="ticks">%s</g>'
            '<text x="80" y="20" class="card">N</text><text x="144" y="84" class="card">E</text>'
            '<text x="80" y="148" class="card">S</text><text x="16" y="84" class="card">W</text>%s</svg>%s</div>%s%s</div>') % (
        _a(label), _a((t.get("kind") or "unavailable").lower() if t.get("state") != "off" else "unavailable"),
        _e(label.upper()), kind_badge(t), TICKS, ptr, read, src_line(t), note)


def gfs_wind_tile(g: dict, lat: float, lon: float) -> dict:
    """GFS 10 m wind at the anchor, labelled FORECAST with model, run and valid time (ET)."""
    import windgrid
    base = sprint_home._tile(id="wind", name="Wind", kind="Forecast", state="off",
                             off="Model wind is unavailable right now.", src="NOAA NCEP GFS 0.25°")
    if not (g or {}).get("ok"):
        return base
    try:
        uv = windgrid.sample(g, lat, lon)
    except Exception:
        uv = None
    if not uv:
        return base
    u, v = uv
    kt = windgrid.speed_kt(u, v)
    deg = windgrid.from_deg(u, v)
    run, valid = homepage_boot._to_dt(g.get("run")), homepage_boot._to_dt(g.get("valid"))
    fh = g.get("forecastHour")
    def fmt(d):
        if not d:
            return "time unknown"
        d = d.astimezone(ET)
        return d.strftime("%a ") + homepage_boot.et_time(d.isoformat())
    t = sprint_home._tile(id="wind", name="Wind", kind="Forecast", state="ok", dir=windgrid.compass(deg),
                          num=str(int(round(kt))), unit="kt", dial=deg,
                          sub="≈ %d mph · model" % int(round(kt * 1.15078)),
                          src="NOAA NCEP GFS 0.25° 10 m wind at %s · valid %s (run %s%s)" % (
                              "%.2f°N %.2f°W" % (lat, abs(lon)), fmt(valid), fmt(run),
                              (", F%03d" % fh) if isinstance(fh, int) else ""))
    t["note"] = "No observed wind station at this water; this is the GFS model forecast."
    return t


# ---------------------------------------------------------------- cells

def seas_cell(seas: dict, swell: dict | None) -> str:
    if seas.get("state") == "off":
        body = off_line(seas)
    else:
        body = ('<p class="num">%s<small>ft</small></p><p class="note">Combined wave height</p>%s') % (
            _e(seas["num"]), ('<p class="sub">%s</p>' % _e(seas["sub"])) if seas.get("sub") else "")
    sw = ""
    if swell is not None:
        if swell.get("state") == "off":
            sw = '<p class="swell" id="swell-in-seas"><span>SWELL</span> %s</p>' % _e(swell.get("off") or sprint_home.SWELL_OFF)
        else:
            sw = ('<p class="swell" id="swell-in-seas"><span>SWELL</span> %s ft%s%s <em>Split from the wave spectrum%s</em></p>') % (
                _e(swell["num"]), (" · " + _e(swell["sub"])) if swell.get("sub") else "",
                ' <i class="k stale">STALE</i>' if swell.get("state") == "stale" else "",
                (" " + _e(_when(swell))) if swell.get("when") else "")
    return ('<div class="cell seas" role="group" aria-label="Seas"><div class="lbl"><span>SEAS</span>%s</div>%s%s%s</div>') % (
        kind_badge(seas), body, sw, src_line(seas))


def water_cell(t: dict) -> str:
    if t.get("state") == "off":
        body = off_line(t)
    else:
        off = t.get("off_read")
        extra = (' <span class="offr">offshore %s %s</span>' % (_e(off["num"]), _e(off["unit"]))) if off else ""
        body = '<p class="num sm">%s<small>%s</small>%s</p>' % (_e(t["num"]), _e(t["unit"]), extra)
        if t.get("label") and (t.get("offshore") or not off):
            body += '<p class="note">%s</p>' % _e(t["label"])
        elif off:
            body += '<p class="note">Inshore</p>'
        if t.get("sub") and not off:
            body += '<p class="sub">%s</p>' % _e(t["sub"])
        if off:
            body += '<p class="src">%s</p>' % _e("Offshore: %s%s" % (off["src"], (" · " + off["when"]) if off.get("when") else ""))
    return '<div class="cell water" role="group" aria-label="Water temperature"><div class="lbl"><span>WATER</span>%s</div>%s%s</div>' % (
        kind_badge(t), body, src_line(t))


def tide_strip(t: dict) -> str:
    if t.get("state") == "off":
        return ('<div class="nextlow" role="group" aria-label="Tide, predicted"><div class="lbl"><span>TIDE</span>%s</div>'
                '<p class="offv">%s</p></div>') % (kind_badge(t), _e(t.get("off")))
    extra = " · ".join(x for x in (t.get("sub"), t.get("then")) if x)
    flood = ('<p class="flood" role="note">%s</p>' % _e(t["flood"])) if t.get("flood") else ""
    return ('<div class="nextlow" role="group" aria-label="%s, predicted"><div class="lbl"><span>%s</span>%s</div>'
            '<p class="tnum">%s <small>%s</small> <span>%s</span></p>%s</div>') % (
        _a(t["name"]), _e(t["name"].upper()), kind_badge(t), _e(t["num"]), _e(t["unit"]), _e(extra), flood)


def ledger_row(t: dict, label: str | None = None) -> str:
    label = (label or t.get("name") or "").upper()
    if t.get("state") == "off":
        val, ls = "—", _e(t.get("off") or sprint_home.NOT_REPORTING) + ((" · " + _e(t["sub"])) if t.get("sub") else "")
    else:
        if t.get("num"):
            val = (_e(t.get("dir") + " ") if t.get("dir") else "") + _e(t["num"]) + " " + _e(t.get("unit") or "")
            if t.get("gust"):
                val += " G" + _e(t["gust"])
        else:
            val = "—"
        ls = " · ".join(x for x in (_e(t.get("sub") or ""), _e(t.get("note") or ""), _e(t.get("obs") or "")) if x)
    src = " ".join(x for x in (_e(t.get("src") or ""), _e(_when(t))) if x)
    fc = (' · <i class="k fcst">FORECAST</i> %s' % _e(t["fc"])) if t.get("fc") else ""
    return '<div class="led"><span class="lk">%s %s</span><b>%s</b><span class="ls">%s%s%s</span></div>' % (
        _e(label), kind_badge(t), val.strip(), ls + (" · " if ls and src else ""), src, fc)


def gauge_svg(value, g: dict) -> str:
    lo, hi = g["lo"], g["hi"]
    span = hi - lo
    gx = (g["guide"] - lo) / span * 150
    fill = ""
    try:   # tiles carry display strings ("245.76"); a missing or non-numeric reading draws no marker
        v = float(str(value).replace(",", "")) if value is not None else None
    except ValueError:
        v = None
    if v is not None and math.isfinite(v):
        x = max(0.0, min(150.0, (v - lo) / span * 150))
        fill = '<rect x="0" y="12" width="%.1f" height="8" rx="4" class="g-fill"/><circle cx="%.1f" cy="16" r="5" class="g-now"/>' % (x, x)
    return ('<svg class="gauge" viewBox="0 -5 150 41" role="img" aria-label="Lake level gauge, %.1f to %.1f ft, guide curve %.1f ft">'
            '<rect x="0" y="12" width="150" height="8" rx="4" class="g-track"/>%s'
            '<line x1="%.1f" y1="5" x2="%.1f" y2="27" class="g-guide"/><text x="%.1f" y="4.5" class="g-t" text-anchor="middle">GUIDE %.1f</text>'
            '<text x="0" y="35" class="g-t">%.1f</text><text x="150" y="35" class="g-t" text-anchor="end">%.1f ft</text></svg>') % (
        lo, hi, g["guide"], fill, gx, gx, max(18, min(132, gx)), g["guide"], lo, hi)


def lake_cell(t: dict, rid: str) -> str:
    g = GAUGES.get(rid)
    if t.get("state") == "off":
        body = off_line(t)
        if g:
            body += gauge_svg(None, g)
    else:
        body = '<p class="num">%s<small>ft</small></p><p class="note">%s</p>' % (_e(t["num"]), _e(t.get("note") or ""))
        if g:
            body += gauge_svg(t["num"], g)
        body += '<p class="sub">%s</p>' % _e(" · ".join(x for x in (t.get("sub"), t.get("obs")) if x))
    scale = ('<p class="gs">Scale: %s → %s ft (%s)</p>' % (_e(g["lo_label"]), _e(g["hi_label"]), _e(g["src"]))) if g else ""
    return '<div class="cell lake" role="group" aria-label="Lake level"><div class="lbl"><span>LAKE LEVEL</span>%s</div>%s%s%s</div>' % (
        kind_badge(t), body, src_line(t), scale)


def river_cell(spec: dict) -> str:
    """River stage vs NWS flood stages, plus flow. Only from a reporting USGS gauge."""
    f, s = spec.get("flowCfs") or {}, spec.get("stageFt") or {}
    fs = spec.get("floodStages") or ((spec.get("nwps") or {}).get("floodStages")) or {}
    label = spec.get("label") or "River gauge"
    src = "%s · USGS %s" % (label, spec.get("usgs") or "")
    stale = bool(s.get("stale") or f.get("stale"))
    t = sprint_home._tile(state="stale" if stale else "ok", kind="Observed")
    if not _num(s.get("value")) and not _num(f.get("value")):
        t["state"] = "off"
        return ('<div class="cell river" role="group" aria-label="River stage"><div class="lbl"><span>RIVER STAGE</span>%s</div>'
                '<p class="offv">%s</p><p class="src">%s</p></div>') % (kind_badge(t), _e(sprint_home.STAGE_OFF), _e(src))
    body = ""
    if _num(s.get("value")):
        body += '<p class="num">%s<small>ft</small></p><p class="note">Gage height, not depth</p>' % _e(homepage_boot._fmt(s["value"], 2))
        if _num(fs.get("minor")):
            top = float(fs.get("major") or fs["minor"] * 1.5)
            x = max(0.0, min(150.0, float(s["value"]) / top * 150))
            marks = "".join('<line x1="%.1f" y1="6" x2="%.1f" y2="26" class="g-%s"/>' % (float(fs[k]) / top * 150, float(fs[k]) / top * 150, k)
                            for k in ("action", "minor") if _num(fs.get(k)))
            body += ('<svg class="gauge" viewBox="0 0 150 36" role="img" aria-label="Stage %s ft; action stage %s ft, minor flood stage %s ft (NWS)">'
                     '<rect x="0" y="12" width="150" height="8" rx="4" class="g-track"/><rect x="0" y="12" width="%.1f" height="8" rx="4" class="g-fill"/>'
                     '%s<circle cx="%.1f" cy="16" r="5" class="g-now"/><text x="0" y="35" class="g-t">0</text>'
                     '<text x="150" y="35" class="g-t" text-anchor="end">%s ft major</text></svg>'
                     '<p class="sub">NWS flood stages: action %s ft · minor %s ft</p>') % (
                _a(s["value"]), _a(fs.get("action")), _a(fs.get("minor")), x, marks, x, _e(fs.get("major") or ""),
                _e(fs.get("action")), _e(fs.get("minor")))
    if _num(f.get("value")):
        band = (spec.get("band") or {}).get("label")
        body += '<p class="sub"><b>%s cfs</b>%s</p>' % ("{:,}".format(int(round(f["value"]))), (" · " + _e(band)) if band and not stale else "")
    when = homepage_boot.et_time((s if _num(s.get("value")) else f).get("time"))
    return ('<div class="cell river" role="group" aria-label="River stage"><div class="lbl"><span>RIVER STAGE</span>%s</div>%s'
            '<p class="src">%s · %s</p></div>') % (kind_badge(t), body, _e(src), _e(when))


# ---------------------------------------------------------------- ribbon

def _x(ts: float, t0: float, t1: float) -> float:
    return (ts - t0) / (t1 - t0) * 330.0


def ribbon(now: datetime, lat: float, lon: float, place: str, tide: dict | None, water: str) -> str:
    """Tide & Light (salt) or Sun & Moon (fresh) from now-4 h to now+20 h. Sun from brief_astro."""
    t0 = (now - timedelta(hours=4)).timestamp() * 1000
    t1 = (now + timedelta(hours=20)).timestamp() * 1000
    nowx = _x(now.timestamp() * 1000, t0, t1)
    d0 = now.astimezone(ET).date()
    suns = [brief_astro.sun_times(lat, lon, d0 + timedelta(days=k)) for k in (-1, 0, 1)]
    stops, events = [], []
    for s in suns:
        if not s:
            continue
        r, st = s["sunrise"].timestamp() * 1000, s["sunset"].timestamp() * 1000
        for ts, kind in ((r, "rise"), (st, "set")):
            if t0 <= ts <= t1:
                events.append((ts, kind, s["sunrise" if kind == "rise" else "sunset"]))
    sky = ['<stop offset="0" class="s-n"/>']
    # day/night by sampling: simple, robust gradient
    def is_day(ts):
        return any(s and s["sunrise"].timestamp() * 1000 <= ts <= s["sunset"].timestamp() * 1000 for s in suns)
    prev = None
    for i in range(0, 49):
        ts = t0 + (t1 - t0) * i / 48
        cls = "s-d" if is_day(ts) else "s-n"
        if cls != prev:
            sky.append('<stop offset="%.3f" class="%s"/>' % (i / 48, cls))
            prev = cls
    sky.append('<stop offset="1" class="%s"/>' % prev)
    svg_tide, legend = "", ""
    today_sun = suns[1]
    if water == "salt":
        curve = [(p[0], p[1]) for p in ((tide or {}).get("curve") or []) if _num(p[0]) and _num(p[1]) and t0 <= p[0] <= t1]
        if tide and tide.get("state") != "off" and len(curve) > 10:
            vs = [v for _, v in curve]
            lo, hi = min(vs), max(vs)
            rng = (hi - lo) or 1.0
            y = lambda v: 72 - (v - lo) / rng * 58
            pts = " L".join("%.1f %.1f" % (_x(ts, t0, t1), y(v)) for ts, v in curve)
            svg_tide = ('<path d="M%s L%.1f 80 L%.1f 80 Z" class="tfill"/><path d="M%s" class="tline" pathLength="700"/>') % (
                pts, _x(curve[-1][0], t0, t1), _x(curve[0][0], t0, t1), pts)
            for ev in (tide.get("events") or []):
                if _num(ev.get("t")) and t0 <= ev["t"] <= t1 and _num(ev.get("v")):
                    ex = _x(ev["t"], t0, t1)
                    svg_tide += '<text x="%.1f" y="%.1f" class="hl">%s</text>' % (
                        ex, (y(ev["v"]) - 4) if ev.get("type") == "H" else min(79, y(ev["v"]) + 10), "H" if ev.get("type") == "H" else "L")
            if tide.get("obs_pt") and t0 <= tide["obs_pt"][0] <= t1:
                svg_tide += '<circle cx="%.1f" cy="%.1f" r="3.2" class="odot"/>' % (_x(tide["obs_pt"][0], t0, t1), y(tide["obs_pt"][1]))
            st_src = (tide.get("src") or "").replace("Predictions: ", "")
            legend = '<span><i class="sw"></i>PREDICTED tide · %s</span>' % _e(st_src)
            if tide.get("obs"):
                legend += '<span><i class="dot"></i>OBSERVED · %s %s</span>' % (_e(tide["obs"]), _e(tide.get("when") or ""))
        else:
            legend = '<span>%s</span>' % _e(sprint_home.TIDE_OFF)
    else:
        if today_sun:
            rx, sx = _x(today_sun["sunrise"].timestamp() * 1000, t0, t1), _x(today_sun["sunset"].timestamp() * 1000, t0, t1)
            svg_tide = '<path d="M%.1f 74 Q%.1f -18 %.1f 74" class="sunarc"/>' % (rx, (rx + sx) / 2, sx)
            if rx <= nowx <= sx:
                f = (nowx - rx) / ((sx - rx) or 1)
                cy = (1 - f) ** 2 * 74 + 2 * (1 - f) * f * -18 + f ** 2 * 74
                svg_tide += '<circle cx="%.1f" cy="%.1f" r="4.5" class="sun"/>' % (nowx, cy)
        what = "lake" if water == "lake" else "river"
        legend = ('<span><i class="sw sunk"></i>Sun path, sunrise to sunset</span>'
                  '<span class="notide">No tide on a %s: the %s instrument above is the level to watch.</span>') % (
            what, "lake level" if what == "lake" else "river stage")
    ticks = [(nowx, "NOW", "nowt")]
    for ts, kind, dt in events:
        ticks.append((_x(ts, t0, t1), ("↑ " if kind == "rise" else "↓ ") + homepage_boot.et_time(dt.isoformat()).replace(" ET", ""), ""))
    ticks.append((0, homepage_boot.et_time((now - timedelta(hours=4)).isoformat()).replace(" ET", ""), "edge"))
    ticks.append((330, homepage_boot.et_time((now + timedelta(hours=20)).isoformat()).replace(" ET", ""), "edge r"))
    placed, spans = [], []
    for x, txt, cls in ticks:
        if any(abs(x - p) < 40 for p in placed):
            continue
        placed.append(x)
        pct = x / 330 * 100
        style = "right:0" if "r" in cls.split() else ("left:%.1f%%;transform:translateX(-50%%)" % pct if cls != "edge" else "left:0")
        spans.append('<span class="%s" style="%s">%s</span>' % (cls, style, _e(txt)))
    head = "TIDE &amp; LIGHT" if water == "salt" else "SUN &amp; MOON"
    sun_txt = ("Sunrise %s · Sunset %s" % (homepage_boot.et_time(today_sun["sunrise"].isoformat()),
                                           homepage_boot.et_time(today_sun["sunset"].isoformat()))) if today_sun else "Sun times unavailable"
    return ('<figure class="ribbon" id="ribbon" aria-label="%s, next 24 hours, at %s">'
            '<figcaption><span class="rb-h">%s · NEXT 24 H</span><span class="rb-sun">%s</span></figcaption>'
            '<svg viewBox="0 0 330 80" preserveAspectRatio="none" aria-hidden="true"><defs><linearGradient id="sky" x1="0" x2="1">%s</linearGradient></defs>'
            '<rect x="0" y="0" width="330" height="80" fill="url(#sky)"/>%s'
            '<line x1="%.1f" y1="0" x2="%.1f" y2="80" class="now"/></svg>'
            '<div class="rb-ticks" aria-hidden="true">%s</div><p class="rb-leg">%s<span>Sun times computed locally for %s (NOAA solar equations).</span></p></figure>') % (
        "Tide and light" if water == "salt" else "Sun and moon", _a(place), head, _e(sun_txt), "".join(sky), svg_tide,
        nowx, nowx, "".join(spans), legend, _e(place))


# ---------------------------------------------------------------- hazards

def _alert_row(sv: str, name: str, same: list, compact: bool) -> str:
    """One row per NWS event name. Every event stays visible; several zones of the same event share
    the row, with each zone's own status, end time and area one tap away (never dropped)."""
    def bits(it):
        tag = (' <span class="ie">%s</span>' % _e(it["tag"])) if it.get("tag") else ""
        meta = (' <span class="t">%s</span>' % _e(it["meta"])) if it.get("meta") else ""
        area = (' <span class="area">%s</span>' % _e(it["area"])) if it.get("area") else ""
        return tag, meta, area
    first = same[0]
    tag, meta, area = bits(first)
    if len(same) == 1:
        return '<p class="ev ev-%s"><b>%s</b>%s%s%s</p>' % (sv, _e(name), tag, meta, area)
    zones = "".join('<li>%s%s%s</li>' % bits(it) for it in same)
    # The summary is the warning row itself: name and status always visible; zones one tap away.
    return ('<details class="ev ev-%s evg"><summary><b>%s</b>%s <span class="t">%d areas · end times</span></summary><ul>%s</ul></details>') % (
        sv, _e(name), tag, len(same), zones)


def hazards_html(a: dict, raw: dict | None) -> str:
    """Warnings first, then watches, advisories, statements. Unknown alert state is never shown as clear."""
    st = a.get("state")
    if st == "clear":
        return ('<div class="haz clear" id="hazards" role="status"><div class="haz-rows"><p><b>No NWS alerts right now</b></p></div>'
                '<a class="haz-link" href="%s" rel="noopener">NWS details</a></div>') % _a(homepage_boot.NWS_DETAILS)
    if st != "active":
        it = (a.get("items") or [{}])[0]
        return ('<div class="haz unknown" id="hazards" role="alert"><div class="haz-rows"><p><b>%s</b></p><p>%s</p></div>'
                '<a class="haz-link" href="%s" rel="noopener">NWS details</a></div>') % (
            _e(it.get("event") or sprint_home.ALERTS_OFF[0]), _e(it.get("meta") or sprint_home.ALERTS_OFF[1]), _a(homepage_boot.NWS_DETAILS))
    order = {"warn": 0, "watch": 1, "adv": 2, "stmt": 3}
    items = sorted(a["items"], key=lambda it: order.get(sprint_home.severity(it.get("event")), 9))
    top = sprint_home.severity(items[0].get("event")) if items else "stmt"
    rows, low = [], []
    for sv in ("warn", "watch", "adv", "stmt"):
        grp = [it for it in items if sprint_home.severity(it.get("event")) == sv]
        if not grp:
            continue
        # Warnings and watches are never collapsed. Advisories and statements collapse only when a
        # higher tier is showing; the top tier on the page is always fully visible.
        visible = sv in ("warn", "watch") or sv == top
        out = rows if visible else low
        out.append('<p class="sev sev-%s">%s</p>' % (sv, (sprint_home.SEV_LABEL[sv] + ("s" if len(grp) > 1 else "")).upper()))
        names = []
        for it in grp:
            if it.get("event") not in names:
                names.append(it.get("event"))
        for name in names:
            same = [it for it in grp if it.get("event") == name]
            out.append(_alert_row(sv, name, same, compact=visible))
    if low:
        n = sum(1 for it in items if sprint_home.severity(it.get("event")) in ("adv", "stmt"))
        names = []
        for it in items:
            if sprint_home.severity(it.get("event")) in ("adv", "stmt") and it.get("event") not in names:
                names.append(it.get("event"))
        rows.append('<details class="haz-more"><summary><span class="cnt">+%d</span> %s</summary>%s</details>' % (
            n, _e(", ".join(names)), "".join(low)))
    kind = sprint_home.flag_for(raw)
    flag = ""
    if kind:
        # Official display only (exact NWS event names); brighter red so it reads on the warning band.
        flag = '<span class="flag">%s</span>' % sprint_home.flag_svg(kind).replace("#B3261E", "#FF6B5E")
    return ('<div class="haz haz-%s" id="hazards" role="alert">%s<div class="haz-rows">%s</div>'
            '<a class="haz-link" href="%s" rel="noopener">NWS details</a></div>') % (
        top, flag, "".join(rows), _a(homepage_boot.NWS_DETAILS))


# ---------------------------------------------------------------- gateways

LABELS = [("Albemarle Sound", 300, 74), ("Pamlico Sound", 290, 160), ("Cape Hatteras", 322, 186), ("Cape Lookout", 236, 258),
          ("Morehead City", 196, 226), ("Wilmington", 108, 288), ("Cape Fear", 116, 328), ("Raleigh", 50, 110), ("Atlantic Ocean", 300, 300)]
RAMP = ["#9be1ff", "#4fc3f7", "#1e88e5", "#2e7d32", "#66bb6a", "#fdd835", "#fb8c00", "#e53935", "#ad1457"]
INH = ["&lt;0.01", "0.04", "0.15", "0.6", "2.5+"]
ILL = '<span class="ill">Illustration · not live data</span>'


def gates_html() -> str:
    coast, streaks = _asset("coast.path"), _asset("streaks.path")
    lab = "".join('<text x="%d" y="%d" class="%s">%s</text>' % (x, y, "pl" if n in ("Raleigh", "Wilmington", "Morehead City") else "rl", n)
                  for n, x, y in LABELS)
    rain = "".join('<ellipse cx="%d" cy="%d" rx="%d" ry="%d" fill="%s" opacity=".85" transform="rotate(-35 %d %d)"/>' % (x, y, rx, ry, c, x, y)
                   for x, y, rx, ry, c in [(120, 150, 70, 22, "#9be1ff"), (128, 150, 48, 14, "#4fc3f7"), (134, 148, 26, 8, "#2e7d32"),
                                           (138, 147, 10, 4, "#fdd835"), (210, 120, 46, 14, "#9be1ff"), (214, 118, 24, 7, "#1e88e5"),
                                           (70, 212, 34, 12, "#4fc3f7")])
    bar = ('<div class="vbar"><img src="/branding/favicon.svg" alt="" width="26" height="26" loading="lazy" decoding="async">'
           '<div><small>THE COASTAL BRIEF</small><b>%s</b></div><span class="chip">%s</span></div>')
    # Coastline and streak paths are written once and reused with <use> (smaller HTML).
    defs = ('<svg width="0" height="0" style="position:absolute" aria-hidden="true" focusable="false"><defs>'
            '<path id="hm-coast" d="%s"/><path id="hm-streaks" d="%s"/></defs></svg>') % (coast, streaks)
    sea = '<rect x="0" y="0" width="390" height="400" class="sea"/><use href="#hm-coast" class="land"/>'
    return """<section class="gates" id="gates" aria-labelledby="gates-h">
<h2 id="gates-h" class="vh">Wind and Radar Viewers</h2>%s
<a class="gate wind" href="/wind">
  %s
  <p class="vfields">NOAA NCEP GFS model wind · animated over every sound and inlet · forecast, not a measurement</p>
  <div class="vmap"><svg viewBox="0 40 390 260" preserveAspectRatio="xMidYMid slice" aria-hidden="true">%s
    <use href="#hm-streaks" class="streak"/><use href="#hm-streaks" class="streak hi"/>%s</svg>
    <div class="wleg" aria-hidden="true"><span class="wramp"></span><span class="wt"><i>0</i><i>10</i><i>20</i><i>30</i><i>35+ kt</i></span></div>
    %s</div>
  <div class="vcta"><b>Open the Wind Viewer</b><span>Chart Helm · live GFS model wind, run and valid times shown in the viewer</span><i aria-hidden="true">→</i></div>
</a>
<a class="gate radar" href="/radar">
  %s
  <p class="vfields">NOAA/NSSL MRMS precipitation rate · observed loop, forecast frames hatched and labelled in the viewer</p>
  <div class="vmap"><svg viewBox="0 40 390 260" preserveAspectRatio="xMidYMid slice" aria-hidden="true">%s
    <g class="rain">%s</g>%s</svg>
    <div class="rleg" aria-hidden="true"><span class="rk">Precip rate <b>in/h</b></span><span class="rramp" style="background:linear-gradient(90deg,%s)"></span>
      <span class="rt">%s</span><span class="rfc"><i></i>Hatched = forecast</span></div>
    %s</div>
  <div class="vcta"><b>Open the Radar Viewer</b><span>Chart Helm · frame times and data age shown in the viewer</span><i aria-hidden="true">→</i></div>
</a>
<p class="fbrow"><button type="button" class="fb-open fb-chip" data-feedback-open aria-haspopup="dialog" aria-controls="fb-dlg">Feedback</button></p>
</section>""" % (defs, bar % ("Wind", "MODEL FORECAST"), sea, lab, ILL,
                 bar % ("Radar", "RADAR"), sea, rain, lab, ",".join(RAMP), "".join("<i>%s</i>" % t for t in INH), ILL)


# ---------------------------------------------------------------- chapters

def _wb() -> dict:
    try:
        return json.loads((ROOT / "data" / "whats_biting.json").read_text(encoding="utf-8"))
    except Exception:
        return {}


SALT_REGS = ("dmf-rec-guide", "dmf-proclamations")
FRESH_REGS = ("ncwrc-inland-regs", "ncwrc-striped-bass")


OLDER_DAYS = 7


def report_age(as_of: str | None, now: datetime) -> tuple[str, int | None]:
    """("Sun, Nov 15, 2026", age in days) from an ISO date; ("date not stated", None) otherwise."""
    try:
        d = datetime.strptime(str(as_of)[:10], "%Y-%m-%d").date()
    except Exception:
        return "date not stated", None
    today = homepage_boot._to_dt(now).astimezone(ET).date() if hasattr(homepage_boot, "_to_dt") else now.date()
    return d.strftime("%a, %b ") + str(d.day) + d.strftime(", %Y"), (today - d).days


def report_rows(reg: dict | None, now: datetime) -> str:
    """Every dated report with its real source and link, its date and its age. Reports older than
    OLDER_DAYS are marked OLDER REPORT; nothing here says or implies that a report is current."""
    out = []
    for r in (reg or {}).get("reports") or []:
        if not r.get("source_name") or not str(r.get("source_url") or "").startswith("https://"):
            continue   # unattributed or unlinked reports are never shown
        when, age = report_age(r.get("as_of"), now)
        if age is None:
            ago, cls, tag = "age unknown", "old", '<i class="k old">DATE NOT STATED</i>'
        else:
            ago = "today" if age <= 0 else ("1 day old" if age == 1 else "%d days old" % age)
            old = age > OLDER_DAYS
            cls, tag = ("old", '<i class="k old">OLDER REPORT</i>') if old else ("", '<i class="k rep">DATED REPORT</i>')
        out.append('<li%s><a href="%s" rel="noopener" target="_blank"><b>%s</b></a> %s<span>Report dated %s · %s</span></li>' % (
            (' class="%s"' % cls) if cls else "", _a(r["source_url"]), _e(r["source_name"]), tag, _e(when), _e(ago)))
    return "".join(out)


def reports_html(rid: str | None, fresh: bool, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    wb = _wb()
    reg = next((r for r in wb.get("regions") or [] if r.get("id") == rid), None)
    notices = wb.get("notices") or {}
    href = "/reports/%s" % rid if reg else "/reports"
    rows = report_rows(reg, now)
    name = (reg or {}).get("short_name") or (reg or {}).get("name") or ""
    if rows:
        line = "%s · latest dated reports, each from its own source. Check the date: fishing changes day to day." % name
    elif reg:
        line = "%s · no dated bite report on file; seasonal notes and official notices only." % name
    else:
        line = "No dated report for this water yet. What's Biting? covers selected regions, each report with its source and date."
    keys = [k for k in ((reg or {}).get("notices") or []) if k in (FRESH_REGS + SALT_REGS)] or list(FRESH_REGS if fresh else SALT_REGS)
    if fresh and "ncwrc-inland-regs" not in keys:
        keys.insert(0, "ncwrc-inland-regs")
    links = []
    for k in keys:
        n = notices.get(k)
        if n and n.get("source_url"):
            links.append('<li><a href="%s" rel="noopener" target="_blank">%s</a> <span>%s · %s</span></li>' % (
                _a(n["source_url"]), _e(n.get("title")), _e(n.get("source_name") or ""), _e(n.get("as_of_label") or "")))
    agency = "NC Wildlife Resources Commission" if fresh else "NC Division of Marine Fisheries"
    return """<div class="fr">
  <a class="frow" href="%s"><span class="eyebrow">WHAT’S BITING? · FISHING REPORTS</span><b>Fishing Reports</b><span>%s</span><i aria-hidden="true">→</i></a>
  %s
  <section class="regs" id="regs" aria-labelledby="regs-h">
    <p class="eyebrow">OFFICIAL · LINKED, NOT RESTATED</p><h3 id="regs-h">Regulations</h3>
    <p class="dek">Size, bag and season rules come only from %s. We link them; we never restate limits.</p>
    <ul>%s</ul>
  </section>
  <p class="lic"><a href="https://license.gooutdoorsnorthcarolina.com/Licensing/CustomerLookup.aspx" rel="noopener" target="_blank">Buy an NC fishing or hunting license</a> · <a href="https://www.ncwildlife.gov/hunting/license-types-and-fees" rel="noopener" target="_blank">License types and fees</a> · NC Wildlife Resources Commission</p>
</div>""" % (_a(href), _e(line), ('<ul class="reps" aria-label="Dated fishing reports">%s</ul>' % rows) if rows else "", _e(agency), "".join(links))


def forecast_quote(f: dict | None, fresh: bool) -> str:
    if not f:
        return ""
    if f.get("off"):
        return '<blockquote class="fcst"><p class="fh"><i class="k fcst">FORECAST</i></p><p class="q off">%s</p></blockquote>' % _e(f["off"])
    label = "NWS forecast" if fresh else "Marine forecast"
    src = _e(f.get("src") or "") + ((" · issued " + _e(f["when"])) if f.get("when") else "")
    return ('<blockquote class="fcst"><p class="fh"><i class="k fcst">FORECAST</i> %s · %s</p><p class="q">%s</p><p class="src">%s</p></blockquote>') % (
        label, _e(f.get("name") or ""), _e(f.get("text") or ""), src)


def _rotation() -> dict:
    try:
        x = json.loads((ROOT / "static" / "featured-photos" / "photo-rotation.json").read_text(encoding="utf-8"))
        x = x if isinstance(x, list) else x.get("photos") or []
        return {p["id"]: p for p in x}
    except Exception:
        return {}


def fphoto(pid: str, cls: str, h: int, cap: str = "", eyebrow: str = "") -> str:
    p = _rotation().get(pid)
    if not p or not (ROOT / "static" / "featured-photos" / pid / ("%s-640.webp" % pid)).is_file():
        return ""
    base = "/static/featured-photos/%s/%s" % (pid, pid)
    eb = ('<span class="eyebrow">%s</span>' % _e(eyebrow)) if eyebrow else ""
    capb = ("<b>%s</b>" % _e(cap)) if cap else ""
    return ('<figure class="%s"><picture><source type="image/avif" srcset="%s-640.avif 640w, %s-1024.avif 1024w" sizes="100vw">'
            '<img src="%s-640.webp" srcset="%s-640.webp 640w, %s-1024.webp 1024w" sizes="100vw" alt="%s" width="640" height="%d" loading="lazy" decoding="async" fetchpriority="low"></picture>'
            '<figcaption>%s%s <span class="cr">%s</span></figcaption></figure>') % (
        cls, base, base, base, base, base, _a(p.get("alt") or ""), h, eb, capb, _e(p.get("credit") or ""))


def water_index(rid: str | None) -> str:
    out = []
    for label, items in sprint_home.public_region_groups(rid or ""):
        if not items:
            continue
        lis = "".join('<li><a href="%s?region=%s"%s>%s</a></li>' % (ROUTE, _a(r), ' aria-current="page"' if c else "", _e(n))
                      for r, n, c, _h in items)
        on = any(c for _r, _n, c, _h in items)
        out.append('<div class="wp%s"><span class="wt">%s</span><ol>%s</ol></div>' % (" on" if on else "", _e(label.upper()), lis))
    return '<nav class="twin" aria-label="Choose your water">%s</nav>' % "".join(out)


def _today_rotation(fresh: bool, now: datetime | None = None) -> dict | None:
    """Today's photograph from the public rotation (photo_rotation): salt uses sprint_home._featured()
    exactly as the public homepage does; fresh uses the same manifest's freshwater/inland pool."""
    try:
        import photo_rotation
        if not fresh:
            return sprint_home._featured()
        man = photo_rotation.active()
        if not man:
            return None
        pool = [e for e in man["photos"] if e.get("approved") and (e.get("category") == "freshwater" or photo_rotation.is_inland(e))]
        shot = photo_rotation.pick(pool, photo_rotation.et_date(now)) if pool else None
        return photo_rotation.resolve(shot, sprint_home.approved_photos()) if shot else None
    except Exception:
        return None


def today_html(ph: dict | None, fallback: str) -> str:
    if not ph:
        return fallback
    try:
        import photo_rotation
        srcs = ph.get("sources") or {}
        fmts = [(f, m) for f, m in photo_rotation.FORMATS if srcs.get(f)]
        if not fmts or not ph.get("alt"):
            return fallback
        sizes = "(max-width: 700px) 100vw, 700px"
        parts = "".join('<source type="%s" srcset="%s" sizes="%s">' % (m, photo_rotation.srcset(srcs[f]), sizes) for f, m in fmts[:-1])
        last = srcs[fmts[-1][0]]
        fb = last[640] if 640 in last else (last[800] if 800 in last else last[min(last)])
        title = ph.get("description") or ph.get("location") or ""
        return ('<figure class="today" data-photo="%s"><picture>%s<img src="%s" srcset="%s" sizes="%s" alt="%s" width="%d" height="%d" '
                'loading="lazy" decoding="async" fetchpriority="low"></picture><figcaption><span class="eyebrow">TODAY’S PHOTOGRAPH</span>'
                '<b>%s</b> <span class="cr">%s</span></figcaption></figure>') % (
            _a(ph.get("id") or ""), parts, _a(photo_rotation.src_url(fb)), photo_rotation.srcset(last), sizes, _a(ph["alt"]),
            int(ph.get("width") or 1600), int(ph.get("height") or 1000), _e(title), photo_rotation.credit_html(ph))
    except Exception:
        return fallback


def featured_catch() -> dict | None:
    """The Catch Wall's own featured slot (admin flag, else newest approved fishing photo)."""
    try:
        import catch_wall_public
        ph = sprint_home.approved_photos()
        f, _rest = catch_wall_public.pick_featured(ph)
        return catch_wall_public.localize_featured(f) if f else None
    except Exception:
        return None


def mosaic_html(fresh: bool) -> str:
    try:
        P = sprint_home._photos()
    except Exception:
        P = {}
    picks = [P.get("fresh"), P.get("wide"), P.get("lead")] if fresh else [P.get("lead"), P.get("life"), P.get("life2")]
    feat = featured_catch()
    if feat:
        fid = str(feat.get("id") or "").lower()
        picks = [feat] + [p for p in picks if p and str(p.get("id") or "").lower() != fid]
    cells = []
    for i, p in enumerate([p for p in picks if p][:3]):
        eb = '<span class="eyebrow">FEATURED ON THE CATCH WALL</span>' if (feat and p is feat) else ""
        cells.append('<figure class="w%d">%s<figcaption>%s<b>%s</b>%s</figcaption></figure>' % (
            i, sprint_home.img_html(p, "(max-width: 640px) 60vw, 400px"), eb, _e(sprint_home.caption(p)), _e(sprint_home.credit(p))))
    if not cells:
        return '<p class="dek">Catch Wall photographs are not available right now.</p>'
    return '<div class="mosaic n%d">%s</div>' % (len(cells), "".join(cells))


# ---------------------------------------------------------------- page

def _ramps_public() -> bool:
    try:
        import launch_flags
        return bool(launch_flags.ramps_public())
    except Exception:
        return False


def nav_html(primary: list, rid: str, fresh: bool, dash_href: str) -> str:
    """Primary row plus an "All sections" menu (native <details>, no script, in normal flow so it
    pushes content down and never covers it). Every link is a 44 px tap target."""
    row = "".join('<a href="%s"%s>%s</a>' % (_a(h), ' aria-current="page"' if c else "", _e(n)) for n, h, c in primary)
    allx = [("Conditions · Saltwater", "%s?region=crystal-coast" % ROUTE), ("Conditions · Freshwater", "%s?region=falls-lake" % ROUTE),
            ("Choose your water", "#rp"), ("Morning Brief", brief_href(rid)), ("Wind Viewer", "/wind"), ("Radar Viewer", "/radar"),
            ("Fishing Reports", "/reports"), ("Regulations", "#regs"), ("Map &amp; tides" if not fresh else "Lake &amp; river map", dash_href),
            ("Toolbox · chart, tides, radar", "#tools"), ("Catch Wall", "/catch-wall"), ("Coastal Life", "/coastal-life"), ("All Photos", "/photos")]
    if _ramps_public():   # same launch flag as the public nav; /ramps is not public yet
        allx.append(("Find a Ramp", "/ramps"))
    lis = "".join('<li><a href="%s">%s</a></li>' % (_a(h), n) for n, h in allx)
    lis += '<li><button type="button" class="fb-open" data-feedback-open aria-haspopup="dialog" aria-controls="fb-dlg">Feedback</button></li>'
    return ('<div class="navrow">%s</div><details class="allnav"><summary aria-label="All sections menu">'
            '<span aria-hidden="true">☰</span> Menu</summary><ul>%s</ul></details>') % (row, lis)


def brief_href(rid: str) -> str:
    """Same rule as the public homepage: this region's own /brief page (site_chrome.brief_target)."""
    try:
        import site_chrome
        tgt, _own = site_chrome.brief_target(rid)
        return "/brief?region=%s" % tgt
    except Exception:
        return "/brief"


def build(rid: str | None, *, now: datetime | None = None, salt_payload=None, fresh_payload=None, grid=None,
          fetch: bool = True) -> str:
    now = now or datetime.now(timezone.utc)
    rid = valid_region(rid)
    fresh = rid in FRESH_IDS
    if fresh:
        p = fresh_payload if fresh_payload is not None else (_fresh(rid) if fetch else None)
        if p:
            m = sprint_home.fresh_model(p)
        else:
            m = sprint_home.fresh_loading_model(rid)
            m["pending"] = False
            for t in m["tiles"] + m["more"]:
                t["off"] = "Readings unavailable right now."
            m["alerts"] = {"state": "unknown", "items": [{"event": sprint_home.ALERTS_OFF[0], "meta": sprint_home.ALERTS_OFF[1]}]}
            m["forecast"] = {"off": sprint_home.FRESH_POINT_OFF}
        region = (p or {}).get("region") or m.get("region") or {}
    else:
        p = salt_payload if salt_payload is not None else (_salt(rid) if fetch else None)
        if p:
            m = sprint_home.salt_model(p)
        else:
            m = {"ok": False, "water": "salt", "region": {"id": rid or "", "name": ""}, "tiles": [], "more": [],
                 "alerts": {"state": "unknown", "items": [{"event": sprint_home.ALERTS_OFF[0], "meta": sprint_home.ALERTS_OFF[1]}]},
                 "forecast": {"off": sprint_home.MARINE_OFF}, "updated": ""}
        region = (p or {}).get("region") or {}
    rid = rid or region.get("id") or ""
    anchor = region.get("anchor") or {}
    lat, lon = anchor.get("lat"), anchor.get("lon")
    place = anchor.get("label") or region.get("name") or ""
    title = region.get("name") or "The Coastal Brief"
    by = {t.get("id"): t for t in m.get("tiles", []) + m.get("more", [])}
    moon_led, _moon = moon(now, place or title)
    water_kind = "salt"
    if fresh:
        lake = bool(by.get("lake")) or rid in GAUGES
        water_kind = "lake" if lake else "river"
        g = grid if grid is not None else (_grid() if fetch else {"ok": False})
        wt = gfs_wind_tile(g, lat, lon) if _num(lat) and _num(lon) else sprint_home._tile(state="off", kind="Forecast", off="Model wind is unavailable right now.")
        dial = dial_html(wt)
        if lake:
            side = lake_cell(by.get("lake") or sprint_home._tile(id="lake", state="off", off=sprint_home.LAKE_OFF), rid) + water_cell(by.get("water") or sprint_home._tile(state="off"))
            ledger = "".join(ledger_row(by[k]) for k in ("release", "inflow", "rain") if k in by) + moon_led
        else:
            rivers = (p or {}).get("river") or []
            hero = next((r for r in rivers if r.get("usgs") == "02087500"), rivers[0] if rivers else None)
            side = (river_cell(hero) if hero else '<div class="cell river"><div class="lbl"><span>RIVER STAGE</span><i class="k off">UNAVAILABLE</i></div><p class="offv">%s</p></div>' % _e(sprint_home.STAGE_OFF))
            side += water_cell(by.get("water") or sprint_home._tile(state="off"))
            others = [t for t in m.get("tiles", []) if str(t.get("id", "")).startswith("river-") and (not hero or (hero.get("label") or "") not in (t.get("name") or ""))]
            ledger = "".join(ledger_row(t) for t in others) + "".join(ledger_row(by[k]) for k in ("rain",) if k in by) + moon_led
        cluster = dial + '<div class="side">%s</div>' % side
    else:
        tiles = {t.get("id"): t for t in m.get("tiles", [])}
        more = {t.get("id"): t for t in m.get("more", [])}
        wind = tiles.get("wind") or sprint_home._tile(state="off")
        cluster = dial_html(wind, label="Wind" if wind.get("name", "Wind") == "Wind" else wind["name"])
        cluster += '<div class="side">%s%s</div>' % (seas_cell(tiles.get("seas") or sprint_home._tile(state="off"), more.get("swell")),
                                                   water_cell(tiles.get("water") or sprint_home._tile(state="off")))
        cluster += tide_strip(tiles.get("tide") or sprint_home._tile(state="off", kind="Predicted", off=sprint_home.TIDE_OFF))
        ledger = "".join(ledger_row(more[k]) for k in ("air", "pressure", "harbor") if k in more) + moon_led
    rib = ribbon(now, lat, lon, place or title, (by.get("tide") if not fresh else None), water_kind) if _num(lat) and _num(lon) else ""
    upd = m.get("updated") or "—"
    nav_items = [("Saltwater", "%s?region=crystal-coast" % ROUTE, not fresh), ("Freshwater", "%s?region=falls-lake" % ROUTE, fresh),
                 ("Wind", "/wind", False), ("Radar", "/radar", False), ("Fishing Reports", "/reports", False)]
    nav = nav_html(nav_items, rid, fresh, dash_href=("/lake?region=%s" % rid) if fresh else ("/dashboard?region=%s" % rid))
    picker = "".join('<optgroup label="%s">%s</optgroup>' % (_a(label), "".join(
        '<option value="%s"%s>%s</option>' % (_a(r), " selected" if c else "", _e(n)) for r, n, c, _h in items))
        for label, items in sprint_home.public_region_groups(rid) if items)
    dash = ("/lake?region=%s" % rid) if fresh else ("/dashboard?region=%s" % rid)
    if fresh:
        wphoto = fphoto("falls-lake-pier" if rid == "falls-lake" else ("jordan-lake-ebenezer" if rid == "jordan-lake" else "neuse-river-cliffs"), "wphoto", 427)
        strip = fphoto("neuse-river-cliffs" if rid != "neuse-river" else "fontana-lake-dock", "strip one", 250)
        tph = _today_rotation(True, now)
        today = today_html(tph, fphoto("mattamuskeet-sunset", "today", 427, "Sunset at Lake Mattamuskeet, North Carolina.", "TODAY’S PHOTOGRAPH"))
        tid = (tph or {}).get("id") or "mattamuskeet-sunset"
        # never the same photograph twice on a page: today's rotation pick replaces its fixed slot
        if tid == "neuse-river-cliffs" and rid != "neuse-river":
            strip = fphoto("fontana-lake-dock", "strip one", 250)
        first = ("mattamuskeet-sunset", "Sunset at Lake Mattamuskeet") if tid == "fontana-lake-dock" else ("fontana-lake-dock", "Still water, early light")
        if tid == "fontana-lake-dock" and rid == "neuse-river":
            strip = fphoto("mattamuskeet-sunset", "strip one", 250)
            first = ("neuse-river-cliffs", "Still water, early light") if False else ("jordan-lake-ebenezer", "Still water, early light")
        second = ("nantahala-family", "Rivers that raise families") if tid != "nantahala-family" else ("mattamuskeet-sunset", "Sunset at Lake Mattamuskeet")
        story = fphoto(first[0], "", 427, first[1]) + fphoto(second[0], "", 427, second[1])
    else:
        wphoto = fphoto("november-fishing-cape-point", "wphoto", 427)
        strip = ('<figure class="strip"><picture><source type="image/avif" srcset="/static/night-strip/docks-phone-l-390.avif 390w">'
                 '<img src="/static/night-strip/docks-phone-l-390.webp" alt="%s" width="195" height="88" loading="lazy" decoding="async"></picture>'
                 '<picture><source type="image/avif" srcset="/static/night-strip/docks-phone-r-390.avif 390w">'
                 '<img src="/static/night-strip/docks-phone-r-390.webp" alt="" width="195" height="88" loading="lazy" decoding="async"></picture></figure>') % _a(sprint_home.STRIP_ALT)
        tph = _today_rotation(False, now)
        today = today_html(tph, fphoto("swan-quarter-landing", "today", 427, "Swan Quarter Landing, North Carolina.", "TODAY’S PHOTOGRAPH"))
        tid = (tph or {}).get("id") or "swan-quarter-landing"
        story = "".join(fphoto(i, "", 427, c) for i, c in (("dawn-at-topsail", "First light at Topsail"), ("shrimp-boats-wanchese", "The working harbor"),
                                                            ("swan-quarter-landing", "Swan Quarter Landing")) if i != tid and i != "november-fishing-cape-point")
        story = story if story.count("<figure") <= 2 else story[:story.index("<figure", story.index("<figure", 1) + 1)]
    tools = ('<a href="%s#map-chart">Nautical chart</a> · <a href="/radar">Radar</a> · <a href="%s#tide-search">Tide tables</a> · <a href="%s">Full dashboard</a>' % (_a(dash), _a(dash), _a(dash))) if not fresh else (
        '<a href="%s">Full lake &amp; river dashboard</a> · <a href="/radar">Radar</a> · <a href="/wind">Wind</a>' % _a(dash))
    test = '<p class="testbar" role="note">TEST DATA</p>' if (p or {}).get("testData") else ""
    main = """<section class="helm" id="helm" aria-labelledby="cg-h">%s
  <div class="edition"><div><h2 id="cg-h">Conditions at a Glance</h2>
    <form class="picker" action="%s" method="get"><label class="vh" for="rp">Choose your water</label>
      <select id="rp" name="region" class="region">%s</select><noscript><button type="submit">Go</button></noscript></form></div>
    <p class="upd">Updated<br><b>%s</b></p></div>
  %s
  <div class="cluster %s">%s
    %s
    <div class="ledger">%s</div>
  </div>
</section>
%s
<section class="chapter water" aria-labelledby="ow-h">
  <h2 id="ow-h" class="chap"><span>I.</span> On the Water</h2>
  %s
  %s
  %s
  %s
  <a class="briefbox" href="%s"><span class="eyebrow">EVERY MORNING</span><b>Today's Morning Brief</b><span>The whole morning on the water, on one page.</span></a>
  <p class="index" id="tools"><b>TOOLBOX · MAP, CHART &amp; RADAR</b> %s</p>
</section>
<section class="chapter coast" aria-labelledby="cl-h">
  %s
  <p class="phrase">More than the forecast. It’s a way of life.</p>
  <h2 class="chap" id="cl-h"><span>II.</span> The Coast</h2>
  %s
  <div class="story">%s</div>
  <p class="eyebrow">CATCH WALL · COASTAL LIFE</p><h3>From the docks, sounds and rivers</h3><p class="dek">Approved community photographs, shown as they were submitted.</p>
  %s
  <div class="ctas"><a class="cta" href="/catch-wall#share">Share yours on the Catch Wall</a><a class="cta2" href="/photos">All Photos →</a></div>
</section>""" % (test, ROUTE, picker, _e(upd), hazards_html(m.get("alerts") or {}, m.get("alerts_raw")), "fresh " + water_kind if fresh else "salt",
                  cluster, rib, ledger, gates_html(), reports_html(rid, fresh, now), forecast_quote(m.get("forecast"), fresh), water_index(rid), wphoto,
                  _a(brief_href(rid)), tools, strip, today, story, mosaic_html(fresh))
    return shell(main, title, fresh, nav)



def shell(main: str, title: str, fresh: bool, nav: str) -> str:
    css = _asset("helm.css").replace("</", "<\\/")
    fb = sprint_home._feedback_embed()
    return """<!DOCTYPE html>
<html lang="en" data-helm data-water="%s">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="robots" content="noindex, nofollow">
<title>The Coastal Brief · Signature Helm (private preview) · %s</title>
<meta name="description" content="Private homepage preview for The Coastal Brief. Not public.">
<meta name="color-scheme" content="light dark">
<meta name="theme-color" content="#071C29">
<link rel="preload" href="/static/night-strip/chart-560.webp" as="image" type="image/webp" fetchpriority="high">
<link rel="preload" href="/fonts/fraunces-var.woff2" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="/fonts/barlow-condensed-600.woff2" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="/fonts/source-sans-3-var.woff2" as="font" type="font/woff2" crossorigin>
<link rel="icon" href="/favicon.ico?v=20261121" sizes="48x48">
<link rel="icon" href="/branding/favicon.svg?v=20261121" type="image/svg+xml">
<link rel="apple-touch-icon" href="/apple-touch-icon.png?v=20261121" sizes="180x180">
<style id="helm-css">
%s
</style>
</head>
<body>
<a class="skip" href="#helm">Skip to Conditions at a Glance</a>
<header class="bridge">
  <div class="bar"><img class="mono" src="/branding/favicon.svg" alt="" width="34" height="34">
    <div class="wm"><a href="%s"><b>The Coastal Brief</b></a><small>Know the Water. Live the Coast.</small></div>
    <div class="cbm-tools"></div></div>
  <nav class="nav" aria-label="Sections">%s</nav>
  <p class="pvtag">Private preview · Signature Helm</p>
</header>
<main id="main">
%s
</main>
<footer class="ft foot"><div class="ft-in">
<p class="brand"><b>THE COASTAL BRIEF —</b><br><em>Know the Water. Live the Coast.</em></p>
%s
<p>Wind Viewer: NOAA NCEP GFS. Radar: NOAA/NSSL MRMS via WeatherAPI.com. Gateway maps: U.S. Census Bureau coastline; illustrations, not live data. Lake pool elevations: USACE Wilmington District. River flood stages: NWS (water.noaa.gov). Sun and moon: computed locally.</p>
%s</div></footer>
<script>(function(){var s=document.getElementById("rp");if(s)s.addEventListener("change",function(){location.href="%s?region="+encodeURIComponent(s.value)});})();</script>
</body>
</html>
""" % ("fresh" if fresh else "salt", _e(title), css, ROUTE, nav, main, sprint_home.PUBLIC_FOOTER, fb, ROUTE)


def page(rid: str | None, **kw) -> bytes:
    import theme_toggle
    data = build(rid, **kw).encode("utf-8")
    try:
        data = theme_toggle.paint(data)   # same Light / Dark / Auto system and storage key as public pages
    except Exception:
        pass
    return data
