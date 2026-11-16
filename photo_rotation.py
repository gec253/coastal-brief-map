"""Daily featured photo for the Hybrid homepage (private prototype, scout/photo-rotation).

One photo per America/New_York calendar day, the same for every visitor, chosen server-side:

    order = rotation_order(valid approved entries)
    photo = order[et_date.toordinal() % len(order)]

The manifest is JSON ({"photos": [entry, ...]}). Lookup order:
  1. $PHOTO_ROTATION_MANIFEST, if set
  2. static/featured-photos/photo-rotation.json (in-repo, the production-visible copy)
The first file that parses AND yields at least one valid approved entry wins.

Entries that fail validation are skipped (and listed in load()["skipped"]), never rendered.
Only approved:true landscape photographs rotate. Community Catch Wall and Coastal Life
photographs stay in the mosaic; catch_wall_id resolution remains for tests and compatibility.
"""
from __future__ import annotations

import html
import json
import os
import re
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
ROOT = Path(__file__).resolve().parent
FIXTURE = ROOT / "static" / "featured-photos" / "photo-rotation.json"
ROUTE = "/featured-photos/"
CATEGORIES = ("saltwater", "freshwater", "heritage", "lifestyle")
FORMATS = (("avif", "image/avif"), ("webp", "image/webp"), ("jpg", "image/jpeg"))
SIZES = "100vw"
_REL = re.compile(r"^(?!.*\.\.)[A-Za-z0-9_-][A-Za-z0-9._/-]*\.(avif|webp|jpe?g)$")
_COLOR = re.compile(r"^#[0-9a-fA-F]{3}([0-9a-fA-F]{3})?$")
_FOCAL = re.compile(r"^\d{1,3}(\.\d+)?% \d{1,3}(\.\d+)?%$")
_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
REQUIRED_TEXT = ("id", "category", "location", "alt", "credit")


def _esc(s, quote=True) -> str:
    return html.escape("" if s is None else str(s), quote=quote)


def manifest_candidates() -> list[Path]:
    env = (os.environ.get("PHOTO_ROTATION_MANIFEST") or "").strip()
    return ([Path(env)] if env else []) + [FIXTURE]


# ------------------------------------------------------------------ validation

def _focal_ok(f) -> bool:
    if isinstance(f, str):
        return bool(_FOCAL.match(f))
    if isinstance(f, dict):
        return bool(f) and set(f) <= {"mobile", "desktop"} and all(isinstance(v, str) and _FOCAL.match(v) for v in f.values())
    return False


def validate(e, base: Path) -> tuple[dict | None, str]:
    """Return (clean entry, "") or (None, reason). Never raises."""
    if not isinstance(e, dict):
        return None, "not an object"
    for k in REQUIRED_TEXT:
        if not isinstance(e.get(k), str) or not e[k].strip():
            return None, "missing %s" % k
    if not _ID.match(e["id"]):
        return None, "bad id"
    if e["category"] not in CATEGORIES:
        return None, "bad category"
    if e.get("approved") is not True:
        return None, "not approved"
    try:
        w, h = int(e.get("width")), int(e.get("height"))
    except (TypeError, ValueError):
        return None, "bad width/height"
    if w <= 0 or h <= 0:
        return None, "bad width/height"
    if h > w:
        # The daily feature is a wide frame (21:9 desktop): portrait phone shots crop badly,
        # so only landscape (or square) photographs rotate. Portrait ones stay in the mosaic.
        return None, "portrait"
    if not _COLOR.match(str(e.get("placeholder") or "")):
        return None, "bad placeholder"
    if not _focal_ok(e.get("focal")):
        return None, "bad focal"
    lic = str(e.get("license") or "").strip()
    if lic.upper().startswith("CC"):
        # CC BY / BY-SA: attribution and a license link are required.
        if not str(e.get("license_url") or "").startswith("https://creativecommons.org/"):
            return None, "CC license without license_url"
        if not str(e.get("photographer") or "").strip():
            return None, "CC license without photographer"
    for k in ("license_url", "source_url"):
        v = str(e.get(k) or "")
        if v and not v.startswith("https://"):
            return None, "bad %s" % k
    clean = dict(e, width=w, height=h, license=lic)
    files = {}
    if e.get("catch_wall_id"):
        if not re.match(r"^[0-9a-f-]{36}$", str(e["catch_wall_id"])):
            return None, "bad catch_wall_id"
        clean["sources"] = {}
    else:
        src = e.get("sources")
        if not isinstance(src, dict):
            return None, "missing sources"
        out = {}
        for fmt, _ in FORMATS:
            m = src.get(fmt) or {}
            if not isinstance(m, dict):
                return None, "bad sources.%s" % fmt
            row = {}
            for wk, rel in m.items():
                if not str(wk).isdigit() or not isinstance(rel, str) or not _REL.match(rel):
                    return None, "bad source path"
                path = (base / rel).resolve()
                if base.resolve() not in path.parents or not path.is_file():
                    return None, "missing file %s" % rel
                row[int(wk)] = rel
                files[rel] = path
            if row:
                out[fmt] = dict(sorted(row.items()))
        if "jpg" not in out and "webp" not in out:
            return None, "needs a jpg or webp fallback"
        clean["sources"] = out
    clean["_files"] = files
    return clean, ""


