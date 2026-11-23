"""Wind & Radar homepage section (approved Concept A). Off until HOME_SHOWCASE is enabled.

Every public region's homepage (saltwater and freshwater) shows the section when
HOME_SHOWCASE is 1/true/on/yes (the flag defaults OFF). Each region's instruments are
centred on that region's own NWS forecast point from data/regions.json (Crystal Coast keeps
its original framing). A region without a map location gets a plain explanation in place of
the instruments, never Crystal Coast data under another name. With the flag off, the homepage is
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
/wind and /radar are public and indexable so the Open links work; /lab/wind stays preview-gated.
"""
from __future__ import annotations

import html as _html
import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
GFS_CREDIT = "Wind: NOAA NCEP GFS 0.25° model forecast (10 m), via NOMADS."


def enabled() -> bool:
    """True only when HOME_SHOWCASE is explicitly on. Defaults off, including on Render."""
    return (os.environ.get("HOME_SHOWCASE") or "").strip().lower() in ("1", "true", "on", "yes")


# Crystal Coast keeps the approved Concept A framing exactly (home dot at Morehead City,
# face centred a little offshore so Cape Lookout and the sound are in view).
_CC = {"id": "crystal-coast", "name": "Crystal Coast", "label": "Morehead City",
       "lat": 34.72, "lon": -76.70, "clat": 34.62, "clon": -76.75}
# Data domain of /api/home-wind (windgrid.BBOX) and the Census coastline file. A focus point
# outside it cannot be drawn honestly, so the instrument says so instead.
_DOMAIN = (32.5, 37.5, -80.0, -73.0)


def _regions() -> list:
    try:
        d = json.loads((ROOT / "data" / "regions.json").read_text(encoding="utf-8"))
        return d.get("regions") or [] if isinstance(d, dict) else d
    except Exception:
        return []


def focus(region: str | None) -> dict:
    """Geographic focus for a region's instruments: name, point label, point and face centre.

    Uses the region's own NWS forecast point from data/regions.json (the same point the
    conditions instruments use). Returns {"id", "name", "supported": False} when the region has
    no usable point, so the section explains rather than falling back to Morehead City."""
    if region in (None, "", "crystal-coast"):
        return dict(_CC, supported=True)
    for r in _regions():
        if r.get("id") != region:
            continue
        name = r.get("name") or region
        fc = r.get("forecast") or {}
        lat, lon = fc.get("lat"), fc.get("lon")
        ok = (isinstance(lat, (int, float)) and isinstance(lon, (int, float))
              and _DOMAIN[0] <= lat <= _DOMAIN[1] and _DOMAIN[2] <= lon <= _DOMAIN[3])
        if not ok:
            return {"id": region, "name": name, "supported": False}
        return {"id": region, "name": name, "label": fc.get("label") or name,
                "lat": round(lat, 4), "lon": round(lon, 4), "clat": round(lat, 4), "clon": round(lon, 4),
                "supported": True, "fresh": (r.get("waterType") == "freshwater")}
    return {"id": region, "name": region, "supported": False}


def variant(query: dict, region: str | None) -> str | None:
    """Return "A" for any region's homepage when the flag is on; otherwise None.

    Callers only reach this for regions that are public (or preview-cookie pages); the server
    404s unknown and non-public ids before rendering."""
    if not enabled():
        return None
    return "A"


def _inst(kind: str, v: str, href: str = "") -> str:
    if kind == "wind":
        return (
            '<a class="sc-inst sc-wind" href="%s">'
            '<span class="sc-top"><span class="sc-name">Wind</span><span class="sc-tag sc-tag-model">Model forecast · GFS</span></span>'
            '<span class="sc-face"><canvas class="sc-cv" aria-hidden="true"></canvas>'
            '<span class="sc-read" data-k="w-read" aria-live="off">—</span><span class="sc-n" aria-hidden="true">N</span></span>'
            '<span class="sc-meta"><span class="sc-time" data-k="w-time">Valid —</span>'
            '<span class="sc-open" aria-hidden="true">Open ›</span><span class="sc-pv"> Opens the full-screen wind viewer.</span></span></a>'
            % (href or "/wind"))
    return (
        '<a class="sc-inst sc-radar" href="%s">'
        '<span class="sc-top"><span class="sc-name">Radar</span><span class="sc-tag sc-tag-obs">Observed</span></span>'
        '<span class="sc-face"><canvas class="sc-cv" aria-hidden="true"></canvas>'
        '<span class="sc-read" data-k="r-read">—</span><span class="sc-n" aria-hidden="true">N</span></span>'
        '<span class="sc-meta"><span class="sc-time" data-k="r-time">Latest frame —</span>'
        '<span class="sc-open" aria-hidden="true">Open ›</span><span class="sc-pv"> Opens the full-screen radar viewer.</span></span></a>'
        % (href or "/radar"))


