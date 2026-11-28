"""Ramp Finder — private, cookie-gated data preview (Ed t415u–t422u).

Server-rendered HTML for /preview/ramps, /preview/ramps/<id>, and the
private interactive map at /preview/ramps/map. No public nav, no sitemap,
no paid APIs. Pins are drawn only from official inventory coordinates.
"""
from __future__ import annotations

import contextvars
import hashlib
import html
import json
import re
from pathlib import Path
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parent
DATA_PATH = ROOT / "preview" / "ramp-finder" / "inventory.json"
CSS_PATH = ROOT / "preview" / "ramp-finder" / "ramps.css"
MAP_JS_PATH = ROOT / "preview" / "ramp-finder" / "ramps-map.js"
MAP_ASSET_SLUGS = frozenset({"map", "map.js", "map.json"})

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


def inventory_facts_digest(data: dict) -> str:
    """Stable hash of inventory facts, classes, directions, notices, and counts.

    Presentation changes must not alter this digest. It is compared to the
    a03bf4c inventory in tests.
    """
    payload = {
        "counts": data.get("counts"),
        "meta": data.get("meta"),
        "records": [{k: rec.get(k) for k in sorted(rec)} for rec in data.get("records") or []],
    }
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def records(data=None) -> list:
    return (data or load_data())["records"]


NEEDS_REVIEW_CLASS = "needs_review"


def is_public_record(rec) -> bool:
    """Verified general and limited-access ramps are public; needs-review is not."""
    return (rec or {}).get("listing_class") != NEEDS_REVIEW_CLASS


def public_records(data=None) -> list:
    return [rec for rec in records(data) if is_public_record(rec)]


def public_index_meta_description(data=None) -> str:
    """Index meta description from verified public counts and covered areas only."""
    n = len(public_records(data))
    return (
        f"Find {n} verified public boat ramps on the Crystal Coast, Falls Lake, "
        "Jordan Lake, and the Neuse River. Official sources only, checked Nov 22, 2026. "
        "Not a live open/closed board."
    )


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


SITE_ORIGIN = "https://thecoastalbrief.com"


# Private statewide preview (Ed t547u) renders through these helpers with its own
# base path. Default None keeps every existing public and preview page unchanged.
STATEWIDE_BASE: contextvars.ContextVar = contextvars.ContextVar("rf_statewide_base", default=None)


def list_base(public: bool = False) -> str:
    override = None if public else STATEWIDE_BASE.get()
    if override:
        return override
    return "/ramps" if public else "/preview/ramps"


def map_base(public: bool = False) -> str:
    return "/ramps/map" if public else "/preview/ramps/map"


def _list_url(params: dict, public: bool = False) -> str:
    q = _qs(params)
    base = list_base(public)
    return base + "?" + q if q else base


def _map_url(params: dict, public: bool = False) -> str:
    q = _qs(params)
    base = map_base(public)
    return base + "?" + q if q else base


def _detail_url(rid: str, public: bool = False) -> str:
    return f"{list_base(public)}/{rid}"


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


MAP_DEFAULT_REGION = "crystal-coast"
MAP_ALL_REGION = "all"


def parse_map_filters(q: dict) -> dict:
    """Map framing: default to Crystal Coast when the visitor has no region or water preference.

    Keep All Areas via ?region=all. The list page still uses parse_filters (default all areas).
    Also accepts ?area= and ?water= as aliases for an existing region key or label.
    """
    def first(name, default=""):
        vals = q.get(name)
        if not vals:
            return default
        return (vals[0] if isinstance(vals, list) else vals) or default

    raw = (first("region") or first("area") or "").strip()
    water = first("water").strip()
    if not raw and water:
        water_key = water.lower().replace(" ", "-")
        keys = {a for a, _ in AREAS if a}
        labels = {label.lower(): key for key, label in AREAS if key}
        if water_key in keys:
            raw = water_key
        elif water.lower() in labels:
            raw = labels[water.lower()]
    filters = parse_filters(q)
    if not raw:
        filters["region"] = MAP_DEFAULT_REGION
    elif raw == MAP_ALL_REGION:
        filters["region"] = ""
    else:
        # Honor region, area, or water aliases even when parse_filters ignored them.
        filters["region"] = raw
    return filters


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


def visible_sets(data, filters: dict, *, public: bool = False):
    term = filters.get("q") or ""
    region = filters.get("region") or ""
    general, limited, review = [], [], []
    for rec in records(data):
        if public and not is_public_record(rec):
            continue
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


def hidden_counts(data, filters: dict, *, public: bool = False):
    """How many limited / needs-review records match search+region but are hidden by filters."""
    term = filters.get("q") or ""
    region = filters.get("region") or ""
    hid_lim = hid_rev = 0
    shown_g, shown_l, shown_r = visible_sets(data, filters, public=public)
    shown_ids = {r["id"] for r in shown_g + shown_l + shown_r}
    for rec in records(data):
        if rec["id"] in shown_ids:
            continue
        if public and not is_public_record(rec):
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


def _shell(title: str, body: str, skip: str = "Skip to the ramp list", *, current: str = "list", extra_head: str = "", extra_script: str = "", main_class: str = "", public: bool = False, canonical: str | None = None, description: str | None = None) -> str:
    import launch_flags
    css_text = css_bytes().decode("utf-8")
    if public and not launch_flags.ramp_map_public():
        map_nav = ""
    elif not public and STATEWIDE_BASE.get():
        map_nav = ""  # statewide map is Phase 2; the private Nov 22 map stays at /preview/ramps/map
    else:
        cur = " aria-current=\"page\"" if current == "map" else ""
        map_nav = f'<a href="{map_base(public)}"{cur}>Map</a>'
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="robots" content="{"index, follow" if public else "noindex, nofollow"}">
{f'<link rel="canonical" href="{esc(canonical)}">\n' if (public and canonical) else ""}{f'<meta name="description" content="{esc(description)}">\n' if description else ""}<meta name="theme-color" content="#071C29">
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
{extra_head}
</head>
<body class="rf-body">
<a class="skip" href="#main">{esc(skip)}</a>
{"" if public else '<p class="rf-banner">Private preview · this browser only · not public · not indexed</p>\n'}<header class="rf-top">
  <div class="rf-top-row">
    <a class="rf-brand" href="{"/" if public else list_base(False)}">The Coastal Brief</a>
    <button type="button" class="theme-toggle" id="theme-toggle">Dark mode</button>
  </div>
  <nav class="rf-nav" aria-label="{"Site" if public else "Preview"}">
    {"" if public else '<a href="/preview">Preview hub</a>'}
    <a href="{list_base(public)}"{' aria-current="page"' if current == "list" else ""}>Ramp Finder</a>
    {map_nav}
  </nav>
