"""One site-wide theme system: Light, Dark or Auto, on every public page (Ed t468u, Nov 25 2026).

Before this module took over, every page carried its own copy of a two-state "Dark mode" button and
boot script (index.html/app.js, lake.html/lake.js, brief.py, ramp_finder.py, whats_biting.py,
catch-wall.html, wind.html, radar.html), and the public homepage had no control at all and ignored
the saved choice. paint() now runs once, server-side, on every public HTML response:

* one localStorage key, "coastalBrief.theme" (the key every page already used): "light" or "dark"
  is an explicit choice; no value means Auto. Anything else is a stale value and is removed;
* a head boot script, first in <head>, sets html[data-theme] (resolved light|dark) and
  html[data-theme-pref] (light|dark|auto) before first paint, so no page flashes the wrong theme;
* Auto follows prefers-color-scheme and reacts live when the phone switches. There is no sunset or
  time-of-day rule anywhere;
* matchMedia("(prefers-color-scheme: dark)") reports the site theme, so canvases (Wind & Radar
  showcase, viewers) agree with a forced choice; a "cb:theme" window event announces each change;
* inline dark blocks written only for the phone setting (the homepage) are rewritten to also
  respect the explicit choice (rewrite_css);
* one Light / Dark / Auto segmented control (role=radiogroup, arrow keys, 44 px targets) replaces
  each page's old button in place, or sits at the right of the masthead ear where a page had none.
  With NAV_V2 on it lands in the new masthead tools; there is only ever one.
"""
from __future__ import annotations

import re

STORE = "coastalBrief.theme"
_DARK = "@media (prefers-color-scheme:dark)"
SYS = ':where(html:not([data-theme="light"]))'
FORCE = ':where(html[data-theme="dark"])'


def _blocks(css: str):
    """Split CSS into (prelude, body) top-level statements; body is None for ;-terminated at-rules."""
    i, n = 0, len(css)
    while i < n:
        j = i
        while j < n and css[j] not in "{;":
            j += 1
        if j >= n:
            if css[i:].strip():
                yield css[i:], None
            return
        if css[j] == ";":
            yield css[i:j + 1], None
            i = j + 1
            continue
        depth, k = 1, j + 1
        while k < n and depth:
            if css[k] == "{":
                depth += 1
            elif css[k] == "}":
                depth -= 1
            k += 1
        yield css[i:j], css[j + 1:k - 1]
        i = k


def _scope_sel(sel: str, scope: str) -> str:
    s = sel.strip()
    if not s:
        return s
    cond = scope[len(":where("):-1]          # html:not(...) or html[...]
    attr = cond[len("html"):]
    m = re.match(r"^(html|:root)((?:\[[^\]]*\]|:[\w-]+(?:\([^)]*\))?)*)(.*)$", s, re.S)
    if m and (m.group(3) == "" or m.group(3)[0] in " >+~"):
        return "%s%s:where(%s)%s" % (m.group(1), m.group(2), "html" + attr if m.group(1) == "html" else ":root" + attr, m.group(3))
    return "%s %s" % (scope, s)


def _scope(css: str, scope: str) -> str:
    out = []
    for pre, body in _blocks(css):
        p = pre.strip()
        if body is None:
            out.append(pre)
        elif p.startswith("@media") or p.startswith("@supports"):
            out.append("%s{%s}" % (p, _scope(body, scope)))
        elif p.startswith("@"):
            out.append("%s{%s}" % (p, body))
        else:
            out.append("%s{%s}" % (",".join(_scope_sel(x, scope) for x in _split_sel(p)), body))
    return "".join(out)


def _split_sel(p: str):
    parts, depth, cur = [], 0, ""
    for ch in p:
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    parts.append(cur)
    return parts


def rewrite_css(css: str) -> str:
    """System dark unless data-theme=light, plus forced dark for data-theme=dark."""
    out = []
    for pre, body in _blocks(css):
        p = pre.strip()
        if body is not None and re.sub(r"\s+", "", p) == re.sub(r"\s+", "", _DARK):
            out.append("%s{%s}%s" % (_DARK, _scope(body, SYS), _scope(body, FORCE)))
        elif body is None:
            out.append(pre)
        else:
            out.append("%s{%s}" % (p, body))
    out.append(':root[data-theme="light"]{color-scheme:light}:root[data-theme="dark"]{color-scheme:dark}')
    return "".join(out)


