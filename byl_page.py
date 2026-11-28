"""Before You Launch page (Phase 3B, private preview only). Renders Summer's approved layout from reviewed
records: the shell (access, regulations, computed sun and moon, links) is server-rendered with no network
calls; live readings arrive from the .json endpoint and replace skeleton cards. Every card says what kind
of value it is, where it came from and when. Nothing here states or implies that launching is safe."""
from __future__ import annotations

import html
import json
import math
from urllib.parse import quote

import byl_data

E = lambda s: html.escape(str(s if s is not None else ""), quote=True)
BASE = "/preview/before-you-launch"


def ic(n):
    P = {'back': '<path d="M15 5l-7 7 7 7"/>', 'nav': '<path d="M12 2l7 19-7-4-7 4z"/>',
         'ext': '<path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/>',
         'wind': '<path d="M3 8h11a3 3 0 1 0-3-3M3 12h16a3 3 0 1 1-3 3M3 16h8a3 3 0 1 1-3 3"/>',
         'radar': '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="4.5"/><path d="M12 12l6-6"/>',
         'book': '<path d="M5 4h11a3 3 0 0 1 3 3v13H8a3 3 0 0 1-3-3z"/><path d="M5 17a3 3 0 0 1 3-3h11"/>',
         'alert': '<path d="M12 3l10 18H2z"/><path d="M12 10v5M12 18v.1"/>',
         'rec': '<path d="M6 3h9l4 4v14H6z"/><path d="M9 12h7M9 16h7M9 8h3"/>',
         'q': '<circle cx="12" cy="12" r="9"/><path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.7.4-1 1-1 1.7M12 17v.1"/>',
         'info': '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5v.1"/>',
         'chart': '<path d="M4 4v16h16"/><path d="M8 15l3-4 3 2 5-7"/>'}
    return f'<svg class="ic" viewBox="0 0 24 24" aria-hidden="true">{P[n]}</svg>'


def tag(k):
    return f'<span class="tag t-{k}"><i class="g"></i>{byl_data.LABELS[k]}</span>'


def src(b, rest=""):
    return f'<p class="src"><span><b>{E(b)}</b>{" · " + E(rest) if rest else ""}</span></p>'


def sec(title, body, note=""):
    return f'<section class="sec"><h2>{E(title)}{f"<em>{E(note)}</em>" if note else ""}</h2>{body}</section>'


def moon_svg(k, r=17):
    rx = r * abs(1 - 2 * k)
    sweep = 1 if k > .5 else 0
    lit = f'M0,{-r} A{r},{r} 0 0 1 0,{r} A{rx:.1f},{r} 0 0 {sweep} 0,{-r}Z'
    return (f'<svg width="{2*r+6}" height="{2*r+6}" viewBox="{-r-3} {-r-3} {2*r+6} {2*r+6}" aria-hidden="true">'
            f'<circle r="{r}" fill="var(--moondark)" stroke="var(--ink2)" stroke-width="1.2"/><path d="{lit}" fill="var(--moonlit)"/></svg>')


DIRS = {d: i * 22.5 for i, d in enumerate(["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"])}
from datetime import datetime as _dt


def _ts(x):
    return _dt.fromisoformat(x)


def _hm(x):
    return _ts(x).astimezone(byl_data.ET).strftime("%-I%p").lower().replace("m", "")


def _scrub(rows, hint):
    """Interactive readout data: [x in viewBox units, text]. Each text is a real reading or prediction with its time."""
    return (f' tabindex="0" data-scrub="{E(json.dumps(rows, separators=(",", ":")))}" data-hint="{E(hint)}"')


def _tlabel(t):
    return _ts(t).astimezone(byl_data.ET).strftime("%a %-I:%M %p")


def _segments(pts, max_gap_s):
    """Split a series wherever readings are missing for longer than max_gap_s, so a gap is drawn
    as a gap and never bridged by a straight line."""
    segs = []
    for t, v in pts:
        ts = _ts(t).timestamp()
        if not segs or ts - segs[-1][-1][0] > max_gap_s:
            segs.append([])
        segs[-1].append((ts, v))
    return segs


def spark_svg(pts, label, unit, W=300, H=64, cls="obs"):
    """24 h line for a measured series; time axis is real time, no smoothing or filling."""
    vs = [v for _, v in pts]
    lo, hi = min(vs), max(vs)
    pad = max((hi - lo) * .15, 0.02 if unit == "ft" else 1)
    lo, hi = lo - pad, hi + pad
    t0, t1 = _ts(pts[0][0]).timestamp(), _ts(pts[-1][0]).timestamp()
    X = lambda t: 8 + (t - t0) / max(t1 - t0, 1) * (W - 16)
    Y = lambda v: 6 + (1 - (v - lo) / (hi - lo)) * (H - 22)
    segs = _segments(pts, 2 * 3600)
    d = "".join("M" + " L".join(f"{X(t):.1f},{Y(v):.1f}" for t, v in s) for s in segs)
    area = "".join("M" + " L".join(f"{X(t):.1f},{Y(v):.1f}" for t, v in s) + f" L{X(s[-1][0]):.1f},{H-16} L{X(s[0][0]):.1f},{H-16}Z" for s in segs)
    lx, ly = X(t1), Y(vs[-1])
    rows = [[round(X(_ts(t).timestamp()), 1), f"{v:g} {unit} · {_tlabel(t)}"] for t, v in pts]
    gap = "; gaps in the record are left blank" if len(segs) > 1 else ""
    return (f'<svg class="chart spark" viewBox="0 0 {W} {H}" role="img" aria-label="{E(label)}: last 24 hours, from {min(vs):g} to {max(vs):g} {E(unit)}{gap}"{_scrub(rows, "Measured")}>'
            f'<path class="a-{cls}" d="{area}"/><path class="l-{cls}" d="{d}"/><circle class="dot {cls[0]}" cx="{lx:.1f}" cy="{ly:.1f}" r="4"/>'
            f'<text x="8" y="{H-3}">{E(_hm(pts[0][0]))}</text><text x="{W-8}" y="{H-3}" text-anchor="end">now</text>'
            f'<text x="{W-8}" y="12" text-anchor="end">{max(vs):g}</text><text x="{W-8}" y="{H-19}" text-anchor="end">{min(vs):g}</text></svg>')