</header>
<main class="rf-main{(" " + main_class) if main_class else ""}" id="main">
{body}
<p class="rf-sign">Know the Water. Live the Coast.</p>
</main>
{_THEME_TOGGLE}
{extra_script}
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
    statewide = "access_status" in rec
    for key, label in mapping:
        if statewide and key == "salinity_class":
            rows.append(("Water (fresh / brackish / salt)", (rec.get("salinity") or {}).get("label") or "Not determined"))
            continue
        if statewide and key == "fishing_water_designation":
            rows.append(("Fishing-rules classification", rec.get("regulatory_label") or "not stated"))
            continue
        item = _facility(rec, key, label)
        if item:
            rows.append(item)
    if statewide:
        st = rec.get("access_status") or {}
        rows[0:0] = [
            ("Access type", rec.get("access_type_label") or "not stated"),
            ("Official status", f'{st.get("label", "")}. {st.get("detail", "")} As of {st.get("as_of") or "not stated"}.'.strip()),
            ("Listed under", rec.get("neuse_segment_label") or rec.get("area_label") or ""),
        ]
        oc = rec.get("official_coordinates")
        if oc:
            rows.append(("Official location point", f'{oc["lat"]}, {oc["lon"]}: {oc["note"]} Source: {oc["source_name"]}, checked {oc["checked"]}.'))
        elif rec.get("coordinates_unresolved"):
            rows.append(("Map point", "None. " + rec["coordinates_unresolved"]))
        rows.append(("Record basis", "Manually verified Ramp Finder record (NCWRC fills only blank fields)"
                     if rec.get("record_basis") == "manual_verified" else
                     "NCWRC official listing; facility details exactly as NCWRC records them"))
    return rows


PAGE_DISCLAIMER = (
    "This page is not a live open/closed board. "
    "Information is from official sources, checked Nov 22, 2026."
)

# Phrases that belong on the page once, not repeated in every block.
_DISCLAIMER_RE = re.compile(
    r"(?:\s*(?:This is a dated official graphic,\s+)?"
    r"(?:That is a dated official graphic,\s+)?"
    r"(?:not a live open/closed confirmation(?: and It is not a live open/closed confirmation)?"
    r"|It is not a live open/closed confirmation"
    r"|This is not a live open/closed confirmation"
    r"|This is scheduled information, not a live(?: ramp)?-?availability check"
    r"|Not a live availability check"
    r"|not a live availability check"
    r"|This is scheduled information, not a live check"
    r"|See lake-level context)\.?)+",
    re.I,
)

_CMS_RE = re.compile(
    r"\s*The CMS image query string is t=\S+ \(asset timestamp June 1, 2026\)\.",
)

_DATED_PREFIX_RE = re.compile(r"^CONFIRMED CURRENT NOTICE \([^)]+\):\s*")


