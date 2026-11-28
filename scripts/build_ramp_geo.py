#!/usr/bin/env python3
"""Build the Ramp Finder map's self-hosted inland water and geography layer (Phase 2, Ed t558u).

Source: U.S. Census Bureau TIGER/Line data through the official TIGERweb REST services
(https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/). TIGER/Line products are U.S.
federal government works in the public domain (no copyright, 17 U.S.C. 105); see
docs/RAMP_MAP_GEO_SOURCES.md. Layers used:
  Hydro/MapServer/1  Areal Hydrography  (lakes H2030, reservoirs H2040, wide rivers H3010; >= 0.4 km2)
  Hydro/MapServer/0  Linear Hydrography (named major rivers, H3010)
  tigerWMS_Current/MapServer/80  States (NC and neighbours; drawn as thin boundary lines)
  tigerWMS_Current/MapServer/28 and /30  Incorporated and Census Designated Places (label points)
Geometry is generalized by the service (maxAllowableOffset) and rounded to 1e-4 degrees (about 11 m).
Lake labels are kept for lakes of 40 km2 or more, or whose name matches a ramp's waterbody.
Kept: every feature with at least one vertex inside North Carolina. Output:
preview/ramp-finder/map/geo-lo.json (statewide, zoom < 9, with labels) and geo-hi.json (zoom >= 9).
Re-run with --refresh to re-download; raw responses are cached in
--cache (outside the repo by default).

  python3 scripts/build_ramp_geo.py [--cache DIR] [--refresh]
"""
import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "preview" / "ramp-finder" / "map" / "geo-lo.json"
B = "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/"
BBOX = "-84.4,33.75,-75.3,36.65"
RIVERS = ["Neuse Riv", "Cape Fear Riv", "Roanoke Riv", "Tar Riv", "Pamlico Riv", "Yadkin Riv", "Pee Dee Riv",
          "Catawba Riv", "French Broad Riv", "Haw Riv", "Deep Riv", "Little Tennessee Riv", "Chowan Riv", "New Riv",
          "Trent Riv", "Northeast Cape Fear Riv", "Black Riv", "Lumber Riv", "Waccamaw Riv", "Dan Riv",
          "Pasquotank Riv", "Perquimans Riv", "Alligator Riv", "Pungo Riv", "South Fork Catawba Riv", "Eno Riv",
          "Hiwassee Riv", "Nolichucky Riv", "Pigeon Riv", "Tuckasegee Riv", "Watauga Riv", "Rocky Riv",
          "Uwharrie Riv", "Meherrin Riv", "Contentnea Crk", "White Oak Riv", "Newport Riv", "Scuppernong Riv",
          "Cashie Riv", "Shallotte Riv", "Mayo Riv", "Smith Riv", "Ararat Riv", "Fisher Riv", "Mitchell Riv",
          "Linville Riv", "Johns Riv", "Cane Riv"]
PLACES = ["Raleigh", "Charlotte", "Greensboro", "Durham", "Winston-Salem", "Fayetteville", "Wilmington", "Asheville",
          "Greenville", "Jacksonville", "New Bern", "Morehead City", "Beaufort", "Elizabeth City", "Nags Head", "Manteo",
          "Kitty Hawk", "Edenton", "Washington", "Goldsboro", "Kinston", "Rocky Mount", "Wilson", "Hickory", "Boone",
          "Lumberton", "Sanford", "Wake Forest", "Pittsboro", "Apex", "Henderson", "Roanoke Rapids", "Swansboro",
          "Emerald Isle", "Surf City", "Wrightsville Beach", "Southport", "Oak Island", "Murphy", "Franklin",
          "Bryson City", "Mount Airy", "Statesville", "Salisbury", "Albemarle", "Belhaven", "Plymouth", "Williamston",
          "Hatteras", "Ocracoke", "Buxton", "Creedmoor", "Holly Springs", "Smithfield", "Tarboro", "Morganton"]
MAJOR = {"Raleigh", "Charlotte", "Greensboro", "Asheville", "Wilmington"}
# TIGER names -> the names people use. Falls and Jordan are spelled out so they can never be confused.
LAKE_ALIASES = {"Falls Lk": "Falls Lake", "Falls of the Neuse Reservoir": "Falls Lake",
                "B Everett Jordan Lk": "Jordan Lake", "John H Kerr Reservoir": "Kerr Lake", "Buggs Island Lk": "Kerr Lake",
                "Shearon Harris Reservoir": "Harris Lake"}


def fetch(layer, where, fields, off, name, cache, refresh, geom=True):
    p = Path(cache) / (name + ".json")
    if p.exists() and not refresh:
        return json.loads(p.read_text())
    out, offset = [], 0
    while True:
        data = urllib.parse.urlencode(dict(where=where, geometry=BBOX, geometryType="esriGeometryEnvelope", inSR=4326,
                                           spatialRel="esriSpatialRelIntersects", outFields=fields,
                                           returnGeometry=str(geom).lower(), outSR=4326, maxAllowableOffset=off,
                                           geometryPrecision=5, f="json", resultOffset=offset,
                                           resultRecordCount=2000)).encode()
        req = urllib.request.Request(B + layer + "/query", data=data, headers={"User-Agent": "CoastalBrief-build/1.0"})
        d = json.load(urllib.request.urlopen(req, timeout=120))
        if "error" in d:
            raise SystemExit("TIGERweb error for %s: %s" % (name, d["error"]))
        out += d["features"]
        if not d.get("exceededTransferLimit"):
            break
        offset += 2000
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out))
    return out


