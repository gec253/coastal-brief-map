# Region research: Wilmington / Wrightsville Beach

Phase 1 only — sources and coverage, no app-code changes.

Checked the evening of 13 Nov 2026, America/New_York (EST, UTC−5), around
**9:46–9:48 PM EST**. Official metadata: NDBC `station_table.txt`, NDBC
`activestations.xml` (created 9:40 PM EST), CO-OPS MDAPI, and NWS `/points`
and `/zones/forecast`. Latest observations: NDBC `realtime2/{id}.txt` and
`.spec` (45-day files, used for cadence and gaps), and CO-OPS Data API
`date=latest`. Distances use the same haversine as `conditions.py`
(`miles_bearing`, R = 3958.8 statute miles). Nothing here was invented or
interpolated.

## Anchor

**Johnnie Mercer's Pier, Wrightsville Beach**, 34.213 N, 77.786 W.

This is the official CO-OPS / NDBC position of station **8658163** (SHEF
**JMPN7**), published as 34°12'48" N, 77°47'11" W. NOAA's name for the
station is "Wrightsville Beach," not the pier's common name, but the
coordinates are the pier itself. It is an ocean pier, not a harbor dock, and
it already reports the inshore instruments the dashboard uses (wind, water
temperature, air, pressure, observed water level, and harmonic tide
predictions).

`JMPN7` is **not** Jennette's Pier in Nags Head. Jennette's Pier is `JPRN7`.
See `docs/REGION_NAGS_HEAD.md`.

## Coverage boundaries

Proposed region: **Wrightsville Beach only**, from Masonboro Inlet north
through Shell Island / Mason Inlet.

- **South end: Masonboro Inlet.** Carolina Beach, Kure Beach, Fort Fisher,
  and the south end of Masonboro Island belong to the later "Carolina Beach /
  Kure Beach" region on the roadmap. `MBIN7` (Masonboro Island south) sits
  9.6 mi southwest of the pier, toward that later region; do not treat it as
  a Wrightsville primary.
- **North end: Mason Inlet / the north end of Wrightsville (Shell Island).**
  Figure Eight Island is adjacent and is still in land zone NCZ108, but
  Topsail Beach and Surf City are a later region (land zone NCZ106, Coastal
  Pender). Do not extend this region to Surf City.
- **West:** Downtown Wilmington is 9.6 mi inland on the **Cape Fear River**
  (CO-OPS 8658120 / `WLON7`). River level, river water temperature, and
  inland air may be shown only with a "Cape Fear River at Wilmington" label.
  They are not ocean conditions.
- **Ocean:** The official marine zone, AMZ250, runs from Surf City to Cape
  Fear and is therefore wider than this region (it also covers Carolina
  Beach and the approach to Surf City). Use it as the marine forecast, but
  do not let that zone name become the coverage claim.
- **Does not overlap Crystal Coast.** Crystal Coast's marine zone is AMZ158
  (Cape Lookout to Surf City, office MHX). This region is office ILM,
  south of that split.

## The disabled `wilmington` stub in `data/regions.json`

The current entry is a stub only: `enabled: false`, name "Wilmington ·
Wrightsville Beach", area "Cape Fear coast", status "planned: 41037 and
41038 were stale on 12 Nov 2026". It has no station wiring, no anchor, and
no zones.

Tonight's check, against that note:

- **41037** (Wrightsville Beach Offshore, ILM3, 28.8 mi ESE) is still
  silent. Last report **6:08 PM EDT, 10 Oct 2026**. It is in
  `activestations.xml` but with `met=n`. The 45-day file still has only
  that October series (hourly met, **no WVHT**, almost no WTMP). Unusable.
- **41038** (Wrightsville Beach Nearshore, ILM2, 6.4 mi SE, companion to
  41110) is **reporting again**. Latest met **9:08 PM EST**, wind 5.0 m/s
  (about 10 kt) from 300°, WTMP 19.7 °C. It is hourly. The 45-day file
  shows a **5-day outage from 12:08 PM EST 6 Nov to 9:08 AM EST 11 Nov**,
  and a 13-hour gap around the 31 Oct / 1 Nov time change. The 12 Nov
  "stale" note is consistent with that outage; the buoy has since returned.