def _clean_notice_text(text: str) -> str:
    cleaned = _CMS_RE.sub("", text or "")
    cleaned = _DISCLAIMER_RE.sub("", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    cleaned = re.sub(r"\s+\.", ".", cleaned)
    return cleaned


def general_info_summary(rec, notice_text: str) -> str:
    """Two or three visitor-facing sentences from existing verified data only."""
    rid = rec.get("id") or ""
    if rid in ("local-newbern-lawson-creek-1", "local-newbern-lawson-creek-2"):
        return (
            "The City of New Bern official boat-ramps map, still posted when checked "
            "Nov 22, 2026, labels this as one of two city boat ramps at Lawson Creek Park. "
            "The map was printed May 6, 2025, so its “Open” legend is a dated official graphic. "
            "Lane counts, trailer-parking counts, hours, and coordinates are not stated on the map; "
            "the two ramps share the official park address used for directions."
        )
    if rid == "local-newbern-glenburnie":
        return (
            "The City of New Bern official boat-ramps map, still posted when checked "
            "Nov 22, 2026, labels Glenburnie Park Ramp as a city boat ramp. "
            "The map was printed May 6, 2025, so its “Open” legend is a dated official graphic. "
            "Lane counts, trailer-parking counts, hours, and coordinates are not stated on the map; "
            "directions use the official park address at 340 Glenburnie Drive."
        )
    if rid == "local-newbern-union-point":
        return (
            "The City of New Bern official boat-ramps map, still posted when checked "
            "Nov 22, 2026, labels “Union Point Ramp” with the map legend “Open.” "
            "The map was printed May 6, 2025, so that label is a dated official graphic. "
            "Amenity detail on the pages checked is thinner than for NCWRC boating access areas."
        )
    if rid == "parks-jordan-ebenezer":
        return (
            "Official sources disagree about hours at this access. Both the 24-hour boat-ramp "
            "wording and the day-use gate schedule are shown under Hours; this page does not choose one."
        )
    cleaned = _clean_notice_text(notice_text)
    return _visitor_prose(cleaned or (notice_text or "").strip())


def visible_notice_text(rec, notice: dict) -> str:
    cat = notice.get("category") or "general_information"
    raw = notice.get("text") or ""
    if cat == "general_information":
        return general_info_summary(rec, raw)
    text = _DATED_PREFIX_RE.sub("", raw)
    # Keep “not a construction closure” as a category distinction; drop the
    # duplicated real-time disclaimer (stated once per page).
    text = text.replace(
        ", not a real-time open-right-now confirmation and not a construction closure",
        ", not a construction closure",
    )
    return _visitor_prose(text)


def address_line(rec) -> str:
    d = rec.get("directions") or {}
    addr = rec.get("address") or d.get("address") or ""
    if addr:
        return addr
    bits = [rec.get("street"), rec.get("city")]
    if rec.get("zip") and rec.get("zip") != "not stated":
        bits.append(rec.get("zip"))
    return ", ".join(p for p in bits if p and p != "not stated")


def notice_html(notices, rec=None) -> str:
    parts = []
    rec = rec or {}
    for n in notices or []:
        cat = n.get("category") or "general_information"
        visible = visible_notice_text(rec, n)
        srcs = []
        # Keep official links on dated notices and standing cautions; move
        # general-info methodology links into Source Details.
        if cat != "general_information":
            for s in n.get("sources") or []:
                srcs.append(
                    f'<li><a href="{esc(s["url"])}" rel="noopener noreferrer">'
                    f'{esc(s.get("label") or s["url"])}</a></li>'
                )
        src_html = f'<ul class="sources">{"".join(srcs)}</ul>' if srcs else ""
        checked = ""
        if cat != "general_information" and n.get("as_of"):
            checked = f'<p class="checked">Checked {esc(n.get("as_of"))}.</p>'
        parts.append(
            f'<aside class="notice notice-{esc(cat)}" data-notice-category="{esc(cat)}">'
            f'<span class="nl">{esc(n.get("label") or cat)}</span>'
            f'<p>{esc(visible)}</p>'
            f'{src_html}'
            f'{checked}'
            f'</aside>'
        )
    return "\n".join(parts)


def source_details_html(rec) -> str:
    blocks = []
    sources = []
    for s in rec.get("sources") or []:
        sources.append(
            f'<li><a href="{esc(s["url"])}" rel="noopener noreferrer">{esc(s.get("label") or s["url"])}</a>'
            f'<div class="checked">{esc(s.get("detail") or "")} Checked {esc(s.get("date_checked") or "")}.</div></li>'
        )
    if sources:
        blocks.append("<h3>Official sources</h3>" f'<ul class="sources">{"".join(sources)}</ul>')
    status = rec.get("site_status_official") or ""
    note = rec.get("site_status_note") or ""
    if status or note:
        bits = ["<h3>Official status wording</h3>"]
        if note:
            bits.append(f"<p>{esc(note)}</p>")
        if status:
            bits.append(f"<p>Recorded official wording: {esc(status)}</p>")
        blocks.append("".join(bits))
    notices = rec.get("notices") or []
    if notices:
        items = []
        for n in notices:
            srcs = []
            for s in n.get("sources") or []:
                srcs.append(
                    f'<li><a href="{esc(s["url"])}" rel="noopener noreferrer">'
                    f'{esc(s.get("label") or s["url"])}</a></li>'
                )
            src_html = f'<ul class="sources">{"".join(srcs)}</ul>' if srcs else ""
            items.append(
                f'<div class="source-note" data-original-notice="{esc(n.get("category") or "")}">'
                f'<span class="nl">{esc(n.get("label") or n.get("category") or "")}</span>'
                f'<p>{esc(_visitor_prose(n.get("text") or ""))}</p>'
                f'{src_html}'
                f'<p class="checked">Checked {esc(n.get("as_of") or "")}.</p>'
                f"</div>"
            )
        blocks.append("<h3>Supporting documentation</h3>" + "".join(items))
    water = rec.get("body_of_water") or ""
    water_note = rec.get("body_of_water_note") or ""
    if water or water_note:
        bits = ["<h3>Official waterbody name as recorded</h3>"]
        if water:
            bits.append(f"<p>{esc(water)}</p>")
        if water_note and water_note != water:
            bits.append(f"<p>{esc(water_note)}</p>")
        blocks.append("".join(bits))
    notes = rec.get("notes") or ""
    asides = research_asides_for(rec)
    research_bits = []
    if notes:
        research_bits.append(f"<p>{esc(notes)}</p>")
    for a in asides:
        if a and a != notes:
            research_bits.append(f"<p>{esc(a)}</p>")
    if research_bits:
        blocks.append("<h3>Research notes</h3>" + "".join(research_bits))
    blocks.append(f'<p class="checked">Date checked: {esc(rec.get("date_checked") or "")}.</p>')
    return (
        '<details class="source-details">'
        "<summary>Source Details</summary>"
        f'<div class="source-details-body">{"".join(blocks)}</div>'
        "</details>"
    )



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
    st = (rec.get("access_status") or {}).get("code")
    if st == "temporarily_closed":
        bits.insert(0, '<span class="badge badge-closed">Temporarily closed</span>')
    elif st == "partially_open":
        bits.insert(0, '<span class="badge badge-caution">Partly open</span>')
    elif st == "conflicting":
        bits.insert(0, '<span class="badge badge-caution">Status unclear</span>')
    elif st == "not_stated":
        bits.append('<span class="badge badge-info">Status not stated</span>')
    if rec.get("access_type") == "paddle":
        bits.append('<span class="badge badge-paddle">Paddle / carry-in</span>')
    if (rec.get("flags") or {}).get("motorboats_restricted"):
        bits.append('<span class="badge badge-limited">Motorboats restricted</span>')
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


def _statewide_water_line(rec) -> str:
    if "salinity" not in rec:
        return ""
    sal = (rec.get("salinity") or {}).get("label") or "Not determined"
    reg = rec.get("regulatory_class") or ""
    reg = {"INLAND": "Inland fishing waters", "COASTAL": "Coastal fishing waters",
           "JOINT": "Joint fishing waters"}.get(reg, "Fishing-rules class not stated")
    extra = f' · {esc(rec["_distance_note"])}' if rec.get("_distance_note") else ""
    return f'<span class="amen sw-water">{esc(sal)} · {esc(reg)}{extra}</span>'


def card_html(rec, *, public: bool = False) -> str:
    amen = amenity_line(rec)
    amen_html = f'<span class="amen">{esc(amen)}</span>' if amen else ""
    county = rec.get("county") or ""
    loc = ", ".join(p for p in (rec.get("city"), county and f"{county} County", rec.get("area_label")) if p)
    return (
        f'<li><a class="ramp-card" href="{esc(_detail_url(rec["id"], public=public))}">'
        f'<h3>{esc(rec["display_name"])}</h3>'
        f'<span class="meta">{esc(display_waterbody_name(rec.get("body_of_water") or ""))}'
        f'{" — " + esc(loc) if loc else ""}</span>'
        f'{amen_html}'
        f'{_statewide_water_line(rec)}'
        f'{badges_for(rec)}'
        f'</a></li>'
    )



JORDAN_LOW_WATER_VISITOR_TEXT = (
    "LOW-WATER ACCESS NOTICE — N.C. State Parks reports Vista Point and Parkers Creek boat ramps closed. "
    "Seaforth has one ramp available for single-axle trailers only. "
    "Ebenezer Church and New Hope are listed as alternatives. "
    "Check the official park notice before traveling."
)


def region_notice_html(data, area: str | None) -> str:
    """Visitor-facing lake-level notice. Internal inventory notes stay in meta only."""
    notice = (data.get("meta") or {}).get("jordan_lake_official_notice")
    if not notice:
        return ""
    if area not in (None, "", "jordan-lake"):
        return ""
    src = notice.get("source_url") or ""
    src_name = notice.get("source_name") or src
    accessed = notice.get("accessed_at_label") or notice.get("as_of") or ""
    visitor = notice.get("text") or JORDAN_LOW_WATER_VISITOR_TEXT
    return (
        f'<aside class="context region-notice" data-notice-category="{esc(notice.get("category") or "current_dated_notice")}">'
        f'<p>{esc(visitor)}</p>'
        f'<p class="notice-meta">'
        f'<a href="{esc(src)}" rel="noopener noreferrer">{esc(src_name)}</a>. '
        f'Last checked {esc(accessed)}.</p>'
        "</aside>"
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


def render_list(data, filters: dict, *, public: bool = False) -> str:
    general, limited, review = visible_sets(data, filters, public=public)
    hid_lim, hid_rev = hidden_counts(data, filters, public=public)
    q = filters.get("q") or ""
    region = filters.get("region") or ""

    hidden = []
    if hid_lim:
        hidden.append(f"{hid_lim} limited-access")
    if hid_rev:
        hidden.append(f"{hid_rev} needs-review")
    hidden_note = ""
    if hidden:
        if public:
            hint = "Use the optional filters to show camper-only, non-gas, size-limited, or no-parking sites."
        else:
            hint = "Use the optional filters to show camper-only, non-gas, size-limited, no-parking, or needs-review sites."
        hidden_note = (
            f'<p class="hidden-note">{esc(" and ".join(hidden))} '
            f'{"entry is" if (hid_lim + hid_rev) == 1 else "entries are"} hidden. '
            f'{esc(hint)}</p>'
        )

    chips = []
    filter_keys = ("q", "limited", "camper_only", "non_gas_only", "size_limited", "no_parking")
    if not public:
        filter_keys += ("needs_review",)
    base = {k: filters[k] for k in filter_keys if filters.get(k)}
    for slug, label in AREAS:
        p = dict(base)
        if slug:
            p["region"] = slug
        current = ' aria-current="page"' if slug == region else ""
        chips.append(f'<a href="{esc(_list_url(p, public=public))}"{current}>{esc(label)}</a>')

    checks = []
    for key, label in FLAG_FILTERS:
        if public and key == "needs_review":
            continue
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
    ctx = region_notice_html(data, region or None) + ctx

    def section(title, lead, rows, kind):
        if not rows:
            return ""
        items = "".join(card_html(r, public=public) for r in rows)
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
    if not public:
        body_sections.append(section(
            "Needs review",
            "Official sources are incomplete, conflicting, or do not confirm a general public trailer ramp. Hidden from the default view.",
            review,
            "needs_review",
        ))
    if not (general or limited or review):
        body_sections.append('<p class="empty" data-empty="ramps">No ramps match those filters.</p>')

    shown = len(general) + len(limited) + len(review)
    title = "Ramp Finder" if public else "Ramp Finder — private preview"
    kicker = "Boat ramps" if public else "Private data preview"
    base = list_base(public)
    meta = public_index_meta_description(data) if public else None
    return _shell(title, f"""
<p class="kicker">{kicker}</p>
<h1>Ramp Finder</h1>
<p class="lead">Crystal Coast, Falls Lake, Jordan Lake, and the Neuse River. Official sources only, checked Nov 22, 2026. This is not a live open/closed board.</p>
<form class="filters" id="filters" method="get" action="{base}" role="search">
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
    <button type="reset" onclick="location.href='{base}'; return false;">Reset</button>
  </div>
</form>
<p class="count">Showing {shown} {"ramp" if shown == 1 else "ramps"}{f" in {dict(AREAS).get(region)}" if region else ""}.</p>
{hidden_note}
{ctx}
{''.join(body_sections)}
""", public=public, canonical=(SITE_ORIGIN + _list_url({"region": region} if region else {}, public=True)) if public else None, description=meta)


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
            f'<p>{esc(_visitor_prose(fees.get("summary") or ""))}</p>'
            + "".join(entries)
            + "</section>"
        )
    text, _ = official_summary_for_visitors(fees.get("summary"))
    return f'<h2>Fees</h2><p>{esc(text)}</p>'


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
            f'<p>{esc(_visitor_prose(hours.get("summary") or ""))}</p>'
            + "".join(entries)
            + "</section>"
        )
    text, _ = official_summary_for_visitors(hours.get("summary"))
    return f'<h2>Hours</h2><p>{esc(text)}</p>'


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


