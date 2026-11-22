"""Ramp Finder — private, cookie-gated data preview (Ed t415u).

Server-rendered HTML for /preview/ramps and /preview/ramps/<id>.
No public nav, no sitemap, no interactive map, no paid APIs.
"""
from __future__ import annotations

import html
import json
from pathlib import Path
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parent
DATA_PATH = ROOT / "preview" / "ramp-finder" / "inventory.json"
CSS_PATH = ROOT / "preview" / "ramp-finder" / "ramps.css"

PROTECTED_PATHS = (
    "index.html",
    "brief.py",
    "brief.html",
    "wind.html",
    "radar.html",
    "catch-wall.html",
    "catch_wall.py",
    "conditions.py",
    "freshwater.py",
    "lake.html",
)

AREAS = [
    ("", "All areas"),
    ("crystal-coast", "Crystal Coast"),
    ("falls-lake", "Falls Lake"),
    ("jordan-lake", "Jordan Lake"),
    ("neuse-river", "Neuse River"),
]

FLAG_FILTERS = [
    ("limited", "Show all limited-access launches"),
    ("camper_only", "Camper-only"),
    ("non_gas_only", "Non-gas only"),
    ("size_limited", "Size-limited"),
    ("no_parking", "No parking"),
    ("needs_review", "Show needs-review entries"),
]

_THEME_BOOT = (
    '<script>(function(){try{var q=new URLSearchParams(location.search).get("theme");'
    'var t=q||localStorage.getItem("coastalBrief.theme");'
    'if(t!=="light"&&t!=="dark")t=matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light";'
    'document.documentElement.setAttribute("data-theme",t)}catch(e){}})();</script>'
)

_THEME_TOGGLE = """<script>
(function(){
  var btn=document.getElementById("theme-toggle");
  if(!btn) return;
  function cur(){return document.documentElement.getAttribute("data-theme")==="dark"?"dark":"light"}
  function sync(){
    var t=cur();
    btn.setAttribute("aria-pressed", t==="dark"?"true":"false");
    btn.setAttribute("aria-label", t==="dark"?"Switch to light mode":"Switch to dark mode");
    btn.textContent=t==="dark"?"Light mode":"Dark mode";
  }
  sync();
  btn.addEventListener("click", function(){
    var n=cur()==="dark"?"light":"dark";
    document.documentElement.setAttribute("data-theme", n);
    try{localStorage.setItem("coastalBrief.theme",n)}catch(e){}
    sync();
  });
})();
</script>"""


def esc(s) -> str:
    return html.escape("" if s is None else str(s), quote=True)


def css_bytes() -> bytes:
    return CSS_PATH.read_bytes()


def load_data() -> dict:
    return json.loads(DATA_PATH.read_text())


def records(data=None) -> list:
    return (data or load_data())["records"]


def by_id(rid: str, data=None):
    for rec in records(data):
        if rec["id"] == rid:
            return rec
    return None


def _qs(params: dict) -> str:
    items = []
    for k, v in params.items():
        if v in ("", None, False, 0, "0"):
            continue
        items.append((k, v if isinstance(v, str) else "1" if v is True else str(v)))
    return urlencode(items)


def _list_url(params: dict) -> str:
    q = _qs(params)
    return "/preview/ramps?" + q if q else "/preview/ramps"


def parse_filters(q: dict) -> dict:
    def first(name, default=""):
        vals = q.get(name)
        if not vals:
            return default
        return (vals[0] if isinstance(vals, list) else vals) or default

    region = first("region")
    if region not in {a for a, _ in AREAS}:
        region = ""
    flags = {key: first(key) in ("1", "true", "on", "yes") for key, _ in FLAG_FILTERS}
    return {"q": first("q").strip(), "region": region, **flags, "theme": first("theme")}


def matches_search(rec, term: str) -> bool:
    if not term:
        return True
    hay = " ".join([
        rec.get("official_name") or "",
        rec.get("display_name") or "",
        rec.get("alias") or "",
        rec.get("body_of_water") or "",
        rec.get("body_of_water_note") or "",
        rec.get("county") or "",
        rec.get("city") or "",
        rec.get("area_label") or "",
        rec.get("street") or "",
        rec.get("managing_agency") or "",
    ]).lower()
    return term.lower() in hay