- The stub never mentioned **41110** (Masonboro Inlet, CDIP 150), which is
  the actual nearshore wave buoy, 6.3 mi from the pier, and was reporting
  tonight.

## Proposed instruments

Labels must name the real place. A backup that is not in the same water
should not fill a tile silently.

| Instrument | Primary | Backup | Distance | Latest obs (ET) | Cadence | Status |
|---|---|---|---|---|---|---|
| Wind (beach / pier) | 8658163 / JMPN7, Johnnie Mercer's Pier | MBNN7, Masonboro Island north end | 0.0 / 3.6 mi | 9:36 PM EST, 4.9 mph WNW (CO-OPS); NDBC 9:00 PM, 2.6 m/s | 6 min both | Active. Prefer the 6-min pier over the hourly buoy. |
| Wind, nearshore ocean (optional / third) | 41038, Wrightsville Beach Nearshore (ILM2) | — | 6.4 mi | 9:08 PM EST, 5.0 m/s (about 10 kt) / 300° | 60 min | Active tonight, but see risks: hourly cadence vs a 75-min stale window, and a 5-day hole 6–11 Nov. If used, set `staleAfterMin` about 130. |
| Seas | 41110, Masonboro Inlet (CDIP 150) | **No suitable source** | 6.3 mi | 9:30 PM EST `.spec` WVHT 0.4 m (1.3 ft); 9:00 PM `.txt` 0.5 m (1.6 ft), DPD 6 s, MWD 171° | 30 min | Active and reliable (two short gaps in 45 days). |
| Swell | 41110 `.spec` | **No suitable source** | 6.3 mi | 9:30 PM EST SwH 0.1 m (0.3 ft), SwP 10 s; wind sea 0.4 m | 30 min | Active. `.spec` is present. |
| Inshore water temp | 8658163, Johnnie Mercer's Pier (ocean) | — | 0.0 mi | 9:36 PM EST, 67.3 °F | 6 min | Active. |
| Offshore / nearshore water temp | 41110 | 41038 (same site; label "Wrightsville Beach Nearshore") | 6.3 / 6.4 mi | Both 19.7 °C (67.5 °F), 9:00 / 9:08 PM EST | 30 / 60 min | Active. Same water as the pier tonight (67.3 °F). |
| Air temp | 8658163 | MBNN7 (island), then KILM only with an "inland, Wilmington Airport" label | 0.0 / 3.6 mi | 9:36 PM EST, 54.7 °F at the pier | 6 min | Active. KILM at 8:55 PM EST was 10 °C and calm; it is not a beach reading. |
| Pressure | 8658163 | MBNN7, then 41038 | 0.0 / 3.6 / 6.4 mi | 9:36 PM EST, 1007.6 mb | 6 min | Active. |
| Harbor / inlet wind | 8658163 (same pier) | MBNN7, labeled "Masonboro Island, north end" | 0.0 / 3.6 mi | 9:36 PM EST | 6 min | There is no separate protected-harbor sensor at Masonboro Inlet. 8658120 has no wind. |
| Tide (observed + predictions) | 8658163, datum MLLW | — | 0.0 mi | 9:36 PM EST, 3.94 ft MLLW, preliminary | 6 min | Active NWLON with harmonics. Quality flag `1,0,0,0` on the latest water level (informational; still published as preliminary). |

Do **not** use as local Wrightsville seas, swell, or ocean water temperature:

- **41108** Wilmington Harbor (CDIP 200), 36.6 mi SSW, near the Cape Fear
  entrance. Reporting (9:26 PM EST, WVHT 0.7 m, DPD 4 s, MWD 272°, WTMP
  19.3 °C; `.spec` present). Tonight it was already a different sea state
  and a different direction than 41110. The 45-day file only begins
  **5 Nov 2026**. Fine as a later Cape Fear / Carolina Beach-area source;
  not a silent backup here.