def lake_svg(hist, guide, datum, W=330, H=140):
    vs = [v for _, v in hist] + ([guide] if guide is not None else [])
    lo, hi = min(vs) - .3, max(vs) + .3
    t0, t1 = _ts(hist[0][0]).timestamp(), _ts(hist[-1][0]).timestamp()
    X = lambda t: 40 + (t - t0) / max(t1 - t0, 1) * (W - 50)
    Y = lambda v: 10 + (1 - (v - lo) / (hi - lo)) * (H - 44)
    segs = _segments(hist, 9 * 3600)  # points are 6-hourly; a longer jump means missing readings
    d = "".join("M" + " L".join(f"{X(t):.1f},{Y(v):.1f}" for t, v in s) for s in segs)
    g = ""
    if guide is not None:
        g = (f'<line class="l-guide" x1="40" x2="{W-10}" y1="{Y(guide):.1f}" y2="{Y(guide):.1f}"/>'
             f'<text x="{W-10}" y="{Y(guide)-5:.1f}" text-anchor="end">guide curve {guide:g}</text>')
    ticks = ""
    step = max(1, int((hi - lo) / 3 + .5))
    v = int(lo) + 1
    while v < hi:
        ticks += f'<line class="gl" x1="40" x2="{W-10}" y1="{Y(v):.1f}" y2="{Y(v):.1f}"/><text x="34" y="{Y(v)+4:.1f}" text-anchor="end">{v}</text>'
        v += step
    days = ""
    for t, _ in hist[::max(1, len(hist) // 4)]:
        days += f'<text x="{X(_ts(t).timestamp()):.1f}" y="{H-18}" text-anchor="middle">{_ts(t).astimezone(byl_data.ET).strftime("%b %-d")}</text>'
    lx, ly = X(t1), Y(hist[-1][1])
    rows = [[round(X(_ts(t).timestamp()), 1), f"{v:.2f} ft {datum} · {_tlabel(t)}" + (f" · {v - guide:+.2f} vs guide" if guide is not None else "")] for t, v in hist]
    return (f'<svg class="chart" viewBox="0 0 {W} {H}" role="img" aria-label="Lake elevation, last 14 days, feet above {E(datum)}{", with guide curve" if guide else ""}"{_scrub(rows, "Measured, 6-hourly")}>'
            f'{ticks}{g}<path class="l-obs" d="{d}"/><circle class="dot o" cx="{lx:.1f}" cy="{ly:.1f}" r="5"/>{days}'
            f'<text x="40" y="{H-1}">ft above {E(datum)} · 14 days · USGS{" · gaps left blank" if len(segs) > 1 else ""}</text></svg>')


def tide_svg(curve, events, now, W=330, H=118):
    vs = [v for _, v in curve]
    lo, hi = min(vs) - .2, max(vs) + .35
    t0, t1 = _ts(curve[0][0]).timestamp(), _ts(curve[-1][0]).timestamp()
    X = lambda t: 10 + (t - t0) / (t1 - t0) * (W - 20)
    Y = lambda v: 22 + (1 - (v - lo) / (hi - lo)) * (H - 46)
    d = "M" + " L".join(f"{X(_ts(t).timestamp()):.1f},{Y(v):.1f}" for t, v in curve)
    area = d + f" L{X(t1):.1f},{H-22} L{X(t0):.1f},{H-22}Z"
    ev = ""
    for e in events:
        t = _ts(e["ts"]).timestamp()
        if t0 <= t <= t1:
            x, y = X(t), Y(e["ft"])
            ev += (f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.6" fill="var(--pred)"/>'
                   f'<text class="tb" x="{min(max(x, 30), W-30):.1f}" y="{(y-8) if e["type"] == "High" else (y+16):.1f}" text-anchor="middle">{"H" if e["type"] == "High" else "L"} {E(e["time"])}</text>')
    nt = _ts(now).timestamp()
    nx = X(min(max(nt, t0), t1))
    step = max(1, round(len(curve) / 24 * 6))  # an hour label every 6 h
    grid = "".join(f'<text x="{X(_ts(t).timestamp()):.1f}" y="{H-6}" text-anchor="middle">{E(_hm(t))}</text>' for t, _ in curve[::step])
    # readout: every plotted 6-minute NOAA prediction
    rows = [[round(X(_ts(t).timestamp()), 1), f"{v:.2f} ft MLLW · {_tlabel(t)}"] for t, v in curve]
    return (f'<svg class="chart" viewBox="0 0 {W} {H}" role="img" aria-label="NOAA 6-minute tide predictions, 6 hours ago to 18 hours ahead, feet above MLLW, with now marker"{_scrub(rows, "Predicted")}>'
            f'<path class="a-pred" d="{area}"/><path class="l-pred" d="{d}"/>{ev}<line class="now" x1="{nx:.1f}" x2="{nx:.1f}" y1="8" y2="{H-22}"/>'
            f'<text class="tb" x="{nx+4:.1f}" y="14">now</text>{grid}</svg>')


def hilo_svg(events, now, W=330, H=118):
    """Official NOAA high and low predictions as a schedule: one bar per event at its time, height
    from MLLW 0. No line joins the bars, because the station publishes no values in between."""
    n0 = _ts(now).timestamp()
    t0, t1 = n0 - 4 * 3600, n0 + 20 * 3600
    ev = [e for e in events if t0 <= _ts(e["ts"]).timestamp() <= t1]
    if not ev:
        return ""
    vs = [float(e["ft"]) for e in ev] + [0.0]
    lo, hi = min(vs) - .3, max(vs) + .6
    X = lambda t: 14 + (t - t0) / (t1 - t0) * (W - 28)
    Y = lambda v: 20 + (1 - (v - lo) / (hi - lo)) * (H - 46)
    out, rows = "", []
    for e in ev:
        x, v = X(_ts(e["ts"]).timestamp()), float(e["ft"])
        y0, y1 = Y(0), Y(v)
        hiw = e["type"] == "High"
        out += (f'<rect class="{"b-hi" if hiw else "b-lo"}" x="{x-7:.1f}" y="{min(y0, y1):.1f}" width="14" height="{max(abs(y1-y0), 1.5):.1f}" rx="3"/>'
                f'<text class="tb" x="{min(max(x, 26), W-26):.1f}" y="{(min(y0, y1) - 5) if hiw else (max(y0, y1) + 13):.1f}" text-anchor="middle">{"H" if hiw else "L"} {v:.1f}</text>'
                f'<text x="{min(max(x, 22), W-22):.1f}" y="{H-6}" text-anchor="middle">{E(e["time"].replace(" AM", "a").replace(" PM", "p"))}</text>')
        rows.append([round(x, 1), f'{e["type"]} {v:.1f} ft MLLW · {_tlabel(e["ts"])}'])
    nx = X(n0)
    return (f'<svg class="chart" viewBox="0 0 {W} {H}" role="img" aria-label="NOAA high and low tide predictions, feet above MLLW, with now marker"{_scrub(rows, "Predicted")}>'
            f'<line class="base" x1="8" x2="{W-8}" y1="{Y(0):.1f}" y2="{Y(0):.1f}"/><text x="{W-10}" y="{Y(0)-3:.1f}" text-anchor="end">0 = MLLW</text>{out}'
            f'<line class="now" x1="{nx:.1f}" x2="{nx:.1f}" y1="8" y2="{H-22}"/><text class="tb" x="{nx+4:.1f}" y="14">now</text></svg>')


def compass_svg(deg, kt, R=34):
    arrow = ""
    if deg is not None:
        arrow = f'<g transform="rotate({(deg + 180) % 360})"><path d="M0 -{R-8} L7 6 L0 1 L-7 6Z" fill="var(--obs)"/></g>'
    ticks = "".join(f'<text x="{(R+9)*__import__("math").sin(a*3.14159/180):.1f}" y="{-(R+9)*__import__("math").cos(a*3.14159/180)+4:.1f}" text-anchor="middle">{n}</text>'
                    for n, a in (("N", 0), ("E", 90), ("S", 180), ("W", 270)))
    return (f'<svg width="{2*R+34}" height="{2*R+34}" viewBox="{-R-17} {-R-17} {2*R+34} {2*R+34}" role="img" aria-label="Wind direction: arrow points where the wind is blowing toward">'
            f'<circle r="{R}" fill="none" stroke="var(--hair)" stroke-width="2"/>{ticks}{arrow}</svg>')


def wind_bars_svg(hourly, W=330, H=86):
    n = len(hourly)
    m = max(max(h["mph"] for h in hourly), 10) * 1.15
    bw = (W - 20) / n
    out = ""
    for i, h in enumerate(hourly):
        x = 10 + i * bw + bw * .2
        w = bw * .6
        bh = h["mph"] / m * 44
        out += f'<rect class="bar-f" x="{x:.1f}" y="{50-bh:.1f}" width="{w:.1f}" height="{bh:.1f}" rx="2"/><text x="{x+w/2:.1f}" y="{46-bh:.1f}" text-anchor="middle">{h["mph"]}</text>'
        if h["dir"] in DIRS and h["mph"] > 0:
            out += f'<g transform="translate({x+w/2:.1f},62) rotate({(DIRS[h["dir"]] + 180) % 360})"><path d="M0 -6 L4 5 L0 2.5 L-4 5Z" fill="var(--ink2)"/></g>'
        if i % 3 == 0:
            out += f'<text x="{x+w/2:.1f}" y="{H-4}" text-anchor="middle">{E(_hm(h["t"]))}</text>'
    return (f'<svg class="chart" viewBox="0 0 {W} {H}" role="img" aria-label="NWS hourly wind forecast for the next {n} hours, mph; arrows show where the wind blows toward">{out}</svg>')


SLOT_H = {"alerts": "s-alerts", "forecast": "s-forecast", "marine": "s-marine", "wind_obs": "s-wind", "tide": "s-tide", "lake": "s-lake",
          "usace": "s-small", "temp": "s-small", "coastal_temp": "s-small", "water_level": "s-level", "below_dam": "s-spark"}


def _slot(key):
    return "slot " + SLOT_H.get(key, "s-spark" if key.startswith("river:") else "s-small")


def _unav_html(c):
    return (f'<section class="card un {_slot(c["key"])}" data-card="{E(c["key"])}"><div class="top"><span class="lbl">{E(c["label"])}</span>{tag("unav")}</div>'
            f'<p>{E(c["note"])}</p>{src(c["source"]) if c.get("source") else ""}</section>')


def card_html(c):
    """One reading card. Unavailable cards never carry a value. Each card keeps its slot class so the
    reserved height is the same before and after the reading arrives."""
    k = c["kind"]
    key = c["key"]
    if k == "unav":
        return _unav_html(c)
    stale = '<p class="note stale-n"><b>Stale:</b> the latest value available, older than usual for this source.</p>' if k == "stale" else ""
    head = f'<div class="top"><span class="lbl">{E(c["label"])}</span>{tag(k)}</div>'
    if key == "alerts":
        if not c["alerts"]:
            return (f'<section class="card none {_slot(key)}" data-card="alerts"><span style="color:var(--ink2)">{ic("info")}</span><div><p><b>No NWS alert listed for this point.</b> '
                    f'{E(c["when"])}. <i>An empty list is not an all-clear.</i></p>'
                    f'<a class="lk2" href="{E(c.get("link") or "https://www.weather.gov/")}" rel="noopener">NWS forecast and hazards for this spot{ic("ext")}</a></div></section>')
        names = ", ".join(dict.fromkeys(a["event"] for a in c["alerts"]))
        items = "".join(f'<li><b>{E(a["event"])}</b>: {E(a["headline"])}</li>' for a in c["alerts"])
        return (f'<section class="card adv {_slot(key)}" data-card="alerts" role="alert"><div class="ico">{ic("alert")}</div><div class="advb"><div class="eyebrow">Official notice · NWS · {E(c["when"])}</div>'
                f'<h3 class="clamp2">{E(names)}</h3><div class="advrow"><details><summary>Details</summary><ul>{items}</ul>{src(c["source"], c["when"])}</details>'
                f'<a class="lk2" href="{E(c.get("link") or "https://www.weather.gov/")}" rel="noopener">Full NWS text{ic("ext")}</a></div></div></section>')
    body = ""
    if key == "forecast":
        body = '<ul class="fc">' + "".join(f'<li><b>{E(p["name"])}</b><span class="t">{E(p["temp"])}°</span> {E(p["short"])}<br><small>Wind {E(p["wind"])}</small></li>' for p in c["periods"][:4]) + "</ul>"
        if c.get("hourly"):
            body += '<p class="note">Hourly wind forecast, mph</p>' + wind_bars_svg(c["hourly"])
    elif key == "marine":
        hd = "".join(f'<p class="advline clamp2">{E(h[:1].upper() + h[1:].lower())}</p>' for h in (c.get("headlines") or [])[:1])
        p = c["periods"]
        lead = f'<p class="note ocean-n">{E(c["note"])}</p>' if c.get("note") else ""
        body = lead + hd + f'<p class="mz clamp4"><b>{E(p[0]["name"])}</b> {E(p[0]["text"])}</p>'
        body += ('<details><summary>Full zone forecast</summary>' + "".join(f'<p class="mz"><b>{E(h[:1].upper() + h[1:].lower())}</b></p>' for h in c.get("headlines") or [])
                 + "".join(f'<p class="mz"><b>{E(x["name"])}</b> {E(x["text"])}</p>' for x in p) + "</details>")
        c = dict(c, note="")
    elif key == "wind_obs":
        g = f' · gusts {c["gust_mph"]} mph' if c.get("gust_mph") is not None else ""
        body = (f'<div class="wind">{compass_svg(None if c.get("calm") else c.get("deg"), c["kt"])}<div><div class="big">{c["mph"]}<small>mph</small></div>'
                f'<p class="delta">{"Calm" if c.get("calm") else ("From " + E(c["dir"]) if c.get("dir") and c.get("deg") is not None else "Direction variable or not reported")}{g}</p><p class="note">{c["kt"]} kt{f" · gusts {c[chr(103)+chr(117)+chr(115)+chr(116)+chr(95)+chr(107)+chr(116)]} kt" if c.get("gust_kt") is not None else ""}</p></div></div>')
    elif key == "tide":
        cv = c.get("curve")
        if cv:
            body = tide_svg(cv["pts"], c.get("all_events") or c["events"], c.get("now") or cv["pts"][0][0]) + '<p class="note">NOAA 6-minute predictions, feet above MLLW (mean lower low water). Not water depth.</p>'
        elif c.get("now") and hilo_svg(c.get("all_events") or c["events"], c["now"]):
            body = (hilo_svg(c.get("all_events") or c["events"], c["now"])
                    + '<p class="note">This NOAA station publishes official high and low predictions only, so no curve is drawn between them. Feet above MLLW; not water depth.</p>')
        else:
            body = '<div class="chart-ph">Tide chart not available right now. High and low times below.</div>'
        body += '<ul class="tides">' + "".join(f'<li><b>{E(e["type"])}</b> {E(e["day"])} {E(e["time"])} · {E(e["ft"])} ft</li>' for e in c["events"]) + "</ul>"
    elif "value" in c:
        extra = ""
        if c.get("vs_guide") is not None:
            extra = f'<span class="delta">{c["vs_guide"]:+.2f} ft vs guide curve</span>'
        elif c.get("trend"):
            extra = f'<span class="delta">{E(c["trend"])} over 6 h</span>'
        v = c["value"]
        v = int(v) if float(v).is_integer() and c.get("unit") in ("cfs", "°F") else v
        dat = f'<span class="datum">{E(c["datum"])}</span>' if c.get("datum") and c.get("unit") == "ft" else ""
        body = f'<div class="val"><span class="big">{E(v)}<small>{E(c["unit"])}</small></span>{dat}{extra}</div>'
        if key == "lake":
            body += lake_svg(c["hist"], c.get("guide"), c.get("datum") or "") if c.get("hist") else '<div class="chart-ph">14-day chart not loaded yet. Reload in a minute.</div>'
            if c.get("guide_note"):
                body += f'<p class="note">The guide difference is {tag("comp")}. {E(c["guide_note"])} The guide curve is the operator’s seasonal target, not a safety line.</p>'
        elif c.get("spark"):
            body += spark_svg(c["spark"], c["label"], c.get("unit") or "")
    note = f'<p class="note">{E(c["note"])}</p>' if c.get("note") else ""
    return f'<section class="card rd {_slot(key)}{" s-marine-o" if key == "marine" and "ocean" in c["label"].lower() else ""}" data-card="{E(key)}">{head}{body}{stale}{note}{src(c["source"], c["when"])}</section>'


def fragments(data):
    return {k: (sun_card(c) if k == "sun" else card_html(c)) for k, c in data["cards"].items()}


def _skel(key, label):
    return (f'<section class="card rd skel {_slot(key)}" data-card="{E(key)}" aria-busy="true"><div class="top"><span class="lbl">{E(label)}</span>'
            f'<span class="tag">Loading</span></div></section>')


def coastal(site_id):
    return byl_data.load_coastal().get(site_id) or {}


def slots(site, cz=None):
    """Water slots the page expects, in order. Only reviewed publishable stations (and reviewed coastal
    instruments) get a slot, so nothing is promised that the data layer will not try to provide."""
    cz = coastal(site["id"]) if cz is None else cz
    water = []
    if byl_data.water_ok(site):
        for c in site["stations"]:
            if not c["publishable"]:
                continue
            key = {"lake_elevation": "lake" if c["source"] == "USGS" else "usace", "water_temp": "temp", "downstream_river_flow": "below_dam",
                   "river_stage_flow": "river:" + c["id"], "tide_predictions": "tide"}.get(c["type"])
            lab = {"lake": "Lake elevation", "usace": "Official lake level", "temp": "Water temperature", "below_dam": "River flow below the dam (measured)",
                   "tide": "Tide predictions"}.get(key, "River gauge")
            if key == "tide" and site["tide_policy"] != "predictions":
                continue
            if key and (key, lab) not in water:
                water.append((key, lab))
        for x in byl_data.accepted(cz.get("water")):
            k = ("coastal_temp", "Water temperature") if x["type"] == "water_temp" else ("water_level", "Water level (observed)")
            if k not in water:
                water.append(k)
    return water


def access_card(rec):
    st = rec.get("st") or "not_stated"
    unc = st in ("not_stated", "unknown", "")
    icon = ic("q") if unc else ic("rec")
    kv = "".join(f"<dt>{E(a)}</dt><dd>{E(b)}</dd>" for a, b in (("Launch", rec.get("tyl")), ("Fees", rec.get("fs") or "Not stated"),
                                                                     ("Notes", rec.get("rx"))) if b)
    return (f'<section class="card"><div class="acc"><div class="ico {"unc" if unc else "lo"}">{icon}</div><div><div class="row"><span class="lbl">Access</span>{tag("rec")}</div>'
            f'<h3>{E(rec.get("stf") or rec.get("stl") or "Status not stated")}</h3><p>{E(rec.get("sd") or "")}</p></div></div>'
            f'<p class="src" style="margin-top:8px"><span><b>{E(rec.get("cs") or "Ramp inventory")}</b> · recorded {E(rec.get("sa"))} · not a live check</span></p>'
            f'<details class="more"><summary>Ramp details</summary><dl class="kv">{kv}</dl></details></section>')


def regs_card(site):
    r = site["regs"]
    links = "".join(f'<a class="lk" href="{E(l["url"])}" rel="noopener"><span class="ico">{ic("book")}</span><span><small>{E(l["agency"])}</small>{E(l["label"])}</span>{ic("ext")}</a>' for l in r["links"])
    why = ""
    if r["jurisdiction"] in ("unresolved", "joint"):
        why = (f'<p class="regs-why">{"This ramp sits near the line between coastal, joint and inland fishing waters" if r["jurisdiction"] == "unresolved" else "These are joint fishing waters"}, '
               f'so both agencies&rsquo; rules may apply. Check the <a href="{E(r["boundary_map"])}" rel="noopener">official boundary map</a> for where you fish.</p>')
    return sec("Fishing regulations", f'<div class="links">{links}</div>{why}', "official links")


CHART_LINKS = (
    # Checked Nov 28, 2026: NOAA has sunset its raster charts (the old OnLineViewer pages now say so),
    # so the gateway links only to NOAA's current ENC products.
    ("https://nauticalcharts.noaa.gov/enconline/enconline.html", "NOAA ENC Viewer", "Official electronic navigational charts"),
    ("https://www.charts.noaa.gov/InteractiveCatalog/nrnc.shtml", "NOAA Chart Locator", "Find and download the ENC cells for this area"),
)


def charts_card(site, cz):
    """Nautical Charts gateway: current official NOAA ENC products, coastal and estuarine ramps only."""
    if site["water_class"] in byl_data.FRESH_CLASSES or not cz.get("chart"):
        return ""
    ch = cz["chart"]
    links = "".join(f'<a class="lk" href="{E(u)}" rel="noopener"><span class="ico">{ic("chart")}</span><span><small>{E(sm)}</small>{E(t)}</span>{ic("ext")}</a>'
                    for u, t, sm in CHART_LINKS)
    return sec("Nautical charts", f'<div class="links">{links}</div>'
               f'<p class="note">Area reference: this ramp lies on former NOAA chart {E(ch["chart"])} ({E(ch["title"])}, 1:{ch["scale"]:,}). '
               'NOAA has retired its raster charts; the ENC is the current official chart. Check Local Notices to Mariners for changes.</p>', "official NOAA")


def sun_card(c):
    if c["kind"] == "unav":
        return _unav_html(c)
    k = (c.get("moon_pct") or 0) / 100
    return (f'<section class="card rd sunrow" data-card="sun"><div class="sm1"><span class="lbl">Sunrise</span><b>{E(c["sunrise"])}</b></div><div class="sm1"><span class="lbl">Sunset</span><b>{E(c["sunset"])}</b></div>'
            f'<div class="sm1 mn">{moon_svg(k, 13)}<span><b>{E(c["moon_pct"])}%</b> {E(c["moon_phase"])}</span></div>'
            f'<p class="src sun-src"><span>{tag("comp")} {E(c["when"])} · for the ramp coordinates (NOAA solar equations; Meeus lunar phase)</span></p></section>')


def directions(rec):
    if rec.get("la") is not None:
        return "https://www.google.com/maps/dir/?api=1&destination=%.6f,%.6f" % (rec["la"], rec["lo"]), ("official map pin" if rec.get("pr") == "exact" else "approximate pin")
    return "https://www.google.com/maps/dir/?api=1&destination=" + quote(rec.get("ad") or rec.get("n")), "official address"


THEME_JS = "try{var t=localStorage.getItem('coastalBrief.theme');if(t==='dark'||(!t&&matchMedia('(prefers-color-scheme: dark)').matches))document.documentElement.classList.add('dark')}catch(e){}"
PRELOAD = ('<link rel="preload" href="/fonts/source-sans-3-var.woff2" as="font" type="font/woff2" crossorigin>'
           '<link rel="preload" href="/fonts/fraunces-var.woff2" as="font" type="font/woff2" crossorigin>')


def render(site_id, sites=None, records=None, now=None, cz=None):
    sites = sites or byl_data.load_sites()
    records = records or byl_data.load_records()
    site, rec = sites[site_id], records[site_id]
    cz = coastal(site_id) if cz is None else cz
    water = slots(site, cz)
    sun = byl_data.sun_moon(rec, now.astimezone(byl_data.ET).date() if now else None)
    durl, dsub = directions(rec)
    wc = {"reservoir": "Reservoir", "natural_lake": "Natural lake", "river": "River", "estuary_wind_driven": "Sound or river estuary (wind-driven water)",
          "tidal_lunar": "Tidal water", "unresolved": "Water type not yet confirmed"}[site["water_class"]]
    body = (f'<div class="head"><div class="eyebrow">Before you launch · {E(rec.get("w") or rec.get("a") or "")}</div><h1>{E(rec["n"])}</h1>'
            f'<p class="sub">{E(wc)} · {E(rec.get("ci"))}, {E(rec.get("co"))} County</p>'
            f'<div class="addr"><span><b>{E(rec.get("ad") or "")}</b><em>{E(dsub)}</em></span><a href="{E(durl)}" rel="noopener">{ic("nav")}Directions</a></div></div>')
    body += sec("Official notices", _skel("alerts", "Weather alerts"), "NWS")
    body += access_card(rec)
    body += sun_card(sun)
    wx = _skel("forecast", "Forecast near the ramp")
    if byl_data.accepted(cz.get("wind")):
        wx = _skel("wind_obs", "Wind now (observed)") + wx
    mzz = cz.get("marine_zone") or {}
    if mzz.get("decision") == "accepted":
        sk = _skel("marine", "Marine forecast")
        wx += sk.replace("s-marine", "s-marine s-marine-o", 1) if mzz.get("kind") == "ocean_beyond_inlet" else sk
    body += sec("Weather and wind", wx, "NWS · NOAA")
    main_w = [(k, l) for k, l in water if k != "below_dam"]
    if main_w:
        small = [x for x in main_w if SLOT_H.get(x[0]) == "s-small"]
        big = [x for x in main_w if x not in small]
        html_w = "".join(_skel(k, l) for k, l in big)
        if small:
            html_w += '<div class="grid2">' + "".join(_skel(k, l) for k, l in small) + "</div>"
        body += sec("Water", html_w)
    elif not byl_data.water_ok(site):
        body += sec("Water", f'<section class="card un withheld"><div class="top"><span class="lbl">Water readings</span>{tag("unav")}</div><p>The water type at this ramp is not yet confirmed, so no gauge or tide reading is shown. Forecasts and alerts do not depend on it.</p></section>')
    else:
        why = {"omit_wind_driven": "Water level here is driven mostly by wind, not by the moon, so tide predictions would mislead.",
               "unavailable_no_same_water_station": "No NOAA tide station on the same water was found within the review distance.",
               "omit_freshwater": "Freshwater: no tides."}.get(site["tide_policy"], "")
        body += sec("Water", f'<section class="card un"><div class="top"><span class="lbl">No reviewed water gauge for this ramp</span>{tag("unav")}</div><p>{E(why)} Readings from other water are not shown.</p></section>')
    if any(k == "below_dam" for k, _ in water):
        body += sec("Below the dam", _skel("below_dam", "River flow below the dam (measured)"))
    loc = locator_svg(site, rec, cz)
    if loc:
        body += sec("Station map", loc, "reviewed stations")
    body += charts_card(site, cz)
    body += regs_card(site)
    body += ('<details class="more foot"><summary>How to read this page</summary><p>Each reading shows what kind it is, where it came from and when. This page gathers information; it does not judge whether conditions suit your boat, crew or experience. '
             'Missing data is uncertainty, never a sign that conditions are fine. Lake elevation and gauge height are measured against a datum and are not water depth. Check official notices and conditions at the ramp.</p></details>')
    bar = (f'<nav class="bar" aria-label="Trip actions"><a class="dir" href="{E(durl)}" rel="noopener">{ic("nav")}<span>Driving directions<small>{E(dsub)}</small></span></a>'
           f'<a class="sm" href="/wind">{ic("wind")}Wind</a><a class="sm" href="/radar">{ic("radar")}Radar</a></nav>')
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
            f'<meta name="robots" content="noindex, nofollow"><title>{E(rec["n"])} · Before you launch · The Coastal Brief</title><script>{THEME_JS}</script>{PRELOAD}'
            f'<link rel="stylesheet" href="{BASE}/byl.css"></head><body>'
            f'<header class="mast"><a class="back" href="{BASE}" aria-label="All pilot ramps">{ic("back")}</a><b>The Coastal Brief<br><small>Before you launch</small></b>'
            f'<span class="th" role="group" aria-label="Theme"><button type="button" data-t="auto">Auto</button><button type="button" data-t="light">Light</button><button type="button" data-t="dark">Dark</button></span></header>'
            f'<main id="main" data-id="{E(site_id)}">{body}<p class="sr" aria-live="polite" id="live"></p></main>{bar}<script src="{BASE}/byl.js" defer></script></body></html>')


def index(sites, records):
    rows = "".join(f'<li><a class="lk" href="{BASE}/{E(i)}"><span><small>{E(s.get("area", ""))}</small>{E(records[i]["n"])}</span></a></li>'
                   for i, s in sorted(sites.items(), key=lambda kv: (kv[1].get("area", ""), records[kv[0]]["n"])))
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex, nofollow">'
            f'<title>Before you launch · pilot ramps</title><script>{THEME_JS}</script><link rel="stylesheet" href="{BASE}/byl.css"></head><body><main><div class="head"><h1>Before you launch: 79 pilot ramps (private)</h1></div><ul style="list-style:none;padding:0">{rows}</ul></main></body></html>')