def visible_sets(data, filters: dict):
    term = filters.get("q") or ""
    region = filters.get("region") or ""
    general, limited, review = [], [], []
    for rec in records(data):
        if region and rec["area"] != region:
            continue
        if not matches_search(rec, term):
            continue
        cls = rec["listing_class"]
        flags = rec.get("flags") or {}
        flag_hit = any(filters.get(k) and flags.get(k) for k in ("camper_only", "non_gas_only", "size_limited", "no_parking"))
        if cls == "general":
            general.append(rec)
        elif cls == "limited":
            if filters.get("limited") or flag_hit:
                limited.append(rec)
        elif cls == "needs_review":
            if filters.get("needs_review") or flag_hit:
                review.append(rec)
    return general, limited, review


def hidden_counts(data, filters: dict):
    """How many limited / needs-review records match search+region but are hidden by filters."""
    term = filters.get("q") or ""
    region = filters.get("region") or ""
    hid_lim = hid_rev = 0
    shown_g, shown_l, shown_r = visible_sets(data, filters)
    shown_ids = {r["id"] for r in shown_g + shown_l + shown_r}
    for rec in records(data):
        if rec["id"] in shown_ids:
            continue
        if region and rec["area"] != region:
            continue
        if not matches_search(rec, term):
            continue
        if rec["listing_class"] == "limited":
            hid_lim += 1
        elif rec["listing_class"] == "needs_review":
            hid_rev += 1
    return hid_lim, hid_rev


def _shell(title: str, body: str, skip: str = "Skip to the ramp list") -> str:
    css_text = css_bytes().decode("utf-8")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<meta name="theme-color" content="#071C29">
<title>{esc(title)}</title>
<link rel="icon" href="/favicon.ico?v=20261121" sizes="48x48">
<link rel="icon" href="/branding/favicon.svg?v=20261121" type="image/svg+xml">
<link rel="apple-touch-icon" href="/apple-touch-icon.png?v=20261121" sizes="180x180">
<link rel="preload" href="/fonts/source-sans-3-var.woff2" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="/fonts/fraunces-var.woff2" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="/fonts/fraunces-italic-var.woff2" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="/fonts/barlow-condensed-600.woff2" as="font" type="font/woff2" crossorigin>
<style>{css_text}</style>
{_THEME_BOOT}
</head>
<body class="rf-body">
<a class="skip" href="#main">{esc(skip)}</a>
<p class="rf-banner">Private preview · this browser only · not public · not indexed</p>
<header class="rf-top">
  <div class="rf-top-row">
    <a class="rf-brand" href="/preview/ramps">The Coastal Brief</a>
    <button type="button" class="theme-toggle" id="theme-toggle">Dark mode</button>
  </div>
  <nav class="rf-nav" aria-label="Preview">
    <a href="/preview">Preview hub</a>
    <a href="/preview/ramps" aria-current="page">Ramp Finder</a>
  </nav>