def load(path: Path) -> dict | None:
    """Parse and validate one manifest. None if unreadable or no valid approved entries."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    items = raw.get("photos") if isinstance(raw, dict) else raw
    if not isinstance(items, list):
        return None
    good, skipped, seen = [], [], set()
    for e in items:
        c, why = validate(e, path.parent)
        if c and c["id"] in seen:
            c, why = None, "duplicate id"
        if c:
            seen.add(c["id"])
            good.append(c)
        else:
            skipped.append(((e or {}).get("id") if isinstance(e, dict) else None, why))
    if not good:
        return None
    files = {}
    for c in good:
        files.update(c.pop("_files"))
    return {"path": path, "photos": good, "skipped": skipped, "files": files}


_cache: dict = {}


def active() -> dict | None:
    """First valid manifest from manifest_candidates(), cached by mtime and size."""
    for p in manifest_candidates():
        try:
            st = p.stat()
            mt = (st.st_mtime_ns, st.st_size)
        except OSError:
            continue
        hit = _cache.get(str(p))
        if not hit or hit[0] != mt:
            hit = (mt, load(p))
            _cache[str(p)] = hit
        if hit[1]:
            return hit[1]
    return None


# ------------------------------------------------------------------ rotation order

def loc_key(e: dict) -> str:
    return re.sub(r"[^0-9a-z]+", "", str(e.get("location") or "").casefold())


def _ok(a: dict | None, b: dict | None) -> bool:
    return a is None or b is None or (a["category"] != b["category"] and loc_key(a) != loc_key(b))


def rotation_order(photos: list[dict], max_steps: int = 50000) -> list[dict]:
    """Interleave categories (saltwater, freshwater, heritage, lifestyle) so neither the
    category nor the location repeats back to back, including last -> first (the wrap).

    Depth-first search in a fixed preference order: next category in the cycle after the
    previous one, and within a category the earliest manifest entry. That yields the plain
    s, f, h, l, s, f, h, l cycle whenever the counts allow and is fully deterministic.
    If no arrangement satisfies every constraint (one category is more than half the set,
    or a single photo), it falls back to a best effort that only places a conflicting
    photo when nothing else is left.
    """
    n = len(photos)
    if n <= 1:
        return list(photos)
    queues = {c: [p for p in photos if p["category"] == c] for c in CATEGORIES}
    steps = [0]

    def prefs(prev):
        start = (CATEGORIES.index(prev["category"]) + 1) if prev else 0
        return [CATEGORIES[(start + i) % 4] for i in range(4)]

    def dfs(seq, used):
        steps[0] += 1
        if steps[0] > max_steps:
            return None
        if len(seq) == n:
            return seq if _ok(seq[-1], seq[0]) else None
        left = n - len(seq)
        counts = {c: sum(1 for p in queues[c] if id(p) not in used) for c in CATEGORIES}
        if max(counts.values()) > (left + 1) // 2:   # cannot alternate any more
            return None
        prev = seq[-1] if seq else None
        for c in prefs(prev):
            tried = set()
            for p in queues[c]:
                if id(p) in used or loc_key(p) in tried or not _ok(prev, p):
                    continue
                tried.add(loc_key(p))
                r = dfs(seq + [p], used | {id(p)})
                if r:
                    return r
        return None

    found = dfs([], frozenset())
    if found:
        return found
    # Best effort: same preference order, accept a conflict only when forced.
    seq, used = [], set()
    while len(seq) < n:
        prev = seq[-1] if seq else None
        pick = None
        for strict in (True, False):
            for c in prefs(prev):
                for p in queues[c]:
                    if id(p) not in used and (not strict or _ok(prev, p)):
                        pick = p
                        break
                if pick:
                    break
            if pick:
                break
        seq.append(pick)
        used.add(id(pick))
    return seq


# ------------------------------------------------------------------ saltwater eligibility
# Ed (Nov 16): nothing freshwater ever appears on a saltwater page. Two independent checks:
#  1. category: "freshwater" entries never rotate on saltwater pages;
#  2. location guard, in case an entry is miscategorised: its id, location and description are
#     checked against known inland waters (a fixed list plus the freshwater region names), and
#     against generic inland words (lake, river, reservoir, dam, falls, gorge, creek, mountain,
#     state park) unless a coastal word is also present (harbor, sound, inlet, ocean, beach, island,
#     seashore, bay, marsh, banks, lighthouse/light, ferry). "Silver Lake Harbor, Ocracoke" and
#     "Bay River, Bayboro" stay eligible; "Nantahala River" (filed as lifestyle) does not.
INLAND_NAMES = ("falls lake", "jordan lake", "fontana", "linville", "nantahala", "mattamuskeet",
                "cliffs of the neuse", "kerr lake", "lake gaston", "lake norman", "high rock lake",
                "badin lake", "lake wheeler", "lake raleigh", "b. everett jordan", "weldon", "roanoke rapids")
_INLAND_WORD = re.compile(r"\b(lakes?|reservoirs?|dams?|falls|gorge|rivers?|creeks?|mountains?|state park)\b", re.I)
_COAST_WORD = re.compile(r"\b(harbou?r|sound|inlet|ocean|beach|island|seashore|bay|marsh|banks|light(house)?|ferry)\b", re.I)


def _inland_names() -> tuple[str, ...]:
    names = list(INLAND_NAMES)
    try:
        import freshwater
        for rid, r in (freshwater.regions() or {}).items():
            n = str((r or {}).get("name") or "").split("(")[0].strip().casefold()
            if n:
                names.append(n)
    except Exception:
        pass
    return tuple(names)


def is_inland(e: dict) -> bool:
    text = " ".join(str(e.get(k) or "") for k in ("id", "location", "description")).replace("-", " ")
    low = text.casefold()
    if any(n in low for n in _inland_names()):
        return True
    return bool(_INLAND_WORD.search(text)) and not _COAST_WORD.search(text)


def salt_eligible(e: dict) -> bool:
    return e.get("category") != "freshwater" and not is_inland(e)


# ------------------------------------------------------------------ selection

def et_date(now: datetime | None = None) -> date:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.astimezone(ET).date()


def pick(photos: list[dict], day: date) -> dict | None:
    order = rotation_order(photos)
    return order[day.toordinal() % len(order)] if order else None


def parse_day(s: str) -> date | None:
    if not s or not _DAY.match(s):
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


# ------------------------------------------------------------------ markup

def src_url(rel: str) -> str:
    return rel if rel.startswith(("https://", "/")) else ROUTE + rel


def srcset(row: dict) -> str:
    return ", ".join("%s %dw" % (_esc(src_url(v)), int(w)) for w, v in sorted(row.items(), key=lambda kv: int(kv[0])))


def preferred(photo: dict) -> tuple[str, str]:
    """(mime, srcset) of the first format the <picture> offers: what the preload must match."""
    for fmt, mime in FORMATS:
        row = photo["sources"].get(fmt)
        if row:
            return mime, srcset(row)
    return "", ""


def picture_html(photo: dict) -> str:
    srcs = photo["sources"]
    parts = []
    fmts = [(f, m) for f, m in FORMATS if srcs.get(f)]
    for fmt, mime in fmts[:-1]:
        parts.append('<source type="%s" srcset="%s" sizes="%s">' % (mime, srcset(srcs[fmt]), SIZES))
    last = srcs[fmts[-1][0]]
    fb_w = 800 if 800 in last else min(last)
    return '<picture>%s<img src="%s" srcset="%s" sizes="%s" alt="%s" width="%d" height="%d" loading="eager" fetchpriority="high" decoding="async"></picture>' % (
        "".join(parts), _esc(src_url(last[fb_w])), srcset(last), SIZES, _esc(photo["alt"]),
        photo["width"], photo["height"])


def preload_html(photo: dict | None) -> str:
    if not photo:
        return ""
    mime, ss = preferred(photo)
    if not ss:
        return ""
    return '<link rel="preload" as="image" type="%s" imagesrcset="%s" imagesizes="%s" fetchpriority="high">\n' % (mime, ss, SIZES)


def credit_html(photo: dict) -> str:
    """The stored credit line, with the photographer linked to the source and the license
    linked to its deed when the license needs it. Public domain says so."""
    text = photo["credit"]
    lic, who = photo.get("license") or "", (photo.get("photographer") or "").strip()
    if lic.lower() == "public domain" and "public domain" not in text.lower():
        text += " (public domain)"
    out = _esc(text, quote=False)
    if lic.upper().startswith("CC"):
        if lic not in text:
            out += ", " + _esc(lic, quote=False)
        if who and photo.get("source_url") and _esc(who, False) in out:
            out = out.replace(_esc(who, False), '<a class="cr-a" href="%s" rel="noopener">%s</a>' % (_esc(photo["source_url"]), _esc(who, False)), 1)
        out = out.replace(_esc(lic, False), '<a class="cr-a" href="%s" rel="noopener license">%s</a>' % (_esc(photo["license_url"]), _esc(lic, False)), 1)
    return out


def focal_style(photo: dict) -> str:
    f = photo["focal"]
    m, d = (f, f) if isinstance(f, str) else (f.get("mobile") or f.get("desktop"), f.get("desktop") or f.get("mobile"))
    return "--fp-m:%s;--fp-d:%s;background-color:%s" % (m, d, photo["placeholder"])


def _squash(s) -> str:
    return re.sub(r"[^0-9a-z]+", "", str(s or "").casefold())


def horizon_html(photo: dict) -> str:
    """Same structure and classes as the Bodie horizon it replaces (.hz / .hz-img / .hz-cap).
    The location line is dropped when the description already names it (no repeated text)."""
    title = photo.get("description") or photo["location"]
    loc = photo["location"] if photo.get("description") and _squash(photo["location"]) not in _squash(title) else ""
    meta = " · ".join(b for b in (loc, photo.get("date") or "") if b)
    return (
        '<section class="hz hz-rot" aria-labelledby="hz-h" data-photo="%s" data-category="%s">'
        '<div class="hz-img" style="%s">%s</div>'
        '<div class="hz-cap"><p class="hz-k">Today\u2019s photograph</p><h2 id="hz-h" class="hz-t">%s</h2>%s<p class="hz-c">%s</p></div></section>'
    ) % (_esc(photo["id"]), _esc(photo["category"]), _esc(focal_style(photo)), picture_html(photo),
         _esc(title, False), ('<p class="hz-m">%s</p>' % _esc(meta, False)) if meta else "", credit_html(photo))


# ------------------------------------------------------------------ community resolution

def resolve(entry: dict, approved: list[dict]) -> dict | None:
    """Fill a catch_wall_id entry's sources from the approved store. None if no longer approved."""
    if not entry.get("catch_wall_id"):
        return entry
    cid = entry["catch_wall_id"].lower()
    rec = next((p for p in approved if str(p.get("id") or "").lower() == cid), None)
    if not rec:
        return None
    try:
        import catch_wall_public
        rec = catch_wall_public.localize_featured(rec) or rec
    except Exception:
        pass
    row = {}
    for k, v in (rec.get("src") or {}).items():
        if str(k).isdigit() and isinstance(v, str) and v.startswith(("https://", "/")):
            row[int(k)] = v
    if not row:
        return None
    fmt = "webp" if all(".webp" in v.split("?")[0] for v in row.values()) else "jpg"
    return dict(entry, sources={fmt: dict(sorted(row.items()))})


