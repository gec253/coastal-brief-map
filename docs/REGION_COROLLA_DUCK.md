# Region research: Corolla / Duck

Phase 1 only — sources and coverage, no app-code changes.

Checked the morning of Sunday 15 Nov 2026, America/New_York (EST, UTC−5),
between about 8:50 and 8:57 AM ET, with read-only GETs to official public
APIs (NDBC catalogs and `latest_obs` / `realtime2` / `.spec`, CO-OPS MDAPI
and Data API, NWS `/points`, `/zones/forecast`, and products). Distances
use a haversine with R = 3958.8 mi from the official CO-OPS coordinate of
Duck Pier 8651370. Nothing here is invented. Existing Nags Head research
already reserved Duck / Corolla as a later region and noted the MHX / AKQ
office split; this audit re-checked stations today and does not reuse
13 Nov values as current.

## Anchor

**CO-OPS 8651370 Duck** (SHEF DUKN7), NWLON. MDAPI: 36.1833 N, 75.7467 W
(checked 8:52–8:54 AM ET). Affiliations NWLON. Tide type Mixed.

This is a solid official anchor for **Duck**. It has live observed water
level, predictions, wind, gust, air temperature, and pressure. It does
**not** offer water temperature today (CO-OPS `water_temperature`
`date=latest` returned "No data was found" at 8:52 AM ET; the NDBC
`latest_obs` digest similarly had no water temp).

**Corolla has no official CO-OPS, NDBC, or USGS station** in today's
catalogs. Name searches of the CO-OPS water-level and meteorological
lists and of the NDBC station table / `activestations` found no station
named Corolla or Currituck Beach (Light). Official USCG / NPS lighthouse
coordinates were not fetched today, so this doc does **not** invent a
Corolla map point. Distances below are from Duck Pier and are labeled
as such. A combined Corolla–Duck region will need a published official
coordinate before the map can be honestly centered between the two towns.

## Coverage boundaries

- **South:** Stay north of the Nags Head / Kitty Hawk instruments. Nags
  Head already uses 44086 (Nags Head CDIP 243) as its seas/swell buoy and
  AMZ150 as its marine zone. Oregon Inlet (8652587, 44095) is 29–38 mi
  SSE of Duck and belongs to that southern stretch. Duck / Corolla should
  not steal 44086 as a primary source.
- **North:** The official ocean marine zone for Duck is **AMZ150** (MHX),
  "S of Currituck Beach Light NC to Oregon Inlet NC out to 20 NM" (NWS
  zone metadata, 8:52 AM ET). Currituck Beach Light sits in Corolla, so
  this zone's **northern edge is at Corolla**, not north of it. Beaches
  and waters **north** of the light (toward Carova and the VA line) are
  **not** in AMZ150. The AKQ marine zone for that ocean stretch was **not
  identified today** (ANZ630 and ANZ634 are Chesapeake Bay; ANZ633 is
  **Currituck Sound**, not the ocean). This is an open boundary question.
- **Land offices split the two towns:**
  - Duck Pier official coordinate → NWS `/points` office **MHX**,
    forecastZone **AMZ150** (the pier point is treated as marine), grid
    MHX 85,128, radar KAKQ (8:52 AM ET). The MHX public land zone
    **NCZ203 Northern Outer Banks** exists. A later land `/points`
    query at the Duck townsite (36.163, −75.75; 15 Nov 2026) confirmed
    forecastZone **NCZ203**, county **NCC055** (Dare), office MHX,
    relativeLocation Duck, NC, 0 m. The official pier coordinate still
    maps to AMZ150.
  - Corolla is in Currituck County. A land `/points` query at
    36.377, −75.830 the same day confirmed forecastZone **NCZ102
    Eastern Currituck**, county **NCC053** (Currituck), office **AKQ**
    (Wakefield). relativeLocation was Coinjock, NC, 10,420 m at 75°.
- **Sound side:** ANZ633 "Currituck Sound" (AKQ) is the official sound
  zone. It is relevant for the sound behind Corolla / Duck, not the
  oceanfront.

## Proposed instruments