def _split_notices(rec):
    priority, general, other = [], [], []
    for n in rec.get("notices") or []:
        cat = n.get("category")
        if cat in ("current_dated_notice", "standing_caution"):
            priority.append(n)
        elif cat == "general_information":
            general.append(n)
        else:
            other.append(n)
    return priority, general, other


NOT_LISTED_OFFICIAL = "Not listed in the official sources checked."

# Acronyms and initialisms left uppercase in presentation-only title case.
WATER_ACRONYMS = {
    "NC", "N.C.", "US", "USA", "USACE", "NCWRC", "NCDMF", "DMF", "ICW",
    "USGS", "ADA", "DCM", "BAA", "TL", "NGVD",
}

# Research asides stripped from visitor-facing leads, fees, and hours.
# The original wording is preserved in Source Details. Restrictions stay
# in their visitor-facing restriction fields.
_ASIDE_PATTERNS = [
    re.compile(r"\s*Never present as Jordan Lake\.?", re.I),
    re.compile(r"\s*\(name on the official town list\)", re.I),
    re.compile(
        r"\s*\(Town of Atlantic Beach official page lists this among public boat ramps\)",
        re.I,
    ),
    re.compile(r"\s*\(not named on the city page\)", re.I),
    re.compile(
        r"\s*DCM site name is Union Street Park at East Front Street and South Front Street, "
        r"which matches the city parks list location for Union Point Park\.?",
        re.I,
    ),
    re.compile(r"\s*The official page does not name the water body\.?", re.I),
    re.compile(r"\s*\(?DCM PRK_FEE\s*=\s*No\)?\.?", re.I),
]


