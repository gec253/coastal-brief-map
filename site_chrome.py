"""Shared public chrome for small server-rendered pages (feedback, not-found pages), and the
"which Morning Brief does this region use" rule shared by the header link and the tools link.

Launch audit Nov 19 2026 (Ed approved items 4, 5, 7 and 11, t334u). Presentation only: no data,
no new regions, no private ids. The colours and type match the feedback page's navy brand bar."""
from __future__ import annotations

import html

# Regions without a public brief use the nearest region that has one (same coast or same basin).
NEAREST_BRIEF = {
    "wilmington": "crystal-coast",
    "emerald-isle": "crystal-coast",
    "topsail": "crystal-coast",
    "nags-head": "hatteras",
    "jordan-lake": "falls-lake",
    "neuse-river": "falls-lake",
}
DEFAULT_BRIEF = "crystal-coast"


def _esc(s, quote: bool = False) -> str:
    return html.escape(str(s or ""), quote=quote)


def brief_on() -> bool:
    try:
        import brief
        return bool(brief.flag_on())
    except Exception:
        return False


def fresh_on() -> bool:
    try:
        import freshwater
        return bool(freshwater.flag_on())
    except Exception:
        return False


def public_brief_regions() -> list[str]:
    """Regions with a public Morning Brief right now (no preview cookie)."""
    try:
        import brief
        return list(brief.enabled_regions(include_fresh=fresh_on()))
    except Exception:
        return [DEFAULT_BRIEF]


def brief_target(rid: str | None) -> tuple[str, bool]:
    """(region whose brief to link, True when that is the region's own brief)."""
    avail = public_brief_regions()
    rid = (rid or "").strip()
    if rid in avail:
        return rid, True
    near = NEAREST_BRIEF.get(rid)
    if near in avail:
        return near, False
    return (DEFAULT_BRIEF if DEFAULT_BRIEF in avail or not avail else avail[0]), False


def region_name(rid: str) -> str:
    """Public display name of a public region, or "" (private and unknown ids are never named)."""
    try:
        import conditions
        for r in conditions.listed_regions(preview=False).get("regions") or []:
            if r.get("id") == rid:
                return r.get("name") or ""
    except Exception:
        pass
    try:
        import freshwater
        if fresh_on():
            r = (freshwater.regions() or {}).get(rid) or {}
            if r.get("enabled") and r.get("previewReady") and not r.get("draft") and not freshwater.is_preview_region(rid):
                return r.get("name") or ""
    except Exception:
        pass
    return ""


NAV_CSS = """
.mh{background:#071C29;color:#F6F1E7;padding:12px 16px 0}
.mh-brand{display:inline-block;color:#F6F1E7;text-decoration:none;font:600 1.15rem/1 Fraunces,Georgia,serif;padding-bottom:6px}
.mh-sec{display:flex;flex-wrap:wrap;gap:0 4px;margin:0 -8px;border-top:1px solid rgba(196,163,106,.45)}
.mh-sec a{display:inline-flex;align-items:center;min-height:44px;padding:0 8px;color:#F6F1E7;text-decoration:none;font:600 .86rem/1 "Source Sans 3",source-sans-3,system-ui,sans-serif;letter-spacing:.02em}
.mh-sec a:hover{text-decoration:underline;text-decoration-color:#C4A36A;text-underline-offset:4px}
.mh-sec a[aria-current]{box-shadow:inset 0 -3px 0 #C4A36A}
.mh-sec a:focus-visible,.mh-brand:focus-visible{outline:3px solid #D9BE86;outline-offset:-3px}
"""


def nav_html(current: str = "", brief_rid: str | None = None) -> str:
    """Brand bar plus the standard section nav (Saltwater, Freshwater, Morning Brief, Catch Wall, Map & tides)."""
    links = [("salt", "/", "Saltwater"),
             ("fresh", "/?region=falls-lake" if fresh_on() else "/lake", "Freshwater")]
    if brief_on():
        links.append(("brief", "/brief?region=%s" % brief_target(brief_rid)[0], "Morning Brief"))
    links += [("catch", "/catch-wall", "Catch Wall"), ("maps", "/dashboard", "Map &amp; tides")]
    a = "".join('<a href="%s"%s>%s</a>' % (_esc(h, True), ' aria-current="page"' if k == current else "", t)
                for k, h, t in links)
    return ('<header class="mh"><a class="mh-brand" href="/">The Coastal Brief</a>'
            '<nav class="mh-sec" aria-label="Sections">%s</nav></header>' % a)


