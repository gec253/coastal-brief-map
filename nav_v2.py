"""Site-wide masthead and navigation, version 2 (Ed t453u, Nov 24 2026). PRIVATE PREVIEW.

Off by default. Active only when NAV_V2=1/true/on/yes is set, or for a browser holding the
preview cookie. When inactive, server responses are byte-identical to production: apply() is
never called.

Presentation only. The transform rewrites the header of each public page into one shared
masthead (the homepage nameplate lettering, compact on secondary pages) and one phone-first
section nav, and upgrades the homepage Guides links into destination cards. It never touches
conditions data, alerts, fishing reports, ramp records or Morning Brief content. Functional
header parts (theme toggle, print button, region picker, #nav-brief) are moved, not rebuilt,
so their existing scripts keep working.
"""
from __future__ import annotations

import datetime as _dt
import html
import os
import re
from urllib.parse import parse_qs, urlparse

import folio_entry
import launch_flags
from theme_toggle import _blocks, _split_sel

ENV = "NAV_V2"
_TRUE = ("1", "true", "on", "yes")


def env_on() -> bool:
    return (os.environ.get(ENV) or "").strip().lower() in _TRUE


def active(preview_ok) -> bool:
    """NAV_V2 env flag, or the preview cookie (callable so the HMAC runs only when needed)."""
    if env_on():
        return True
    try:
        return bool(preview_ok())
    except Exception:
        return False


def _esc(s, quote: bool = True) -> str:
    return html.escape(str(s or ""), quote=quote)


# ---------------------------------------------------------------------------------------------
# Which page is this, and which section is current.

def page_key(path: str) -> str | None:
    """Section key for a public HTML route, or None when the page is not restyled."""
    p = (path or "/").rstrip("/") or "/"
    if p in ("/", "/dashboard", "/lake"):
        return "conditions"
    if p == "/brief":
        return "brief"
    if p == "/reports" or p.startswith("/reports/"):
        return "biting"
    if p == "/ramps" or (p.startswith("/ramps/") and not p.startswith("/ramps/map")):
        return "ramps"
    if p == "/catch-wall":
        return "catch"
    if p == "/coastal-life":
        return "life"
    if p in ("/photos", "/feedback"):
        return ""
    return None


_RID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _rid(query: str) -> str:
    rid = ((parse_qs(query or "").get("region") or [""])[0] or "").strip().lower()
    return rid if (_RID.match(rid) and len(rid) <= 40) else ""


def _brief_on() -> bool:
    try:
        import site_chrome
        return site_chrome.brief_on()
    except Exception:
        return False


FRESH = ("falls-lake", "jordan-lake", "neuse-river")

# Small inline icons (stroke = currentColor). No icon font, no library.
_I = {
    "home": '<path d="M3 10.5 12 3l9 7.5"/><path d="M5.5 9v11h13V9"/><path d="M10 20v-6h4v6"/>',
    "fish": ('<path d="M3 12c3.2-4.3 8.6-5.6 13-2.6l3.5-2.9v11l-3.5-2.9c-4.4 3-9.8 1.7-13-2.6z"/>'
             '<circle cx="8.6" cy="11" r=".9" fill="currentColor" stroke="none"/>'),
    "ramp": ('<path d="M2 20h20"/><path d="M3 20 15 11h6"/><path d="M5 16.5c1.3.9 2.7.9 4 0s2.7-.9 4 0 2.7.9 4 0"/>'
             '<path d="M15.5 8.5h4.5l-1.2 2.5h-3.3z"/>'),
    "gauge": ('<circle cx="12" cy="12" r="9"/><path d="M12 12l4.5-4.5"/><path d="M12 5v1.5M5 12h1.5M17.5 12H19M7 7l1 1"/>'
              '<circle cx="12" cy="12" r="1.2" fill="currentColor" stroke="none"/>'),
    "chev": '<path d="M9 5l7 7-7 7"/>',
    "wave": '<path d="M2 9c2.5-2 5-2 7.5 0s5 2 7.5 0 3.5-1.6 5-1"/><path d="M2 15c2.5-2 5-2 7.5 0s5 2 7.5 0 3.5-1.6 5-1"/>',
    "lake": ('<path d="M3 12l4.5-5 3 3.5 3-4.5 6.5 6"/><path d="M2 16c2.5-2 5-2 7.5 0s5 2 7.5 0 3.5-1.6 5-1"/>'
             '<path d="M5 20c2-1.4 4-1.4 6 0s4 1.4 6 0"/>'),
}


