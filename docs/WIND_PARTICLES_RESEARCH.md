# Animated wind particles: research and prototype

Status: **prototype built, OFF in production.** `/lab/wind`, `/lab/wind.js`, and
`/api/wind-grid` return 404 unless `WIND_PARTICLES_ENABLED=1`. Nothing links to them.
The live site's wind layer is unchanged (NWS NDFD colour tiles plus the existing
flow canvas on the wind instrument).

Ground rules: animate only real gridded vectors from NOAA models, label them as a model
forecast with run and valid times, never animate radar or colour tiles, never imply
observation, and respect reduced motion.

## Sources checked live (13 Nov 2026, about 7:00 AM ET)

| Source | What | Result |
| --- | --- | --- |
| NOMADS GRIB filter `filter_gfs_0p25_1hr.pl` | GFS 0.25° (~25 km), 10 m UGRD/VGRD, hourly to 120 h, 4 runs a day | **Works.** A 7°×5° box around NC is 609 points, **1.3 KB**, simple packing (GRIB2 template 5.0) on a lat/lon grid (3.0). Decoded with the standard library, no eccodes. |
| NOMADS GRIB filter `filter_hrrr_2d.pl` | HRRR 3 km, hourly runs, 18–48 h | **Works.** Same box is 57,021 points, **~120 KB**, simple packing, but on a Lambert conformal grid (template 3.30), so it needs a small projection step. Best quality near the coast and sounds. |
| NOMADS OpenDAP (`/dods/`) | — | **Retired.** It now returns a "format has been retired" page (NWS SCN 25-81). |
| NDFD (digital.weather.gov) | Official NWS forecast wind, already used as colour tiles | Gridded GRIB2 exists, but in a CONUS file far larger than needed and with complex packing; the WMS used today is images only, so it can't be animated honestly. |
| RTOFS (ocean currents) | 1/12° global ocean model | Available on NOMADS, but files are large NetCDF; worth a later look for Gulf Stream currents, not wind. |

Licence: NOAA model output is US Government work, public domain. Attribution used:
"NOAA NCEP GFS (model forecast)". No NOAA endorsement is implied.

Sanity check against observations: the GFS run of 13 Nov 06Z, valid 7:00 AM ET, gave
**19.7 kt from 301°** at 34.5° N, 76.5° W; the Cape Lookout C-MAN station (CLKN7) was
reporting WNW 19–20 kt, gusting 25, at the same time. A model value must still be
shown as a forecast.

## Processing options

1. **GRIB to JSON on the server (prototype uses this).** `windgrid.py`, standard library:
   pick the newest available GFS cycle (falls back up to 18 h), forecast hour nearest
   now, decode, return U/V arrays plus run/valid times. Cached 30 min. ~15 KB JSON.
2. **PNG-encoded U/V** (the earth.nullschool approach): pack U and V into the red and
   green channels of a small PNG. Smaller for HRRR-sized grids and fast to sample on the
   GPU. Needs Pillow on the server (already planned for photos). Worth it only for HRRR.
3. **Precomputed files on a schedule:** not possible without a worker or storage; the
   on-demand cache is enough at this size.

## Drawing options

| Option | Licence | Notes |
| --- | --- | --- |
| Small custom canvas (prototype) | ours | ~130 lines, no dependency. Bilinear interpolation, fading trails, colour by speed, pauses while panning or when the tab is hidden. |
| leaflet-velocity | CSIRO open source licence (a BSD/MIT variation) | Mature, expects the grib2json format; adds ~30 KB plus its own conventions. Fine if we ever want its controls. |
| WebGL (e.g. mapbox webgl-wind pattern) | MIT/ISC variants | Smoothest for 100k+ particles, but more code and GPU memory, and Leaflet integration is manual. Not needed at this scale. |

## Measured prototype performance (Chromium, local)

- Phone size (390×844, DPR 2, CPU throttled 4×): steady **~60 fps**, JS heap ~10 MB, ~700 particles.
- Desktop (1280×900): ~60 fps, ~1,400 particles.
- Reduced motion: no animation; a static grid of arrows coloured by speed.
- Payload: one ~15 KB JSON request, cached 10 min in the browser and 30 min on the server.

Not yet measured: real iPhone battery and thermal behaviour, Safari (WebKit could not be
run on this box because system libraries are missing).

## Refinement, 13 Nov 2026

