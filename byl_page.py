"""Before You Launch page (Phase 3B, private preview only). Renders Summer's approved layout from reviewed
records: the shell (access, regulations, computed sun and moon, links) is server-rendered with no network
calls; live readings arrive from the .json endpoint and replace skeleton cards. Every card says what kind
of value it is, where it came from and when. Nothing here states or implies that launching is safe."""
from __future__ import annotations

import html
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
         'info': '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5v.1"/>'}
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


def card_html(c):
    """One reading card. Unavailable cards never carry a value."""
    k = c["kind"]
    if k == "unav":
        return (f'<section class="card un" data-card="{E(c["key"])}"><div class="top" style="display:flex;justify-content:space-between;align-items:center">'
                f'<span class="lbl">{E(c["label"])}</span>{tag("unav")}</div><p>{E(c["note"])}</p>{src(c["source"]) if c.get("source") else ""}</section>')
    body = ""
    if c["key"] == "forecast":
        body = '<ul class="fc">' + "".join(f'<li><b>{E(p["name"])}</b>{E(p["temp"])}°{E(p["unit"])} · {E(p["short"])}<br>Wind {E(p["wind"])}</li>' for p in c["periods"]) + "</ul>"
    elif c["key"] == "alerts":
        if not c["alerts"]:
            return (f'<section class="card none" data-card="alerts"><span style="color:var(--ink2)">{ic("info")}</span><p><b>No NWS alert listed for this point.</b> '
                    f'{E(c["when"])}. <i>An empty list is not an all-clear.</i></p></section>')
        items = "".join(f'<li><b>{E(a["event"])}</b>: {E(a["headline"])}</li>' for a in c["alerts"])
        return (f'<section class="card adv" data-card="alerts" role="alert"><div class="ico">{ic("alert")}</div><div><div class="eyebrow">Official notice · National Weather Service</div>'
                f'<h3>{E(c["alerts"][0]["event"])}{" and more" if len(c["alerts"]) > 1 else ""}</h3><ul>{items}</ul>{src(c["source"], c["when"])}'
                f'<a class="lk2" href="{E(c.get("link") or "https://www.weather.gov/")}" rel="noopener">Read the full NWS text{ic("ext")}</a></div></section>')
    elif c["key"] == "tide":
        body = '<ul class="tides">' + "".join(f'<li><b>{E(e["type"])}</b> {E(e["day"])} {E(e["time"])} · {E(e["ft"])} ft</li>' for e in c["events"]) + "</ul>"
    elif "value" in c:
        extra = ""
        if c.get("vs_guide") is not None:
            extra = f'<span class="delta">{c["vs_guide"]:+.2f} ft vs guide curve {E(c["guide"])} ft</span>'
        elif c.get("trend"):
            extra = f'<span class="delta">{E(c["trend"])} over 6 h</span>'
        v = c["value"]
        v = int(v) if float(v).is_integer() and c.get("unit") in ("cfs", "°F") else v
        body = f'<div class="val"><span class="big">{E(v)}<small>{E(c["unit"])}</small></span>{extra}</div>'
        if c.get("vs_guide") is not None or c.get("trend"):
            body += f'<p class="note">The {"guide difference" if c.get("vs_guide") is not None else "trend"} is {tag("comp")} from the readings.</p>'
    note = f'<p class="note">{E(c["note"])}</p>' if c.get("note") else ""
    stale = f'<p class="note"><b>Stale:</b> this is the latest value available and it is older than usual for this source.</p>' if k == "stale" else ""
    return (f'<section class="card rd" data-card="{E(c["key"])}"><div class="top"><span class="lbl">{E(c["label"])}</span>{tag(k)}</div>{body}{stale}{note}'
            f'{src(c["source"], c["when"])}</section>')


def fragments(data):
    out = {k: (sun_card(c) if k == "sun" else card_html(c)) for k, c in data["cards"].items()}
    return out


def _skel(key, label):
    return f'<section class="card rd skel" data-card="{key}" aria-busy="true"><div class="top"><span class="lbl">{E(label)}</span><span class="tag">Loading</span></div></section>'