def _icon(name: str, cls: str) -> str:
    return ('<svg class="%s" viewBox="0 0 24 24" aria-hidden="true" focusable="false" fill="none" '
            'stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">%s</svg>'
            % (cls, _I[name]))


def nav_items(current: str, rid: str = "") -> list[tuple[str, str, str]]:
    """(key, href, label) in display order. Gated items follow their public launch flags."""
    cond = "/?region=%s" % rid if rid else "/"
    items = [("conditions", cond, "Conditions")]
    if _brief_on():
        items.append(("brief", "/brief?region=%s" % (rid or "crystal-coast"), "Morning Brief"))
    if launch_flags.whats_biting_public():
        items.append(("biting", folio_entry.whats_biting_entry(rid or None)[0], "What\u2019s Biting?"))
    if launch_flags.ramps_public():
        items.append(("ramps", folio_entry.ramps_entry(rid or None)[0], "Find a Ramp"))
    items += [("catch", "/catch-wall", "Catch Wall"), ("life", "/coastal-life", "Coastal Life")]
    return items


def nav_html(current: str, rid: str = "") -> str:
    out = []
    for key, href, label in nav_items(current, rid):
        attrs = ' aria-current="page"' if key == current else ""
        if key == "brief":
            attrs += ' id="nav-brief"'  # brief-link.js keeps this on the visitor's region
        icon = _icon("home", "cbn-i") if key == "conditions" else ""
        out.append('<a class="cbn-a cbn-%s" href="%s"%s>%s<span>%s</span></a>'
                   % (key, _esc(href), attrs, icon, _esc(label, False)))
    return '<nav class="cbn" aria-label="Sections">%s</nav>' % "".join(out)


RULES = ('<div class="cbm-rules" aria-hidden="true"><span class="cbm-rule-heavy"></span>'
         '<span class="cbm-rule-brass"></span></div>')


def _today_et() -> _dt.date:
    try:
        from zoneinfo import ZoneInfo
        return _dt.datetime.now(ZoneInfo("America/New_York")).date()
    except Exception:
        return _dt.date.today()


def _date_html() -> str:
    d = _today_et()
    return ('<p class="cbm-date"><time datetime="%s">%s</time></p>'
            % (d.isoformat(), d.strftime("%a \u00b7 %b ") + str(d.day) + d.strftime(", %Y")))


def masthead_html(current: str, rid: str, *, tools: str = "", picker: str = "", heading_tag: str = "p") -> str:
    """Compact secondary masthead: navy ear (region picker or date, tools), ivory plate with the
    homepage nameplate lettering and double rule, then the section nav."""
    left = ('<div class="cbm-pick">%s</div>' % picker) if picker else _date_html()
    tag = "h1" if heading_tag == "h1" else "p"
    return ('<header class="cbm" data-nav-v2>'
            '<div class="cbm-ear"><div class="cbm-ear-in">%s<div class="cbm-tools">%s</div></div></div>'
            '<div class="cbm-plate"><%s class="cbm-name"><a href="/">The Coastal Brief</a></%s>%s%s</div>'
            '</header>' % (left, tools, tag, tag, RULES, nav_html(current, rid)))


# ---------------------------------------------------------------------------------------------
# Water choice (homepage, Ed t454u): Saltwater / Freshwater segments plus an area picker, built from
# the page's own "Choose your water" list, so region ids, names and public gating stay exactly as served.

_RR = re.compile(rb'<nav class="rr" aria-label="Choose your water">(.*?)</nav>', re.S)
_RR_G = re.compile(rb'<div class="rr-g rr-(saltwater|freshwater)">(.*?)</div></div>', re.S)
_RR_A = re.compile(rb'<a href="/\?region=([a-z0-9-]+)"( aria-current="page")?>([^<]+)</a>')


