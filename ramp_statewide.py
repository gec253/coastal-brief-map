"""Statewide Ramp Finder — PRIVATE preview only (Ed t547u, Phase 1).

/preview/ramps-statewide and /preview/ramps-statewide/<slug>, cookie-gated by server.py.
Reads the static preview/ramp-finder/statewide.json written by
scripts/build_ramps_statewide.py. Public /ramps keeps reading inventory.json and is
unchanged. No map, near-me or conditions panel here (Phase 2).
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import ramp_finder as rf

ROOT = Path(__file__).resolve().parent
DATA_PATH = ROOT / "preview" / "ramp-finder" / "statewide.json"
BASE = "/preview/ramps-statewide"
_cache: dict = {"mtime": None, "data": None}

# Homepage regions first, then the Neuse split, then the rest of the state.
REGION_CHOICES = [
    ("", "All of North Carolina"),
    ("crystal-coast", "Crystal Coast"),
    ("emerald-isle", "Emerald Isle"),
    ("wilmington", "Wilmington · Wrightsville Beach"),
    ("topsail", "Topsail"),
    ("nags-head", "Nags Head · Outer Banks"),
    ("hatteras", "Hatteras Island"),
    ("falls-lake", "Falls Lake"),
    ("jordan-lake", "Jordan Lake"),
    ("neuse-river", "Neuse River (upper and lower)"),
    ("neuse-upper", "Upper Neuse: Falls Dam to Goldsboro"),
    ("neuse-lower", "Lower Neuse: below Goldsboro"),
    ("other-coastal", "Elsewhere: Coastal Plain"),
    ("other-piedmont", "Elsewhere: Piedmont"),
    ("other-mountain", "Elsewhere: Mountains"),
]
REGION_LABELS = dict(REGION_CHOICES)
TYPE_CHOICES = [("", "All access types"), ("trailer", "Trailer launches"), ("paddle", "Paddle / carry-in")]
WATER_CHOICES = [("", "Any water"), ("fresh", "Freshwater"), ("tidal", "Brackish or salt (tidal)"), ("unknown", "Not determined")]
CLOSED_CODES = ("temporarily_closed", "conflicting")

EXTRA_CSS = """<style>
.sw-select{display:grid;gap:.6rem;grid-template-columns:repeat(auto-fit,minmax(13rem,1fr));margin:.6rem 0}
.sw-select label{display:grid;gap:.2rem;font-size:.85rem}
.sw-select select{min-height:44px;font:inherit;padding:.35rem .5rem;border-radius:8px;border:1px solid var(--rule,#9aa);background:var(--paper,#fff);color:inherit}
.badge-closed{background:#8a1c1c;color:#fff}
.badge-paddle{background:#1f5a4f;color:#fff}
.sw-water{display:block;font-size:.85rem;opacity:.85}
.sw-honest{border-left:4px solid #a8803a;padding:.6rem .9rem;margin:1rem 0;background:rgba(168,128,58,.08)}
.sw-refresh-bad{border-left:4px solid #8a1c1c;padding:.6rem .9rem;margin:1rem 0}
.sw-about summary{cursor:pointer;min-height:44px;display:flex;align-items:center}
.sw-about li{margin:.3rem 0}
</style>"""


def load() -> dict:
    m = DATA_PATH.stat().st_mtime
    if _cache["mtime"] != m:
        _cache["data"] = json.loads(DATA_PATH.read_text())
        _cache["mtime"] = m
    return _cache["data"]


def by_id(rid: str, data: dict):
    for r in data["records"]:
        if r["id"] == rid:
            return r
    return None


def _first(q: dict, k: str) -> str:
    v = (q or {}).get(k)
    if not v:
        return ""
    return ((v[0] if isinstance(v, list) else v) or "").strip()


def parse(q: dict) -> dict:
    f = {"region": _first(q, "region"), "q": _first(q, "q"), "type": _first(q, "type"), "water": _first(q, "water")}
    for key, _ in rf.FLAG_FILTERS:
        f[key] = _first(q, key) in ("1", "true", "on", "yes")
    if f["type"] not in dict(TYPE_CHOICES):
        f["type"] = ""
    if f["water"] not in dict(WATER_CHOICES):
        f["water"] = ""
    return f


def _water_group(r) -> str:
    c = (r.get("salinity") or {}).get("class")
    if c == "freshwater":
        return "fresh"
    if c in ("brackish", "saltwater", "tidal"):
        return "tidal"
    return "unknown"


def region_match(r, region: str) -> bool:
    if not region:
        return True
    if region == "emerald-isle":
        return r["area"] == "crystal-coast"
    if region == "neuse-upper":
        return r["area"] == "neuse-river" and r.get("neuse_segment") == "upper"
    if region == "neuse-lower":
        return r["area"] == "neuse-river" and r.get("neuse_segment") == "lower"
    return r["area"] == region


def _miles(lat1, lon1, lat2, lon2) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return 2 * 3958.7613 * math.asin(math.sqrt(a))


def nearest_verified(data, lat, lon, n=3):
    out = []
    for r in data["records"]:
        d = r.get("directions") or {}
        if r["listing_class"] == "needs_review" or not isinstance(d.get("latitude"), (int, float)):
            continue
        out.append((_miles(lat, lon, d["latitude"], d["longitude"]), r))
    out.sort(key=lambda x: x[0])
    return out[:n]


def classify(data, f):
    """Return dict of section -> records, plus hidden counts."""
    secs = {"trailer": [], "paddle": [], "closed": [], "limited": [], "needs_review": []}
    hidden = {"limited": 0, "needs_review": 0}
    flag_keys = ("camper_only", "non_gas_only", "size_limited", "no_parking")
    for r in data["records"]:
        if not region_match(r, f["region"]):
            continue
        if not rf.matches_search(r, f["q"]):
            continue
        if f["type"] and r.get("access_type") != f["type"]:
            continue
        if f["water"] and _water_group(r) != f["water"]:
            continue
        cls = r["listing_class"]
        code = (r.get("access_status") or {}).get("code")
        flag_hit = any(f.get(k) and (r.get("flags") or {}).get(k) for k in flag_keys)
        if cls == "needs_review":
            if f.get("needs_review") or flag_hit:
                secs["needs_review"].append(r)
            else:
                hidden["needs_review"] += 1
            continue
        if code in CLOSED_CODES:
            secs["closed"].append(r)
            continue
        if cls == "limited":
            if f.get("limited") or flag_hit:
                secs["limited"].append(r)
            else:
                hidden["limited"] += 1
            continue
        secs["paddle" if r.get("access_type") == "paddle" else "trailer"].append(r)
    return secs, hidden


SECTION_TEXT = {
    "trailer": ("Trailer launches", "Public launch lanes for trailered boats, from official records. Listed as open in the official record; not a live check."),
    "paddle": ("Paddle and carry-in access", "NCWRC records these as portable-boat access (steps, slides or small launches). Not for trailered boats."),
    "closed": ("Temporarily closed or status unclear", "An official source lists these as closed, or official sources disagree. Dates are shown on each page."),
    "limited": ("Limited or restricted access", "Verified sites with a hard restriction: camper-only, non-gas only, size-limited, no parking, or motorboats restricted."),
    "needs_review": ("Needs review", "Official sources are incomplete, conflicting, or do not confirm a general public launch."),
}


def _section(kind, rows, sub=None):
    if not rows:
        return ""
    title, lead = SECTION_TEXT[kind]
    if sub:
        title = f"{title}: {sub}"
    items = "".join(rf.card_html(r, public=False) for r in rows)
    return (f'<section class="rf-section" data-section="{rf.esc(kind)}">'
            f'<h2>{rf.esc(title)} ({len(rows)})</h2><p class="section-lead">{rf.esc(lead)}</p>'
            f'<ul class="list">{items}</ul></section>')


def _select(name, label, choices, current):
    opts = "".join(f'<option value="{rf.esc(v)}"{" selected" if v == current else ""}>{rf.esc(t)}</option>' for v, t in choices)
    return f'<label for="sw-{name}">{rf.esc(label)}<select id="sw-{name}" name="{name}">{opts}</select></label>'


def _about(data) -> str:
    rules = (data.get("meta") or {}).get("rules") or {}
    return f"""<details class="sw-about"><summary>How this list is built</summary><ul>
<li>Sources: our manually verified Ramp Finder records (checked Nov 22, 2026) plus every NCWRC Boating Access Area in the official feature service. Our verified details win field by field; NCWRC only fills blanks, and each page says which.</li>
<li>Nothing is guessed. A blank official field shows as not stated. It never means an amenity is there or that a site is open.</li>
<li>Regions: new NCWRC sites join Crystal Coast (including Emerald Isle), Wilmington, Topsail, Nags Head or Hatteras when they are within {rules.get("region_radius_mi", 20):g} miles, straight line, of that region's homepage anchor. The nearest anchor wins. Falls Lake, Jordan Lake and Neuse River sites go by their NCWRC waterbody. Everything else is grouped by NCWRC's Coastal, Piedmont or Mountain region.</li>
<li>Upper Neuse means launches at or upstream of the Goldsboro access, matching the homepage Neuse region. Lower Neuse is everything below Goldsboro to Pamlico Sound. That includes freshwater, brackish and tidal launches.</li>
<li>Fishing-rules classification (inland, coastal or joint) is NCWRC's regulatory label, not a salinity reading. Fresh, brackish or salt is shown separately. It is marked verified where our research recorded it and inferred otherwise. Inferred freshwater means inland fishing waters more than {rules.get("fresh_min_tide_mi", 15):g} miles from any NOAA tide-prediction station. Inferred tidal means coastal fishing waters within {rules.get("tidal_max_tide_mi", 10):g} miles of one. Anything else is not determined.</li>
<li>Status comes from the official record or a dated official notice, whichever is newer. It is never a live open/closed check.</li>
</ul></details>"""


def render_list(data, q) -> str:
    tok = rf.STATEWIDE_BASE.set(BASE)
    try:
        return _render_list(data, q)
    finally:
        rf.STATEWIDE_BASE.reset(tok)


def _render_list(data, q) -> str:
    f = parse(q)
    region = f["region"]
    meta = data.get("meta") or {}
    checked = meta.get("date_checked", "")
    refresh = meta.get("refresh") or {}
    honest = ""
    if region and region not in REGION_LABELS:
        honest = (f'<aside class="sw-honest" data-honest="unknown-region"><p>We don’t have a ramp area called '
                  f'“{rf.esc(region)}”. Nothing is filtered here, so no ramps are shown for it.</p>'
                  f'<p><a href="{BASE}">See the statewide ramp list</a></p></aside>')
        secs, hidden = {k: [] for k in SECTION_TEXT}, {"limited": 0, "needs_review": 0}
    else:
        secs, hidden = classify(data, f)
    if region == "emerald-isle":
        honest = ('<aside class="sw-honest" data-honest="emerald-isle"><p>Emerald Isle ramps are listed with the '
                  'Crystal Coast. This list shows the whole Crystal Coast area.</p></aside>')
    shown_total = sum(len(v) for v in secs.values())
    if region == "hatteras" and shown_total == 0 and not (f["q"] or f["type"] or f["water"]):
        anc = (meta.get("rules") or {}).get("anchors", {}).get("hatteras") or {}
        near = nearest_verified(data, anc.get("lat"), anc.get("lon")) if anc else []
        cards = []
        for d, r in near:
            r2 = dict(r)
            r2["_distance_note"] = f"{d:.0f} mi straight line from {anc.get('label', 'Cape Hatteras')}"
            cards.append(rf.card_html(r2, public=False))
        honest = (f'<aside class="sw-honest" data-honest="hatteras"><p><strong>No verified public launches are listed for '
                  f'the Hatteras area yet.</strong> Our Hatteras area is within {(meta.get("rules") or {}).get("region_radius_mi", 20):g} '
                  f'miles of {rf.esc(anc.get("label", "Cape Hatteras"))}, and no official record we use falls inside it. '
                  'National Park Service and Dare County launches on the island are not in our official sources yet, '
                  'so we don’t list them.</p>'
                  f'<p>The nearest verified launches are outside the Hatteras area:</p></aside>'
                  f'<section class="rf-section" data-section="nearest-outside"><h2>Nearest verified launches outside this area</h2>'
                  f'<ul class="list">{"".join(cards)}</ul></section>'
                  f'<p><a href="{BASE}">See the statewide ramp list</a></p>')
    body = []
    if region in ("neuse-river",):
        for seg, sub in (("upper", "Upper Neuse, Falls Dam to Goldsboro"), ("lower", "Lower Neuse, below Goldsboro (brackish and tidal launches included)")):
            for kind in ("trailer", "paddle", "closed", "limited", "needs_review"):
                body.append(_section(kind, [r for r in secs[kind] if r.get("neuse_segment") == seg], sub))
    else:
        for kind in ("trailer", "paddle", "closed", "limited", "needs_review"):
            body.append(_section(kind, secs[kind]))
    if shown_total == 0 and not honest:
        body.append('<p class="empty" data-empty="ramps">No ramps match those filters.</p>')
    hid = []
    if hidden["limited"]:
        hid.append(f'{hidden["limited"]} limited-access')
    if hidden["needs_review"]:
        hid.append(f'{hidden["needs_review"]} needs-review')
    hidden_note = (f'<p class="hidden-note">{rf.esc(" and ".join(hid))} '
                   f'{"entry is" if hidden["limited"] + hidden["needs_review"] == 1 else "entries are"} hidden. '
                   'Use the optional filters to show them.</p>') if hid else ""
    ctx = ""
    if region in ("falls-lake", "jordan-lake"):
        ctx = rf.lake_context_html(data, region)
    ctx = (rf.region_notice_html(data, region if region in ("jordan-lake",) else (None if not region else "x")) + ctx)
    refresh_html = ""
    if refresh.get("status") == "kept_last_known_good":
        refresh_html = (f'<aside class="sw-refresh-bad" data-refresh="kept-last-known-good"><p>The latest official data refresh '
                        f'({rf.esc(refresh.get("attempted_at", ""))}) did not pass its checks: {rf.esc(refresh.get("reason", ""))}. '
                        f'This list still shows the last good data, checked {rf.esc(refresh.get("data_from", ""))}.</p></aside>')
    checks = "".join(
        f'<label><input type="checkbox" name="{rf.esc(k)}" value="1"{" checked" if f.get(k) else ""}> {rf.esc(lbl)}</label>'
        for k, lbl in rf.FLAG_FILTERS)
    where = ("the Crystal Coast (Emerald Isle is listed here)" if region == "emerald-isle"
             else REGION_LABELS.get(region, "") if region else "")
    count_line = (f'Showing {shown_total} {"site" if shown_total == 1 else "sites"}'
                  f'{" in " + rf.esc(where) if where else ""}'
                  + (f' ({len(secs["trailer"])} trailer, {len(secs["paddle"])} paddle, {len(secs["closed"])} closed or unclear'
                     f'{", " + str(len(secs["limited"])) + " limited" if secs["limited"] else ""}'
                     f'{", " + str(len(secs["needs_review"])) + " needs review" if secs["needs_review"] else ""})' if shown_total else "")
                  + ".")
    n_total = len(data["records"])
    return rf._shell("Ramp Finder statewide — private preview", f"""
<p class="kicker">Private data preview · Phase 1</p>
<h1>Ramp Finder: North Carolina</h1>
<p class="lead">{n_total} public boating access sites statewide, from official sources only, checked {rf.esc(checked)}. This is not a live open/closed board.</p>
{refresh_html}
<form class="filters" id="filters" method="get" action="{BASE}" role="search">
  <label class="q-lab" for="q">Search by name, town, county or body of water</label>
  <input type="search" id="q" name="q" value="{rf.esc(f["q"])}" placeholder="Search ramps" autocomplete="off">
  <div class="sw-select">
    {_select("region", "Area", REGION_CHOICES, region if region in REGION_LABELS else "")}
    {_select("type", "Access type", TYPE_CHOICES, f["type"])}
    {_select("water", "Water", WATER_CHOICES, f["water"])}
  </div>
  <fieldset class="opt-filters"><legend>Optional filters</legend><div class="opt-row">{checks}</div></fieldset>
  <div class="actions"><button type="submit">Apply filters</button>
  <button type="reset" onclick="location.href='{BASE}'; return false;">Reset</button></div>
</form>
{honest}
{"" if (honest and shown_total == 0) else f'<p class="count">{count_line}</p>'}
{hidden_note}
{ctx}
{"".join(body)}
{_about(data)}
""", extra_head=EXTRA_CSS, public=False)


def render_detail(data, rec) -> str:
    tok = rf.STATEWIDE_BASE.set(BASE)
    try:
        html_out = rf.render_detail(data, rec, public=False)
    finally:
        rf.STATEWIDE_BASE.reset(tok)
    return html_out.replace("</head>", EXTRA_CSS + "\n</head>", 1)


def resolve_request(path: str, query: dict):
    raw = path.rstrip("/") or BASE
    data = load()
    if raw == BASE:
        return 200, "text/html; charset=utf-8", render_list(data, query or {})
    if raw.startswith(BASE + "/"):
        rid = raw[len(BASE) + 1:].strip("/")
        rec = by_id(rid, data)
        if not rec:
            return 404, "text/plain", "not found"
        return 200, "text/html; charset=utf-8", render_detail(data, rec)
    return 404, "text/plain", "not found"