def slots(site):
    """Card slots the page expects, in order, by section. Only reviewed publishable stations get a slot."""
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
    return water


def access_card(rec):
    st = rec.get("st") or "not_stated"
    unc = st in ("not_stated", "unknown", "")
    icon = ic("q") if unc else ic("rec")
    kv = "".join(f"<dt>{E(a)}</dt><dd>{E(b)}</dd>" for a, b in (("Launch", rec.get("tyl")), ("Fees", rec.get("fs") or "Not stated"),
                                                                     ("Notes", rec.get("rx"))) if b)
    return (f'<section class="card"><div class="acc"><div class="ico {"unc" if unc else "lo"}">{icon}</div><div><div class="row"><span class="lbl">Access</span>{tag("rec")}</div>'
            f'<h3>{E(rec.get("stf") or rec.get("stl") or "Status not stated")}</h3><p>{E(rec.get("sd") or "")}</p></div></div>'
            f'<p class="src" style="margin-top:10px"><span><b>{E(rec.get("cs") or "Ramp inventory")}</b> · recorded {E(rec.get("sa"))} · not a live check</span></p>'
            f'<details class="more"><summary>Ramp details</summary><dl class="kv">{kv}</dl></details></section>')


def regs_card(site):
    r = site["regs"]
    links = "".join(f'<a class="lk" href="{E(l["url"])}" rel="noopener"><span class="ico">{ic("book")}</span><span><small>{E(l["agency"])}</small>{E(l["label"])}</span>{ic("ext")}</a>' for l in r["links"])
    why = ""
    if r["jurisdiction"] in ("unresolved", "joint"):
        why = (f'<p class="regs-why">{"This ramp sits near the line between coastal, joint and inland fishing waters" if r["jurisdiction"] == "unresolved" else "These are joint fishing waters"}, '
               f'so both agencies&rsquo; rules may apply. Check the <a href="{E(r["boundary_map"])}" rel="noopener">official boundary map</a> for where you fish.</p>')
    return sec("Fishing regulations", f'<div class="links">{links}</div>{why}', "official links")


def sun_card(c):
    if c["kind"] == "unav":
        return card_html(c)
    k = (c.get("moon_pct") or 0) / 100
    return (f'<section class="card rd" data-card="sun"><div class="top"><span class="lbl">Sun &amp; moon · {E(c["when"])}</span>{tag("comp")}</div>'
            f'<div style="display:flex;gap:14px;align-items:center;flex-wrap:wrap"><div><b>Sunrise</b> {E(c["sunrise"])}<br><b>Sunset</b> {E(c["sunset"])}</div>'
            f'<div style="display:flex;gap:8px;align-items:center">{moon_svg(k)}<div><b>{E(c["moon_pct"])}% lit</b><br>{E(c["moon_phase"])}</div></div></div>'
            f'{src(c["source"])}</section>')


def directions(rec):
    if rec.get("la") is not None:
        return "https://www.google.com/maps/dir/?api=1&destination=%.6f,%.6f" % (rec["la"], rec["lo"]), ("official map pin" if rec.get("pr") == "exact" else "approximate pin")
    return "https://www.google.com/maps/dir/?api=1&destination=" + quote(rec.get("ad") or rec.get("n")), "official address"


THEME_JS = "try{var t=localStorage.getItem('coastalBrief.theme');if(t==='dark'||(!t&&matchMedia('(prefers-color-scheme: dark)').matches))document.documentElement.classList.add('dark')}catch(e){}"