def regions_from_page(data: bytes) -> list[tuple[str, list[tuple[str, str, bool]]]]:
    """[(water, [(rid, name, current), ...]), ...] from the homepage region list, or []."""
    m = _RR.search(data)
    if not m:
        return []
    out = []
    for g in _RR_G.finditer(m.group(1)):
        items = [(a.group(1).decode(), html.unescape(a.group(3).decode("utf-8")), bool(a.group(2)))
                 for a in _RR_A.finditer(g.group(2))]
        if items:
            out.append((g.group(1).decode(), items))
    return out


def water_html(groups, rid: str) -> str:
    if not groups:
        return ""
    cur_water, cur_rid = "", ""
    for water, items in groups:
        for r, _, c in items:
            if c or (rid and r == rid):
                cur_water, cur_rid = water, r
    if not cur_water:
        cur_water = "saltwater"
    seg = []
    for water, items in groups:
        label = "Saltwater" if water == "saltwater" else "Freshwater"
        # Same targets as the old homepage tabs: Saltwater opens /, Freshwater the first lake.
        href = "/" if water == "saltwater" else "/?region=%s" % items[0][0]
        cur = ""
        if water == cur_water:
            cur = ' aria-current="true"'
            href = "/?region=%s" % cur_rid if cur_rid else href  # current water keeps its area
        icon = _icon("wave" if water == "saltwater" else "lake", "cbw-i")
        seg.append('<a class="cbw-s cbw-%s" href="%s"%s>%s<span>%s</span></a>' % (water, _esc(href), cur, icon, label))
    opts = []
    for water, items in groups:
        label = "Saltwater" if water == "saltwater" else "Freshwater"
        o = "".join('<option value="%s"%s>%s</option>' % (_esc(r), " selected" if r == cur_rid else "", _esc(n, False))
                    for r, n, _ in items)
        opts.append('<optgroup label="%s">%s</optgroup>' % (label, o))
    return ('<section class="cbw" aria-label="Choose your water">'
            '<div class="cbw-seg" role="group" aria-label="Water">%s</div>'
            '<form class="cbw-pick" action="/" method="get"><label class="cbw-k" for="cbw-r">Area</label>'
            '<div class="cbw-row"><select id="cbw-r" name="region">%s</select>'
            '<button type="submit" class="cbw-go">Show</button></div></form></section>'
            % ("".join(seg), "".join(opts)))


# ---------------------------------------------------------------------------------------------
# Guides (homepage): destination cards.

def _fresh(rid: str) -> bool:
    return rid in FRESH


def guides_html(rid: str) -> str:
    cards = []

    def card(cls, href, icon, title, sub, note=""):
        n = '<span class="cbg-note">%s</span>' % _esc(note, False) if note else ""
        cards.append(
            '<a class="cbg-card %s" href="%s"><span class="cbg-ic">%s</span>'
            '<span class="cbg-tx"><span class="cbg-t">%s</span><span class="cbg-s">%s</span>%s</span>%s</a>'
            % (cls, _esc(href), _icon(icon, "cbg-svg"), _esc(title, False), _esc(sub, False), n,
               _icon("chev", "cbg-chev")))

    if launch_flags.whats_biting_public():
        href, _, note = folio_entry.whats_biting_entry(rid or None)
        card("cbg-biting", href, "fish", "What\u2019s Biting?", "Regional fishing reports", note)
    if launch_flags.ramps_public():
        href, _, note = folio_entry.ramps_entry(rid or None)
        card("cbg-ramps", href, "ramp", "Find a Ramp", "Boat launches and water access", note)
    if _fresh(rid):
        card("cbg-dash", "/lake?region=%s" % rid, "gauge", "Full Dashboard", "All lake and river readings")
    else:
        card("cbg-dash", "/dashboard?region=%s" % rid if rid else "/dashboard", "gauge", "Full Dashboard",
             "Map, tides and all readings")
    return ('<section class="cbg" aria-labelledby="cbg-h"><h2 class="cbg-h" id="cbg-h">Guides</h2>'
            '<div class="cbg-l">%s</div></section>' % "".join(cards))


# ---------------------------------------------------------------------------------------------
# CSS. One small inline block; same fonts the pages already load (Fraunces, Source Sans 3).