_CACHE = {}


def resolve_request(path):
    """(status, content type, body) for a /preview/before-you-launch path. The caller checks the preview cookie first.
    Only the 79 pilot ramps resolve; anything else is 404."""
    from pathlib import Path
    sub = path[len(BASE):].strip("/")
    if sub in ("byl.css", "byl.js"):
        f = Path(__file__).resolve().parent / "preview/before-you-launch" / sub
        return 200, "text/css; charset=utf-8" if sub.endswith("css") else "text/javascript; charset=utf-8", f.read_bytes()
    if "sites" not in _CACHE:
        _CACHE["sites"], _CACHE["records"] = byl_data.load_sites(), byl_data.load_records()
        byl_data.warm()
    sites, records = _CACHE["sites"], _CACHE["records"]
    if sub == "":
        return 200, "text/html; charset=utf-8", index(sites, records)
    if sub.endswith(".json"):
        sid = sub[:-5]
        if sid not in sites:
            return 404, "", b""
        d = byl_data.assemble(sid, sites=sites, records=records)
        import json
        return 200, "application/json; charset=utf-8", json.dumps({"id": sid, "generated": d["generated"], "withheld": d["withheld"],
                                                                     "cards": d["cards"], "fragments": fragments(d)}, default=str)
    if sub not in sites or "/" in sub:
        return 404, "", b""
    return 200, "text/html; charset=utf-8", render(sub, sites, records)


