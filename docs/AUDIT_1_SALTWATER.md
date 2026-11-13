# Saltwater source audit 1 — Crystal Coast and Hatteras

Read-only check of official feeds used by the live Conditions dashboard, 13 Nov 2026.
Observation times below are in America/New_York (EST, UTC−5). Ages are relative to
about 14:02 ET (NDBC) / 14:03 ET (CO-OPS and NWS). Raw values are from the official
endpoints; nothing was interpolated.

Scope: enabled saltwater regions in `data/regions.json` only (`crystal-coast`, `hatteras`).
No app code was changed. Official metadata: NDBC `station_table.txt`, CO-OPS MDAPI,
NWS `/points` and `/zones`. Latest observations: NDBC `realtime2/*.txt` and `*.spec`,
CO-OPS Data API `date=latest` (and a 1-hour water-level range for cadence).

## Scout list vs `data/regions.json`

The configured sources match Scout's list. The file also has extras (backups and
inshore instruments) that were verified where they share a station already on the list.

**Crystal Coast (`crystal-coast`)** — matches:

| Scout | Config |
|---|---|
| CLKN7 wind, 41064 backup | `readings.wind.sources`: CLKN7, 41064 |
| 41159 seas + swell | `seas` and `swell` sources: 41159 only |
| CO-OPS 8656483 water / air / pressure / tides | `waterTemp`, `airTemp`, `pressure`, `tide.station` all 8656483 |
| NWS MHX forecast | `forecast`: MHX grid 58,59, label Morehead City — confirmed by NWS `/points/34.7229,-76.726` |
| Alerts AMZ158 / AMZ156 + NCZ195 | `alertZones`: AMZ158, AMZ156, NCZ195 |

