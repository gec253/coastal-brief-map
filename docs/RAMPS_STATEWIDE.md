# Ramp Finder statewide data (Phase 1, private preview)

Approved by Ed (t547u, Nov 27, 2026). **Private preview only.** It lives at `/preview/ramps-statewide`
and `/preview/ramps-statewide/<slug>`, behind the PREVIEW_KEY cookie. Pages are noindex and no-store,
and they aren't in the sitemap. Public `/ramps` still reads `preview/ramp-finder/inventory.json` and is unchanged.
There's no map, near-me search or conditions panel yet (Phase 2).

## Refresh (manual, no cron, no paid service)

```
python3 scripts/build_ramps_statewide.py            # live NCWRC + NOAA station list
python3 scripts/build_ramps_statewide.py --dry-run  # report only
python3 scripts/build_ramps_statewide.py --from-file saved-query.json --no-noaa-fetch
```

The script exits 0 when it wrote data and 2 when it kept the last-known-good data. Afterwards, review
`preview/ramp-finder/refresh-report.json` (the diff of added, removed and changed NCWRC records and fields,
plus counts and data quality) before committing. Recheck `official_notices.json` against the official pages
before every deploy.

### Last-known-good protection
The script keeps the previous `statewide.json` records and sets `meta.refresh.status = kept_last_known_good`
(the preview then shows a warning) when any of these happen:
- the fetch fails, or the response is an error or has no features
- required NCWRC fields are missing (schema change)
- the record count drops more than `--max-drop` (default 10%) from the previous snapshot
- more than 5% of records lack coordinates or a GlobalID, or GlobalIDs are duplicated
- no NOAA station list is available (the build needs it for salinity inference)

Missing data always means uncertainty. It's never shown as "open".

## Files
| File | What |
|---|---|
| `inventory.json` | Manually verified Nov 22 records (unchanged; public /ramps uses it) |
| `statewide.json` | Built output for the private statewide preview |
| `ncwrc_snapshot.json` | Raw NCWRC attributes by GlobalID (the diff baseline) |
| `ncwrc_crosswalk.json` | Stable slug ↔ NCWRC GlobalID. Slugs never change once assigned |
| `official_notices.json` | Dated official notices entered by hand (closures, low water) |
| `noaa_tide_stations_nc.json` | NOAA tide-prediction stations (NC, VA, SC), cached |
| `refresh-report.json` | Last refresh diff, counts and data-quality report |

## Rules
- **Merge.** Manual records win field by field. NCWRC fills only blank or "not stated" fields, and only for
  records matched to an NCWRC GlobalID. Each fill is attributed in `field_sources`. When both have a value and
  they differ, the manual value is kept and the conflict is logged.
- **No invention.** NCWRC 1 → yes, 0 → no, null → "not stated". Text values are kept verbatim. For sites
  NCWRC doesn't own, fees and hours are "Not stated … check with the owner".
- **Dedupe.** Match on the crosswalk GlobalID first. Otherwise match on coordinates within 150 m plus a name
  match, then on exact name plus county. An NCWRC site within 400 m whose name doesn't match is kept separate
  and flagged.
- **Access type.** NCWRC `Portable_Boat_Access_Type` set → paddle / carry-in. Lanes ≥ 1 → trailer.
  `Motorboats_Restricted` = 1 → limited.
- **Status precedence.** A dated official notice (`official_notices.json`) wins over the NCWRC Site_Status
  when it's newer. NCWRC "CLOSED TEMPORARILY" → temporarily closed. "OPEN" with a closure reason → status
  unclear (review). No status → "not stated".
- **Regions.** New NCWRC sites are assigned to the nearest homepage anchor within 20 miles (straight line):
  Crystal Coast (Beaufort Inlet), Emerald Isle (Bogue Inlet, listed with Crystal Coast), Wilmington (Johnnie
  Mercer's Pier), Topsail (Ocean City Pier), Nags Head (Jennette's Pier) or Hatteras (Cape Hatteras). Anchors
  come from `data/regions.json`. Falls Lake, Jordan Lake and the Neuse go by NCWRC waterbody. Everything else
  is grouped by NCWRC's administrative region (Coastal, Piedmont or Mountain). Manually verified records keep
  their Nov 22 area.
