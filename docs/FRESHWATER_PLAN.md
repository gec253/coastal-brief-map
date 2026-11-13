# Freshwater plan: from the rivers to the sounds to the sea

Status: **planning only.** No freshwater region is enabled, and none can be served yet:
`conditions.py` refuses any region whose `waterType` isn't `saltwater` (or that is
marked `draft`), even if `enabled` is flipped by mistake. Saltwater instruments stay
first on phones.

Sources below were checked live on **13 Nov 2026, about 7 AM ET**. Numbers are quoted
only to show the feeds work; they are not shown on the site.

## 1. What changed in the code (groundwork only)

- **`data/regions.json`** gains:
  - `waterTypes`: `saltwater` (Ocean, inlets, and sounds) and `freshwater` (Lakes,
    rivers, and reservoirs, `comingSoon: true`).
  - `instrumentSets`:
    - `coastal`: what the dashboard shows today.
    - `freshwater-lake`: lake elevation vs normal pool, water temperature, air
      temperature, wind, 24 h rain, forecast and QPF, alerts, access, regulations.
    - `freshwater-river`: streamflow with a percentile for the day, gage height, water
      temperature, rain, NWPS river forecast, forecast and QPF, alerts, access,
      regulations.
  - `"waterType": "saltwater"` on every existing region.
  - One **draft, disabled** region, `falls-lake`, built only from sources verified below.
- **`/api/regions`** now includes `waterType`. The region picker groups regions under
  "Saltwater", with a disabled "Freshwater: Lakes and rivers: coming soon" entry.
- **Photos** have a water type (Saltwater or Freshwater) next to the category. Galleries
  filter with `?water=salt|fresh`, and the admin can change it. See
  PHOTO_UPLOADS_SETUP.md for the SQL.
- The home strip adds one line: "From the rivers to the sounds to the sea. Freshwater
  lakes and rivers are coming soon."

## 2. Structure (proposed)

- **One site, two equal pillars.** Saltwater stays the default because the current
  audience is coastal and the phone first screen is the marine instrument panel.
  Freshwater regions will appear in the same picker under their own group. The URL stays
  `/?region=<id>`, so there are no new routes and nothing to break.
- **The dashboard is chosen by instrument set, not by region.** One shell renders the
  set the region names: tiles, a level or flow chart in place of the tide chart, and
  forecast and alerts (shared). That avoids a second app.
- **Readings keep the same honesty rules:**
  - Every tile says Observed, Forecast, or Predicted, plus its station and time.
  - No estimates are shown in place of observations.
  - Stale data is labelled as stale.
- **Lake level is shown as "X ft below/above guide curve", never as a percentage full.**
  The USACE guide curve (the seasonal target) is the honest reference, and normal pool
  changes by season.
- **The datum is shown with the number.** USGS publishes Falls and Jordan in both
  NGVD29 (62614) and NAVD88 (62615). USACE guide curves are in NGVD29 ft-msl, so compare
  62614 to the guide curve, never 62615.
- **Flow percentile:** use USGS daily statistics for the calendar day (p10/p25/p50/p75/p90).
  Bands follow USGS WaterWatch: below p10 "much below normal", p10–p24 "below normal",
  p25–p75 "normal", and so on. Label the band as USGS historical context, not a
  forecast.

## 3. Sources checked live

**USGS Water Services, instantaneous values** (`waterservices.usgs.gov/nwis/iv`): **works**
(JSON, no key). The new OGC API (`api.waterdata.usgs.gov/ogcapi/v0/collections/latest-continuous`)
also answers. USGS is moving users to it, so a later build should use it, with
waterservices as the fallback.
- Falls Lake above dam, 02087182:
  - elevation 245.09 ft NGVD29 (62614) and 244.19 ft NAVD88 (62615) at 6:45 AM ET;
  - water temperature 16.7 °C (00010).
- Neuse River near Falls (dam release), 02087183: 60 cfs and gage 0.94 ft at 6:45 AM ET.
  This matches USACE's posted release of about 60 cfs.
- Neuse River near Clayton, 02087500: 221 cfs and gage 1.23 ft at 6:15 AM ET.

**USGS daily statistics** (`waterservices.usgs.gov/nwis/stat`): **works**. Clayton
percentiles for 13 Nov: p10 209, p25 251, p50 322, p75 915 cfs. So 221 cfs is
"below normal" (between p10 and p25).

**USGS reservoir elevation sites (62614/62615)**: **works.**
- Live sites include:
  - Falls Lake 02087182;
  - B. Everett Jordan Lake 02098197 (212.23 ft at 6:45 AM ET);
  - W. Kerr Scott 02111391 (1030.64 ft);
  - Hyco Lake;
  - Lake Mattamuskeet;
  - several Wake County lakes.
- **USGS water temperature (00010):**
  - Active at:
    - Falls Lake;
    - the Roanoke (Halifax, Jamesville, Westover);
    - Rocky River at Siler City;
    - Yadkin at Patterson;
    - three Pee Dee sites;
    - many Catawba sites;
    - French Broad (Fletcher, Asheville);
    - Pigeon at Canton;
    - Little Tennessee at Needmore;
    - Oconaluftee, Cheoah, Mills, Davidson, Cataloochee, Hyco.
  - Stale, or returning the sentinel −999999:
    - Cape Fear at Lillington;
    - Cape Fear Lock 1;
    - Roanoke at Oak City;
    - Pigeon below the power plant.
  - **None on the Neuse or Tar rivers.** River water temperature must be shown as
    unavailable there, never estimated.

