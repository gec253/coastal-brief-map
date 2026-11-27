#!/usr/bin/env python3
"""Statewide Ramp Finder data build (Phase 1, Ed t547u). PRIVATE PREVIEW DATA ONLY.

Pulls the official NCWRC Boating Access Areas feature service, merges it with the
manually verified Ramp Finder inventory (preview/ramp-finder/inventory.json), applies
dated official notices (preview/ramp-finder/official_notices.json), and writes one
static file: preview/ramp-finder/statewide.json.

Rules (documented in docs/RAMPS_STATEWIDE.md):
  * Manual records win field by field. NCWRC only fills fields the manual record
    leaves blank / "not stated", and every filled field is attributed.
  * Nothing is invented. Missing NCWRC values stay "not stated". A 0 is the
    official "no"; null is "not stated".
  * Dedupe: crosswalk (slug <-> NCWRC GlobalID) first, then coordinates within
    MATCH_RADIUS_M plus a name match. Coordinates-only near misses are flagged.
  * Last-known-good: on a fetch failure, a record-count drop above --max-drop,
    or a schema change, the previous statewide.json records are kept and the
    attempt is flagged in meta.refresh. Missing data never means "open".

Usage:
  python3 scripts/build_ramps_statewide.py                 # live refresh
  python3 scripts/build_ramps_statewide.py --from-file X   # rebuild from a saved query response
  python3 scripts/build_ramps_statewide.py --dry-run       # report only, write nothing
Exit codes: 0 = written (or unchanged), 2 = kept last-known-good, 1 = usage error.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import re
import sys
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
RF = ROOT / "preview" / "ramp-finder"
INVENTORY = RF / "inventory.json"
OUT = RF / "statewide.json"
SNAPSHOT = RF / "ncwrc_snapshot.json"
CROSSWALK = RF / "ncwrc_crosswalk.json"
NOTICES = RF / "official_notices.json"
NOAA_CACHE = RF / "noaa_tide_stations_nc.json"
REPORT = RF / "refresh-report.json"
REGIONS = ROOT / "data" / "regions.json"
OFFICIAL_COORDS = RF / "official_coordinates.json"

NCWRC_LAYER = ("https://services1.arcgis.com/YfqBAUM5nWR3yhGP/arcgis/rest/services/"
               "NCWRC_Boating_Access_Areas_view/FeatureServer/0")
NCWRC_PAGE = "https://www.ncwildlife.gov/boating/boating-access-areas"
NCWRC_ITEM = "https://www.arcgis.com/home/item.html?id=825b21606e2040aabed210d878b2f3e5"
NOAA_STATIONS = ("https://api.tidesandcurrents.noaa.gov/mdapi/prod/webapi/stations.json"
                 "?type=tidepredictions")
ET = ZoneInfo("America/New_York")

REQUIRED_FIELDS = {
    "GlobalID", "OBJECTID", "Site_Status", "BAA_Name", "BAA_Alias", "Water_Access", "Region",
    "Street", "City", "Zip", "County", "Phone", "Longitude", "Latitude", "Owner",
    "Fishing_Water_Designation", "Launch_Lane_No", "Fix_Dock_No", "Float_Dock_No",
    "Courtesy_Dock_No", "Fishing_Pier", "Parking_Trailer", "Parking_Trailer_ADA",
    "Parking_nonTrailer", "Parking_nonTrailer_ADA", "Parking_Surface", "ADA_Paved_Walkway",
    "ADA_Dock_Handrails", "Shallow_Draft_Vessel", "Motorboats_Restricted",
    "Non_Motorized_Access", "Caution_Notes", "Kiosk", "Restroom", "Trash_Can", "Lighting",
    "Closure_Reason", "Portable_Boat_Access_Type",
}
MATCH_RADIUS_M = 150.0
NEAR_FLAG_RADIUS_M = 400.0
REGION_RADIUS_MI = 20.0
FRESH_MIN_TIDE_MI = 15.0      # INLAND water farther than this from any NOAA tide station -> fresh (inferred)
TIDAL_MAX_TIDE_MI = 10.0      # COASTAL water within this of a NOAA tide station -> brackish or salt (inferred)
NEUSE_UPPER_MAX_LON = -78.0   # at or upstream (west) of the NCWRC Goldsboro BAA (lon -78.0236)
NS = "not stated"

# Documented geographic exceptions (Ed t548u). Keyed by NCWRC GlobalID; they override the radius rule
# for that one record only. The 20-mile rule itself is unchanged.
GEO_EXCEPTIONS = {
    "06bbb31d-4a33-45a2-917c-7eecba2e1e1e": {
        "area": "hatteras",
        "reason": "Rodanthe BAA (Dare County) is on Hatteras Island but 24 mi from the Cape Hatteras anchor; "
                  "listed with Hatteras Island by explicit exception (Ed t548u).",
    },
}

TYPE_DIMENSION = ("trailer", "paddle", "limited", "needs_review", "unknown")
STATUS_DIMENSION = ("listed_open", "temporarily_closed", "partially_open", "conflicting", "not_stated")

# Coastal homepage regions that can receive NCWRC records by the radius rule.
# Emerald Isle has no list of its own: its ramps are listed with the Crystal Coast.
RADIUS_REGIONS = {
    "crystal-coast": "crystal-coast",
    "emerald-isle": "crystal-coast",
    "wilmington": "wilmington",
    "topsail": "topsail",
    "nags-head": "nags-head",
    "hatteras": "hatteras",
}
AREA_LABELS = {
    "crystal-coast": "Crystal Coast",
    "falls-lake": "Falls Lake",
    "jordan-lake": "Jordan Lake",
    "neuse-river": "Neuse River",
    "wilmington": "Wilmington · Wrightsville Beach",
    "topsail": "Topsail",
    "nags-head": "Nags Head · Outer Banks",
    "hatteras": "Hatteras Island",
    "other-coastal": "Elsewhere: Coastal Plain",
    "other-piedmont": "Elsewhere: Piedmont",
    "other-mountain": "Elsewhere: Mountains",
}
REGULATORY_LABELS = {
    "INLAND": "Inland fishing waters (NCWRC rules)",
    "COASTAL": "Coastal fishing waters (NC Marine Fisheries rules)",
    "JOINT": "Joint fishing waters (both agencies)",
}


def now_et() -> dt.datetime:
    return dt.datetime.now(ET)


def haversine_m(lat1, lon1, lat2, lon2) -> float:
    r = 6371008.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def miles(m: float) -> float:
    return m / 1609.344


def slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (name or "").lower().replace("'", "")).strip("-")
    return s or "site"


_UPPER_TOKENS = {"US", "NC", "SR", "II", "III", "BAA", "WRC", "USACE", "ADA", "DOT"}


def title_name(s: str) -> str:
    if not s:
        return ""
    out = []
    for w in re.split(r"(\s+|-|/)", s.strip()):
        if not w or w.isspace() or w in "-/":
            out.append(w)
            continue
        if w.upper() in _UPPER_TOKENS:
            out.append(w.upper())
            continue
        t = w[:1].upper() + w[1:].lower()
        t = re.sub(r"'S\b", "'s", t)
        t = re.sub(r"^Mc([a-z])", lambda m: "Mc" + m.group(1).upper(), t)
        out.append(t)
    return "".join(out)


def yn(v):
    if isinstance(v, str):
        return v.strip() or NS  # NCWRC sometimes records a name here (e.g. the pier's waterbody); keep it verbatim
    if v == 1:
        return "yes"
    if v == 0:
        return "no"
    return NS


def num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else NS


def txt(v):
    v = (v or "").strip() if isinstance(v, str) else v
    return v if v not in (None, "") else NS


def stated(v) -> bool:
    return v not in (None, "", NS, "not stated in the NCWRC feature service")


def name_key(s: str) -> set:
    stop = {"the", "access", "area", "boat", "ramp", "landing", "baa", "public", "park", "at", "of"}
    return {w for w in re.findall(r"[a-z0-9]+", (s or "").lower()) if w not in stop}


def names_match(a: str, b: str) -> bool:
    ka, kb = name_key(a), name_key(b)
    return bool(ka and kb and (ka <= kb or kb <= ka or len(ka & kb) >= 2))


# ---------------------------------------------------------------- fetch

def fetch_json(url: str, timeout: int = 45) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "CoastalBrief-ramp-build/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch_ncwrc() -> tuple[list, list, dict]:
    layer = fetch_json(NCWRC_LAYER + "?f=json")
    if "error" in layer:
        raise RuntimeError(f"layer error: {layer['error']}")
    feats, offset = [], 0
    while True:
        q = fetch_json(NCWRC_LAYER + "/query?where=1%3D1&outFields=*&orderByFields=OBJECTID"
                       f"&resultOffset={offset}&resultRecordCount=1000&f=json")
        if "error" in q:
            raise RuntimeError(f"query error: {q['error']}")
        batch = q.get("features") or []
        feats += batch
        if not q.get("exceededTransferLimit") or not batch:
            break
        offset += len(batch)
    fields = [f["name"] for f in layer.get("fields") or []]
    return [f["attributes"] for f in feats], fields, layer.get("editingInfo") or {}


def load_from_file(path: str) -> tuple[list, list, dict]:
    d = json.loads(Path(path).read_text())
    if "error" in d:
        raise RuntimeError(f"saved response is an error: {d['error']}")
    feats = d.get("features")
    if feats is None:
        raise RuntimeError("saved response has no features key")
    fields = [f["name"] for f in d.get("fields") or []] or sorted({k for x in feats for k in x["attributes"]})
    return [f["attributes"] for f in feats], fields, d.get("editingInfo") or {}


def noaa_stations(fetch: bool) -> list:
    if fetch:
        try:
            d = fetch_json(NOAA_STATIONS)
            st = [{"id": s["id"], "name": s["name"], "lat": s["lat"], "lng": s["lng"], "type": s.get("type")}
                  for s in d.get("stations") or [] if s.get("state") in ("NC", "VA", "SC")]
            if len(st) >= 40:
                NOAA_CACHE.write_text(json.dumps({"source": NOAA_STATIONS, "fetched": now_et().isoformat(timespec="minutes"),
                                                  "stations": st}, indent=1) + "\n")
                return st
        except Exception:  # noqa: BLE001  fall back to the cached copy
            pass
    if NOAA_CACHE.exists():
        return json.loads(NOAA_CACHE.read_text())["stations"]
    return []


# ---------------------------------------------------------------- validation (last-known-good)

def validate(attrs: list, fields: list, prev_count: int | None, max_drop: float) -> list:
    problems = []
    missing = sorted(REQUIRED_FIELDS - set(fields))
    if missing:
        problems.append("schema change: missing fields " + ", ".join(missing))
    if not attrs:
        problems.append("no records returned")
    if prev_count and attrs and len(attrs) < prev_count * (1 - max_drop):
        problems.append(f"record count dropped from {prev_count} to {len(attrs)} (more than {int(max_drop*100)}%)")
    bad = [a.get("BAA_Name") for a in attrs if not isinstance(a.get("Latitude"), (int, float))
           or not isinstance(a.get("Longitude"), (int, float)) or not a.get("GlobalID")]
    if attrs and len(bad) > max(3, len(attrs) * 0.05):
        problems.append(f"{len(bad)} records lack coordinates or GlobalID")
    ids = [a.get("GlobalID") for a in attrs]
    if len(set(ids)) != len(ids):
        problems.append("duplicate GlobalIDs in the response")
    return problems


def diff_snapshots(prev: dict, new: dict) -> dict:
    added = sorted(set(new) - set(prev))
    removed = sorted(set(prev) - set(new))
    changed = {}
    for gid in sorted(set(prev) & set(new)):
        a, b = prev[gid], new[gid]
        delta = {k: [a.get(k), b.get(k)] for k in sorted(set(a) | set(b)) if a.get(k) != b.get(k)}
        if delta:
            changed[gid] = {"name": b.get("BAA_Name"), "fields": delta}
    return {
        "added": [{"globalid": g, "name": new[g].get("BAA_Name")} for g in added],
        "removed": [{"globalid": g, "name": prev[g].get("BAA_Name")} for g in removed],
        "changed": changed,
    }


# ---------------------------------------------------------------- normalize

def classify_access(a: dict) -> tuple[str, str]:
    portable = (a.get("Portable_Boat_Access_Type") or "").strip()
    lanes = a.get("Launch_Lane_No")
    if portable:
        return "paddle", "Paddle / carry-in access: " + portable[:1] + portable[1:].lower()
    if isinstance(lanes, int) and lanes >= 1:
        return "trailer", "Trailer launch"
    return "unknown", "Launch type not stated"


def infer_salinity(designation: str, lat: float, lon: float, stations: list) -> dict:
    near = None
    for s in stations:
        d = miles(haversine_m(lat, lon, float(s["lat"]), float(s["lng"])))
        if near is None or d < near[0]:
            near = (d, s)
    dist = round(near[0], 1) if near else None
    sid = near[1]["id"] if near else None
    base = {"basis": "inferred", "nearest_noaa_tide_station": sid, "nearest_noaa_tide_station_mi": dist}
    if designation == "INLAND" and (dist is None or dist > FRESH_MIN_TIDE_MI):
        return {**base, "class": "freshwater",
                "label": "Freshwater (inferred)",
                "method": f"NCWRC inland fishing waters and more than {FRESH_MIN_TIDE_MI:g} mi from any NOAA tide-prediction station"}
    if designation == "COASTAL" and dist is not None and dist <= TIDAL_MAX_TIDE_MI:
        return {**base, "class": "tidal",
                "label": "Brackish or salt, tidal (inferred)",
                "method": f"NCWRC coastal fishing waters within {TIDAL_MAX_TIDE_MI:g} mi of a NOAA tide-prediction station"}
    return {**base, "basis": "not_inferred", "class": "unknown", "label": "Not determined",
            "method": "Does not meet either inference rule (joint waters, or inland/coastal water near the rule edges)"}


def anchors() -> dict:
    d = json.loads(REGIONS.read_text())
    out = {}
    for r in d["regions"]:
        if r["id"] in RADIUS_REGIONS and r.get("anchor"):
            out[r["id"]] = (r["anchor"]["lat"], r["anchor"]["lon"], r["anchor"].get("label", ""))
    return out


def assign_area(a: dict, anc: dict) -> dict:
    exc = GEO_EXCEPTIONS.get(a.get("GlobalID"))
    if exc:
        return {"area": exc["area"], "rule": "Documented geographic exception: " + exc["reason"], "exception": True}
    w = (a.get("Water_Access") or "").upper()
    if w == "FALLS LAKE":
        return {"area": "falls-lake", "rule": "NCWRC waterbody is Falls Lake"}
    if w in ("LAKE JORDAN", "JORDAN LAKE"):
        return {"area": "jordan-lake", "rule": "NCWRC waterbody is Jordan Lake"}
    if w == "NEUSE RIVER":
        return {"area": "neuse-river", "rule": "NCWRC waterbody is the Neuse River"}
    best = None
    for rid, (la, lo, label) in anc.items():
        d = miles(haversine_m(a["Latitude"], a["Longitude"], la, lo))
        if d <= REGION_RADIUS_MI and (best is None or d < best[0]):
            best = (d, rid, label)
    if best:
        return {"area": RADIUS_REGIONS[best[1]],
                "rule": f"Within {REGION_RADIUS_MI:g} mi (straight line) of the {best[1]} anchor, {best[2]}; nearest anchor wins",
                "anchor_region": best[1], "anchor_distance_mi": round(best[0], 1)}
    reg = (a.get("Region") or "").upper()
    key = {"COASTAL": "other-coastal", "PIEDMONT": "other-piedmont", "MOUNTAIN": "other-mountain"}.get(reg, "other-coastal")
    return {"area": key, "rule": f"Outside every regional radius; grouped by the NCWRC administrative region ({reg.title() or 'not stated'})"}


def ncwrc_record(a: dict, slug: str, *, checked: str, data_edit: str, stations: list, anc: dict) -> dict:
    access_type, access_label = classify_access(a)
    owner = txt(a.get("Owner"))
    wrc_owned = owner == "NC WRC"
    motor_restricted = a.get("Motorboats_Restricted") == 1
    listing_class = "limited" if motor_restricted else "general"
    lat, lon = float(a["Latitude"]), float(a["Longitude"])
    area = assign_area(a, anc)
    designation = txt(a.get("Fishing_Water_Designation"))
    caution = txt(a.get("Caution_Notes"))
    flags = {"camper_only": False, "non_gas_only": False, "size_limited": False, "no_parking": False,
             "shallow_draft": a.get("Shallow_Draft_Vessel") == 1, "limited_trailer_parking": False,
             "hours_uncertain": False, "fee_conflict": False, "size_limit_note": "",
             "motorboats_restricted": motor_restricted}
    street, city, zipc = txt(a.get("Street")), title_name(a.get("City") or ""), a.get("Zip")
    addr = ", ".join(str(p) for p in (street if stated(street) else "", city, "NC", zipc or "") if p)
    rec = {
        "id": slug,
        "official_name": a.get("BAA_Name") or "",
        "display_name": title_name(a.get("BAA_Name") or ""),
        "alias": txt(a.get("BAA_Alias")),
        "area": area["area"],
        "area_label": AREA_LABELS[area["area"]],
        "body_of_water": txt(a.get("Water_Access")),
        "body_of_water_note": "",
        "county": title_name(a.get("County") or ""),
        "city": city,
        "street": street,
        "zip": str(zipc) if zipc else NS,
        "listing_class": listing_class,
        "verification_status": "official_listing",
        "record_class": "ncwrc_official_listing",
        "suitable_for_trailered_motorboats": "yes" if access_type == "trailer" and not motor_restricted else NS,
        "flags": flags,
        "managing_agency": owner,
        "program": "NCWRC Boating Access Area",
        "site_status_official": txt(a.get("Site_Status")),
        "site_status_note": ("The official Site_Status field is a recorded dataset value, "
                             f"NCWRC data last edited {data_edit}, checked {checked}. It is not a live open/closed confirmation."),
        "lanes": num(a.get("Launch_Lane_No")),
        "trailer_parking": num(a.get("Parking_Trailer")),
        "trailer_parking_ada": num(a.get("Parking_Trailer_ADA")),
        "nontrailer_parking": num(a.get("Parking_nonTrailer")),
        "nontrailer_parking_ada": num(a.get("Parking_nonTrailer_ADA")),
        "parking_surface": txt(a.get("Parking_Surface")),
        "fixed_docks": num(a.get("Fix_Dock_No")),
        "floating_docks": num(a.get("Float_Dock_No")),
        "courtesy_docks": num(a.get("Courtesy_Dock_No")),
        "fishing_pier": yn(a.get("Fishing_Pier")),
        "restrooms": yn(a.get("Restroom")),
        "lighting": yn(a.get("Lighting")),
        "kiosk": yn(a.get("Kiosk")),
        "trash_can": yn(a.get("Trash_Can")),
        "ada_paved_walkway": yn(a.get("ADA_Paved_Walkway")),
        "ada_dock_handrails": yn(a.get("ADA_Dock_Handrails")),
        "motorboats_restricted": yn(a.get("Motorboats_Restricted")),
        "non_motorized_access": yn(a.get("Non_Motorized_Access")),
        "shallow_draft_recommended": yn(a.get("Shallow_Draft_Vessel")),
        "vehicle_restrictions": "not stated in the NCWRC feature service",
        "accessibility_notes": NS,
        "restriction_notes": ("NCWRC records motorboats as restricted at this site." if motor_restricted else NS),
        "caution_notes": caution,
        "fishing_water_designation": designation,
        "salinity_class": None,  # set below from the inference
        "phone": txt(a.get("Phone")),
        "fees": {"summary": ("Free (NCWRC BAA program description: free public access). No site-specific fee is stated in the feature service."
                             if wrc_owned else f"Not stated in the NCWRC feature service. Owner: {owner}. Check with the owner."),
                 "conflict": False, "entries": []},
        "hours": {"summary": ("NCWRC BAA program description: 24 hours, 7 days a week. No site-specific hours field is in the feature service."
                              if wrc_owned else f"Not stated in the NCWRC feature service. Owner: {owner}. Check with the owner."),
                  "conflict": False, "entries": []},
        "notices": ([{"category": "standing_caution", "label": "NCWRC caution note", "text": caution, "as_of": checked,
                      "sources": [{"label": "NCWRC Boating Access Areas feature service", "url": NCWRC_LAYER}]}]
                    if stated(caution) else []),
        "directions": {"mode": "coordinates", "latitude": lat, "longitude": lon, "address": addr or NS,
                       "apple_url": f"https://maps.apple.com/?daddr={lat},{lon}",
                       "google_url": f"https://www.google.com/maps/dir/?api=1&destination={lat},{lon}",
                       "caveat": ""},
        "sources": [
            {"label": "Primary official source", "url": NCWRC_PAGE,
             "detail": f"Feature service data last edit {data_edit}", "date_checked": checked},
            {"label": "Related official page or dataset", "url": NCWRC_LAYER, "detail": "", "date_checked": checked},
            {"label": "Feature-service item", "url": NCWRC_ITEM, "detail": "", "date_checked": checked},
        ],
        "date_checked": checked,
        "notes": "",
        "coordinates_source": f"NCWRC Boating Access Areas feature service attributes (Latitude/Longitude), retrieved {checked}",
        # Phase 1 fields
        "access_type": access_type,
        "access_type_label": access_label,
        "regulatory_class": designation,
        "regulatory_label": REGULATORY_LABELS.get(designation, "Fishing-water designation not stated"),
        "salinity": infer_salinity(designation, lat, lon, stations),
        "area_rule": area,
        "ncwrc": {"globalid": a.get("GlobalID"), "objectid": a.get("OBJECTID"),
                  "region": txt(a.get("Region")), "closure_reason": txt(a.get("Closure_Reason")),
                  "data_last_edit": data_edit},
        "record_basis": "ncwrc_official_listing",
        "field_sources": {"*": f"ncwrc:{checked}"},
    }
    rec["salinity_class"] = rec["salinity"]["class"] if rec["salinity"]["class"] != "unknown" else NS
    return rec


# fields NCWRC can fill on a manual record (manual value always wins when stated)
MERGE_FIELDS = [
    "lanes", "trailer_parking", "trailer_parking_ada", "nontrailer_parking", "nontrailer_parking_ada",
    "parking_surface", "fixed_docks", "floating_docks", "courtesy_docks", "fishing_pier", "restrooms",
    "lighting", "kiosk", "trash_can", "ada_paved_walkway", "ada_dock_handrails", "motorboats_restricted",
    "non_motorized_access", "shallow_draft_recommended", "site_status_official",
    "fishing_water_designation", "phone",
]


def _norm(v):
    if isinstance(v, str):
        return v.strip().upper()
    return v


def merge_manual(man: dict, off: dict | None, checked: str, match: dict | None, manual_date: str) -> tuple[dict, list]:
    rec = json.loads(json.dumps(man))
    conflicts = []
    fs = {"*": f"manual:{man.get('date_checked') or manual_date}"}
    if off:
        for f in MERGE_FIELDS:
            mv, ov = rec.get(f), off.get(f)
            if stated(mv):
                if stated(ov) and _norm(mv) != _norm(ov):
                    conflicts.append({"id": rec["id"], "field": f, "manual": mv, "ncwrc": ov, "resolution": "manual value kept"})
            elif stated(ov):
                rec[f] = ov
                fs[f] = f"ncwrc:{checked}"
        mlat, mlon = (rec.get("directions") or {}).get("latitude"), (rec.get("directions") or {}).get("longitude")
        if isinstance(mlat, (int, float)):
            d = haversine_m(mlat, mlon, off["directions"]["latitude"], off["directions"]["longitude"])
            if d > 25:
                conflicts.append({"id": rec["id"], "field": "coordinates", "manual": [mlat, mlon],
                                  "ncwrc": [off["directions"]["latitude"], off["directions"]["longitude"]],
                                  "resolution": f"manual coordinates kept ({d:.0f} m apart)"})
        rec["ncwrc"] = off["ncwrc"]
        rec["access_type"], rec["access_type_label"] = off["access_type"], off["access_type_label"]
    else:
        rec["ncwrc"] = None
        rec["access_type"] = "trailer" if rec.get("suitable_for_trailered_motorboats") == "yes" else "unknown"
        rec["access_type_label"] = "Trailer launch" if rec["access_type"] == "trailer" else "Launch type: see restrictions"
    desig = rec.get("fishing_water_designation") or NS
    reg = desig.split(" ")[0].upper() if stated(desig) else NS
    reg = reg if reg in REGULATORY_LABELS else ("COASTAL" if desig.lower().startswith("coastal") else NS)
    rec["regulatory_class"] = reg
    rec["regulatory_label"] = REGULATORY_LABELS.get(reg, "Fishing-water designation not stated")
    sal = rec.get("salinity_class")
    rec["salinity"] = ({"basis": "verified", "class": sal, "label": sal.capitalize() + " (verified)",
                        "method": f"Recorded in the manually verified Ramp Finder inventory, checked {man.get('date_checked') or manual_date}"}
                       if stated(sal) else {"basis": "unknown", "class": "unknown", "label": "Not determined", "method": ""})
    rec["area_rule"] = {"area": rec["area"], "rule": "Manually verified area assignment (Nov 22, 2026 inventory)"}
    rec["record_basis"] = "manual_verified"
    rec["field_sources"] = fs
    if match:
        rec["dedupe"] = match
    return rec, conflicts


def apply_notices(rec: dict, notices: list, data_edit_date: str) -> None:
    """Set access_status. Dated official notices win over older dataset status."""
    st = (rec.get("site_status_official") or "").upper()
    reason = ((rec.get("ncwrc") or {}).get("closure_reason") or "")
    if st == "CLOSED TEMPORARILY":
        status = {"code": "temporarily_closed", "label": "Temporarily closed (NCWRC data)",
                  "detail": f"NCWRC lists this site as temporarily closed" + (f": {reason.rstrip('.')}." if stated(reason) else "."),
                  "as_of": data_edit_date, "source": "NCWRC Boating Access Areas feature service"}
    elif st == "OPEN" and stated(reason) and "CLOSED" in reason.upper():
        status = {"code": "conflicting", "label": "Status unclear: check before traveling",
                  "detail": f"NCWRC records Site_Status OPEN but also the closure reason “{reason}”.",
                  "as_of": data_edit_date, "source": "NCWRC Boating Access Areas feature service",
                  "review": True}
    elif st == "OPEN":
        status = {"code": "listed_open", "label": "Listed as open (not a live check)",
                  "detail": "Recorded official status, not a live open/closed confirmation.",
                  "as_of": data_edit_date if rec.get("record_basis") == "ncwrc_official_listing" else rec.get("date_checked"),
                  "source": "NCWRC Boating Access Areas feature service" if rec.get("ncwrc") else "Official source recorded in the inventory"}
    else:
        status = {"code": "not_stated", "label": "Status not stated",
                  "detail": "No official status is recorded. Treat as unknown, not open.",
                  "as_of": rec.get("date_checked"), "source": ""}
    applied = []
    for n in notices:
        hit = rec["id"] in (n.get("ids") or []) or (
            n.get("waterbody") and (rec.get("body_of_water") or "").upper() == n["waterbody"].upper())
        if not hit:
            continue
        if n.get("as_of_date", "") < (status.get("as_of") or "")[:10] and n.get("status") != "info":
            continue
        applied.append(n["key"])
        if n.get("status") in ("temporarily_closed", "partially_open", "conflicting"):
            status = {"code": n["status"], "label": n["label"], "detail": n["text"], "as_of": n["as_of_label"],
                      "source": n["source_name"], "source_url": n["source_url"], "notice": n["key"],
                      "review": n.get("review", False)}
        rec.setdefault("notices", [])
        rec["notices"] = list(rec["notices"]) + [{
            "category": "current_dated_notice", "label": n["notice_label"], "text": n["text"],
            "as_of": n["as_of_label"], "sources": [{"label": n["source_name"], "url": n["source_url"]}]}]
    rec["access_status"] = status
    rec["applied_notices"] = applied


# ---------------------------------------------------------------- build

def build(attrs: list, fields: list, edit_info: dict, *, checked: str, stations: list) -> tuple[dict, dict]:
    inv = json.loads(INVENTORY.read_text())
    manual = inv["records"]
    notices = json.loads(NOTICES.read_text())["notices"]
    cross = json.loads(CROSSWALK.read_text()) if CROSSWALK.exists() else {"by_slug": {}}
    anc = anchors()
    ts = edit_info.get("dataLastEditDate")
    data_edit = (dt.datetime.fromtimestamp(ts / 1000, ET).strftime("%Y-%m-%d %-I:%M %p ET") if ts else "not stated")
    data_edit_date = data_edit[:10] if ts else checked
    by_gid = {a["GlobalID"]: a for a in attrs if a.get("GlobalID")}
    manual_ids = {m["id"] for m in manual}

    off = {}
    used_slugs = set(manual_ids)
    gid_to_slug = {v: k for k, v in cross.get("by_slug", {}).items()}
    for a in sorted(attrs, key=lambda x: x.get("OBJECTID") or 0):
        gid = a["GlobalID"]
        slug = gid_to_slug.get(gid)
        if not slug:
            base = "baa-" + slugify(a.get("BAA_Name"))
            slug = base if base not in used_slugs else f"{base}-{slugify(a.get('County'))}"
            n = 2
            while slug in used_slugs:
                slug, n = f"{base}-{n}", n + 1
        used_slugs.add(slug)
        off[gid] = ncwrc_record(a, slug, checked=checked, data_edit=data_edit, stations=stations, anc=anc)

    # ---- dedupe manual <-> NCWRC
    matched, flags_near, report_matches = {}, [], []
    taken = set()
    for m in manual:
        gid = cross.get("by_slug", {}).get(m["id"])
        how = None
        if gid and gid in off:
            how = "crosswalk (NCWRC GlobalID)"
        else:
            gid = None
            d0 = m.get("directions") or {}
            if isinstance(d0.get("latitude"), (int, float)):
                best = None
                for g, o in off.items():
                    if g in taken:
                        continue
                    d = haversine_m(d0["latitude"], d0["longitude"], o["directions"]["latitude"], o["directions"]["longitude"])
                    if d <= NEAR_FLAG_RADIUS_M and (best is None or d < best[0]):
                        best = (d, g)
                if best:
                    o = off[best[1]]
                    nm = names_match(m["official_name"], o["official_name"]) or names_match(m["display_name"], o["display_name"])
                    if best[0] <= MATCH_RADIUS_M and nm:
                        gid, how = best[1], f"coordinates within {best[0]:.0f} m + name match"
                    else:
                        flags_near.append({"manual": m["id"], "ncwrc": o["official_name"], "ncwrc_slug": o["id"],
                                           "distance_m": round(best[0]), "name_match": nm,
                                           "resolution": "kept separate, flagged for manual review"})
            if not gid:
                for g, o in off.items():
                    if g in taken:
                        continue
                    if (o["official_name"].upper() == (m.get("official_name") or "").upper()
                            and o["county"].upper() == (m.get("county") or "").upper()):
                        gid, how = g, "exact name + county (no manual coordinates)"
                        break
        if gid:
            matched[m["id"]] = gid
            taken.add(gid)
            report_matches.append({"slug": m["id"], "globalid": gid, "ncwrc_name": off[gid]["official_name"], "method": how})

    records, conflicts = [], []
    for m in manual:
        o = off.get(matched.get(m["id"])) if m["id"] in matched else None
        rec, c = merge_manual(m, o, checked, next((x for x in report_matches if x["slug"] == m["id"]), None),
                              inv["meta"].get("date_checked", ""))
        conflicts += c
        records.append(rec)
    for gid, o in off.items():
        if gid in taken:
            continue
        records.append(o)

    # Neuse split (URL-stable: area stays neuse-river; segment is a new field)
    for r in records:
        if r["area"] == "neuse-river":
            lon = (r.get("directions") or {}).get("longitude")
            upper = isinstance(lon, (int, float)) and lon <= NEUSE_UPPER_MAX_LON
            r["neuse_segment"] = "upper" if upper else "lower"
            r["neuse_segment_label"] = ("Upper Neuse: Falls Dam to Goldsboro (freshwater)" if upper else
                                        "Lower Neuse: below Goldsboro to Pamlico Sound (includes brackish and tidal launches)")
    for r in records:
        apply_notices(r, notices, f"{data_edit_date} (NCWRC data last edit; rechecked {checked})")

    oc = json.loads(OFFICIAL_COORDS.read_text()) if OFFICIAL_COORDS.exists() else {"records": {}, "sources": {}}
    for r in records:
        r["type_dimension"] = type_dimension(r)
        c = oc["records"].get(r["id"])
        d = r.get("directions") or {}
        if c and not isinstance(d.get("latitude"), (int, float)):
            src = next((v for k, v in oc.get("sources", {}).items() if r["id"].startswith(k)), {})
            r["official_coordinates"] = {"lat": c["lat"], "lon": c["lon"], "kind": "owner_access_area_gps",
                                         "label": c.get("label", ""), "source_name": src.get("name", ""),
                                         "source_url": src.get("url", ""), "checked": oc.get("checked", checked),
                                         "note": "Owner's published access-area GPS point, not a surveyed ramp position. Directions use the address."}
        elif r["id"] in oc.get("unresolved", {}):
            r["coordinates_unresolved"] = oc["unresolved"][r["id"]]
    records.sort(key=lambda r: (r["area"], r["display_name"].lower()))
    new_cross = {"by_slug": {r["id"]: r["ncwrc"]["globalid"] for r in records if r.get("ncwrc")},
                 "note": "Stable slug <-> NCWRC GlobalID crosswalk. Slugs never change once assigned."}
    unmatched_notices = [n["key"] for n in notices if not any(n["key"] in r["applied_notices"] for r in records)]
    meta = dict(inv["meta"])
    meta.update({
        "title": "North Carolina Ramp Finder — statewide private preview (Phase 1)",
        "date_checked": checked,
        "scope": "Statewide: the manually verified Ramp Finder inventory plus every NCWRC Boating Access Area.",
        "ncwrc": {"layer": NCWRC_LAYER, "record_count": len(attrs), "data_last_edit": data_edit,
                  "license": "NCWRC: developed and maintained for free and unrestricted use; no warranty."},
        "rules": {
            "match_radius_m": MATCH_RADIUS_M, "near_flag_radius_m": NEAR_FLAG_RADIUS_M,
            "region_radius_mi": REGION_RADIUS_MI, "fresh_min_tide_mi": FRESH_MIN_TIDE_MI,
            "tidal_max_tide_mi": TIDAL_MAX_TIDE_MI, "neuse_upper_max_lon": NEUSE_UPPER_MAX_LON,
            "anchors": {k: {"lat": v[0], "lon": v[1], "label": v[2]} for k, v in anc.items()},
        },
    })
    data = {"meta": meta, "records": records}
    data["counts"] = counts(records)
    quality = {
        "matches": report_matches, "near_duplicates_flagged": flags_near, "conflicts": conflicts,
        "unmatched_notices": unmatched_notices,
        "missing": {k: [r["id"] for r in records if not stated(v(r))] for k, v in {
            "coordinates": lambda r: "x" if has_point(r) else None,
            "lanes": lambda r: r.get("lanes"),
            "trailer_parking": lambda r: r.get("trailer_parking"),
            "fees": lambda r: None if (r.get("fees") or {}).get("summary", "").lower().startswith(("not stated", "no separate")) else "x",
        }.items()},
        "review": [r["id"] for r in records if r["listing_class"] == "needs_review" or (r.get("access_status") or {}).get("review")],
    }
    return data, {"crosswalk": new_cross, "quality": quality}


def type_dimension(r: dict) -> str:
    """Access type from the listing and facility record only; never from operational status."""
    if r.get("listing_class") == "needs_review":
        return "needs_review"
    if r.get("listing_class") == "limited":
        return "limited"
    if r.get("access_type") in ("trailer", "paddle"):
        return r["access_type"]
    return "unknown"


def has_point(r: dict) -> bool:
    return isinstance((r.get("directions") or {}).get("latitude"), (int, float)) or bool(r.get("official_coordinates"))


def counts(records: list) -> dict:
    from collections import Counter
    c = {"total": len(records)}
    c["by_basis"] = dict(Counter(r["record_basis"] for r in records))
    c["by_access_type"] = dict(Counter(r["access_type"] for r in records))
    c["by_listing_class"] = dict(Counter(r["listing_class"] for r in records))
    c["by_status"] = {k: sum(1 for r in records if r["access_status"]["code"] == k) for k in STATUS_DIMENSION}
    c["by_type_dimension"] = {k: sum(1 for r in records if r["type_dimension"] == k) for k in TYPE_DIMENSION}
    c["type_by_status"] = {t: {k: sum(1 for r in records if r["type_dimension"] == t and r["access_status"]["code"] == k)
                               for k in STATUS_DIMENSION} for t in TYPE_DIMENSION}
    c["coordinates"] = {"ncwrc_or_inventory": sum(1 for r in records if isinstance((r.get("directions") or {}).get("latitude"), (int, float))),
                        "owner_access_area_gps": sum(1 for r in records if r.get("official_coordinates")),
                        "none": sum(1 for r in records if not has_point(r))}
    c["by_regulatory"] = dict(Counter(r["regulatory_class"] for r in records))
    c["by_salinity"] = dict(Counter(f'{r["salinity"]["class"]}:{r["salinity"]["basis"]}' for r in records))
    c["by_area"] = dict(Counter(r["area"] for r in records))
    c["neuse"] = dict(Counter(r.get("neuse_segment") for r in records if r["area"] == "neuse-river"))
    return c


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--from-file", help="saved FeatureServer query JSON (features + fields)")
    ap.add_argument("--max-drop", type=float, default=0.10, help="max allowed record-count drop (default 0.10)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--checked", help="date checked, YYYY-MM-DD (default: today ET)")
    ap.add_argument("--no-noaa-fetch", action="store_true", help="use the cached NOAA station list")
    args = ap.parse_args(argv)
    checked = args.checked or now_et().strftime("%Y-%m-%d")
    attempted = now_et().isoformat(timespec="minutes")
    prev_snap = json.loads(SNAPSHOT.read_text()) if SNAPSHOT.exists() else None
    prev_count = len(prev_snap["records"]) if prev_snap else None

    def keep_lkg(reason: str) -> int:
        rep = {"status": "kept_last_known_good", "attempted_at": attempted, "reason": reason,
               "previous_count": prev_count}
        if OUT.exists() and not args.dry_run:
            cur = json.loads(OUT.read_text())
            cur["meta"]["refresh"] = {**rep, "data_from": cur["meta"].get("date_checked")}
            OUT.write_text(json.dumps(cur, ensure_ascii=False, indent=1) + "\n")
            REPORT.write_text(json.dumps(rep, indent=1) + "\n")
        print(json.dumps(rep, indent=1))
        return 2

    try:
        attrs, fields, edit = load_from_file(args.from_file) if args.from_file else fetch_ncwrc()
    except Exception as e:  # noqa: BLE001
        return keep_lkg(f"fetch failed: {e}")
    problems = validate(attrs, fields, prev_count, args.max_drop)
    if problems:
        return keep_lkg("; ".join(problems))
    stations = noaa_stations(fetch=not (args.no_noaa_fetch or args.from_file))
    if not stations:
        return keep_lkg("no NOAA tide-station list available for salinity inference")
    new_snap = {"fetched_at": attempted, "editingInfo": edit, "fields": fields,
                "records": {a["GlobalID"]: a for a in attrs}}
    diff = diff_snapshots(prev_snap["records"], new_snap["records"]) if prev_snap else {"added": [], "removed": [], "changed": {}, "first_run": True}
    data, extra = build(attrs, fields, edit, checked=checked, stations=stations)
    data["meta"]["refresh"] = {"status": "ok", "attempted_at": attempted, "data_from": checked,
                               "added": len(diff["added"]), "removed": len(diff["removed"]), "changed": len(diff["changed"])}
    rep = {"status": "ok", "attempted_at": attempted, "ncwrc_count": len(attrs), "previous_count": prev_count,
           "diff": diff, "counts": data["counts"], "quality": extra["quality"]}
    if not args.dry_run:
        OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n")
        SNAPSHOT.write_text(json.dumps(new_snap, ensure_ascii=False, indent=1, sort_keys=True) + "\n")
        CROSSWALK.write_text(json.dumps(extra["crosswalk"], indent=1, sort_keys=True) + "\n")
        REPORT.write_text(json.dumps(rep, ensure_ascii=False, indent=1) + "\n")
    print(json.dumps({"status": "ok", "counts": data["counts"], "added": len(diff["added"]),
                      "removed": len(diff["removed"]), "changed": len(diff["changed"])}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
