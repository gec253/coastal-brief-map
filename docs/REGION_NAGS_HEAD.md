# Region research: Nags Head / Outer Banks

Phase 1 only — sources and coverage, no app-code changes.

Checked the evening of 13 Nov 2026, America/New_York (EST, UTC−5), around
**9:46–9:48 PM EST**. Official metadata: NDBC `station_table.txt`, NDBC
`activestations.xml` (created 9:40 PM EST), CO-OPS MDAPI (including tide
prediction offsets), and NWS `/points` and `/zones/forecast`. Latest
observations: NDBC `realtime2/{id}.txt` and `.spec` (45-day files, used for
cadence and gaps), CO-OPS Data API `date=latest`, and NWS station
observations for nearby airports. Distances use the same haversine as
`conditions.py` (`miles_bearing`, R = 3958.8 statute miles). Nothing here
was invented or interpolated.

## Anchor

**Jennette's Pier, Nags Head**, 35.912 N, 75.587 W.

This is the official NDBC position of **JPRN7** (35°54'44" N, 75°35'12" W),
"Jennette's Pier, Nags Head, NC." CO-OPS also publishes a subordinate tide
prediction station, **8652226** "Jennette's Pier," at 35.910 N, 75.592 W,
on the ocean side of the pier. The pier is the right local landmark: it is
in Nags Head, on the ocean, and already appears in official NOAA tables.

**JPRN7 is not currently a usable observation source.** It is listed as a
bottom-mounted ADCP, it is **not** in tonight's `activestations.xml`, and
both `realtime2/JPRN7.txt` and `.spec` return HTTP 404. The coordinates are
used as the region anchor only.

### `JMPN7` is not Jennette's Pier

`JMPN7` is CO-OPS **8658163, Wrightsville Beach**, at Johnnie Mercer's Pier
(34.213 N, 77.786 W), about 171 miles southwest of Nags Head. The IDs look
alike (`JMPN7` vs `JPRN7`) and are easy to swap. For this region, ignore
`JMPN7`.

## Coverage boundaries

Proposed region: **Kitty Hawk, Kill Devil Hills, and Nags Head, south to
Oregon Inlet / Bodie Island.**

- **South end: Oregon Inlet.** Do not cross onto Pea Island or Hatteras
  Island. Rodanthe is already in the live Hatteras region (land zone
  **NCZ205**, marine **AMZ152**). Oregon Inlet is the clean split.
- **North end: the Kitty Hawk / Southern Shores line, before Duck.** Duck
  and Corolla are a later roadmap region. Duck's ocean pier (8651370 /
  `DUKN7`) and the Duck FRF buoys (44056, 44100) are useful nearby sources,
  but they must be labeled "Duck," not "Nags Head."
- **Corolla is a different Weather Service office.** A point at Corolla
  returned **NWS Wakefield (AKQ)** and land zone **NCZ102 Eastern
  Currituck**, not MHX / NCZ203. That is a hard reason to keep Corolla out
  of this region. Duck sits near the MHX / AKQ line; a land point just west
  of Duck already resolved to AKQ and ANZ633 (Currituck Sound). Forecast
  points at the north edge need care in Phase 2.
- **West:** Roanoke Island / Manteo is in the same land zone (NCZ203) but
  is sound-side (marine **AMZ231**, Croatan and Roanoke Sounds). Ocean-buoy
  conditions are not Manteo conditions. Include Manteo only as an open
  question, not as an unlabeled part of the ocean dashboard.
- **Does not overlap Hatteras.** Hatteras already uses AMZ154 (primary
  marine), AMZ152 (alerts / east of the cape), and NCZ205. This region's
  ocean zone is **AMZ150**, which ends at Oregon Inlet.

## Proposed instruments

There is **no live wind, water-temperature, or observed-tide sensor at
Jennette's Pier tonight**. Several good stations sit 8–24 miles away and
can be used if every label names the real place. Do not present Duck or
Oregon Inlet conditions as "Nags Head" without that label.

