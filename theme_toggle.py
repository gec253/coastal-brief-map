"""Homepage day/night toggle on the site-wide theme system (Ed t392u).

The Hybrid homepage paints dark mode only through @media (prefers-color-scheme:dark). This module
lets the saved site preference (localStorage "coastalBrief.theme" = "light" | "dark", the same key
the Morning Brief, Catch Wall, Coastal Life, /wind and /radar use) override the phone setting:

* every dark block in the page's inline <style> tags is rewritten into two zero-specificity copies:
  system dark unless the visitor chose light, and forced dark when the visitor chose dark;
* a head boot script sets html[data-theme] before first paint (no flash) and makes
  matchMedia("(prefers-color-scheme: dark)") follow the choice, so the Wind & Radar canvases agree;
* a compact masthead button (aria-pressed, aria-label, 44 px hit area) flips and saves the choice.

Only /preview/home-b calls apply() today; the public homepage is unchanged until the Concept B merge.
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


BOOT = ("<script>(function(){var d=document.documentElement,K=%r,t=null;"
        "try{t=localStorage.getItem(K)}catch(e){}if(t==='light'||t==='dark')d.setAttribute('data-theme',t);"
        "var mm=window.matchMedia&&window.matchMedia.bind(window);if(!mm)return;var sys=mm('(prefers-color-scheme: dark)'),L=[];"
        "function dark(){var a=d.getAttribute('data-theme');return a?a==='dark':sys.matches}"
        "var q={get matches(){return dark()},media:'(prefers-color-scheme: dark)',onchange:null,"
        "addEventListener:function(ty,f){if(ty==='change')L.push(f)},removeEventListener:function(ty,f){L=L.filter(function(x){return x!==f})},"
        "addListener:function(f){L.push(f)},removeListener:function(f){L=L.filter(function(x){return x!==f})}};"
        "function fire(){var e={matches:dark(),media:q.media};L.forEach(function(f){try{f(e)}catch(x){}});if(q.onchange)try{q.onchange(e)}catch(x){}}"
        "try{sys.addEventListener('change',function(){if(!d.getAttribute('data-theme'))fire()})}catch(e){}"
        "window.matchMedia=function(s){return /prefers-color-scheme:\\s*dark/.test(String(s))?q:mm(s)};"
        "window.__cbTheme={dark:dark,fire:fire,key:K};})();</script>") % STORE

BUTTON = ('<button type="button" class="mh-theme" id="mh-theme" aria-pressed="false" aria-label="Switch to dark mode">'
          '<svg class="mh-theme-i" viewBox="0 0 16 16" aria-hidden="true" focusable="false">'
          '<path class="i-moon" d="M10.9 11.6A5.2 5.2 0 0 1 6.4 3.1a5.3 5.3 0 1 0 6.5 7.6 5 5 0 0 1-2 .9z"/>'
          '<g class="i-sun"><circle cx="8" cy="8" r="2.9"/><path d="M8 1.2v1.9M8 12.9v1.9M1.2 8h1.9M12.9 8h1.9M3.2 3.2l1.3 1.3M11.5 11.5l1.3 1.3M3.2 12.8l1.3-1.3M11.5 4.5l1.3-1.3"/></g>'
          '</svg><span class="mh-theme-t">Dark</span></button>')

SCRIPT = ("<script>(function(){var d=document.documentElement,b=document.getElementById('mh-theme'),T=window.__cbTheme;if(!b||!T)return;"
          "var t=b.querySelector('.mh-theme-t');function sync(){var k=T.dark();b.setAttribute('aria-pressed',k?'true':'false');"
          "b.setAttribute('aria-label',k?'Switch to light mode':'Switch to dark mode');t.textContent=k?'Light':'Dark';d.classList.toggle('is-dark',k)}"
          "sync();window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change',sync);"
          "b.addEventListener('click',function(){var n=T.dark()?'light':'dark';d.setAttribute('data-theme',n);"
          "try{localStorage.setItem(T.key,n)}catch(e){}sync();T.fire()});})();</script>")

_STYLE = re.compile(rb"(<style\b[^>]*>)(.*?)(</style>)", re.S)


def apply(data: bytes) -> bytes:
    """Gated: rewrite dark CSS, add the boot script, the masthead button and its wiring."""
    data = _STYLE.sub(lambda m: m.group(1) + rewrite_css(m.group(2).decode("utf-8")).encode("utf-8") + m.group(3), data)
    if b"<head>" not in data or b'<div class="mh-ear-in">' not in data:
        raise RuntimeError("theme toggle: anchors not found")
    data = data.replace(b"<head>", b"<head>\n" + BOOT.encode("utf-8"), 1)
    i = data.index(b'<div class="mh-ear-in">')
    j = data.index(b"</div>", i) + len(b"</div>")
    data = data[:j] + BUTTON.encode("utf-8") + data[j:]
    k = data.rindex(b"</body>")
    return data[:k] + SCRIPT.encode("utf-8") + data[k:]
