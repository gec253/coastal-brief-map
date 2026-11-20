"""Wind & Radar homepage section (approved Concept A). Off until HOME_SHOWCASE is enabled.

The Crystal Coast homepage shows the section only when HOME_SHOWCASE is 1/true/on/yes
(the flag defaults OFF). Other regions are unchanged. With the flag off, the homepage is
served unchanged and /showcase.js 404s, so merging this branch does not change the live
page until the flag is turned on.

Activation (requires Ed's approval; do not flip in this change):
  * Set HOME_SHOWCASE=1 on the Render web service as an environment variable.
    No DNS, domain, plan, or key changes. No new WeatherAPI keys.
  * Render restarts the service when the env var is saved; no code deploy is required
    if this branch is already the running build. Do not activate between 5:00 and 5:45 AM ET.
  * Deactivation: set HOME_SHOWCASE=0 (or unset it) and save; the homepage returns to the
    previous layout. /api/home-wind and /api/home-coast stay available (read-only, cached).

Data: /api/home-wind is a public, GFS-only, cached snapshot (HRRR and /api/wind-grid stay
private). /api/home-coast is the public-domain Census coastline. Radar uses the existing
public /api/radar proxy; the WeatherAPI key and signed tile URLs stay on the server.
/wind and /radar are public (noindex until the showcase is launched) so the Open links work; /lab/wind stays preview-gated.
"""
from __future__ import annotations

import html as _html
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
GFS_CREDIT = "Wind: NOAA NCEP GFS 0.25° model forecast (10 m), via NOMADS."


def enabled() -> bool:
    """True only when HOME_SHOWCASE is explicitly on. Defaults off, including on Render."""
    return (os.environ.get("HOME_SHOWCASE") or "").strip().lower() in ("1", "true", "on", "yes")


def variant(query: dict, region: str | None) -> str | None:
    """Return "A" for the Crystal Coast homepage when the flag is on; otherwise None."""
    if not enabled() or region not in (None, "", "crystal-coast"):
        return None
    return "A"


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
        '<p class="sc-pv">Wind and radar for the Crystal Coast.</p>'
        '<div class="sc-grid">%s%s</div>'
        '<p class="sc-credit"><span>%s</span><span class="sc-sep" aria-hidden="true"> · </span><span data-k="r-attr">%s</span><span class="sc-sep" aria-hidden="true"> · </span><span class="sc-disc" data-k="r-disc">%s</span></p>'
        '</section>' % (v.lower(), v, _inst("wind", v), _inst("radar", v), GFS_CREDIT, attr, disc))


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
    # Keep the page's existing robots rules (this is a public homepage section when the flag is on).
    doc = doc.replace("</head>", '<style id="sc-css">%s</style>\n</head>' % css, 1)
    doc = doc.replace("</body>", '<script src="/showcase.js" defer></script>\n</body>', 1)
    return doc.encode("utf-8")