PREF_ATTR = "data-theme-pref"
MARK = b"data-cb-theme"

# Head boot: runs before <body> exists. Kept dependency-free and small (about 1.6 KB).
BOOT = ("<script data-cb-theme>(function(){var d=document.documentElement,K=%r,p='auto',L=[],"
        "q=/[?&]theme=(light|dark)\\b/.exec(location.search);q=q&&q[1];"
        "function rd(){var s=null;try{s=localStorage.getItem(K);if(s!==null&&s!=='light'&&s!=='dark'){localStorage.removeItem(K);s=null}}catch(e){}return s||'auto'}"
        "p=rd();var mm=window.matchMedia&&window.matchMedia.bind(window),sys=mm?mm('(prefers-color-scheme: dark)'):null;"
        "function want(){return q||(p==='auto'?(sys&&sys.matches?'dark':'light'):p)}"
        "function dark(){return d.getAttribute('data-theme')==='dark'}"
        "function set(){d.setAttribute('data-theme',want());d.setAttribute(%r,p)}set();"
        "var mq={get matches(){return dark()},media:'(prefers-color-scheme: dark)',onchange:null,"
        "addEventListener:function(t,f){if(t==='change')L.push(f)},removeEventListener:function(t,f){L=L.filter(function(x){return x!==f})},"
        "addListener:function(f){L.push(f)},removeListener:function(f){L=L.filter(function(x){return x!==f})},dispatchEvent:function(){return true}};"
        "function fire(ch){var e={matches:dark(),media:mq.media};if(ch){L.slice().forEach(function(f){try{f(e)}catch(x){}});if(mq.onchange)try{mq.onchange(e)}catch(x){}}"
        "try{window.dispatchEvent(new CustomEvent('cb:theme',{detail:{theme:d.getAttribute('data-theme'),pref:p}}))}catch(x){}}"
        "function go(np,save){if(save){q=null;try{if(np==='auto')localStorage.removeItem(K);else localStorage.setItem(K,np)}catch(e){}}"
        "p=np==='light'||np==='dark'?np:'auto';var was=d.getAttribute('data-theme');set();fire(d.getAttribute('data-theme')!==was)}"
        "if(sys){var h=function(){if(p==='auto')go('auto',false)};if(sys.addEventListener)sys.addEventListener('change',h);else if(sys.addListener)sys.addListener(h)}"
        "window.addEventListener('storage',function(e){if(e.key===K||e.key===null)go(rd(),false)});"
        "window.addEventListener('pageshow',function(e){if(e.persisted)go(rd(),false)});"
        "if(mm)window.matchMedia=function(s){return /prefers-color-scheme:\\s*dark/.test(String(s))?mq:mm(s)};"
        "window.__cbTheme={key:K,dark:dark,fire:function(){fire(true)},pref:function(){return p},set:function(v){go(v,true)}};})();</script>"
        ) % (STORE, PREF_ATTR)

_OPTS = (("light", "Light", '<circle cx="8" cy="8" r="3"/><path d="M8 1.5v1.7M8 12.8v1.7M1.5 8h1.7M12.8 8h1.7M3.4 3.4l1.2 1.2M11.4 11.4l1.2 1.2M3.4 12.6l1.2-1.2M11.4 4.6l1.2-1.2"/>'),
         ("dark", "Dark", '<path d="M13.2 10.1A5.6 5.6 0 0 1 5.9 2.8a5.6 5.6 0 1 0 7.3 7.3z"/>'),
         ("auto", "Auto", '<circle cx="8" cy="8" r="5.6"/><path d="M8 2.4v11.2A5.6 5.6 0 0 0 8 2.4z" fill="currentColor"/>'))


def _radios(icons: bool) -> str:
    out = []
    for v, label, icon in _OPTS:
        on = v == "auto"
        out.append('<button type="button" role="radio" class="cbt-b" data-v="%s" aria-checked="%s" tabindex="%s" '
                   'aria-label="%s theme%s" title="%s">%s<span class="cbt-t">%s</span></button>'
                   % (v, "true" if on else "false", "0" if on else "-1", label,
                      " (follow this device)" if v == "auto" else "",
                      "Auto \u2014 follow this device\u2019s light or dark setting" if v == "auto" else label + " theme",
                      ('<svg class="cbt-i" viewBox="0 0 16 16" aria-hidden="true" focusable="false">%s</svg>' % icon) if icons else "",
                      label))
    return "".join(out)