CSS = """
.cbm,.cbg,.cbn,.cbw{--cb-navy:#071C29;--cb-ivory:#F6F1E7;--cb-brass:#C4A36A;--cb-brass-ink:#7A5D2C;--cb-ink:#0B2A3D;--cb-ink2:#40596A;
--cb-page:#F6F1E7;--cb-chip:#FFFDF8;--cb-edge:rgba(11,42,61,.22);--cb-serif:"Fraunces","Fraunces Fallback",Georgia,"Times New Roman",serif;
--cb-ui:"Source Sans 3","Source Sans 3 Fallback","Segoe UI",Helvetica,Arial,sans-serif}
.cbm{display:block;background:var(--cb-page);color:var(--cb-ink);margin:0;padding:0;border:0;position:relative;z-index:20;text-align:left}
.cbm *{box-sizing:border-box}
.cbm-ear{background:linear-gradient(180deg,#0A2133,#071C29);color:#EDE5D3;border-bottom:1px solid rgba(196,163,106,.55)}
.cbm-ear-in{max-width:1264px;margin:0 auto;display:flex;align-items:center;justify-content:space-between;gap:8px;min-height:48px;padding:2px max(12px,env(safe-area-inset-left))}
.cbm-date{margin:0;color:#EDE5D3;font:600 .7rem/1.2 var(--cb-ui);letter-spacing:.16em;text-transform:uppercase;font-variant-numeric:lining-nums;white-space:nowrap}
.cbm-tools{display:flex;align-items:center;gap:6px;flex:none}
.cbm-tools:empty{display:none}
.cbm-pick{flex:1 1 auto;min-width:0;position:relative}
.cbm .region-nav,.cbm .region-nav-wrap{display:block;min-height:0;padding:0;margin:0;position:relative}
.cbm .rn-line{display:none}
.cbm .rn-btn{display:inline-flex;align-items:center;gap:6px;min-height:44px;max-width:100%;width:auto;margin:0;padding:0 12px;border:1px solid rgba(237,229,211,.45);border-radius:999px;background:transparent;color:#F6F1E7;font:600 .95rem/1 var(--cb-ui);cursor:pointer}
.cbm .rn-btn:hover{background:rgba(196,163,106,.16)}
.cbm .rn-k{display:none}
.cbm .rn-name{max-width:12.5rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.cbm .rn-menu{left:0;right:auto;top:calc(100% + 6px);width:min(360px,calc(100vw - 24px));z-index:60}
.cbm .theme-toggle,.cbm .mb-print{appearance:none;display:inline-flex;align-items:center;justify-content:center;gap:6px;min-width:44px;min-height:44px;width:auto;height:auto;margin:0;padding:0 12px;border:1px solid rgba(237,229,211,.45);border-radius:999px;background:transparent;color:#F6F1E7;font:700 .7rem/1 var(--cb-ui);letter-spacing:.1em;text-transform:uppercase;cursor:pointer;position:static;box-shadow:none}
.cbm .theme-toggle svg,.cbm .mb-print svg{width:18px;height:18px}
.cbm .theme-toggle:hover,.cbm .mb-print:hover{background:rgba(196,163,106,.18)}
.cbm .theme-toggle:focus-visible,.cbm .mb-print:focus-visible,.cbm .rn-btn:focus-visible,.cbm-name a:focus-visible{outline:3px solid var(--cb-brass);outline-offset:2px}
.cbm-plate{position:relative;isolation:isolate;max-width:1264px;margin:0 auto;padding:10px 12px 12px;text-align:center}
.cbm-plate::before{content:"";position:absolute;left:0;right:0;top:0;height:66px;z-index:-1;pointer-events:none;background:#0E3A57;opacity:.08;
-webkit-mask:url("/branding/masthead-chart.webp") 62% 46%/cover no-repeat;mask:url("/branding/masthead-chart.webp") 62% 46%/cover no-repeat}
.cbm-name{margin:0;font:600 1.95rem/1 var(--cb-serif);letter-spacing:-.012em;color:var(--cb-navy);text-transform:none;font-style:normal}
.cbm-name a{color:inherit;text-decoration:none;display:inline-block;padding:4px 2px;min-height:44px;line-height:36px}
.cbm-rules{display:grid;gap:1px;margin:2px 0 0}
.cbm-rule-heavy{display:block;height:2px;background:var(--cb-navy)}
.cbm-rule-brass{display:block;height:1.6px;background:var(--cb-brass)}
.cbn{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:6px;margin:10px 0 0;padding:0}
.cbn-a{display:flex;align-items:center;justify-content:center;gap:5px;min-height:46px;padding:4px 6px;border:1px solid var(--cb-edge);border-radius:10px;background:var(--cb-chip);color:var(--cb-ink);text-decoration:none;font:600 .95rem/1.1 var(--cb-ui);letter-spacing:.005em;text-align:center;-webkit-tap-highlight-color:transparent}
.cbn-a span{min-width:0}
.cbn-i{width:16px;height:16px;flex:none;color:var(--cb-brass-ink)}
.cbn-a:hover{border-color:var(--cb-brass);background:#FBF6EA}
.cbn-a:focus-visible{outline:3px solid var(--cb-brass);outline-offset:2px}
.cbn-a[aria-current]{background:var(--cb-navy);border-color:var(--cb-navy);color:var(--cb-ivory);box-shadow:inset 0 -3px 0 var(--cb-brass)}
.cbn-a[aria-current] .cbn-i{color:var(--cb-brass)}
@media (min-width:761px){
.cbm-ear-in{padding:2px 32px}
.cbm-plate{padding:14px 32px 14px}
.cbm-plate::before{height:84px}
.cbm-name{font-size:2.8rem}
.cbm-name a{line-height:52px}
.cbm-rules{margin-top:6px}
.cbn{grid-template-columns:repeat(6,minmax(0,1fr));max-width:980px;margin:12px auto 0}
.cbm .rn-name{max-width:18rem}
}
@media (max-width:359px){.cbn-a{font-size:.88rem}.cbn-i{display:none}.cbm-name{font-size:1.8rem}}
.mh-hybrid .cbn{margin:6px 0 10px}
@media (min-width:761px){.mh-hybrid .cbn{margin:10px auto 12px}}
html[data-mastchart] .mh-hybrid .mh-plate::before{bottom:auto;height:96px}
.cbw{margin:12px 0 4px;padding:0 12px;display:grid;grid-template-columns:minmax(0,1fr);gap:8px}
.cbw-seg{display:grid;grid-template-columns:1fr 1fr;gap:0;border:1.5px solid var(--cb-navy);border-radius:12px;overflow:hidden;background:var(--cb-chip)}
.cbw-s{display:flex;align-items:center;justify-content:center;gap:8px;min-height:48px;padding:4px 8px;color:var(--cb-ink);text-decoration:none;font:700 1rem/1.1 var(--cb-ui);letter-spacing:.01em}
.cbw-s+.cbw-s{border-left:1.5px solid var(--cb-navy)}
.cbw-i{width:20px;height:20px;flex:none;color:var(--cb-brass-ink)}
.cbw-s[aria-current]{background:var(--cb-navy);color:var(--cb-ivory);box-shadow:inset 0 -3px 0 var(--cb-brass)}
.cbw-s[aria-current] .cbw-i{color:var(--cb-brass)}
.cbw-s:focus-visible,.cbw-go:focus-visible,.cbw-row select:focus-visible{outline:3px solid var(--cb-brass);outline-offset:2px}
.cbw-pick{margin:0;min-width:0}
.cbw-k{display:block;margin:0 0 3px;font:700 .72rem/1.2 var(--cb-ui);letter-spacing:.12em;text-transform:uppercase;color:var(--cb-ink2)}
.cbw-row{display:flex;gap:8px;min-width:0}
.cbw-row select{flex:1 1 0;min-width:0;width:100%;text-overflow:ellipsis;min-height:48px;padding:0 12px;border:1px solid var(--cb-edge);border-radius:10px;background:var(--cb-chip);color:var(--cb-ink);font:600 1rem/1.2 var(--cb-ui)}
.cbw-go{flex:none;min-width:72px;min-height:48px;padding:0 16px;border:1px solid var(--cb-navy);border-radius:10px;background:var(--cb-navy);color:var(--cb-ivory);font:700 1rem/1 var(--cb-ui);cursor:pointer}
@media (min-width:761px){.cbw{padding:0;grid-template-columns:minmax(0,1fr) minmax(0,1fr);align-items:end;gap:16px;margin:14px 0 4px}}
.cbg{margin:18px 0 20px;padding:0 12px}
.cbg-h{margin:0 0 8px;font:600 1.35rem/1.15 var(--cb-serif);letter-spacing:-.005em;color:var(--cb-ink);padding-bottom:6px;border-bottom:3px double var(--cb-brass)}
.cbg-l{display:grid;gap:10px}
.cbg-card{display:flex;align-items:center;gap:14px;min-height:76px;padding:12px 14px;border-radius:14px;background:linear-gradient(180deg,#0E2A3D,#071C29);border:1px solid #071C29;color:var(--cb-ivory);text-decoration:none;box-shadow:0 1px 0 rgba(196,163,106,.35) inset,0 6px 16px -10px rgba(7,28,41,.6)}
.cbg-card:hover{border-color:var(--cb-brass)}
.cbg-card:focus-visible{outline:3px solid var(--cb-brass);outline-offset:3px}
.cbg-ic{flex:none;display:grid;place-items:center;width:48px;height:48px;border-radius:50%;border:1.5px solid var(--cb-brass);color:#E2C68F;background:rgba(196,163,106,.10)}
.cbg-svg{width:26px;height:26px}
.cbg-tx{flex:1 1 auto;min-width:0;display:grid;gap:2px}
.cbg-t{font:600 1.28rem/1.1 var(--cb-serif);letter-spacing:-.005em;color:#FFFDF8}
.cbg-s{font:600 .95rem/1.25 var(--cb-ui);color:#E3D7BF}
.cbg-note{font:500 .85rem/1.25 var(--cb-ui);color:#C9D6DE}
.cbg-chev{flex:none;width:22px;height:22px;color:var(--cb-brass)}
@media (min-width:761px){.cbg{padding:0}.cbg-l{grid-template-columns:repeat(3,minmax(0,1fr))}}
@media (prefers-color-scheme:dark){
:where(html:not([data-theme="light"])) .cbm,:where(html:not([data-theme="light"])) .cbn{--cb-page:#071C29;--cb-ink:#F3EEE3;--cb-ink2:#B9C7CF;--cb-chip:rgba(246,241,231,.05);--cb-edge:rgba(246,241,231,.24)}
:where(html:not([data-theme="light"])) .cbm-name{color:#F6F1E7}
:where(html:not([data-theme="light"])) .cbm-plate::before{background:#E6DCC8;opacity:.10}
:where(html:not([data-theme="light"])) .cbm-rule-heavy{background:#C9BCA5}
:where(html:not([data-theme="light"])) .cbn-a:hover{background:rgba(196,163,106,.14)}
:where(html:not([data-theme="light"])) .cbn-i{color:var(--cb-brass)}
:where(html:not([data-theme="light"])) .cbn-a[aria-current]{background:#F6F1E7;border-color:#F6F1E7;color:#071C29}
:where(html:not([data-theme="light"])) .cbn-a[aria-current] .cbn-i{color:#7A5D2C}
:where(html:not([data-theme="light"])) .cbg{--cb-ink:#F3EEE3}
:where(html:not([data-theme="light"])) .cbg-card{background:linear-gradient(180deg,#123247,#0B2536);border-color:rgba(196,163,106,.45)}
:where(html:not([data-theme="light"])) .cbw{--cb-ink:#F3EEE3;--cb-ink2:#B9C7CF;--cb-chip:rgba(246,241,231,.05);--cb-edge:rgba(246,241,231,.3);--cb-navy:#C9BCA5}
:where(html:not([data-theme="light"])) .cbw-s[aria-current]{background:#F6F1E7;color:#071C29}
:where(html:not([data-theme="light"])) .cbw-s[aria-current] .cbw-i{color:#7A5D2C}
:where(html:not([data-theme="light"])) .cbw-i{color:var(--cb-brass)}
:where(html:not([data-theme="light"])) .cbw-go{background:#F6F1E7;color:#071C29;border-color:#F6F1E7}
:where(html:not([data-theme="light"])) .cbw-row select{background:#0E2433;color-scheme:dark}
}
html[data-theme="dark"] .cbm,html[data-theme="dark"] .cbn{--cb-page:#071C29;--cb-ink:#F3EEE3;--cb-ink2:#B9C7CF;--cb-chip:rgba(246,241,231,.05);--cb-edge:rgba(246,241,231,.24)}
html[data-theme="dark"] .cbm-name{color:#F6F1E7}
html[data-theme="dark"] .cbm-plate::before{background:#E6DCC8;opacity:.10}
html[data-theme="dark"] .cbm-rule-heavy{background:#C9BCA5}
html[data-theme="dark"] .cbn-a:hover{background:rgba(196,163,106,.14)}
html[data-theme="dark"] .cbn-i{color:var(--cb-brass)}
html[data-theme="dark"] .cbn-a[aria-current]{background:#F6F1E7;border-color:#F6F1E7;color:#071C29}
html[data-theme="dark"] .cbn-a[aria-current] .cbn-i{color:#7A5D2C}
html[data-theme="dark"] .cbg{--cb-ink:#F3EEE3}
html[data-theme="dark"] .cbg-card{background:linear-gradient(180deg,#123247,#0B2536);border-color:rgba(196,163,106,.45)}
html[data-theme="dark"] .cbw{--cb-ink:#F3EEE3;--cb-ink2:#B9C7CF;--cb-chip:rgba(246,241,231,.05);--cb-edge:rgba(246,241,231,.3);--cb-navy:#C9BCA5}
html[data-theme="dark"] .cbw-s[aria-current]{background:#F6F1E7;color:#071C29}
html[data-theme="dark"] .cbw-s[aria-current] .cbw-i{color:#7A5D2C}
html[data-theme="dark"] .cbw-i{color:var(--cb-brass)}
html[data-theme="dark"] .cbw-go{background:#F6F1E7;color:#071C29;border-color:#F6F1E7}
html[data-theme="dark"] .cbw-row select{background:#0E2433;color-scheme:dark}
@media print{.cbn,.cbm-ear{display:none}}
"""

