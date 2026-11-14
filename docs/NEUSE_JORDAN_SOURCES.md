# Neuse River and Jordan Lake: sources, stations and limitations

Private preview, same gate as Falls Lake. `/lake?region=jordan-lake`,
`/lake?region=neuse-river` and `/api/freshwater?region=` return 404 unless
`FRESHWATER_ENABLED=1` (or a preview cookie) is set. Both regions stay
`enabled: false` / `draft: true` and `previewReady: true`. Falls Lake is unchanged.
This note is the source survey used to build those views, in the same form as
`docs/FALLS_LAKE_SOURCES.md`.

Official checks, 13 Nov 2026 (ET, America/New_York, currently EST). USGS site service
and instantaneous values (IV), NWS NWPS `api.water.noaa.gov/nwps/v1/gauges/{LID}`,
USACE Wilmington District pages. Values below are from those endpoints; nothing was
interpolated.

Duke Energy and NCWRC are **link-only** here: no values should be copied from their
sites. These water bodies are USACE / USGS / NWS, not Duke lakes. When a page is
built, use the same pattern as Falls: NCWRC boating access and fishing regulations
as links (`ncwildlife.gov`), plus the official USACE project page.

## Stations and parameters

### Neuse River (Falls Dam to Kinston)

Stage is gauge height above a local gauge datum, in feet. Call it **stage**, never
depth. Discharge is USGS parameter 00060, cubic feet per second, provisional (P)
when live. Flows below Falls Dam are **regulated**.

| What a page would show | Source | Station / ID | Parameter | Units | Kind | Update frequency |
|---|---|---|---|---|---|---|
| Stage and flow, below Falls Dam | USGS IV | 02087183 Neuse River near Falls, NC / NWPS NEUN7 | 00065 stage, 00060 flow (also 63160 elevation, NAVD88) | ft, cfs | observed, provisional, **regulated** | USGS IV timestamps are consistent with the usual 15-minute interval |
| Stage and flow, Clayton | USGS IV + NWPS | 02087500 / CLYN7 Neuse River near Clayton, NC. 35.64722, −78.40528 | 00060, 00065 (also 63160 NAVD88) | cfs, ft | observed; NWPS also issues a routine stage forecast | 15-minute class IV; NWPS forecasts year-round |
| Stage only, Smithfield | USGS IV + NWPS | 02087570 / SMFN7 Neuse River at Smithfield, NC. 35.5125, −78.34944 | **00065 only**. USGS stopped IV discharge here: last 00060 is 30 Sep 1991 (qualifier A). Daily 00060 ends 29 Sep 1991. | ft | observed stage; NWPS routine stage forecast | 15-minute class IV for stage |
| Stage and flow, Goldsboro | USGS IV + NWPS | 02089000 / GLDN7 Neuse River near Goldsboro, NC. 35.3375, −77.9975 | 00060, 00065 | cfs, ft | observed; NWPS routine forecast | 15-minute class IV |
| Stage and flow, Kinston | USGS IV + NWPS | 02089500 / KINN7 Neuse River at Kinston, NC. 35.25778, −77.58556 | 00060, 00065 | cfs, ft | observed; NWPS forecasts **as needed in high water**, not routine | 15-minute class IV |
| Flood stages / river forecasts | NWS NWPS | NEUN7, CLYN7, SMFN7, GLDN7, KINN7 (see thresholds below) | official category stages (and forecast series where issued) | ft | official NWS thresholds / forecast | follows USGS for observed; forecast cadence as above |
| Water temperature | — | No active USGS IV 00010 on the Neuse main stem (see below) | — | — | show unavailable; do not borrow the Falls Lake dam sensor | — |

The draft `neuse-river` region in `regions.json` currently runs Falls Dam–Goldsboro
and does not list Kinston. Kinston is a live, official main-stem gauge and is included
here because it was on the verification list.

NWS flood categories (stage, feet), from NWPS on 13 Nov 2026:

