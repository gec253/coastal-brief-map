# /wind — dedicated wind viewer (private)

Phase 1 of the Wind & Radar Signature Experience (Ed, t349u, 19 Nov 2026). Branch `feature/wind-viewer-1119` from production `d000cfe`.

## What it is

A full-viewport "helm" page that animates the **NOAA NCEP GFS 0.25° 10 m wind model forecast** over coastal North Carolina. It is a **model forecast**, never a station or buoy reading, and the page says so in the top badge, the tap readout and the About note. Run time, valid time and forecast hour are shown in Eastern Time with an `ET` label; a separate `Now` clock shows the current ET time.

## Access

Private, gated exactly like `/lab/wind`: 404 unless `WIND_PARTICLES_ENABLED=1` (off in production) or the browser holds Ed's preview cookie (`/preview?key=…`). It is `noindex`, `no-store`, and not linked from the homepage, `/dashboard`, public navigation or freshwater pages. The private preview hub lists it as "Wind viewer". `/lab/wind` still works.

| Route | File |
|---|---|
| `/wind` | `wind.html` |
| `/wind.css` | `wind.css` (slim, ~9 KB; no homepage `styles.css`, no web fonts) |
| `/wind/viewer.js` | `wind-viewer.js` (UI: controls, readout, clock, forecast-hour step, tinted canvas basemap) |
| `/lab/wind.js` | `wind-lab.js` (shared particle engine + `WindMath`; also used by `/lab/wind`) |
| `/api/wind-grid[?ahead=0/3/6/9/12]` | `windgrid.py` (GFS via NOMADS filter, cached 30 min per step) |

## Reused, not rebuilt

- `windgrid.py`: same NOMADS GRIB2 decoder. Added `ahead` (forecast-hour step, one extra NOMADS file per step, cached), plus `sample()`, `speed_kt()`, `from_deg()`, `compass()` for tests and spot checks.
- `wind-lab.js`: the same particle engine, refactored into `CBWind.layer(map, opts)` and `CBWindMath` (pure math, loadable in Node). The lab page bootstraps from the same file.
- Leaflet 1.x from `/vendor/leaflet`.

## Performance design

- The basemap is our own Census coastline (below), drawn into `<canvas>` tiles (an `L.GridLayer`), one tile per animation frame, so no tile can be the Largest Contentful Paint element and no frame commits several fresh tiles at once. The chrome, strip, legend and attribution are static HTML and paint first.
- Fixed grid rows (`top / strip / stage / controls`) and fixed-width clock: CLS 0.
- All scripts `defer`; Leaflet and the grid are preloaded; startup yields between map, tiles and particles.
- Phones (touch, short side < 600 px) draw at **30 fps**, DPR capped at 1.5, ≤ 1,100 particles. iPad and desktop draw every frame (**60 fps**), DPR ≤ 2, ≤ 2,200 particles. The engine backs off particles if frames run long, and stops when the tab is hidden, the map is off-screen or moving.
- `prefers-reduced-motion`: particles off by default; static colored arrows instead. The Flow/Pause button overrides and is remembered (`coastalBrief.windMotion`, shared with the lab).
- `?fps=30|60` and `?perf=1` (HUD) are test aids.

## Coastline basemap (replaces Esri on /wind, Nov 19 2026)

- **Source:** U.S. Census Bureau, *2025 Cartographic Boundary File (SHP), State and Equivalent Entities for United States, 1:500,000* — `cb_2025_us_state_500k`, https://www2.census.gov/geo/tiger/GENZ2025/shp/cb_2025_us_state_500k.zip (metadata dated 2026-05; zip sha256 `9cbfe171dad1555e11770c981d8f4db9e687a65c86f5bdae684eeb487e2e9b80`). Public domain; the use constraint asks that the Census Bureau be acknowledged as the source and that the data not be shown at scales larger than 1:500,000.
- **On-page attribution:** "Coastline: U.S. Census Bureau, 2025 cartographic boundary file, 1:500,000 (not endorsed by the Census Bureau)".
- **Build:** `python scripts/build_wind_coast.py cb_2025_us_state_500k.shp` (needs shapely + pyshp, offline only) unions the states, clips to 29–41°N, 85–68°W, simplifies, and writes delta-encoded 1e-4° rings with a bbox per polygon:
  - `wind-coast/lo.json` (tolerance 0.004°, zoom < 8; ~28 KB, ~12 KB gzipped)
  - `wind-coast/hi.json` (tolerance 0.0005°, zoom ≥ 8; ~78 KB, ~30 KB gzipped)
