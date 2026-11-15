"""Multi-zone NWS alert coverage for private freshwater preview briefs.

Used only by brief_preview and river_gate. Public Falls Lake keeps its
single-point / single-zone check in freshwater.py.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

import brief_strings
import preview_zones

UA = "TheCoastalBrief/1.0 (+https://thecoastalbrief.com; coastal conditions site)"

# Verified 15 Nov 2026 from USGS site county_cd and NWS /points at each gauge,
# plus api.weather.gov zones?type=county&area=NC and zones?type=forecast&area=NC.
# Neuse reach (Falls Dam to Goldsboro): official gauges map to Wake, Johnston
# and Wayne only. The dam and 02087183 are Wake (NCZ041 / NCC183), not Durham
# or Granville. Jordan official points (dam, Haw at Moncure, Haw at Bynum) all
# map to Chatham (NCZ040 / NCC037); Wake/Durham were not added because no
# official station on this preview's instrument list maps to those counties.
NEUSE_ALERT_COUNTIES = (
    {"short": "Wake", "name": "Wake County", "id": "NCZ041", "ncc": "NCC183"},
    {"short": "Johnston", "name": "Johnston County", "id": "NCZ042", "ncc": "NCC101"},
    {"short": "Wayne", "name": "Wayne County", "id": "NCZ078", "ncc": "NCC191"},
)
JORDAN_ALERT_COUNTIES = (
    {"short": "Chatham", "name": "Chatham County", "id": "NCZ040", "ncc": "NCC037"},
)
ALERT_COUNTIES = {
    "neuse-river": NEUSE_ALERT_COUNTIES,
    "jordan-lake": JORDAN_ALERT_COUNTIES,
}


def areas_phrase(counties=None, rid: str = "") -> str:
    counties = list(counties or ALERT_COUNTIES.get(rid) or [])
    shorts = [c["short"] for c in counties]
    if not shorts:
        return "the checked area"
    if len(shorts) == 1:
        return shorts[0] + " County"
    if len(shorts) == 2:
        return "%s and %s counties" % (shorts[0], shorts[1])
    return "%s and %s counties" % (", ".join(shorts[:-1]), shorts[-1])


def zone_ids(counties=None, rid: str = "") -> list[str]:
    out = []
    for c in counties or ALERT_COUNTIES.get(rid) or []:
        out.append(c["id"])
        if c.get("ncc"):
            out.append(c["ncc"])
    return out


def _get_json(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/geo+json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode("utf-8")), None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError, ValueError) as e:
        return None, str(e) or type(e).__name__


def _items_from_geojson(data: dict) -> list[dict]:
    items, seen = [], set()
    for f in (data or {}).get("features") or []:
        p = f.get("properties") or {}
        key = p.get("id") or (p.get("event"), p.get("ends") or p.get("expires"))
        if key in seen:
            continue
        seen.add(key)
        items.append({
            "id": p.get("id"),
            "event": p.get("event"),
            "severity": p.get("severity"),
            "areas": p.get("areaDesc"),
            "ends": p.get("ends") or p.get("expires"),
            "headline": p.get("headline"),
        })
    return items


def fetch_zone(zone_id: str) -> dict:
    url = "https://api.weather.gov/alerts/active?zone=%s" % zone_id
    data, err = _get_json(url)
    if data is None:
        return {"id": zone_id, "status": "failed", "items": [], "error": err, "sourceUrl": url}
    return {"id": zone_id, "status": "ok", "items": _items_from_geojson(data), "sourceUrl": url}


def coverage_from_fetches(rid: str, fetches: list[dict]) -> dict:
    """Build the alerts payload from per-zone fetch results (no network)."""
    counties = ALERT_COUNTIES.get(rid) or ()
    by_id = {f["id"]: f for f in fetches}
    coverage = []
    failed = []
    merged, seen = [], set()
    for c in counties:
        for zid in (c["id"], c.get("ncc")):
            if not zid:
                continue
            got = by_id.get(zid) or {"id": zid, "status": "failed", "items": [], "error": "not fetched"}
            coverage.append({
                "id": zid,
                "county": c["name"],
                "status": "ok" if got.get("status") == "ok" else "failed",
                "error": got.get("error"),
                "count": len(got.get("items") or []),
            })
            if got.get("status") != "ok":
                failed.append("%s (%s)" % (c["name"], zid))
            for it in got.get("items") or []:
                key = it.get("id") or (it.get("event"), it.get("ends"))
                if key in seen:
                    continue
                seen.add(key)
                merged.append(it)
    areas = areas_phrase(counties)
    if failed:
        reason = (
            "NWS alerts check failed for %s; checked %s (%s)."
            % (", ".join(failed), areas, ", ".join(zone_ids(counties)))
        )
        return {
            "status": "failed",
            "items": merged,
            "coverage": coverage,
            "areasChecked": areas,
            "failedAreas": failed,
            "reason": reason,
            "sourceUrl": "https://api.weather.gov/alerts/active",
        }
    return {
        "status": "ok",
        "items": merged,
        "coverage": coverage,
        "areasChecked": areas,
        "failedAreas": [],
        "reason": "NWS alerts check succeeded for %s." % areas,
        "sourceUrl": "https://api.weather.gov/alerts/active",
    }


def fetch_coverage(rid: str) -> dict:
    counties = ALERT_COUNTIES.get(rid) or ()
    if not counties:
        return {"status": "unavailable", "items": [], "coverage": []}
    return coverage_from_fetches(rid, [fetch_zone(z) for z in zone_ids(counties)])


def apply_coverage(rid: str, payload: dict, fetch=fetch_coverage) -> dict:
    """Replace point alerts with multi-zone coverage unless coverage is already set."""
    if not payload or rid not in ALERT_COUNTIES:
        return payload
    al = payload.get("alerts") or {}
    if al.get("coverage"):
        return payload
    out = dict(payload)
    out["alerts"] = fetch(rid)
    return out


def alert_line(al: dict, rid: str = "", codes=None) -> str:
    ids = list(codes or zone_ids(rid=rid) or [])
    areas = preview_zones.format_alert_areas(ids) if ids else (
        al.get("areasChecked") or areas_phrase(rid=rid) or "this area"
    )
    if al.get("items"):
        import brief
        text = "; ".join(
            "%s until %s" % (a["event"], brief._t(a["ends"])) if a.get("ends") else a["event"]
            for a in al["items"]
        ) + "."
        return "Alerts: " + text
    if al.get("status") == "ok":
        return brief_strings.alerts_none(areas)
    return brief_strings.ALERTS_CHECK_FAILED


def ok_coverage(rid: str, items=None) -> dict:
    """A passing coverage payload for tests (no network)."""
    counties = ALERT_COUNTIES.get(rid) or ()
    fetches = [{"id": z, "status": "ok", "items": list(items or [])} for z in zone_ids(counties)]
    return coverage_from_fetches(rid, fetches)


def failed_coverage(rid: str, failed_ids: list[str], items=None) -> dict:
    """Partial or failed coverage for tests."""
    fetches = []
    for z in zone_ids(rid=rid):
        if z in failed_ids:
            fetches.append({"id": z, "status": "failed", "items": [], "error": "timeout"})
        else:
            fetches.append({"id": z, "status": "ok", "items": list(items or [])})
    return coverage_from_fetches(rid, fetches)


def alert_item_text(al: dict, rid: str = "") -> str:
    line = alert_line(al, rid)
    return line[len("Alerts: "):] if line.startswith("Alerts: ") else line