# ---------- geographic locator (Ed t572u): where each reading comes from, drawn on official TIGER/Line water
_GEO = {}


def _enc():
    """NOAA ENC land areas (LNDARE) already in the repo for the coastal basemap (wind-coast/enc.json,
    CC0, Office of Coast Survey; see docs/BASEMAP.md), plus its coverage mask. Not for navigation."""
    if "enc" not in _GEO:
        from pathlib import Path
        d = json.loads((Path(__file__).resolve().parent / "wind-coast/enc.json").read_text())
        q = d["q"]

        def dec(polys):
            out = []
            for p in polys:
                rings = []
                for a in p["r"]:
                    x = y = 0
                    pts = []
                    for i in range(0, len(a) - 1, 2):
                        x += a[i]; y += a[i + 1]
                        pts.append((x / q, y / q))
                    rings.append(pts)
                out.append(([v / q for v in p["b"]], rings))
            return out
        _GEO["enc"] = (dec(d["polys"]), dec(d["cover"]))
    return _GEO["enc"]


def _in_polys(polys, lo, la):
    inside = False
    for b, rings in polys:
        if lo < b[0] or lo > b[2] or la < b[1] or la > b[3]:
            continue
        for r in rings:
            j = len(r) - 1
            for i in range(len(r)):
                (xi, yi), (xj, yj) = r[i], r[j]
                if (yi > la) != (yj > la) and lo < (xj - xi) * (la - yi) / (yj - yi) + xi:
                    inside = not inside
                j = i
    return inside