**USACE Wilmington District lake levels** (`epec.saw.usace.army.mil`, plus the weekly
update PDF dated 9 Nov 2026): **works, as HTML and PDF.**
- Guide curves (ft-msl, NGVD29):
  - Falls 251.5 ft;
  - Jordan 216.0 ft;
  - W. Kerr Scott 1030.0 ft;
  - John H. Kerr 297.0 ft;
  - Philpott 971.5 ft.
- With the USGS reading, Falls is about 6.4 ft and Jordan about 3.8 ft below guide curve
  this morning (drought).
- The CWMS Data API (`cwms-data.usace.army.mil`) returned no SAW catalog to an anonymous
  query, and `water.usace.army.mil` is a JavaScript app.
- Plan: take the elevation from USGS, and keep the guide curve as a dated config
  value checked against USACE (it changes only seasonally). Link to the USACE page.

**Duke Energy lake levels** (`lakes.duke-energy.com`, which loads
`lakes.hydro-derived.duke-energy.app`): the page answers (200, a JavaScript app).
- **Terms:** Duke Energy's Terms of Use (updated 3 Apr 2023) limit site content to
  "your own internal residential or business use". They forbid reproducing,
  publishing, distributing, or displaying it.
  - I read these terms through a search-engine copy, because duke-energy.com returns
    403 to the fetcher.
- **Conclusion:** do **not** scrape or redisplay Duke lake levels. Link to Duke's page
  only, unless Duke gives written permission.
  - Many Duke lakes are reported against a local "100 ft = full pond" datum, which
    would need clear labelling anyway.
  - USGS covers some Duke lakes directly (e.g. Hyco), and those are fine to use.

**NWS NWPS river forecasts** (`api.water.noaa.gov/nwps/v1/gauges/CLYN7`): **works**.
- Observed 1.23 ft / 0.183 kcfs, not flooding, with a forecast series.
- Flood stages: action 8 ft, minor 9, moderate 13, major 16.
- Its observation time trails USGS, so use USGS for "now" and NWPS for the forecast and
  flood categories.

**NWS observations, forecast and QPF** (`api.weather.gov`): **works**.
- Falls Lake dam (35.9411, −78.5833) maps to RAH grid 76,65 and zone NCZ041.
- Gridpoint data includes `quantitativePrecipitation` for QPF.
- Observations: nearby ASOS stations (RDU, etc.), to be chosen and checked at build
  time.

**NCWRC boating access areas**: **works**.
- Public ArcGIS feature service `NCWRC_Boating_Access_Areas_view` (267 sites).
- Fields include:
  - status (OPEN …);
  - name and water body;
  - lat/lon;
  - launch lanes, docks, parking;
  - `Fishing_Water_Designation` (COASTAL / INLAND …), which maps neatly onto water type.
- **License:** "free, public, non-commercial use only", with no warranty.
  - The site shows ads, so **ask NCWRC before embedding the data**. Until then, link to
    `ncwildlife.org/boating/boating-access-areas`.
- **Regulations:** the NCWRC fishing regulations page answers (200). **Link only**:
  rules change, and we should never paraphrase limits.

## 4. Recommended first region: Falls Lake and the Neuse below it

Why Falls Lake:
- Every core instrument is verified and free:
  - lake elevation and water temperature at one USGS site;
  - a USACE guide curve for an honest "below/above normal pool";
  - dam release flow (02087183);
  - Clayton streamflow with daily percentiles;
  - an NWPS forecast with flood stages;
  - the NWS RAH forecast, QPF and alerts.
- It is close to the Triangle's population, a large fishing audience.
- The Neuse ties the story together, from the river to the sound to the sea, because
  it is the same river as the existing New Bern / Pamlico context.

Alternatives:
- **Jordan Lake** (same quality of USGS and USACE data, no water temperature at the dam).
- **W. Kerr Scott / Yadkin** (water temperature at Patterson).
- The **Catawba chain** has rich USGS temperature data, but its lake levels are Duke's
  (terms above).

## 5. Phased rollout

0. **Done now:** schema and config groundwork, photo water type and filters, "coming
   soon" in the picker, and this plan. Nothing freshwater is served.
1. **Build the instrument set behind a flag.** Add USGS and NWPS fetchers with the same
   caching and staleness rules as the coastal ones, and a lake tile plus a flow tile. A
   level or flow chart replaces the tide chart. Check it on a local or preview URL at
   390/768/1280 in light and dark.
2. **Enable Falls Lake in production.** Do this only after Ed signs off on the copy and
   numbers have been compared against the USACE and USGS pages for a week. Add the
   access and regulations links (links only).
3. **Second region and river view.** Jordan Lake, and a Neuse river view (Clayton, NWPS).
   Consider moving to the USGS OGC API.
4. **Optional:** NCWRC ramp data on the map, if NCWRC allows it. Duke lakes only with
   permission. Mountain trout waters later, where USGS temperature coverage is good.

## 6. Decisions for Ed

1. Approve Falls Lake as the first freshwater region, or pick Jordan Lake instead.
2. Rename "Coastal Life"? Options:
   - keep it (simple, on-brand);
   - "Life on the Water", which covers lakes and rivers;
   - rename only once freshwater launches.

   URLs can stay, with `/coastal-life` kept working.
3. Ask NCWRC for permission to show boating-access data on an ad-supported site? This
   is optional; links work without it.
4. Ask Duke Energy for permission for lake levels? Optional, and only needed for the
   Catawba / Yadkin-Pee Dee lakes.