def section(v: str, attribution: str = "", disclaimer: str = "", region: str | None = None) -> str:
    attr = _html.escape(attribution or "")
    disc = _html.escape(disclaimer or "")
    f = focus(region)
    name = _html.escape(f["name"])
    credit = ('<p class="sc-credit"><span>%s</span><span class="sc-sep" aria-hidden="true"> · </span><span data-k="r-attr">%s</span>'
              '<span class="sc-sep" aria-hidden="true"> · </span><span class="sc-disc" data-k="r-disc">%s</span></p>' % (GFS_CREDIT, attr, disc))
    if not f.get("supported"):
        # No map point on file: say so plainly. No canvases, no script data, no Morehead City fallback.
        return (
            '<section class="sc sc-%s" id="showcase" aria-labelledby="sc-h" data-showcase="%s" data-region="%s" data-unsupported="1">'
            '<header class="sc-head"><h2 id="sc-h">Wind &amp; Radar</h2><p class="sc-sub">%s</p></header>'
            '<p class="sc-note">The wind and radar instruments aren\'t set up for %s yet, so nothing is shown here rather than another '
            'area\'s conditions. The full-screen <a href="/wind">wind</a> and <a href="/radar">radar</a> viewers cover coastal and central North Carolina.</p>'
            '</section>' % (v.lower(), v, _html.escape(f["id"]), name, name))
    if f["id"] == "crystal-coast":
        wind_href, radar_href = "/wind", "/radar"
    else:
        at = "?at=%s,%s" % (f["lat"], f["lon"])
        wind_href, radar_href = "/wind" + at, "/radar" + at
    data = ' data-region="%s" data-label="%s" data-lat="%s" data-lon="%s" data-clat="%s" data-clon="%s"' % (
        _html.escape(f["id"]), _html.escape(f["label"]), f["lat"], f["lon"], f["clat"], f["clon"])
    return (
        '<section class="sc sc-%s" id="showcase" aria-labelledby="sc-h" data-showcase="%s"%s>'
        '<header class="sc-head"><h2 id="sc-h">Wind &amp; Radar</h2>'
        '<p class="sc-sub">%s · tap an instrument for the full-screen viewer</p></header>'
        '<p class="sc-pv">Wind and radar for %s.</p>'
        '<div class="sc-grid">%s%s</div>%s'
        '</section>' % (v.lower(), v, data, name, name,
                        _inst("wind", v, wind_href), _inst("radar", v, radar_href), credit))


def _close_of_section(doc: str, start: int) -> int:
    """Index just past the </section> that closes the <section> opening at `start`."""
    depth, i = 0, start
    for m in re.finditer(r"<section\b|</section>", doc[start:]):
        depth += 1 if m.group(0) != "</section>" else -1
        if depth == 0:
            return start + m.end()
    raise ValueError("showcase: conditions section not closed")


def inject(page: bytes, v: str, radar_meta=None, region: str | None = None) -> bytes:
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
    doc = doc[:end] + section(v, attribution, disclaimer, region) + doc[end:]
    css = (ROOT / "showcase.css").read_text(encoding="utf-8")
    # Keep the page's existing robots rules (this is a public homepage section when the flag is on).
    doc = doc.replace("</head>", '<style id="sc-css">%s</style>\n</head>' % css, 1)
    doc = doc.replace("</body>", '<script src="/showcase.js" defer></script>\n</body>', 1)
    return doc.encode("utf-8")
