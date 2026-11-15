"""Private Catch Wall redesign preview: /preview/catch-wall (cookie-gated, noindex).

Presentation only. Reads the same approved-photo list the public Catch Wall uses
(catch_wall_public.load_approved) and never writes anything. Uploads, moderation,
the share form and /admin are untouched; "Submit your catch" links to the
existing flow on /catch-wall.
"""
from __future__ import annotations

import html
import json
from pathlib import Path

import sprint_home

ROOT = Path(__file__).resolve().parent
DIR = ROOT / "preview" / "catch-wall"
ROUTE = "/preview/catch-wall"
SUBMIT_HREF = "/catch-wall"  # existing public page; its "Share your catch" button opens the existing form
NO_PHOTOGRAPHER = "Community photo \u00b7 Catch Wall"
VARIANTS = ("400", "800", "1600")

# Mosaic shapes cycle per section. Each is a crop (aspect ratio) plus a placement.
SHAPES = ("pl-a", "pl-b", "pl-c", "pl-d")
CROPS = {"pl-a": (5, 4), "pl-b": (4, 5), "pl-c": (1, 1), "pl-d": (3, 2)}
SIZES = {
    "pl-a": "(min-width: 1000px) 600px, 100vw",
    "pl-b": "(min-width: 1000px) 440px, 78vw",
    "pl-c": "(min-width: 1000px) 380px, 62vw",
    "pl-d": "(min-width: 1000px) 600px, 100vw",
}
SECTIONS = (
    ("salt", "Saltwater", "Sounds, inlets and the coast"),
    ("fresh", "Freshwater", "Lakes, reservoirs and rivers"),
)


def _esc(s) -> str:
    return html.escape("" if s is None else str(s), quote=True)


def is_approved(p: dict) -> bool:
    """The public list is approved-only; also refuse anything that says otherwise."""
    st = p.get("status")
    if st not in (None, "", "approved"):
        return False
    if p.get("approved") is False:
        return False
    src = p.get("src") or {}
    return bool(p.get("id")) and any(str(src.get(k) or "").startswith(("https://", "/")) for k in VARIANTS)


def catch_photos(live: list[dict] | None = None) -> list[dict]:
    if live is None:
        try:
            import catch_wall_public
            live = catch_wall_public.load_approved() or []
        except Exception:
            live = []
    seen, out = set(), []
    for p in live:
        pid = str(p.get("id") or "")
        if pid in seen or p.get("category") != "fishing" or not is_approved(p):
            continue
        seen.add(pid)
        out.append(dict(p))
    return out


def water(p: dict) -> str:
    return "fresh" if p.get("water") == "freshwater" else "salt"


def title(p: dict) -> str:
    return str(p.get("species") or p.get("title") or p.get("location") or "Catch Wall photograph")


def place(p: dict) -> str:
    bits = [b for b in (p.get("location"), p.get("region")) if b and b != title(p)]
    return " \u00b7 ".join(str(b) for b in bits)


def credit(p: dict) -> str:
    """Only stored fields. Never invent a name."""
    if p.get("credit_line"):
        return str(p["credit_line"])
    if p.get("name"):
        return "Photo: %s \u00b7 Catch Wall" % p["name"]
    return NO_PHOTOGRAPHER


def alt(p: dict) -> str:
    if p.get("alt"):
        return str(p["alt"])
    if p.get("species"):
        base = "%s catch" % p["species"]
    else:
        base = "Fishing photograph"
    where = p.get("location") or p.get("region") or ""
    return base + ((" at " + where) if where else "") + ", Catch Wall community photo"


def when(p: dict) -> str:
    return str(p.get("takenOn") or "")


def _srcset(p: dict) -> str:
    src = p.get("src") or {}
    w = int(p.get("w") or 0)
    parts = []
    for k in VARIANTS:
        if src.get(k):
            parts.append("%s %dw" % (_esc(src[k]), min(int(k), w) if w else int(k)))
    return ", ".join(parts)


def _src(p: dict, prefer: str = "800") -> str:
    src = p.get("src") or {}
    for k in (prefer, "800", "1600", "400"):
        if src.get(k):
            return str(src[k])
    return ""


