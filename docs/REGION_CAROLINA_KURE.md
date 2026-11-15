# Region research: Carolina Beach / Kure Beach

Phase 1 only — sources and coverage, no app-code changes.

Checked the morning of Sunday 15 Nov 2026, America/New_York (EST, UTC−5),
between about 8:50 and 8:57 AM ET, with read-only GETs to official public
APIs (NDBC `activestations.xml` and `station_table.txt`, NDBC
`latest_obs` / `realtime2` / `.spec`, CO-OPS MDAPI and Data API,
NWS `/points`, `/zones/forecast`, and products, plus USGS only where a
station came up in a catalog). Distances use a haversine with R = 3958.8 mi
from the official CO-OPS coordinate of 8658559. Nothing here is invented:
every reading cites the station and the time of the check. Where something
was not verified today, the doc says so.

Existing Wilmington research already reserved MBIN7 (Masonboro Island
south) for this later region and set the Wilmington south boundary at
Masonboro Inlet. This audit re-checked those stations today; it does not
reuse 13 Nov values as current.


## Tide decision (15 Nov 2026, 9:03 AM ET)

Settled before any preview code was written. Live read-only checks against
CO-OPS MDAPI (`stations/8658559.json`, `tidepredoffsets`, `harcon`) and the
Data API (`datagetter` product=predictions, datum=MLLW, interval=hilo,
time_zone=lst_ldt; and product=water_level date=latest).

**Decision:** CO-OPS still publishes official high/low predictions for
8658559 today. The dashboard must show those predictions, labeled

> Tide predictions, NOAA CO-OPS 8658559 Wilmington Beach (subordinate
> station; predictions only)

Do not substitute raw predictions from the reference station as the
displayed series. Observed water level is a separately labeled Wrightsville
Beach 8658163 reading and is never presented as local.

**Evidence:**

- MDAPI 8658559: name WILMINGTON BEACH, 34.0317 N, 77.8933 W, tidal=true.
  Products include Tide Predictions, Benchmarks, and Datums — not Water
  Levels or Meteorological. Details: established 1977-01-28, removed
  1979-12-20. `harcon.json` returned an empty HarmonicConstituents list.
- The actual offsets record (`tidepredoffsets.json`) confirms the Cape
  Hatteras claim: `refStationId` is **8654400**, type **S**. Height offsets
  are 1.4 (high) and 1.25 (low); time offsets are +18 min (high) and
  +10 min (low). `heightAdjustedType` is **R** (ratios, not additive feet).
  MDAPI 8654400 is "Cape Hatteras Fishing Pier," 35.2233 N, 75.635 W
  (SHEF CFPN7).
- Arithmetic check against today's lst_ldt hilo: 8654400 11:03 3.171 H
  × 1.4 = 4.439, +18 min = 11:21, matches 8658559 11:21 4.44 H. Low
  04:24 0.764 × 1.25 = 0.955, +10 min = 04:34, matches 04:34 0.955 L.
- Official CO-OPS datagetter still published 8658559 predictions today
  (lst_ldt, MLLW, interval=hilo): 04:34 0.955 L, 11:21 4.44 H, 17:53
  1.005 L, 23:49 3.281 H.
- Same day, 8658163 predictions: 04:19 1.133 L, 11:14 4.143 H, 17:28
  1.122 L, 23:33 3.222 H. Observed water level at 08:54 ET: 3.963 ft
  MLLW, preliminary (`q=p`). 8658559 `water_level` date=latest returned
  "No data was found."
- Earlier audit GMT times (03:56 etc.) are the same events; the product
  uses lst_ldt / ET.

Open question 2 in this doc is therefore settled: show 8658559 official
predictions (with the required subordinate label and the Hatteras
reference note) plus a clearly labeled Wrightsville 8658163 observed
water level. No 6-minute curve at 8658559; do not draw Wrightsville's
curve under Wilmington Beach highs and lows.

This section was recorded while pausing a WIP preview implementation
on `data/regions-ckd`. The preview itself was not finished or tested.

## Anchor

**CO-OPS 8658559 Wilmington Beach**, 34.0317 N, 77.8933 W (MDAPI, checked
8:54 AM ET). This is a tide-prediction station, not a live water-level
gauge.

NWS `/points` for that official coordinate (ILM 92,67) returned
relativeLocation **Carolina Beach, NC, 0 meters** (checked 8:52 AM ET).
The official CO-OPS name remains "Wilmington Beach"; NWS treats the same
point as Carolina Beach.