</header>
<main class="rf-main" id="main">
{body}
<p class="rf-sign">Know the Water. Live the Coast.</p>
</main>
{_THEME_TOGGLE}
</body>
</html>
"""


def _facility(rec, key, label=None):
    val = rec.get(key)
    if val in (None, "", "not stated"):
        return None
    return (label or key, val)


def facility_rows(rec):
    rows = []
    mapping = [
        ("lanes", "Launch lanes"),
        ("trailer_parking", "Trailer parking"),
        ("trailer_parking_ada", "Trailer parking (ADA)"),
        ("nontrailer_parking", "Vehicle parking"),
        ("nontrailer_parking_ada", "Vehicle parking (ADA)"),
        ("parking_surface", "Parking surface"),
        ("fixed_docks", "Fixed docks"),
        ("floating_docks", "Floating docks"),
        ("courtesy_docks", "Courtesy docks"),
        ("restrooms", "Restrooms"),
        ("lighting", "Lighting"),
        ("fishing_pier", "Fishing pier"),
        ("ada_paved_walkway", "ADA paved walkway"),
        ("ada_dock_handrails", "ADA dock handrails"),
        ("salinity_class", "Salinity"),
        ("fishing_water_designation", "Fishing-water designation"),
    ]
    for key, label in mapping:
        item = _facility(rec, key, label)
        if item:
            rows.append(item)
    return rows


def notice_html(notices) -> str:
    parts = []
    for n in notices or []:
        cat = n.get("category") or "general_information"
        srcs = []
        for s in n.get("sources") or []:
            srcs.append(f'<li><a href="{esc(s["url"])}" rel="noopener noreferrer">{esc(s.get("label") or s["url"])}</a></li>')
        src_html = f'<ul class="sources">{"".join(srcs)}</ul>' if srcs else ""
        as_of = n.get("as_of") or ""
        parts.append(
            f'<aside class="notice notice-{esc(cat)}" data-notice-category="{esc(cat)}">'
            f'<span class="nl">{esc(n.get("label") or cat)}</span>'
            f'<p>{esc(n.get("text") or "")}</p>'
            f'{src_html}'
            f'<p class="checked">Checked {esc(as_of)}.</p>'
            f'</aside>'
        )
    return "\n".join(parts)


def badges_for(rec) -> str:
    bits = []
    for n in rec.get("notices") or []:
        cat = n.get("category")
        if cat == "current_dated_notice":
            bits.append('<span class="badge badge-notice">Current dated notice</span>')
        elif cat == "standing_caution":
            bits.append('<span class="badge badge-caution">Standing caution</span>')
    flags = rec.get("flags") or {}
    if rec["listing_class"] == "limited":
        bits.append('<span class="badge badge-limited">Limited access</span>')
    if rec["listing_class"] == "needs_review":
        bits.append('<span class="badge badge-review">Needs review</span>')
    if flags.get("camper_only"):
        bits.append('<span class="badge badge-limited">Camper-only</span>')
    if flags.get("non_gas_only"):
        bits.append('<span class="badge badge-limited">Non-gas only</span>')
    if flags.get("size_limited"):
        note = flags.get("size_limit_note") or "Size-limited"
        bits.append(f'<span class="badge badge-limited">{esc(note)}</span>')
    if flags.get("no_parking"):
        bits.append('<span class="badge badge-limited">No parking</span>')
    if flags.get("limited_trailer_parking"):
        bits.append('<span class="badge badge-info">Limited trailer parking</span>')
    if flags.get("fee_conflict"):
        bits.append('<span class="badge badge-caution">Fee information conflicts</span>')
    if flags.get("hours_uncertain"):
        bits.append('<span class="badge badge-caution">Hours need clarification</span>')
    if rec.get("county") == "Jones" or "Jones" in (rec.get("county") or ""):
        bits.append('<span class="badge badge-county">Jones County</span>')
    if not bits:
        return ""
    return '<div class="badges">' + "".join(bits) + "</div>"


def amenity_line(rec) -> str:
    bits = []
    if rec.get("lanes") not in (None, "", "not stated"):
        bits.append(f'{rec["lanes"]} lane' + ("s" if rec["lanes"] != 1 else ""))
    if rec.get("trailer_parking") not in (None, "", "not stated"):
        bits.append(f'{rec["trailer_parking"]} trailer spaces')
    if rec.get("flags", {}).get("limited_trailer_parking") and not bits:
        bits.append("Parking for 3 vehicles with trailers")
    return " · ".join(str(b) for b in bits)


def card_html(rec) -> str:
    amen = amenity_line(rec)
    amen_html = f'<span class="amen">{esc(amen)}</span>' if amen else ""
    county = rec.get("county") or ""
    loc = ", ".join(p for p in (rec.get("city"), county and f"{county} County", rec.get("area_label")) if p)
    return (
        f'<li><a class="ramp-card" href="/preview/ramps/{esc(rec["id"])}">'
        f'<h3>{esc(rec["display_name"])}</h3>'
        f'<span class="meta">{esc(rec.get("body_of_water") or "")}'
        f'{" — " + esc(loc) if loc else ""}</span>'
        f'{amen_html}'
        f'{badges_for(rec)}'
        f'</a></li>'
    )


def lake_context_html(data, area: str) -> str:
    ctx = (data.get("meta") or {}).get("lake_level_context") or {}
    key = {"falls-lake": "falls_lake", "jordan-lake": "jordan_lake"}.get(area)
    if not key or key not in ctx:
        return ""
    block = ctx[key]
    return (
        f'<aside class="context" data-notice-category="general_information">'
        f'<strong>{esc(ctx.get("label") or "Water-level context (not a closure)")}</strong>'
        f'<p>USGS {esc(block.get("usgs_site"))}: {esc(block.get("reading"))} at {esc(block.get("time"))}. '
        f'Guide curve {esc(block.get("guide_curve"))} ({esc(block.get("departure"))}). '
        f'{esc(block.get("usace_weekly"))}.</p>'
        f'<p>{esc(ctx.get("note") or "")}</p>'
        f'</aside>'
    )


def render_list(data, filters: dict) -> str:
    general, limited, review = visible_sets(data, filters)
    hid_lim, hid_rev = hidden_counts(data, filters)
    q = filters.get("q") or ""
    region = filters.get("region") or ""

    hidden = []
    if hid_lim:
        hidden.append(f"{hid_lim} limited-access")
    if hid_rev:
        hidden.append(f"{hid_rev} needs-review")
    hidden_note = ""
    if hidden:
        hidden_note = (
            f'<p class="hidden-note">{esc(" and ".join(hidden))} '
            f'{"entry is" if (hid_lim + hid_rev) == 1 else "entries are"} hidden. '
            f'Use the optional filters to show camper-only, non-gas, size-limited, no-parking, or needs-review sites.</p>'
        )

    chips = []
    base = {k: filters[k] for k in ("q", "limited", "camper_only", "non_gas_only", "size_limited", "no_parking", "needs_review") if filters.get(k)}
    for slug, label in AREAS:
        p = dict(base)
        if slug:
            p["region"] = slug
        current = ' aria-current="page"' if slug == region else ""
        chips.append(f'<a href="{esc(_list_url(p))}"{current}>{esc(label)}</a>')

    checks = []
    for key, label in FLAG_FILTERS:
        on = " checked" if filters.get(key) else ""
        checks.append(
            f'<label><input type="checkbox" name="{esc(key)}" value="1"{on}> {esc(label)}</label>'
        )

    region_input = f'<input type="hidden" name="region" value="{esc(region)}">' if region else ""
    ctx = ""
    if region in ("falls-lake", "jordan-lake"):
        ctx = lake_context_html(data, region)
    elif not region:
        ctx = lake_context_html(data, "falls-lake") + lake_context_html(data, "jordan-lake")

    def section(title, lead, rows, kind):
        if not rows:
            return ""
        items = "".join(card_html(r) for r in rows)
        return (
            f'<section class="rf-section" data-section="{esc(kind)}">'
            f'<h2>{esc(title)} ({len(rows)})</h2>'
            f'<p class="section-lead">{esc(lead)}</p>'
            f'<ul class="list">{items}</ul>'
            f'</section>'
        )

    body_sections = []
    body_sections.append(section(
        "Public trailered motorboat launches",
        "Verified public launches suitable for general use. Standing cautions and limited parking stay in this list when official sources describe them.",
        general,
        "general",
    ))
    body_sections.append(section(
        "Limited access",
        "Verified launches with a hard restriction: camper-only, non-gas only, size-limited, or no parking. Hidden from the default view.",
        limited,
        "limited",
    ))
    body_sections.append(section(
        "Needs review",
        "Official sources are incomplete, conflicting, or do not confirm a general public trailer ramp. Hidden from the default view.",
        review,
        "needs_review",
    ))
    if not (general or limited or review):
        body_sections.append('<p class="empty" data-empty="ramps">No ramps match those filters.</p>')

    shown = len(general) + len(limited) + len(review)
    return _shell("Ramp Finder — private preview", f"""
