# Region research: Topsail / Surf City

Phase 1 only — sources and coverage, no app-code changes.

Checked the morning of 14 Nov 2026, America/New_York (EST, UTC−5), around
**8:53–8:58 AM EST**. Official metadata: NDBC `station_table.txt`, NDBC
`activestations.xml` (created 8:50 AM EST), CO-OPS MDAPI (including tide
prediction offsets and products), and NWS `/points` plus `/zones/forecast`
for NCZ106, NCZ199, AMZ250, AMZ158, and the neighboring land zones.
Latest observations: NDBC `realtime2/{id}.txt` and `.spec` (45-day files,
used for cadence and gaps), CO-OPS Data API `date=latest` and official
high/low and 6-minute predictions, and NWS station observations for
nearby airfields. Distances use the same haversine as `conditions.py`
(`miles_bearing`, R = 3958.8 statute miles). Nothing here was invented or
interpolated.

## Anchor

**Ocean City, Fishing Pier (CO-OPS 8657419)**, 34.4517 N, 77.4950 W,
on Topsail Island.

This is the official CO-OPS position of the only ocean-pier tide-prediction
station on the island, published as "OCEAN CITY, FISHING PIER" / "Ocean
City Beach (fishing pier)," 34.4517 N, 77.4950 W, NOAA chart 11542. NWS
`/points` at that coordinate returns a relative location of **North
Topsail Beach**, 231 m (0.14 mi) at bearing 232°. It is a published NOAA
coordinate, not an unofficial pier pin — the same method as Bogue Inlet
(TEC2837) and Johnnie Mercer's Pier (8658163).

The pier sits just north of the ILM / MHX office split at Surf City. The
official AMZ250 / AMZ158 vertex (34.44101 N, 77.51729 W) is 1.5 mi
west-southwest and geocodes as Surf City. A land point in official zone
NCZ106 south of that split (34.42711 N, 77.54725 W) is 3.4 mi
west-southwest, also Surf City, and is the ILM grid already cited in
`docs/REGION_EMERALD_ISLE.md` (ILM 102, 86). The geographic mid-latitude
of official New River Inlet (8657167) and the official NWS shoreline
vertex at the south end of Topsail Beach (34.34832 N, 77.64777 W) is
34.4408 N, almost the same latitude as the office split; the pier is
about 0.75 mi north of that mid-latitude, on the North Topsail / MHX
side.

There is **no official NOAA station named Surf City, Topsail Beach, or
New Topsail Inlet.** If a later phase prefers a civic midpoint in Surf
City itself, the official NCZ106 land vertex above is the clean ILM land
forecast point, but it has no instrument.

The pier coordinate itself resolves to marine zone **AMZ158**. A land
forecast point must be slightly inland (see zones below).

## Coverage boundaries

Proposed region: **Topsail Island, from New River Inlet to New Topsail
Inlet** — North Topsail Beach, Surf City, and Topsail Beach — not the
Onslow mainland behind the island and not Figure Eight or Wrightsville.

- **Northeast end: New River Inlet.** Official CO-OPS 8657167 sits at
  34.5333 N, 77.3417 W, 10.4 mi east-northeast of the pier. NWS `/points`
  there returns MHX, Coastal Onslow (NCZ199), county Onslow (NCC133),
  relative to North Topsail Beach (201 m). This is the natural split with
  the earlier Emerald Isle research, which stopped at Hammocks Beach /
  Bear Inlet and left New River Inlet, Sneads Ferry, and North Topsail
  for this region. Do not extend this region past the inlet to Camp
  Lejeune, Jacksonville, or back to Bear Inlet.
- **Southwest end: New Topsail Inlet / the south end of Topsail Beach.**
  There is no official CO-OPS station at that inlet. An official NWS
  shoreline vertex of AMZ250 / NCZ106 (34.34832 N, 77.64777 W) geocodes
  as **Topsail Beach**, 0 m, office ILM, marine zone AMZ250, and is
  11.3 mi southwest of the pier. Inland of that shore, the official
  NCZ106 land vertex 34.37013 N, 77.62779 W is also Topsail Beach, 0 m,
  ILM grid 100, 83, land zone NCZ106. Lea-Hutaff Island, Rich Inlet, and
  Figure Eight Island lie farther southwest and are **not** in this
  region.
- **No overlap with Wilmington.** Ed's 14 Nov decision keeps Wilmington
  / Wrightsville at Masonboro Inlet to Mason Inlet, with Figure Eight
  Island out. Mason Inlet is south of Figure Eight, and Wrightsville's
  pier (8658163) is 23.4 mi southwest of this anchor. Stopping at New
  Topsail Inlet leaves a gap (Lea-Hutaff, Rich Inlet, Figure Eight)
  between the two regions.
- **No overlap with Emerald Isle.** Ed's 14 Nov Phase 2 default is the
  Town of Emerald Isle only, from Bogue Inlet to the east town line;
  even the Phase 1 west-edge proposal stopped at Bear Inlet, not New
  River Inlet. Bogue Inlet (TEC2837) is 26.3 mi east-northeast of this
  pier. The Onslow mainland between Bear Inlet and New River Inlet
  (Sneads Ferry, the New River, Camp Lejeune) is not Emerald Isle and is
  not automatically this island page either — see the open question on
  Sneads Ferry.
