"""Build radar-only land polygons and state-border lines for /preview/radar.

Sources (public domain / U.S. Government, used only at build time):

- U.S. Census Bureau 2025 Cartographic Boundary File, State and Equivalent
  Entities, 1:500,000 (cb_2025_us_state_500k). Acknowledgement required.
- Natural Earth land 1:50m (public domain) for Canada, Mexico, the Caribbean
  and other land inside the wide clip, so the United States is not an island
  of land in a rectangular sea.

Offline tool (not used at runtime). Needs a venv with shapely and pyshp:

    curl -LO https://www2.census.gov/geo/tiger/GENZ2025/shp/cb_2025_us_state_500k.zip
    curl -LO https://naciscdn.org/naturalearth/50m/physical/ne_50m_land.zip
    python3 scripts/build_radar_coast.py \\
        --census cb_2025/cb_2025_us_state_500k.shp \\
        --ne ne_50m_land.shp

Writes preview/radar/coast-lo.json, coast-hi.json, and borders.json.

The lo clip extends beyond any view the radar map can show at minZoom 5 on a
phone (portrait or landscape) with the center at a maxBounds corner, so no
clip edge is on screen to the north, south, east or west. The hi clip is a
tighter pad around maxBounds (zoom >= 8 cannot see as far). Land is the union
of Census states and Natural Earth land, clipped to each box, so Canada,
Mexico, Cuba and the interior stay land, and the Atlantic / Gulf stay water.

Borders are shared land boundaries between states around North Carolina.
Coordinates are integers in 1e-4° (~11 m), delta-encoded like wind-coast.
Does not modify wind-coast/ or any Wind file.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import shapefile
from shapely.geometry import box, shape
from shapely.ops import linemerge, unary_union

# Radar maxBounds is [[32.5, -86.5], [38.0, -74.0]], minZoom 5.
# At z=5 a 390x844 (or 844x390) viewport centered on a maxBounds corner can
# reach about 51°N, 16°S, 105°W, 55°W. The lo clip sits beyond that on all sides.
CLIP_LO = (-112.0, 8.0, -48.0, 58.0)
# hi is only used at zoom >= 8, where the viewport is ~2° across; pad ~4°.
CLIP_HI = (-91.0, 28.5, -70.0, 42.5)
# Borders stay local to NC and its neighbours so the payload stays lean.
BORDER_CLIP = (-87.5, 32.0, -73.5, 38.5)
BORDER_STATES = {"NC", "SC", "VA", "TN", "GA", "KY", "WV"}
Q = 10000
# lo keeps Census-level detail in a window around the radar view, and a coarser
# simplify on the far buffer so the preloaded file stays lean.
DETAIL = (-91.0, 24.0, -70.0, 43.5)  # includes Florida / the Keys and the Mid-Atlantic
LO_NEAR_TOL = 0.006
LO_FAR_TOL = 0.04
LO_FAR_MIN_AREA = 0.05  # deg^2; drop tiny far-buffer islands, keep Cuba and larger
LODS = {
    "lo": {"tol": LO_NEAR_TOL, "far_tol": LO_FAR_TOL, "maxZoom": 7.99, "clip": CLIP_LO},
    "hi": {"tol": 0.0005, "minZoom": 8, "clip": CLIP_HI},
}
BORDER_TOL = 0.02
SOURCE_CENSUS = (
    "U.S. Census Bureau, 2025 Cartographic Boundary File, State and Equivalent Entities, "
    "1:500,000 (cb_2025_us_state_500k), "
    "https://www2.census.gov/geo/tiger/GENZ2025/shp/cb_2025_us_state_500k.zip"
)
SOURCE_NE = (
    "Natural Earth land, 1:50m, public domain, "
    "https://www.naturalearthdata.com/downloads/50m-physical-vectors/"
)
SOURCE = SOURCE_CENSUS + " Unioned with " + SOURCE_NE + " for land outside the United States."


def clean(g):
    if g is None or g.is_empty:
        return g
    if not g.is_valid:
        g = g.buffer(0)
    return g


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
    g = clean(land.simplify(lod["tol"], preserve_topology=True))
    polys = []
    parts = getattr(g, "geoms", [g])
    for p in sorted(parts, key=lambda p: -p.area):
        if p is None or p.is_empty or p.area <= 0:
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
        "clip": list(lod["clip"]),
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
        "source": SOURCE_CENSUS,
        "q": Q,
        "clip": list(BORDER_CLIP),
        "simplify_deg": BORDER_TOL,
        "note": "Shared land borders between states around North Carolina. Shoreline is not included.",
        "pairs": pairs,
        "lines": lines,
        "nc_neighbors": sorted({x["a"] if x["b"] == "NC" else x["b"] for x in lines if "NC" in (x["a"], x["b"])}),
    }


def load_census_states(shp, clip):
    reader = shapefile.Reader(shp)
    fields = [f[0] for f in reader.fields[1:]]
    name_field = "STUSPS" if "STUSPS" in fields else ("STATE_ABBR" if "STATE_ABBR" in fields else None)
    if not name_field:
        raise SystemExit("shapefile has no STUSPS field: %s" % fields)
    states = {}
    for rec, s in zip(reader.iterRecords(), reader.iterShapes()):
        data = dict(zip(fields, rec))
        name = str(data.get(name_field) or "").strip()
        g = clean(shape(s.__geo_interface__))
        if not name or g is None or g.is_empty or not g.intersects(clip):
            continue
        part = clean(g.intersection(clip))
        if part is None or part.is_empty:
            continue
        states[name] = part
    return states


def load_ne_land(shp, clip):
    reader = shapefile.Reader(shp)
    parts = []
    for s in reader.iterShapes():
        g = clean(shape(s.__geo_interface__))
        if g is None or g.is_empty or not g.intersects(clip):
            continue
        part = clean(g.intersection(clip))
        if part is not None and not part.is_empty:
            parts.append(part)
    return unary_union(parts) if parts else box(*clip).difference(box(*clip))  # empty


def main(census_shp, ne_shp):
    clip_lo = box(*CLIP_LO)
    states = load_census_states(census_shp, clip_lo)
    print("census states in lo clip", len(states), sorted(states))
    us_land = unary_union(list(states.values()))
    ne_land = load_ne_land(ne_shp, clip_lo)
    print("ne land bounds", None if ne_land is None or ne_land.is_empty else ne_land.bounds)
    land_lo = clean(unary_union([us_land, ne_land]))
    outdir = Path(__file__).resolve().parent.parent / "preview" / "radar"
    outdir.mkdir(parents=True, exist_ok=True)
    for name, lod in LODS.items():
        if name == "lo":
            detail = box(*DETAIL)
            near = clean(land_lo.intersection(detail)).simplify(LO_NEAR_TOL, preserve_topology=True)
            far = clean(land_lo.difference(detail)).simplify(LO_FAR_TOL, preserve_topology=True)
            far_parts = [g for g in (far.geoms if hasattr(far, "geoms") else [far]) if g.area >= LO_FAR_MIN_AREA]
            land = clean(unary_union([near] + far_parts))
            doc = encode_land(land, {**lod, "tol": 0})  # already simplified
            doc["simplify_deg"] = LO_NEAR_TOL
            doc["simplify_deg_buffer"] = LO_FAR_TOL
        else:
            land = clean(land_lo.intersection(box(*lod["clip"])))
            doc = encode_land(land, lod)
        path = outdir / ("coast-%s.json" % name)
        path.write_text(json.dumps(doc, separators=(",", ":")))
        pts = sum(len(r) // 2 for p in doc["polys"] for r in p["r"])
        print(name, "clip", doc["clip"], len(doc["polys"]), "polys", pts, "pts", path.stat().st_size, "bytes")
    borders = encode_borders(states, clip_lo)
    bpath = outdir / "borders.json"
    bpath.write_text(json.dumps(borders, separators=(",", ":")))
    pts = sum(len(x["r"]) // 2 for x in borders["lines"])
    print("borders", borders["pairs"], "pairs", len(borders["lines"]), "segs", pts, "pts",
          "nc_neighbors", borders["nc_neighbors"], bpath.stat().st_size, "bytes")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--census", default="/tmp/cb_2025/cb_2025_us_state_500k.shp")
    ap.add_argument("--ne", default="ne_50m_land.shp")
    args = ap.parse_args()
    main(args.census, args.ne)