_FONT = ('@font-face{font-family:"Fraunces";font-style:normal;font-weight:400 700;font-display:optional;'
         'src:url("/fonts/fraunces-var.woff2") format("woff2")}')


def _keep(sel: str, home: bool) -> bool:
    """Homepage keeps nav + Guides rules; secondary pages keep masthead + nav rules."""
    if home:
        return ".cbn" in sel or ".cbg" in sel or ".cbw" in sel or ".mh-hybrid" in sel
    return ".cbm" in sel or ".cbn" in sel


def _min(css: str, home: bool) -> str:
    out = []
    for pre, body in _blocks(css):
        p = pre.strip()
        if body is None:
            continue
        if p.startswith("@media"):
            inner = _min(body, home)
            if inner:
                out.append("%s{%s}" % (re.sub(r"\s+", " ", p), inner))
            continue
        sels = [x.strip() for x in _split_sel(p) if _keep(x, home)]
        if sels:
            out.append("%s{%s}" % (",".join(sels), re.sub(r";?\s*$", "", re.sub(r"\n", "", body.strip()))))
    return "".join(out)


def style_tag(need_font: bool, home: bool = False) -> bytes:
    css = _min(CSS, home)
    return ('<style id="cb-nav-v2">%s%s</style>' % (_FONT if need_font else "", css)).encode("utf-8")


