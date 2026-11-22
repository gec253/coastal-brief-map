"""Cookie-gated “Featured in The Coastal Brief” homepage section.

The public homepage is unchanged. server.py calls inject() only when the
request has a valid cb_preview cookie. The linked article stays on its
own cookie-gated /reports/… page.

Editor-selected record: data/homepage-feature.json (one feature at a time;
no auto-rotation, no homepage JavaScript).
"""
from __future__ import annotations

import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data" / "homepage-feature.json"
CSS_PATH = ROOT / "static" / "featured-in" / "featured.css"
CSS_ID = "cb-featured-css"
SECTION_ID = "featured-in-the-coastal-brief"
LIFE_MARK = '<aside class="cb-life"'
SALT_SKIP = {"falls-lake", "jordan-lake", "neuse-river"}


def _esc(s, quote=True) -> str:
    return html.escape("" if s is None else str(s), quote=quote)


def load() -> dict | None:
    """Return the editor-selected feature, or None if the file is missing or invalid."""
    try:
        raw = json.loads(DATA.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict):
        return None
    for key in ("category", "kicker", "headline", "dek", "href", "cta"):
        if not isinstance(raw.get(key), str) or not raw[key].strip():
            return None
    href = raw["href"].strip()
    if not href.startswith("/") or href.startswith("//") or ".." in href:
        return None
    img = raw.get("image")
    if not isinstance(img, dict):
        return None
    for key in ("id", "alt", "credit", "base"):
        if not isinstance(img.get(key), str) or not img[key].strip():
            return None
    try:
        w, h = int(img.get("width")), int(img.get("height"))
    except (TypeError, ValueError):
        return None
    if w <= 0 or h <= 0:
        return None
    widths = img.get("widths") or [640, 960, 1280]
    if not isinstance(widths, list) or not all(isinstance(n, int) and n > 0 for n in widths):
        return None
    base = img["base"].strip()
    if not base.startswith("/static/featured-in/") or ".." in base:
        return None
    raw["href"] = href
    img["width"], img["height"], img["widths"], img["base"] = w, h, widths, base
    raw["image"] = img
    return raw


def should_inject(region_id: str | None) -> bool:
    """Site-wide editorial on the salt/default Hybrid homepage, not freshwater pages."""
    rid = (region_id or "").strip()
    return rid not in SALT_SKIP


def section(feature: dict | None = None) -> str:
    feat = feature if feature is not None else load()
    if not feat:
        return ""
    img = feat["image"]
    widths = img["widths"]
    base = img["base"]
    sizes = "(min-width: 900px) 48vw, 100vw"

    def srcset(ext: str) -> str:
        return ", ".join("%s-%d.%s %dw" % (base, w, ext, w) for w in widths)

    fallback = "%s-%d.jpg" % (base, max(widths))
    return """
<section class="cb-featured" id="%s" aria-labelledby="cb-feat-h">
  <p class="cb-feat-kicker">
    <span class="cb-feat-series">%s</span>
    <span class="cb-feat-cat">%s</span>
  </p>
  <div class="cb-feat-grid">
    <div class="cb-feat-media">
      <div class="cb-feat-frame">
        <picture>
          <source type="image/avif" srcset="%s" sizes="%s">
          <source type="image/webp" srcset="%s" sizes="%s">
          <img src="%s" width="%d" height="%d" alt="%s" loading="lazy" decoding="async">
        </picture>
      </div>
      <p class="cb-feat-credit">%s</p>
    </div>
    <div class="cb-feat-copy">
      <h2 id="cb-feat-h">%s</h2>
      <p class="cb-feat-dek">%s</p>
      <p class="cb-feat-cta-wrap"><a class="cb-feat-cta" href="%s">%s</a></p>
    </div>
  </div>
</section>
""" % (
        SECTION_ID,
        _esc(feat["kicker"]),
        _esc(feat["category"]),
        _esc(srcset("avif"), quote=True),
        sizes,
        _esc(srcset("webp"), quote=True),
        sizes,
        _esc(fallback),
        img["width"],
        img["height"],
        _esc(img["alt"]),
        _esc(feat["image"]["credit"]),
        _esc(feat["headline"]),
        _esc(feat["dek"]),
        _esc(feat["href"]),
        _esc(feat["cta"]),
    )


def inject(page: bytes, region_id: str | None = None) -> bytes:
    """Insert the feature after #showcase and before aside.cb-life. No-op if the
    page has no lifestyle aside, the record is invalid, or the region is freshwater.
    """
    if not should_inject(region_id):
        return page
    feat = load()
    if not feat:
        return page
    try:
        doc = page.decode("utf-8")
        css = CSS_PATH.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return page
    if LIFE_MARK not in doc or 'id="%s"' % SECTION_ID in doc:
        return page
    block = section(feat)
    if not block.strip():
        return page
    if f'id="{CSS_ID}"' not in doc:
        if "</head>" not in doc:
            return page
        doc = doc.replace("</head>", '<style id="%s">%s</style>\n</head>' % (CSS_ID, css), 1)
    doc = doc.replace(LIFE_MARK, block + LIFE_MARK, 1)
    return doc.encode("utf-8")