def display_waterbody_name(name: str) -> str:
    """Presentation-only title case for waterbody labels. Inventory is unchanged."""
    s = (name or "").strip()
    if not s:
        return s
    if any("a" <= c <= "z" for c in s):
        return s
    parts = []
    for word in s.split():
        prefix = suffix = ""
        core = word
        while core and core[0] in "([{":
            prefix += core[0]
            core = core[1:]
        while core and core[-1] in ".,;:)]}":
            suffix = core[-1] + suffix
            core = core[:-1]
        if not core:
            parts.append(word)
            continue
        key = core.upper()
        if key in WATER_ACRONYMS or core.upper().replace(".", "") + ("." if "." in core else "") in WATER_ACRONYMS:
            if key in WATER_ACRONYMS:
                core = key if key != "N.C." else "N.C."
            else:
                core = core.upper()
        else:
            core = core.capitalize()
        parts.append(prefix + core + suffix)
    return " ".join(parts)


def _title_lead(lead: str) -> str:
    if " — " not in lead:
        return display_waterbody_name(lead)
    left, right = lead.split(" — ", 1)
    # Title-case an ALL-CAPS official name; leave an already mixed-case qualifier alone.
    right_out = display_waterbody_name(right) if right.isupper() else right
    return f"{display_waterbody_name(left)} — {right_out}"


def extract_research_asides(text: str) -> tuple[str, list[str]]:
    """Split visitor copy from research asides. Inventory text is not modified."""
    s = (text or "").strip()
    asides: list[str] = []
    if not s:
        return "", asides
    for pat in _ASIDE_PATTERNS:
        for m in pat.finditer(s):
            chunk = re.sub(r"^[\s,;.(]+", "", m.group(0).strip())
            chunk = chunk.strip(" 	,;().")
            if chunk:
                asides.append(chunk)
        s = pat.sub("", s)
    s = re.sub(r"\s{2,}", " ", s).strip(" 	,;")
    s = re.sub(r"\s+\.", ".", s).strip()
    return s, asides


def official_summary_for_visitors(summary: str | None) -> tuple[str, list[str]]:
    """Visitor Hours/Fees line, plus any research asides for Source Details."""
    raw = (summary or "").strip()
    if not raw or raw.casefold() == "not stated":
        return NOT_LISTED_OFFICIAL, []
    if re.fullmatch(r"(?:not stated\s*)?\(?DCM PRK_FEE\s*=\s*No\)?\.?", raw, re.I):
        return NOT_LISTED_OFFICIAL, [raw]
    s = re.sub(r"^not stated\.\s+", "", raw, flags=re.I).strip()
    s, asides = extract_research_asides(s)
    if not s:
        if raw not in asides:
            asides.insert(0, raw)
        return NOT_LISTED_OFFICIAL, asides
    return _visitor_prose(s), asides


def _waterbody_lead_raw(rec) -> str:
    """Deduped waterbody line from inventory fields, before presentation cleanup."""
    water = (rec.get("body_of_water") or "").strip()
    note = (rec.get("body_of_water_note") or "").strip()
    if not note:
        return water
    if not water:
        return note
    water_core = re.sub(r"[\s.,;:]+$", "", water)
    # Beaverdam: the note restates the separated-section fact and quotes the
    # gas-motor prohibition, which already appears under Restrictions.
    if re.search(r"separated section of Falls Lake", water, re.I) and re.match(
        r"Beaverdam Lake is separated", note, re.I
    ):
        return water
    if re.match(re.escape(water_core) + r"(?:[\s.,;:\u2013\u2014-]|$)", note, flags=re.I):
        rest = re.sub(
            r"^" + re.escape(water_core) + r"[\s.,;:\u2013\u2014-]*",
            "",
            note,
            count=1,
            flags=re.I,
        ).strip()
        if not rest:
            return re.sub(r"[\s.,;:]+$", "", note) or water_core
        return note
    return f"{water} — {note}"


def _strip_orphan_label_period(lead: str) -> str:
    """Drop a leftover period on a parenthetical identifier after an aside is removed.

    Example: 'Falls Lake (main reservoir).' -> 'Falls Lake (main reservoir)'.
    Official sentences such as 'Falls Lake. Camper-only launch …' stay intact.
    """
    s = (lead or "").strip()
    if re.search(r"\)\.$", s) and not re.search(r"\.\s+\S", s):
        return s[:-1]
    return s


def waterbody_lead(rec) -> str:
    """Visitor-facing waterbody line: no duplicated name, no research asides, title case."""
    raw = _waterbody_lead_raw(rec)
    cleaned, _ = extract_research_asides(raw)
    lead = cleaned or raw
    if " — " in lead:
        left, right = lead.split(" — ", 1)
        right = right.strip(" ,;")
        if not right:
            lead = left
        else:
            lead = f"{left} — {right}"
    return _title_lead(_strip_orphan_label_period(lead))


