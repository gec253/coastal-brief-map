"""Statewide Ramp Finder directory (Phase 1 / 1.1, public launch Ed t550u).

Public /ramps and /ramps/<slug> read statewide.json. The same pages remain
available behind the cookie at /preview/ramps-statewide. The interactive map
stays private. No near-me or conditions panel (Phase 2).
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import launch_flags
import ramp_finder as rf
import ramp_search

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
.sw-active{display:flex;flex-wrap:wrap;align-items:center;gap:.4rem;margin:.6rem 0}
.sw-al{font-size:.85rem;font-weight:600}
.sw-chip{display:inline-flex;align-items:center;gap:.3rem;min-height:44px;padding:0 .8rem;border-radius:999px;border:1.5px solid currentColor;text-decoration:none;color:inherit;font-weight:600;font-size:.9rem}
.sw-chip span{font-size:1.1rem}
.sw-scope{font-size:.9rem;margin:.4rem 0}.sw-scope a{display:inline-flex;align-items:center;min-height:44px}
.sw-allnc{display:inline-flex;align-items:center;justify-content:center;min-height:48px;text-decoration:none;text-align:center}
html[data-theme="dark"] .sw-allnc{background:var(--ivory);color:var(--navy);border-color:var(--ivory)}
.sw-viewmap{margin-left:auto;min-height:44px;gap:.2rem}
.sw-inarea{display:flex;align-items:center;gap:.5rem;min-height:44px;font-size:.9rem}
.sw-inarea input{width:22px;height:22px}
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
    f = {"region": _first(q, "region"), "q": _first(q, "q"), "type": _first(q, "type"), "water": _first(q, "water"),
         "in_area": _first(q, "in_area") in ("1", "true", "on", "yes")}
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


STATUS_CHOICES = [("", "Any status"), ("listed_open", "Open as listed"), ("temporarily_closed", "Temporarily closed"),
                  ("partially_open", "Partly open"), ("conflicting", "Status unclear"), ("not_stated", "Unknown / not stated")]
STATUS_LABELS = dict(STATUS_CHOICES)
TYPE_LABELS = {"trailer": "trailer", "paddle": "paddle / carry-in", "limited": "limited / restricted",
               "needs_review": "needs review", "unknown": "type not stated"}
TYPE_CHOICES = [("", "All access types"), ("trailer", "Trailer launches"), ("paddle", "Paddle / carry-in"),
                ("limited", "Limited / restricted"), ("needs_review", "Needs review")]

EXTRA_CSS = EXTRA_CSS.replace("</style>", """
.sw-group{border-top:1px solid var(--rule,#9aa)}
.sw-group>summary{cursor:pointer;min-height:44px;display:flex;align-items:center;justify-content:space-between;gap:.5rem;font-weight:600;padding:.25rem 0}
.sw-group>summary:focus-visible,.sw-about summary:focus-visible{outline:3px solid #a8803a;outline-offset:2px}
.sw-group>summary .n{font-weight:400;opacity:.8}
.sw-dims{font-size:.85rem;margin:.2rem 0 .8rem}
.sw-dims b{font-weight:600}
[data-find][hidden]{display:none}
</style>""")

FIND_JS = "<script>" + ramp_search.JS.replace("</", "<\\/") + """
(function(){
  /* Live filtering with the shared search rules (ramp_search.py). Search never depends on stored
     state: the form is reset to the server's values on back/forward restores (iPhone Safari). */
  var form=document.getElementById("filters"), q=document.getElementById("q"), live=document.getElementById("sw-live");
  if(!form||!q||!live||!window.CBRampSearch) return;
  var S=window.CBRampSearch, area=form.getAttribute("data-area")||"", statewide=form.getAttribute("data-statewide")||"/ramps";
  var items=[].slice.call(document.querySelectorAll("li[data-find]"));
  var groups=[].slice.call(document.querySelectorAll("details.sw-group"));
  var start=groups.map(function(g){return g.open});
  var reg=document.getElementById("sw-region"), inArea=form.querySelector('input[name="in_area"]');
  var go=document.createElement("p"); go.className="sw-scope"; go.hidden=true; live.parentNode.insertBefore(go, live.nextSibling);
  function run(){
    var raw=q.value.trim(), t=S.norm(raw), n=0;
    items.forEach(function(li){var hit=!t||S.matches(li.getAttribute("data-find"),raw); li.hidden=!hit; if(hit) n++;});
    groups.forEach(function(g,i){
      var vis=g.querySelectorAll("li[data-find]:not([hidden])").length;
      g.hidden=!!t&&vis===0; g.open=t?vis>0:start[i];
      var c=g.querySelector("summary .n"); if(c) c.textContent=vis;
    });
    if(!t){live.textContent=""; go.hidden=true; return;}
    if(area){
      live.textContent=n+(n===1?" site in ":" sites in ")+area+" match \u201c"+raw+"\u201d. Press Search to look across all of North Carolina.";
      go.innerHTML=""; var a=document.createElement("a"); a.className="btn sw-allnc"; a.setAttribute("data-allnc",""); a.href=statewide+"?q="+encodeURIComponent(raw); a.textContent="Search all North Carolina ramps for \u201c"+raw+"\u201d"; go.appendChild(a); go.hidden=false;
    } else {
      live.textContent=n+(n===1?" site matches":" sites match")+" \u201c"+raw+"\u201d.";
      go.hidden=true;
    }
  }
  var mv=document.getElementById("sw-viewmap");
  function mapHref(){
    if(!mv) return; var u=[], v=q.value.trim(), ty=document.getElementById("sw-type"), st=document.getElementById("sw-status");
    if(v) u.push("q="+encodeURIComponent(v).replace(/%20/g,"+"));
    if(ty&&/^(trailer|paddle|limited|needs_review)$/.test(ty.value)) u.push("type="+ty.value);
    if(st&&st.value) u.push("status="+st.value);
    mv.setAttribute("href","/ramps/map"+(u.length?"?"+u.join("&"):""));
  }
  q.addEventListener("input",function(){run();mapHref();});
  form.addEventListener("change",mapHref);
  if(reg&&inArea) reg.addEventListener("change",function(){inArea.checked=!!reg.value;});
  addEventListener("pageshow",function(e){ if(e.persisted){ form.reset(); run(); mapHref(); } });
  run();
})();
</script>"""


def region_applies(f) -> bool:
    """An area from a homepage link scopes browsing, not searching (Ed t559u, t560u).

    Typing a search looks across all of North Carolina unless the visitor chose
    "Only search in this area" (in_area=1). This was the root cause of "every search fails
    until Reset": homepage links carry ?region=..., the Area select inside the collapsed
    "More filters" was pre-filled from it, and every search was silently limited to that area.
    """
    return bool(f["region"]) and (not ramp_search.norm(f["q"]) or f.get("in_area", False))


def classify(data, f):
    """Group the filtered records by access type (one dimension). Status is a separate filter."""
    secs = {k: [] for k in TYPE_LABELS}
    flag_keys = ("camper_only", "non_gas_only", "size_limited", "no_parking")
    scoped = region_applies(f)
    for r in data["records"]:
        if scoped and not region_match(r, f["region"]):
            continue
        if not ramp_search.matches(ramp_search.record_haystack(r), f["q"]):
            continue
        if f["type"] and r.get("type_dimension") != f["type"]:
            continue
        if f["water"] and _water_group(r) != f["water"]:
            continue
        if f.get("status") and (r.get("access_status") or {}).get("code") != f["status"]:
            continue
        if any(f.get(k) for k in flag_keys) and not any(f.get(k) and (r.get("flags") or {}).get(k) for k in flag_keys):
            continue
        secs[r.get("type_dimension") or "unknown"].append(r)
    return secs


SECTION_TEXT = {
    "trailer": ("Trailer launches", "Public launch lanes for trailered boats, from official records. Each card shows its official status; none is a live check."),
    "paddle": ("Paddle and carry-in access", "NCWRC records these as portable-boat access (steps, slides or small launches). Not for trailered boats."),
    "limited": ("Limited or restricted access", "Verified sites with a hard restriction: camper-only, non-gas only, size-limited, no parking, or motorboats restricted."),
    "needs_review": ("Needs review", "Official sources are incomplete, conflicting, or do not confirm a general public launch."),
    "unknown": ("Access type not stated", "The official record does not say what kind of launch this is."),
}


def _find_text(r) -> str:
    """Same haystack the server and the statewide map search (ramp_search)."""
    return ramp_search.record_haystack(r)


def _card(r, *, public: bool = False) -> str:
    return rf.card_html(r, public=public).replace("<li>", f'<li data-find="{rf.esc(_find_text(r))}">', 1)


def _section(kind, rows, *, group_by_area=False, collapsed=False, sub=None, public: bool = False):
    if not rows:
        return ""
    title, lead = SECTION_TEXT[kind]
    if sub:
        title = f"{title}: {sub}"
    if group_by_area:
        order = [k for k, _ in REGION_CHOICES if k]
        buckets = {}
        for r in rows:
            buckets.setdefault(r["area"], []).append(r)
        parts = []
        for area in sorted(buckets, key=lambda a: order.index(a) if a in order else 99):
            items = "".join(_card(r, public=public) for r in buckets[area])
            label = REGION_LABELS.get(area, area)
            parts.append(f'<details class="sw-group" data-area="{rf.esc(area)}"{"" if collapsed else " open"}>'
                         f'<summary>{rf.esc(label)} <span class="n">{len(buckets[area])}</span></summary>'
                         f'<ul class="list">{items}</ul></details>')
        inner = "".join(parts)
    else:
        inner = f'<ul class="list">{"".join(_card(r, public=public) for r in rows)}</ul>'
    return (f'<section class="rf-section" data-section="{rf.esc(kind)}">'
            f'<h2>{rf.esc(title)} ({len(rows)})</h2><p class="section-lead">{rf.esc(lead)}</p>{inner}</section>')


def _select(name, label, choices, current):
    opts = "".join(f'<option value="{rf.esc(v)}"{" selected" if v == current else ""}>{rf.esc(t)}</option>' for v, t in choices)
    return f'<label for="sw-{name}">{rf.esc(label)}<select id="sw-{name}" name="{name}">{opts}</select></label>'


def _about(data) -> str:
    rules = (data.get("meta") or {}).get("rules") or {}
    return f"""<details class="sw-about"><summary>How this list is built</summary><ul>
<li>Sources: our manually verified Ramp Finder records (checked Nov 22, 2026) plus every NCWRC Boating Access Area in the official feature service. Our verified details win field by field; NCWRC only fills blanks, and each page says which.</li>
<li>Nothing is guessed. A blank official field shows as not stated. It never means an amenity is there or that a site is open.</li>
<li>Two separate labels: access type (trailer, paddle or carry-in, limited or restricted, needs review) and official status (open as listed, temporarily closed, partly open, status unclear, unknown). A closed launch keeps its access type.</li>
<li>Regions: new NCWRC sites join Crystal Coast (including Emerald Isle), Wilmington, Topsail, Nags Head or Hatteras when they are within {rules.get("region_radius_mi", 20):g} miles, straight line, of that region's homepage anchor. The nearest anchor wins. One documented exception: Rodanthe, on Hatteras Island, is listed with Hatteras. Falls Lake, Jordan Lake and Neuse River sites go by their NCWRC waterbody. Everything else is grouped by NCWRC's Coastal, Piedmont or Mountain region.</li>
<li>Upper Neuse means launches at or upstream of the Goldsboro access, matching the homepage Neuse region. Lower Neuse is everything below Goldsboro to Pamlico Sound. That includes freshwater, brackish and tidal launches.</li>
<li>Fishing-rules classification (inland, coastal or joint) is NCWRC's regulatory label, not a salinity reading. Fresh, brackish or salt is shown separately. It is marked verified where our research recorded it and inferred otherwise. Inferred freshwater means inland fishing waters more than {rules.get("fresh_min_tide_mi", 15):g} miles from any NOAA tide-prediction station. Inferred tidal means coastal fishing waters within {rules.get("tidal_max_tide_mi", 10):g} miles of one. Anything else is not determined.</li>
<li>Status comes from the official record or a dated official notice, whichever is newer. It is never a live open/closed check.</li>
</ul></details>"""


def _dims_html(rows) -> str:
    from collections import Counter
    t = Counter(r.get("type_dimension") or "unknown" for r in rows)
    s = Counter((r.get("access_status") or {}).get("code") or "not_stated" for r in rows)
    tt = " · ".join(f"{t[k]} {TYPE_LABELS[k]}" for k in TYPE_LABELS if t[k])
    ss = " · ".join(f"{s[k]} {STATUS_LABELS[k].lower()}" for k, _ in STATUS_CHOICES if k and s[k])
    return f'<p class="sw-dims" data-dims><b>Access type:</b> {rf.esc(tt)}.<br><b>Official status:</b> {rf.esc(ss)}.</p>'



def _unmatched_notices_html(data, area: str | None) -> str:
    """Official notices that do not attach to a listed ramp, with source and date."""
    parts = []
    for n in (data.get("meta") or {}).get("unmatched_official_notices") or []:
        key = n.get("key") or ""
        # Parkers Creek (and any later unmatched Jordan notice) belong on the Jordan Lake section.
        if area == "jordan-lake" and "jordan" not in key:
            continue
        if area is None and "jordan" in key:
            continue  # statewide already shows Parkers Creek inside the Jordan banner; the standalone item is on the Jordan page
        parts.append(
            f'<aside class="context region-notice" data-notice="unmatched" data-notice-key="{rf.esc(key)}">'
            f'<p><strong>Official notice not tied to a listed ramp.</strong> {rf.esc(n.get("text") or "")} '
            f'This site is not in our directory, so the official notice is shown here rather than on a ramp page.</p>'
            f'<p class="notice-meta"><a href="{rf.esc(n.get("source_url") or "")}" rel="noopener noreferrer">'
            f'{rf.esc(n.get("source_name") or n.get("source_url") or "")}</a>. '
            f'Last checked {rf.esc(n.get("as_of_label") or "")}.</p></aside>'
        )
    return "".join(parts)


def _url(base: str, params: dict) -> str:
    from urllib.parse import urlencode
    keep = {k: v for k, v in params.items() if v not in ("", None, False)}
    return base + ("?" + urlencode(keep) if keep else "")


def _params(f, region_param) -> dict:
    p = {"q": f["q"], "region": region_param, "in_area": "1" if f.get("in_area") else "",
         "type": f["type"], "status": f.get("status", ""), "water": f["water"]}
    for k, _ in rf.FLAG_FILTERS:
        if f.get(k):
            p[k] = "1"
    return p


def _active_filters(f, region_param, scoped, base) -> list:
    """Every filter that is narrowing the list, each with a link that removes just that filter."""
    p = _params(f, region_param)
    out = []
    def drop(*keys):
        return _url(base, {k: v for k, v in p.items() if k not in keys})
    if scoped and region_param:
        out.append(("Area: " + REGION_LABELS.get(region_param, region_param), drop("region", "in_area")))
    if f["type"]:
        out.append(("Type: " + dict(TYPE_CHOICES).get(f["type"], f["type"]), drop("type")))
    if f.get("status"):
        out.append(("Status: " + STATUS_LABELS.get(f["status"], f["status"]), drop("status")))
    if f["water"]:
        out.append(("Water: " + dict(WATER_CHOICES).get(f["water"], f["water"]), drop("water")))
    for k, lbl in rf.FLAG_FILTERS:
        if f.get(k) and k in ("camper_only", "non_gas_only", "size_limited", "no_parking"):
            out.append((lbl, drop(k)))
    return out


def _active_html(active, f, region_param, scoped, base) -> str:
    bits = []
    if active:
        chips = "".join(f'<a class="sw-chip" href="{rf.esc(href)}" aria-label="Remove filter: {rf.esc(lbl)}">{rf.esc(lbl)} <span aria-hidden="true">×</span></a>'
                        for lbl, href in active)
        bits.append(f'<div class="sw-active" data-active-filters role="group" aria-label="Active filters"><span class="sw-al">Active filters:</span>{chips}</div>')
    if f["q"] and region_param and region_param in REGION_LABELS and not scoped:
        p = _params(f, region_param); p["in_area"] = "1"
        bits.append(f'<p class="sw-scope" data-scope="statewide">Searching all of North Carolina for “{rf.esc(f["q"])}”. '
                    f'<a href="{rf.esc(_url(base, p))}">Only search {rf.esc(REGION_LABELS[region_param])}</a></p>')
    return "".join(bits)


def render_list(data, q, *, public: bool = False) -> str:
    base = "/ramps" if public else BASE
    tok = rf.STATEWIDE_BASE.set(base)
    try:
        return _render_list(data, q, public=public, base=base)
    finally:
        rf.STATEWIDE_BASE.reset(tok)


def _render_list(data, q, *, public: bool = False, base: str = BASE) -> str:
    f = parse(q)
    f["status"] = _first(q, "status") if _first(q, "status") in STATUS_LABELS else ""
    region_param = f["region"]
    scoped = region_applies(f)
    region = region_param if scoped else ""  # the area shapes this page only when it applies
    meta = data.get("meta") or {}
    checked = meta.get("date_checked", "")
    refresh = meta.get("refresh") or {}
    honest = ""
    nearest_html = ""
    unknown = bool(region and region not in REGION_LABELS)
    secs = {k: [] for k in TYPE_LABELS} if unknown else classify(data, f)
    shown = [r for k in TYPE_LABELS for r in secs[k]]
    if unknown:
        honest = (f'<aside class="sw-honest" data-honest="unknown-region"><p>We don’t have a ramp area called '
                  f'“{rf.esc(region)}”. Nothing is filtered here, so no ramps are shown for it.</p>'
                  f'<p><a href="{base}">See the statewide ramp list</a></p></aside>')
    elif region == "emerald-isle":
        honest = ('<aside class="sw-honest" data-honest="emerald-isle"><p>Emerald Isle ramps are listed with the '
                  'Crystal Coast. This list shows the whole Crystal Coast area.</p></aside>')
    elif region == "hatteras":
        anc = (meta.get("rules") or {}).get("anchors", {}).get("hatteras") or {}
        near = []
        if anc:
            near = [x for x in nearest_verified(data, anc.get("lat"), anc.get("lon"), n=6) if x[1]["area"] != "hatteras"][:3]
        cards = []
        for d, r in near:
            r2 = dict(r)
            r2["_distance_note"] = f"{d:.0f} mi straight line from {anc.get('label', 'Cape Hatteras')}"
            cards.append(rf.card_html(r2, public=public))
        honest = (f'<aside class="sw-honest" data-honest="hatteras"><p><strong>Hatteras Island coverage is limited.</strong> '
                  'The one verified public trailer launch we list is Rodanthe, a Dare County ramp in the NCWRC program. '
                  'It is included by a documented exception because it sits on Hatteras Island but outside our 20-mile '
                  f'Hatteras radius from {rf.esc(anc.get("label", "Cape Hatteras"))}. National Park Service sound-side areas '
                  'and other island launches are not listed until an official source verifies ownership, public access, '
                  'coordinates and restrictions.</p></aside>')
        if cards and not (f["q"] or f["type"] or f["water"] or f["status"]):
            nearest_html = (f'<section class="rf-section" data-section="nearest-outside"><h2>Nearest verified launches outside this area</h2>'
                       f'<ul class="list">{"".join(cards)}</ul></section>')
    grouped = not region and not f["q"]
    body = []
    if region == "neuse-river":
        for seg, sub in (("upper", "Upper Neuse, Falls Dam to Goldsboro"), ("lower", "Lower Neuse, below Goldsboro (brackish and tidal launches included)")):
            for kind in TYPE_LABELS:
                body.append(_section(kind, [r for r in secs[kind] if r.get("neuse_segment") == seg], sub=sub, public=public))
    else:
        for kind in TYPE_LABELS:
            body.append(_section(kind, secs[kind], group_by_area=grouped, collapsed=grouped, public=public))
    active = _active_filters(f, region_param, scoped, base)
    if not shown and not unknown:
        if active:
            body.append('<div class="empty sw-empty" data-empty="ramps"><p>No ramps match with these filters.</p>'
                        f'<p><a class="btn sw-allnc" data-allnc href="{rf.esc(_url(base, {"q": f["q"]}))}">Search all North Carolina ramps</a></p></div>')
        else:
            body.append('<p class="empty" data-empty="ramps">No ramps match that search. Try a town, county, ramp name or waterbody.</p>')
    ctx = ""
    if region in ("falls-lake", "jordan-lake"):
        ctx = rf.lake_context_html(data, region)
    if region == "jordan-lake":
        ctx = rf.region_notice_html(data, "jordan-lake") + _unmatched_notices_html(data, "jordan-lake") + ctx
    rechecked = (data.get("meta") or {}).get("notices_rechecked") or ""
    if rechecked:
        ctx = (f'<p class="sw-dims" data-notices-rechecked>Official closure notices (NC State Parks, NCWRC) rechecked '
               f'{rf.esc(rechecked)}. Each launch shows its own official status and source.</p>') + ctx
    refresh_html = ""
    if refresh.get("status") == "kept_last_known_good":
        refresh_html = (f'<aside class="sw-refresh-bad" data-refresh="kept-last-known-good"><p>The latest official data refresh '
                        f'({rf.esc(refresh.get("attempted_at", ""))}) did not pass its checks: {rf.esc(refresh.get("reason", ""))}. '
                        f'This list still shows the last good data, checked {rf.esc(refresh.get("data_from", ""))}.</p></aside>')
    checks = "".join(
        f'<label><input type="checkbox" name="{rf.esc(k)}" value="1"{" checked" if f.get(k) else ""}> {rf.esc(lbl)}</label>'
        for k, lbl in rf.FLAG_FILTERS if k in ("camper_only", "non_gas_only", "size_limited", "no_parking"))
    where = ("the Crystal Coast (Emerald Isle is listed here)" if region == "emerald-isle"
             else REGION_LABELS.get(region, "") if region else "")
    count_line = (f'<p class="count">Showing {len(shown)} {"site" if len(shown) == 1 else "sites"}'
                  f'{" in " + rf.esc(where) if where else ""}.</p>' + (_dims_html(shown) if shown else "")) if not unknown else ""
    n_total = len(data["records"])
    map_link = ""
    if public and launch_flags.ramp_map_public():
        mp = {"q": f["q"], "type": f["type"] if f["type"] in ("trailer", "paddle", "limited", "needs_review") else "", "status": f.get("status", "")}
        map_link = (f'<a class="btn sw-viewmap" id="sw-viewmap" href="{rf.esc(_url("/ramps/map", mp))}">'
                    '<svg viewBox="0 0 20 20" width="18" height="18" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"><path d="M2.5 5l5-2 5 2 5-2v12l-5 2-5-2-5 2z"/><path d="M7.5 3v12M12.5 5v12"/></svg>'
                    '&nbsp;View map</a>')
    kicker = "" if public else '<p class="kicker">Private data preview · Phase 1.1</p>'
    desc = (f"{n_total} public boating access sites across North Carolina, from official sources only, "
            f"checked {checked}. Search by name, town, county or waterbody. Not a live open/closed board.")
    return rf._shell("Ramp Finder: North Carolina", f"""
{kicker}
<h1>Ramp Finder: North Carolina</h1>
<p class="lead">{n_total} public boating access sites statewide, from official sources only, checked {rf.esc(checked)}. This is not a live open/closed board.</p>
{refresh_html}
<form class="filters" id="filters" method="get" action="{base}" role="search" autocomplete="off" data-area="{rf.esc(REGION_LABELS.get(region, "") if region else "")}" data-statewide="{rf.esc(base)}">
  <label class="q-lab" for="q">Search by ramp name, town, county or waterbody</label>
  <input type="search" id="q" name="q" value="{rf.esc(f["q"])}" placeholder="e.g. Kerr, Wilmington, Neuse" autocomplete="off" aria-describedby="sw-live">
  <p id="sw-live" class="sw-dims" aria-live="polite"></p>
  <details class="sw-about"><summary>More filters</summary>
  <div class="sw-select">
    {_select("region", "Area", REGION_CHOICES, region_param if region_param in REGION_LABELS else "")}
    <label class="sw-inarea"><input type="checkbox" name="in_area" value="1"{" checked" if f.get("in_area") else ""}> Only search in the selected area</label>
    {_select("type", "Access type", TYPE_CHOICES, f["type"])}
    {_select("status", "Official status", STATUS_CHOICES, f["status"])}
    {_select("water", "Water", WATER_CHOICES, f["water"])}
  </div>
  <fieldset class="opt-filters"><legend>Restrictions</legend><div class="opt-row">{checks}</div></fieldset>
  </details>
  <div class="actions"><button type="submit">Search</button>
  <button type="reset" onclick="location.href='{base}'; return false;">Reset</button>{map_link}</div>
</form>
{_active_html(active, f, region_param, scoped, base)}
{honest}
{count_line}
{ctx}
{"".join(body)}
{nearest_html}
{_about(data)}
""", extra_head=EXTRA_CSS, extra_script=FIND_JS, public=public,
              canonical=(rf.SITE_ORIGIN + _list_canonical(q)) if public else None,
              description=desc if public else None)


def _list_canonical(q: dict) -> str:
    region = (q or {}).get("region") or [""]
    region = region[0] if isinstance(region, list) else region
    return "/ramps?region=" + region if region else "/ramps"


def render_detail(data, rec, *, public: bool = False) -> str:
    base = "/ramps" if public else BASE
    tok = rf.STATEWIDE_BASE.set(base)
    try:
        html_out = rf.render_detail(data, rec, public=public)
    finally:
        rf.STATEWIDE_BASE.reset(tok)
    return html_out.replace("</head>", EXTRA_CSS + "\n</head>", 1)


def resolve_request(path: str, query: dict, *, public: bool = False):
    base = "/ramps" if public else BASE
    raw = path.rstrip("/") or base
    data = load()
    if raw == base:
        return 200, "text/html; charset=utf-8", render_list(data, query or {}, public=public)
    if not public:
        # Phase 2 statewide map (private). Public /ramps/map is routed by the server behind PUBLIC_RAMP_MAP.
        import ramp_map
        for suffix in ramp_map.SUFFIXES:
            if raw == base + "/map" + suffix:
                return ramp_map.resolve(suffix, public=False)
    if raw.startswith(base + "/"):
        rid = raw[len(base) + 1:].strip("/")
        rec = by_id(rid, data)
        if not rec:
            return 404, "text/plain", "not found"
        return 200, "text/html; charset=utf-8", render_detail(data, rec, public=public)
    return 404, "text/plain", "not found"