What changed in `/lab/wind` (still 404 unless `WIND_PARTICLES_ENABLED=1`, never linked):
- Theme-aware: Esri Light Gray or Dark Gray canvas basemap, and a speed ramp tuned for each
  (deep inks on light, luminous tints on dark). Stroke width and opacity rise with speed.
  A 0–35+ kt colour scale is shown beside the controls.
- **Motion toggle** (`Motion: on / off (arrows)`), stored in `localStorage`; defaults to the OS
  `prefers-reduced-motion` setting. Off draws static arrows and stops the loop entirely.
- Tap readout: "Model forecast 19 kt from WNW (295°) · GFS 10 m, interpolated", so the picture can
  be checked against numbers.
- Loop pauses when the tab is hidden, when the map is scrolled off screen (IntersectionObserver), and
  while the map pans or zooms. Measured: 0 frames drawn in each paused state.
- Speed: lat/lon per pixel column/row precomputed once per view (Web Mercator separates them), typed
  arrays for particles, strokes batched into 12 speed buckets (12 `stroke()` calls a frame instead of
  ~1,000), canvas DPR capped at 1.5 on touch devices, particle count backs off if frames run long.
- Phones draw at 30 fps (particles step twice as far, shorter trails) to halve raster and battery cost;
  `?fps=60` forces 60 for comparison, `?perf=1` shows an FPS/draw/heap HUD.

### Measurements (headless Chromium on this box, 10 s windows, software raster)

| Viewport | CPU throttle | FPS | JS draw p50 / p95 | Particles | JS heap | Main thread busy |
|---|---|---|---|---|---|---|
| 390×844 @3x, light | 1× | 29.9 (capped) | 0.1 / 0.2 ms | 801 | 2.7 MB | 13% |
| 390×844 @3x, dark | 4× | 30.1 | 0.4 / 0.9 ms | 801 | 3.5 MB | 48% |
| 390×844 @3x, light | 6× | 30.0 | 0.5 / 1.2 ms | 801 | 3.9 MB | 73% |
| 1280×900, dark | 1× | 60.0 | 0.3 / 0.4 ms | 1,724 | 2.7 MB | 31% |

Same phone runs at uncapped 60 fps before the 30 fps cap: 21% busy at 1×, 80% at 4×, and 49 fps at 6×,
so the cap cut main-thread load by about 40%. Almost all of the busy time is raster (the box has no GPU);
JavaScript itself is under 2% of wall time. Real iPhones raster canvas on the GPU, so these are a pessimistic
proxy; battery and thermals still need a check on Ed's phone.

### Accuracy check (model vs observation, 13 Nov 2026)
- Client interpolation equals the raw GRIB values exactly at grid nodes (checked at 3 nodes).
- NDBC 41025 Diamond Shoals observed 300° 11 m/s (21 kt), 8:40 AM ET; GFS valid 9 AM ET at that node:
  295°, 18.9 kt. Close.
- NOS BFTN7 Beaufort observed 330° 4.1 m/s (8 kt), 8:30 AM ET; GFS node: 304°, 10.2 kt. The 25 km cell
  mixes open water and land, so the model runs stronger than the sheltered harbor station. This is the
  expected limitation of GFS near the sounds, and why HRRR is still the recommendation.

## Reliability and cost

- Cost: $0. NOMADS is free; requests are tiny and cached (at most ~50 a day).
- NOMADS has usage limits (rapid repeated requests can get an IP blocked for a while)
  and occasional outages. The cache and the 18 h fallback cover short gaps; on failure
  the API returns `ok:false` and the page says model wind is unavailable.
- GFS runs appear about 3.5–5 h after cycle time, so "valid" can be up to ~6 h after
  "run". Both are shown in Eastern time on the page.

## Recommendation

1. Keep the prototype off until Ed has tried `/lab/wind` on his phone.
2. If it's wanted, move to **HRRR** (3 km) for the coast and sounds: add Lambert
   conformal unprojection in `windgrid.py` (or PNG encoding), keep GFS as the fallback
   beyond HRRR's range.
3. Then offer it as an opt-in "Flow" toggle on the wind layer, not the default: label
   "Model forecast (HRRR), run …, valid …", a pause button, reduced-motion arrows, and
   no animation when the map is off screen.

## Trying it locally

```bash
WIND_PARTICLES_ENABLED=1 python server.py --port 8801
# open http://127.0.0.1:8801/lab/wind
```