def research_asides_for(rec) -> list[str]:
    """Asides removed from visitor leads, fees, and hours. For Source Details only."""
    found: list[str] = []
    raw_lead = _waterbody_lead_raw(rec)
    _, lead_asides = extract_research_asides(raw_lead)
    found.extend(lead_asides)
    # When the Beaverdam note is held back from the lead, keep the full note.
    note = (rec.get("body_of_water_note") or "").strip()
    water = (rec.get("body_of_water") or "").strip()
    if note and re.search(r"separated section of Falls Lake", water, re.I) and re.match(
        r"Beaverdam Lake is separated", note, re.I
    ):
        found.append(note)
    for summary in ((rec.get("fees") or {}).get("summary"), (rec.get("hours") or {}).get("summary")):
        _, asides = official_summary_for_visitors(summary)
        found.extend(asides)
    # Dedup while preserving order.
    out, seen = [], set()
    for a in found:
        key = re.sub(r"\s+", " ", a).strip().casefold()
        if key and key not in seen:
            seen.add(key)
            out.append(a.strip())
    return out


def _visitor_prose(text: str) -> str:
    """Replace leftover private-preview wording in visitor-facing copy."""
    if not text:
        return text
    return (
        text.replace("This preview shows", "This page shows")
        .replace("this preview does not", "this page does not")
        .replace("This preview does not", "This page does not")
    )


def _has_stated_summary(val) -> bool:
    s = (val or "").strip()
    return bool(s) and s.casefold() != "not stated"


def render_detail(data, rec, *, public: bool = False) -> str:
    loc_bits = [rec.get("city"), (rec.get("county") + " County") if rec.get("county") else "", rec.get("area_label")]
    loc = ", ".join(p for p in loc_bits if p)
    rows = facility_rows(rec)
    facts = ""
    if rows:
        tr = "".join(f"<tr><th>{esc(k)}</th><td>{esc(v)}</td></tr>" for k, v in rows)
        facts = f'<h2>Facilities</h2><table class="facts">{tr}</table>'
    alias = f'<p class="meta">Also recorded as {esc(rec["alias"])}.</p>' if rec.get("alias") and rec.get("alias") != "not stated" else ""
    restrict = rec.get("restriction_notes") or ""
    restrict_html = f"<h2>Restrictions</h2><p>{esc(restrict)}</p>" if restrict and restrict != "not stated" else ""
    ctx = ""
    if rec["area"] in ("falls-lake", "jordan-lake"):
        ctx = lake_context_html(data, rec["area"])
    if rec["area"] == "jordan-lake":
        ctx = region_notice_html(data, "jordan-lake") + ctx
    addr = address_line(rec)
    addr_html = f'<p class="addr">{esc(addr)}</p>' if addr else ""
    priority, general, other = _split_notices(rec)
    title = rec["display_name"] + (" — Ramp Finder" if public else " — Ramp Finder (private preview)")
    water = esc(waterbody_lead(rec))
    agency = esc(rec.get("managing_agency") or "")
    if rec.get("program"):
        agency = agency + " · " + esc(rec.get("program"))
    return _shell(title, f"""
<p class="crumb"><a href="{list_base(public)}">Ramp Finder</a> / {esc(rec["display_name"])}</p>
<p class="kicker">{esc(rec.get("area_label") or "")}</p>
<h1>{esc(rec["display_name"])}</h1>
<p class="lead">{water}</p>
{addr_html}
<p class="meta">{esc(loc)}</p>
<p class="meta">{agency}</p>
{alias}
<p class="rf-disclaimer">{esc(PAGE_DISCLAIMER)}</p>
{ctx}
{badges_for(rec)}
{notice_html(priority, rec)}
{notice_html(general + other, rec)}
{restrict_html}
{fees_html(rec)}
{hours_html(rec)}
{facts}
{directions_html(rec)}
{source_details_html(rec)}
""", skip="Skip to ramp details", current="detail", public=public, canonical=(SITE_ORIGIN + _detail_url(rec["id"], public=True)) if public else None)



def official_coordinates(rec):
    """Return (lat, lon) only when the inventory recorded official coordinates."""
    d = rec.get("directions") or {}
    if d.get("mode") != "coordinates":
        return None
    lat, lon = d.get("latitude"), d.get("longitude")
    if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
        return float(lat), float(lon)
    return None


def has_official_pin(rec) -> bool:
    return official_coordinates(rec) is not None


def pin_inventory_counts(data=None, recs=None) -> dict:
    """How many records have official pins vs address-only directions."""
    data = data or load_data()
    src = list(recs) if recs is not None else records(data)
    pins = addr = 0
    by_class = {"general": {"pin": 0, "address": 0}, "limited": {"pin": 0, "address": 0}, "needs_review": {"pin": 0, "address": 0}}
    by_area = {}
    for rec in src:
        cls = rec["listing_class"]
        area = rec["area"]
        by_area.setdefault(area, {"pin": 0, "address": 0})
        if has_official_pin(rec):
            pins += 1
            by_class[cls]["pin"] += 1
            by_area[area]["pin"] += 1
        else:
            addr += 1
            by_class[cls]["address"] += 1
            by_area[area]["address"] += 1
    return {"pin": pins, "address": addr, "total": pins + addr, "by_class": by_class, "by_area": by_area}


def _map_notice_excerpt(rec, notice: dict, limit: int = 240) -> str:
    text = visible_notice_text(rec, notice).strip()
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return cut + "…"


