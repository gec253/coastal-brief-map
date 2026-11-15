"""Public Catch Wall presentation. Approved photos only; no sample states."""
from __future__ import annotations

import html
import json
import sys
import time
from urllib.request import Request, urlopen

import photos

VIEWS = {
    "catch": {
        "h": "Catch Wall",
        "eyebrow": "Community photos · Fishing",
        "path": "/catch-wall",
    },
    "life": {
        "h": "Coastal Life",
        "eyebrow": "Community photos · The coast",
        "path": "/coastal-life",
    },
    "all": {
        "h": "All photos",
        "eyebrow": "Community photos",
        "path": "/photos",
    },
}
DEK = "Real catches. Real Carolina waters. Every picture has a story."
RED_DRUM_ID = "3e41ed83-23a3-4032-8a5f-c7957b788e3f"
EXISTING_VARIANTS = ("400", "800", "1600")
FEATURED_SIZES = "(min-width: 860px) 55vw, 100vw"
PROD_PHOTOS_URL = "https://thecoastalbrief.com/api/photos?view=all"
_PUBLIC_CACHE: dict = {"t": 0.0, "photos": []}


def parse_view(raw: str | None) -> str:
    v = (raw or "").strip().lower()
    return v if v in VIEWS else "catch"


def parse_water(raw: str | None) -> str:
    w = (raw or "").strip().lower()
    return w if w in ("all", "salt", "fresh") else "all"


def _fetch_public_approved() -> list[dict]:
    """Unauthenticated GET of the public gallery when this process has no storage backend."""
    now = time.time()
    if now - _PUBLIC_CACHE["t"] < 60:
        return [dict(p) for p in _PUBLIC_CACHE["photos"]]
    try:
        req = Request(
            PROD_PHOTOS_URL,
            headers={"User-Agent": "CoastalBrief/1.0", "Accept": "application/json"},
        )
        with urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        photos_out = [dict(p) for p in (data.get("photos") or [])]
        _PUBLIC_CACHE["t"] = now
        _PUBLIC_CACHE["photos"] = photos_out
        return [dict(p) for p in photos_out]
    except Exception as exc:  # noqa: BLE001 — page must still render
        sys.stderr.write("catch-wall public photos: %s\n" % exc)
        return [dict(p) for p in _PUBLIC_CACHE["photos"]]


def load_approved(live: list[dict] | None = None) -> list[dict]:
    if live is not None:
        return [dict(p) for p in live]
    data = photos.public_photos("all")
    if data.get("configured"):
        return [dict(p) for p in (data.get("photos") or [])]
    return _fetch_public_approved()


def _matches(p: dict, view: str, water: str) -> bool:
    if view == "catch" and p.get("category") != "fishing":
        return False
    if view == "life" and p.get("category") == "fishing":
        return False
    if water == "salt" and p.get("water") == "freshwater":
        return False
    if water == "fresh" and p.get("water") != "freshwater":
        return False
    return True


def pick_featured(photo_list: list[dict]) -> tuple[dict | None, list[dict]]:
    if not photo_list:
        return None, []

    def score(p: dict) -> tuple:
        sid = str(p.get("id") or "")
        return (
            1 if sid == RED_DRUM_ID else 0,
            1 if p.get("category") == "fishing" else 0,
            1 if p.get("species") else 0,
        )

    i = max(range(len(photo_list)), key=lambda k: (score(photo_list[k]), -k))
    featured = photo_list[i]
    rest = photo_list[:i] + photo_list[i + 1 :]
    return featured, rest


def tile_kind(p: dict) -> str:
    w, h = int(p.get("w") or 1), int(p.get("h") or 1)
    if h / max(w, 1) >= 1.2:
        return "is-tall"
    if w / max(h, 1) >= 1.2:
        return "is-wide"
    return "is-mid"


def assemble(view: str, water: str, live: list[dict] | None = None) -> dict:
    seen: set[str] = set()
    unique = []
    for p in load_approved(live):
        pid = str(p.get("id") or "")
        if not pid or pid in seen:
            continue
        seen.add(pid)
        unique.append(p)
    filtered = [p for p in unique if _matches(p, view, water)]
    featured, rest = pick_featured(filtered)
    return {
        "view": view,
        "water": water,
        "featured": featured,
        "rest": rest,
        "photos": ([featured] if featured else []) + rest,
        "invite": featured is None or not rest,
    }


def _esc(s) -> str:
    return html.escape("" if s is None else str(s), quote=True)