def control_html(compact: bool = False) -> str:
    """Light / Dark / Auto radio group. Server-rendered with Auto checked; the wiring script and
    the html[data-theme-pref] CSS show the saved choice from first paint.

    compact=True (the full-screen Wind and Radar viewers, whose top bar has room for one 44 px
    button): a single button showing the current choice opens the same three radios."""
    if not compact:
        return ('<div class="cbt" role="radiogroup" aria-label="Color theme" data-cb-theme-control>%s</div>'
                % _radios(False))
    icons = "".join('<svg class="cbt-i" data-v="%s" viewBox="0 0 16 16" aria-hidden="true" focusable="false">%s</svg>'
                    % (v, icon) for v, _l, icon in _OPTS)
    return ('<div class="cbt-menu" data-cb-theme-menu><button type="button" class="cbt-m" aria-haspopup="true" '
            'aria-expanded="false" aria-controls="cbt-pop" aria-label="Color theme: Light, Dark or Auto" title="Color theme">%s</button>'
            '<div class="cbt cbt-pop" id="cbt-pop" role="radiogroup" aria-label="Color theme" data-cb-theme-control hidden>%s</div></div>'
            % (icons, _radios(True)))


CSS = ("<style data-cb-theme>"
       ":root[data-theme=\"light\"]{color-scheme:light}:root[data-theme=\"dark\"]{color-scheme:dark}"
       ".cbt{position:relative;display:inline-flex;align-items:center;flex:none;margin:-5px 0;padding:0 3px;color:inherit;"
       "font:600 11px/1 \"Source Sans 3\",system-ui,-apple-system,\"Segoe UI\",sans-serif;letter-spacing:.07em;text-transform:uppercase}"
       ".cbt::before{content:\"\";position:absolute;left:0;right:0;top:50%;height:30px;margin-top:-15px;border:1px solid currentColor;border-radius:15px;opacity:.42;pointer-events:none}"
       ".cbt-b{appearance:none;-webkit-appearance:none;position:relative;display:inline-flex;align-items:center;justify-content:center;"
       "min-width:44px;min-height:44px;margin:0;padding:0;border:0;background:none;color:inherit;font:inherit;letter-spacing:inherit;"
       "text-transform:inherit;cursor:pointer;-webkit-tap-highlight-color:transparent}"
       ".cbt-b::before{content:\"\";position:absolute;left:1px;right:1px;top:50%;height:24px;margin-top:-12px;border-radius:12px;border:1px solid transparent}"
       ".cbt-t{position:relative;padding:0 6px}.cbt-i{display:none;position:relative;width:15px;height:15px;fill:none;stroke:currentColor;stroke-width:1.6;stroke-linecap:round}"
       "html[data-theme-pref=\"light\"] .cbt-b[data-v=\"light\"]::before,html[data-theme-pref=\"dark\"] .cbt-b[data-v=\"dark\"]::before,"
       "html[data-theme-pref=\"auto\"] .cbt-b[data-v=\"auto\"]::before,html:not([data-theme-pref]) .cbt-b[data-v=\"auto\"]::before"
       "{border-color:currentColor;background:rgba(196,163,106,.22)}"
       ".cbt-b:hover::before{border-color:currentColor}"
       ".cbt-b:focus{outline:none}.cbt-b:focus-visible::before{outline:2px solid currentColor;outline-offset:2px}"
       ".cbt-menu{position:relative;flex:none;display:inline-flex}"
       ".cbt-m{appearance:none;-webkit-appearance:none;display:grid;place-items:center;width:44px;height:44px;margin:0;padding:0;border:0;border-radius:22px;"
       "background:none;color:inherit;cursor:pointer;-webkit-tap-highlight-color:transparent}"
       ".cbt-m .cbt-i{width:20px;height:20px;stroke-width:1.5}"
       "html[data-theme-pref=\"light\"] .cbt-m .cbt-i[data-v=\"light\"],html[data-theme-pref=\"dark\"] .cbt-m .cbt-i[data-v=\"dark\"],"
       "html[data-theme-pref=\"auto\"] .cbt-m .cbt-i[data-v=\"auto\"],html:not([data-theme-pref]) .cbt-m .cbt-i[data-v=\"auto\"]{display:block}"
       ".cbt-m:focus{outline:none}.cbt-m:focus-visible{outline:2px solid currentColor;outline-offset:-2px}"
       ".cbt-pop{position:absolute;right:0;top:100%;z-index:2000;flex-direction:column;align-items:stretch;margin:4px 0 0;padding:4px;"
       "background:#071C29;color:#EDE5D3;border:1px solid rgba(196,163,106,.6);border-radius:14px;box-shadow:0 8px 24px rgba(4,14,22,.35)}"
       ".cbt-pop[hidden]{display:none}.cbt-pop::before{display:none}.cbt-pop .cbt-b{justify-content:flex-start;padding:0 10px 0 6px;gap:2px;white-space:nowrap}"
       ".cbt-pop .cbt-b::before{left:0;right:0;height:36px;margin-top:-18px;border-radius:10px}.cbt-pop .cbt-i{display:block}"
       ".mh-ear-in .cbt{margin-left:auto}.mh-ear-in .mh-date:first-child:not(:only-child){margin:0}"
       "@media (max-width:420px){.mh-ear .mh-date{letter-spacing:.06em}}"
       "header.mh>.cbt{float:right;margin:-6px 0 0 8px}"
       # Dashboard tide-search mini chart (app.js tideCurveSvg) draws with fixed navy presentation
       # attributes, which vanish on its dark panel; CSS outranks them, so dark mode gets light ink.
       "html[data-theme=\"dark\"] .tide-curve polyline{stroke:#A9D6CC}html[data-theme=\"dark\"] .tide-curve line{stroke:#3B6680}"
       "html[data-theme=\"dark\"] .tide-curve circle[fill=\"#0B2A3D\"]{fill:#F3EEE3}"
       "@media print{.cbt{display:none}}"
       "</style>")