Extras in config (not on Scout's short list): `waterTempOffshore` 41159 then 41064;
`harborWind` 8656483; air-temp backup KMRH; pressure backup CLKN7; primary marine
tile zone AMZ158. KMRH was not curl-checked this pass.

**Hatteras (`hatteras`)** — matches:

| Scout | Config |
|---|---|
| 41025 wind | `readings.wind.sources`: 41025 |
| 41120 seas | `seas` primary 41120; config also lists 41025 as backup |
| CO-OPS 8654467 | water / air / pressure / tides / harbor wind |
| Zone AMZ154 | `marine.zone` AMZ154 |

Extras: swell 41120 then 41025; `waterTempOffshore` 41120 then 41025; air-temp
backup KHSE; pressure backup 41025; NWS MHX grid 93,86 (confirmed by
`/points/35.2196,-75.69`); `alertZones` also include AMZ152, AMZ135, NCZ205.
KHSE was not curl-checked this pass.

Disabled saltwater stubs (`atlantic-beach`, `cape-lookout`, `new-bern`,
`wilmington`) were out of scope.

## Per-station table

Locations below are from the source metadata endpoint, not from `regions.json`.
Configured lat/lon matched official positions in every case (within the file's rounding).

### Crystal Coast

| ID | Official name / location | Feeds (kind) | Reporting? | Latest obs (ET) | Age | Cadence | Notes |
|---|---|---|---|---|---|---|---|
| CLKN7 | Cape Lookout, NC. NDBC C-MAN. 34.611 N, 76.528 W | Ocean wind (obs); pressure backup (obs) | Yes | 13:40 EST 13 Nov 2026 (WSPD 4.6 m/s, WDIR 270) | 22 min | 10 min (met) | No water temperature in the first 200 rows. PTDY only on the hour (13:00 EST). In region (Cape Lookout). |
| 41064 | Onslow Bay Outer, NC (LEJ3). CORMP moored buoy. 34.207 N, 76.949 W | Wind backup (obs); offshore water-temp backup (obs) | Yes | 13:08 EST (WSPD 6.0 m/s, WTMP 21.3 °C) | 54 min | typically 60 min (one 120 min gap in the last eight rows) | No WVHT in the file; `.spec` is 404. Correctly not used for seas/swell. |
| 41159 | Onslow Bay Outer, NC (217 / CDIP). Waverider. 34.211 N, 76.944 W | Seas, swell, offshore water temp (obs) | Yes | 12:56 EST (WVHT 1.0 m, SwH 0.1 m, WTMP 21.3 °C) | 66 min | 30 min (met/waves and SwH) | Only seas/swell source for this region. No wind sensors. |
| 8656483 | Beaufort, Duke Marine Lab. CO-OPS NWLON. 34.71733, −76.67066. SHEF BFTN7 | Inshore water temp, air, pressure, harbor wind, tide predictions, observed water level | Yes | 13:54 EST for wind, water temp (65.8 °F), air (62.2 °F), pressure (1004.4 mb), WL 2.425 ft MLLW (preliminary) | 9 min | 6 min (confirmed on a 1-hour water-level range) | At Pivers Island / Beaufort Inlet. In region. |
| NWS MHX 58,59 | Point forecast for Morehead City (34.7229, −76.726). Office MHX | Land forecast | Grid confirmed | — | — | NWS gridpoint forecast (code TTL 30 min) | `kind: forecast`. Public zone at this point is NCZ195 West Carteret. |
| AMZ158 | S of Cape Lookout NC to Surf City NC out to 20 NM (coastal, CWA MHX) | Marine forecast (primary) | Zone metadata confirmed | — | — | NWS coastal forecast | Correct ocean zone for Beaufort Inlet / Bogue / Onslow Bay. |
| AMZ156 | S of Ocracoke Inlet NC to Cape Lookout NC out to 20 NM | Alerts only | Zone metadata confirmed | — | — | — | Core Banks side of the cape; reasonable alert neighbor. |
| NCZ195 | West Carteret (public, MHX) | Alerts | Zone metadata confirmed | — | — | — | Covers Morehead City. Does **not** cover Beaufort or Cape Lookout (see problems). |

### Hatteras

| ID | Official name / location | Feeds (kind) | Reporting? | Latest obs (ET) | Age | Cadence | Notes |
|---|---|---|---|---|---|---|---|
| 41025 | Diamond Shoals, NC. NDBC 3-meter foam buoy. 35.026 N, 75.380 W | Wind (obs); seas/swell/offshore-temp/pressure backup | Yes | Met 13:30 EST (WSPD 6.0 m/s, WTMP 25.3 °C); WVHT 1.4 m at 13:20 EST; SwH 1.1 m at 13:10 EST | 32 / 42 / 52 min | 10 min met; ~30 min waves and SwH | In region (SE of the cape). Water temp is much warmer than 41120 — see problems. |
| 41120 | Cape Hatteras East, NC (250 / CDIP). Waverider. 35.258 N, 75.285 W | Seas, swell, offshore water temp (obs) | Yes | 13:26 EST (WVHT 1.5 m, SwH 0.1 m, WTMP 20.5 °C) | 36 min | 30 min | East of the cape, ~14 NM. No wind sensors. |
| 8654467 | USCG Station Hatteras. CO-OPS NWLON. 35.2086, −75.7042. SHEF HCGN7 | Inshore water temp, air, pressure, harbor wind, tides, observed water level | Yes | 13:54 EST for wind, water temp (63.0 °F), air (58.6 °F), pressure (1004.8 mb), WL 1.047 ft MLLW (preliminary) | 9 min | 6 min | Sound-side at Hatteras Inlet. In region. Some 6-minute WL rows, including the latest, carried flag `1,0,0,0` (Beaufort was almost all `0,0,0,0`). Still published as preliminary; not treated as a missing observation. |
| NWS MHX 93,86 | Point forecast for Hatteras (35.2196, −75.69). Office MHX | Land forecast | Grid confirmed | — | — | NWS gridpoint forecast | Public zone at this point is NCZ205 Hatteras Island. |
| AMZ154 | S of Cape Hatteras NC to Ocracoke Inlet NC out to 20 NM | Marine forecast (primary) + alerts | Zone metadata confirmed | — | — | NWS coastal forecast | Matches Scout and config. This is the south side of the cape. |
| AMZ152 | S of Oregon Inlet NC to Cape Hatteras NC out to 20 NM | Alerts only | Zone metadata confirmed | — | — | — | East / north-of-cape ocean; 41120 sits on this side. |
| AMZ135 | Pamlico Sound | Alerts only | Zone metadata confirmed | — | — | — | Reasonable for a Hatteras Island product. |
| NCZ205 | Hatteras Island (public, MHX) | Alerts | Zone metadata confirmed | — | — | — | Matches the land forecast point. |

No station was stale by the audit rule used here (>3 h for tides/buoys). All listed observation stations were reporting.

## Swell vs combined seas (not mislabeled)

The code keeps them separate end to end.

- Config (`data/regions.json`): distinct `seas` and `swell` readings. Crystal Coast both from 41159; Hatteras both from 41120, with 41025 as backup.
- Fetch (`conditions.py`): `seas` uses NDBC standard met file field `WVHT` (significant / combined wave height). `swell` uses the `.spec` file field `SwH` (and wind-sea `WWH`), not `WVHT`.

```227:238:conditions.py
    if kind == "seas":
        rec = first_row(rows, "WVHT")
        ...
        return {
            "time": rec["_dt"], "url": url,
            "values": {"heightFt": r1(h * M_TO_FT), "dominantPeriodS": dpd, ...},
            "raw": {"WVHT_m": h, "DPD_s": dpd, "APD_s": apd, "MWD_degT": mwd},
```

```186:210:conditions.py
    if kind == "swell":
        rows, url = ndbc_rows(sid, "spec")
        ...
            if num(r, "SwH") is not None:
        ...
                "heightFt": r1(swh * M_TO_FT) if swh is not None else None,
                ...
                "windWaveFt": r1(wwh * M_TO_FT) if wwh is not None else None,
            "raw": {"SwH_m": swh, "SwP_s": swp, "SwD": swd, "WWH_m": wwh, ...},
```

- UI (`dashboard.js`): Seas tile title "Seas", label "Significant wave height", footnote "average of the highest third of waves, all wave trains combined" (`renderSeas`, lines 363–376). Swell tile title "Swell", label "Swell height", plus a "Wind sea" bar; footnote "NDBC splits the buoy's measured wave spectrum into swell and wind sea" (`renderSwell`, lines 381–402). Observed vs forecast tags are separate (`kindTag`, lines 90–91).

Live values at the check time were consistent with that split (41159/41120: WVHT 1.0–1.5 m vs SwH 0.1 m). 41025, used only as a Hatteras backup, does publish a real SwH series.

## Staleness and timestamps (code behavior)

Saltwater observations are not estimated. `conditions.py` lines 5–6, 35–41, 417–445, 485–532, 692:

- Every reading carries its observation time (`time` / `lastReport`) and `ageMin`.
- Per-parameter stale thresholds (`STALE_MIN`): wind 75 min, harbor wind 45, seas/swell 120, inshore water/air/pressure 90, offshore water temp 180. Older than the threshold is shown as `stale` (dimmed, with time) if still under `MAX_AGE_H` (12 h); older than 12 h is `unavailable` (time kept if known).
- Observed tide/water level: stale after 30 min, not shown after 6 h (`OBS_WL_STALE_MIN` / `OBS_WL_MAX_MIN`). Quality is labeled `preliminary`.
- Tide curve and highs/lows are `kind: predicted`; observed water level is a separate `kind: observed` overlay.
- NWS land and marine blocks are `kind: forecast` with an update time.
- Cache fallback still uses the record's own observation time, not the fetch time.

This is solid. The only tightness is 41064's hourly cadence vs the 75-minute wind stale window (see below).

## Problems, ranked

1. **Medium — Crystal Coast land alerts miss East Carteret (NCZ196).** `alertZones` include NCZ195 (West Carteret) only. NWS `/points` for Beaufort (34.718, −76.664) and Cape Lookout / CLKN7 (34.611, −76.528) both return forecast zone NCZ196, official name "East Carteret". Morehead City is correctly NCZ195. The region name is "Morehead City · Beaufort", so alerts can miss warnings that apply to Beaufort, Shackleford, and Cape Lookout. File: `data/regions.json` (`crystal-coast.alertZones`). Proposed change: add `NCZ196`. No code change required.

2. **Medium — Hatteras offshore water-temp backup is a different water mass.** At 13:26–13:30 EST, 41120 (primary) WTMP was 20.5 °C and 41025 (backup) was 25.3 °C, about 8.6 °F warmer (Diamond Shoals / Gulf Stream influence). If 41120 drops, the offshore water-temp tile would jump rather than look like a slightly delayed 41120 reading. Wind/seas/swell backup use of 41025 is geographically reasonable. File: `data/regions.json` (`hatteras.readings.waterTempOffshore`). Proposed: drop 41025 from that list, or keep it only with a clear "different station / warmer water" note if it is ever used.

3. **Low / at-risk — Crystal Coast seas and swell have no backup.** Only 41159. 41064 is nearby but has no wave or `.spec` data. If 41159 lags past 120 min, those tiles go stale then unavailable. Not wrong today (66 min old, still reporting).

4. **Low / at-risk — 41064 as wind backup vs a 75-minute stale window.** 41064 reports about hourly (one 2-hour gap in the recent rows). `STALE_MIN["wind"]` is 75 minutes (`conditions.py` lines 37–39). If CLKN7 is down, a healthy 41064 report will often be marked stale before the next hour arrives. Do not loosen the threshold globally without checking CLKN7 (10-minute). Options: accept the occasional stale backup, or give hourly sources a longer window.

5. **Low — Hatteras primary marine forecast is only AMZ154.** That zone is the ocean south of Cape Hatteras to Ocracoke Inlet. The region is "Hatteras Island" and the wave buoy 41120 is east of the cape (AMZ152). AMZ152 and Pamlico Sound (AMZ135) are already in `alertZones`. Question is whether the marine tile should also show AMZ152, not whether alerts are missing it.

6. **Informational — intermittent CO-OPS water-level quality flag at 8654467.** Latest Hatteras WL (and 3 of 9 points in the last hour) had `f=1,0,0,0`; Beaufort almost all `0,0,0,0`. Values were still preliminary and on the 6-minute cadence. Not a source or labeling error. No code change suggested without a product-owner read of the flag.

No stations were found outside the region they feed. Swell is not labeled as combined seas. Observations are not mixed with forecasts. No estimates are presented as readings in the saltwater path. Freshness checks and timestamps are in place.

## Proposed changes (not made)

- Add `NCZ196` to `crystal-coast.alertZones`.
- Revisit `hatteras.readings.waterTempOffshore` backup (41025).
- Optionally document, or special-case, 41064's hourly wind cadence vs the 75-minute stale rule.
- Consider a second marine zone on the Hatteras marine tile (AMZ152), or a short caption that AMZ154 is the south side of the cape.

## Open questions

- Should Crystal Coast alerts always include NCZ196 (East Carteret)?
- Should the Hatteras marine instrument show AMZ152 as well as AMZ154?
- Is a Crystal Coast wave-buoy backup worth adding if one is ever available, or is "41159 or unavailable" preferred?
- What should happen when 41120 water temp is down — hide offshore temp, or show 41025 with a strong location caveat?