PAGE_CSS = """
:root{--paper:#FFFDF8;--page:#F7F3EA;--ink:#102030;--ink-2:#40596A;--brass:#A7864F;--line-2:#C9D4D6}
html,body{margin:0;background:var(--page);color:var(--ink);font:16px/1.45 "Source Sans 3",source-sans-3,system-ui,sans-serif}
a.skip{position:absolute;left:-999px}
a.skip:focus{left:12px;top:12px;background:#fff;padding:8px;z-index:10}
.nf{max-width:640px;margin:0 auto;padding:24px 16px 56px}
.nf h1{font:600 1.5rem/1.2 Fraunces,Georgia,serif;margin:0 0 10px;padding-bottom:8px;border-bottom:3px double var(--brass)}
.nf p{margin:0 0 12px;color:var(--ink)}
.nf ul{list-style:none;margin:8px 0 16px;padding:0;display:grid;gap:8px}
.nf li a{display:flex;align-items:center;min-height:44px;padding:0 14px;border:1px solid var(--line-2);border-radius:6px;background:var(--paper);color:var(--ink);text-decoration:none;font-weight:600}
.nf li a:hover{border-color:var(--brass)}
.nf li a:focus-visible{outline:3px solid var(--brass);outline-offset:2px}
.nf .nf-k{font:600 .72rem/1 "Barlow Condensed",system-ui,sans-serif;letter-spacing:.16em;text-transform:uppercase;color:var(--ink-2);margin:18px 0 0}
@media (prefers-color-scheme:dark){
  :root{--paper:#0E2433;--page:#071C29;--ink:#F3EEE3;--ink-2:#B9C7CF;--line-2:#29506B}
}
"""


def page(title: str, heading: str, body_html: str, current: str = "", brief_rid: str | None = None) -> bytes:
    """A small public page (noindex) with the brand bar, section nav and the given body."""
    out = """<!DOCTYPE html>
<html lang="en" data-page="notice">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="robots" content="noindex, nofollow">
<title>%s \u2014 The Coastal Brief</title>
<meta name="color-scheme" content="light dark">
<link rel="icon" href="/branding/favicon.svg" type="image/svg+xml">
<style>%s%s</style>
</head>
<body>
<a class="skip" href="#main">Skip to content</a>
%s
<main class="nf" id="main"><h1>%s</h1>%s</main>
</body>
</html>
""" % (_esc(title), PAGE_CSS, NAV_CSS, nav_html(current, brief_rid), _esc(heading), body_html)
    return out.encode("utf-8")


def _brief_links(exclude: str = "") -> str:
    items = []
    for rid in public_brief_regions():
        if rid == exclude:
            continue
        nm = region_name(rid) or rid.replace("-", " ").title()
        items.append('<li><a href="/brief?region=%s">Morning Brief \u00b7 %s</a></li>' % (_esc(rid, True), _esc(nm)))
    return "<ul>%s</ul>" % "".join(items) if items else ""


def no_brief_page(rid: str) -> bytes:
    """/brief?region=<a region with no public brief>: explain, link the briefs that exist."""
    name = region_name(rid)
    if name:
        near, _own = brief_target(rid)
        near_name = region_name(near) or near
        lead = ("<p>%s does not have its own Morning Brief yet. Live readings for %s are on the "
                '<a href="%s">conditions page</a>. The nearest Morning Brief is %s.</p>'
                % (_esc(name), _esc(name), _esc("/?region=%s" % rid, True), _esc(near_name)))
    else:
        lead = "<p>There is no Morning Brief for that area.</p>"
    body = lead + '<p class="nf-k">Today\u2019s Morning Briefs</p>' + _brief_links()
    return page("No Morning Brief here", "No Morning Brief for this area", body, current="brief", brief_rid=rid if name else None)


def region_not_found_page(api_hint: bool = False) -> bytes:
    """Unknown or not-public region id on / or /dashboard. Never names the id or says whether it exists."""
    links = []
    try:
        import conditions
        for r in conditions.listed_regions(preview=False).get("regions") or []:
            links.append('<li><a href="/?region=%s">%s</a></li>' % (_esc(r["id"], True), _esc(r.get("name") or r["id"])))
    except Exception:
        pass
    try:
        import freshwater
        if fresh_on():
            for rid in sorted(freshwater.regions() or {}):
                nm = region_name(rid)
                if nm:
                    links.append('<li><a href="/?region=%s">%s</a></li>' % (_esc(rid, True), _esc(nm)))
    except Exception:
        pass
    body = ("<p>We could not find that region. It may be misspelled, or it is not on the public site yet.</p>"
            '<p class="nf-k">Choose your water</p><ul>%s</ul>' % "".join(links))
    return page("Region not found", "Region not found", body)