def featured(day: date | None = None, photo_id: str | None = None, approved: list[dict] | None = None,
             manifest: dict | None = None, salt: bool = False) -> dict | None:
    """Today's photo (or the given day's, or a given id: preview overrides only).
    salt=True (every saltwater page): only salt_eligible() entries, rotated among themselves, and a
    ?photo= override naming a freshwater entry is ignored."""
    man = manifest or active()
    if not man:
        return None
    if salt:
        photos = [p for p in man["photos"] if salt_eligible(p)]
        if not photos:
            return None
        man = dict(man, photos=photos)
    if approved is None:
        approved = []
        if any(p.get("catch_wall_id") for p in man["photos"]):
            try:
                import catch_wall_public
                approved = list(catch_wall_public.load_approved() or [])
            except Exception:
                approved = []
    if photo_id:
        hit = next((p for p in man["photos"] if p["id"] == photo_id), None)
        hit = resolve(hit, approved) if hit else None
        if hit:
            return hit
    # The order is built from the manifest alone, so a store hiccup never reshuffles the calendar.
    # If the day's entry can't be resolved (a submission was un-approved), the next one shows.
    order = rotation_order(man["photos"])
    i = (day or et_date()).toordinal() % len(order)
    for k in range(len(order)):
        r = resolve(order[(i + k) % len(order)], approved)
        if r:
            return r
    return None


def file_for(rel: str) -> Path | None:
    """Only files referenced by the active manifest are served."""
    man = active()
    return (man or {}).get("files", {}).get(rel) if rel and _REL.match(rel) else None
