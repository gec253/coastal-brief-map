"""PRIVATE design preview: Wind & Radar homepage showcase (concepts A and B). Not for production.

The homepage shows a variant only when ALL of these hold:
  * the process is not on Render (Render sets RENDER / RENDER_SERVICE_ID in every service),
  * HOME_SHOWCASE=1 is set locally, and
  * the URL asks for it with ?showcase=A or ?showcase=B (Crystal Coast only).
Otherwise the default homepage is served byte-for-byte unchanged and /showcase.js 404s, so production
can never show it (same gate pattern as the radar fixture). Data comes from the existing systems:
/api/wind-grid (NOAA GFS) and /api/radar + /api/radar/tile/... (WeatherAPI via the server proxy).
"""
from __future__ import annotations

import html as _html
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VARIANTS = ("A", "B")
GFS_CREDIT = "Wind: NOAA NCEP GFS 0.25° model forecast (10 m), via NOMADS."


def enabled() -> bool:
    if os.environ.get("RENDER") or os.environ.get("RENDER_SERVICE_ID"):
        return False
    return os.environ.get("HOME_SHOWCASE", "").strip() == "1"


def variant(query: dict, region: str | None) -> str | None:
    if not enabled() or region not in (None, "", "crystal-coast"):
        return None
    v = ((query.get("showcase") or [""])[0] or "").strip().upper()
    return v if v in VARIANTS else None


def _inst(kind: str, v: str) -> str:
    if kind == "wind":
        return (
            '<a class="sc-inst sc-wind" href="/wind">'
            '<span class="sc-top"><span class="sc-name">Wind</span><span class="sc-tag sc-tag-model">Model forecast · GFS</span></span>'
            '<span class="sc-face"><canvas class="sc-cv" aria-hidden="true"></canvas>'
            '<span class="sc-read" data-k="w-read" aria-live="off">—</span><span class="sc-n" aria-hidden="true">N</span></span>'
            '<span class="sc-meta"><span class="sc-time" data-k="w-time">Valid —</span>'
            '<span class="sc-open" aria-hidden="true">Open ›</span><span class="sc-pv"> Opens the full-screen wind viewer.</span></span></a>')
    return (
        '<a class="sc-inst sc-radar" href="/radar">'
        '<span class="sc-top"><span class="sc-name">Radar</span><span class="sc-tag sc-tag-obs">Observed</span></span>'
        '<span class="sc-face"><canvas class="sc-cv" aria-hidden="true"></canvas>'
        '<span class="sc-read" data-k="r-read">—</span><span class="sc-n" aria-hidden="true">N</span></span>'
        '<span class="sc-meta"><span class="sc-time" data-k="r-time">Latest frame —</span>'
        '<span class="sc-open" aria-hidden="true">Open ›</span><span class="sc-pv"> Opens the full-screen radar viewer.</span></span></a>')


def section(v: str, attribution: str = "", disclaimer: str = "") -> str:
    attr = _html.escape(attribution or "")
    disc = _html.escape(disclaimer or "")
    return (
        '<section class="sc sc-%s" id="showcase" aria-labelledby="sc-h" data-showcase="%s">'
        '<header class="sc-head"><h2 id="sc-h">Wind &amp; Radar</h2>'
        '<p class="sc-sub">Crystal Coast · tap an instrument for the full-screen viewer</p></header>'
        '<p class="sc-pv">Design preview %s · not public</p>'
        '<div class="sc-grid">%s%s</div>'
        '<p class="sc-credit"><span>%s</span><span class="sc-sep" aria-hidden="true"> · </span><span data-k="r-attr">%s</span><span class="sc-sep" aria-hidden="true"> · </span><span class="sc-disc" data-k="r-disc">%s</span></p>'
        '</section>' % (v.lower(), v, v, _inst("wind", v), _inst("radar", v), GFS_CREDIT, attr, disc))


def _close_of_section(doc: str, start: int) -> int:
    """Index just past the </section> that closes the <section> opening at `start`."""
    depth, i = 0, start
    for m in re.finditer(r"<section\b|</section>", doc[start:]):
        depth += 1 if m.group(0) != "</section>" else -1
        if depth == 0:
            return start + m.end()
    raise ValueError("showcase: conditions section not closed")


def inject(page: bytes, v: str, radar_meta=None) -> bytes:
    doc = page.decode("utf-8")
    i = doc.find('<section class="cg')
    if i < 0 or 'id="conditions"' not in doc[i:i + 200]:
        raise ValueError("showcase: conditions section not found")
    attribution = disclaimer = ""
    if radar_meta is not None:
        try:
            _, p = radar_meta()
            attribution, disclaimer = p.get("attribution") or "", p.get("disclaimer") or ""
        except Exception:
            pass
    end = _close_of_section(doc, i)
    doc = doc[:end] + section(v, attribution, disclaimer) + doc[end:]
    css = (ROOT / "showcase.css").read_text(encoding="utf-8")
    doc = re.sub(r'<meta name="robots"[^>]*>\s*', "", doc)
    head = '<meta name="robots" content="noindex, nofollow">\n<style id="sc-css">%s</style>\n' % css
    doc = doc.replace("</head>", head + "</head>", 1)
    doc = doc.replace("</body>", '<script src="/showcase.js" defer></script>\n</body>', 1)
    return doc.encode("utf-8")
