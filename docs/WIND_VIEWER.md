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

- Esri basemap tiles are drawn into `<canvas>` (an `L.GridLayer`), tinted to the palette, so a third-party tile can never be the Largest Contentful Paint element. The chrome, strip, legend and attribution are static HTML and paint first.
- Fixed grid rows (`top / strip / stage / controls`) and fixed-width clock: CLS 0.
- All scripts `defer`; Leaflet and the grid are preloaded; startup yields between map, tiles and particles.
- Phones (touch, short side < 600 px) draw at **30 fps**, DPR capped at 1.5, ≤ 1,100 particles. iPad and desktop draw every frame (**60 fps**), DPR ≤ 2, ≤ 2,200 particles. The engine backs off particles if frames run long, and stops when the tab is hidden, the map is off-screen or moving.
- `prefers-reduced-motion`: particles off by default; static colored arrows instead. The Flow/Pause button overrides and is remembered (`coastalBrief.windMotion`, shared with the lab).
- `?fps=30|60` and `?perf=1` (HUD) are test aids.

## Known GFS limitations (harbors and sounds)

- **Grid ≈ 25 km** (0.25°). One cell can span an inlet, a barrier island and open ocean. Values between nodes are bilinearly interpolated, so coastline and sound detail is coarser than the smooth flow suggests.
- **Near-harbor readings run light.** In the 13 Nov checks, open water (Diamond Shoals buoy **41025**, Cape Lookout **CLKN7**) was close, while the Beaufort harbor station (**BFTN7**) read stronger than the 25 km cell. Expect the same in Pamlico/Albemarle/Core/Bogue sounds and around inlets.
- **Valid hour vs observation time.** The viewer shows the forecast hour nearest to now (GFS hourly files), so a comparison with a station reading can be up to 30 minutes apart, plus model-run latency (newest run is usually 4–6 hours old).
- **Future upgrade: HRRR 3 km** (free NOAA, hourly runs). Needs Lambert-conformal unprojection in `windgrid.py`. Recommended after Ed signs off on the GFS viewer.

The page carries a short version of this in its About (i) note.

## Tests

`tests/test_wind_viewer.py`: real GFS fixture decode, bounds and units, `ahead` URL selection and caching, knots and meteorological direction, bilinear interpolation against raw nodes, browser engine vs Python (Node), ET labels across EST/EDT, copy (MODEL FORECAST present; "observed"/"live" absent), controls and 44 px+ sizes, location prompt only after a tap, fps/reduced-motion/pausing hooks, route gating (public 404, cookie, flag), payload budget (no `styles.css`, no fonts, own assets < 45 KB).
