"""Private Catch Wall redesign preview: /preview/catch-wall (cookie-gated, noindex).

Presentation only. Reads the same approved-photo list the public Catch Wall uses
(catch_wall_public.load_approved) and never writes anything. Uploads, moderation,
the share form and /admin are untouched; "Submit your catch" links to the
existing flow on /catch-wall.
"""
from __future__ import annotations

import html
import json
import re
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
    "pl-f": "(min-width: 1000px) 600px, 100vw",
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


def featured_catch(photos: list[dict], day=None) -> dict | None:
    """One highlighted catch per America/New_York day, the same for every visitor.
    Approved catches only (catch_photos already filters), ordered by their stored id so the
    pick never depends on list order; day ordinal modulo the count. No randomness."""
    pool = sorted((p for p in photos if is_approved(p) and p.get("category") == "fishing"), key=lambda p: str(p.get("id") or ""))
    if not pool:
        return None
    if day is None:
        import photo_rotation
        day = photo_rotation.et_date()
    return pool[day.toordinal() % len(pool)]


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


def plate(p: dict, i: int, n: int, eager: bool, feat: bool = False) -> str:
    shape = "pl-f" if feat else SHAPES[(n - 1) % len(SHAPES)]
    w, h = int(p.get("w") or 1600), int(p.get("h") or 1200)
    cw, ch = ((4, 5) if h > w * 1.1 else (4, 3)) if feat else crop(shape, w, h)
    load = 'loading="eager" fetchpriority="high"' if eager else 'loading="lazy"'
    img = (
        '<img src="%s" srcset="%s" sizes="%s" width="%d" height="%d" alt="%s" %s decoding="async">'
        % (_esc(_src(p)), _srcset(p), SIZES[shape], w, h, _esc(alt(p)), load)
    )
    label = '<span class="pl-feat">Featured catch</span>' if feat else ""
    return (
        '<figure class="pl %s" style="--crop:%d / %d"%s>'
        '<a class="pl-open" href="%s" data-i="%d" aria-label="Open photo: %s">'
        '<span class="pl-frame">%s</span></a>'
        '<figcaption class="pl-cap">%s%s</figcaption></figure>'
    ) % (shape, cw, ch, ' data-featured="1"' if feat else "", _esc(_src(p, "1600")), i,
         _esc(title(p) + (", " + place(p) if place(p) else "")), img, label, _caption(p, n))


def _count(n: int) -> str:
    return "%d %s" % (n, "photo" if n == 1 else "photos")


CONTRIB = (
    '<aside class="pl pl-join" aria-labelledby="cw-j-h"><p class="pl-join-k">Catch Wall</p>'
    '<h2 id="cw-j-h" class="pl-join-h">Have a catch from Carolina water?</h2>'
    '<p>Send the photograph with the species and where you caught it. We review every picture before it appears, '
    'and we credit you by name if you give one.</p>'
    '%s</aside>'
)
SUBMIT_LINK = '<a class="cw-submit"%s href="%s"%s>Submit your catch <span aria-hidden="true">\u2192</span></a>'
SOON = '<p class="cw-soon"%s>Photo sharing opens soon.</p>'


def submit_cta(public: bool, primary: bool) -> str:
    """Preview: a plain link to the existing /catch-wall page. Public (/catch-wall itself): the same
    existing share flow as before. The link opens the existing share dialog via catch-wall-public.js
    ([data-share] / #share-open) and stays hidden until /api/photos/config says uploads are on;
    otherwise the existing "Photo sharing opens soon." note shows, exactly as on the old page."""
    if not public:
        return SUBMIT_LINK % ("", SUBMIT_HREF, "")
    return (SUBMIT_LINK % (' id="share-open" hidden' if primary else " hidden", SUBMIT_HREF + "#share", " data-share")
            + SOON % (' id="share-soon"' if primary else " data-share-soon"))