def map_record(rec, *, public: bool = False) -> dict:
    """Slim, presentation-only record for the private map. Never invents coordinates."""
    d = rec.get("directions") or {}
    coords = official_coordinates(rec)
    dated = caution = None
    for n in rec.get("notices") or []:
        cat = n.get("category")
        if cat == "current_dated_notice" and dated is None:
            dated = _map_notice_excerpt(rec, n)
        elif cat == "standing_caution" and caution is None:
            caution = _map_notice_excerpt(rec, n)
    restriction = rec.get("restriction_notes")
    if restriction in (None, "", "not stated"):
        restriction = None
    flags = rec.get("flags") or {}
    active = {k: True for k, v in flags.items() if v}
    return {
        "id": rec["id"],
        "name": rec.get("display_name") or rec.get("official_name"),
        "waterbody": rec.get("body_of_water_note") or rec.get("body_of_water") or "",
        "area": rec["area"],
        "area_label": rec.get("area_label") or "",
        "listing_class": rec["listing_class"],
        "has_pin": coords is not None,
        "lat": coords[0] if coords else None,
        "lon": coords[1] if coords else None,
        "address": d.get("address"),
        "apple_url": d.get("apple_url"),
        "google_url": d.get("google_url"),
        "restriction": restriction,
        "dated_notice": dated,
        "standing_caution": caution,
        "flags": active,
        "detail_url": _detail_url(rec["id"], public=public),
    }


def map_payload(data=None, *, public: bool = False) -> dict:
    data = data or load_data()
    src = public_records(data) if public else records(data)
    recs = [map_record(rec, public=public) for rec in src]
    counts = pin_inventory_counts(data, recs=src)
    return {
        "disclaimer": PAGE_DISCLAIMER,
        "counts": counts,
        "records": recs,
    }


def map_js_bytes() -> bytes:
    return MAP_JS_PATH.read_bytes()


def _map_list_item(rec, payload_rec) -> str:
    pin = payload_rec["has_pin"]
    pin_note = "" if pin else (
        '<span class="rf-no-pin">No map pin — address directions</span>'
    )
    badges = []
    if payload_rec.get("dated_notice"):
        badges.append('<span class="badge badge-notice">Current dated notice</span>')
    if payload_rec.get("standing_caution"):
        badges.append('<span class="badge badge-caution">Standing caution</span>')
    if rec["listing_class"] == "limited":
        badges.append('<span class="badge">Limited access</span>')
    elif rec["listing_class"] == "needs_review":
        badges.append('<span class="badge">Needs review</span>')
    if (rec.get("flags") or {}).get("fee_conflict"):
        badges.append('<span class="badge">Fee figures differ</span>')
    if (rec.get("flags") or {}).get("hours_uncertain"):
        badges.append('<span class="badge">Hours uncertain</span>')
    loc = rec.get("city") or rec.get("county") or ""
    notice_bit = ""
    if payload_rec.get("dated_notice"):
        notice_bit = f'<p class="rf-list-notice">{esc(payload_rec["dated_notice"])}</p>'
    elif payload_rec.get("standing_caution"):
        notice_bit = f'<p class="rf-list-caution">{esc(payload_rec["standing_caution"])}</p>'
    return (
        f'<li class="rf-sync-item{" rf-has-pin" if pin else " rf-address-only"}"'
        f' id="ramp-{esc(rec["id"])}" data-ramp-id="{esc(rec["id"])}">'
        f'<button type="button" class="rf-sync-select" data-ramp-id="{esc(rec["id"])}">'
        f'<span class="rf-sync-name">{esc(payload_rec["name"])}</span>'
        f'<span class="rf-sync-meta">{esc(payload_rec["waterbody"])}'
        f'{" — " + esc(loc) if loc else ""}</span>'
        f'{pin_note}'
        f'<span class="rf-sync-badges">{"".join(badges)}</span>'
        f'{notice_bit}'
        f'</button>'
        f'<a class="rf-sync-detail" href="{esc(payload_rec["detail_url"])}">Details</a>'
        f'</li>'
    )


