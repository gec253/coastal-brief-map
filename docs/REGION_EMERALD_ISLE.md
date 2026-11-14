# Region research: Emerald Isle / Swansboro

Phase 1 only — sources and coverage, no app-code changes.

Checked the morning of 14 Nov 2026, America/New_York (EST, UTC−5), around
**8:10–8:20 AM EST**. Official metadata: NDBC `station_table.txt`, NDBC
`activestations.xml` (created 8:10 AM EST), CO-OPS MDAPI (including tide
prediction offsets), and NWS `/points` and `/zones/forecast`. Latest
observations: NDBC `realtime2/{id}.txt` and `.spec` (45-day files, used for
cadence and gaps), CO-OPS Data API `date=latest`, and NWS station
observations for nearby airfields. Distances use the same haversine as
`conditions.py` (`miles_bearing`, R = 3958.8 statute miles). Nothing here
was invented or interpolated.

## Anchor

**Bogue Inlet, Emerald Isle**, 34.650 N, 77.100 W.

This is the official CO-OPS position of tide-prediction station **TEC2837**,
published as "Bogue Inlet," 34.650 N, 77.100 W (34°39'00" N, 77°06'00" W).
The inlet is the right local landmark: it is the west end of Emerald Isle,
on the ocean, and it is the natural split between Emerald Isle (Carteret
County, land zone NCZ195) and Hammocks Beach / Swansboro (Onslow County,
land zone NCZ199). NOAA already publishes a tide station at this inlet.

The fishing pier at the west end of Emerald Isle sits at this same inlet.
This research uses NOAA's published inlet coordinates as the anchor, not an
unofficial pier pin.

The inlet coordinate itself resolves to marine zone AMZ158. The land
forecast point must be slightly inland (see zones below).

## Coverage boundaries

Proposed region: **Emerald Isle and the Bogue Inlet / Swansboro side**, not
all of Bogue Banks and not the later Topsail region.

- **East end: the Town of Emerald Isle, before Indian Beach and Pine Knoll
  Shores.** Atlantic Beach is 20.7 mi east of this anchor and only 2.5 mi
  west of Crystal Coast's Beaufort Inlet anchor. Pine Knoll Shores and
  Indian Beach sit on that same eastern half of the island, in the same
  land zone (NCZ195) but much closer to Beaufort Inlet and Morehead City.
  They belong with Crystal Coast, or with the existing disabled
  `atlantic-beach` stub, not here.
- **West end: Hammocks Beach / Bear Inlet, not New River Inlet.** New River
  Inlet (8657167) is 15.9 mi west-southwest, and Sneads Ferry / North
  Topsail are the later "Topsail Beach / Surf City" region on the roadmap.
  Do not extend this region to North Topsail or Surf City.
- **North:** Swansboro, Cedar Point, and Cape Carteret on the mainland
  side of Bogue Sound and the White Oak River. Jacksonville and inland
  Onslow are out.
- **Ocean:** The official marine zone, AMZ158, runs from Cape Lookout to
  Surf City and is therefore wider than this region (it is also Crystal
  Coast's marine zone). Use it as the marine forecast, but do not let that
  zone name become the coverage claim.
- **The MHX / ILM office split is at Surf City, not here.** Every
  Emerald Isle, Swansboro, Hammocks Beach, Sneads Ferry, and North Topsail
  point checked this morning returned **NWS Newport / Morehead City (MHX)**.
  Surf City returned **NWS Wilmington (ILM)**, grid ILM 102, 86, land zone
  **NCZ106 Coastal Pender**, marine AMZ250. That is the later Topsail /
  Surf City region, not this one.

## The disabled `atlantic-beach` stub in `data/regions.json`

The current entry is a stub only: `enabled: false`, name "Atlantic Beach ·
Emerald Isle", area "Bogue Banks", status "planned: needs a verified Bogue
Inlet tide station and nearshore wind source". It has no station wiring, no
anchor, and no zones.

This morning's check, against that note:

- A verified Bogue Inlet tide station exists: **TEC2837**, official highs
  and lows only. It has **no live water-level gauge** and **no 6-minute
  prediction curve**. Its published reference is 8654400 Cape Hatteras
  Fishing Pier, 91.9 mi east-northeast, which itself has no water-levels
  product.
- There is **no nearshore ocean wind sensor** at Emerald Isle or Bogue
  Inlet. The closest official wind reading is **KNJM**, Bogue Field Marine
  Corps Auxiliary Field, 5.0 mi northeast, on the sound side. The closest
  ocean wind buoy is **41064**, 31.8 mi south-southeast, already Crystal
  Coast's wind backup, and it is hourly.
- The stub treats Atlantic Beach and Emerald Isle as one Bogue Banks
  region. The two ends of the island are 21 miles apart and already have
  different nearest instruments (Beaufort / Cape Lookout at the east end;
  Bogue Inlet predictions and, at a distance, the Onslow Bay buoy at the
  west end). This research treats them as separate.

## Proposed instruments

Labels must name the real place. A backup that is not in the same water
should not fill a tile silently. Stations that Crystal Coast already uses
are marked below; sharing them is discussed in the overlap section.

| Instrument | Primary | Backup | Distance | Latest obs (ET) | Cadence | Status |
|---|---|---|---|---|---|---|
| Wind (ocean-exposed) | **No station at Emerald Isle or Bogue Inlet.** Proposed: 41064, Onslow Bay Outer (LEJ3), labeled "Onslow Bay Outer" | CLKN7, Cape Lookout, only with a "Cape Lookout" label — it is Crystal Coast's primary, 32.6 mi east | 31.8 / 32.6 mi | 41064 7:08 AM EST, 11.0 m/s (21 kt) from 020°, gust 15.0 m/s; CLKN7 7:30 AM EST, 6.2 m/s (12 kt) from 340°, gust 8.8 m/s | 60 min / 10 min | Both active. They already disagreed this morning (21 kt offshore vs 12 kt at the cape). 41064 is hourly; a 75-min wind stale window will trip unless `staleAfterMin` is about 130, as Crystal Coast already does for this buoy. |
| Wind, sound-side (optional / closer) | KNJM, Bogue Field Marine Corps Auxiliary Field, labeled "Bogue Field (sound side)" | — | 5.0 mi | 6:51 AM EST, AUTO METAR 32005KT (5 kt from 320°), 3.9 °C (39 °F) | ~60 min, irregular | Active this morning (ASOS AUTO). Not in the NWS observation-station list for the Emerald Isle grid. Missing hours appear in the recent set (for example 5:51–6:51 PM EST 13 Nov). This is a sound-side airfield, not the ocean beach; this morning it was 5 kt when 41064 was 21 kt. |
| Seas | 41159, Onslow Bay Outer (CDIP 217), labeled "Onslow Bay Outer" | **No suitable source.** 41109 (New River Inlet, CDIP 190, 16.2 mi) is not reporting. 41110 (Masonboro Inlet) is 49.5 mi southwest and already a different sea state | 31.6 mi | 7:56 AM EST `.spec` and `.txt`, WVHT 1.4 m (4.6 ft), DPD 5 s, MWD 358° | 30 min | Active and generally reliable. This is also Crystal Coast's only seas source. |
| Swell | 41159 `.spec` | **No suitable automatic backup** | 31.6 mi | 7:56 AM EST, SwH 0.1 m (0.3 ft), SwP 10.5 s, SwD E; wind sea 1.4 m | 30 min | Active. Every `.spec` row has SwH. 41110 swell was also 0.1 m this morning but seas were 0.8 m vs 1.4 m here; do not substitute. |
| Inshore water temp | **No suitable ocean-pier source.** Do not silently use 8656483 (Beaufort harbor, 24.8 mi east) | — | — | — | — | There is no ocean-pier temperature sensor at Emerald Isle, Bogue Inlet, or Swansboro. Beaufort was 63.0 °F at 8:12 AM EST versus 70.2 °F at 41159. Different water. |
| Offshore / nearshore water temp | 41159, labeled "Onslow Bay Outer" | 41064, same site, labeled the same way | 31.6 / 31.8 mi | Both 21.2 °C (70.2 °F), 7:56 / 7:08 AM EST | 30 / 60 min | Active. Crystal Coast already uses this same pair. |
| Air temp | KNJM, labeled "Bogue Field (sound side)", if air is shown from an airport at all | 8656483 / KMRH at Beaufort, labeled "Beaufort", 24.8 / 25.8 mi east | 5.0 / 24.8 mi | KNJM 6:51 AM EST, 3.9 °C (39 °F); Beaufort CO-OPS 8:12 AM EST, 46.6 °F; KMRH 7:55 AM EST, 8 °C (46 °F) | ~60 / 6 / ~60 min | KNJM is much closer but sound-side and cooler than the Beaufort airport this morning. KILM-style caution: an airfield reading is not a beach reading. |
| Pressure | 41064, labeled "Onslow Bay Outer", or KNJM altimeter with a sound-side label | 8656483 / CLKN7, labeled Beaufort / Cape Lookout | 31.8 / 5.0 mi | 41064 7:08 AM EST, 1014.4 mb; Beaufort 8:12 AM EST, 1014.7 mb | 60 / 6 min | Active. |
| Harbor / inlet wind | **No protected-harbor sensor at Bogue Inlet.** KNJM is the closest sound-side wind, 5.0 mi, and must be labeled "Bogue Field (sound side)" | 8656483 is Crystal Coast's harbor wind at Beaufort, 24.8 mi east | 5.0 / 24.8 mi | KNJM 5 kt at 6:51 AM EST; Beaufort 6.03 mph N, gust 11.47, at 8:12 AM EST (CO-OPS English units) | ~60 / 6 min | 8656613 Swansboro has no wind product. |
| Tide predictions | TEC2837, Bogue Inlet (ocean / inlet), subordinate to 8654400 | 8656613, Swansboro, East Corbett Ave. Bridge, is a **different tidal basin** (White Oak River / sound), 2.7 mi north | 0.0 / 2.7 mi | Predictions only at both; no live water level at either | Official highs and lows at TEC2837; 6-min curve at 8656613 only | TEC2837 highs and lows exist (next high 10:29 AM EST, 2.425 ft MLLW). Interval=6 returns "No Predictions data was found." Official offsets vs 8654400 Cape Hatteras Fishing Pier: high-tide height factor 0.73, low-tide 0.83; time offset +13 min high, +15 min low. 8654400 has no water-levels product, so there is no official live reference gauge. Swansboro this morning had a later, lower high (12:20 PM EST, 1.968 ft) than Bogue Inlet (10:29 AM, 2.425 ft). Do not use the Swansboro curve as a silent stand-in for the inlet. |
| Tide, observed water level | **No local gauge.** 8656483 Beaufort, Duke Marine Lab, is a different inlet, 24.8 mi east, and already Crystal Coast's observed tide | — | 24.8 mi | Beaufort 8:12 AM EST, 3.301 ft MLLW, preliminary, flag `1,0,0,0` | 6 min | Active NWLON, but the wrong inlet. This morning's predicted highs were 2.425 ft at Bogue Inlet vs 3.466 ft at Beaufort. If observed level is shown at all, it must be labeled "Beaufort, Duke Marine Lab." Preferring "unavailable" is consistent with not inventing a local residual. |

Do **not** use as local Emerald Isle seas, swell, or ocean water temperature:

- **41110** Masonboro Inlet (CDIP 150), 49.5 mi southwest, already Wilmington's seas buoy. Reporting (8:00 AM EST, WVHT 0.8 m, DPD 4 s, MWD 61°, WTMP 19.5 °C). Seas were already a different height and direction than 41159 (1.4 m from the north).
- **41109** New River Inlet (CDIP 190), 16.2 mi southwest. Would be the nearest nearshore waverider if it were alive. It is **not** in this morning's `activestations.xml`, and both `realtime2/41109.txt` and `.spec` return HTTP 404. No last observation is available from NDBC. Mention it only as a possible later Topsail / New River source if it returns, labeled "New River Inlet."
- **41035 / 41036**, historical Onslow Bay buoys, officially disestablished (2011 and 2015). 41064 / 41159 replaced 41036 at the same site.
- **8656483** Beaufort harbor water (63.0 °F this morning) is not Onslow Bay surface water (70.2 °F at 41159).

## Station details

Locations are official NDBC, CO-OPS, or NWS positions.

| ID | Official name / location | Water body | Feeds | Reporting? | Latest (ET) | Cadence | 45-day gaps |
|---|---|---|---|---|---|---|---|
| TEC2837 | Bogue Inlet. CO-OPS subordinate prediction station. 34.650 N, 77.100 W | Ocean / inlet, west end of Emerald Isle | Tide **predictions only** (official highs and lows), referenced to 8654400 | Predictions exist; no observations; no 6-minute curve | Next official high 10:29 AM EST, 2.425 ft MLLW | Highs and lows only | Not an observation station. Interval=6 is empty. |
| 8656613 | Swansboro, East Corbett Ave. Bridge. CO-OPS harmonic prediction station. 34.6866 N, 77.1181 W | White Oak River / sound, at the highway bridge, not the ocean beach | Tide predictions, including a 6-minute curve, harmonics, datums. **No water levels, wind, air, pressure, or water temperature** | Predictions exist; every `date=latest` observation product returned "No data was found" | Predicted high 12:20 PM EST, 1.968 ft MLLW | 6-min curve available | Not an observation station. Do not treat the curve as Bogue Inlet water. |
| 41159 | Onslow Bay Outer, NC (CDIP 217). CORMP waverider. 34.211 N, 76.944 W | Offshore ocean, 31.6 mi SSE of Bogue Inlet (37.0 mi SSW of Beaufort Inlet) | Seas (WVHT), swell (`.spec`), nearshore-offshore WTMP. **No wind** | Yes. In `activestations` (`met=y`) | `.spec` and `.txt` 7:56 AM EST, WVHT 1.4 m, SwH 0.1 m, WTMP 21.2 °C | 30 min | Five gaps; longest 16.0 h, 5:26 PM 11 Oct–9:26 AM EDT 12 Oct. Every `.txt` and `.spec` row has WVHT; every `.spec` row has SwH; every `.txt` row has WTMP. NDBC points met users to 41064. Already Crystal Coast's only seas/swell source. |
| 41064 | Onslow Bay Outer, NC (LEJ3). CORMP moored buoy. 34.207 N, 76.949 W | Offshore ocean, same site as 41159, 31.8 mi SSE | Wind, pressure, air, WTMP | Yes (`met=y`, `waterquality=y`) | 7:08 AM EST, WSPD 11.0 m/s, WDIR 020°, WTMP 21.2 °C, PRES 1014.4 mb | 60 min | Two gaps; longest 3.0 h on 21 Oct. **No WVHT** in 1,066 rows. `.spec` is 404. NDBC points wave users to 41159. Already Crystal Coast's wind and offshore-temp backup. WTMP was present on 883 of 1,066 rows. |
| 41109 | New River Inlet, NC (CDIP 190). Scripps waverider. 34.484 N, 77.300 W | Nearshore ocean, off New River Inlet, 16.2 mi SW | Would be seas, swell, WTMP if alive | **No.** Not in `activestations`; realtime 404 | — | — | Not a current source. The station table does not mark it disestablished, unlike 41035/41036. |
| CLKN7 | Cape Lookout, NC. NDBC C-MAN. 34.611 N, 76.528 W | Ocean, at the cape, 32.6 mi east (9.8 mi from Beaufort Inlet) | Wind, air, pressure. **No WTMP, no waves** | Yes | 7:30 AM EST, 6.2 m/s from 340° | 10 min in the current 45-day file | Five short gaps; longest 2.5 h on 2 Nov. Crystal Coast's primary wind. Too far east to be an unlabeled Emerald Isle source. |
| 8656483 / BFTN7 | Beaufort, Duke Marine Lab. CO-OPS NWLON. 34.7173 N, 76.6707 W | Harbor / inlet water at Beaufort, 24.8 mi east (1.5 mi from Beaufort Inlet) | Wind, inshore WTMP, air, pressure, observed WL, tide predictions | Yes | CO-OPS 8:12 AM EST, wind 6.03 mph N, air 46.6 °F, WTMP 63.0 °F, pressure 1014.7 mb, WL 3.301 ft MLLW. NDBC met 7:30 AM EST | 6 min | Five short gaps; longest 4.5 h on 14 Oct. Water-level flag `1,0,0,0` on the latest row. Already Crystal Coast's tide, inshore temp, and harbor wind. |
| 8656590 | Atlantic Beach Triple S Pier. CO-OPS harmonic prediction station. 34.6933 N, 76.7117 W | Ocean pier at Atlantic Beach, 22.3 mi east (2.5 mi from Beaufort Inlet) | Tide predictions, including a 6-minute curve. **No observations** | Predictions only | Predicted high 10:18 AM EST, 3.982 ft MLLW | 6-min curve available | Atlantic Beach / Crystal Coast, not this region. Range is already unlike Bogue Inlet (3.98 ft vs 2.43 ft this morning). |
| 8657167 | New River Inlet. CO-OPS subordinate, referenced to 8654400. 34.5333 N, 77.3417 W | Inlet, 15.9 mi WSW, toward North Topsail | Tide **predictions only** (highs and lows). No 6-minute curve | Predictions exist | — | Highs and lows only | Later Topsail / New River region. |
| 8657002 | Sneads Ferry, New River. CO-OPS harmonic prediction station. 34.5763 N, 77.3954 W | New River, 17.6 mi WSW | Tide predictions, including a 6-minute curve. **No observations** | Predictions only | — | 6-min curve available | Later region. River / sound, not Bogue Inlet. |
| 8654400 | Cape Hatteras Fishing Pier. CO-OPS harmonic / historical station. 35.2233 N, 75.635 W | Ocean, Hatteras Island, 91.9 mi ENE | Tide predictions and harmonics. **No water-levels product** | Not a live gauge | — | — | Published reference for TEC2837 and several other NC subordinates. Cannot supply observed water level for Bogue Inlet. |
| KNJM | Bogue Field Marine Corps Auxiliary Field. NWS / ASOS. 34.69403 N, 77.02945 W | Sound-side airfield, north of Bogue Sound, 5.0 mi NE of the inlet (Carteret, NCZ195) | Wind, air, altimeter (AUTO METAR) | Yes this morning | 6:51 AM EST, 5 kt from 320°, 3.9 °C, A2994 | Typically ~60 min; recent hours are irregular | Closest official wind/air, but not the beach. Not listed among NWS observation stations for MHX grid 46, 54. KNCA (MCAS New River) last observation was 6:56 PM EST 13 Nov and is stale; it is also inland. KOAJ (Albert J. Ellis, Jacksonville) is inland Onslow, 7:55 AM EST, 3 kt — not a beach reading. |
| KMRH | Beaufort Smith Field. 34.7326 N, 76.6566 W | Inland of Beaufort Inlet, 25.8 mi ENE | Airport wind and air | Yes | 7:55 AM EST, 18.5 km/h (10 kt) from 340°, 8 °C | ~60 min | Already Crystal Coast's air-temp backup. Not local here. |

## NWS office, forecast point, and zones

Office: **NWS Newport / Morehead City (MHX)** for this entire region.
The ILM boundary is at Surf City, not at Emerald Isle or Swansboro.

The NOAA Bogue Inlet coordinate resolves to marine zone **AMZ158**. A land
forecast point must be slightly inland so it returns **NCZ195**, not the
marine zone. The island and the sound shore are narrow; several first-guess
town points this morning fell into AMZ158.

- **Recommended land forecast point:** west Emerald Isle, just inland of
  the inlet, 34.655 N, 77.090 W. NWS `/points` returns **MHX grid 46, 54**,
  forecast zone **NCZ195 West Carteret**, office MHX, county Carteret
  (NCC031). A mid-island Emerald Isle point (34.674 N, 76.980 W) is also
  NCZ195, grid MHX 50, 55, if a more central town point is preferred.
- **Swansboro is a different land zone.** The East Corbett Ave. Bridge
  point (34.6866 N, 77.1181 W) returns **MHX grid 44, 55**, forecast zone
  **NCZ199 Coastal Onslow**, county Onslow (NCC133). Cedar Point and Cape
  Carteret, immediately east of the White Oak River, stay in NCZ195
  (Carteret). A region that includes both Emerald Isle and Swansboro
  therefore spans two land zones and two counties.
- **Marine tile:** **AMZ158**, official name "S of Cape Lookout NC to Surf
  City NC out to 20 NM" (CWA MHX, metadata confirmed). This is the correct
  ocean zone. It is also Crystal Coast's marine zone, and it is wider than
  this region (it covers Atlantic Beach, Cape Lookout, and the approach to
  Surf City). The same kind of zone-vs-region mismatch as AMZ250 at
  Wrightsville and AMZ150 at Nags Head; a short `marine.zoneNote` would
  match Ed's 14 Nov decisions there.
- **No separate Bogue Sound marine zone turned up in `/points`.** Sound
  and White Oak River points resolved to NCZ195, NCZ199, or AMZ158, not to
  a dedicated sound zone like AMZ231 behind Nags Head. **AMZ156** is "S of
  Ocracoke Inlet NC to Cape Lookout NC out to 20 NM" and is the ocean on
  the other side of the cape, not Bogue Sound.
- **Alert zones (proposed):** `AMZ158`, `NCZ195` (West Carteret, which
  already includes Emerald Isle, and which Crystal Coast already alerts),
  and `NCZ199` (Coastal Onslow, for Swansboro / Hammocks Beach; Crystal
  Coast does **not** currently include this). Do **not** add `NCZ196`
  (East Carteret — Down East / the Beaufort side of Crystal Coast),
  `AMZ156`, `NCZ106` (Coastal Pender / Surf City, office ILM), or `AMZ250`.

## Overlap with Crystal Coast

Crystal Coast is live today, anchored at Beaufort Inlet, named "Morehead
City · Beaufort." Its instruments and zones, and how they sit relative to
this region:

| Crystal Coast source | Role there | Distance from Bogue Inlet | Use here? |
|---|---|---|---|
| CLKN7 | Primary wind | 32.6 mi E (but only 9.8 mi from Beaufort Inlet) | Not as an unlabeled Emerald Isle primary. Cape Lookout is local to Crystal Coast. A labeled last-resort backup at most. |
| 41064 | Wind backup; offshore water-temp backup | 31.8 mi SSE | Same offshore site as 41159. Honest as a **labeled** "Onslow Bay Outer" wind / temp source; it is not a beach reading. Reusing it shares Crystal Coast's backup buoy. |
| 41159 | Only seas, swell, and primary offshore temp | 31.6 mi SSE (37.0 mi from Beaufort Inlet) | The only active WVHT source in reach. Slightly closer to Emerald Isle than to Beaufort Inlet, but still a regional offshore buoy, ~32 miles out. Must be labeled "Onslow Bay Outer." Reusing it means two dashboards share Crystal Coast's only seas buoy; if 41159 is down, both regions would go unavailable (41109 is dead; 41110 is the wrong water). |
| 8656483 | Tide, inshore temp, harbor wind, air, pressure | 24.8 mi E (1.5 mi from Beaufort Inlet) | Beaufort harbor / Beaufort Inlet, not Bogue Inlet. Do not reuse silently. Predicted tide range and timing already differed this morning. |
| AMZ158 | Marine forecast | Official zone for both | Correct official zone, and a duplicate marine tile if both regions show it without a caption that the zone also covers Crystal Coast and the run to Surf City. |
| NCZ195 | Alert zone (West Carteret) | Emerald Isle is already in this zone | Crystal Coast already alerts Emerald Isle, Indian Beach, Atlantic Beach, Morehead City, Cedar Point, and Cape Carteret. Adding this region does not create a new land-zone forecast; it only adds a closer forecast point (MHX 46, 54 vs Morehead City MHX 58, 59). |
| NCZ196 | Alert zone (East Carteret) | Not this region | Do not reuse. East Carteret is the Down East / Beaufort side of Crystal Coast. |

**Verdict: this would not just be a second Crystal Coast page, but it
would share Crystal Coast's ocean buoy and official marine zone.** The
honest local additions are the Bogue Inlet (and, if included, Swansboro)
tide predictions, a west-Bogue-Banks forecast point, Coastal Onslow alerts
if Swansboro is in, and any sound-side KNJM wind that is clearly labeled.
Wind, seas, swell, and water temperature at the beach itself are not
locally instrumented. A clone that reused CLKN7, 8656483, and AMZ158
without labels would be a duplicate, and a misleading one: Cape Lookout
and Beaufort Inlet are the east end of Bogue Banks, 22–33 miles from this
anchor.

Atlantic Beach is the clean split. It is already in Crystal Coast's
backyard (2.5 mi from Beaufort Inlet; Triple S Pier tide predictions exist
there). Folding it into an "Emerald Isle / Swansboro" region would pull
Crystal Coast's core shore into a west-island page.

## Risks

1. **No instrument at the anchor itself** except official high/low tide
   predictions. Wind, seas, swell, inshore ocean temperature, and observed
   water level all have to come from somewhere else and be labeled, or
   show as unavailable.
2. **TEC2837 has no 6-minute curve and no official live reference gauge.**
   This is harder than Nags Head, where Duck (8651370) is both the live
   NWLON and the published reference for Jennette's Pier. Here the
   published reference, 8654400, is a Hatteras prediction station with no
   water-levels product. Applying the official offsets to invent a
   6-minute Bogue Inlet curve would be derived data; do not do that.
   Using the Swansboro 6-minute curve silently would mix basins (this
   morning's highs were 91 minutes and 0.46 ft apart).
3. **41159 / 41064 are ~32 miles offshore** and already belong to the
   Crystal Coast dashboard. They are the best available ocean series, not
   local pier readings.
4. **41064 is a shaky wind primary.** Hourly reports will trip a 75-minute
   stale window unless `staleAfterMin` is raised (this morning's 7:08 AM
   report was already 72 minutes old at 8:20 AM). It also disagreed with
   both Cape Lookout and Bogue Field.
5. **KNJM is close but is a sound-side airfield**, with irregular hourly
   METARs, and it is not in the NWS grid station list. It is not a
   substitute for a missing ocean-pier wind sensor.
6. **AMZ158 and NCZ195 are wider than the region** and are already used
   by Crystal Coast. Alerts and the marine forecast will also apply to
   Atlantic Beach, Morehead City, and (for AMZ158) the waters toward Cape
   Lookout and Surf City.
7. **41109 is a hole in the nearshore wave network.** If it returns, it
   would be a closer, more local seas candidate (16.2 mi, New River
   Inlet) — still not at Emerald Isle, and closer to the later Topsail
   region — and would have to be labeled.

## Open questions for Scout and Ed

1. Confirm the east edge: Town of Emerald Isle only, stopping before
   Indian Beach and Pine Knoll Shores? Or treat "Bogue Banks" as one
   region, which would overlap Crystal Coast / Atlantic Beach?
2. Confirm the west edge: include Hammocks Beach / Bear Inlet with
   Swansboro, and leave New River Inlet / Sneads Ferry / North Topsail
   for the later Topsail region?
3. Is Swansboro / Cedar Point / Cape Carteret in this region, as the
   name "Emerald Isle / Swansboro" implies, or is this a beach-only
   region with Swansboro as a labeled sound-side footnote?
4. Tide tile: can a later phase show TEC2837 official highs and lows at
   Bogue Inlet with no 6-minute curve and no local observed water level
   (show observed as unavailable)? Or is a labeled Swansboro curve, or a
   labeled Beaufort observed level, acceptable the way Duck is used at
   Nags Head? Duck is the official reference for Jennette's; Beaufort is
   not the official reference for Bogue Inlet, and 8654400 cannot fill
   that role.
5. Wind: show 41064 as the ocean-wind tile (labeled Onslow Bay Outer),
   KNJM as sound-side / harbor wind (labeled Bogue Field), and accept
   that Emerald Isle itself has no wind sensor? Or hide ocean wind when
   we have no local station?
6. Inshore water temp: hide it (no ocean-pier sensor), rather than show
   Beaufort harbor water?
7. Accept sharing 41159 and AMZ158 with Crystal Coast, with labels and a
   short zone caption, rather than treating this page as a duplicate?
8. What happens to the disabled `atlantic-beach` stub — leave Atlantic
   Beach / Pine Knoll Shores for a later page, or retire the combined
   name?

## Phase 2 defaults (14 Nov 2026)

Set for the private preview on 14 Nov 2026. Config-driven; later review can change them.

- **Coverage:** Town of Emerald Isle only, from Bogue Inlet to the east town line.
  Swansboro, Cedar Point and Cape Carteret are out. No NCZ199.
- **Alerts:** AMZ158 and NCZ195. Land forecast point 34.655 N, 77.090 W, MHX grid
  46, 54. Anchor is TEC2837 Bogue Inlet.
- **Tide:** official highs and lows from TEC2837, labeled as predictions. No
  6-minute curve and no observed water level. The Swansboro bridge curve and
  Beaufort observed level are not used.
- **Ocean wind:** 41064 only, labeled "Onslow Bay buoy, ~32 mi offshore", with
  that station's existing 130-minute stale window. KNJM and CLKN7 are not used.
- **Inshore water temperature:** unavailable. Beaufort harbor water is not used.
- **Seas, swell and offshore temperature:** 41159 only (swell from `.spec`),
  labeled with its distance. No backup.
- **Marine zone:** the official zone, AMZ158, with a short caption that the
  zone runs from Cape Lookout to Surf City, a larger area than Emerald Isle.
- The existing `atlantic-beach` stub stays disabled and untouched.
- The region stays a private preview (`enabled: false`, `previewReady: true`).
  Without the `cb_preview` cookie, `/?region=emerald-isle` and
  `/api/conditions?region=emerald-isle` return 404 and `/api/regions` does not
  list it. Going public needs Ed's separate approval.