There is **no CO-OPS observed water-level or meteorological station, and
no NDBC station, named Carolina Beach or Kure Beach** in today's catalogs.

Kure Beach does not have its own official tide station. The nearest official
coordinate with a published name is CO-OPS 8658715 Federal Point, Cape Fear
River (33.9617 N, 77.94 W), 5.5 mi SSW of 8658559. NWS `/points` for
Federal Point returned relativeLocation Kure Beach, NC, 2,575 m at bearing
215° (about 1.6 mi). Federal Point is a **Cape Fear River** prediction
station, not an oceanfront gauge, and it has no observed water level.

Until an official Kure oceanfront benchmark is identified, treat 8658559 as
the region anchor and label Kure distances as measured from that point
(or from Federal Point where the river station is the subject).

## Coverage boundaries

- **North:** Masonboro Inlet is the clean split with the Wilmington /
  Wrightsville region. MBIN7 sits on the south side of that inlet (4.3 mi
  NNE of 8658559) and was reserved for this region. Do not steal
  Wrightsville's primary instruments (8658163 / JMPN7, 41110) as if they
  were local to Carolina Beach; they may be used only when clearly labeled
  as Wrightsville / Masonboro Inlet sources.
- **South:** Cape Fear / Federal Point / Fort Fisher. Official marine zone
  AMZ250 ends at Cape Fear; AMZ252 begins there ("Coastal waters from Cape
  Fear NC to Little River Inlet SC out 20 NM", ILM). This region should
  stay on AMZ250 and should not absorb Southport / Oak Island (NCZ110).
- **Ocean:** The official marine zone is **AMZ250** (ILM), "Coastal waters
  from Surf City to Cape Fear NC out 20 nm" (NWS zone metadata, 8:52 AM
  ET). That zone is wider than these two beaches — it also covers
  Wrightsville, Masonboro, and the run up to Surf City.
- **Land weather:** NWS `/points` at 8658559 and at Federal Point both
  resolved to office **ILM**, public zone **NCZ108 Coastal New Hanover**,
  county NCC129, radar KLTX (8:52 AM ET).
- **Does not overlap Wilmington** if the north boundary stays at Masonboro
  Inlet and Wrightsville instruments stay labeled.

## Proposed instruments

