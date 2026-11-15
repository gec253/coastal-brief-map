"""Public Catch Wall presentation. Approved photos only; no sample states."""
from __future__ import annotations

import html
import json
import re
import sys
import threading
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
# Stale-while-revalidate: serve a warm list instantly, refresh in the background.
_CACHE_FRESH_S = 60.0
_CACHE_TTL_S = 300.0
_FETCH_TIMEOUT_S = 1.0
_PUBLIC_CACHE: dict = {"t": 0.0, "photos": [], "ok": True, "filled": False}
_CACHE_LOCK = threading.Lock()
_REFRESHING = False
_REFRESH_DONE = threading.Event()
_MEDIA_CACHE: dict[tuple[str, str], bytes] = {}
_MEDIA_LOCK = threading.Lock()
_MEDIA_RE = re.compile(
    r"^/catch-wall-media/([0-9a-fA-F-]{8,36})/(400|800|1600)\.webp$"
)


def parse_view(raw: str | None) -> str:
    v = (raw or "").strip().lower()
    return v if v in VIEWS else "catch"


def parse_water(raw: str | None) -> str:
    w = (raw or "").strip().lower()
    return w if w in ("all", "salt", "fresh") else "all"


def _cache_snapshot() -> tuple[float, list[dict], bool, bool]:
    with _CACHE_LOCK:
        return (
            _PUBLIC_CACHE["t"],
            [dict(p) for p in _PUBLIC_CACHE["photos"]],
            bool(_PUBLIC_CACHE.get("ok", True)),
            bool(_PUBLIC_CACHE.get("filled")),
        )


def _store_cache(photos_out: list[dict], ok: bool = True) -> None:
    with _CACHE_LOCK:
        # A failed fill is immediately stale so the next request retries in the background.
        now = time.time()
        _PUBLIC_CACHE["t"] = now if ok else now - _CACHE_FRESH_S - 1
        _PUBLIC_CACHE["photos"] = [dict(p) for p in photos_out]
        _PUBLIC_CACHE["ok"] = bool(ok)
        _PUBLIC_CACHE["filled"] = True
        snapshot = [dict(p) for p in photos_out]
    # Drop any cached derivative that is no longer the featured approved photo.
    _evict_stale_media(snapshot)


def _allow_self_fetch() -> bool:
    """Lab-only fallback. Never self-fetch when a backend is configured, or on Render."""
    if photos.on_render() or photos.backend():
        return False
    return True


def _self_fetch_approved() -> list[dict] | None:
    try:
        req = Request(
            PROD_PHOTOS_URL,
            headers={"User-Agent": "CoastalBrief/1.0", "Accept": "application/json"},
        )
        with urlopen(req, timeout=_FETCH_TIMEOUT_S) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return [dict(p) for p in (data.get("photos") or [])]
    except Exception as exc:  # noqa: BLE001 — page must still render
        sys.stderr.write("catch-wall public photos: %s\n" % exc)
        return None


def _refresh_sync() -> None:
    """Fill the SWR cache from the configured backend, or the lab-only self-fetch."""
    if photos.backend():
        # Bypass photos.py's 60s cache so our SWR refresh always does a live read.
        photos._pub_cache.pop((None, False), None)
        data = photos.public_photos("all")
        if data.get("ok") is False:
            _, stale, _, filled = _cache_snapshot()
            if filled and stale:
                # Keep the last good list; do not replace it with an empty error.
                return
            _store_cache([], ok=False)
            return
        photos_out = [dict(p) for p in (data.get("photos") or [])]
        _store_cache(photos_out, ok=True)
        return
    if _allow_self_fetch():
        photos_out = _self_fetch_approved()
        if photos_out is None:
            _, stale, _, filled = _cache_snapshot()
            if filled:
                return
            _store_cache([], ok=False)
            return
        _store_cache(photos_out, ok=True)
        return
    _, stale, _, filled = _cache_snapshot()
    if filled:
        return
    _store_cache([], ok=False)


def _kick_refresh() -> None:
    """Refresh the approved list off the request path."""
    global _REFRESHING
    with _CACHE_LOCK:
        if _REFRESHING:
            return
        _REFRESHING = True
        _REFRESH_DONE.clear()

    def run() -> None:
        global _REFRESHING
        try:
            _refresh_sync()
        finally:
            with _CACHE_LOCK:
                _REFRESHING = False
            _REFRESH_DONE.set()
        _, photos_out, ok, filled = _cache_snapshot()
        if filled and ok and photos_out:
            _warm_featured_media(photos_out)

    threading.Thread(target=run, daemon=True, name="cw-photo-cache").start()


def _refresh_bounded(timeout: float) -> tuple[list[dict], bool, bool]:
    """Wait up to timeout for a cold fill. Never block a request longer than that."""
    _kick_refresh()
    _REFRESH_DONE.wait(timeout)
    _, photos, ok, filled = _cache_snapshot()
    if filled:
        return photos, ok, (not ok and not photos)
    return [], False, True


def warm_cache() -> None:
    """Start a background fill so the first public request is not a blocking GET."""
    _kick_refresh()


def invalidate() -> None:
    """Mark the list stale and refresh in the background. Called from photos._bust_cache."""
    with _CACHE_LOCK:
        if _PUBLIC_CACHE.get("filled") and _PUBLIC_CACHE["t"]:
            _PUBLIC_CACHE["t"] = min(_PUBLIC_CACHE["t"], time.time() - _CACHE_FRESH_S - 1)
    _kick_refresh()


