"""Build the /wind coastline from the U.S. Census Bureau 2025 Cartographic Boundary File,
State and Equivalent Entities, 1:500,000 (cb_2025_us_state_500k). Public domain U.S. Government
data; acknowledgement of the Census Bureau as the source is required by the file's use constraints.

Offline tool (not used at runtime). Needs: pip install shapely pyshp
    curl -LO https://www2.census.gov/geo/tiger/GENZ2025/shp/cb_2025_us_state_500k.zip
    unzip cb_2025_us_state_500k.zip -d cb_2025
    python3 scripts/build_wind_coast.py cb_2025/cb_2025_us_state_500k.shp

Writes wind-coast/lo.json (zoomed out) and wind-coast/hi.json (zoomed in): land polygons, the
state polygons unioned so only the shoreline remains, clipped to 29–41°N, 85–68°W (beyond the
viewer's pan limits so the clip edge is never on screen). Coordinates are integers in 1e-4°
(~11 m), each ring delta-encoded: [x0, y0, dx1, dy1, ...] with x = lon, y = lat.
"""
import json
import sys
from pathlib import Path

import shapefile
from shapely.geometry import box, shape
from shapely.ops import unary_union

CLIP = (-85.0, 29.0, -68.0, 41.0)
Q = 10000
LODS = {"lo": {"tol": 0.004, "maxZoom": 7.99}, "hi": {"tol": 0.0005, "minZoom": 8}}
SOURCE = ("U.S. Census Bureau, 2025 Cartographic Boundary File, State and Equivalent Entities, 1:500,000 "
          "(cb_2025_us_state_500k), https://www2.census.gov/geo/tiger/GENZ2025/shp/cb_2025_us_state_500k.zip")


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


def main(shp):
    clip = box(*CLIP)
    geoms = [shape(s.__geo_interface__) for s in shapefile.Reader(shp).shapes()]
    land = unary_union([g.intersection(clip) for g in geoms if g.intersects(clip)])
    outdir = Path(__file__).resolve().parent.parent / "wind-coast"
    outdir.mkdir(exist_ok=True)
    for name, lod in LODS.items():
        g = land.simplify(lod["tol"], preserve_topology=True)
        polys = []
        for p in sorted(getattr(g, "geoms", [g]), key=lambda p: -p.area):
            rings = [r for r in [ring(p.exterior.coords)] + [ring(i.coords) for i in p.interiors] if r]
            if not rings:
                continue
            minx, miny, maxx, maxy = p.bounds
            polys.append({"b": [round(minx * Q), round(miny * Q), round(maxx * Q), round(maxy * Q)], "r": rings})
        doc = {"source": SOURCE, "q": Q, "clip": CLIP, "simplify_deg": lod["tol"],
               "zoom": [lod.get("minZoom", 0), lod.get("maxZoom", 99)], "polys": polys}
        (outdir / ("%s.json" % name)).write_text(json.dumps(doc, separators=(",", ":")))
        print(name, len(polys), "polys", sum(len(r) // 2 for p in polys for r in p["r"]), "pts",
              (outdir / ("%s.json" % name)).stat().st_size, "bytes")


if __name__ == "__main__":
    main(sys.argv[1])
