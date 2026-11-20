# Dashboard land backdrop (Census + NOAA ENC shoreline)

The public `/dashboard` map draws its own land fill, then keys out the cream land in the official NOAA ENC Chart Display Service overlay so the chart symbols sit on a matching shoreline. There is no Esri (or other third-party) basemap tile on `/dashboard`. `/lab/wind` still uses Esri Canvas tiles; that is a separate, private leftover and is not changed here.

`HOME_SHOWCASE` is independent of this work and stays off until Ed enables it.

## What the browser loads

- `/wind/coast-lo.json` at zoom &lt; 8 and `/wind/coast-hi.json` at zoom ≥ 8: U.S. Census Bureau 2025 cartographic boundary land, 1:500,000, built by `scripts/build_wind_coast.py`. These stay on at every zoom so inland land does not disappear.
- `/wind/coast-enc.json`, lazy-loaded only when the dashboard first reaches zoom 11 or closer: a clipped NOAA ENC land file so the coastal fill follows the chart shoreline (including the Cape Lookout hook). `/wind` does not request this file; its max zoom stays below 11.
- The official NOAA ENC Chart Display Service via `/proxy/enc` (unchanged).

The ENC file is public domain (CC0, Office of Coast Survey, ENC Direct to GIS). It is derived from official NOAA ENC cells but is **not certified for navigation**. The compact map credit and the site footer say so, and neither Census nor NOAA endorses the site. Do not describe this fill as an official chart.

## Refreshing the stored NOAA ENC shoreline file

NOAA updates ENC Direct weekly. This site does **not** fetch ENC Direct at runtime and does not refresh `wind-coast/enc.json` automatically. Updating the stored file is a manual, reviewed change: download, rebuild, visually check, run the tests, and commit. Do not add a cron job, Render job, or other automation without Ed’s approval.

### 1. Download Harbor and Coastal land areas

Query the ENC Direct MapServer layers for the North Carolina coastal bbox, paging at 1,000 records until `exceededTransferLimit` is absent:

- Harbor Land Area (LNDARE), layer 233: `https://encdirect.noaa.gov/arcgis/rest/services/encdirect/enc_harbour/MapServer/233/query`
- Coastal Land Area (LNDARE), layer 171: `https://encdirect.noaa.gov/arcgis/rest/services/encdirect/enc_coastal/MapServer/171/query`

Use `f=geojson`, `geometryType=esriGeometryEnvelope`, `inSR=4326`, `outSR=4326`, `spatialRel=esriSpatialRelIntersects`, `outFields=DSNM,OBJNAM`, `returnGeometry=true`, `resultRecordCount=1000`, and increment `resultOffset`. The envelope is:

```json
{"xmin":-79,"ymin":33.5,"xmax":-75,"ymax":36.8,"spatialReference":{"wkid":4326}}
```

Save the FeatureCollections as `harbour_lndare.geojson` and `coastal_lndare.geojson` (keep them out of the repo; they are large). Harbor-scale cells do not cover every stretch of the Outer Banks — Cape Hatteras is the main gap — which is why the Coastal layer is also required. The Approach service has been unavailable; do not rely on it.

### 2. Rebuild the baked file

The build is an offline tool and needs Shapely (not used at runtime):

```bash
python3 scripts/build_enc_coast.py harbour_lndare.geojson coastal_lndare.geojson
```

That writes `wind-coast/enc.json`. The script uses Harbor LNDARE where those cells exist, fills remaining shoreline with Coastal LNDARE, and does not union the two before simplifying, so the coarser Coastal shoreline cannot round off the Lookout hook. A short bridge closes the ~165 m cell-edge seam. Output is delta-encoded rings at 1e-4°, clipped to the NC coast, plus a `cover` mask the dashboard uses to punch Census overshoot in the coastal strip.

### 3. Verify before committing

- `python3 -m unittest tests.test_wind_coastline tests.test_dashboard_basemap tests.test_wind_viewer` (and the full suite before deploy). The coastline tests require the Lookout hook, Ocracoke village, and Cape Hatteras Light to be land, and the inlet channels to stay water. They also check that `/wind/coast-enc.json` is public, gzip works, and `/wind` does not load the ENC file.
- On `/dashboard`, with the official chart on, inspect Cape Lookout (the hook curl), Beaufort Inlet, Shackleford Banks, and Ocracoke Inlet at zoom 14. The oyster land fill should follow the chart’s black shoreline. Switch day and night; the fill uses the same approved palettes.
- Confirm a first visit at a regional zoom does not request `coast-enc.json`, and that zooming in to 11 or closer fetches it once (about 269 KB gzip).
- Confirm the map credit stays fully visible on an iPhone-width screen and does not sit under the radar controls. Required credits must not be hidden.
- File-size budget: `enc.json` should stay under 950 KB raw and 280 KB gzip-9. A large jump usually means slivers were left in the Coastal gap fill.

If the hook is rounded, Harbor and Coastal were probably unioned and simplified together; rebuild with the current script instead of a straight union. If Hatteras Light falls in the water, the Coastal download is incomplete or the clip excluded the cape.

## Cadence

ENC Direct is updated weekly. There is no required refresh interval for this site: refresh when a close-zoom shoreline no longer matches the official chart, after a major storm that redraws an inlet, or when Ed asks for a refresh. Each update is a reviewed commit, not a silent production pull.