- **Hatteras.** If no record falls inside the Hatteras radius, the page says so and lists the nearest 3
  verified launches outside it, with straight-line distance. It never implies local coverage.
- **Neuse split.** The area key stays `neuse-river`, so URLs are stable. `neuse_segment` = upper when the
  launch is at or upstream of the NCWRC Goldsboro BAA (longitude ≤ −78.0), matching the homepage region
  "Falls Dam to Goldsboro". Everything else is lower (below Goldsboro to Pamlico Sound, including brackish and
  tidal launches). Address-only New Bern records count as lower. The preview also accepts `?region=neuse-upper`
  and `?region=neuse-lower`.
- **Regulatory class vs salinity.** `regulatory_class` is NCWRC's Fishing_Water_Designation
  (INLAND/COASTAL/JOINT), a fishing-rules boundary. `salinity` is separate: it's *verified* where the Nov 22
  research recorded it. Otherwise it's *inferred*: INLAND waters more than 15 mi from any NOAA tide-prediction
  station → freshwater, and COASTAL waters within 10 mi of one → brackish or salt (tidal). Anything else is
  *not determined*.
- **Unknown regions.** `?region=<anything unknown>` shows an honest message and a statewide link, never every
  ramp.

## Phase 1.1 refinements (Nov 27, 2026, Ed t548u)

- **Documented geographic exception.** `GEO_EXCEPTIONS` in `scripts/build_ramps_statewide.py` lists records by NCWRC GlobalID that are assigned to an area outside the 20-mile rule. The only entry is Rodanthe BAA (GlobalID `06bbb31d-4a33-45a2-917c-7eecba2e1e1e`). It is on Hatteras Island, 24 miles from the Cape Hatteras anchor, so it is listed with Hatteras Island. The 20-mile rule itself is unchanged. Each exception records its reason in `area_rule.rule` and sets `exception: true`.
- **Two independent dimensions.** `type_dimension` (trailer, paddle, limited, needs_review, unknown) comes only from the listing class and access type. Official status (`access_status.code`: listed_open, temporarily_closed, partially_open, conflicting, not_stated) is separate. A closed launch keeps its access type. `counts.by_type_dimension`, `counts.by_status` and `counts.type_by_status` each total every record.
- **Official coordinates overlay.** `preview/ramp-finder/official_coordinates.json` holds access-area GPS points published by the owner (NC State Parks pages for Falls Lake and Jordan Lake). They are shown as "Official location point". `directions` are never changed, and addresses are never geocoded. Records the owner does not publish a point for are listed under `unresolved` and keep address-only directions.
- **Notices.** `official_notices.json` carries the date and time each official page was last rechecked. NCWRC statuses show the NCWRC data edit date plus the recheck date. Where sources conflict, the status is "status unclear", never "open".
- **Preview UI.** There is one search field (name, town, county, waterbody). The server-side GET search works without JavaScript, and a small inline script filters as you type. The statewide view groups launches by area in native `<details>`, collapsed by default. Each section shows an access-type line and a status line.

## Public launch (Nov 27, 2026, Ed t550u)

Public `/ramps` and `/ramps/<slug>` serve this statewide directory (285 sites). `/preview/ramps-statewide` stays cookie-gated and shows the same data. The inventory preview at `/preview/ramps` and the interactive map stay private. `PUBLIC_RAMPS=0` still hides `/ramps`. `PUBLIC_RAMP_MAP` stays off, so `/ramps/map` is 404.

The sitemap lists only `/ramps` (the same as before this launch). Individual ramp pages are not added, which matches how the earlier public directory was listed.

Jordan Lake (`/ramps?region=jordan-lake`) shows the official low-water banner and the unmatched Parkers Creek closure as an official notice not tied to a listed ramp, with its source and date.