def body_html(photos: list[dict], day=None, public: bool = False, show_empty: bool = True) -> str:
    feat = featured_catch(photos, day)
    groups = {k: [p for p in photos if water(p) == k] for k, _, _ in SECTIONS}
    if feat:   # the featured catch leads its own section (shown once, never duplicated)
        k = water(feat)
        groups[k] = [feat] + [p for p in groups[k] if p is not feat]
    order = [p for k, _, _ in SECTIONS for p in groups[k]]
    index = {id(p): i for i, p in enumerate(order)}
    chips = "".join(
        '<a class="chip chip-%s" href="#sec-%s"><span class="chip-k">%s</span><span class="chip-n">%s</span></a>'
        % (k, k, _esc(label), _esc(_count(len(groups[k]))))
        for k, label, _ in SECTIONS if groups[k] or show_empty
    )
    intro = (
        '<section class="cw-head" aria-labelledby="cw-h">'
        '<p class="kicker"><span class="dm dm-sq" aria-hidden="true"></span>Catch Wall \u00b7 Fishing photographs</p>'
        '<h1 id="cw-h" class="cw-h">The Catch Wall</h1>'
        '<p class="cw-dek">Catches from North Carolina water, from the sounds to the reservoirs, shown as anglers sent them. '
        'Every photograph is reviewed before it appears here. Coastal Life photographs stay on Coastal Life.</p>'
        '<div class="cw-act"><nav class="chips" aria-label="Jump to water type">%s</nav>'
        '%s</div>'
        '<svg class="brass" viewBox="0 0 1200 4" preserveAspectRatio="none" aria-hidden="true" focusable="false">'
        '<rect width="1200" height="4" fill="url(#cw-brass)"/></svg>'
        '</section>'
    ) % (chips, submit_cta(public, True))
    contrib = CONTRIB % submit_cta(public, False)
    secs = []
    first = True
    shown = [k for k, _, _ in SECTIONS if groups[k]]
    # contribution card: in the shorter column (desktop) so the two columns end together
    join_at = min(shown, key=lambda k: (len(groups[k]), shown.index(k))) if shown else None
    for k, label, sub in SECTIONS:
        items = groups[k]
        if not items and not show_empty:
            continue
        plates = []
        for n, p in enumerate(items, start=1):
            plates.append(plate(p, index[id(p)], n, eager=first and n == 1, feat=p is feat))
        if not items:
            plates.append(
                '<p class="cw-empty" role="status">No %s catches on the wall yet. Approved photographs will appear here.</p>'
                % _esc(label.lower())
            )
        if k == join_at:
            plates.append(contrib)
        first = False
        secs.append(
            '<section class="ws ws-%s" id="sec-%s" aria-labelledby="ws-%s-h">'
            '<header class="ws-head"><p class="ws-k"><span class="ws-dm" aria-hidden="true"></span>%s</p><h2 class="ws-h" id="ws-%s-h">%s</h2>'
            '<p class="ws-n">%s</p></header><div class="ws-plates">%s</div></section>'
            % (k, k, k, _esc(label), k, _esc(sub), _esc(_count(len(items))), "".join(plates))
        )
    if not secs:
        secs.append('<p class="cw-none" role="status">Photographs are unavailable right now. Please try again shortly.</p>')
    if not shown:
        secs.append(contrib)
    return intro + '<div class="ws-wrap">' + "".join(secs) + "</div>", order


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


def masthead_html(public: bool = False) -> str:
    """Same newspaper masthead as the Hybrid homepage; the page's own h1 is "The Catch Wall"."""
    m = sprint_home._hybrid_masthead(public, "salt")
    m = m.replace('<h1 class="mh-name">', '<p class="mh-name">', 1).replace("</a></h1>", "</a></p>", 1)
    m = m.replace(' aria-current="page">Saltwater', ">Saltwater", 1)
    if public:
        if '<a href="/catch-wall">Catch Wall</a>' not in m or "pv-flag" in m:
            raise RuntimeError("public catch wall: masthead shape changed")
        return m.replace('<a href="/catch-wall">Catch Wall</a>', '<a href="/catch-wall" aria-current="page">Catch Wall</a>', 1)
    m = m.replace('<a href="/catch-wall">Catch Wall</a>', '<a href="/preview/catch-wall" aria-current="page">Catch Wall</a>', 1)
    return m.replace("Private concept · C · Hybrid", "Private preview · Catch Wall redesign", 1)


BRASS_DEFS = (
    '<svg class="wi-defs" aria-hidden="true" focusable="false"><defs>'
    '<linearGradient id="cw-brass" x1="0" x2="1" y1="0" y2="0">'
    '<stop offset="0" stop-color="#8A6A3A"/><stop offset=".35" stop-color="#C4A36A"/>'
    '<stop offset=".55" stop-color="#D9BE86"/><stop offset=".8" stop-color="#A7864F"/><stop offset="1" stop-color="#7C5E33"/>'
    '</linearGradient></defs></svg>'
)


_CSS_COMMENT = re.compile(r"/\*.*?\*/", re.S)


def style_tag(public: bool = False) -> str:
    css = "\n".join(
        (sprint_home.DIR / n).read_text(encoding="utf-8") for n in ("base.css", "hybrid.css")
    ) + "\n" + (DIR / "catch-wall.css").read_text(encoding="utf-8")
    if public:
        css = _CSS_COMMENT.sub("", css + "\n" + share_css())
        return '<style id="cw-css">\n%s\n</style>\n' % css.replace("</", "<\\/")
    return '<style id="cw-preview-css">\n%s\n</style>\n' % css.replace("</", "<\\/")


