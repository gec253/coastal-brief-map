#!/usr/bin/env python3
"""Phase 3A: station mapping and water classification for every ramp (no page UI, nothing public).

Builds data/ramp_stations.json from:
  preview/ramp-finder/map-data.json   the 285 ramp records
  data/ramp_stations_inputs.json      read-only snapshot of NLDI, USGS, NWS, CO-OPS, NCDMF and USACE lookups
  data/ramp_stations_review.json      the human review: decisions for the 79 pilot ramps

Rules (Ed, Nov 28, 2026):
- Stations are matched by waterway relevance, never by distance alone. Candidates come only from the same
  river network (USGS NLDI upstream/downstream mainstem, within 40 km along the river, under 25 miles).
- Never cross a dam for reservoir elevation or local conditions. A gauge below a dam is typed
  below_dam_release and is never used as lake elevation or local river conditions.
- No astronomical tide predictions on wind-driven waters.
- Only reviewed entries on pilot ramps are publishable. Everything else is a hidden candidate.
- This file holds station assignments only. It never holds readings.
"""
from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RECORDS = ROOT / "preview/ramp-finder/map-data.json"
INPUTS = ROOT / "data/ramp_stations_inputs.json"
REVIEW = ROOT / "data/ramp_stations_review.json"
OUT = ROOT / "data/ramp_stations.json"
TIDE_STATIONS = ROOT / "data/tide-stations.json"

PILOT_AREAS = ("Falls Lake", "Jordan Lake", "Neuse River", "Crystal Coast", "Wilmington · Wrightsville Beach",
               "Nags Head · Outer Banks", "Topsail", "Hatteras Island")
MAX_MI = 25.0
CAMA = {"Beaufort", "Bertie", "Brunswick", "Camden", "Carteret", "Chowan", "Craven", "Currituck", "Dare", "Gates",
        "Hertford", "Hyde", "New Hanover", "Onslow", "Pamlico", "Pasquotank", "Pender", "Perquimans", "Tyrrell", "Washington"}
WATER_CLASSES = ("reservoir", "natural_lake", "river", "estuary_wind_driven", "tidal_lunar", "unresolved")
TIDE_POLICIES = ("predictions", "omit_wind_driven", "omit_freshwater", "unavailable_no_same_water_station", "unresolved")
RELATIONS = ("same_waterbody", "same_river_upstream", "same_river_downstream", "below_dam_release", "related")
TYPES = ("lake_elevation", "river_stage_flow", "water_temp", "tide_predictions", "below_dam_release", "water_level_observed")
STATUSES = ("reviewed", "unreviewed", "rejected")
REG_LINKS = {
    "coastal": [{"agency": "NCDMF", "label": "NC Division of Marine Fisheries: recreational size and bag limits",
                 "url": "https://www.deq.nc.gov/about/divisions/marine-fisheries/rules-proclamations-and-size-and-bag-limits/recreational-size-and-bag-limits"}],
    "inland": [{"agency": "NCWRC", "label": "NC Wildlife Resources Commission: fishing regulations",
                "url": "https://www.ncwildlife.gov/fishing/regulations"}],
}
REG_LINKS["joint"] = REG_LINKS["coastal"] + REG_LINKS["inland"]
JURIS_MAP_URL = "https://www.deq.nc.gov/marine-fisheries/maps-current-rules/coastal-joint-inland-waters/open"
OFFICIAL_DOMAINS = ("www.deq.nc.gov", "deq.nc.gov", "www.ncwildlife.gov", "ncwildlife.gov", "www.ncwildlife.org")

# Albemarle-Pamlico system waters: small lunar tides, wind dominates water level (USGS WRI 79-46; APNEP).
APES = re.compile(r"ALBE?MARLE|PAMLICO|CURRITUCK|CROATAN|ROANOKE SOUND|KITTY HAWK BAY|CHOWAN|PASQUOTANK|PERQUIMANS|"
                  r"ALLIGATOR|SCUPPERNONG|PUNGO|BAY RIVER|NEUSE|TRENT|BRICE|DAWSON|SLOCUM|HANCOCK|GREENS CREEK|"
                  r"UPPER BROAD|BROAD CREEK|SWIFT CREEK|BLOUNTS|PANTEGO|TRANTERS|SOUTH CREEK|CASHIE|WICCACON|"
                  r"SALTERS|BIG FLATTY|EAST LAKE|NORTHWEST RIVER|LITTLE RIVER|HALLS CREEK|TULL|GOOSE", re.I)