<p class="kicker">Private data preview</p>
<h1>Ramp Finder</h1>
<p class="lead">Crystal Coast, Falls Lake, Jordan Lake, and the Neuse River. Official sources only, checked Nov 22, 2026. This is not a live open/closed board.</p>
<form class="filters" id="filters" method="get" action="/preview/ramps" role="search">
  {region_input}
  <label class="q-lab" for="q">Search by name, body of water, or region</label>
  <input type="search" id="q" name="q" value="{esc(q)}" placeholder="Search ramps" autocomplete="off">
  <div class="regions" aria-label="Region">{''.join(chips)}</div>
  <fieldset class="opt-filters">
    <legend>Optional filters</legend>
    <div class="opt-row">{''.join(checks)}</div>
  </fieldset>
  <div class="actions">
    <button type="submit">Apply filters</button>
    <button type="reset" onclick="location.href='/preview/ramps'; return false;">Reset</button>
  </div>
</form>
<p class="count">Showing {shown} {"ramp" if shown == 1 else "ramps"}{f" in {dict(AREAS).get(region)}" if region else ""}.</p>
{hidden_note}
{ctx}
{''.join(body_sections)}
""")


def fees_html(rec) -> str:
    fees = rec.get("fees") or {}
    if fees.get("conflict"):
        entries = []
        for e in fees.get("entries") or []:
            entries.append(
                '<div class="fee-entry">'
                f'<div class="amount">{esc(e.get("amount") or "")}</div>'
                f'<p>{esc(e.get("also") or "")}</p>'
                f'<p><a href="{esc(e.get("source_url") or "")}" rel="noopener noreferrer">{esc(e.get("source_label") or "Official source")}</a>'
                f' · checked {esc(e.get("date_checked") or "")}</p>'
                "</div>"
            )
        return (
            '<section class="conflict" data-fee-conflict="true">'
            "<h3>Official fee information conflicts</h3>"
            f'<p>{esc(fees.get("summary") or "")}</p>'
            + "".join(entries)
            + "</section>"
        )
    summary = fees.get("summary") or "not stated"
    return f'<h2>Fees</h2><p>{esc(summary)}</p>'


def hours_html(rec) -> str:
    hours = rec.get("hours") or {}
    if hours.get("conflict"):
        entries = []
        for e in hours.get("entries") or []:
            entries.append(
                '<div class="hours-entry">'
                f'<p>{esc(e.get("text") or "")}</p>'
                f'<p><a href="{esc(e.get("source_url") or "")}" rel="noopener noreferrer">{esc(e.get("source_label") or "Official source")}</a>'
                f' · checked {esc(e.get("date_checked") or "")}</p>'
                "</div>"
            )
        return (
            '<section class="conflict" data-hours-conflict="true">'
            "<h3>Official hours information conflicts</h3>"
            f'<p>{esc(hours.get("summary") or "")}</p>'
            + "".join(entries)
            + "</section>"
        )
    return f'<h2>Hours</h2><p>{esc(hours.get("summary") or "not stated")}</p>'


def directions_html(rec) -> str:
    d = rec.get("directions") or {}
    apple = d.get("apple_url") or ""
    google = d.get("google_url") or ""
    if not apple or not google:
        return '<p class="caveat">Directions are not published; official coordinates and a verified address were not found.</p>'
    if d.get("mode") == "coordinates":
        how = (
            f'Directions use official coordinates '
            f'({esc(d.get("latitude"))}, {esc(d.get("longitude"))})'
            f'{": " + esc(rec.get("coordinates_source")) if rec.get("coordinates_source") else "."}'
        )
    else:
        how = f'Directions use the verified address {esc(d.get("address") or "")}.'
    caveat = d.get("caveat") or ""
    return (
        "<h2>Directions</h2>"
        f'<p>{how}</p>'
        f'{f"<p class=\"caveat\">{esc(caveat)}</p>" if caveat else ""}'
        '<div class="dirs">'
        f'<a href="{esc(apple)}" rel="noopener noreferrer">Apple Maps</a>'
        f'<a href="{esc(google)}" rel="noopener noreferrer">Google Maps</a>'
        "</div>"
    )


def render_detail(data, rec) -> str:
    loc_bits = [rec.get("city"), (rec.get("county") + " County") if rec.get("county") else "", rec.get("area_label")]
    loc = ", ".join(p for p in loc_bits if p)
    rows = facility_rows(rec)
    facts = ""
    if rows:
        tr = "".join(f"<tr><th>{esc(k)}</th><td>{esc(v)}</td></tr>" for k, v in rows)
        facts = f'<h2>Facilities</h2><table class="facts">{tr}</table>'
    sources = []
    for s in rec.get("sources") or []:
        sources.append(
            f'<li><a href="{esc(s["url"])}" rel="noopener noreferrer">{esc(s.get("label") or s["url"])}</a>'
            f'<div class="checked">{esc(s.get("detail") or "")} Checked {esc(s.get("date_checked") or "")}.</div></li>'
        )
    alias = f'<p class="meta">Also recorded as {esc(rec["alias"])}.</p>' if rec.get("alias") else ""
    restrict = rec.get("restriction_notes") or ""
    restrict_html = f"<h2>Restrictions</h2><p>{esc(restrict)}</p>" if restrict and restrict != "not stated" else ""
    notes = rec.get("notes") or ""
    notes_html = f"<h2>Notes</h2><p>{esc(notes)}</p>" if notes else ""
    status = rec.get("site_status_official") or ""
    status_html = ""
    if status:
        status_html = (
            "<h2>Official status wording</h2>"
            f'<p>{esc(rec.get("site_status_note") or "")}</p>'
            f'<p>Recorded official wording: {esc(status)}</p>'
        )
    ctx = ""
    if rec["area"] in ("falls-lake", "jordan-lake"):
        ctx = lake_context_html(data, rec["area"])
    title = f'{rec["display_name"]} — Ramp Finder (private preview)'
    return _shell(title, f"""