SCRIPT = ("<script data-cb-theme>(function(){var T=window.__cbTheme;if(!T)return;var G=[].slice.call(document.querySelectorAll('[data-cb-theme-control]'));"
          "function sync(){var p=T.pref();G.forEach(function(g){[].forEach.call(g.querySelectorAll('.cbt-b'),function(b){var on=b.getAttribute('data-v')===p;"
          "b.setAttribute('aria-checked',on?'true':'false');b.tabIndex=on?0:-1})});"
          "[].forEach.call(document.querySelectorAll('.cbt-m'),function(m){m.setAttribute('aria-label','Color theme: '+p.charAt(0).toUpperCase()+p.slice(1)+'. Change')})}"
          "G.forEach(function(g){var B=[].slice.call(g.querySelectorAll('.cbt-b'));B.forEach(function(b,i){"
          "b.addEventListener('click',function(){T.set(b.getAttribute('data-v'))});"
          "b.addEventListener('keydown',function(e){var k=e.key,n=-1;if(k==='ArrowRight'||k==='ArrowDown')n=(i+1)%B.length;"
          "else if(k==='ArrowLeft'||k==='ArrowUp')n=(i+B.length-1)%B.length;else if(k==='Home')n=0;else if(k==='End')n=B.length-1;"
          "if(n<0)return;e.preventDefault();B[n].focus();T.set(B[n].getAttribute('data-v'))})})});"
          "[].forEach.call(document.querySelectorAll('[data-cb-theme-menu]'),function(w){var m=w.querySelector('.cbt-m'),pop=w.querySelector('.cbt-pop');"
          "function open(o,f){pop.hidden=!o;m.setAttribute('aria-expanded',o?'true':'false');if(o){var c=pop.querySelector('[aria-checked=\"true\"]');if(c)c.focus()}else if(f)m.focus()}"
          "m.addEventListener('click',function(){open(pop.hidden,false)});"
          "pop.addEventListener('click',function(e){if(e.target.closest&&e.target.closest('.cbt-b'))open(false,true)});"
          "w.addEventListener('keydown',function(e){if(e.key==='Escape'&&!pop.hidden){e.preventDefault();open(false,true)}});"
          "document.addEventListener('click',function(e){if(!pop.hidden&&!w.contains(e.target))open(false,false)})});"
          "window.addEventListener('cb:theme',sync);sync()})();</script>")

