"""Build wind-coast/enc.json from NOAA ENC Direct land areas (LNDARE).

ENC Direct to GIS is derived from official NOAA ENC cells, updated weekly, and
released to the public domain (CC0) by the Office of Coast Survey. It is not
certified for navigation. The dashboard uses it only as a close-zoom land fill
under the official NOAA ENC Chart Display Service overlay, so the fill follows
the same shoreline as the chart.

Harbor-scale LNDARE is used where those cells exist (Cape Lookout, Beaufort
Inlet, and most inlets). Coastal-scale LNDARE fills remaining shoreline,
notably Cape Hatteras, where Harbor cells do not cover the cape. The two
are not unioned before simplifying, so the coarser Coastal shoreline cannot
round off the Lookout hook. A short bridge closes the 165 m cell-edge seam.

Offline tool (not used at runtime). Needs shapely.

    # 1) Query Harbor.Land_Area (layer 233) and Coastal.Land_Area (layer 171)
    #    for the NC coastal bbox, paging at 1000 records:
    #      https://encdirect.noaa.gov/arcgis/rest/services/encdirect/enc_harbour/MapServer/233/query
    #      https://encdirect.noaa.gov/arcgis/rest/services/encdirect/enc_coastal/MapServer/171/query
    #    geometry={"xmin":-79,"ymin":33.5,"xmax":-75,"ymax":36.8,"spatialReference":{"wkid":4326}}
    #    Save FeatureCollections as harbour_lndare.geojson and coastal_lndare.geojson
    # 2) python3 scripts/build_enc_coast.py harbour_lndare.geojson coastal_lndare.geojson
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from shapely.geometry import MultiPolygon, Polygon, box, shape
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parent.parent
Q = 10000
CLIP = (-79.0, 33.5, -75.0, 36.8)
TOL_HARBOUR = 0.00005
TOL_COASTAL = 0.00008
GAP = 0.0015  # ~165 m; keeps Coastal from leaving a second shoreline along Harbor
SOURCE = (
    "NOAA Office of Coast Survey, ENC Direct to GIS, Harbor and Coastal scale land areas (LNDARE), "
    "clipped to the North Carolina coast. Harbor LNDARE is used where it exists; Coastal LNDARE "
    "fills remaining shoreline (including Cape Hatteras) so the fill follows the chart. "
    "Derived from official NOAA ENC cells but not certified for navigation. Public domain (CC0). "
    "https://encdirect.noaa.gov/"
)


def decode_census(doc):
    q = doc["q"]
    polys = []
    for p in doc["polys"]:
        rings = []
        for a in p["r"]:
            x = y = 0
            coords = []
            for i in range(0, len(a), 2):
                x += a[i]
                y += a[i + 1]
                coords.append((x / q, y / q))
            rings.append(coords)
        if not rings:
            continue
        poly = Polygon(rings[0], rings[1:])
        if not poly.is_valid:
            poly = poly.buffer(0)
        if not poly.is_empty:
            polys.append(poly)
    return unary_union(polys)


def load_fc(path):
    raw = json.loads(Path(path).read_text())
    geoms = []
    for f in raw["features"]:
        g = shape(f["geometry"])
        if not g.is_valid:
            g = g.buffer(0)
        if not g.is_empty:
            geoms.append(g)
    return unary_union(geoms)


def parts(g):
    if g.is_empty:
        return []
    if g.geom_type == "Polygon":
        return [g]
    if g.geom_type == "MultiPolygon":
        return list(g.geoms)
    return [x for x in getattr(g, "geoms", []) if x.geom_type == "Polygon"]


def clean(g, min_part=1e-6, min_hole=1e-5):
    out = []
    for p in parts(g):
        if p.area < min_part:
            continue
        holes = [i for i in p.interiors if Polygon(i).area >= min_hole]
        out.append(Polygon(p.exterior, holes))
    return MultiPolygon(out)


def ring(coords, q=Q):
    pts = [(round(x * q), round(y * q)) for x, y in coords]
    dedup = [pts[0]] + [p for a, p in zip(pts, pts[1:]) if p != a]
    if dedup[0] != dedup[-1]:
        dedup.append(dedup[0])
    if len(dedup) < 4:
        return None
    out = [dedup[0][0], dedup[0][1]]
    for (ax, ay), (bx, by) in zip(dedup, dedup[1:]):
        out += [bx - ax, by - ay]
    return out


def encode_polys(g, q=Q):
    out = []
    geoms = parts(g)
    for p in sorted(geoms, key=lambda p: -p.area):
        if p.is_empty:
            continue
        rings = [r for r in [ring(p.exterior.coords)] + [ring(i.coords) for i in p.interiors] if r]
        if not rings:
            continue
        minx, miny, maxx, maxy = p.bounds
        out.append({"b": [round(minx * q), round(miny * q), round(maxx * q), round(maxy * q)], "r": rings})
    return out


def main(harbour_src, coastal_src):
    census = decode_census(json.loads((ROOT / "wind-coast" / "hi.json").read_text()))
    shore = (
        census.intersection(box(-79.2, 33.4, -74.8, 36.9))
        .simplify(0.002, preserve_topology=True)
        .boundary.buffer(0.12)
    )
    cover = shore.simplify(0.001, preserve_topology=True)
    harbour = load_fc(harbour_src).intersection(box(*CLIP))
    coastal = load_fc(coastal_src).intersection(box(*CLIP))
    harbour_strip = clean(harbour.intersection(shore)).simplify(TOL_HARBOUR, preserve_topology=True)
    gap = coastal.difference(harbour.buffer(GAP))
    coastal_strip = clean(gap.intersection(shore), min_part=2e-5).simplify(TOL_COASTAL, preserve_topology=True)
    donut = harbour.buffer(GAP).difference(harbour)
    bridge = coastal_strip.buffer(GAP + 0.0001).intersection(donut).intersection(coastal)
    land = unary_union([harbour_strip, coastal_strip, bridge])
    doc = {
        "source": SOURCE,
        "q": Q,
        "clip": list(CLIP),
        "simplify_deg": TOL_HARBOUR,
        "zoom": [11, 99],
        "kind": "noaa-enc-lndare-harbour-coastal",
        "polys": encode_polys(land),
        "cover": encode_polys(cover),
    }
    out = ROOT / "wind-coast" / "enc.json"
    out.write_text(json.dumps(doc, separators=(",", ":")))
    print("wrote", out, out.stat().st_size, "bytes", len(doc["polys"]), "polys")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