# ---- Public /catch-wall: the existing share flow, carried over unchanged -------------
# The share dialog markup is copied at render time from catch-wall.html (the old public page)
# and its CSS from styles.css, so the form, its fields and /api/photos/submit stay exactly as
# they are. catch-wall-public.js drives it, as before. Missing pieces raise, and server.py then
# serves the old render.
_DLG_RE = re.compile(r'<dialog class="share-dlg".*?</dialog>', re.S)
_PHASE2_KEEP = ("body.no-scroll", ".gal-soon", ".btn-share", ".sr-only")
_DARK_RE = re.compile(r'^\[data-theme="dark"\] (.+)$', re.M)
SHARE_VARS = (
    ".share-dlg{--d-panel:#FBF8F2;--d-inst:#FFFFFF;--d-inst-2:#F7F2E8;--d-edge:rgba(11,42,61,.14);--d-ink:#0B2A3D;"
    "--d-ink-2:#3E5868;--d-accent:#2B6F8F;--teal:#5BA8A0;--navy:#0B2A3D;--copper:#B8743A;"
    "--f-display:'Fraunces',Georgia,'Times New Roman',serif;font-family:var(--f-ui,system-ui,sans-serif)}\n"
    "@media (prefers-color-scheme:dark){.share-dlg{--d-panel:#0C2231;--d-inst:#0F2A3C;--d-inst-2:#0B2333;"
    "--d-edge:rgba(169,214,204,.16);--d-ink:#F6F1E7;--d-ink-2:#B9C9CF;--d-accent:#8CC9EA}}\n"
    ".cw-submit[hidden],.cw-soon[hidden]{display:none}\n"
    ".cw-soon{margin:0;min-height:44px;display:flex;align-items:center;font-size:.9rem;color:var(--ink-2);border-left:3px solid #B8743A;padding:0 0 0 10px}\n"
    ".pl-join .cw-soon{color:#E2DACB;margin-top:6px}\n"
)


def share_dialog_html() -> str:
    m = _DLG_RE.search((ROOT / "catch-wall.html").read_text(encoding="utf-8"))
    if not m or 'id="share-form"' not in m.group(0):
        raise RuntimeError("public catch wall: share dialog missing from catch-wall.html")
    return m.group(0)


def share_css() -> str:
    full = (ROOT / "styles.css").read_text(encoding="utf-8")
    a, b = full.find("/* Share dialog */"), full.find("/* Home: coastal-life")
    if a < 0 or b < a:
        raise RuntimeError("public catch wall: share dialog CSS missing from styles.css")
    keep = [ln for ln in full[full.find("/* ===== Phase 2"):a].splitlines() if ln.startswith(_PHASE2_KEEP)
            and not ln.startswith(".gal-soon {")]
    chunk = "\n".join(keep) + "\n" + full[a:b]
    chunk = _DARK_RE.sub(lambda m: "@media (prefers-color-scheme:dark){%s}" % m.group(1), chunk)
    return SHARE_VARS + chunk


PUBLIC_TITLE = "Catch Wall \u2014 The Coastal Brief"
PUBLIC_URL = "https://thecoastalbrief.com/catch-wall"
PUBLIC_DESC = ("Catches from North Carolina water, from the sounds to the reservoirs, shown as anglers sent them. "
               "Every photograph is reviewed before it appears.")
PUBLIC_FOOT = (
    '<footer class="ft"><div class="ft-in ft-pub">'
    '<ul class="ft-links" aria-label="Quick links">'
    '<li><a href="https://license.gooutdoorsnorthcarolina.com/Licensing/CustomerLookup.aspx" rel="noopener" target="_blank">Buy an NC fishing or hunting license</a></li>'
    '<li><a href="https://www.ncwildlife.gov/hunting/license-types-and-fees" rel="noopener" target="_blank">License types and fees</a></li>'
    '<li><a href="https://www.ncwildlife.gov/" rel="noopener" target="_blank">NC Wildlife Resources Commission</a></li></ul>'
    "<p>The Coastal Brief is not weather, surf, or fishing advice. Always check official NWS marine forecasts and advisories before going out.</p>"
    "<p>Photos are shared by visitors, reviewed before they appear, and stay the property of the people who took them.</p>"
    "<p>Licenses are sold by the NC Wildlife Resources Commission; The Coastal Brief is not affiliated with it.</p>"
    "</div></footer>"
)