| Instrument | Primary | Backup | Distance | Latest obs (ET) | Cadence | Status |
|---|---|---|---|---|---|---|
| Wind (ocean-exposed) | **No station at Nags Head.** Proposed: 8651370 / DUKN7, Duck Pier, labeled "Duck Pier" | 8652587 / ORIN7, Oregon Inlet Marina, labeled "Oregon Inlet Marina (sound side)" | 20.8 / 8.3 mi | Duck 9:36 PM EST, 16.9 mph NNW; marina 12.4 mph N | 6 min both | Both active. Tonight they already differed (ocean pier vs sound). KFFA (First Flight, Kill Devil Hills) and KMQI (Manteo) latest observations at 9:15 PM EST had **no wind or temperature values** (`qualityControl: Z`). Not usable tonight. |
| Seas | 44086, Nags Head (CDIP 243) | 44095, Oregon Inlet (CDIP 192), **labeled**, and only for combined seas — see swell | 11.1 / 18.2 mi | 44086 9:30 PM EST, WVHT 1.5 m (4.9 ft); 44095 8:56 PM EST, 1.6 m (5.2 ft) | 30 min | Both active and reliable. |
| Swell | 44086 `.spec` | **No suitable automatic backup** | 11.1 mi | 9:30 PM EST, SwH 0.2 m (0.7 ft), SwP 10 s; wind sea 1.5 m | 30 min | Active. **44095 swell was 1.1 m (3.6 ft) at 8:56 PM — not the same train as 44086.** Do not substitute. Duck 44100 / 44056 SwH was 0.2 m tonight (same as 44086) but those buoys are at Duck, 21–24 mi north. |
| Inshore water temp | **No suitable ocean-pier source.** 8652587 Oregon Inlet Marina is sound / inlet water if it is shown at all, and must be labeled that way | 8651370 Duck Pier currently **does not publish water temperature** | 8.3 mi (marina) | Marina 9:36 PM EST, 62.4 °F | 6 min | JPRN7 is down. Duck CO-OPS latest water-temperature call returned "No data was found." NDBC `DUKN7` had **no WTMP in the entire 45-day file**. |
| Offshore water temp | 44086 | Do not silently use 44095 or the Duck buoys | 11.1 mi | 9:00 PM EST, 18.3 °C (64.9 °F) | 30 min | Active. Tonight 44095 was 19.2 °C and Duck 44056 / 44100 were 17.0 °C. |
| Air temp | 8652587, labeled "Oregon Inlet Marina" (closer) or 8651370, labeled "Duck Pier" | The other of those two | 8.3 / 20.8 mi | 9:36 PM EST, 52.0 °F marina / 51.4 °F Duck | 6 min | Active. No sensor at the pier. |
| Pressure | Same pair, with labels | — | 8.3 / 20.8 mi | 9:36 PM EST, 1006.3 mb marina / 1007.4 mb Duck | 6 min | Active. |
| Harbor / inlet wind | 8652587, Oregon Inlet Marina (sound side) | — | 8.3 mi | 9:36 PM EST, 12.4 mph N | 6 min | Active. This is the inlet / sound wind, not the ocean beach. |
| Tide predictions | 8652226, Jennette's Pier (ocean), subordinate to 8651370 Duck | — | 0.2 mi from the anchor | Predictions only (no live water level) | — | Official NOAA offsets vs Duck: high-tide height factor 1.04, low-tide 1.43; time offset −5 min high, +1 min low. No harmonics of its own. Phase 2 must check whether the tide tile can use a subordinate prediction station with a different observed-WL station. |
| Tide, observed water level | 8651370 Duck Pier (ocean), labeled "Duck Pier" — this is also the official reference for the Jennette's prediction | 8652587 is a **different tidal basin** (sound / inlet), 8.3 mi south | 20.8 mi | 9:36 PM EST, 4.644 ft MLLW, preliminary, flag `1,0,0,0` | 6 min | Active NWLON. Kitty Hawk (ocean) 8651605 is also a Duck subordinate (predictions only). |

## Station details