- **Served** only through the gated routes `/wind/coast.js`, `/wind/coast-lo.json`, `/wind/coast-hi.json` (404 without access; `private, max-age=86400`). The raw `/wind-coast/` folder is denied.
- **Look:** the map background is the water colour; tiles fill land and stroke the shoreline from CSS vars `--map-bg`, `--coast-land`, `--coast-line` (day `#EAF1F4` / `#F6F1E7`; night `#0C2740` / `#1B4263`). Every legend colour is ≥ 3:1 against both (day worst 3.11 water / 3.15 land; night 4.72 / 3.24).
- **maxZoom is 9.5** (≈1:630,000 at 35°N) to respect the Census 1:500,000 display limit.
- **Not drawn:** inland lakes and rivers, creeks, marsh, small inlets narrower than the 1:500k generalisation, place labels. Land outside the clip box is absent (never visible; it is wider than the pan limits).
- `/lab/wind` and `/dashboard` still use Esri tiles — separate decision (Esri's keyless endpoints are not licensed for commercial use).

## Day / night theme (Nov 19 2026, Ed t354u)

- **Same preference as the rest of the site:** `localStorage["coastalBrief.theme"]` = `"light"` or `"dark"`, written by the Morning Brief and dashboard toggles. Nothing stored = follow the phone's appearance (`prefers-color-scheme`). `?theme=light|dark` overrides for one load (testing).
- **Before first paint:** the inline script in `wind.html`'s `<head>` sets `data-theme` before any CSS loads; the toggle icon is CSS-driven, so there is no flash of the wrong theme or icon.
- **Live, no reload:** the sun/moon button (top bar, 44 px, `aria-label="Night mode"` + `aria-pressed`) writes the same key. `/wind` also follows a change made in another tab (`storage` event), the phone switching appearance when nothing is stored, and Safari's back/forward cache (`pageshow`). A switch repaints the coastline tiles in place (`CBCoast.layer().restyle`) and swaps the particle palette (`CBWind.layer().setDark`); view, data, forecast hour and animation are untouched.
- **Known gap (not /wind):** the public homepage (`/`, hybrid) has no toggle and does not read the stored key; it follows only the phone's appearance. The Morning Brief and dashboard read the key on load but don't listen for changes made in other open tabs.

## Known GFS limitations (harbors and sounds)

- **Grid ≈ 25 km** (0.25°). One cell can span an inlet, a barrier island and open ocean. Values between nodes are bilinearly interpolated, so coastline and sound detail is coarser than the smooth flow suggests.
- **Near-harbor readings run light.** In the 13 Nov checks, open water (Diamond Shoals buoy **41025**, Cape Lookout **CLKN7**) was close, while the Beaufort harbor station (**BFTN7**) read stronger than the 25 km cell. Expect the same in Pamlico/Albemarle/Core/Bogue sounds and around inlets.
- **Valid hour vs observation time.** The viewer shows the forecast hour nearest to now (GFS hourly files), so a comparison with a station reading can be up to 30 minutes apart, plus model-run latency (newest run is usually 4–6 hours old).
- **Future upgrade: HRRR 3 km** (free NOAA, hourly runs). Needs Lambert-conformal unprojection in `windgrid.py`. Recommended after Ed signs off on the GFS viewer.

The page carries a short version of this in its About (i) note.

## Tests

`tests/test_wind_viewer.py`: real GFS fixture decode, bounds and units, `ahead` URL selection and caching, knots and meteorological direction, bilinear interpolation against raw nodes, browser engine vs Python (Node), ET labels across EST/EDT, copy (MODEL FORECAST present; "observed"/"live" absent), controls and 44 px+ sizes, location prompt only after a tap, fps/reduced-motion/pausing hooks, route gating (public 404, cookie, flag), payload budget (no `styles.css`, no fonts, own assets < 50 KB). `tests/test_wind_theme.py`: shared key with app.js/brief.py, pre-paint script in `<head>` before CSS, live-sync hooks, toggle markup/aria/44 px/placement, in-place repaint, Esri-free. `tests/test_wind_coastline.py`: coastline data integrity (source, bounds, closed rings, bbox, no self-crossing on the Outer Banks, size budget), land/water at 17 known points in both LODs (Python and the browser module in Node), projection parity with Leaflet EPSG:3857, legend ≥ 3:1 on land and water in both themes, no Esri/third-party tiles on /wind, one-tile-per-frame drawing, maxZoom 9.5, gated coast routes.