| LID | USGS | Action | Minor | Moderate | Major | Forecasts |
|---|---|---|---|---|---|---|
| NEUN7 | 02087183 | 5 | 6 | 7 | 8 | Observed only; no forecast |
| CLYN7 | 02087500 | 8 | 9 | 13 | 16 | Routine, year-round |
| SMFN7 | 02087570 | 14 | 15 | 18 | 20 | Routine, year-round |
| GLDN7 | 02089000 | 17 | 18 | 20 | 24 | Routine, year-round (flow also published at the category lines) |
| KINN7 | 02089500 | 13 | 14 | 18 | 21 | As needed in high water, not routine |

Official pages:

- USGS IV: `https://waterservices.usgs.gov/nwis/iv/?format=json&sites={id}`
- USGS site: `https://waterdata.usgs.gov/monitoring-location/{id}/`
- NWPS: `https://water.noaa.gov/gauges/{lid}` and `https://api.water.noaa.gov/nwps/v1/gauges/{lid}`

### Jordan Lake (Cape Fear / Haw)

| What a page would show | Source | Station / ID | Parameter | Units | Kind | Update frequency |
|---|---|---|---|---|---|---|
| Lake elevation (headline) | USGS IV | 02098197 B. Everett Jordan Lake at dam nr Moncure, NC / NWPS NHPN7. 35.65472, −79.06833 | 62614 (lake/reservoir elevation, NGVD29) | ft | observed, provisional | 15-minute class IV |
| Lake elevation, NAVD88 (secondary) | USGS IV | 02098197 | 62615 | ft | observed, provisional | 15-minute class IV |
| Guide curve (target pool) | USACE Wilmington District | `https://epec.saw.usace.army.mil/dsslake.txt` (header), cross-checked with `BEJPERT.TXT` "top of conservation pool" | static **216.0** ft, each day of the year | ft (NGVD29 / USACE ft-msl) | reference | file is a 180-day midnight series; the 216.0 figure itself is standing project data |
| Official project elevation, inflow, outflow, gate settings | USACE | Project page `https://epec.saw.usace.army.mil/jord.htm`; daily report `https://epec.saw.usace.army.mil/bejrept.txt`; district report `https://epec.saw.usace.army.mil/dailyrep.pdf`; pertinent data `https://epec.saw.usace.army.mil/BEJPERT.TXT` | elevation ft-msl, outflow/inflow cfs | ft, cfs | official project report, **not a substitute for USGS IV when the report is stale** | Intended daily (0800-to-0800). See freshness below. |
| Rain at the dam | USGS IV | 02098197 | 00045 incremental | in | observed, one point | 15-minute class IV |
| Lake water temperature | — | **No USGS 00010** at 02098197 | — | — | USACE daily report has a "Lake temperature" line, but that file can lag (see below). Do not present a stale report as a live reading. | — |
| Inflow, Haw at Bynum | USGS IV + NWPS | 02096960 / BYNN7 Haw River near Bynum, NC. 35.76528, −79.13583 | 00060, 00065 | cfs, ft | observed, unregulated inflow **upstream of the lake**, not a below-dam gauge | 15-minute class IV; NWPS forecasts year-round. Flood: action 10, minor 11, moderate 15, major 17 ft. |
| Release at the dam (old gauge) | USGS | **02098198 Haw R below B. Everett Jordan Dam nr Moncure, NC. 35.64944, −79.06556 — discontinued.** IV flow ended 29 Sep 2010; IV stage ended 29 Sep 2016. | 00060, 00065 | — | **do not use** | dead |
| Nearest live flow below the dam | USGS IV + NWPS | 02098206 / HRMN7 Haw River near Moncure, NC. 35.63222, −79.06000. About 1.6 mi below the dam, above the Deep River confluence. | 00060, 00065 | cfs, ft | observed; **dam release plus local runoff**, not the official gate outflow. NWPS flood cats are estimated (action/minor 16, moderate 18; major not set). No NWPS forecast. | 15-minute class IV (see freshness) |
| Flood stages on the lake | NWS NWPS | NHPN7 (USGS 02098197) | action 240, minor 240, moderate 241, major 242 | ft, on the **pool elevation** scale (top of flood-control pool in `BEJPERT.TXT` is 240.0 ft msl) | official NWS thresholds; observed only, no lake-level forecast | follows USGS |
| Alerts | NWS API | draft zone NCZ040; or a point at the dam (35.6547, −79.0683) | — | — | official | — |