- **North / mainland:** Sneads Ferry (8657002) is 10.3 mi north-northeast
  on the **New River**, not the ocean beach. Hampstead (8657813) is
  14.3 mi west-southwest on the mainland ICWW / sound in Pender County.
  Holly Ridge has no official NOAA tide station and no ASOS/AWOS in the
  NWS lists checked this morning. Jacksonville and inland Onslow (NCZ198)
  are out.
- **Ocean:** The official marine zones change at Surf City. **AMZ158**
  (MHX), "S of Cape Lookout NC to Surf City NC out to 20 NM," covers the
  North Topsail / New River Inlet waters and is already the marine zone
  for Crystal Coast and Emerald Isle. **AMZ250** (ILM), "Coastal waters
  from Surf City to Cape Fear NC out 20 nm," covers the Surf City /
  Topsail Beach waters and is already Wilmington's marine zone. Both
  zones are wider than this island. Use the official zone (or zones) as
  the marine forecast, but do not let a zone name become the coverage
  claim.

## There is no Topsail stub in `data/regions.json`

Unlike Wilmington, Nags Head, and the disabled `atlantic-beach` entry,
there is no existing region id for Topsail or Surf City in the current
`data/regions.json`. This research does not add one.

## Proposed instruments

Labels must name the real place. A backup that is not in the same water
should not fill a tile silently — the same rule Ed applied at Emerald
Isle (no Swansboro curve, no Beaufort observed, no CLKN7 wind) and at
Wilmington (no Cape Fear River instruments as ocean conditions). Stations
that Crystal Coast, Emerald Isle, or Wilmington already use are marked
below; sharing them is discussed in the overlap section.

