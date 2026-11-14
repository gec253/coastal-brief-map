# Falls Lake dashboard: sources, stations and limitations

Private preview only. `/lake`, `/lake.js` and `/api/freshwater` return 404 unless
`FRESHWATER_ENABLED=1` is set in the server environment. It is **not** set on Render.
Only regions with `"previewReady": true` in `data/regions.json` are assembled (`falls-lake`, `jordan-lake`, `neuse-river`). All three stay `enabled: false` / `draft: true` and are 404 to the public.

Code: `freshwater.py` (assembly), `lake.html` + `lake.js` (page), routes in `server.py`.

## Stations and parameters

| What the page shows | Source | Station / ID | Parameter | Units | Kind |
|---|---|---|---|---|---|
| Lake elevation (headline) | USGS IV | 02087182 Falls Lake above dam nr Falls | 62614 (lake/reservoir elevation, NGVD29) | ft | observed, provisional |
| Lake elevation, NAVD88 (secondary) | USGS IV | 02087182 | 62615 | ft | observed, provisional |
| Guide curve (target pool) | USACE Wilmington District | `epec.saw.usace.army.mil/dsslake.txt`, cross-checked against the district homepage table | static 251.5 ft-msl every day | ft (NGVD29 / ft-msl) | reference |
| Lake water temperature | USGS IV | 02087182 | 00010 | °C, shown °F (1 decimal) | observed, one sensor at the dam |
| Rain at the dam | USGS IV | 02087182 | 00045 (incremental), summed for 24 h / 7 d | in | observed, one point |
| Rain forecast (24 h / 72 h) | NWS API gridpoint `quantitativePrecipitation` | grid cell for 35.9411, -78.5833 | QPF | in (converted from mm) | forecast |
| Dam release | USGS IV | 02087183 Neuse R below Falls Dam | 00060 flow, 00065 stage | cfs, ft | observed, **regulated** |
| Flow vs normal for the date | USGS daily statistics service | same site | 00060 daily-mean percentiles | cfs | historical reference |
| Downstream river | USGS IV + NWPS | 02087500/CLYN7 Clayton, 02087570/SMFN7 Smithfield, 02089000/GLDN7 Goldsboro | 00060, 00065 | cfs, ft | observed, regulated by the dam |
| Inflows | USGS IV | 02085070 Eno R nr Durham, 02085500 Flat R at Bahama | 00060, 00065 | cfs, ft | observed, unregulated |
| Flood stages, river forecasts | NWS NWPS | NUDN7 (lake), NEUN7 (below dam), plus downstream LIDs | stages and forecast series | ft | official NWS thresholds / forecast |
| Alerts | NWS API `/alerts/active?point=` | dam coordinates | — | — | official |

Links only, no data copied: NCWRC boating access areas and fishing regulations
(link-only, `ncwildlife.gov`), USACE Falls Lake water management page, NC Parks Falls Lake State Recreation Area. (Duke Energy has no Falls Lake data; Duke lakes stay link-only when added.)

## Datums
- USGS 62614 is NGVD29. USACE "ft-msl" for Falls Lake is the same NGVD29 datum, so the guide curve
  comparison (`vsGuideFt`) is like for like. USGS 62615 (NAVD88) reads 0.90 ft lower; the page shows
  it as a secondary line and never mixes the two.
- NWPS NUDN7 flood stages (action 264, minor 265, moderate 266, major 267) are on the lake elevation scale.
- River "stage" is gauge height above a local gauge datum. The page calls it **stage**, never depth.

## Freshness rules
- USGS IV readings older than 3 h are flagged stale on the page with their timestamp.
- Every reading carries its own time; the page prints source, time and units next to each value.
- QPF is labeled forecast with its NWS update time; observed vs forecast is always visible.
- Missing values render as "Not available from USGS right now" (or the matching source), never as zero.

## Live verification, 13 Nov 2026 (ET)
| Check | Our API | Official page | Result |
|---|---|---|---|
| Lake elevation 08:30 | 245.07 ft | USGS IV JSON 02087182 08:30: 245.07 (P) | match |
| vs guide curve | -6.43 ft | 245.07 − 251.50 | match |
| NAVD88 | 244.17 ft | USGS 62615 | match, offset 0.90 |
| Water temp | 16.7 °C / 62.1 °F | USGS 00010 | match |
| Dam release | 60 cfs, stage 0.94 ft | USGS 02087183 | match |
| Release vs date | below lowest daily mean (min 62.2 cfs, 1983–2026) | USGS daily stats | match |
| Eno / Flat | 5.88 / 2.88 cfs, much below normal | USGS | match |
| Guide curve | 251.5 | USACE homepage table and dsslake.txt | match |

## Unresolved accuracy issues
1. **USACE homepage elevation disagrees with USGS.** The district homepage "0800 Elevation" for Falls
   reads 245.26 ft today; USGS shows 245.07 at 08:00 and never reached 245.26 in the last 3 days.
   The table may not update daily. We do not display the USACE elevation; only the guide curve comes
   from USACE. Ask USACE before ever using that number.
2. **USACE homepage column headers are misordered** (the Falls and Jordan values are swapped relative
   to the header). We match values by the known guide curve (Falls 251.5, Jordan 216.0), not by header.
3. **Percentile bands compare an instantaneous value with daily-mean statistics.** Near the extremes
   (e.g. 60 cfs vs a 62.2 cfs lowest daily mean) the label is softened to "Below lowest daily mean for
   this date", not "record low".
4. **Released flows are regulated.** Percentiles for 02087183 and downstream gauges describe dam
   operations as much as weather; the page marks them "Regulated by Falls Dam".
5. **Point measurements.** Water temperature and rain are single sensors at the dam.
6. USGS IV values are provisional (qualifier P) and can be revised.

## Other private freshwater previews
- `neuse-river` (Falls Dam to Goldsboro): USGS 02087183/NEUN7 below Falls Dam, 02087500/CLYN7 Clayton,
  02087570/SMFN7 Smithfield (stage only), 02089000/GLDN7 Goldsboro; NWS RAH grid 84,53; zone NCZ042.
  No active USGS water-temperature sensor on the main stem (checked 13 Nov 2026), so the river view
  will show water temp as unavailable rather than borrowing the lake sensor.
- `jordan-lake`: USGS 02098197 (62614/62615, rain 00045), NWPS NHPN7, USACE guide curve 216.0 ft;
  NWS RAH grid 60,50; zone NCZ040. No USGS water temperature at the dam. The old release gauge 02098198
  stopped reporting (flow 2010, stage 2016), so Haw River near Moncure 02098206/HRMN7 (about 1.6 mi below
  the dam, above the Deep River) is the nearest live flow and must be labeled "release plus local runoff".
- Both are `previewReady` and assembled behind the same flag. See `docs/NEUSE_JORDAN_SOURCES.md`.