USACE project and recreation landing page (link-only context):
`https://www.saw.usace.army.mil/Locations/District-Lakes-and-Dams/B-Everett-Jordan/`.

Bynum (02096960 / BYNN7) is a valid official Haw River gauge, but it is **above**
Jordan Lake (NWPS lists it as upstream of NHPN7). It is an inflow candidate, not a
"at or below the dam" source. The below-dam gauge Scout listed, 02098198, is real
but no longer reports. The draft `jordan-lake` region already uses 02098206 / HRMN7
for that reason.

## Datums

- USGS 62614 is NGVD29. USACE "ft-msl" for Jordan (guide curve 216.0, flood pool 240.0)
  should be compared to 62614, not 62615, same rule as Falls Lake. On 13 Nov 2026 at
  13:30 EST, 62614 was 212.23 ft and 62615 (NAVD88) was 211.46 ft, a 0.77 ft offset.
  Never mix the two.
- River "stage" is gauge height, not water depth, and not NAVD88/NGVD29 elevation
  (some Neuse sites also publish 63160, which *is* NAVD88 elevation — label it as such
  if shown).
- NWPS NHPN7 flood stages are on the lake elevation scale, far above the 216.0 guide
  curve (action/minor 240). Do not compare them to river stages at Moncure or Bynum.

## Freshness rules

Mirror Falls Lake:

- USGS IV older than 3 h: flag stale and keep the timestamp. Older records must not
  be shown as current. This matters: a bare USGS IV call for 02087570 still returns
  the 1991 discharge, and 02098198 still returns 2010 flow / 2016 stage. Any client
  that takes "latest IV" without checking the time would display a decades-old value
  as a reading.
- Every value carries source, time, and units. Missing → "Not available from USGS
  (or USACE / NWS) right now", never zero.
- Observed vs forecast always labeled. Smithfield must not show discharge as a USGS
  reading. If NWPS publishes a secondary flow there, treat it as an NWS estimate,
  not a USGS observation.
- Prefer USGS 62614 for the live Jordan pool. Do not treat the USACE daily report or
  `dsslake.txt` midnight column as real-time when those files lag.

## Live verification, 13 Nov 2026 (ET)

Checked early afternoon (about 14:03 ET). Ages are from that moment.

| Check | Official source | Result |
|---|---|---|
| 02087500 Clayton | USGS IV 13:15 EST | stage 1.22 ft, flow 217 cfs (P), age 49 min |
| 02087570 Smithfield | USGS IV 13:15 EST | stage 4.45 ft (P), age 49 min. IV 00060 present but dated 30 Sep 1991, 298 cfs (A) — not a current flow |
| 02089000 Goldsboro | USGS IV 13:15 EST | stage 2.69 ft, flow 319 cfs (P), age 49 min |
| 02089500 Kinston | USGS IV 13:15 EST | stage 3.31 ft, flow 494 cfs (P), age 49 min |
| 02087183 below Falls Dam | USGS IV 13:30 EST | stage 0.94 ft, flow 60 cfs (P), age 34 min |
| 02096960 Haw at Bynum | USGS IV 13:45 EST | stage 2.62 ft, flow 77.4 cfs (P), age 19 min. Confirmed live inflow, not below the dam |
| 02098197 Jordan at dam | USGS IV 13:30 EST | 62614 212.23 ft, 62615 211.46 ft, rain 00045 0.00 in (P), age 34 min. No 00010 |
| 02098198 below Jordan Dam | USGS IV | last flow 29 Sep 2010, last stage 29 Sep 2016 — discontinued, as already noted in `regions.json` |
| 02098206 Haw near Moncure | USGS IV 12:45 EST | stage 2.02 ft, flow 245 cfs (P), age 79 min (still under 3 h; older than the other IV points at the same check) |
| Guide curve 216.0 | `dsslake.txt` header and `BEJPERT.TXT` top of conservation pool | match |
| USACE `dsslake.txt` midnight series | same file | last daily row **22 Oct 2026** — not current; do not use for today's elevation |
| USACE `bejrept.txt` | "MONDAY 9 NOV 2026" daily report | midnight elevation that day 212.37 ft-msl; outflow on the order of a few hundred cfs. **Four days old** when fetched on 13 Nov. Lake temperature on that report was 67 °F — not a live 13 Nov reading |
| NWPS CLYN7 / SMFN7 / GLDN7 / KINN7 / BYNN7 / NHPN7 | API 13 Nov | IDs, names, USGS crosswalks, and flood categories as in the tables above. All in service |