def media_url(photo_id: str, variant: str) -> str:
    return "/catch-wall-media/%s/%s.webp" % (photo_id, variant)


def _approved_ids(photos: list[dict]) -> set[str]:
    return {str(p.get("id") or "").lower() for p in photos if p.get("id")}


def _featured_id(photos: list[dict]) -> str:
    featured, _ = pick_featured(photos)
    if not featured:
        return ""
    return str(featured.get("id") or "").lower()


def _evict_stale_media(photos: list[dict]) -> None:
    """Keep only the current featured photo's variants. Everything else goes."""
    keep = _featured_id(photos)
    if keep not in _approved_ids(photos):
        keep = ""
    with _MEDIA_LOCK:
        for key in list(_MEDIA_CACHE):
            if not keep or key[0] != keep:
                _MEDIA_CACHE.pop(key, None)


def media_bytes(photo_id: str, variant: str) -> bytes | None:
    """Return cached bytes only for the current featured, approved photo."""
    pid = (photo_id or "").lower()
    _, photos, _, _ = _cache_snapshot()
    if pid not in _approved_ids(photos) or pid != _featured_id(photos):
        return None
    with _MEDIA_LOCK:
        return _MEDIA_CACHE.get((pid, variant))


def parse_media_path(path: str) -> tuple[str, str] | None:
    m = _MEDIA_RE.match(path or "")
    if not m:
        return None
    return m.group(1).lower(), m.group(2)


def _fetch_media(photo_id: str, variant: str, url: str) -> None:
    if not url.startswith("https://"):
        return
    if media_bytes(photo_id, variant):
        return
    try:
        req = Request(url, headers={"User-Agent": "CoastalBrief/1.0", "Accept": "image/webp"})
        with urlopen(req, timeout=3.0) as resp:
            body = resp.read()
        if len(body) < 100 or not body.startswith(b"RIFF"):
            return
        pid = (photo_id or "").lower()
        _, photos, _, _ = _cache_snapshot()
        if pid not in _approved_ids(photos) or pid != _featured_id(photos):
            return
        with _MEDIA_LOCK:
            _MEDIA_CACHE[(pid, variant)] = body
            for key in list(_MEDIA_CACHE):
                if key[0] != pid:
                    _MEDIA_CACHE.pop(key, None)
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write("catch-wall media %s/%s: %s\n" % (photo_id, variant, exc))


def _warm_featured_media(photos: list[dict]) -> None:
    _evict_stale_media(photos)
    featured, _ = pick_featured(photos)
    if not featured:
        return
    pid = str(featured.get("id") or "").lower()
    src = featured.get("src") or {}
    for key in EXISTING_VARIANTS:
        href = src.get(key)
        if pid and href:
            _fetch_media(pid, key, href)


def localize_featured(photo: dict | None) -> dict | None:
    """Point the featured catch at same-origin derivatives once they are cached."""
    if not photo:
        return photo
    p = dict(photo)
    pid = str(p.get("id") or "").lower()
    src = dict(p.get("src") or {})
    changed = False
    for key in EXISTING_VARIANTS:
        if src.get(key) and media_bytes(pid, key):
            src[key] = media_url(pid, key)
            changed = True
    if changed:
        p["src"] = src
    return p


def _gallery_state() -> dict:
    """Read through the SWR cache. After warmup, never waits on the backend."""
    stamped, photos, ok, filled = _cache_snapshot()
    age = time.time() - stamped if stamped else 1e9
    if filled and age < _CACHE_FRESH_S:
        return {"photos": photos, "ok": ok, "unavailable": (not ok and not photos)}
    if filled:
        _kick_refresh()
        return {"photos": photos, "ok": ok, "unavailable": (not ok and not photos)}
    photos, ok, unavailable = _refresh_bounded(_FETCH_TIMEOUT_S)
    return {"photos": photos, "ok": ok, "unavailable": unavailable}


def _fetch_public_approved() -> list[dict]:
    """Back-compat wrapper used by tests: photos from the SWR cache."""
    return _gallery_state()["photos"]


def load_approved(live: list[dict] | None = None) -> list[dict]:
    return load_state(live)["photos"]


def load_state(live: list[dict] | None = None) -> dict:
    if live is not None:
        return {"photos": [dict(p) for p in live], "ok": True, "unavailable": False}
    return _gallery_state()


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
    state = load_state(live)
    seen: set[str] = set()
    unique = []
    for p in state["photos"]:
        pid = str(p.get("id") or "")
        if not pid or pid in seen:
            continue
        seen.add(pid)
        unique.append(p)
    filtered = [p for p in unique if _matches(p, view, water)]
    featured, rest = pick_featured(filtered)
    featured = localize_featured(featured)
    unavailable = bool(state.get("unavailable")) and featured is None and not rest
    return {
        "view": view,
        "water": water,
        "featured": featured,
        "rest": rest,
        "photos": ([featured] if featured else []) + rest,
        "unavailable": unavailable,
        "invite": (not unavailable) and (featured is None or not rest),
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


def unavailable_html() -> str:
    return (
        '<aside class="cw-invite" role="status">'
        "<h3>Photos are unavailable right now</h3>"
        "<p>The Catch Wall will be back shortly. Please try again in a moment.</p>"
        "</aside>"
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
    if model.get("unavailable"):
        parts.append(unavailable_html())
    elif model.get("invite"):
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