def crop(shape: str, w: int, h: int) -> tuple[int, int]:
    """Varied crops, but never fight the photograph's orientation."""
    tall = h > w * 1.1
    if shape == "pl-a":
        return (4, 5) if tall else (5, 4)
    if shape == "pl-b":
        return (4, 5) if tall else (4, 3)
    if shape == "pl-d":
        return (1, 1) if tall else (3, 2)
    return CROPS[shape]


def _caption(p: dict, n: int) -> str:
    bits = ['<span class="pl-no" aria-hidden="true">%02d</span>' % n,
            '<span class="pl-t">%s</span>' % _esc(title(p))]
    if place(p):
        bits.append('<span class="pl-p">%s</span>' % _esc(place(p)))
    if when(p):
        bits.append('<span class="pl-d"><time>%s</time></span>' % _esc(when(p)))
    bits.append('<span class="pl-cr">%s</span>' % _esc(credit(p)))
    return "".join(bits)


def plate(p: dict, i: int, n: int, eager: bool) -> str:
    shape = SHAPES[(n - 1) % len(SHAPES)]
    w, h = int(p.get("w") or 1600), int(p.get("h") or 1200)
    cw, ch = crop(shape, w, h)
    load = 'loading="eager" fetchpriority="high"' if eager else 'loading="lazy"'
    img = (
        '<img src="%s" srcset="%s" sizes="%s" width="%d" height="%d" alt="%s" %s decoding="async">'
        % (_esc(_src(p)), _srcset(p), SIZES[shape], w, h, _esc(alt(p)), load)
    )
    return (
        '<figure class="pl %s" style="--crop:%d / %d">'
        '<a class="pl-open" href="%s" data-i="%d" aria-label="Open photo: %s">'
        '<span class="pl-frame">%s</span></a>'
        '<figcaption class="pl-cap">%s</figcaption></figure>'
    ) % (shape, cw, ch, _esc(_src(p, "1600")), i, _esc(title(p) + (", " + place(p) if place(p) else "")),
         img, _caption(p, n))


def _count(n: int) -> str:
    return "%d %s" % (n, "photo" if n == 1 else "photos")


def body_html(photos: list[dict]) -> str:
    groups = {k: [p for p in photos if water(p) == k] for k, _, _ in SECTIONS}
    order = [p for k, _, _ in SECTIONS for p in groups[k]]
    index = {id(p): i for i, p in enumerate(order)}
    chips = "".join(
        '<a class="chip chip-%s" href="#sec-%s"><span class="chip-k">%s</span><span class="chip-n">%s</span></a>'
        % (k, k, _esc(label), _esc(_count(len(groups[k])))) for k, label, _ in SECTIONS if groups[k]
    )
    intro = (
        '<section class="cw-head" aria-labelledby="cw-h">'
        '<p class="kicker"><span class="dm dm-sq" aria-hidden="true"></span>Community photographs \u00b7 Fishing</p>'
        '<h1 id="cw-h" class="cw-h">The Catch Wall</h1>'
        '<p class="cw-dek">Catches from North Carolina water, from the sounds to the reservoirs, shown as anglers sent them. '
        'Every photograph is reviewed before it appears here.</p>'
        '<div class="cw-act"><nav class="chips" aria-label="Jump to water type">%s</nav>'
        '<a class="cw-submit" href="%s">Submit your catch <span aria-hidden="true">\u2192</span></a></div>'
        '<svg class="brass" viewBox="0 0 1200 4" preserveAspectRatio="none" aria-hidden="true" focusable="false">'
        '<rect width="1200" height="4" fill="url(#cw-brass)"/></svg>'
        '</section>'
    ) % (chips, SUBMIT_HREF)
    secs = []
    first = True
    for k, label, sub in SECTIONS:
        items = groups[k]
        if not items:
            continue  # no empty sections or placeholder slots
        plates = []
        for n, p in enumerate(items, start=1):
            plates.append(plate(p, index[id(p)], n, eager=first and n == 1))
        first = False
        secs.append(
            '<section class="ws ws-%s" id="sec-%s" aria-labelledby="ws-%s-h">'
            '<header class="ws-head"><p class="ws-k"><span class="ws-dm" aria-hidden="true"></span>%s</p><h2 class="ws-h" id="ws-%s-h">%s</h2>'
            '<p class="ws-n">%s</p></header><div class="ws-plates">%s</div></section>'
            % (k, k, k, _esc(label), k, _esc(sub), _esc(_count(len(items))), "".join(plates))
        )
    if not secs:
        secs.append('<p class="cw-none" role="status">Photographs are unavailable right now. Please try again shortly.</p>')
    foot = (
        '<aside class="cw-foot" aria-labelledby="cw-f-h"><h2 id="cw-f-h" class="cw-f-h">Have a catch from Carolina water?</h2>'
        '<p>Send the photograph with the species and where you caught it. We review every picture before it appears, '
        'and we credit you by name if you give one.</p>'
        '<a class="cw-submit" href="%s">Submit your catch <span aria-hidden="true">\u2192</span></a></aside>'
    ) % SUBMIT_HREF
    return intro + '<div class="ws-wrap">' + "".join(secs) + "</div>" + foot, order