def _clip_ring(r, x0, y0, x1, y1):
    """Sutherland-Hodgman clip of one ring to a lon/lat rectangle."""
    def clip(pts, inside, cut):
        out = []
        for i in range(len(pts)):
            a, b = pts[i - 1], pts[i]
            if inside(b):
                if not inside(a):
                    out.append(cut(a, b))
                out.append(b)
            elif inside(a):
                out.append(cut(a, b))
        return out

    def cx(x):
        return lambda a, b: (x, a[1] + (b[1] - a[1]) * (x - a[0]) / (b[0] - a[0]))

    def cy(y):
        return lambda a, b: (a[0] + (b[0] - a[0]) * (y - a[1]) / (b[1] - a[1]), y)
    pts = r
    for inside, cut in ((lambda p: p[0] >= x0, cx(x0)), (lambda p: p[0] <= x1, cx(x1)),
                        (lambda p: p[1] >= y0, cy(y0)), (lambda p: p[1] <= y1, cy(y1))):
        pts = clip(pts, inside, cut)
        if not pts:
            return []
    return pts


def enc_land(x0, y0, x1, y1):
    """ENC land rings clipped to the frame, or None when any part of the frame lies outside the
    ENC coverage mask (then the map would show uncharted land as water, so it is not used)."""
    land, cover = _enc()
    n = 6
    for i in range(n + 1):
        for j in range(n + 1):
            if not _in_polys(cover, x0 + (x1 - x0) * i / n, y0 + (y1 - y0) * j / n):
                return None
    out = []
    for b, rings in land:
        if b[2] < x0 or b[0] > x1 or b[3] < y0 or b[1] > y1:
            continue
        for r in rings:
            c = _clip_ring(r, x0, y0, x1, y1)
            if len(c) > 2:
                out.append(c)
    return out