LUNAR = re.compile(r"INTRACOASTAL|BOGUE|CORE SOUND|NEWPORT RIVER|WHITE OAK|CAPE FEAR|TAYLOR CREEK|NEW RIVER|CALICO|"
                   r"LOCKWOOD|SHALLOTTE|MASONBORO|TOPSAIL", re.I)
LAKE = re.compile(r"LAKE|RESERVOIR|POND|TAILRACE|AFTERBAY", re.I)
NATURAL_LAKES = re.compile(r"MATTAMUSKEET|WACCAMAW$|LAKE WACCAMAW|GREAT LAKE|PHELPS|LAKE RIM", re.I)
DAM_BELOW = re.compile(r"\bBL\b.*\bDAM\b|BELOW .*DAM|\bBL\b .*(ABAY|AFTERBAY)|TAILWATER|TAILRACE", re.I)
STOP = {"RIVER", "R", "LAKE", "CREEK", "CR", "NC", "NEAR", "NR", "AT", "THE", "OF", "SOUND", "B.", "EVERETT", "ABOVE",
        "BELOW", "BL", "DAM", "HWY", "RD", "SOUTH", "NORTH", "EAST", "WEST", "UPPER", "LOWER", "FORK", "PRONG", "S", "N"}


def mi(a, b, c, d):
    r = 3958.8
    p1, p2 = math.radians(a), math.radians(c)
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(d - b) / 2) ** 2
    return round(2 * r * math.asin(math.sqrt(h)), 1)


def tokens(s):
    return {t for t in re.findall(r"[A-Z][A-Z.]+", (s or "").upper()) if t not in STOP and len(t) > 2}


def classify(rec):
    w = (rec.get("w") or "").upper()
    if NATURAL_LAKES.search(w):
        return "natural_lake", "Natural lake named in the NCWRC waterbody field."
    if LAKE.search(w) and not APES.search(w):
        return "reservoir", "NCWRC waterbody field names a lake or reservoir (dammed impoundment)."
    if rec.get("co") in CAMA and APES.search(w):
        return "estuary_wind_driven", "Albemarle-Pamlico system water (USGS WRI 79-46: small lunar tides, wind dominates water level)."
    if rec.get("co") in CAMA and LUNAR.search(w):
        return "tidal_lunar", "Coastal water connected to an inlet with regular lunar tides (automatic; needs review)."
    if rec.get("co") in CAMA:
        return "unresolved", "Coastal county water that the automatic rules cannot place."
    return "river", "Inland river or creek named in the NCWRC waterbody field."


def jurisdiction(rec, hits):
    if rec.get("la") is None:
        return "unresolved", "No coordinates, so the official boundary layer cannot be queried."
    if hits is None or "ERR" in (hits or []):
        return "unresolved", "Official boundary layer query failed."
    if len(hits) == 1:
        return hits[0], "NCDMF coastal/joint/inland boundary layer (15A NCAC 03Q .0202)."
    if len(hits) > 1:
        return "unresolved", "Within 300 m of a jurisdiction boundary (%s)." % ", ".join(hits)
    if rec.get("co") not in CAMA:
        return "inland", "Outside every coastal and joint polygon in a non-coastal county: inland fishing waters."
    return "unresolved", "Coastal county, but no polygon within 300 m."