# ---------------------------------------------------------------------------------------------
# HTML surgery helpers (bytes in, bytes out).

def _balanced(data: bytes, start: int, tag: bytes) -> int:
    """End index (exclusive) of the element of `tag` opening at `start`, counting nesting."""
    op, cl = b"<" + tag, b"</" + tag + b">"
    depth, i = 0, start
    while True:
        a = data.find(op, i)
        c = data.find(cl, i)
        if c < 0:
            raise ValueError("unbalanced %r" % tag)
        if 0 <= a < c and data[a + len(op):a + len(op) + 1] in (b" ", b">", b"\n", b"\t"):
            depth += 1
            i = a + len(op)
            continue
        depth -= 1
        i = c + len(cl)
        if depth == 0:
            return i


def _grab(data: bytes, pattern: bytes, tag: bytes) -> bytes:
    m = re.search(pattern, data)
    if not m:
        return b""
    return data[m.start():_balanced(data, m.start(), tag)]


def _tools(block: bytes) -> bytes:
    out = b""
    for pat in (rb'<button[^>]*class="mb-print"', rb'<button[^>]*id="theme-toggle"'):
        out += _grab(block, pat, b"button")
    return out


def _inject_css(data: bytes, home: bool = False) -> bytes:
    need_font = b'font-family:"Fraunces"' not in data and b"fraunces-var.woff2" not in data
    tag = style_tag(need_font, home)
    i = data.find(b"</head>")
    if i < 0:
        raise ValueError("no </head>")
    return data[:i] + tag + data[i:]