def _srcset(p: dict, keys: tuple[str, ...] | None = None) -> str:
    src = p.get("src") or {}
    if keys:
        order = [k for k in keys if src.get(k)]
    else:
        order = [k for k in EXISTING_VARIANTS if src.get(k)]
        if not order:
            order = sorted(src.keys(), key=lambda k: int(k) if str(k).isdigit() else 0)
    parts = []
    for k in order:
        w = min(int(k) if str(k).isdigit() else 0, int(p.get("w") or 0) or int(k or 0) or 800)
        parts.append("%s %sw" % (_esc(src[k]), w))
    return ", ".join(parts)


def _fallback_src(p: dict, prefer: str = "800") -> str:
    src = p.get("src") or {}
    if src.get(prefer):
        return src[prefer]
    for k in ("800", "1600", "400", "1280"):
        if src.get(k):
            return src[k]
    return next(iter(src.values()), "")


def _alt(p: dict) -> str:
    if p.get("alt"):
        return str(p["alt"])
    if p.get("category") == "fishing":
        base = (p.get("species") or "Fishing photo") + (" catch" if p.get("species") else "")
    else:
        base = p.get("title") or "Coastal photograph"
    place = p.get("location") or p.get("region") or ""
    who = (" Shared by " + p["name"]) if p.get("name") else ""
    return base + ((" near " + place) if place else "") + who


def _water_label(p: dict) -> str:
    return "Freshwater" if p.get("water") == "freshwater" else "Saltwater"


def _frame_style(w, h) -> str:
    ww, hh = int(w or 3), int(h or 2)
    return ' style="--cw-aspect:%s / %s;--cw-w:%s;--cw-h:%s"' % (ww, hh, ww, hh)


def _photo_figure(p: dict, index: int, featured: bool) -> str:
    kind = tile_kind(p)
    cls = "cw-feature" if featured else ("cw-tile " + kind)
    sizes = FEATURED_SIZES if featured else "(min-width: 1100px) 40vw, (min-width: 640px) 50vw, 50vw"
    labels = []
    if p.get("species"):
        labels.append('<p class="cw-species">%s</p>' % _esc(p["species"]))
    elif p.get("title"):
        labels.append('<p class="cw-title">%s</p>' % _esc(p["title"]))
    place = p.get("location") or p.get("region") or ""
    meta = ['<div class="cw-labels">']
    meta.extend(labels)
    if place:
        meta.append('<p class="cw-place">%s</p>' % _esc(place))
    if p.get("water"):
        wt = "fresh" if p.get("water") == "freshwater" else "salt"
        meta.append(
            '<span class="cw-water-tag" data-water="%s">%s</span>' % (wt, _esc(_water_label(p)))
        )
    meta.append("</div>")
    if p.get("name"):
        meta.append('<p class="cw-credit">Photo: %s</p>' % _esc(p["name"]))
    if p.get("credit_line"):
        meta.append('<p class="cw-credit">%s</p>' % _esc(p["credit_line"]))
    src = _esc(_fallback_src(p, "800"))
    srcset = _srcset(p)
    img_attrs = (
        'src="%s" srcset="%s" sizes="%s" width="%s" height="%s" alt="%s" '
        'decoding="%s" loading="%s"%s'
        % (
            src,
            srcset,
            sizes,
            int(p.get("w") or 800),
            int(p.get("h") or 800),
            _esc(_alt(p)),
            "sync" if featured else "async",
            "eager" if featured else "lazy",
            ' fetchpriority="high"' if featured else "",
        )
    )
    if featured and (p.get("src") or {}).get("800"):
        phone_ss = _srcset(p, ("400", "800"))
        img = (
            "<picture>"
            '<source media="(max-width: 859px)" srcset="%s" sizes="100vw">'
            "<img %s>"
            "</picture>"
        ) % (phone_ss, img_attrs)
    else:
        img = "<img %s>" % img_attrs
    return (
        '<figure class="%s">'
        '<button type="button" class="cw-open" data-i="%d" aria-label="%s">'
        '<span class="cw-frame"%s>%s</span></button>'
        '<figcaption class="cw-meta">%s</figcaption></figure>'
        % (cls, index, _esc(_alt(p)), _frame_style(p.get("w"), p.get("h")), img, "".join(meta))
    )


def featured_preload_html(model: dict) -> str:
    p = model.get("featured") or {}
    src = p.get("src") or {}
    href = src.get("800") or _fallback_src(p, "800")
    if not href:
        return ""
    phone_ss = _srcset(p, ("400", "800")) or _srcset(p)
    desk_ss = _srcset(p, EXISTING_VARIANTS) or _srcset(p)
    desk_href = src.get("1600") or href
    preconnect = ""
    if href.startswith("http"):
        from urllib.parse import urlparse
        origin = "%s://%s" % (urlparse(href).scheme, urlparse(href).netloc)
        preconnect = '<link rel="preconnect" href="%s" crossorigin>\n  ' % _esc(origin)
    return (
        preconnect
        + (
            '<link rel="preload" as="image" href="%s" imagesrcset="%s" imagesizes="100vw" '
            'media="(max-width: 859px)" fetchpriority="high">\n'
            '  <link rel="preload" as="image" href="%s" imagesrcset="%s" imagesizes="55vw" '
            'media="(min-width: 860px)" fetchpriority="high">\n'
            % (_esc(href), phone_ss, _esc(desk_href), desk_ss)
        )
    )