def auto_candidates(rec, cls, inp):
    s = inp["sites"].get(rec["id"]) or {}
    g = inp["usgs"]
    out = []
    seen = set()
    wt = tokens(rec.get("w"))
    for nav, ids in (("up", s.get("um") or []), ("down", s.get("dm") or [])):
        for i in ids:
            if i in seen:
                continue  # NLDI lists the gauge on the ramp's own reach in both directions
            seen.add(i)
            m = g.get(i) or {}
            name = m.get("name") or ""
            params = set(m.get("active_params") or [])
            d = mi(rec["la"], rec["lo"], m["lat"], m["lon"]) if rec.get("la") is not None and m.get("lat") is not None else None
            c = {"source": "USGS", "id": i, "name": name, "distance_mi": d, "params": sorted(params), "found": "nldi_" + nav + "stream"}
            same_name = bool(wt & tokens(name))
            if d is not None and d > MAX_MI:
                c.update(type="river_stage_flow", relation="related", status="rejected", reject_reason="More than 25 miles away.")
            elif DAM_BELOW.search(name):
                c.update(type="below_dam_release", relation="below_dam_release", status="unreviewed",
                         note="Gauge below a dam: release reading only, never lake elevation or local conditions.")
                if cls == "reservoir" and nav == "down":
                    c["note"] += " It is downstream of this reservoir's dam."
            elif cls in ("reservoir", "natural_lake"):
                if LAKE.search(name) and nav == "up":
                    c.update(type="lake_elevation", relation="related", status="rejected",
                             reject_reason="Reservoir gauge upstream of this ramp: lake gauges sit at dams, so it measures a different impoundment (crosses a dam).")
                elif LAKE.search(name) and same_name and params & {"62614", "62615"}:
                    c.update(type="lake_elevation", relation="same_waterbody", status="unreviewed")
                elif nav == "up":
                    c.update(type="river_stage_flow", relation="related", status="rejected",
                             reject_reason="Inflow gauge upstream of the reservoir: measures the tributary, not the lake.")
                else:
                    c.update(type="river_stage_flow", relation="related", status="rejected",
                             reject_reason="Downstream of the reservoir: crosses a dam, not lake conditions.")
            else:
                if LAKE.search(name):
                    c.update(type="lake_elevation", relation="related", status="rejected",
                             reject_reason="Reservoir gauge on a river ramp: crosses a dam, not river conditions.")
                elif same_name:
                    c.update(type="river_stage_flow", relation="same_river_" + ("upstream" if nav == "up" else "downstream"), status="unreviewed")
                else:
                    c.update(type="river_stage_flow", relation="related", status="unreviewed",
                             note="Connected stream with a different name (tributary or other branch); review before any use.")
            out.append(c)
            if c["status"] != "rejected" and "00010" in params and c["relation"] in ("same_waterbody", "same_river_upstream", "same_river_downstream"):
                t = dict(c, type="water_temp")
                out.append(t)
    return out


def tide_candidate(rec, tide_stations):
    """Nearest CO-OPS prediction station within 10 miles, as a hidden lead only: same water is never assumed."""
    best = None
    for t in tide_stations:
        d = mi(rec["la"], rec["lo"], t["lat"], t["lng"])
        if d <= 10 and (best is None or d < best[0]):
            best = (d, t)
    if not best:
        return []
    return [{"source": "NOAA CO-OPS", "id": best[1]["id"], "name": best[1]["name"], "type": "tide_predictions", "relation": "related",
             "status": "unreviewed", "distance_mi": best[0], "found": "nearest_within_10_mi",
             "note": "Nearest prediction station only; same water body not confirmed. Hidden until reviewed."}]