def dialog_html() -> str:
    return (
        '<dialog class="lb" id="lb" aria-labelledby="lb-t">'
        '<div class="lb-in"><div class="lb-bar">'
        '<p class="lb-pos" id="lb-pos" aria-live="polite"></p>'
        '<button type="button" class="lb-btn" id="lb-prev" aria-label="Previous photo">\u2190</button>'
        '<button type="button" class="lb-btn" id="lb-next" aria-label="Next photo">\u2192</button>'
        '<button type="button" class="lb-btn lb-x" id="lb-close" aria-label="Close photo">\u00d7</button></div>'
        '<figure class="lb-fig"><img id="lb-img" alt="" width="1600" height="1200" decoding="async">'
        '<figcaption><h2 class="lb-t" id="lb-t"></h2><p class="lb-p" id="lb-p"></p><p class="lb-cr" id="lb-cr"></p></figcaption>'
        '</figure></div></dialog>'
    )


LB_JS = r"""
(function(){
  var P=window.__CWP||[],d=document.getElementById('lb');if(!d||!d.showModal)return;
  var img=document.getElementById('lb-img'),t=document.getElementById('lb-t'),pl=document.getElementById('lb-p'),
      cr=document.getElementById('lb-cr'),pos=document.getElementById('lb-pos'),cur=0,opener=null;
  function show(i){cur=(i+P.length)%P.length;var p=P[cur];
    img.width=p.w;img.height=p.h;img.src=p.src;img.srcset=p.srcset;img.sizes='(min-width:1000px) 70vw, 100vw';img.alt=p.alt;
    t.textContent=p.title;pl.textContent=p.place;pl.hidden=!p.place;cr.textContent=p.credit;
    pos.textContent='Photo '+(cur+1)+' of '+P.length;
    document.getElementById('lb-prev').hidden=document.getElementById('lb-next').hidden=P.length<2;}
  document.addEventListener('click',function(e){var a=e.target.closest&&e.target.closest('.pl-open');if(!a)return;
    e.preventDefault();opener=a;show(+a.dataset.i);d.showModal();document.getElementById('lb-close').focus();});
  document.getElementById('lb-close').onclick=function(){d.close();};
  document.getElementById('lb-prev').onclick=function(){show(cur-1);};
  document.getElementById('lb-next').onclick=function(){show(cur+1);};
  d.addEventListener('click',function(e){if(e.target===d)d.close();});
  d.addEventListener('close',function(){if(opener)opener.focus();});
  d.addEventListener('keydown',function(e){
    if(e.key==='ArrowLeft'&&P.length>1){show(cur-1);}
    else if(e.key==='ArrowRight'&&P.length>1){show(cur+1);}
    else if(e.key==='Tab'){var f=[].filter.call(d.querySelectorAll('button'),function(b){return !b.hidden;});
      if(!f.length)return;var a=f[0],z=f[f.length-1];
      if(e.shiftKey&&document.activeElement===a){e.preventDefault();z.focus();}
      else if(!e.shiftKey&&document.activeElement===z){e.preventDefault();a.focus();}}
  });
})();
"""