| ID | Official name / location | Water body | Feeds | Reporting? | Latest (ET) | Cadence | 45-day gaps |
|---|---|---|---|---|---|---|---|
| JPRN7 | Jennette's Pier, Nags Head, NC. Bottom-mounted ADCP. 35.912 N, 75.587 W | Ocean, at the pier | None in the NDBC realtime feed | **No.** Not in `activestations`; realtime 404 | — | — | Not a current source. Anchor only. |
| 8652226 | Jennette's Pier (ocean). CO-OPS subordinate prediction station. 35.910 N, 75.592 W | Ocean, at the pier | Tide **predictions only**, referenced to 8651370 | Predictions exist; no observations | — | — | Not an observation station. |
| 44086 | Nags Head, NC (CDIP 243). UNC Coastal Studies Institute waverider. 36.001 N, 75.421 W | Offshore ocean, 11.1 mi ENE of the pier | Seas (WVHT), swell (`.spec`), WTMP, air | Yes (`met=y`) | `.spec` 9:30 PM EST, WVHT 1.5 m, SwH 0.2 m; `.txt` 9:00 PM, WTMP 18.3 °C | 30 min | Two short gaps on 21 Oct (90 and 150 min). Almost every row has WVHT and WTMP; every `.spec` row has SwH. **No wind.** |
| 44095 | Oregon Inlet, NC (CDIP 192). UNC CSI waverider. 35.750 N, 75.330 W | Offshore ocean, 18.2 mi SE, off Oregon Inlet | Seas, swell, WTMP (no air in the latest `.txt`) | Yes | 8:56 PM EST, WVHT 1.6 m, SwH **1.1 m**, WTMP 19.2 °C | 30 min | One 90-min gap late on 7 Nov. Reliable as a station, but tonight's swell split does not match 44086. |
| 44100 | Duck FRF 26m, NC (CDIP 430). Scripps waverider. 36.257 N, 75.593 W | Offshore / mid-nearshore at Duck, 23.8 mi north | Seas, swell, WTMP, air | Yes | `.spec` 9:30 PM EST, WVHT 1.4 m, SwH 0.2 m; `.txt` 9:00 PM, WTMP 17.0 °C | 30 min | A few 90–180 min gaps (21 Oct, 12 Nov). Label "Duck FRF 26 m." |
| 44056 | Duck FRF, NC. USACE waverider. 36.200 N, 75.714 W | Nearshore at the Duck Field Research Facility, 21.1 mi NNW | Seas, swell, WTMP, air | Yes | 9:00 PM EST, WVHT 1.3 m (4.3 ft, a little lower than 44086), SwH 0.2 m, WTMP 17.0 °C | 30 min | Four short gaps, all in late October. Label "Duck FRF." |
| FRFN7 | USACE-CHL Field Research Facility, Duck, NC. 36.190 N, 75.739 W | Nearshore Duck | Listed as a waverider in the station table | **No** usable realtime. In `activestations` with `met=n`; realtime 404 | — | — | Do not wire. 44056 / 44100 already cover Duck waves. |
| 8651370 / DUKN7 | Duck Pier, NC. CO-OPS NWLON. 36.1833 N, 75.7467 W | Ocean pier at Duck | Wind, air, pressure, observed WL, tide predictions (reference for Jennette's and Kitty Hawk). **No water temp** | Yes | 9:36 PM EST, wind 16.9 mph NNW, air 51.4 °F, pressure 1007.4 mb, WL 4.644 ft MLLW | 6 min | One long outage **2:00 PM 5 Oct–3:30 PM 7 Oct** (about 49.5 h); otherwise short October gaps. `DUCN7` (old C-MAN) failed in 2008 and is not active; NDBC points to `DUKN7`. |
| 8652587 / ORIN7 | Oregon Inlet Marina, NC. CO-OPS NWLON. 35.7957 N, 75.5482 W | Sound / marina, west of the inlet, not the ocean beach | Wind, air, pressure, **inlet / sound WTMP**, observed WL, tide predictions | Yes | 9:36 PM EST, wind 12.4 mph N, air 52.0 °F, WTMP 62.4 °F, pressure 1006.3 mb, WL 1.637 ft MLLW | 6 min | Short gaps only; longest 4.5 h on 14 Oct. Water-level flag `1,0,0,0` on the latest row. |
| 41120 / 41025 | Cape Hatteras East / Diamond Shoals | Hatteras region | Already used by the live Hatteras dashboard | — | — | — | Out of this region. Do not reuse as Nags Head sources. |

Older table entries 41062 (Hatteras Bay), 44006, and 44019 are not in
`activestations`. OOI Pioneer buoys (41082, 41083, 44079) are far offshore
in the Mid-Atlantic Bight and are not local.

## NWS office, forecast point, and zones

Office: **NWS Newport / Morehead City (MHX)** for this region. (Corolla and
some Duck-sound points fall in AKQ; do not aim the forecast point there.)

The pier coordinate itself resolves to marine zone **AMZ150**. A point only
a couple of hundred yards west can fall into **AMZ231** (Croatan and
Roanoke Sounds) because the island is so narrow. Phase 2 must pick a land
point that returns **NCZ203**, not a pier or sound point.

- **Recommended land forecast point:** Whalebone Junction / south Nags
  Head, 35.895 N, 75.590 W. NWS `/points` returns **MHX grid 92, 116**,
  forecast zone **NCZ203 Northern Outer Banks**, office MHX. Kill Devil
  Hills (36.031 N, 75.671 W) is also NCZ203, grid MHX 88, 122, if a more
  central town point is preferred.
- **Marine tile:** **AMZ150**, official name "S of Currituck Beach Light NC
  to Oregon Inlet NC out to 20 NM" (CWA MHX, metadata confirmed). This is
  the ocean from the northern Outer Banks down to Oregon Inlet. It also
  covers Duck and the approach to Corolla, which is wider than the proposed
  region — the same kind of zone-vs-region mismatch as AMZ250 at
  Wrightsville.
- **Do not use AMZ152 as the primary marine zone.** That is "S of Oregon
  Inlet NC to Cape Hatteras NC out to 20 NM," already in the Hatteras
  product. It can be an alert neighbor only.
- **Alert zones (proposed):** `AMZ150`, `NCZ203`, `AMZ231` (Croatan and
  Roanoke Sounds, which is the sound behind Nags Head; Oregon Inlet Marina
  sits in this zone). Optional neighbor: `AMZ152` (south of the inlet) and
  maybe `AMZ230` Albemarle Sound. Do **not** add NCZ205 (Hatteras Island)
  or NCZ102 (Eastern Currituck / Corolla, office AKQ).

## Risks

1. **No instrument at the anchor itself** except a subordinate tide
   prediction. Wind, inshore ocean water temperature, and observed water
   level all have to come from Duck or Oregon Inlet and be labeled, or
   show as unavailable.
2. **Duck Pier has no water temperature** in the current CO-OPS product
   list or in 45 days of NDBC data. The only inshore water-temp sensor in
   reach is Oregon Inlet Marina, which is sound-side and was 62.4 °F
   tonight versus 64.9 °F at 44086.
3. **44095 is a poor automatic swell (and water-temp) backup** for 44086.
   Combined seas were close tonight (1.6 m vs 1.5 m), but swell was not
   (1.1 m vs 0.2 m), and water temp differed by 0.9 °C. If 44086 is down,
   swell and offshore temperature should show as unavailable rather than
   flip to Oregon Inlet. Combined seas from 44095 can be shown only with
   an "Oregon Inlet offshore" label.
4. **Duck and Oregon Inlet winds already disagreed tonight** (16.9 mph at
   the ocean pier vs 12.4 mph at the marina). A single unlabeled "Nags
   Head wind" number would be misleading.
5. **Observed ocean tide is 20.8 mi away at Duck.** That is the official
   reference for the Jennette's Pier prediction, so it is the honest
   observed-WL source, but it is not local. Oregon Inlet Marina is closer
   and is the wrong basin for the ocean beach.
6. **MHX / AKQ boundary near Duck.** A careless forecast point can leave
   the MHX grid.
7. **KFFA and KMQI were not a safety net tonight** — the latest airport
   observations had no wind or temperature values.
8. **ID confusion between JMPN7 and JPRN7.**

## Open questions for Scout and Ed

1. Confirm the north edge: include Kitty Hawk and Kill Devil Hills, and
   stop before Duck? Or treat "Nags Head / Outer Banks" more broadly until
   the Duck / Corolla region is built, still labeling every Duck station
   as Duck?
2. Is Roanoke Island / Manteo in this region, as a sound-side footnote, or
   out?
3. Wind: show Duck Pier as the ocean-wind tile (labeled), Oregon Inlet
   Marina as harbor wind (labeled), and accept that Nags Head itself has
   no wind sensor? Or hide ocean wind when we have no local station?
4. Tide tile: can Phase 2 show 8652226 predictions at Jennette's Pier
   together with observed water level from Duck? The current saltwater
   tile uses one CO-OPS station for both.
5. Inshore water temp: hide it (no ocean-pier sensor), or show Oregon
   Inlet Marina with a strong "sound / inlet" label?
6. If 44086 is down, is "unavailable" for seas and swell preferred to a
   labeled 44095 seas-only backup?
7. Accept AMZ150 as the marine tile, with a caption that the official zone
   also covers Duck and north to Currituck Beach Light?
