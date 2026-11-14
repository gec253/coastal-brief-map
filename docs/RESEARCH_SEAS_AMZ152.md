# Research: Crystal Coast seas backup, and a draft AMZ152 tile

Checked the evening of 13 Nov 2026, America/New_York (EST, UTC−5). Sources: NDBC
`station_table.txt`, NDBC `activestations.xml` (created 8:45 PM EST), NDBC
`realtime2/{id}.txt` latest rows, and NWS zone metadata
`https://api.weather.gov/zones/forecast/AMZ152` and `AMZ154`. Distances use the
same haversine as `conditions.py` (statute miles). Nothing here was invented or
interpolated. A CDIP metadata URL (`/data_access/metadata.cdip?stn=`) returned
404, so CDIP IDs are taken from the NDBC station names, which already label
them that way (217, 150, 190, 200, 250).

This branch is research plus a draft only. It has not been pushed or deployed.

## (a) Is there a real wave station that can back up 41159?

**No. Nothing suitable.** If 41159 is down, Crystal Coast seas and swell should
show as unavailable. Do not substitute a farther buoy in different water. That
is the same rule already used for Hatteras offshore temperature (do not
substitute 41025 for 41120).

41159 itself (Onslow Bay Outer, CDIP 217, 34.211N 76.944W) is active and was
reporting WVHT 0.9 m, DPD 6 s, MWD 198° at **7:56 PM EST**, about a 30-minute
cadence, 36.3 mi from Cape Lookout (34.61N 76.53W). It is an offshore waverider
in Onslow Bay, south of Bogue Banks and Beaufort Inlet, outside the cape.

### Station table (as of this check)

| Station | Official name | In NDBC activestations? | Reports WVHT? | Latest observation (ET) | Distance from 41159 | Distance from Cape Lookout | Same water as 41159? |
|---|---|---|---|---|---|---|---|
| **41159** (CDIP 217) | Onslow Bay Outer, NC | Yes (CORMP / IOOS, type buoy, met=y) | Yes. 0.9 m, 6 s, MWD 198°. Every row in the file has WVHT. | 7:56 PM EST, 13 Nov 2026 | 0 | 36.3 mi | Primary. Offshore Onslow Bay, south of the cape. |
| 41064 (LEJ3) | Onslow Bay Outer, NC | Yes (CORMP / IOOS) | **No.** WVHT/DPD/APD/MWD are MM in every row. NDBC's own station note points wave users to 41159. | Latest met 7:08 PM EST (wind 7 kt / 330°, WTMP 21.2 °C). Hourly. | 0.4 mi | 36.7 mi | Same site, but it is the weather buoy, not a wave sensor. |
| 41036 | Onslow Bay Outer, NC (old NDBC 3 m) | No | — | — | 0.4 mi | 36.7 mi | Same site historically. **Disestablished 26 May 2015** (funding). |
| 41035 | Onslow Bay Inner, NC | No | — | — | 26.5 mi | 43.7 mi | Nearer-shore Onslow Bay. **Recovered and disestablished 22 Aug 2011.** |
| 41109 (CDIP 190) | New River Inlet, NC | No | No realtime file (HTTP 404) | — | 27.7 mi | 44.7 mi | Nearshore Onslow Bay / New River Inlet. Listed as a waverider in the station table, but not currently reporting. |
| 41037 (ILM3) | Wrightsville Beach Offshore, NC | Listed yes, but `met=n` | **No** WVHT in the file | Last any report **6:08 PM EDT, 10 Oct 2026** (~34 days stale). Unusable. | 28.4 mi | 64.0 mi | Offshore Wrightsville, farther SW in Onslow Bay. Matches the earlier note that 41037 was stale on 12 Nov. |
| **41110** (CDIP 150) | Masonboro Inlet, ILM2, NC | Yes (CORMP / IOOS) | Yes. 0.5 m, 6 s, MWD 167°. Fresh, ~30 min. | 8:00 PM EST, 13 Nov 2026 | 44.3 mi | 74.9 mi | Closest *active* other waverider. Nearshore at Masonboro / Wrightsville, 44 mi SW. Same broad bay, not the same water as an offshore Crystal Coast reading. Tonight it was already 0.4 m lower than 41159. |
| 41038 (ILM2) | Wrightsville Beach Nearshore, NC | Yes (CORMP / IOOS) | **No.** All WVHT MM. NDBC points wave users to 41110. | Latest met 8:08 PM EST | 44.3 mi | 74.9 mi | Met companion to 41110, not a wave station. |
| 41108 (CDIP 200) | Wilmington Harbor, NC | Yes (SCRIPPS / IOOS) | Yes. 0.7 m, 4 s, MWD 268°. Fresh, ~30 min. File only goes back to 5 Nov 2026. | 7:56 PM EST, 13 Nov 2026 | 70.2 mi | 104.9 mi | Cape Fear / Wilmington Harbor nearshore. Different coastal segment. |
| 41013 | Frying Pan Shoals, NC | Yes (NDBC) | Yes. 0.8 m, APD 3.6 s, MWD 208° (DPD MM on this row). ~10 min. | 8:10 PM EST, 13 Nov 2026 | 71.3 mi | 107.6 mi | South of Cape Fear. Different shelf water. |
| 41025 | Diamond Shoals, NC | Yes (NDBC) | Yes. 0.9 m, APD 4.7 s, MWD 218°. ~10 min. | 8:10 PM EST, 13 Nov 2026 | 105.3 mi | 71.3 mi | SE of Cape Hatteras, on the other side of Cape Lookout. Already the Hatteras wind/wave backup. |
| 41120 (CDIP 250) | Cape Hatteras East, NC | Yes (SCRIPPS / IOOS) | Yes. 1.2 m, 6 s, MWD 277°. ~30 min. | 8:26 PM EST, 13 Nov 2026 | 118.8 mi | 83.5 mi | East of Cape Hatteras, AMZ152 side. Already the Hatteras seas primary. Different water. |
| CLKN7 | Cape Lookout, NC | Yes (NDBC C-MAN) | **No.** All WVHT MM. | Latest met 8:10 PM EST (5.1 kt / 330°) | 36.4 mi | 0.1 mi | At the cape. Wind only. |
| 41063 | Raleigh Bay (B2) | No | — | — | 69.4 mi | 35.5 mi | Would have been the nearest station *north* of the cape. **Recovered 21 Nov 2018.** |
| BFTN7 / 8656483 | Beaufort, Duke Marine Lab | Yes (CO-OPS) | No waves (tide / harbor weather) | — | 38.3 mi | 10.9 mi | Inside the inlet. Not a wave station. |