def _geo():
    if "g" not in _GEO:
        from pathlib import Path
        root = Path(__file__).resolve().parent
        d = json.loads((root / "preview/ramp-finder/map/geo-hi.json").read_text())
        q = d["q"]

        def dec(ring):
            pts, x, y = [], ring[0], ring[1]
            pts.append((x / q, y / q))
            for i in range(2, len(ring) - 1, 2):
                x += ring[i]; y += ring[i + 1]
                pts.append((x / q, y / q))
            return pts
        water = [[dec(r) for r in feat] for feat in d["water"]]
        rivers = [[dec(r) for r in feat] for feat in d["rivers"]]
        _GEO["g"] = (water, rivers)
        _GEO["coords"] = json.loads((root / "stations/byl_station_coords.json").read_text())
    return _GEO["g"]


def _mi(a, b, c, d):
    import math
    p = math.pi / 180
    x = math.sin((c - a) * p / 2) ** 2 + math.cos(a * p) * math.cos(c * p) * math.sin((d - b) * p / 2) ** 2
    return 3958.8 * 2 * math.asin(math.sqrt(x))


def locator_points(site, rec, cz):
    """Ramp plus every station this page actually uses (reviewed and publishable only)."""
    _geo()
    co = _GEO["coords"]
    pts = []
    def add(role, sid, why):
        c = co.get(sid)
        if c and all(p[1] != sid for p in pts):
            pts.append((role, sid, c["name"], c["lat"], c["lon"], why, c["source"]))
    if byl_data.water_ok(site):
        for c in site["stations"]:
            if c["publishable"] and c["source"] == "USGS":
                add("G", c["id"], {"lake_elevation": "lake elevation", "water_temp": "water temperature", "downstream_river_flow": "flow below the dam",
                                    "river_stage_flow": "river gauge"}.get(c["type"], c["type"]))
            elif c["publishable"] and c["type"] == "tide_predictions" and site["tide_policy"] == "predictions":
                add("T", c["id"], "tide predictions")
        for x in byl_data.accepted(cz.get("water")):
            add("N", x["id"], "observed water level and temperature")
    for x in byl_data.accepted(cz.get("wind")):
        add("W", x["id"], "observed wind")
    return pts