def invite_html(view: str) -> str:
    if view == "life":
        body = (
            "Coastal Life is just getting started. If you have a photograph from "
            "Carolina waters, share it. Every picture is reviewed before it appears."
        )
        cta = "Share a photo"
    else:
        body = (
            "The wall is just getting started. If you have a catch from Carolina waters, "
            "share the photograph. Every picture is reviewed before it appears."
        )
        cta = "Share your catch"
    return (
        '<aside class="cw-invite">'
        "<h3>A place for real photographs</h3>"
        "<p>%s</p>"
        '<button type="button" class="cw-share" data-share hidden>%s</button>'
        "</aside>" % (_esc(body), _esc(cta))
    )


def gallery_html(model: dict) -> str:
    parts = []
    featured = model["featured"]
    rest = model["rest"]
    stage_cls = "cw-stage"
    if featured and not rest:
        stage_cls += " is-single"
    if featured:
        parts.append(_photo_figure(featured, 0, True))
    if model.get("invite"):
        parts.append(invite_html(model["view"]))
    grid = []
    for i, p in enumerate(rest, start=1 if featured else 0):
        grid.append(_photo_figure(p, i, False))
    if grid:
        parts.append('<div class="cw-grid">' + "".join(grid) + "</div>")
    if not parts:
        parts.append(invite_html(model["view"]))
    return '<div class="%s" id="gallery">%s</div>' % (stage_cls, "".join(parts))


def intro_html(view: str) -> str:
    v = VIEWS[view]
    return """
    <section class="cw-intro" aria-labelledby="gal-h">
      <div class="cw-intro-inner">
        <p class="cw-kicker" id="gal-eyebrow">%s</p>
        <h2 id="gal-h">%s</h2>
        <p class="cw-dek" id="gal-lead">%s</p>
        <p class="cw-actions">
          <button type="button" class="cw-share" id="share-open" hidden>Share your catch</button>
          <span class="gal-soon" id="share-soon">Photo sharing opens soon.</span>
        </p>
      </div>
    </section>
    """ % (_esc(v["eyebrow"]), _esc(v["h"]), _esc(DEK))


def switch_html(view: str, water: str, count: int = 0) -> str:
    def href(v: str, w: str) -> str:
        path = VIEWS[v]["path"]
        return path + ("?water=" + w if w != "all" else "")

    tabs = []
    for key, label in (("catch", "Catch Wall"), ("life", "Coastal Life"), ("all", "All photos")):
        cur = ' aria-current="page"' if key == view else ""
        tabs.append('<a href="%s" data-view="%s"%s>%s</a>' % (href(key, water), key, cur, label))
    waters = []
    for key, label in (("all", "All"), ("salt", "Saltwater"), ("fresh", "Freshwater")):
        cur = ' aria-current="true"' if key == water else ""
        waters.append('<a href="%s" data-water="%s"%s>%s</a>' % (href(view, key), key, cur, label))
    waters_label = {"all": "", "salt": ", Saltwater", "fresh": ", Freshwater"}[water]
    if count == 0:
        status = "No photos in %s%s yet" % (VIEWS[view]["h"], waters_label)
    else:
        status = "%d %s in %s%s" % (count, "photo" if count == 1 else "photos", VIEWS[view]["h"], waters_label)
    return """
    <div class="cw-switch">
      <nav class="gal-tabs cw-tabs" aria-label="Photo galleries">%s</nav>
      <nav class="gal-water cw-water" aria-label="Filter by water">
        <span class="gw-k">Water</span>%s
      </nav>
    </div>
    <p class="sr-only" id="gal-count" role="status" aria-live="polite">%s</p>
    """ % ("".join(tabs), "".join(waters), _esc(status))


def main_html(model: dict) -> str:
    n = len(model["photos"])
    return intro_html(model["view"]) + switch_html(model["view"], model["water"], n) + gallery_html(model)


def boot_script(model: dict) -> str:
    payload = {
        "view": model["view"],
        "water": model["water"],
        "photos": model["photos"],
    }
    return (
        "<script>window.__CW_BOOT = %s;</script>\n"
        % json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    )