## Water temperature: Neuse and Tar

Scout's statement holds for the rivers, with two basin-level caveats.

A statewide USGS site search for **active instantaneous** parameter 00010 (13 Nov 2026)
returned 37 sites in North Carolina. In the Neuse and Tar-Pamlico accounting units:

- **Neuse main stem: no active IV water-temperature gauge.** Clayton, Smithfield,
  Goldsboro, Kinston, and below Falls Dam have only historical discrete (qw) 00010
  samples, not a live sensor. The draft `neuse-river` note in `regions.json` is correct.
- **Tar River: no active IV water-temperature gauge** on the Tar itself (no Tar River,
  Tarboro, or similar IV 00010 site in the list).
- The only active IV 00010 in HUC 030202 (Neuse) is **02087182 Falls Lake above dam**
  — a lake sensor, already used on the Falls Lake preview. Do not reuse it as Neuse
  River water temperature.
- The only active IV 00010 in HUC 030201 (Tar-Pamlico) is **0208458893 Lake
  Mattamuskeet**, a coastal lake, not the Tar River.

Jordan Lake dam (02098197) and the Haw gauges checked here also have no IV 00010.

## Unresolved issues and build cautions

1. **USACE files were stale on the check day.** `bejrept.txt` was dated 9 Nov 2026;
   `dsslake.txt` ended 22 Oct 2026. The standing guide curve (216.0) is still usable.
   Live pool elevation should come from USGS 62614 until a fresh USACE file is confirmed.
   Ask USACE if the lag is a current outage or normal for these paths. Same caution
   already recorded for the Falls homepage elevation in `FALLS_LAKE_SOURCES.md`.
2. **02098198 is the true below-dam gauge and it is dead.** Use 02098206 / HRMN7 only
   with the label "release plus local runoff", not "Jordan Dam release". Official
   gate outflow lives on the USACE daily report, when that report is current.
3. **02096960 / BYNN7 is inflow (Haw at Bynum), not a dam or tailwater gauge.**
4. **Smithfield is stage-only at USGS.** A naive IV fetch still returns a 1991
   discharge. NWPS may show a secondary flow; do not present that as USGS.
5. **Kinston is live but not in the draft `neuse-river` region** (that draft stops
   at Goldsboro). Add it only if the product is meant to continue downstream; its
   NWPS forecast is not year-round.
6. **Point rainfall** at 02098197 is one sensor at the dam.
7. USGS IV values are provisional (P) and can be revised. Downstream Neuse flows
   are regulated by Falls Dam and should be marked as such, same as the Falls preview.
8. `BEJPERT.TXT` lists two different "bottom of conservation pool" elevations (150.0
   in the storage table, 202.0 in the event table). That does not affect the 216.0
   guide curve. Do not invent a low-pool line from those figures without a USACE read.