def build(records, inp, review, tide_stations=None):
    if tide_stations is None:
        tide_stations = json.loads(TIDE_STATIONS.read_text())["stations"]
    rv = review.get("sites", {})
    sites = []
    for rec in records:
        pilot = rec["a"] in PILOT_AREAS
        cls, basis = classify(rec)
        s = inp["sites"].get(rec["id"]) or {}
        juris, jbasis = jurisdiction(rec, s.get("juris"))
        e = {"id": rec["id"], "name": rec["n"], "waterbody": rec.get("w"), "county": rec.get("co"), "area": rec["a"],
             "pilot": pilot, "precision": rec.get("pr"), "water_class": cls, "class_basis": basis,
             "tide_policy": None, "tide_basis": "", "nws_point": None,
             "regs": {"jurisdiction": juris, "basis": jbasis, "links": REG_LINKS.get(juris, REG_LINKS["joint"] if juris == "unresolved" else []),
                      "boundary_map": JURIS_MAP_URL},
             "stations": [], "review": {"status": "unreviewed", "reviewer": None, "date": None, "note": ""}}
        if s.get("nws"):
            o, x, y = s["nws"]
            e["nws_point"] = {"office": o, "grid_x": x, "grid_y": y, "url": "https://api.weather.gov/gridpoints/%s/%s,%s/forecast" % (o, x, y),
                              "relation": "site_grid_cell", "status": "reviewed" if pilot else "unreviewed"}
        if rec.get("la") is not None:
            e["stations"] = auto_candidates(rec, cls, inp)
        r = rv.get(rec["id"])
        if not r and cls == "tidal_lunar" and rec.get("la") is not None:
            e["stations"] += tide_candidate(rec, tide_stations)
        if r:
            for k in ("water_class", "class_basis", "tide_policy", "tide_basis"):
                if k in r:
                    e[k] = r[k]
            if "jurisdiction" in r:
                e["regs"].update(jurisdiction=r["jurisdiction"], basis=r.get("jurisdiction_basis", "Reviewed."),
                                 links=REG_LINKS[r["jurisdiction"]] if r["jurisdiction"] in REG_LINKS else REG_LINKS["joint"])
            by = {(c["id"], c["type"]): c for c in e["stations"]}
            for d in r.get("decisions", []):
                c = by.get((d["id"], d["type"]))
                if c is None:
                    c = {"source": d.get("source", "USGS"), "id": d["id"], "name": d.get("name", ""), "type": d["type"],
                         "distance_mi": d.get("distance_mi"), "found": "review"}
                    e["stations"].append(c); by[(d["id"], d["type"])] = c
                for k in ("relation", "status", "note", "reject_reason", "name", "distance_mi", "datum"):
                    if k in d:
                        c[k] = d[k]
            for c in e["stations"]:
                if c["id"] in r.get("accept", []) and c["status"] == "unreviewed" and c["relation"] != "related":
                    c["status"] = "reviewed"
                    c["note"] = (c.get("note", "") + " Reviewed: same named river, no dam between, within 25 miles.").strip()
            for c in e["stations"]:
                if c["status"] == "unreviewed" and r.get("reject_unlisted"):
                    c["status"] = "rejected"; c["reject_reason"] = c.get("reject_reason") or r["reject_unlisted"]
            if r.get("operator"):
                op = review.get("operators", {}).get(r["operator"], {})
                e["operator"] = {"key": r["operator"], "name": op.get("name"), "levels_url": op.get("levels_url"), "verdict": op.get("verdict")}
            e["review"] = {"status": r.get("status", "reviewed"), "reviewer": review.get("reviewer"), "date": review.get("date"), "note": r.get("note", "")}
        if e["tide_policy"] is None:
            e["tide_policy"] = {"reservoir": "omit_freshwater", "natural_lake": "omit_freshwater", "river": "omit_freshwater",
                                "estuary_wind_driven": "omit_wind_driven"}.get(e["water_class"], "unresolved")
            e["tide_basis"] = e["tide_basis"] or {"omit_freshwater": "Freshwater: no astronomical tide.",
                                                  "omit_wind_driven": e["class_basis"], "unresolved": "Not yet reviewed."}[e["tide_policy"]]
        for c in e["stations"]:
            c["publishable"] = bool(pilot and e["review"]["status"] == "reviewed" and c["status"] == "reviewed")
        sites.append(e)
    return {"_about": "Station assignments only; no readings. Only entries with publishable=true may ever be shown. Built by scripts/build_ramp_stations.py.",
            "built_from": {"records": "preview/ramp-finder/map-data.json", "inputs": "data/ramp_stations_inputs.json", "review": "data/ramp_stations_review.json"},
            "retrieved": inp.get("retrieved"), "pilot_areas": list(PILOT_AREAS), "max_candidate_miles": MAX_MI,
            "operators": review.get("operators", {}), "sites": sites}


def main():
    records = json.loads(RECORDS.read_text())["records"]
    inp = json.loads(INPUTS.read_text())
    review = json.loads(REVIEW.read_text())
    out = build(records, inp, review)
    OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
    print("wrote", OUT, len(out["sites"]), "sites")


if __name__ == "__main__":
    sys.exit(main())