def _apply_home(data: bytes, rid: str) -> bytes:
    i = data.find(b'<nav class="mh-sec"')
    if i < 0:
        raise ValueError("home nav not found")
    j = _balanced(data, i, b"nav")
    data = data[:i] + nav_html("conditions", rid).encode("utf-8") + data[j:]
    water = water_html(regions_from_page(data), rid).encode("utf-8")
    if water:
        k = data.find(b'<main id="main">')
        if k >= 0:
            k += len(b'<main id="main">')
            data = data[:k] + water + data[k:]
    g = data.find(b'<nav class="folio-guides"')
    new = guides_html(rid).encode("utf-8")
    if g >= 0:
        data = data[:g] + new + data[_balanced(data, g, b"nav"):]
    else:  # no launch flag on: place the Guides after the Conditions section
        c = data.find(b'<section class="cg')
        if c >= 0:
            e = _balanced(data, c, b"section")
            data = data[:e] + new + data[e:]
    return data


def _apply_identity(data: bytes, cur: str, rid: str) -> bytes:
    i = data.find(b"<header class=\"site\" data-identity")
    j = _balanced(data, i, b"header")
    head = data[i:j]
    k = data.find(b'<div class="compact-bar', j)
    if k < 0 or k - j > 200:
        raise ValueError("compact bar not found")
    kend = _balanced(data, k, b"div")
    bar = data[k:kend]
    picker = _grab(bar, rb'<div class="region-nav"', b"div")
    tag = "h1" if b"<h1" in head else "p"
    mh = masthead_html(cur, rid, tools=_tools(head).decode("utf-8"), picker=picker.decode("utf-8"), heading_tag=tag)
    sentinel = b'<div class="sticky-sentinel" id="sticky-sentinel" aria-hidden="true"></div>'
    return data[:i] + mh.encode("utf-8") + (sentinel if sentinel in data[j:k] else b"") + data[kend:]