def locator_svg(site, rec, cz, W=330, H=210):
    import math
    if rec.get("la") is None:
        return ""
    pts = locator_points(site, rec, cz)
    if not pts:
        return ""
    water, rivers = _geo()
    lats = [rec["la"]] + [p[3] for p in pts]
    lons = [rec["lo"]] + [p[4] for p in pts]
    k = math.cos(rec["la"] * math.pi / 180)
    cy, cx = (max(lats) + min(lats)) / 2, (max(lons) + min(lons)) / 2
    span_y = max((max(lats) - min(lats)) * 1.35, 0.03)
    span_x = max((max(lons) - min(lons)) * 1.35 * k, 0.03)
    if span_x / span_y < W / H:
        span_x = span_y * W / H
    else:
        span_y = span_x * H / W
    x0, x1 = cx - span_x / k / 2, cx + span_x / k / 2
    y0, y1 = cy - span_y / 2, cy + span_y / 2
    X = lambda lo: (lo - x0) / (x1 - x0) * W
    Y = lambda la: (y1 - la) / (y1 - y0) * H

    def path(rings, close):
        out = []
        for r in rings:
            if max(p[0] for p in r) < x0 or min(p[0] for p in r) > x1 or max(p[1] for p in r) < y0 or min(p[1] for p in r) > y1:
                continue
            seg, last = [], None
            for lo, la in r:
                q = (round(X(lo), 1), round(Y(la), 1))
                if last is None or abs(q[0] - last[0]) + abs(q[1] - last[1]) >= 1.2:
                    seg.append(q); last = q
            if len(seg) > 2:
                out.append("M" + " L".join("%g,%g" % s for s in seg) + ("Z" if close else ""))
        return "".join(out)
    wpath = "".join(path(f, True) for f in water)
    rpath = "".join(path(f, False) for f in rivers)
    lpath = ""
    if cz:
        # Coastal and estuarine ramps: the inland TIGER layer has no sounds or ocean, so it would paint
        # open water as land. Use the NOAA ENC shoreline when it covers the whole frame, else no outline.
        wpath = rpath = ""
        land = enc_land(x0, y0, x1, y1)
        if land is not None:
            lpath = path(land, True) or "M0,0"
            rpath = ""
    marks = ""
    for role, sid, name, la, lo, why, srcn in pts:
        x, y = X(lo), Y(la)
        marks += (f'<g class="lm lm-{role}"><circle cx="{x:.1f}" cy="{y:.1f}" r="9"/><text x="{x:.1f}" y="{y+4:.1f}" text-anchor="middle">{role}</text></g>')
    rx, ry = X(rec["lo"]), Y(rec["la"])
    marks += f'<g class="lm-ramp"><path d="M{rx:.1f},{ry:.1f} l-7,-14 a8,8 0 1 1 14,0z"/><circle cx="{rx:.1f}" cy="{ry-17:.1f}" r="3"/></g>'
    scale_mi = max(1, round(span_x * 69.0 / 4))
    sb = scale_mi / (span_x * 69.0) * W
    svg = (f'<svg class="chart loc" viewBox="0 0 {W} {H}" role="img" aria-label="Map of the ramp and the {len(pts)} stations this page uses">'
           + (f'<rect width="{W}" height="{H}" class="loc-sea"/><path class="loc-enc" fill-rule="evenodd" d="{lpath}"/>' if lpath else
              f'<rect width="{W}" height="{H}" class="{"loc-land" if wpath else "loc-plain"}"/><path class="loc-water" d="{wpath}"/><path class="loc-river" d="{rpath}"/>')
           + f'{marks}'
           f'<line class="loc-sb" x1="10" x2="{10+sb:.1f}" y1="{H-10}" y2="{H-10}"/><text x="10" y="{H-14}">{scale_mi} mi</text>'
           f'<text x="{W-8}" y="14" text-anchor="end">N ↑</text></svg>')
    legend = "".join(f'<li><span class="lm lm-{r}"><b>{r}</b></span> {E(why.capitalize())}: {E(srcn)} {E(sid)} · {E(n)} · {_mi(rec["la"], rec["lo"], la, lo):.1f} mi</li>'
                     for r, sid, n, la, lo, why, srcn in pts)
    return (f'<section class="card rd"><div class="top"><span class="lbl">Where these readings come from</span>{tag("comp")}</div>{svg}'
            f'<ul class="loc-leg">{legend}</ul><p class="note">Pin is the ramp; positions and distances are to scale. '
            + ("Water outlines: U.S. Census TIGER/Line, simplified. " if wpath else
               "Shoreline: NOAA ENC land areas (Office of Coast Survey, ENC Direct), simplified; not a chart. " if lpath else
               "Coastline not drawn: neither our inland water layer nor our NOAA ENC shoreline covers this whole area. ")
            + 'Illustration, not for navigation; use the NOAA chart for that.</p></section>')