| Need | Primary | Backup | Distance from 8658559 | Latest today (ET) | Cadence | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| Wind / gusts / pressure / air temp | MBIN7 Masonboro Island south (CORMP) | 41038 Wrightsville Beach Nearshore (CORMP), labeled; then 8658163 Wrightsville Beach, labeled | 4.3 / 12.7 / 14.0 mi | MBIN7 8:00 AM EST: NNW 7 kt, gust 10 kt, 30.26 in rising, air 42.1 °F (NDBC `latest_obs`, 8:52 AM ET check). 41038 8:08 AM EST: NNW 11.7 kt, gust 15.5 kt, 30.25 in, air 47.3 °F. 8658163 8:42 AM ET: NNW 8.16 kt, gust 10.69 kt (CO-OPS, GMT 13:42) | MBIN7 cadence **not verified** (NDBC `realtime2` 404 today; only a single `latest_obs` line). 41038 met: 60 min in `realtime2` (13:08, 12:08, 11:08 UTC, checked ~8:57 AM ET). 8658163: 6 min (CO-OPS interval=6 today) | MBIN7 is the closest official wind. It has no water temp in today's `latest_obs`. |
| Seas (significant wave height, WVHT / combined seas) | 41110 Masonboro Inlet, ILM2 (CDIP 150, CORMP), **labeled "Masonboro Inlet"** | **No suitable automatic backup.** 41108 and 41013 are a different stretch of coast. 41037 is not reporting. | 12.8 mi NE | `latest_obs` 8:30 AM EST: Seas 2.0 ft, peak period 10 s; `realtime2` newest row 8:30 AM ET (13:30 UTC): WVHT 0.6 m (~2.0 ft), DPD 10 s | 30 min (`realtime2` 13:30, 13:00, 12:30 UTC) | No wind on 41110 (WDIR/WSPD all MM). Do not call WVHT "swell." |
| Swell (SwH / SwP / SwD from `.spec`, not WVHT) | 41110 `.spec` | **No suitable automatic backup** | 12.8 mi | `.spec` 8:30 AM ET: WVHT 0.6 m, **SwH 0.2 m (0.7 ft), SwP 10.0 s, SwD E**; wind sea WWH 0.6 m, WWP 9.5 s, WWD E | 30 min | Today swell was much smaller than combined seas. Always label swell separately from seas. 41108 `.spec` at 8:26 AM ET had SwH 0.1 m vs seas 0.7 m — similar swell height, but it is 22.7 mi SSW at the Cape Fear entrance, not a silent substitute. |
| Ocean water temp | 41110 WTMP; 41038 WTMP is at almost the same place | 8658163 water temperature, labeled Wrightsville Beach (pier / inlet, not this oceanfront) | 12.8 / 12.7 / 14.0 mi | 41110 8:30 AM EST: 66.0 °F. 41038 8:08 AM EST: 66.2 °F. 8658163 8:42 AM ET: 65.3 °F | 41110 30 min; 41038 60 min; 8658163 6 min (WL/met products) | No local ocean temp at Carolina or Kure. |
| Observed water level | **None local.** Closest ocean NWLON is 8658163 Wrightsville Beach, **labeled**, datum MLLW | 8658120 Wilmington (Cape Fear River harbor, not ocean) | 14.0 / 13.9 mi | 8658163 8:42 AM ET: 3.848 ft MLLW, preliminary (`q=p`). 8658120 8:42 AM ET: 1.736 ft MLLW, preliminary | 6 min (today's 6-minute series at 8658163: 13:18–13:48 UTC in 6.0 min steps, 139 points from 00:00 UTC) | 8658559, 8658715, 8658579, and 8659084 all returned "No data was found" for `product=water_level&date=latest` at 8:54 AM ET. |
| Tide predictions | 8658559 Wilmington Beach, **predictions only**, subordinate type S | 8658163 Wrightsville Beach predictions (and its observed WL), labeled | 0.0 / 14.0 mi | 8658559 today's official hilo, GMT, datum MLLW (CO-OPS `date=today`, 8:52 AM ET): 03:56 3.292 H, 09:34 0.955 L, 16:21 4.44 H, 22:53 1.005 L | Harmonic/subordinate daily predictions (not an observation cadence) | **Reference station is 8654400 Cape Hatteras Fishing Pier** (MDAPI `tidepredoffsets`, 8:54 AM ET): type S, `heightOffsetHighTide` 1.4, `heightOffsetLowTide` 1.25, `timeOffsetHighTide` 18, `timeOffsetLowTide` 10, `heightAdjustedType` R. The physical 8658559 station was **established 1977-01-28 and removed 1979-12-20** (MDAPI details). Predictions still exist; they are not a live gauge. Label this clearly. |
| Air / pressure at an NWLON | 8658163 Wrightsville Beach, labeled | 8658120 Wilmington has air and pressure but **no wind product** today | 14.0 / 13.9 mi | 8658163 8:42 AM ET: air 44.4 °F, pressure 1025.6 mb. 8658120 8:42 AM ET: air 46.6 °F, pressure 1025.6 mb; wind product error "No data was found" | 6 min | JMPN7 `latest_obs` 8:18 AM EST had wind NW 7.0 kt, gust 9.9 kt, pressure 30.28, water temp 65.3 °F (same CO-OPS station, slightly older NDBC digest). |

Do **not** use as local Carolina/Kure ocean seas, swell, or ocean temperature:

- **41108** Wilmington Harbor (CDIP 200, SCRIPPS), 33.719 N, 78.016 W, 22.7 mi SSW — Cape Fear entrance / harbor approach, not the Carolina Beach oceanfront. Reporting today (seas 2.3 ft / WVHT 0.7 m at 8:26 AM ET; swell 0.3 ft / 0.1 m). Labeled use only, if at all.
- **41013** Frying Pan Shoals (NDBC), 33.436 N, 77.764 W, 41.8 mi S — too far, different water. Reporting (8:30 AM EST `latest_obs`: wind N 11.7 kt, gust 15.5 kt, seas/swell from the wave summary: swell 2.0 ft / 10 s ENE, wind wave 2.6 ft / 4.8 s N; water 68.7 °F). `realtime2` met is 10 min; `.spec` ~30 min.
- **41037** Wrightsville Beach Offshore, ILM3 (CORMP), 33.988 N, 77.362 W, 30.6 mi E — **not reporting today.** See Station details.

## Station details

| Station | Identity | Location vs anchor | What it measures | Reporting today? | Latest today | Cadence | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| MBIN7 | CORMP, Masonboro Island south. NDBC 34.091 N, 77.868 W. In `activestations` (`met=y`) | 4.3 mi NNE, south of Masonboro Inlet | Wind, gust, pressure, air temp, dew point. No waves. No water temp in today's `latest_obs` | Yes, `latest_obs` 200 | 8:00 AM EST 15 Nov, NNW 7 kt, gust 10, 30.26 in rising, air 42.1 °F | **Unknown from a time series** — `realtime2` and `.spec` 404 at 8:52 AM ET | Closest official wind to Carolina Beach. Reserved in the Wilmington research for this region. |
| MBNN7 | CORMP, Masonboro Island north. 34.171 N, 77.824 W | 10.4 mi NNE, Wilmington side of the inlet | Same met suite as MBIN7 | Yes, `latest_obs` 200 | 8:00 AM EST, NNW 5 kt, gust 9, 30.25 in rising, air 41.9 °F | `realtime2` 404 | Keep with the Wilmington region; labeled backup only. |
| 41038 | CORMP, Wrightsville Beach Nearshore. `activestations` 34.141 N, 77.715 W, `met=y` | 12.7 mi NE | Wind, gust, pressure, air, water temp. **No waves** (WVHT MM; `.spec` 404) | Yes | `latest_obs` 8:08 AM EST; `realtime2` newest 13:08 UTC (8:08 AM ET): 330°, 6.0 m/s, gust 8.0, 1024.5 hPa, ATMP 8.5 °C, WTMP 19.0 °C | 60 min | Complementary to 41110 at almost the same place (41110 has waves, no wind; 41038 has wind and WTMP, no waves). |
| 41110 | CORMP / CDIP 150, Masonboro Inlet ILM2. 34.144 N, 77.715 W | 12.8 mi NE | Seas (WVHT), swell (`.spec` SwH), water and air temp. No wind | Yes | See table above | 30 min | Best available seas/swell, but it is Wilmington's primary wave buoy and must be labeled. |
| 41108 | SCRIPPS / CDIP 200, Wilmington Harbor. 33.719 N, 78.016 W | 22.7 mi SSW | Seas, swell, water temp. No wind | Yes | 8:26 AM EST seas 2.3 ft; `.spec` SwH 0.1 m | 30 min | Different segment (harbor / Cape Fear entrance). |
| 41013 | NDBC Frying Pan Shoals. 33.436 N, 77.764 W | 41.8 mi S | Wind, seas, swell, air and water temp | Yes | 8:30 AM EST met; wave summary 8:10 AM EST | 10 min met; waves / `.spec` ~30 min | Too far to be local. |
| 41037 | CORMP, Wrightsville Beach Offshore (ILM3). `activestations` 33.988 N, 77.362 W, **`met=n`** | 30.6 mi E | Would be an offshore buoy; today's file has met columns, wave fields MM, no `.spec` | **No.** `latest_obs` 404 (8:52 AM ET). `realtime2` newest row is **10 Oct 2026 22:08 UTC** (6:08 PM ET 10 Oct), and many preceding rows repeat the same 230° / 6.0 m/s / 1019.3 hPa values | Last row 6:08 PM ET 10 Oct 2026 | When it was moving, rows were ~60 min apart (historical, not current) | Still listed in `activestations` (catalog created 2026-11-15T13:45:01Z) but not reporting. Same silence noted on 13 Nov. |
| 8658163 / JMPN7 | CO-OPS NWLON, Wrightsville Beach. MDAPI 34.213306 N, 77.7867 W. Affiliations NWLON, Global, NWS. Tide type Mixed | 14.0 mi NNE | Observed water level (MLLW used today), predictions, wind, gust, air, pressure, water temp | Yes, all of those products returned data at 8:42 AM ET | See table. Datums (MDAPI, epoch 1983–2001, accepted Aug 19 2020): MLLW 18.83, NAVD88 21.58, MN (mean range) 3.98 ft, all relative to STND | 6 min | Closest observed ocean water level. Label as Wrightsville Beach. |
| 8658120 / WLON7 | CO-OPS NWLON, Wilmington. 34.2267 N, 77.9533 W | 13.9 mi NNW | Observed river/harbor water level, predictions, air, pressure, water temp. **No wind today** | Yes, except wind | 8:42 AM ET WL 1.736 ft MLLW; WTMP 64.2 °F. NDBC `latest_obs` 8:18 AM EST: pressure 30.28, water 64.0 °F (no wind in that digest) | 6 min (not separately re-sampled; same NWLON pattern as 8658163) | Harbor, not oceanfront. |
| 8658559 | CO-OPS Wilmington Beach, 34.0317 N, 77.8933 W | Anchor | Tide **predictions only** | Predictions yes; water_level no | See table | Predictions, not obs | Subordinate to Cape Hatteras 8654400. Removed as a physical station in 1979. Products list: Tide Predictions, Benchmarks, Datums — no Water Levels, no Meteorological. |
| 8658715 | CO-OPS Federal Point, Cape Fear River. 33.9617 N, 77.94 W | 5.5 mi SSW | Tide predictions only, subordinate type S to **8658120 Wilmington** (offsets timeHigh −77 min, timeLow −112 min, heightHigh 0.94, heightLow 0.93) | Predictions yes; water_level no | Today's hilo GMT MLLW: 04:36 3.707 H, 09:56 0.602 L, 17:00 4.189 H, 23:05 0.875 L | Predictions | River, not Kure oceanfront. |
| 8658579 | CO-OPS Sunny Point, MOTSU North Wharf. 34.0233 N, 77.9467 W. Type R (harmonic; empty reference id) | 3.1 mi W, river / ammunition terminal | Harmonic predictions. No observed WL today | Predictions yes; water_level no | Today's hilo GMT MLLW: 05:39 3.546 H, 11:49 1.194 L, 17:53 4.321 H (three events returned) | Predictions | Cape Fear River, not the ocean beach. Has a Harmonic product. |
| 8658501 | Orton Point, Cape Fear River. 34.0567 N, 77.94 W | 3.2 mi WNW | Predictions (tideType Diurnal in MDAPI) | Predictions yes | 05:17 3.865 H, 10:50 0.647 L, 17:41 4.367 H GMT MLLW | Predictions | River. |
| 8659084 | Southport. Type R, affiliations Hydro. 33.915 N, 78.0183 W | 10.8 mi SW | Harmonic predictions. No observed WL today | Predictions yes; water_level no | 04:27 3.411 H, 10:18 0.748 L, 16:48 4.32 H, 23:14 0.679 L GMT MLLW | Predictions | Next region toward the mouth, not this oceanfront. NWS point is NCZ110, not NCZ108. |
| ZBQN7 / NOQN7 / NOXN7 | NERRS (Zeke's Basin 33.955 N, 77.935 W; Research Creek) | ZBQN7 5.8 mi SSW | `activestations` lists them with **`met=n`** | **No.** NDBC `latest_obs` and `realtime2` 404 at 8:52 AM ET | — | — | Do not wire. Water-quality feeds, if any, were not verified and are out of scope. |

## NWS office, forecast point, and zones

- **Office:** NWS Wilmington, NC (ILM). Point forecast at the official
  8658559 coordinate: `https://api.weather.gov/gridpoints/ILM/92,67/forecast`
  (and hourly / grid). Checked 8:52 AM ET.
- **Land zone:** NCZ108 Coastal New Hanover. (NCZ107 Inland New Hanover
  exists; it was not the forecast zone for 8658559 or Federal Point.)
- **Marine tile:** AMZ250, official name "Coastal waters from Surf City to
  Cape Fear NC out 20 nm." Caption that the zone also covers Wrightsville
  and the run to Surf City — the same kind of zone-vs-region mismatch as
  at Wrightsville itself.
- **Do not use AMZ252** (Cape Fear to Little River Inlet) as this region's
  marine zone.
- **Alert products (proposed):** AMZ250, NCZ108. County NCC129 (New Hanover)
  is available if county alerts are used elsewhere. Do not add Brunswick
  NCZ110 or Crystal Coast zones.
- **Surf zone forecast (SRF) and rip-current / CFW:** SRF and CFW are valid
  NWS product types (listed in `/products/types` at 8:54 AM ET). Queries
  for recent products were empty for these offices today: `/products?type=SRF&start=2026-11-14T00:00:00Z`
  returned 74 SRF products nationally and **none from ILM, MHX, or AKQ**;
  `/products?type=SRF&location=ILM` and `/products/types/SRF/locations/ILM`
  (and the MHX/AKQ analogues) returned empty `@graph`; the same pattern
  held for CFW (54 national products since 14 Nov, none from ILM/MHX/AKQ).
  The `forecast.weather.gov` product.php pages for ILM/MHX/AKQ SRF did not
  contain a product `<pre>` at 8:54 AM ET. **Whether ILM issues an SRF or
  a rip-current statement seasonally was not confirmed from a product text
  today.** Do not advertise a live surf-zone or rip-current product until
  one is observed.

## What's missing

- No observed tide, wind, or water-temperature sensor on the Carolina
  Beach or Kure Beach oceanfront.
- No nearshore wave buoy off these beaches; 41110 is 12.8 mi NE at
  Masonboro Inlet.
- 41037, the listed offshore CORMP buoy, is silent (last `realtime2` row
  10 Oct 2026).
- Ocean tide predictions at the named local station are a 1979-removed
  subordinate of Cape Hatteras, not a local harmonic or a live gauge.
- No verified ILM SRF / rip-current product on this check date.
- NERRS stations in the Cape Fear estuary are not delivering NDBC met.

## Forecast coverage

ILM point forecast and hourly grid at 8658559; marine forecasts for AMZ250;
land forecasts / advisories for NCZ108. Tide predictions at 8658559
(label the Hatteras reference) and at 8658163. No NWPS river forecast is
needed for the ocean beaches (Cape Fear at Wilmington is a different, tidal
product and belongs to a harbor or river page, not this oceanfront).

## Licensing notes

United States government works from NOAA (NWS, CO-OPS, NDBC) are generally
public domain; still cite the station and the time. CORMP (UNC-W) operates
MBIN7, MBNN7, 41038, 41110, and 41037 — attribution is required; any
additional CORMP terms were not independently reviewed today. 41108 is a
Scripps / CDIP buoy — CDIP/Scripps attribution is required; license terms
beyond that were not verified today. NERRS stations, if ever used, need
their own attribution and were not usable today.

## How the region should appear on the site

- **Map center and zoom:** center on 8658559 (34.0317, −77.8933). Zoom
  **11** (tighter than Wilmington's 10; this is a short beach stretch from
  Masonboro Inlet to Federal Point). A later tweak can nudge the center
  slightly south if Kure needs equal billing, but do not invent a Kure
  pier coordinate.
- **Tiles:** Wind from MBIN7 (name Masonboro Island south). Seas and swell
  from 41110, with **separate labels** — "Seas (combined / significant wave
  height)" vs "Swell" from `.spec`, never one number for both — and a
  source label "Masonboro Inlet." Ocean water temp from 41110 or 41038,
  labeled. Tide tile: **predictions at Wilmington Beach 8658559**, with a
  note that they are subordinate to Cape Hatteras and that the closest
  observed ocean water level is Wrightsville Beach 8658163 (show that
  observed series only with a Wrightsville label, or keep observed WL on a
  clearly labeled backup). Weather: ILM point forecast. Marine: AMZ250
  with a short zone caption. Alerts: AMZ250 and NCZ108.
- **Do not** silently backfill seas/swell from 41108, 41013, or a stale
  41037. If 41110 is down, seas and swell should show as unavailable
  (same rule as other regions).

## Fit with the river gate / Falls-style brief

This is a coastal salt region, not a freshwater brief. `river_gate.py`
(on `data/river-gate`, tip d2708ef) does not apply. It should follow the
existing Wilmington / Wrightsville coastal brief pattern, with stricter
labeling because several "local" sensors actually sit in the Wilmington
region.

## Risks

1. Sharing 41110 with Wilmington: if that buoy drops, both regions lose
   seas and swell at once.
2. 8658559 is easy to misread as a live Carolina Beach tide gauge. It is
   not. The Hatteras reference and 1979 removal must stay on the tile.
3. AMZ250 and NCZ108 are wider than the two beaches.
4. Federal Point / Sunny Point / Southport predictions are river or cape
   tides, not Kure oceanfront tides.
5. MBIN7 cadence could not be confirmed today (`realtime2` 404).

## Open questions for Scout and Ed

1. Accept 41110 as a labeled Masonboro Inlet seas/swell source, with no
   automatic backup, even though Wilmington already uses it?
2. For the tide tile, show 8658559 predictions (with the Hatteras note)
   plus a labeled Wrightsville observed water level, or predictions only?
3. Is MBIN7 acceptable as the primary wind even though its update cadence
   could not be read from `realtime2` today?
4. Where exactly should the south boundary fall — Federal Point, the
   south end of Kure, or Cape Fear — and should AMZ252 ever appear?
5. Re-check ILM SRF / rip-current product issuance in season before
   promising that tile.