def _apply_simple(data: bytes, cur: str, rid: str, opener: bytes) -> bytes:
    i = data.find(opener)
    j = _balanced(data, i, b"header")
    head = data[i:j]
    tag = "h1" if b"<h1" in head else "p"
    mh = masthead_html(cur, rid, tools=_tools(head).decode("utf-8"), heading_tag=tag)
    return data[:i] + mh.encode("utf-8") + data[j:]


def apply(data: bytes, request_path: str) -> bytes:
    """Rewrite one public HTML page. Unknown pages and unknown layouts are returned unchanged."""
    u = urlparse(request_path or "/")
    cur = page_key(u.path)
    if cur is None or not data or b"data-nav-v2" in data:
        return data
    rid = _rid(u.query)
    if b'<header class="mh mh-hybrid">' in data:
        out = _apply_home(data, rid)
    elif b"<header class=\"site\" data-identity" in data:
        out = _apply_identity(data, cur, rid)
    elif b'<header class="wb-top">' in data:
        out = _apply_simple(data, cur, rid, b'<header class="wb-top">')
    elif b'<header class="rf-top">' in data:
        out = _apply_simple(data, cur, rid, b'<header class="rf-top">')
    elif b'<header class="mh">' in data:
        out = _apply_simple(data, cur, rid, b'<header class="mh">')
    else:
        return data
    return _inject_css(out, home=b'<header class="mh mh-hybrid">' in data)