- **41013** Frying Pan Shoals, 53.7 mi south. Reporting (9:20 PM EST, WVHT
  0.9 m, wind 8.0 m/s, WTMP **22.8 °C / 73.0 °F**). That water is several
  degrees warmer than Masonboro. Different shelf water, south of Cape Fear.
- **41037**, still stale since 10 Oct, and it never reported WVHT.
- **41024** Sunset Nearshore, 47.3 mi SW: last report 4:08 PM EST tonight
  (already hours stale), plus a 21-day hole in late October–November. Out
  of region.

## Station details

Locations are official NDBC or CO-OPS positions.

| ID | Official name / location | Water body | Feeds | Reporting? | Latest (ET) | Cadence | 45-day gaps |
|---|---|---|---|---|---|---|---|
| 8658163 / JMPN7 | Wrightsville Beach, NC. CO-OPS NWLON at Johnnie Mercer's Pier. 34.2133 N, 77.7867 W | Ocean pier | Wind, inshore WTMP, air, pressure, observed WL, tide predictions | Yes | 9:36 PM EST (CO-OPS). NDBC met file 9:00 PM EST | 6 min | Four short gaps; longest 4.5 h on 14 Oct. Air temp is not on every 6-min row, but it was present on the latest reports. No WVHT; `.spec` is 404. |
| 41110 | Masonboro Inlet, ILM2, NC (CDIP 150). CORMP waverider. 34.144 N, 77.715 W | Nearshore ocean, off Masonboro Inlet | Seas (WVHT), swell (`.spec`), nearshore WTMP and air | Yes. In `activestations` (`met=y`) | `.spec` 9:30 PM EST; `.txt` 9:00 PM EST | 30 min | Two gaps, both on 21 Oct (90 and 150 min). Every `.txt` and `.spec` row has WVHT; every `.spec` row has SwH. No wind sensors. NDBC points met users to 41038. |
| 41038 | Wrightsville Beach Nearshore, NC (ILM2). CORMP moored buoy. 34.141 N, 77.715 W | Nearshore ocean, same site as 41110 | Wind, pressure, air, WTMP | Yes tonight (`met=y`, `waterquality=y`) | 9:08 PM EST, WSPD 5.0 m/s, WTMP 19.7 °C | 60 min | 5-day outage 6–11 Nov; 13-hour gap 31 Oct–1 Nov. **No WVHT.** `.spec` is 404. NDBC points wave users to 41110. |
| MBNN7 | Masonboro Island, NC (MSNB_N). CORMP C-MAN. 34.171 N, 77.824 W | Barrier island, north end, just south of Masonboro Inlet | Wind, pressure, air, dew point | Yes | 9:00 PM EST, 2.1 m/s / 290° | 6 min | One 12.3 h gap 31 Oct 11:30 PM EDT–1 Nov 10:48 AM EST; otherwise a few 36–66 min holes. **No WTMP, no waves.** |
| MBIN7 | Masonboro Island, NC (MSNB_S). CORMP C-MAN. 34.091 N, 77.868 W | Barrier island, south end, toward Carolina Beach | Wind, pressure, air | Yes | 8:54 PM EST, 3.1 m/s / 320° | 6 min | Same gap pattern as MBNN7. Use later for Carolina Beach, or only as a labeled non-primary. |
| 8658120 / WLON7 | Wilmington, NC. CO-OPS NWLON. 34.2267 N, 77.9533 W | Cape Fear River, downtown | Observed WL, tide predictions, river WTMP (66.9 °F at 9:36 PM), air, pressure | Yes | 9:36 PM EST, WL 3.42 ft MLLW | 6 min | Same short October gaps as JMPN7. **No wind.** Do not present as ocean tide or ocean temperature. |
| 41037 | Wrightsville Beach Offshore, NC (ILM3). CORMP. 33.988 N, 77.362 W | Offshore ocean, 28.8 mi ESE | Met only, when alive | **No.** Last 6:08 PM EDT 10 Oct 2026 | — | Was 60 min | Unusable. No WVHT in the file. |
| 41108 | Wilmington Harbor, NC (CDIP 200). Scripps waverider. 33.719 N, 78.016 W | Nearshore, Cape Fear entrance | WVHT and `.spec`, WTMP | Yes | 9:26 PM EST, 0.7 m, DPD 4 s, MWD 272°, WTMP 19.3 °C | 30 min | File starts 5 Nov; one 150-min gap that day. Too far, different segment. |
| 41013 | Frying Pan Shoals, NC. NDBC 3 m buoy. 33.436 N, 77.764 W | Offshore, south of Cape Fear | Wind, seas, `.spec`, WTMP | Yes | 9:20 PM EST, WVHT 0.9 m, WSPD 8.0 m/s, WTMP 22.8 °C | 10 min met; waves ~20–30 min | A few gaps of 40–190 min in early Nov; one 11-hour `.spec` hole on 2 Nov. Too far, warmer water. |

