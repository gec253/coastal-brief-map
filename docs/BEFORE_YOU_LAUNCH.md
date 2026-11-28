# Before You Launch (Phase 3B, private preview)

Private only: `/preview/before-you-launch/<ramp-id>` for the 79 pilot ramps, behind the existing preview cookie.
Without the cookie every path (page, `.json`, `byl.css`, `byl.js`) is 404. Pages are noindex, no-store, and not in the sitemap.

- `byl_data.py`: the data layer. It reads only `publishable` stations from `stations/ramp_stations.json`. Each source has its own cache TTL, timeout, concurrency limit and failure backoff:
  - NWS forecast 30 min, NWS alerts 5 min, USGS 10 min, USACE 6 h, CO-OPS 6 h.
- Stale thresholds:
  - USGS is Stale after 3 h and not shown after 24 h.
  - USACE is Stale after 36 h and not shown after 7 days.
  - The NWS forecast is Stale after 12 h and not shown after 36 h.
- `byl_page.py`: Summer's approved layout (design/before-you-launch @ c2a0d01).
  - The server renders the shell (recorded access, regulations, computed sun and moon). Readings arrive asynchronously and replace skeletons.
  - A failed source becomes an Unavailable card. Nothing is filled in.

## Labels
Observed, Forecast, Predicted, Related station, Computed, Stale, Unavailable, Recorded status (access).

## Integrity
- Access is the recorded status and never a live check. Missing data is uncertainty, not a sign of safety.
- Ramps with an unresolved water class (10) still get the NWS forecast, alerts and sun/moon. Water readings are withheld there.
- Freshwater pages (reservoir, natural lake, river) drop marine alerts.
- `downstream_river_flow` is labelled "River flow below the dam (measured)". No `dam_release_reported` source is verified, so none is shown.
- No Duke, Dominion, TVA or Cube readings are shown.

## Mockup reconciliation (what the pages really get)

| Instrument | Union Point (New Bern) | Cedar Point |
|---|---|---|
| NWS point forecast | Yes | Yes |
| NWS alerts (point) | Yes (estuary, so marine alerts are allowed) | Yes |
| Water level (observed) | Unavailable: no reviewed same-water gauge (Pollocksville rejected; no active USGS or CO-OPS level gauge near New Bern) | Not in the inventory |
| Tide predictions | Omitted: wind-driven water | Yes: Swansboro 8656613, same water, 0.8 mi |
| Observed wind | Unavailable: no reviewed station | Unavailable: no reviewed station |
| Marine / sound forecast | Unavailable: marine zone not reviewed | Unavailable: marine zone not reviewed |
| Water temperature | Unavailable | Unavailable |
| Sun & moon | Computed | Computed |
| Regulations | NCDMF and NCWRC, with an explanation (jurisdiction unresolved) | NCDMF (coastal) |

## Phase 3C (Ed t571u)

- **Coastal instrument review:** `scripts/review_byl_coastal.py` writes `stations/byl_coastal_review.json`, which is not served. It records a decision for every candidate wind station, NWS marine zone, CO-OPS water temperature and water level station, and NOAA chart, across the 49 coastal and estuarine pilot ramps. The rules are in the file header.
- **Instruments:**
  - Tide curve from NOAA predictions, with hourly harmonic predictions. For subordinate stations, the curve is drawn between NOAA's high/low times and says so.
  - Lake elevation with a 14-day USGS chart and the USACE guide curve (Falls and Jordan).
  - Observed wind, always labelled Related station, with a compass.
  - NWS hourly wind bars.
  - 24-hour series for measured discharge, river gauges and water level.
  - Marine zone forecast. Ocean zones are labelled "beyond the inlet".
  - NOAA nautical chart gateway.
- **Datums:**
  - USGS 62614 is NGVD29 and 62615 is NAVD88.
  - USACE "ft MSL" equals the USGS NGVD29 readings: midnight Nov 20 matched exactly, Falls 244.78 and Jordan 211.93.
  - CO-OPS readings are feet above MLLW. Gauge height uses a local gauge datum.
  - None of these is water depth. 00060 is measured discharge.
- **Caching:**
  - One shared USGS request (and one history request) serves every pilot page.
  - The NWS grid, CO-OPS station and marine zone caches are keyed by URL, so pages share them.
  - Last known good is used per source within a window. Alerts never use it.
  - Observation times still drive Stale and hide.
- **USACE:** `dsslake.txt` was last modified Fri Oct 23, 2026 at 1:35 PM ET, and its latest row is 22OCT2026. `dailyrep.pdf` was last modified Nov 20. The project pages (`fall.htm`, `jord.htm`) date from 2021. The site posts no outage notice, and no CWMS catalog entries were found for Falls. The cause is not published, and no substitute data is used.

### Phase 3C: instruments, interaction and the station map

- Charts (tide, lake elevation, gauge sparklines) can be scrubbed by dragging, tapping, or with the Left/Right arrow keys. The value under the cursor is read out in an `aria-live` line, and every value comes from the plotted official series. Nothing is interpolated except subordinate tide curves, which are labelled on the card.
- The station map is drawn to scale. It shows the ramp and only the reviewed stations used on the page (gauge, tide, water level/temperature, wind), each with its distance. Inland water comes from TIGER/Line. Coastal sounds are not in that layer, so coastal maps show a plain frame with a note rather than an invented coastline. Every map says "Illustration, not for navigation", and the Nautical charts section links the official NOAA chart.
- Slot heights are reserved for each card type so live data loads without layout shift.