| Need | Primary | Backup | Distance from 8651370 | Latest today (ET) | Cadence | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| Wind / gusts / pressure / air temp | 8651370 Duck Pier (CO-OPS NWLON) | 8652587 Oregon Inlet Marina, **labeled**, and only if Duck is down (already a Nags Head backup). No Corolla wind sensor. | 0.0 / 29.0 mi | 8651370 8:42 AM ET: wind 6.8 kt from 304° (NW), gust 7.97 kt, air 44.8 °F, pressure 1023.8 mb (CO-OPS, GMT 13:42). NDBC `latest_obs` DUKN7 8:18 AM EST: WNW 6.0 kt, gust 8.0, 30.23 in (no air temp in that digest) | 6 min (today's 6-minute WL series at 8651370: 13:18–13:48 UTC in 6.0 min steps, 139 points from 00:00 UTC) | Best official ocean-pier wind for Duck. Nothing closer to Corolla was found. |
| Seas (WVHT / combined seas) | 44056 Duck FRF (USACE waverider), labeled "Duck FRF" | 44100 Duck FRF 26 m (CDIP 430), **labeled offshore / 26 m**, not a silent substitute. Do not auto-use 44086 (Nags Head, 22.1 mi) or 44095 (Oregon Inlet, 37.9 mi). | 2.2 / 10.0 mi ENE | 44056 `latest_obs` 8:00 AM EST: Seas 3.3 ft, peak period 6 s; `realtime2` 8:00 AM ET (13:00 UTC): WVHT 1.0 m (~3.3 ft), DPD 6 s. 44100 `latest_obs` 8:30 AM EST: Seas 4.3 ft, peak 6 s; `realtime2` also 30 min | 30 min | Today 44100 seas (4.3 ft) were higher than 44056 (3.3 ft). They are not interchangeable without a label. Neither is at Corolla. |
| Swell (`.spec` SwH, not WVHT) | 44056 `.spec` | 44100 `.spec`, labeled. **No automatic backup from 44086** — Nags Head research already showed that Oregon Inlet / Nags Head swell can be a different train than Duck. | 2.2 / 10.0 mi | 44056 `.spec` 8:00 AM ET: WVHT 1.0 m, **SwH 0.2 m (0.7 ft), SwP 10.0 s, SwD ENE**; wind sea 1.0 m, 6.2 s, NE. 44100 `.spec` 8:30 AM ET: SwH 0.2 m (0.7 ft), SwP 10.0 s, ENE; wind sea 1.3 m class (WWH 4.3 ft in `latest_obs`) | 30 min | Today combined seas were wind-sea dominated; swell was a 0.7 ft leftover. Always separate the labels. 44086 at 8:30 AM EST: seas 4.6 ft, swell 0.7 ft / 10 s NE — same small swell, larger seas, and it is Nags Head's buoy. |
| Ocean / nearshore water temp | 44056 WTMP (and 44100, labeled) | No CO-OPS water temp at Duck. Oregon Inlet 8652587 has water temp but it is a **marina / sound-side** sensor 29 mi south, not Duck ocean. | 2.2 / 10.0 mi | 44056 8:00 AM EST: 60.8 °F. 44100 8:30 AM EST: 61.2 °F. 8652587 8:42 AM ET: 50.7 °F (much colder — do not present as oceanfront Duck) | 30 min (buoys) / 6 min (Oregon Inlet) | Duck Pier has no WTMP today. |
| Observed water level | 8651370 Duck, datum MLLW (requested today) | None closer to Corolla. 8652587 Oregon Inlet Marina is sound / inlet, 29 mi SSE, labeled only | 0.0 / 29.0 mi | 8:42 AM ET: 3.23 ft MLLW, preliminary (`q=p`), sigma 0.266 | 6 min | Datums (MDAPI, epoch 1983–2001, accepted Sep 26 2011): MLLW 18.58, NAVD88 20.77, MN 3.22 ft, relative to STND. |
| Tide predictions | 8651370 Duck (same station as observed WL — harmonic / NWLON) | 8651605 Kitty Hawk (ocean), subordinate type S to 8651370, 6.0 mi SSE, labeled if used. **No Corolla prediction station found.** | 0.0 / 6.0 mi | 8651370 today's hilo GMT MLLW (8:52 AM ET): 03:44 2.706 H, 09:37 0.986 L, 16:00 3.399 H, 22:36 0.813 L. 8651605 (offsets vs Duck: heightHigh 1.01, heightLow 1.43, timeHigh −1 min, timeLow +2 min): 03:43 2.733 H, 09:39 1.41 L, 15:59 3.433 H, 22:38 1.162 L | Predictions | Duck can honestly show observed and predicted water level at one official station. Corolla cannot. |

## Station details

| Station | Identity | Location vs Duck Pier | What it measures | Reporting today? | Latest today | Cadence | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 8651370 / DUKN7 | CO-OPS NWLON, Duck, NC. 36.1833 N, 75.7467 W | Anchor (pier) | Observed WL, predictions, wind, gust, air, pressure. **No water temp today.** Products include Water Levels, Meteorological, Tide Predictions, Harmonic, etc. | Yes, except WTMP | 8:42 AM ET CO-OPS; NDBC digest 8:18 AM EST | 6 min | Primary wind, pressure, air, and tide for Duck. |
| 44056 | USACE FRF waverider, Duck FRF. `activestations` 36.200 N, 75.714 W, `met=y`, `currents=y`. NDBC table: FZUS52.KMHX | 2.2 mi ENE | Seas (WVHT), swell (`.spec`), air and water temp. No wind in today's `realtime2` (WDIR/WSPD MM) | Yes | 8:00 AM EST / 13:00 UTC | 30 min | Closest wave buoy to Duck. Currents were listed in the catalog (`currents=y`); a currents time series was **not fetched** today, so current-velocity availability is unverified. |
| 44100 | SCRIPPS / CDIP 430, Duck FRF 26 m. 36.257 N, 75.593 W, `met=y`, `currents=y`. NDBC table forecast office FZUS51.KAKQ | 10.0 mi ENE (farther offshore and a bit north) | Seas, swell, air and water temp. No wind in `realtime2` | Yes | 8:30 AM EST seas 4.3 ft; `.spec` SwH 0.7 ft | 30 min | Useful labeled offshore / slightly-norther buoy. Still not a Corolla buoy. Today seas were higher than at 44056. |
| 44086 | UNC CSI / CDIP 243, Nags Head. 36.001 N, 75.421 W | 22.1 mi SE | Seas, swell, air and water temp | Yes | 8:30 AM EST seas 4.6 ft; swell 0.7 ft / 10 s NE | 30 min | **Nags Head region's primary wave buoy.** Labeled comparison only; not a silent backup. |
| 44095 | Oregon Inlet waves (CDIP). Latest_obs position 35°45.0' N, 75°19.8' W | 37.9 mi SSE | Seas, swell, water temp | Yes | 7:56 AM EST seas 4.6 ft; wave summary swell 3.9 ft / 6.2 s NNE — a **different swell** than Duck's 0.7 ft / 10 s ENE at 8:00 AM | 30 min | Do not substitute Duck swell from this buoy. Already in the Nags Head research as a seas-only labeled option. |
| FRFN7 | USACE-CHL Field Research Facility, Duck. `activestations` 36.19 N, 75.739 W, elev −11.4, **`met=n`**. In the NDBC station table as a waverider | 0.6 mi NE | Cataloged; not delivering NDBC realtime | **No.** `latest_obs`, `realtime2`, and `.spec` all 404 at 8:52 AM ET | — | — | Still listed in `activestations` (created 2026-11-15T13:45:01Z) but unusable. Do not wire unless a later check shows a live feed. |
| 8651605 | CO-OPS Kitty Hawk (ocean). 36.1017 N, 75.71 W. Type S subordinate to 8651370 | 6.0 mi SSE | Predictions only | Predictions yes | See table | Predictions | Optional, labeled. Not a Corolla station. |
| 8652587 / ORIN7 | CO-OPS NWLON, Oregon Inlet Marina. 35.7957 N, 75.5482 W | 29.0 mi SSE | Observed WL, wind, air, pressure, water temp (marina / inlet, not ocean pier) | Yes | 8:42 AM ET: WL 1.493 ft MLLW, wind 9.14 kt NNW, gust 13.41, air 48.7 °F, WTMP 50.7 °F, 1023.0 mb | 6 min (not separately re-sampled; NWLON) | Nags Head / inlet backup. Water temp is not Duck ocean temp. |
| 44099 | SCRIPPS, Cape Henry, VA (CDIP 147). 36.915 N, 75.722 W | 50.6 mi N | Listed in the station table (AKQ). Not shortlisted for today's `latest_obs` | **Not checked today** | — | — | Too far to be a Corolla local buoy; mention only as a possible far-north labeled comparison if a later check is needed. |
| 44014 | NDBC Virginia Beach 64 NM east. 36.603 N, 74.837 W | Far offshore | Offshore met / waves | **Not checked today** | — | — | Not a local source. |

JPRN7 (Jennette's Pier ADCP, Nags Head) remains a Nags Head-area station
and was not re-fetched today.

## NWS office, forecast point, and zones

- **Duck (official pier point):** NWS Newport / Morehead City (**MHX**),
  grid MHX 85,128. Point forecast:
  `https://api.weather.gov/gridpoints/MHX/85,128/forecast`. The pier
  coordinate's `forecastZone` is **AMZ150**, not a land zone.
- **Duck land zone (confirmed 15 Nov 2026):** NCZ203 Northern Outer
  Banks (MHX). NWS `/points` at 36.163, −75.75 (Duck townsite) returned
  forecastZone NCZ203, county NCC055, office MHX, relativeLocation
  Duck, NC, 0 m. User-Agent: TheCoastalBrief/1.0
  (+https://thecoastalbrief.com; coastal conditions site).
- **Corolla land (confirmed 15 Nov 2026):** NCZ102 Eastern Currituck,
  office **AKQ** (Wakefield). NWS `/points` at 36.377, −75.830 returned
  forecastZone NCZ102, county NCC053, office AKQ, relativeLocation
  Coinjock, NC, 10,420 m at bearing 75°. Same User-Agent. Alert zones
  were not changed; both already matched.
- **Marine tile for Duck and for Corolla beaches south of Currituck
  Beach Light:** AMZ150, with a caption that the official zone runs from
  the light to Oregon Inlet and is shared with Nags Head. Waters **north
  of the light** need an AKQ ocean zone that was not identified today.
- **Sound:** ANZ633 Currituck Sound (AKQ), if a sound-side tile is wanted.
- **Alert products (proposed):** AMZ150, NCZ203 (Duck / northern Dare
  Outer Banks — confirm land membership with a land point before shipping),
  NCZ102 (Corolla / eastern Currituck). Consider ANZ633 for sound-side
  alerts. Do not add Hatteras zones (AMZ152/154, NCZ205) or Chesapeake
  ANZ630/634.
- **Surf zone forecast / rip current:** Same empty result as the Carolina
  Beach check: no ILM, MHX, or AKQ SRF or CFW in the NWS products API
  from 14 Nov 2026 00:00 UTC through this morning's 8:54–8:56 AM ET
  queries. Do not advertise a live MHX or AKQ surf-zone or rip-current
  product until one is observed.

This region **crosses the MHX / AKQ county line**. A single "NWS office"
tile will be wrong for one of the two towns unless the UI names both
offices and zones.

## What's missing

- No official station of any kind at Corolla or Currituck Beach Light
  (no wind, no observed tide, no local predictions, no wave buoy).
- No official Corolla map coordinate in this audit.
- No water temperature at Duck Pier (CO-OPS) today; ocean temp has to
  come from the FRF buoys.
- FRFN7, the FRF pier station in the NDBC table, is still 404.
- Marine zone north of Currituck Beach Light not identified.
- Land-zone membership of the Duck townsite (NCZ203) was confirmed with
  a land `/points` query on 15 Nov 2026 (see NWS office section).
- No verified MHX or AKQ SRF / rip-current product today.
- FRF currents (`currents=y` on 44056 and 44100) not verified with a
  time series.

## Forecast coverage

- Duck: MHX point forecast at the pier grid, marine AMZ150, expected land
  NCZ203.
- Corolla: AKQ / NCZ102 land forecast (verify with an official point);
  ocean AMZ150 only south of the light.
- Tide: observed + predicted at 8651370. No Corolla tide station.
- Wave forecasts: NDBC station table points 44056 at FZUS52.KMHX and
  44100 at FZUS51.KAKQ; those text products were not fetched today.

## Licensing notes

NOAA / NWS / CO-OPS / NDBC and USACE (as U.S. government works) are
generally public domain; cite station and time. 44056 is a USACE FRF
waverider. 44100 is listed as SCRIPPS / CDIP 430 at the FRF 26 m site —
CDIP/Scripps attribution is required; additional terms were not verified
today. 44086 is UNC Coastal Studies Institute / CDIP — attribution
required, not a primary for this region. FRF / USACE pages may also
exist for research instruments that are not on the NDBC wire (FRFN7 is
an example); do not scrape those unless a later official, licensed feed
is documented.

## How the region should appear on the site

- **Map center and zoom:** until an official Corolla coordinate exists,
  center on Duck Pier **36.1833, −75.7467**, zoom **10** (same as Nags
  Head). That framing will under-show Corolla. A later center between
  the two towns, probably zoom 9, should wait for a published official
  Corolla / Currituck Beach Light coordinate — do not invent one.
- **Tiles:** Wind, observed tide, and predictions from 8651370 (one
  official station for all three is a strength). Seas and swell from
  44056, **separately labeled** (combined seas vs swell), source "Duck
  FRF." Optional second wave tile or caption for 44100 as "Duck FRF 26 m
  / farther offshore" when seas disagree (they did today: 4.3 ft vs
  3.3 ft). Ocean water temp from 44056, not from Oregon Inlet's 50.7 °F
  marina reading. Weather: show **both** MHX (Duck) and AKQ (Corolla)
  rather than a single office. Marine: AMZ150 with a caption about the
  light-to-Oregon Inlet span and the hole north of the light. Alerts:
  AMZ150, NCZ203, NCZ102.
- If 44056 is down, do not silently substitute 44086 or 44095 swell.
  A labeled 44100 seas/swell is the only nearby official alternative,
  and it must be named.

## Fit with the river gate / Falls-style brief

Coastal salt region. `river_gate.py` (d2708ef) does not apply. Follow
the Nags Head coastal brief pattern, with the added office-split and
the lack of any Corolla sensor.

## Risks

1. A "Corolla / Duck" product that only has Duck sensors will disappoint
   Corolla users unless every tile is honest about location.
2. Sharing AMZ150 with Nags Head: alerts and the marine forecast also
   cover Kitty Hawk to Oregon Inlet.
3. The MHX / AKQ split is easy to get wrong (Duck vs Corolla land
   forecasts and alerts).
4. FRFN7 looks like a local FRF pier station in the catalog but is dead
   on the NDBC wire today.
5. 44100 and 44056 disagreed on seas this morning; auto-averaging them
   would hide a real difference.

## Open questions for Scout and Ed

1. Ship a Duck-centered region first, and add Corolla only as a named
   forecast/alert zone without local observations — or wait for an
   official Corolla coordinate and a clearer north-of-the-light marine
   zone?
2. What official coordinate should be used for Corolla / Currituck
   Beach Light (USCG light list, NPS, or an NWS point)?
3. Which AKQ ocean marine zone covers waters north of Currituck Beach
   Light?
4. NCZ203 at the Duck townsite and NCZ102 at Corolla were confirmed with land `/points` queries on 15 Nov 2026 (forecastZone and county as recorded above).
5. Is a labeled 44100 "26 m / offshore" tile worth showing beside 44056
   when seas differ, or should 44100 stay backup-only?
6. Re-check MHX and AKQ SRF / rip-current products in season.
7. Should FRF currents be investigated in a later, scoped check, or
   ignored until they appear on a public NDBC currents feed?