NERRS Research Creek (`NOXN7` / `NOQN7`) is in the Masonboro estuary and has
no NDBC realtime file (HTTP 404). Not a beach instrument.

## NWS office, forecast point, and zones

Office: **NWS Wilmington (ILM)**.

The pier coordinate itself resolves to marine zone AMZ250, because the pier
stands in the ocean. The land forecast point must be slightly inland.

- **Recommended land forecast point:** Wrightsville Beach loop,
  34.208 N, 77.796 W. NWS `/points` returns **ILM grid 95, 75**, forecast
  zone **NCZ108 Coastal New Hanover**, office ILM. The pier coordinate
  falls on the same grid, but its forecast zone is AMZ250, so do not use
  the pier coordinate as the land-forecast point.
- **Marine tile:** **AMZ250**, official name "Coastal waters from Surf City
  to Cape Fear NC out 20 nm" (CWA ILM, metadata confirmed). This is the
  correct ocean zone. It is wider than the region (see boundaries).
- **Alert zones (proposed):** `AMZ250`, `NCZ108`. Add `NCZ107` Inland New
  Hanover only if downtown Wilmington is in the region. Do **not** add
  NCZ106 (Coastal Pender / Topsail) or NCZ110 (Coastal Brunswick /
  Southport). Do **not** add Crystal Coast zones (AMZ158, NCZ195/196).

AMZ252 is "Coastal waters from Cape Fear NC to Little River Inlet SC out
20 NM" and is the next region south, not this one. AMZ158 (MHX, Lookout to
Surf City) is Crystal Coast.

## Risks

1. **No honest seas / swell backup.** 41108 and 41013 are in different
   water and already disagreed with 41110 tonight. If 41110 is down, seas
   and swell should show as unavailable. Same rule as Crystal Coast / 41159.
2. **41038 is a shaky wind backup.** Hourly reports will trip a 75-minute
   wind stale window unless `staleAfterMin` is raised, and it had a 5-day
   outage last week. Tonight it was also windier than the pier (about 10 kt
   vs about 5 kt), so the two are not interchangeable without a label.
3. **41037 is still dead** and should not be wired.
4. **AMZ250 and NCZ108 are wider than the region.** Alerts and the marine
   forecast will also apply to Carolina Beach / Kure Beach (and, for AMZ250,
   up toward Surf City). That is a zone fact, not a reason to widen the
   region.
5. **CO-OPS water-level flag `1,0,0,0`** on the latest Wrightsville
   observation, same informational note as in the Hatteras audit. Still
   preliminary and on cadence.
6. **Name collision:** `JMPN7` is Wrightsville, not Jennette's Pier.

## Open questions for Scout and Ed

1. Confirm the south and north edges (Masonboro Inlet to Mason Inlet) versus
   holding Figure Eight Island in or out.
2. Is downtown Wilmington / the Cape Fear River in this region at all, as a
   clearly labeled river instrument, or is this a beach-only region?
3. Primary wind: the pier (local, 6-min, recommended here), Masonboro Island
   north (3.6 mi, 6-min, no water temp), or the nearshore buoy (hourly,
   more exposed, recent outage)?
4. Is a separate harbor-wind tile useful when the only local wind sensors
   are the ocean pier and the island, or should one wind tile suffice?
5. Accept AMZ250 as the marine tile with a short caption that the official
   zone also covers the beaches toward Cape Fear and Surf City?