| Instrument | Primary | Backup | Distance | Latest obs (ET) | Cadence | Status |
|---|---|---|---|---|---|---|
| Wind (ocean-exposed) | **No station at the pier or anywhere on Topsail Island.** Proposed: 41064, Onslow Bay Outer (LEJ3), labeled "Onslow Bay Outer, ~35 mi offshore" | 41038, Wrightsville Beach Nearshore (ILM2), only with a "Wrightsville Beach Nearshore" label — it is Wilmington's nearshore buoy, 24.9 mi southwest, and it had a 5-day outage 6–11 Nov | 35.4 / 24.9 mi | 41064 8:08 AM EST, 10.0 m/s (19 kt) from 010°, gust 15.0 m/s; 41038 8:08 AM EST, 8.0 m/s (16 kt) from 350°, gust 11.0 m/s | 60 min both | Both active this morning. 41064 is already Crystal Coast's wind backup and Emerald Isle's labeled ocean wind; a 75-min stale window will trip unless `staleAfterMin` stays about 130, as those regions already do. 41038 is closer but is the wrong stretch of beach, is hourly, and is a shaky backup (see risks). Do not use JMPN7, MBNN7, CLKN7, or KNCA as an unlabeled island wind. |
| Seas | **41109 (New River Inlet, CDIP 190, 11.3 mi) would be the local waverider if it were alive; it is not reporting.** Proposed until it returns: 41159, Onslow Bay Outer (CDIP 217), labeled "Onslow Bay Outer, ~36 mi" | **No suitable source.** 41110 (Masonboro Inlet, CDIP 150) is 24.7 mi southwest and already a different sea state this morning | 35.6 mi | 41159 7:56 AM EST `.spec` and `.txt`, WVHT 1.4 m (4.6 ft), DPD 5 s, MWD 358° | 30 min | Active. This is also Crystal Coast's and Emerald Isle's only seas source. 41110 was 0.8 m (2.6 ft) from 059° at 8:30 AM EST — a different height and direction. |
| Swell | 41159 `.spec` | **No suitable automatic backup** | 35.6 mi | 7:56 AM EST, SwH 0.1 m (0.3 ft), SwP 10.5 s, SwD E; wind sea 1.4 m from N | 30 min | Active. Every `.spec` row has SwH. 41110 swell was also 0.1 m this morning; do not substitute on that coincidence, because the seas already disagreed. |
| Inshore water temp | **No suitable ocean-pier source.** 8657419 has no temperature product. Do not silently use 8658163 (Wrightsville Beach pier, 23.4 mi southwest) or 8656483 (Beaufort harbor) | — | — | — | — | There is no ocean-pier temperature sensor at North Topsail Beach, Surf City, or Topsail Beach. Wrightsville was 66.7 °F at 8:48 AM EST versus 70.2 °F at 41159 and 67.1 °F at 41110. Different water. Preferring "unavailable" matches Ed's Emerald Isle inshore-temp default. |
| Offshore / nearshore water temp | 41159, labeled "Onslow Bay Outer" | 41064, same site, labeled the same way | 35.6 / 35.4 mi | Both 21.2 °C (70.2 °F), 7:56 / 8:08 AM EST | 30 / 60 min | Active. Crystal Coast and Emerald Isle already use this same pair. 41110 / 41038 (19.5 / 19.6 °C this morning) are Wilmington's nearshore water, not a silent backup. |
| Air temp | **No suitable local source** of the KNJM kind (a labeled airfield a few miles away). The closest ASOS is KNCA, MCAS New River, 17.9 mi north, inland Onslow, and it is not usable this morning (see station details). KOAJ (Albert J. Ellis, Jacksonville) is 27.3 mi north-northwest and reporting, but it is an inland airport in NCZ198, not a beach reading. KILM is 26.4 mi west-southwest, also inland. There is no Holly Ridge ASOS/AWOS in the official NWS station lists | — | 17.9 / 27.3 / 26.4 mi | KNCA last report 6:56 PM EST 13 Nov, 10.6 °C (51 °F), 28004KT, 14 h stale; KOAJ 8:40 AM EST, 8 °C (46 °F), wind 9.3 km/h from 320°; KILM 8:25 AM EST, 8 °C (46 °F), wind 11.1 km/h from 330° | KNCA irregular (multi-day holes); KOAJ and KILM frequent this morning | If air is shown at all, it must be labeled with the real inland airport. Showing unavailable is consistent with not pretending an inland field is the beach. |
| Pressure | 41064, labeled "Onslow Bay Outer, ~35 mi offshore" | 41038, labeled "Wrightsville Beach Nearshore," or an inland ASOS altimeter with its real name | 35.4 / 24.9 mi | 41064 8:08 AM EST, 1015.6 mb; 41038 8:08 AM EST, 1014.7 mb. 41064's 45-day file still has no PTDY values, so a 3-hour trend should be hidden, not computed from the hourly PRES series (same rule as Emerald Isle) | 60 min | Active. |
| Harbor / inlet wind | **No suitable source.** There is no protected-harbor or inlet wind sensor at New River Inlet, Surf City, or New Topsail Inlet | — | — | — | — | KNCA is an inland airfield, not a harbor reading, and is stale this morning. 8657167 and 8657419 have no wind product. |
| Tide predictions | 8657419, Ocean City Fishing Pier (ocean / pier at North Topsail Beach), subordinate to 8654400 | 8657167, New River Inlet, is a second official ocean/inlet prediction station 10.4 mi east-northeast, also subordinate to 8654400, and is **not a silent substitute** (this morning's highs were already 13 minutes and 1.40 ft apart) | 0.0 / 10.4 mi | Predictions only at both; no live water level at either | Official highs and lows only; interval=6 is empty at both | 8657419 next official high 10:19 AM EST, 4.652 ft MLLW; 8657167 next official high 10:32 AM EST, 3.256 ft MLLW. Official offsets vs 8654400 Cape Hatteras Fishing Pier: at 8657419, high-tide height factor 1.40, low-tide 1.33, time offset +3 min high, −1 min low; at 8657167, height factors 0.98 / 0.83, time +16 / +17 min. 8654400 has no water-levels product, so there is no official live reference gauge — the same situation as TEC2837 at Emerald Isle. There is no official station named Surf City, Topsail Beach, or New Topsail Inlet. |
| Tide, 6-minute predicted curve at a different basin | **Do not use as the island ocean tide.** 8657002 Sneads Ferry, New River (harmonic, 10.3 mi NNE) and 8657813 Hampstead (harmonic, 14.3 mi WSW) both have 6-minute prediction curves and no observations | — | 10.3 / 14.3 mi | Predictions only | 6-min curve available at both | Sneads Ferry this morning had a later, much smaller high (12:39 PM EST, 0.97 ft) than the Ocean City pier (10:19 AM, 4.652 ft). Hampstead's high was 11:29 AM EST, 3.759 ft — closer in range, but it is a mainland ICWW / sound station, not the ocean beach. Using either curve silently would mix basins, the same error as using the Swansboro bridge curve at Bogue Inlet. |
| Tide, observed water level | **No local gauge.** 8658163 Wrightsville Beach is a different inlet, 23.4 mi southwest, and already Wilmington's observed tide | — | 23.4 mi | Wrightsville 8:48 AM EST, 4.308 ft MLLW, preliminary, flag `1,0,0,0` | 6 min | Active NWLON, but the wrong inlet. This morning's predicted highs were 4.652 ft at the Ocean City pier vs 4.28 ft at Wrightsville. If observed level is shown at all, it must be labeled "Wrightsville Beach." Preferring "unavailable" is consistent with Ed's Emerald Isle tide default and with not inventing a local residual from 8654400. |

Do **not** use as local Topsail seas, swell, or ocean water temperature:

- **41110** Masonboro Inlet (CDIP 150), 24.7 mi southwest, already Wilmington's seas buoy. Reporting (8:30 AM EST, WVHT 0.8 m, DPD 4 s, MWD 59°, WTMP 19.5 °C). Seas were already a different height and direction than 41159 (1.4 m from the north).
- **41109** New River Inlet (CDIP 190), 11.3 mi east-northeast. Would be the nearest nearshore waverider if it were alive, and the only one that is honestly local to this island. It is **not** in this morning's `activestations.xml`, and both `realtime2/41109.txt` and `.spec` return HTTP 404. No last observation is available from NDBC. The station table does not mark it disestablished, unlike 41035/41036. Mention it as the first-choice seas source **if it returns**, labeled "New River Inlet."
- **41035**, Onslow Bay Inner, 12.4 mi east of the pier, officially disestablished 22 Aug 2011 (recovered). **41036**, Onslow Bay Outer, officially disestablished 26 May 2015; 41064 / 41159 replaced it at that same outer site.
- **8658163** Wrightsville pier water (66.7 °F this morning) is not Onslow Bay surface water (70.2 °F at 41159).

## Station details

Locations are official NDBC, CO-OPS, or NWS positions. Distances in this
table are from 8657419 unless noted.

| ID | Official name / location | Water body | Feeds | Reporting? | Latest (ET) | Cadence | 45-day gaps |
|---|---|---|---|---|---|---|---|
| 8657419 | Ocean City, Fishing Pier. CO-OPS subordinate prediction station. 34.4517 N, 77.4950 W. NOAA chart 11542. A physical gauge was established 31 May 1973 and removed 8 Aug 1975; official high/low predictions continue | Ocean pier at North Topsail Beach, just north of the Surf City office split | Tide **predictions only** (official highs and lows), referenced to 8654400. Products: Tide Predictions, Superseded Benchmarks, Datums. **No water levels, wind, air, pressure, or water temperature** | Predictions exist; every `date=latest` observation product returned "No data was found" (water-level also rejected without a datum, as expected for a non-gauge) | Next official high 10:19 AM EST, 4.652 ft MLLW | Highs and lows only | Not an observation station. Interval=6 returns "No Predictions data was found." |
| 8657167 | New River Inlet. CO-OPS subordinate, referenced to 8654400. 34.5333 N, 77.3417 W | Inlet at the northeast end of North Topsail Beach, 10.4 mi ENE | Tide **predictions only** (highs and lows). Products: Tide Predictions. No 6-minute curve | Predictions exist; no observations | Next official high 10:32 AM EST, 3.256 ft MLLW | Highs and lows only | Interval=6 is empty. A second official ocean/inlet series for this region, not a copy of 8657419. |
| 8657002 | Sneads Ferry, New River. CO-OPS harmonic prediction station. 34.5763 N, 77.3954 W. A physical gauge was established 8 Dec 2021 and removed 11 Jun 2022; harmonics remain | New River, 10.3 mi NNE, not the ocean beach | Tide predictions, including a 6-minute curve, harmonics, datums, benchmarks. **No observations** | Predictions exist; every observation product was empty | Predicted high 12:39 PM EST, 0.97 ft MLLW | 6-min curve available | Different tidal basin. Do not treat the curve as New River Inlet or pier water. |
| 8657813 | Hampstead. CO-OPS harmonic prediction station. 34.3394 N, 77.7060 W. A physical gauge was established 15 Dec 2021 and removed 9 Jun 2022; harmonics remain. NOAA chart 11539 | Mainland ICWW / sound, Pender County, 14.3 mi WSW, not the ocean beach at Topsail Beach | Tide predictions, including a 6-minute curve, harmonics, datums, benchmarks. **No observations** | Predictions exist; every observation product was empty | Predicted high 11:29 AM EST, 3.759 ft MLLW | 6-min curve available | The nearest official "sound-side" harmonic station, but it is inland of the sound, not a Topsail Beach sound-side gauge. There is no official Topsail Beach sound-side station in the CO-OPS inventory. |
| 41109 | New River Inlet, NC (CDIP 190). Scripps waverider. 34.484 N, 77.300 W | Nearshore ocean, off New River Inlet, 11.3 mi ENE (NWS: 6.0 km / 3.7 mi east of North Topsail Beach, zone AMZ158) | Would be seas, swell, WTMP if alive | **No.** Not in `activestations`; realtime `.txt` and `.spec` HTTP 404 | — | — | Not a current source. The station table does not mark it disestablished. The hole that matters most for this region. |
| 41159 | Onslow Bay Outer, NC (CDIP 217). CORMP waverider. 34.211 N, 76.944 W | Offshore ocean, 35.6 mi ESE of the pier (31.6 mi SSE of Bogue Inlet; also Crystal Coast's seas buoy) | Seas (WVHT), swell (`.spec`), nearshore-offshore WTMP. **No wind** | Yes. In `activestations` (`met=y`) | `.spec` and `.txt` 7:56 AM EST, WVHT 1.4 m, SwH 0.1 m, WTMP 21.2 °C | 30 min | File from 8:26 PM EST 29 Sep. Longest gap 16.0 h, 5:26 PM 11 Oct–9:26 AM EST 12 Oct. Every `.txt` and `.spec` row has WVHT; every `.spec` row has SwH; every `.txt` row has WTMP. NDBC points met users to 41064. Already Crystal Coast's and Emerald Isle's only seas/swell source. |
| 41064 | Onslow Bay Outer, NC (LEJ3). CORMP moored buoy. 34.207 N, 76.949 W | Offshore ocean, same site as 41159, 35.4 mi ESE | Wind, pressure, air, WTMP | Yes (`met=y`, `waterquality=y`) | 8:08 AM EST, WSPD 10.0 m/s, WDIR 010°, GST 15.0 m/s, WTMP 21.2 °C, PRES 1015.6 mb, ATMP 11.1 °C | 60 min | File from 8:08 PM EST 29 Sep. Two gaps of 3.0 h (21 Oct and 13 Nov). **No WVHT** in 1,067 rows. `.spec` is 404. PTDY is still MM throughout. Already Crystal Coast's wind backup and Emerald Isle's labeled ocean wind. |
| 41110 | Masonboro Inlet, ILM2, NC (CDIP 150). CORMP waverider. 34.144 N, 77.715 W | Nearshore ocean, off Masonboro Inlet, 24.7 mi SSW | Seas (WVHT), swell (`.spec`), nearshore WTMP and air. **No wind** | Yes (`met=y`) | `.spec` and `.txt` 8:30 AM EST, WVHT 0.8 m, DPD 4 s, MWD 59°, SwH 0.1 m from ENE, WTMP 19.5 °C, ATMP 10.0 °C | 30 min | File from 8:00 PM EST 29 Sep. One gap of 2.5 h, 4:00–6:30 PM EST 21 Oct. Every `.txt` and `.spec` row has WVHT; every `.spec` row has SwH. Already Wilmington's seas/swell source. Different sea state and water temperature than 41159 this morning. |
| 41038 | Wrightsville Beach Nearshore, NC (ILM2). CORMP moored buoy. 34.141 N, 77.715 W | Nearshore ocean, same site as 41110, 24.9 mi SSW | Wind, pressure, air, WTMP | Yes this morning (`met=y`, `waterquality=y`) | 8:08 AM EST, WSPD 8.0 m/s from 350°, GST 11.0 m/s, WTMP 19.6 °C, PRES 1014.7 mb, ATMP 9.8 °C | 60 min | File from 8:08 PM EST 29 Sep. 13-hour gap 11:08 PM 31 Oct–11:08 AM EST 1 Nov, and a **117-hour (4.9-day) outage from 12:08 PM EST 6 Nov to 9:08 AM EST 11 Nov**. **No WVHT.** `.spec` is 404. Already discussed in the Wilmington research as a shaky backup. |
| 41037 | Wrightsville Beach Offshore, NC (ILM3). CORMP. 33.988 N, 77.362 W | Offshore ocean, 32.9 mi SSE | Met only, when alive | **No.** In `activestations` with `met=n`. Last report 6:08 PM EST, 10 Oct 2026 | — | Was 60 min | Unusable. No WVHT in the file. Same stale buoy noted in the Wilmington stub and Phase 1 doc. |
| 8658163 / JMPN7 | Wrightsville Beach, NC. CO-OPS NWLON at Johnnie Mercer's Pier. 34.2133 N, 77.7867 W | Ocean pier at Wrightsville Beach, 23.4 mi SW | Wind, inshore WTMP, air, pressure, observed WL, tide predictions | Yes | CO-OPS 8:48 AM EST, wind 8.16 from 334° NNW gust 11.47 (English units as published), air 48.2 °F, WTMP 66.7 °F, pressure 1016.3 mb, WL 4.308 ft MLLW flag `1,0,0,0`. NDBC met 8:18 AM EST, 4.1 m/s from 350°, WTMP 19.2 °C | 6 min | Already Wilmington's local pier. Too far, and the wrong inlet, to be an unlabeled Topsail source. |
| MBNN7 | Masonboro Island, north end. CORMP C-MAN. 34.171 N, 77.824 W | Island / inlet, 27.0 mi SW | Wind, air, pressure. **No WTMP, no waves** | Yes | 8:00 AM EST, 3.1 m/s from 350° | 6 min | Wilmington's island wind backup. Not local here. |
| 8654400 | Cape Hatteras Fishing Pier. CO-OPS harmonic / historical station. 35.2233 N, 75.635 W | Ocean, Hatteras Island, far northeast of this region | Tide predictions and harmonics. **No water-levels product** | Not a live gauge | — | — | Published reference for 8657419, 8657167, and TEC2837. Cannot supply observed water level for Topsail or New River Inlet. (Position and product status as documented in `docs/REGION_EMERALD_ISLE.md`; not re-fetched this morning.) |
| KNCA | MCAS New River. NWS / ASOS. 34.70627 N, 77.44066 W | Inland airfield at Camp Lejeune, 17.9 mi N, county Onslow, forecast zone **NCZ198 Inland Onslow** (MHX) | Wind, air, altimeter (METAR) | **Stale this morning.** Latest 6:56 PM EST 13 Nov, 10.6 °C, 28004KT, 7 SM, A2972 | 6:56 PM EST 13 Nov | Irregular; this morning's recent set of 13 reports ran from Mon 7:56 AM through Fri 6:56 PM and included holes of 39 h and 46 h | Closest official airfield, but not the beach, not a regular hourly station, and currently unusable. |
| KOAJ | Jacksonville, Albert J. Ellis Airport. NWS / ASOS. 34.83333 N, 77.61667 W | Inland Onslow airport, 27.3 mi NNW, forecast zone NCZ198 | Wind, air, altimeter | Yes this morning | 8:40 AM EST, 8 °C, wind 9.3 km/h from 320° | Frequent in this morning's recent window (median 5 min, no gap ≥ 90 min in the last 40 reports) | A reliable inland airport, not a beach reading. |
| KILM | Wilmington International Airport. NWS / ASOS. 34.26681 N, 77.89987 W | Inland New Hanover, 26.4 mi WSW, forecast zone NCZ107 Inland New Hanover (ILM) | Wind, air, altimeter | Yes | 8:25 AM EST, 8 °C, wind 11.1 km/h from 330° | Frequent this morning (median 5 min in the last 40 reports) | Already the kind of inland airport Wilmington's research declined to use as a beach air-temp primary. |
| KNJM | Bogue Field Marine Corps Auxiliary Field. 34.69403 N, 77.02945 W | Sound-side airfield, 31.3 mi ENE, already Emerald Isle's labeled air temp | Wind, air, altimeter | Yes, but 127 min old at 8:58 AM | 6:51 AM EST, 3.9 °C, 32005KT | Typically ~60 min, irregular (same 2–4 h gaps documented this morning in the Emerald Isle amendment) | Too far, and it belongs to the Emerald Isle page. Not a Topsail source. |
| KACZ | Henderson Field Airport. 34.71786 N, 78.00389 W | Inland Pender / vicinity, 34.3 mi WNW, forecast zone NCZ105 Inland Pender | Airport wind and air | Not fetched live (too far inland); listed because it appears in the official NCZ106 observation-station list | — | — | Not a beach reading. No Holly Ridge station appears in that list, or in the NWS observation-station lists returned for the pier and the Surf City land point. Other listed fields (KSUT, KNKT, KMRH) are farther still. |

## NWS office, forecast point, and zones

**This island is split between two NWS offices at Surf City.** That is
not a rounding artifact. Official NWS zone vertices a few hundred feet
apart return different offices, different land zones, different counties,
and different marine zones, and both geocode as Surf City.

- The official AMZ250 / AMZ158 split vertex, **34.44101 N, 77.51729 W**,
  is the north end of AMZ250 and sits on the south edge of AMZ158. NWS
  `/points` returns **MHX grid 31, 42**, forecast zone **NCZ199 Coastal
  Onslow**, county Onslow (NCC133), office MHX, relative location **Surf
  City**, 0.5 m.
- A second official vertex, **34.44041 N, 77.51825 W**, is the south end
  of NCZ199 and is also an AMZ250 vertex. `/points` returns **ILM grid
  103, 86**, forecast zone **NCZ106 Coastal Pender**, county Pender
  (NCC141), office ILM, relative location **Surf City**, 0 m.

Checked this morning, from northeast to southwest, all of them official
CO-OPS or NDBC coordinates or official NWS zone vertices:

| Point (official source) | Office | Grid | Land / marine zone | County | NWS relative city |
|---|---|---|---|---|---|
| 8657002 Sneads Ferry, 34.5763 N, 77.3954 W | MHX | 35, 49 | NCZ199 | Onslow | Sneads Ferry, 0 m |
| 8657167 New River Inlet, 34.5333 N, 77.3417 W | MHX | 37, 47 | NCZ199 | Onslow | North Topsail Beach, 201 m |
| NCZ199 land vertex, 34.50017 N, 77.40154 W | MHX | 35, 46 | NCZ199 | Onslow | North Topsail Beach, 0 m |
| 41109, 34.484 N, 77.300 W | MHX | 39, 45 | AMZ158 | — | North Topsail Beach, 6.0 km E |
| 8657419 Ocean City Fishing Pier, 34.4517 N, 77.4950 W | MHX | 32, 43 | AMZ158 | — | North Topsail Beach, 231 m |
| AMZ250 / AMZ158 split, 34.44101 N, 77.51729 W | MHX | 31, 42 | NCZ199 | Onslow | Surf City, 0.5 m |
| NCZ199 south / AMZ250 vertex, 34.44041 N, 77.51825 W | ILM | 103, 86 | NCZ106 | Pender | Surf City, 0 m |
| NCZ106 island land vertex, 34.42711 N, 77.54725 W | ILM | 102, 86 | NCZ106 | Pender | Surf City, 0 m |
| NCZ106 Topsail Beach land vertex, 34.37013 N, 77.62779 W | ILM | 100, 83 | NCZ106 | Pender | Topsail Beach, 0 m |
| South-island AMZ250 / NCZ106 shoreline vertex, 34.34832 N, 77.64777 W | ILM | 99, 82 | AMZ250 | — | Topsail Beach, 0 m |
| 8657813 Hampstead, 34.3394 N, 77.7060 W | ILM | 97, 81 | NCZ106 | Pender | Hampstead, 0 m |
| 8658163 Wrightsville pier, 34.2133 N, 77.7867 W | ILM | 95, 75 | AMZ250 | — | Wrightsville Beach, 0 m |

Zone metadata, confirmed from `/zones/forecast`:

- **NCZ199 Coastal Onslow**, CWA MHX. Official polygon lat 34.44041–
  34.78473 N, lon 77.57632–77.09842 W. This is the land zone for North
  Topsail Beach, New River Inlet, and Sneads Ferry. It is also the zone
  Emerald Isle left out of alerts until Swansboro is added.
- **NCZ106 Coastal Pender**, CWA ILM. Official polygon lat 34.28545–
  34.47323 N, lon 77.76337–77.51825 W. This is the land zone for the
  Pender part of Surf City, Topsail Beach, and the Pender mainland
  (Hampstead). It is the zone Wilmington's alerts correctly omitted.
- **AMZ158**, official name "S of Cape Lookout NC to Surf City NC out to
  20 NM", CWA MHX.
- **AMZ250**, official name "Coastal waters from Surf City to Cape Fear
  NC out 20 nm", CWA ILM.

**Land forecast points** have to be slightly inland of the pier and of
the south-end shoreline, which both fall in a marine zone — the same
pattern as Bogue Inlet and Johnnie Mercer's Pier.

- North Topsail / MHX: the official NCZ199 land vertex **34.50017 N,
  77.40154 W** returns MHX grid **35, 46**, NCZ199, North Topsail Beach,
  0 m. New River Inlet itself (MHX 37, 47) is also a valid NCZ199 point.
- Surf City / ILM: the official NCZ106 land vertex **34.42711 N,
  77.54725 W** returns ILM grid **102, 86**, NCZ106, Surf City, 0 m.
- Topsail Beach / ILM: **34.37013 N, 77.62779 W** returns ILM grid
  **100, 83**, NCZ106, Topsail Beach, 0 m.

A single-grid forecast cannot represent the whole island. One region that
covers New River Inlet through New Topsail Inlet would need **two land
forecast points and two marine zones**, in the same spirit as the
Hatteras marine tile that already shows AMZ154 and AMZ152, but here the
split is the land office as well. The alternative is two pages (North
Topsail vs Surf City / Topsail Beach). That is an open question, not a
Phase 1 default.

**Alert zones (proposed), if this is one island region:** `AMZ158`,
`AMZ250`, `NCZ199`, and `NCZ106`. Do **not** add `NCZ108` (Coastal New
Hanover — Wilmington / Wrightsville), `NCZ195` (West Carteret — Emerald
Isle / Crystal Coast), `NCZ198` (Inland Onslow — Camp Lejeune /
Jacksonville), `NCZ107` (Inland New Hanover), `NCZ105` (Inland Pender),
or `AMZ156`.

**Marine tile:** if the region includes both sides of Surf City, both
official zones belong on the tile, each with a short caption that the
zone is wider than the town and that the office split is at Surf City.
Showing only AMZ158 would omit Topsail Beach; showing only AMZ250 would
omit North Topsail and New River Inlet.

## Overlap with Emerald Isle, Crystal Coast, and Wilmington

Emerald Isle (private preview, town only, MHX, AMZ158 + NCZ195) is live
in the local tree and is 26.3 mi east-northeast at Bogue Inlet. Crystal
Coast (public, anchored at Beaufort Inlet) is farther east and already
shares 41159, 41064, and AMZ158 with Emerald Isle. Wilmington / Wrightsville
(private preview, ILM, AMZ250 + NCZ108) is 23.4 mi southwest.

| Shared source | Role elsewhere | Distance from 8657419 | Use here? |
|---|---|---|---|
| 41159 | Only seas, swell, and primary offshore temp for Crystal Coast and Emerald Isle | 35.6 mi ESE | The only active WVHT source in reach while 41109 is dead. It is a regional offshore buoy, ~36 miles out, not a Topsail reading. Must be labeled "Onslow Bay Outer." Reusing it means **three** dashboards would share Crystal Coast's only seas buoy; if 41159 is down, all three go unavailable (41109 is dead; 41110 is the wrong water). |
| 41064 | Crystal Coast wind backup; Emerald Isle labeled ocean wind, air was deliberately not used there | 35.4 mi ESE | Honest as a **labeled** "Onslow Bay Outer" wind / pressure / offshore-temp source. Same hourly stale-window issue already handled for Emerald Isle. Not a beach reading. |
| AMZ158 | Marine forecast for Crystal Coast and Emerald Isle | Official zone for the North Topsail / New River Inlet waters | Correct official zone for that half of the island, and a three-way duplicate marine tile unless each page captions that the zone runs from Cape Lookout to Surf City. |
| NCZ199 | Left out of Emerald Isle alerts until Swansboro is added | Official land zone for North Topsail and Sneads Ferry | Correct for the Onslow half of this island. Adding it here does not require adding it to Emerald Isle. |
| 41110 / 41038 | Wilmington seas (41110) and nearshore wind/temp (41038) | 24.7 / 24.9 mi SSW | Different sea state and water temperature this morning. Labeled last-resort at most; not a silent backup. 41038 also has the 6–11 Nov outage. |
| 8658163 / JMPN7 | Wilmington local pier (wind, inshore temp, air, pressure, observed tide) | 23.4 mi SW | Wrightsville Beach, not Topsail. Do not reuse silently. |
| AMZ250 | Wilmington marine forecast | Official zone for the Surf City / Topsail Beach waters | Correct official zone for that half of the island, already wider than Wrightsville and wider than Topsail Beach. Needs a caption, same as Wilmington's `zoneNote`. |
| NCZ106 | Omitted from Wilmington alerts (Coastal Pender / Topsail) | Official land zone for Surf City (Pender) and Topsail Beach | Correct for the Pender half of this island. |
| TEC2837, KNJM, 8656613, CLKN7, 8656483 | Emerald Isle / Crystal Coast locals | 26–32+ mi ENE | Wrong island, wrong inlet, or sound-side airfield for a different town. Do not reuse. |
| 41037 | Mentioned in the old Wilmington stub | 32.9 mi SSE | Still dead since 10 Oct 2026. Do not wire. |

**Verdict: a whole-island Topsail page would not just be a second
Emerald Isle page or a second Wilmington page, but it would share
Crystal Coast's ocean buoy and would sit on the official office split
that those two regions were carefully kept on opposite sides of.** The
honest local additions are the Ocean City pier and New River Inlet tide
predictions, a North Topsail forecast point (MHX) and a Surf City /
Topsail Beach forecast point (ILM), Coastal Onslow and Coastal Pender
alerts, and both marine zones with captions. Wind, seas, swell, inshore
temperature, observed water level, and beach air are not locally
instrumented while 41109 is down. A clone that reused 41110, 8658163,
or Beaufort / Cape Lookout without labels would be misleading: those
stations are 23–35 miles away, on a different beach or a different inlet,
and this morning they already disagreed with the Onslow Bay Outer series.

## Risks

1. **The ILM / MHX split is inside the proposed coverage, at Surf City.**
   One page that runs from New River Inlet to New Topsail Inlet spans two
   offices, two land zones, two counties, and two marine zones. A single
   forecast grid or a single marine tile would quietly drop half the
   island. This is a harder split than Hatteras's two marine zones,
   because the land office changes too.
2. **No instrument at the beach itself** except official high/low tide
   predictions at the Ocean City pier (and, at the inlet, at 8657167).
   Wind, seas, swell, inshore ocean temperature, observed water level,
   and beach air all have to come from somewhere else and be labeled, or
   show as unavailable.
3. **41109 is a hole in the nearshore wave network**, and for this region
   it is the hole that hurts most. At 11.3 mi it would be the only
   honestly local seas candidate. Until it returns, the only active WVHT
   source is 41159, ~36 miles offshore, already the only seas buoy for
   two other regions.
4. **8657419 and 8657167 have no 6-minute curve and no official live
   reference gauge.** Both are subordinate to 8654400, which has no
   water-levels product — the same constraint Ed accepted at Emerald
   Isle for TEC2837. Applying official offsets to invent a 6-minute
   curve would be derived data; do not do that. Using the Sneads Ferry
   or Hampstead 6-minute curves silently would mix basins (this
   morning's highs were hours and feet apart). Using Wrightsville
   observed water level would use the wrong inlet.
5. **The two official ocean/inlet tide stations already disagree.** This
   morning's highs were 10:19 AM, 4.652 ft at the pier vs 10:32 AM,
   3.256 ft at New River Inlet. A single unlabeled "Topsail tide" tile
   cannot honestly be both.
6. **41064 is a distant, hourly wind primary**, 35 miles offshore, and
   already labeled as such on the Emerald Isle preview. 41038 is closer
   but belongs to Wilmington, had a 5-day outage this month, and is also
   hourly.
7. **AMZ158, AMZ250, NCZ199, and NCZ106 are all wider than any one
   town.** Alerts and marine forecasts will also apply to neighboring
   shores (for AMZ158, toward Cape Lookout and Emerald Isle; for AMZ250,
   toward Wrightsville and Cape Fear; for NCZ199, to Sneads Ferry and
   the rest of Coastal Onslow; for NCZ106, to the Pender mainland).
8. **No close, reliable airfield reading.** KNCA is the closest official
   ASOS and is stale, irregular, and inland. KOAJ and KILM are regular
   this morning but ~26–27 miles inland. There is no Holly Ridge station.
9. **8657419 is on the MHX / North Topsail side of the split.** Using it
   as the island anchor is honest about the NOAA instrument and slightly
   off-center for Surf City and Topsail Beach. A Surf City land anchor
   would be closer to the civic midpoint and would have no official tide
   station.

## Open questions for Scout and Ed

1. Confirm the coverage: the whole island, New River Inlet to New
   Topsail Inlet (North Topsail Beach, Surf City, and Topsail Beach)?
   Island only, or also Sneads Ferry on the New River and/or the Pender
   mainland (Hampstead, Holly Ridge)?
2. The office split at Surf City: one region with two land forecast
   points and two marine zones, each captioned, or two pages (North
   Topsail / MHX vs Surf City–Topsail Beach / ILM)?
3. Anchor: official 8657419 at the Ocean City Fishing Pier (North
   Topsail, MHX side, the only ocean-pier tide station), or a Surf City
   land point with no instrument (for example the official NCZ106 vertex
   at ILM 102, 86)?
4. Tide tile: can a later phase show 8657419 official highs and lows
   with no 6-minute curve and no local observed water level, as Ed did
   at Emerald Isle? Should 8657167 appear as a second, labeled inlet
   series? Are the Sneads Ferry or Hampstead curves, or Wrightsville
   observed level, acceptable if clearly labeled, given that 8654400 is
   not a live reference?
5. Wind: show 41064 as the ocean-wind tile (labeled Onslow Bay Outer,
   ~35 mi), and accept that the island has no wind sensor? Offer 41038
   as a labeled Wrightsville Nearshore backup despite the November
   outage? Or hide ocean wind when there is no local station?
6. Seas: accept sharing 41159 (~36 mi) with Crystal Coast and Emerald
   Isle, with a label and with no automatic backup while 41109 is dead?
   Never silently use 41110?
7. Inshore water temperature and air temperature: show both as
   unavailable (no pier sensor; no close reliable airfield), rather than
   a Wrightsville pier temperature or an inland ASOS?
8. What happens if 41109 returns — promote it to the labeled primary
   seas/swell/nearshore-temp source for this region, and leave 41159 as
   a labeled offshore backup?