def render(site_id, sites=None, records=None, now=None):
    sites = sites or byl_data.load_sites()
    records = records or byl_data.load_records()
    site, rec = sites[site_id], records[site_id]
    water = slots(site)
    sun = byl_data.sun_moon(rec, (now or byl_data.datetime.now(byl_data.ET)).date() if now else None)
    durl, dsub = directions(rec)
    wc = {"reservoir": "Reservoir", "natural_lake": "Natural lake", "river": "River", "estuary_wind_driven": "Sound or river estuary (wind-driven water)",
          "tidal_lunar": "Tidal water", "unresolved": "Water type not yet confirmed"}[site["water_class"]]
    body = (f'<div class="head"><div class="eyebrow">Before you launch · {E(rec.get("w") or rec.get("a") or "")}</div><h1>{E(rec["n"])}</h1>'
            f'<p class="sub">{E(wc)} · {E(rec.get("ci"))}, {E(rec.get("co"))} County</p>'
            f'<div class="addr"><span><b>{E(rec.get("ad") or "")}</b><em>{E(dsub)}</em></span><a href="{E(durl)}" rel="noopener">{ic("nav")}Directions</a></div></div>')
    body += sec("Access", access_card(rec))
    body += sec("Official notices", _skel("alerts", "Weather alerts"), "NWS")
    body += sec("Forecast", _skel("forecast", "Forecast near the ramp"), "NWS")
    if water:
        body += sec("Water", "".join(_skel(k, l) for k, l in water if k != "below_dam"))
    elif not byl_data.water_ok(site):
        body += sec("Water", f'<section class="card un withheld"><div class="top">{tag("unav")}</div><h3>Water readings withheld</h3><p>The water type at this ramp is not yet confirmed, so no gauge or tide reading is shown. Forecasts and alerts above do not depend on it.</p></section>')
    else:
        why = {"omit_wind_driven": "Water level here is driven mostly by wind, not by the moon, so tide predictions would mislead.",
               "unavailable_no_same_water_station": "No NOAA tide station on the same water was found within the review distance.",
               "omit_freshwater": "Freshwater: no tides."}.get(site["tide_policy"], "")
        body += sec("Water", f'<section class="card un"><div class="top">{tag("unav")}</div><h3>No reviewed water gauge for this ramp</h3><p>{E(why)} Readings from other water are not shown.</p></section>')
    body += sec("Sun & moon", sun_card(sun))
    body += regs_card(site)
    sec_more = "".join(_skel(k, l) for k, l in water if k == "below_dam")
    body += sec("More", f'<details class="more"{" open" if sec_more else ""}><summary>Below the dam and sources</summary>{sec_more}'
                f'<div class="foot"><b>How to read this page.</b> Each reading shows what kind it is, where it came from and when. This page gathers information; it does not judge whether conditions suit your boat, crew or experience. Missing data is uncertainty, never a sign that conditions are fine. Check official notices and conditions at the ramp.</div></details>')
    bar = (f'<nav class="bar" aria-label="Trip actions"><a class="dir" href="{E(durl)}" rel="noopener">{ic("nav")}<span>Driving directions<small>{E(dsub)}</small></span></a>'
           f'<a class="sm" href="/wind">{ic("wind")}Wind</a><a class="sm" href="/radar">{ic("radar")}Radar</a></nav>')
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
            f'<meta name="robots" content="noindex, nofollow"><title>{E(rec["n"])} · Before you launch · The Coastal Brief</title><script>{THEME_JS}</script>'
            f'<link rel="stylesheet" href="{BASE}/byl.css"></head><body>'
            f'<header class="mast"><a class="back" href="/ramps/map" aria-label="Back to Ramp Finder">{ic("back")}</a><b>The Coastal Brief<br><small>Before you launch</small></b>'
            f'<span class="th" role="group" aria-label="Theme"><button type="button" data-t="auto">Auto</button><button type="button" data-t="light">Light</button><button type="button" data-t="dark">Dark</button></span></header>'
            f'<main id="main" data-id="{E(site_id)}">{body}<p class="sr" aria-live="polite" id="live"></p></main>{bar}<script src="{BASE}/byl.js" defer></script></body></html>')


def index(sites, records):
    rows = "".join(f'<li><a class="lk" href="{BASE}/{E(i)}"><span><small>{E(s["region"] if "region" in s else s.get("area", ""))}</small>{E(records[i]["n"])}</span></a></li>'
                   for i, s in sorted(sites.items(), key=lambda kv: records[kv[0]]["n"]))
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex, nofollow">'
            f'<title>Before you launch · pilot ramps</title><script>{THEME_JS}</script><link rel="stylesheet" href="{BASE}/byl.css"></head><body><main><div class="head"><h1>Before you launch: pilot ramps (private)</h1></div><ul style="list-style:none;padding:0">{rows}</ul></main></body></html>')


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