No other CDIP, NCCOOS, CORMP, or Duke waverider appears in the NDBC tables near
Beaufort or Cape Lookout. The only active wave sensors in the wider area are
well SW (Masonboro, Wilmington Harbor, Frying Pan) or well NE (Diamond Shoals,
Cape Hatteras East, then Oregon Inlet / Nags Head / Duck, 140+ mi). There is
currently no wave buoy in Raleigh Bay.

### Recommendation

Leave Crystal Coast seas and swell on 41159 only. 41110 is the least-distant
active waverider, but it is a nearshore Masonboro Inlet buoy 44 miles southwest
and was already reading a different sea state tonight. It is a poor automatic
stand-in for Beaufort / Lookout / Onslow Bay Outer. 41064 is co-located and
healthy, but it does not measure waves.

## (b) Draft: show AMZ152 alongside AMZ154 on the Hatteras marine tile

Official NWS names (zone metadata, effective 16 Apr 2026):

- **AMZ154** — S of Cape Hatteras NC to Ocracoke Inlet NC out to 20 NM (already
  the tile's primary zone)
- **AMZ152** — S of Oregon Inlet NC to Cape Hatteras NC out to 20 NM (already in
  `alertZones`, not previously shown on the marine tile)

The draft on this branch, behind no flag and not merged, is:

- `data/regions.json`: Hatteras `marine.also` lists AMZ152 with the official
  name. The primary `zone` stays AMZ154.
- `conditions.py`: `marine_block` still returns the primary zone as today. Extra
  zones are fetched from the same NWS coastal-forecast URL and hung off `also`.
  Crystal Coast has no `also` list, so its payload is unchanged.
- `dashboard.js`: the marine instrument stacks both zone forecasts (two periods
  each). The seven-day strip gets a chip and an expanded column per zone. The
  sources table gets a row per zone. Zones are labeled separately and are not
  combined into one text.

### Live check, 13 Nov 2026

`marine_block` was run against live NWS for AMZ154, AMZ152, and AMZ158 (three
calls). All three returned status `ok`, issued **6:15 PM EST**. The two
Hatteras zones were already different, which is why they should not be merged:

- AMZ154 tonight: NW winds around 10 kt, increasing to 20–25 kt; **seas 2 to 4
  ft, building to 4 to 6 ft after midnight**. Saturday: seas 4 to 6 ft.
- AMZ152 tonight: N 10–15 kt becoming NW 20–25 kt; **seas 4 to 6 ft**. Saturday:
  seas 5 to 7 ft.

Unit tests in `tests/test_conditions.py` (`HatterasMarineZones`) cover the
config shape, that both URLs are fetched and not merged, that Crystal Coast
stays a single zone, and that the dashboard script renders `also`.

### Tradeoff

**Tile clutter and length.** The marine instrument currently reserves 280–576 px
(`--rh-mar`, measured for one zone and two periods). Stacking AMZ152 roughly
doubles that tile. On a phone, two seven-day marine columns and two summary
chips also add a lot of text. Shipping this would need a new reserved-height
pass or the load will shift the layout (CLS). This draft does not change those
heights.

**41120 sits on the AMZ152 side.** The Hatteras seas buoy (Cape Hatteras East,
CDIP 250) is east of the cape, in AMZ152 water, about 119 mi from 41159. The
tile today only shows AMZ154 (south of the cape). A visitor looking at 41120
seas and an AMZ154 forecast is looking at two different sides of the point.
Showing AMZ152 alongside AMZ154 makes that honest. It does not mean the two
forecasts should be averaged; tonight they already disagreed by a couple of
feet.

**Which zone matters for which inlets.**

- **Oregon Inlet** and the east-facing ocean from there down to the cape
  (Rodanthe, Avon, Buxton east side, Cape Point north and east): AMZ152.
- **Hatteras Inlet** and the ocean south of the cape toward **Ocracoke Inlet**:
  AMZ154. Hatteras village and the south-facing inlet sit on this side.
- Pamlico Sound remains AMZ135 (alerts only; not part of this draft).

The region is "Hatteras Island," which includes both sides of the cape, so
showing both nearshore ocean zones is defensible. The cost is a longer, busier
tile. A caption-only alternative (keep AMZ154, add one line that 41120 and the
east-side beaches are AMZ152) would be shorter but would not give the east-side
forecast.

## Uncertainties

- 41109 has no NDBC "disestablished" note, only a missing active record and a
  404 on the realtime file. Treated as not currently reporting, not as a formal
  retirement date.
- 41037 is still listed in `activestations.xml` even though its last report is
  10 Oct 2026 and `met=n`.
- Water depths and hull-mounted vs surface sensors were not re-checked beyond
  the NDBC table.
- Reserved marine-tile heights were not remeasured on this draft.
