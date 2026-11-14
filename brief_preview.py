"""Private preview Morning Briefs for regions that do not have a public brief yet.

Ed approved preview prep (not publication) for Wilmington, Nags Head, Emerald Isle and Topsail on
14 Nov 2026. These briefs reuse brief.build_salt (the same rules as Crystal Coast and Hatteras) and
run brief.validate as a read-only check, but they are:

- served only at /preview/brief/<region-id> to a browser holding the cb_preview cookie (404 otherwise);
- built in memory on request and kept in this module's own short cache, never in brief._mem,
  cache/briefs/ or the brief-archive branch;
- never part of brief.enabled_regions(), the 5:15 AM schedule, /api/brief/wake, or /brief.

Readings a region has no honest sensor for are shown as "unavailable" with the region's own note,
the same wording the region dashboards use. Nothing is substituted.
"""
from __future__ import annotations

import html
import re
import threading
import time
from datetime import datetime, timezone

import brief
import conditions

REGIONS = ("wilmington", "nags-head", "emerald-isle", "topsail")
TTL_S = 15 * 60
_cache: dict[str, tuple[float, dict]] = {}
_locks = {rid: threading.Lock() for rid in REGIONS}

# brief.build_salt names missing items in lower case; map them to region reading kinds.
_MISS_KIND = {"wind": "wind", "seas": "seas", "swell": "swell", "pressure": "pressure"}  # water temp: handled above


def available(rid: str) -> bool:
    """A preview brief exists for this id: one of the four regions, public on the map, and not
    already a real brief region (so a preview never shadows the live Crystal Coast/Hatteras briefs)."""
    if rid not in REGIONS:
        return False
    cfg = next((r for r in conditions.load_regions().get("regions") or [] if r.get("id") == rid), None)
    return bool(cfg) and conditions._servable(cfg, preview=True) and cfg.get("brief") is not True \
        and rid not in brief.enabled_regions(False)


def _cfg(rid: str) -> dict:
    return next((r for r in conditions.load_regions().get("regions") or [] if r.get("id") == rid), {}) or {}


def _no_sensor(spec: dict | None) -> bool:
    return bool(spec) and not (spec.get("sources") or [])


def compose(rid: str, now: datetime | None = None) -> dict:
    """Build a preview brief in memory. Never stores, archives or raises BriefInvalid."""
    now = now or datetime.now(timezone.utc)
    body = brief.build_salt(rid, now)
    cfg = _cfg(rid)
    specs = cfg.get("readings") or {}
    items = list(body["items"])
    missing = list(body["missing"])
    unavailable = []  # (label, why) shown with the dashboard's "unavailable" treatment
    # brief.build_salt already writes "Inshore unavailable" plus the offshore reading when the region
    # has no inshore sensor; list the region's note so the reader sees why.
    if _no_sensor(specs.get("waterTemp")):
        unavailable.append(("Inshore water temp", specs["waterTemp"].get("note") or "No sensor in this area."))
    # Any other missing reading the region has no sensor for gets its note, never a substitute.
    for name in list(missing):
        kind = _MISS_KIND.get(name)
        if kind and _no_sensor(specs.get(kind)):
            missing.remove(name)
            unavailable.append((name.capitalize(), specs[kind].get("note") or "No sensor in this area."))
    tide = cfg.get("tide") or {}
    if tide.get("observed") is False:
        unavailable.append(("Observed water level", "Tide times are NOAA predictions only. " + (tide.get("note") or "")))

    words = len(" ".join([v for _, v in items] + body["take"]).split())
    b = {"ok": True, "regionId": rid, "issueDate": brief._issue_date(now), "issuedAt": now.isoformat(),
         "issuedEt": brief._et(now).strftime("%a %b %-d, %-I:%M %p ET"), "reason": "preview", "words": words,
         **body, "items": items, "missing": missing, "unavailable": unavailable, "preview": True}
    errs, summary = brief.validate(b, rid, now)  # read-only: reports, never gates or stores
    b["validation"] = {**summary, "errors": errs}
    return b


def get(rid: str, now: datetime | None = None) -> tuple[int, dict]:
    if not available(rid):
        return 404, {"ok": False, "error": "No preview brief for this region."}
    with _locks[rid]:
        hit = _cache.get(rid)
        if hit and time.time() - hit[0] < TTL_S and now is None:
            return 200, hit[1]
        try:
            b = compose(rid, now)
        except Exception as e:
            return 503, {"ok": False, "error": "The preview brief could not be built right now (%s)." % (str(e) or type(e).__name__)}
        _cache[rid] = (time.time(), b)
        return 200, b


def _names() -> list[tuple[str, str]]:
    out = []
    for rid in REGIONS:
        out.append((rid, _cfg(rid).get("name") or rid))
    return out


def page(b: dict) -> str:
    """brief.page() with a private-preview banner, preview navigation, and an Unavailable section."""
    esc = html.escape
    rid = b.get("regionId") or ""
    out = brief.page(b, include_fresh=False, public=False, ads_on=False)
    nav = "".join('<a href="/preview/brief/%s"%s>%s</a>' % (esc(i), ' aria-current="page"' if i == rid else "", esc(n))
                  for i, n in _names())
    out = re.sub(r'<nav class="mb-regions" aria-label="Brief region">.*?</nav>',
                 lambda m: '<nav class="mb-regions" aria-label="Preview brief region">%s</nav>' % nav, out, count=1, flags=re.S)
    v = b.get("validation") or {}
    if v.get("errors"):
        check = "Data checks: would NOT pass (%s)." % "; ".join(v["errors"])
    else:
        bits = []
        if v.get("status") == "partial":
            bits.append("some readings missing at issue time")
        if b.get("unavailable"):
            bits.append("some readings have no local sensor, listed below")
        check = "Data checks: would pass (%s)." % ("; ".join(bits) or "all core readings present")
    banner = ('<section class="mb-pv" style="margin:0 0 14px;padding:10px 12px;border:2px dashed #8c2f23;border-radius:10px">'
              '<p style="margin:0;font-weight:700;letter-spacing:.08em;text-transform:uppercase;font-size:.72rem;color:#8c2f23">'
              'Private preview · not published</p><p style="margin:4px 0 0;font-size:.88rem">Built on request from live readings for '
              'this browser only. Not on the schedule, not archived, and not linked from the site. %s</p></section>'
              % esc(check))
    out = out.replace('<main class="mb" id="brief-body">', '<main class="mb" id="brief-body">\n  ' + banner, 1)
    out = out.replace('<p class="mb-why"> · ', '<p class="mb-why">Private preview, built on request · ', 1)
    out = out.replace("<title>Morning Brief", "<title>Preview · Morning Brief", 1)
    out = out.replace("https://thecoastalbrief.com/brief?region=%s" % esc(rid), "https://thecoastalbrief.com/preview/brief/%s" % esc(rid))
    if b.get("unavailable"):
        lis = "".join('<li><b>%s:</b> unavailable. %s</li>' % (esc(k), esc(w)) for k, w in b["unavailable"])
        sec = ('<section class="mb-miss mb-unavail" aria-label="Unavailable in this area"><p><b>Unavailable in this area</b> '
               '(no honest local sensor, so nothing is shown in its place):</p><ul>%s</ul></section>' % lis)
        out = out.replace("  <script>\n  (function(){\n    var d=document.getElementById(\"mb-details\");",
                          sec + "\n  <script>\n  (function(){\n    var d=document.getElementById(\"mb-details\");", 1)
    return out