def _payload(order: list[dict]) -> str:
    data = [{
        "src": _src(p, "1600"), "srcset": _srcset(p).replace("&amp;", "&"), "w": int(p.get("w") or 1600),
        "h": int(p.get("h") or 1200), "alt": alt(p), "title": title(p), "place": place(p), "credit": credit(p),
    } for p in order]
    return json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


def masthead_html() -> str:
    return (
        '<header class="mh mh-hybrid"><p class="pv-flag">Private preview \u00b7 Catch Wall redesign</p>'
        '<div class="mh-bar"><nav class="mh-nav" aria-label="Sections"><a href="/brief">Morning Brief</a>'
        '<a href="/lake">Lakes &amp; rivers</a><a href="/preview/catch-wall" aria-current="page">Catch Wall</a></nav></div>'
        '<div class="mh-plate"><p class="mh-name"><a href="/">The Coastal Brief</a></p>'
        '<svg class="mh-rule" viewBox="0 0 1200 4" preserveAspectRatio="none" aria-hidden="true" focusable="false">'
        '<rect width="1200" height="4" fill="url(#cw-brass)"/></svg>'
        '<p class="mh-date"><time>%s</time><span class="mh-motto">From the rivers to the sounds to the sea</span></p></div>'
        '</header>'
    ) % _esc(sprint_home._today())


BRASS_DEFS = (
    '<svg class="wi-defs" aria-hidden="true" focusable="false"><defs>'
    '<linearGradient id="cw-brass" x1="0" x2="1" y1="0" y2="0">'
    '<stop offset="0" stop-color="#8A6A3A"/><stop offset=".35" stop-color="#C4A36A"/>'
    '<stop offset=".55" stop-color="#D9BE86"/><stop offset=".8" stop-color="#A7864F"/><stop offset="1" stop-color="#7C5E33"/>'
    '</linearGradient></defs></svg>'
)


def style_tag() -> str:
    css = "\n".join(
        (sprint_home.DIR / n).read_text(encoding="utf-8") for n in ("base.css", "hybrid.css")
    ) + "\n" + (DIR / "catch-wall.css").read_text(encoding="utf-8")
    return '<style id="cw-preview-css">\n%s\n</style>\n' % css.replace("</", "<\\/")


def page(live: list[dict] | None = None) -> bytes:
    photos = catch_photos(live)
    main, order = body_html(photos)
    first = order[0] if order else None
    preload = ""
    if first and _src(first):
        preload = '<link rel="preload" as="image" href="%s" imagesrcset="%s" imagesizes="%s" fetchpriority="high">\n' % (
            _esc(_src(first)), _srcset(first), SIZES["pl-a"])
    out = """<!DOCTYPE html>
<html lang="en" data-sprint="hybrid" data-page="catch-wall">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="robots" content="noindex, nofollow">
<meta name="color-scheme" content="light dark">
<title>Catch Wall \u00b7 The Coastal Brief (private preview)</title>
<meta name="description" content="Private Catch Wall redesign preview for The Coastal Brief. Not public.">
<link rel="preload" href="/fonts/fraunces-var.woff2" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="/fonts/source-sans-3-var.woff2" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="/fonts/barlow-condensed-600.woff2" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="/fonts/fraunces-italic-var.woff2" as="font" type="font/woff2" crossorigin>
<link rel="icon" href="/branding/favicon.svg" type="image/svg+xml">
<link rel="preconnect" href="https://wgjoenkugzfrrfejmtvh.supabase.co" crossorigin>
%(preload)s%(css)s</head>
<body>
%(defs)s
<a class="skip" href="#main">Skip to photographs</a>
%(mast)s
<main id="main">%(main)s</main>
%(dialog)s
<footer class="ft"><div class="ft-in"><p>Private preview. Photographs are approved Catch Wall submissions, shown with only the details each submission includes and credited as stored.</p></div></footer>
<script>window.__CWP=%(payload)s;</script>
<script>%(js)s</script>
</body>
</html>
""" % {"preload": preload, "css": style_tag(), "defs": BRASS_DEFS, "mast": masthead_html(), "main": main,
       "dialog": dialog_html(), "payload": _payload(order), "js": LB_JS}
    return out.encode("utf-8")