<p class="crumb"><a href="/preview/ramps">Ramp Finder</a> / {esc(rec["display_name"])}</p>
<p class="kicker">{esc(rec.get("area_label") or "")}</p>
<h1>{esc(rec["display_name"])}</h1>
<p class="lead">{esc(rec.get("body_of_water") or "")}{" — " + esc(rec.get("body_of_water_note")) if rec.get("body_of_water_note") and rec.get("body_of_water_note") != rec.get("body_of_water") else ""}</p>
<p class="meta">{esc(loc)}</p>
<p class="meta">{esc(rec.get("managing_agency") or "")}{" · " + esc(rec.get("program")) if rec.get("program") else ""}</p>
{alias}
{badges_for(rec)}
{notice_html(rec.get("notices"))}
{ctx}
{fees_html(rec)}
{hours_html(rec)}
{restrict_html}
{facts}
{directions_html(rec)}
{status_html}
{notes_html}
<h2>Official sources</h2>
<ul class="sources">{''.join(sources)}</ul>
<p class="checked">Date checked: {esc(rec.get("date_checked") or "")}. This page does not confirm that a ramp is open right now.</p>
""", skip="Skip to ramp details")


def resolve_request(path: str, query: dict):
    raw = path.rstrip("/") or "/preview/ramps"
    if raw in ("/preview/ramps.css",):
        return 200, "text/css; charset=utf-8", css_bytes()
    data = load_data()
    if raw in ("/preview/ramps.json",):
        return 200, "application/json; charset=utf-8", json.dumps(data, ensure_ascii=False)
    if raw in ("/preview/ramps",):
        return 200, "text/html; charset=utf-8", render_list(data, parse_filters(query or {}))
    prefix = "/preview/ramps/"
    if raw.startswith(prefix):
        rid = raw[len(prefix):].strip("/")
        rec = by_id(rid, data)
        if not rec:
            return 404, "text/plain", "not found"
        return 200, "text/html; charset=utf-8", render_detail(data, rec)
    return 404, "text/plain", "not found"