def _head_meta(public: bool) -> str:
    if not public:
        return ('<meta name="robots" content="noindex, nofollow">\n<meta name="color-scheme" content="light dark">\n'
                '<title>Catch Wall \u00b7 The Coastal Brief (private preview)</title>\n'
                '<meta name="description" content="Private Catch Wall redesign preview for The Coastal Brief. Not public.">\n')
    t, d = _esc(PUBLIC_TITLE), _esc(PUBLIC_DESC)
    return (
        '<meta name="robots" content="index, follow">\n<meta name="color-scheme" content="light dark">\n'
        '<title>%s</title>\n<meta name="description" content="%s">\n<link rel="canonical" href="%s">\n'
        '<meta name="theme-color" content="#0B2A3D">\n'
        '<meta property="og:title" content="%s">\n<meta property="og:description" content="%s">\n'
        '<meta property="og:url" content="%s">\n<meta property="og:type" content="website">\n'
        '<meta name="twitter:title" content="%s">\n<meta name="twitter:description" content="%s">\n%s'
    ) % (t, d, PUBLIC_URL, t, d, PUBLIC_URL, t, d, _og_image_meta())


_OG_IMG_RE = re.compile(r'<meta (?:property="og:image[^"]*"|name="twitter:(?:image[^"]*|card)") content="[^"]*">')


def _og_image_meta() -> str:
    """The site's share card tags (image, size, alt), copied from the previous public page."""
    tags = _OG_IMG_RE.findall((ROOT / "catch-wall.html").read_text(encoding="utf-8"))
    if not any("og:image\"" in t for t in tags):
        raise RuntimeError("public catch wall: share card meta missing from catch-wall.html")
    return "".join(t + "\n" for t in tags)


class NotReady(Exception):
    """Expected state (no approved catches yet, or storage unavailable): the previous public
    render already handles it with its invitation / "Photos are unavailable" copy."""


def public_page(water_q: str = "all") -> bytes:
    """Public /catch-wall. Same photo source as the previous page (catch_wall_public's
    approved-only cache). ?water=salt|fresh keeps working: only that water's section shows."""
    import catch_wall_public
    if not catch_wall_public._cache_snapshot()[3]:
        # Cold cache: the previous render does the one bounded fetch, so a slow backend is never waited on twice.
        raise NotReady("photo cache not warm yet")
    state = catch_wall_public.load_state()   # served from the warm cache; never blocks
    w = catch_wall_public.parse_water(water_q)
    live = [p for p in state["photos"] if w == "all" or water(p) == w]
    if state.get("unavailable") or not catch_photos(live):
        raise NotReady("no approved catches to show" if not state.get("unavailable") else "photos unavailable")
    return page(live, public=True, show_empty=(w == "all"))


def _feedback_embed() -> str:
    try:
        import feedback
        return feedback.embed_html()
    except Exception:
        return ""


def page(live: list[dict] | None = None, public: bool = False, show_empty: bool = True) -> bytes:
    """public=False: /preview/catch-wall (unchanged). public=True: /catch-wall, approved photos only,
    no preview chrome, indexable, with the existing share dialog and catch-wall-public.js."""
    photos = catch_photos(live)
    main, order = body_html(photos, public=public, show_empty=show_empty)
    first = order[0] if order else None
    preload = ""
    if first and _src(first):
        preload = '<link rel="preload" as="image" href="%s" imagesrcset="%s" imagesizes="%s" fetchpriority="high">\n' % (
            _esc(_src(first)), _srcset(first), SIZES["pl-a"])
    if public:
        dialog = dialog_html() + "\n" + share_dialog_html()
        foot = PUBLIC_FOOT[:-len("</div></footer>")] + _feedback_embed() + "</div></footer>"
        boot = json.dumps({"view": "catch", "water": "all", "photos": []})
        scripts = ('<script>window.__CW_BOOT=%s;</script>\n<script src="/catch-wall-public.js" defer></script>\n'
                   '<script src="/brief-link.js" defer></script>\n' % boot)
    else:
        dialog = dialog_html()
        foot = ('<footer class="ft"><div class="ft-in"><p>Private preview. Photographs are approved Catch Wall submissions, '
                'shown with only the details each submission includes and credited as stored.</p>'
                + _feedback_embed() + '</div></footer>')
        scripts = ""
    out = """<!DOCTYPE html>
<html lang="en" data-sprint="hybrid" data-page="catch-wall">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
%(meta)s<link rel="preload" href="/fonts/fraunces-var.woff2" as="font" type="font/woff2" crossorigin>
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
%(foot)s
<script>window.__CWP=%(payload)s;</script>
<script>%(js)s</script>
%(scripts)s</body>
</html>
""" % {"meta": _head_meta(public), "preload": preload, "css": style_tag(public), "defs": BRASS_DEFS,
       "mast": masthead_html(public), "main": main, "dialog": dialog, "foot": foot, "payload": _payload(order),
       "js": LB_JS, "scripts": scripts}
    return out.encode("utf-8")