def inside(pt, rings):
    x, y = pt
    c = False
    for ring in rings:
        j = len(ring) - 1
        for i in range(len(ring)):
            xi, yi = ring[i]; xj, yj = ring[j]
            if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
                c = not c
            j = i
    return c


def rnd(ring):
    out = []
    for x, y in ring:
        p = [round(x, 4), round(y, 4)]
        if not out or out[-1] != p:
            out.append(p)
    return out


def _dp(pts, tol):
    if len(pts) < 3:
        return pts
    keep = [False] * len(pts); keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    t2 = tol * tol
    while stack:
        a, b = stack.pop()
        (x1, y1), (x2, y2) = pts[a], pts[b]
        dx, dy = x2 - x1, y2 - y1
        L = dx * dx + dy * dy
        best, bi = -1.0, -1
        for i in range(a + 1, b):
            x, y = pts[i]
            if L == 0:
                d = (x - x1) ** 2 + (y - y1) ** 2
            else:
                t = max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / L))
                d = (x - x1 - t * dx) ** 2 + (y - y1 - t * dy) ** 2
            if d > best:
                best, bi = d, i
        if best > t2:
            keep[bi] = True
            stack += [(a, bi), (bi, b)]
    return [p for p, k in zip(pts, keep) if k]


def _ring_area(r):
    return abs(sum(r[i][0] * r[i - 1][1] - r[i - 1][0] * r[i][1] for i in range(len(r)))) / 2


def enc(line):
    """Delta-encoded 1e-4 degree integers: [x0, y0, dx1, dy1, ...]."""
    out, px, py = [], 0, 0
    for x, y in line:
        ix, iy = int(round(x * 1e4)), int(round(y * 1e4))
        out += [ix - px, iy - py]
        px, py = ix, iy
    return out


def lod(doc, wtol, rtol, min_area):
    water = []
    for rings in doc["water"]:
        rs = [_dp(r, wtol) for r in rings if _ring_area(r) >= min_area]
        rs = [r for r in rs if len(r) >= 4]
        if rs:
            water.append([enc(r) for r in rs])
    rivers = []
    for paths in doc["rivers"]:
        ps = [_dp(p, rtol) for p in paths]
        ps = [p for p in ps if len(p) >= 2]
        if ps:
            rivers.append([enc(p) for p in ps])
    states = [[enc(_dp(r, max(wtol, 0.002))) for r in rings] for rings in doc["states"]]
    return {"water": water, "rivers": rivers, "states": states}


def lake_name(n):
    if not n:
        return ""
    if n in LAKE_ALIASES:
        return LAKE_ALIASES[n]
    if n.startswith("Lk "):
        n = "Lake " + n[3:]
    if n.endswith(" Lk"):
        n = n[:-3] + " Lake"
    return n.replace(" Res", " Reservoir") if n.endswith(" Res") else n


def river_name(n):
    return n.replace(" Riv", " River").replace(" Crk", " Creek")