_STYLE = re.compile(rb"(<style\b[^>]*>)(.*?)(</style>)", re.S)
_HEAD = re.compile(rb"<head\b[^>]*>", re.I)
# Old per-page buttons, replaced in place (the page's own scripts are null-safe without them).
_OLD = (re.compile(rb'<button\b[^>]*\bid="theme-toggle"[^>]*>.*?</button>', re.S),
        re.compile(rb'<button\b[^>]*\bid="w-theme"[^>]*>.*?</button>', re.S),
        re.compile(rb'<button\b[^>]*\bid="mh-theme"[^>]*>.*?</button>', re.S))

_PUBLIC = frozenset(("/", "/index.html", "/dashboard", "/lake", "/brief", "/catch-wall", "/coastal-life",
                     "/photos", "/feedback", "/wind", "/radar", "/reports", "/ramps"))


def page_ok(path: str) -> bool:
    """Public HTML routes that carry the shared theme system."""
    p = (path or "/").rstrip("/") or "/"
    return p in _PUBLIC or p.startswith("/reports/") or p.startswith("/ramps/")


def _rewrite_styles(data: bytes) -> bytes:
    def one(m):
        css = m.group(2).decode("utf-8")
        if "prefers-color-scheme" not in css or "dark" not in css:
            return m.group(0)
        return m.group(1) + rewrite_css(css).encode("utf-8") + m.group(3)
    return _STYLE.sub(one, data)


def _place_control(data: bytes) -> bytes:
    compact = b'id="w-theme"' in data
    ctl = control_html(compact=compact).encode("utf-8")
    placed = False
    for rx in _OLD:
        def sub(m):
            nonlocal placed
            if placed:
                return b""
            placed = True
            return ctl
        data = rx.sub(sub, data)
    if placed:
        return data
    for anchor in (b'<div class="cbm-tools">', b'<div class="mh-ear-in">'):
        i = data.find(anchor)
        if i < 0:
            continue
        if anchor == b'<div class="cbm-tools">':
            j = i + len(anchor)
            return data[:j] + ctl + data[j:]
        # end of the ear's inner row: before the </div> that balances it
        depth, k = 0, i
        while True:
            o = data.find(b"<div", k + 1)
            c = data.find(b"</div>", k + 1)
            if c < 0:
                raise RuntimeError("theme: ear not closed")
            if 0 <= o < c:
                depth += 1
                k = o
                continue
            if depth == 0:
                return data[:c] + ctl + data[c:]
            depth -= 1
            k = c
    m = re.search(rb'<header class="mh">', data)
    if m:  # small notice pages (feedback, not found): top right of the brand bar
        return data[:m.end()] + ctl + data[m.end():]
    m = re.search(rb"<header\b[^>]*>", data)
    if m:
        j = data.find(b"</header>", m.end())
        if j > 0:
            return data[:j] + ctl + data[j:]
    raise RuntimeError("theme: no place for the control")


def paint(data: bytes) -> bytes:
    """Add the shared theme system to one HTML page. Idempotent. Raises if the page has no head,
    body or masthead to hold the control (callers serve the page unchanged)."""
    if not data or MARK in data:
        return data
    m = _HEAD.search(data)
    if not m or b"</body>" not in data:
        raise RuntimeError("theme: page has no <head> or </body>")
    data = _rewrite_styles(data)
    data = _place_control(data)
    m = _HEAD.search(data)
    data = data[:m.end()] + b"\n" + BOOT.encode("utf-8") + CSS.encode("utf-8") + data[m.end():]
    k = data.rindex(b"</body>")
    return data[:k] + SCRIPT.encode("utf-8") + data[k:]


def apply(data: bytes) -> bytes:
    """/preview/home-b (cookie-gated): the same shared system as every public page."""
    if b'<div class="mh-ear-in">' not in data and b"<head>" not in data:
        raise RuntimeError("theme toggle: anchors not found")
    return paint(data)