def render_map(data, filters: dict, *, public: bool = False) -> str:
    general, limited, review = visible_sets(data, filters, public=public)
    hid_lim, hid_rev = hidden_counts(data, filters, public=public)
    region = filters.get("region") or ""
    payload = map_payload(data, public=public)
    by_id_payload = {r["id"]: r for r in payload["records"]}

    def section(title, recs, cls):
        if not recs:
            return ""
        items = "\n".join(_map_list_item(rec, by_id_payload[rec["id"]]) for rec in recs)
        return f'<h2 class="rf-sync-h">{esc(title)}</h2>\n<ul class="rf-sync-list" data-class="{esc(cls)}">{items}</ul>'

    shown = general + limited + review
    pin_shown = sum(1 for r in shown if has_official_pin(r))
    addr_shown = len(shown) - pin_shown

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
            f'Use the optional filters to show them on the map and in the list.</p>'
        )

    chips = []
    for key, label in AREAS:
        params = {k: v for k, v in filters.items() if k != "theme"}
        params["region"] = MAP_ALL_REGION if key == "" else key
        url = _map_url(params, public=public)
        current = key == region
        if current:
            chips.append(f'<span aria-current="page">{esc(label)}</span>')
        else:
            chips.append(f'<a href="{esc(url)}">{esc(label)}</a>')

    checks = []
    map_flags = (("limited", "Show limited-access launches"),)
    if not public:
        map_flags += (("needs_review", "Show needs-review entries"),)
    for key, label in map_flags:
        on = " checked" if filters.get(key) else ""
        checks.append(
            f'<label class="flag"><input type="checkbox" name="{esc(key)}" value="1"{on}> {esc(label)}</label>'
        )

    status = (
        f'{pin_shown} {"ramp has" if pin_shown == 1 else "ramps have"} a verified map pin'
        f' · {addr_shown} {"is" if addr_shown == 1 else "are"} listed with no map pin — address directions'
    )

    lists = (
        section("General-use ramps", general, "general")
        + section("Limited-access launches", limited, "limited")
        + section("Needs review", review, "needs_review")
    )
    if not shown:
        lists = '<p class="count">No ramps match these filters.</p>'

    visible_ids = {r["id"] for r in shown}
    page_records = []
    for r in payload["records"]:
        if r["id"] not in visible_ids:
            continue
        item = {k: v for k, v in r.items() if v not in (None, "", [], {})}
        page_records.append(item)
    page_payload = {"counts": payload["counts"], "records": page_records}
    map_notice = region_notice_html(data, region if region else None)
    map_kicker = "Boat ramps" if public else "Private preview"

    body = f"""
<p class="kicker">{map_kicker}</p>
<h1>Ramp map</h1>
<p class="rf-disclaimer">{esc(PAGE_DISCLAIMER)} Pins are placed only from official coordinates.</p>
<div class="regions rf-map-regions" aria-label="Region">{''.join(chips)}</div>
<p class="count rf-map-status" id="rf-map-status" aria-live="polite">{esc(status)}</p>
{map_notice}
<div class="rf-map-layout">
  <div class="rf-map-frame">
    <div class="rf-map-toolbar">
      <div class="rf-basemap" role="group" aria-label="Basemap">
        <button type="button" class="rf-basemap-btn is-active" id="rf-basemap-topo" aria-pressed="true">Topo</button>
        <button type="button" class="rf-basemap-btn" id="rf-basemap-aerial" aria-pressed="false">Aerial</button>
      </div>
    </div>
    <div id="rf-map" class="rf-map-stage" role="region" aria-label="Interactive ramp map">
      <p class="rf-map-placeholder">Loading map…</p>
    </div>
    <p class="rf-map-credit">Basemap: map services and data available from U.S. Geological Survey, National Geospatial Program (public domain). Not for navigation.</p>
  </div>
  <div class="rf-map-list-wrap" id="rf-map-list">
    <form class="filters rf-map-filters" id="filters" method="get" action="{map_base(public)}" role="search">
      <input type="hidden" name="region" value="{esc(region)}">
      <div class="flag-row">{''.join(checks)}</div>
      <div class="actions">
        <button type="submit">Update map</button>
        <button type="reset" onclick="location.href='{map_base(public)}'; return false;">Reset</button>
      </div>
    </form>
    {hidden_note}
    <h2 class="rf-sync-title">Ramp list</h2>
    <p class="count">Selecting a name highlights its marker, and tapping a marker highlights its row. Address-only ramps have no pin.</p>
    {lists}
  </div>
</div>
<div id="rf-sheet" class="rf-sheet" hidden>
  <div class="rf-sheet-scrim" id="rf-sheet-scrim" hidden></div>
  <div class="rf-sheet-panel" id="rf-sheet-panel" role="dialog" aria-modal="true" aria-labelledby="rf-sheet-title" tabindex="-1">
    <button type="button" class="rf-sheet-close" id="rf-sheet-close" aria-label="Close ramp panel">Close</button>
    <h3 id="rf-sheet-title"></h3>
    <p id="rf-sheet-water" class="rf-sheet-water"></p>
    <p id="rf-sheet-alert" class="rf-sheet-alert" hidden></p>
    <div class="rf-sheet-actions">
      <a class="btn" id="rf-sheet-detail" href="#">Ramp details</a>
      <a class="btn" id="rf-sheet-apple" href="#">Apple Maps directions</a>
      <a class="btn" id="rf-sheet-google" href="#" rel="noopener noreferrer" target="_blank">Google Maps directions</a>
    </div>
  </div>
</div>
<script type="application/json" id="rf-map-data">{json.dumps(page_payload, ensure_ascii=False, separators=(",", ":"))}</script>
"""
    extra_script = f'<script src="{list_base(public)}/map.js" defer></script>'
    title = "Ramp map — The Coastal Brief" if public else "Ramp map — The Coastal Brief (private preview)"
    return _shell(
        title,
        body,
        skip="Skip to the ramp map",
        current="map",
        extra_script=extra_script,
        main_class="rf-map-main",
        public=public,
        canonical=(SITE_ORIGIN + _map_url({"region": region} if region else {}, public=True)) if public else None,
    )


def _canonical_ramp_path(raw: str) -> str:
    """Map public /ramps paths onto the existing /preview/ramps names."""
    if raw in ("/ramps.css",):
        return "/preview/ramps.css"
    if raw in ("/ramps.json",):
        return "/preview/ramps.json"
    if raw == "/ramps":
        return "/preview/ramps"
    if raw.startswith("/ramps/"):
        return "/preview/ramps/" + raw[len("/ramps/"):]
    return raw


def resolve_request(path: str, query: dict, *, public: bool = False):
    raw = path.rstrip("/") or ("/ramps" if public else "/preview/ramps")
    raw = _canonical_ramp_path(raw)
    if raw in ("/preview/ramps.css",):
        return 200, "text/css; charset=utf-8", css_bytes()
    if raw in ("/preview/ramps/map.js",):
        return 200, "text/javascript; charset=utf-8", map_js_bytes()
    data = load_data()
    if raw in ("/preview/ramps.json",):
        if public:
            return 404, "text/plain", "not found"
        return 200, "application/json; charset=utf-8", json.dumps(data, ensure_ascii=False)
    if raw in ("/preview/ramps/map.json",):
        return 200, "application/json; charset=utf-8", json.dumps(map_payload(data, public=public), ensure_ascii=False)
    if raw in ("/preview/ramps/map",):
        return 200, "text/html; charset=utf-8", render_map(data, parse_map_filters(query or {}), public=public)
    if public and raw == "/preview/ramps":
        import ramp_statewide
        return ramp_statewide.resolve_request("/ramps", query, public=True)
    if public and raw.startswith("/preview/ramps/"):
        import ramp_statewide
        rid = raw[len("/preview/ramps/"):].strip("/")
        if rid in MAP_ASSET_SLUGS:
            return 404, "text/plain", "not found"
        return ramp_statewide.resolve_request("/ramps/" + rid, query, public=True)
    if raw in ("/preview/ramps",):
        return 200, "text/html; charset=utf-8", render_list(data, parse_filters(query or {}), public=public)
    prefix = "/preview/ramps/"
    if raw.startswith(prefix):
        rid = raw[len(prefix):].strip("/")
        if rid in MAP_ASSET_SLUGS:
            return 404, "text/plain", "not found"
        rec = by_id(rid, data)
        if not rec or (public and not is_public_record(rec)):
            return 404, "text/plain", "not found"
        return 200, "text/html; charset=utf-8", render_detail(data, rec, public=public)
    return 404, "text/plain", "not found"
