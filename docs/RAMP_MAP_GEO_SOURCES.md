# Ramp Finder map: geography sources and licenses

The private statewide Ramp Finder map (`/preview/ramps-statewide/map`) draws everything from files we host
ourselves. It uses no third-party tiles and no paid services.

| Layer | File | Source | License |
| --- | --- | --- | --- |
| Coastline and land | `wind-coast/lo.json`, `wind-coast/hi.json` (shared with /wind) | U.S. Census Bureau 2025 cartographic boundary land, 1:500,000 | Public domain (U.S. government work) |
| Inland water: lakes, reservoirs, wide rivers | `preview/ramp-finder/map/geo-lo.json`, `geo-hi.json` | U.S. Census Bureau TIGER/Line® Areal Hydrography (MTFCC H2030, H2040, H3010; at least 0.4 km²), via the official TIGERweb REST service `TIGERweb/Hydro/MapServer/1` | Public domain |
| Major rivers (lines) | same files | TIGER/Line® Linear Hydrography (MTFCC H3010, named major rivers only), `TIGERweb/Hydro/MapServer/0` | Public domain |
| State boundaries | same files | TIGER/Line® States, `TIGERweb/tigerWMS_Current/MapServer/80` | Public domain |
| Place names | `geo-lo.json` labels | TIGER/Line® Incorporated Places and Census Designated Places internal points, `tigerWMS_Current/MapServer/28` and `/30` | Public domain |
| Ramp pins | `preview/ramp-finder/map-data.json` | NCWRC, NC DEQ DCM, Carteret County and N.C. State Parks official data (see `docs/RAMPS_STATEWIDE.md`) | as documented there |

## License record (checked Nov 28, 2026)

- TIGER/Line Shapefiles 2026 Technical Documentation, section 1.2: “Copyright protection is not available for any
  work of the United States Government (Title 17 U.S.C., Section 105). Thus, you are free to reproduce census
  materials as you see fit. We would ask, however, that you cite the Census Bureau as the source.”
  https://www2.census.gov/geo/pdfs/maps-data/data/tiger/tgrshp2026/TGRSHP2026_TechDoc.pdf
- Data.gov catalog entry for TIGER/Line state boundaries lists the license as CC0 1.0 (public domain) and asks that
  the U.S. Census Bureau be acknowledged as the source.
  https://catalog.data.gov/dataset/tiger-line-shapefile-2025-nation-u-s-state-and-equivalent-entities
- TIGER/Line® is a registered trademark of the U.S. Census Bureau. We use it only to name the source. The map
  attribution reads “U.S. Census Bureau TIGER/Line® water and places (public domain)”.
- Census disclaimer: no warranty is made about positional or attribute accuracy. Boundaries are for statistical
  purposes and are not legal land descriptions. Our map says “Illustration, not for navigation”.

## How the layer is built

`python3 scripts/build_ramp_geo.py` downloads the layers above for a box around North Carolina, keeps features with at
least one vertex inside North Carolina, and generalizes them:

- `geo-lo.json` (statewide view, zoom < 9): Douglas-Peucker at 0.0025° for water and 0.004° for rivers. Water rings
  smaller than about 3 km² are dropped. This file also holds the labels. Budget: 60 KB gzip or less.
- `geo-hi.json` (zoom 9 and closer, loaded only when needed): 0.0006° water and 0.0012° rivers, all features from the
  0.4 km² query. Budget: 200 KB gzip or less.

Coordinates are delta-encoded integers at 1e-4°, about 11 m.

Lake labels come from the TIGER feature names. Common names replace the abbreviated TIGER names: “Falls Lk” and “Falls
of the Neuse Reservoir” become **Falls Lake**, “B Everett Jordan Lk” becomes **Jordan Lake**, “John H Kerr Reservoir”
and “Buggs Island Lk” become **Kerr Lake**, and “Shearon Harris Reservoir” becomes **Harris Lake**. A lake is labeled
when it covers 40 km² or more, or when its name matches a ramp's official waterbody.

Accuracy is spot-checked in `tests/test_ramp_map_phase2.py`. Every Falls Lake and Jordan Lake pin, exact and approximate,
sits on the matching lake or close to it. Each lake label sits inside its own lake.