def build(cache, refresh):
    area = fetch("Hydro/MapServer/1", "AREAWATER>=400000 AND MTFCC IN ('H2030','H2040','H3010')",
                 "NAME,MTFCC,AREAWATER,INTPTLAT,INTPTLON", 0.0004, "area", cache, refresh)
    lin = fetch("Hydro/MapServer/0", "MTFCC='H3010' AND NAME IN (%s)" % ",".join("'%s'" % r for r in RIVERS),
                "NAME", 0.0015, "rivers", cache, refresh)
    st = fetch("tigerWMS_Current/MapServer/80", "STUSAB IN ('NC','VA','SC','GA','TN')", "STUSAB,NAME", 0.004,
               "states", cache, refresh)
    names = ",".join("'%s'" % p.replace("'", "''") for p in PLACES)
    pl = fetch("tigerWMS_Current/MapServer/28", "STATE='37' AND BASENAME IN (%s)" % names,
               "NAME,BASENAME,INTPTLAT,INTPTLON", 0.01, "places_inc", cache, refresh, geom=False)
    pl += fetch("tigerWMS_Current/MapServer/30", "STATE='37' AND BASENAME IN (%s)" % names,
                "NAME,BASENAME,INTPTLAT,INTPTLON", 0.01, "places_cdp", cache, refresh, geom=False)
    nc = [f for f in st if f["attributes"]["STUSAB"] == "NC"][0]["geometry"]["rings"]

    def in_nc(rings):
        return any(inside(pt, nc) for r in rings for pt in r[:: max(1, len(r) // 40)])

    water, lake_area, lake_pt = [], {}, {}
    for f in area:
        rings = [rnd(r) for r in f["geometry"]["rings"]]
        rings = [r for r in rings if len(r) >= 4]
        if not rings or not in_nc(rings):
            continue
        a = f["attributes"]
        water.append(rings)
        if a["MTFCC"] in ("H2030", "H2040") and a["NAME"]:
            n = lake_name(a["NAME"])
            lake_area[n] = lake_area.get(n, 0) + a["AREAWATER"]
            if n not in lake_pt or a["AREAWATER"] > lake_pt[n][0]:
                lake_pt[n] = (a["AREAWATER"], float(a["INTPTLAT"]), float(a["INTPTLON"]))
    rivers, river_pt = [], {}
    for f in lin:
        paths = [rnd(p) for p in f["geometry"]["paths"]]
        paths = [p for p in paths if len(p) >= 2]
        if not paths or not in_nc(paths):
            continue
        rivers.append(paths)
        n = river_name(f["attributes"]["NAME"])
        longest = max(paths, key=len)
        if len(longest) > len(river_pt.get(n, [])):
            river_pt[n] = longest
    states = [[rnd(r) for r in f["geometry"]["rings"]] for f in st]
    labels = []
    for n, (a, la, lo) in lake_pt.items():
        tot = lake_area[n]
        if tot >= 15e6 and inside((lo, la), nc):
            labels.append({"t": n, "k": "lake", "la": round(la, 4), "lo": round(lo, 4), "z": 8 if tot >= 40e6 else 9.5,
                           "area": tot})
    for n, path in river_pt.items():
        mid = path[len(path) // 2]
        labels.append({"t": n, "k": "river", "la": mid[1], "lo": mid[0], "z": 10})
    seen = set()
    for p in pl:
        a = p["attributes"]
        if a["BASENAME"] in seen:
            continue
        seen.add(a["BASENAME"])
        labels.append({"t": a["BASENAME"], "k": "place", "la": round(float(a["INTPTLAT"]), 4),
                       "lo": round(float(a["INTPTLON"]), 4), "z": 6 if a["BASENAME"] in MAJOR else 8})
    labels.sort(key=lambda l: (l["k"], l["t"]))
    return {
        "source": "U.S. Census Bureau, TIGER/Line® via TIGERweb REST services (Areal and Linear Hydrography, States, "
                  "Incorporated and Census Designated Places)",
        "license": "Public domain (U.S. federal government work, 17 U.S.C. 105). See docs/RAMP_MAP_GEO_SOURCES.md.",
        "generalization": "Service maxAllowableOffset 0.0004 deg (water), 0.0015 deg (rivers), 0.004 deg (states); "
                          "rounded to 1e-4 deg. Illustration, not for navigation.",
        "built": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "water": water, "rivers": rivers, "states": states, "labels": labels,
    }


RAMP_WATERS = ROOT / "preview" / "ramp-finder" / "statewide.json"


def write_outputs(doc):
    waters = " | ".join(str(r.get("body_of_water") or "") for r in json.loads(RAMP_WATERS.read_text())["records"]).lower()
    labels = []
    for l in doc["labels"]:
        if l["k"] == "lake":
            core = l["t"].lower().replace("lake ", "").replace(" lake", "").replace(" reservoir", "").strip()
            if not (l.get("area", 0) >= 40e6 or core in waters):
                continue
        labels.append({k: v for k, v in l.items() if k != "area"})
    meta = {k: doc[k] for k in ("source", "license", "generalization", "built")}
    base = doc["generalization"].replace(" Illustration, not for navigation.", "")
    lo = dict(meta, q=1e4, **lod(doc, 0.0025, 0.004, 3e-4), labels=labels)
    lo["generalization"] = base + " Then Douglas-Peucker 0.0025 deg (water), 0.004 deg (rivers); water rings under 3e-4 sq deg dropped. Illustration, not for navigation."
    hi = dict(meta, q=1e4, **lod(doc, 0.0006, 0.0012, 0))
    hi["generalization"] = base + " Then Douglas-Peucker 0.0006 deg (water), 0.0012 deg (rivers). Illustration, not for navigation."
    for name, d in (("geo-lo.json", lo), ("geo-hi.json", hi)):
        (OUT.parent / name).write_text(json.dumps(d, separators=(",", ":"), ensure_ascii=False) + "\n")
    return lo, hi


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cache", default=os.environ.get("RAMP_GEO_CACHE", "/tmp/ramp-geo-cache"))
    ap.add_argument("--refresh", action="store_true")
    a = ap.parse_args(argv)
    doc = build(a.cache, a.refresh)
    lo, hi = write_outputs(doc)
    print(json.dumps({"water": len(hi["water"]), "rivers": len(hi["rivers"]), "labels": len(lo["labels"]),
                      "lo_bytes": (OUT.parent / "geo-lo.json").stat().st_size,
                      "hi_bytes": (OUT.parent / "geo-hi.json").stat().st_size}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
