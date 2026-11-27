"""Build radar-only land polygons and state-border lines for /preview/radar.

Source: U.S. Census Bureau 2025 Cartographic Boundary File, State and Equivalent
Entities, 1:500,000 (cb_2025_us_state_500k). Public-domain U.S. Government data;
acknowledgement of the Census Bureau as the source is required by the file's use
constraints.

Offline tool (not used at runtime). Needs a venv with shapely and pyshp:

    curl -LO https://www2.census.gov/geo/tiger/GENZ2025/shp/cb_2025_us_state_500k.zip
    unzip cb_2025_us_state_500k.zip -d cb_2025
    python3 scripts/build_radar_coast.py cb_2025/cb_2025_us_state_500k.shp

Writes preview/radar/coast-lo.json, coast-hi.json, and borders.json. Land is the
union of all states, clipped to a box that extends beyond the radar viewer's
pannable extent so no clip edge is on screen. Borders are shared land
boundaries between states around North Carolina (so the shoreline is not
double-stroked). Coordinates are integers in 1e-4° (~11 m), delta-encoded
like wind-coast. Does not modify wind-coast/ or any Wind file.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import shapefile
from shapely.geometry import box, shape
from shapely.ops import linemerge, unary_union

# Beyond radar maxBounds [[32.5, -86.5], [38.0, -74.0]] so the clip edge stays off-screen
# even at minZoom 5 on a narrow phone.
CLIP = (-89.0, 30.0, -71.0, 40.5)
# Borders are clipped to a padded view (not the full land clip) and only states
# around North Carolina, so the payload stays lean.
BORDER_CLIP = (-87.5, 32.0, -73.5, 38.5)
BORDER_STATES = {"NC", "SC", "VA", "TN", "GA", "KY", "WV"}
Q = 10000
LODS = {"lo": {"tol": 0.004, "maxZoom": 7.99}, "hi": {"tol": 0.0005, "minZoom": 8}}
BORDER_TOL = 0.02
SOURCE = (
    "U.S. Census Bureau, 2025 Cartographic Boundary File, State and Equivalent Entities, "
    "1:500,000 (cb_2025_us_state_500k), "
    "https://www2.census.gov/geo/tiger/GENZ2025/shp/cb_2025_us_state_500k.zip"
)


def ring(coords):
    pts = [(round(x * Q), round(y * Q)) for x, y in coords]
    dedup = [pts[0]] + [p for a, p in zip(pts, pts[1:]) if p != a]
    if dedup[0] != dedup[-1]:
        dedup.append(dedup[0])
    if len(dedup) < 4:
        return None
    out = [dedup[0][0], dedup[0][1]]
    for (ax, ay), (bx, by) in zip(dedup, dedup[1:]):
        out += [bx - ax, by - ay]
    return out


def line_code(coords):
    pts = [(round(x * Q), round(y * Q)) for x, y in coords]
    dedup = [pts[0]] + [p for a, p in zip(pts, pts[1:]) if p != a]
    if len(dedup) < 2:
        return None
    out = [dedup[0][0], dedup[0][1]]
    for (ax, ay), (bx, by) in zip(dedup, dedup[1:]):
        out += [bx - ax, by - ay]
    return out


def iter_lines(geom):
    if geom is None or geom.is_empty:
        return
    t = geom.geom_type
    if t == "LineString":
        yield geom
    elif t == "MultiLineString":
        for g in geom.geoms:
            yield g
    elif t == "GeometryCollection":
        for g in geom.geoms:
            yield from iter_lines(g)


def encode_land(land, lod):
    g = land.simplify(lod["tol"], preserve_topology=True)
    polys = []
    parts = getattr(g, "geoms", [g])
    for p in sorted(parts, key=lambda p: -p.area):
        if p.is_empty or p.area <= 0:
            continue
        rings = [r for r in [ring(p.exterior.coords)] + [ring(i.coords) for i in p.interiors] if r]
        if not rings:
            continue
        minx, miny, maxx, maxy = p.bounds
        polys.append({
            "b": [round(minx * Q), round(miny * Q), round(maxx * Q), round(maxy * Q)],
            "r": rings,
        })
    return {
        "source": SOURCE,
        "q": Q,
        "clip": list(CLIP),
        "simplify_deg": lod["tol"],
        "zoom": [lod.get("minZoom", 0), lod.get("maxZoom", 99)],
        "polys": polys,
    }


def encode_borders(states_in_clip, clip):
    names = sorted(n for n in states_in_clip if n in BORDER_STATES)
    border_clip = box(*BORDER_CLIP).intersection(clip)
    lines = []
    pairs = 0
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            inter = states_in_clip[a].boundary.intersection(states_in_clip[b].boundary)
            inter = inter.intersection(border_clip)
            if inter.is_empty:
                continue
            simplified = inter.simplify(BORDER_TOL, preserve_topology=False)
            merged = linemerge(simplified) if not simplified.is_empty else simplified
            segs = []
            for ln in iter_lines(merged):
                code = line_code(ln.coords)
                if code:
                    segs.append(code)
            if not segs:
                continue
            pairs += 1
            for code in segs:
                lines.append({"a": a, "b": b, "r": code})
    return {
        "source": SOURCE,
        "q": Q,
        "clip": list(BORDER_CLIP),
        "simplify_deg": BORDER_TOL,
        "note": "Shared land borders between states around North Carolina. Shoreline is not included.",
        "pairs": pairs,
        "lines": lines,
        "nc_neighbors": sorted({x["a"] if x["b"] == "NC" else x["b"] for x in lines if "NC" in (x["a"], x["b"])}),
    }


def main(shp):
    clip = box(*CLIP)
    reader = shapefile.Reader(shp)
    fields = [f[0] for f in reader.fields[1:]]
    name_field = "STUSPS" if "STUSPS" in fields else ("STATE_ABBR" if "STATE_ABBR" in fields else None)
    if not name_field:
        raise SystemExit("shapefile has no STUSPS field: %s" % fields)
    states = {}
    for rec, s in zip(reader.iterRecords(), reader.iterShapes()):
        data = dict(zip(fields, rec))
        name = str(data.get(name_field) or "").strip()
        g = shape(s.__geo_interface__)
        if not name or not g.intersects(clip):
            continue
        part = g.intersection(clip)
        if part.is_empty:
            continue
        states[name] = part
    print("states in clip", len(states), sorted(states))
    land = unary_union(list(states.values()))
    outdir = Path(__file__).resolve().parent.parent / "preview" / "radar"
    outdir.mkdir(parents=True, exist_ok=True)
    for name, lod in LODS.items():
        doc = encode_land(land, lod)
        path = outdir / ("coast-%s.json" % name)
        path.write_text(json.dumps(doc, separators=(",", ":")))
        pts = sum(len(r) // 2 for p in doc["polys"] for r in p["r"])
        print(name, len(doc["polys"]), "polys", pts, "pts", path.stat().st_size, "bytes")
    borders = encode_borders(states, clip)
    bpath = outdir / "borders.json"
    bpath.write_text(json.dumps(borders, separators=(",", ":")))
    pts = sum(len(x["r"]) // 2 for x in borders["lines"])
    print("borders", borders["pairs"], "pairs", len(borders["lines"]), "segs", pts, "pts",
          "nc_neighbors", borders["nc_neighbors"], bpath.stat().st_size, "bytes")


if __name__ == "__main__":
    main(sys.argv[1])
