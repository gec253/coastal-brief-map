# Wind & Radar homepage section (HOME_SHOWCASE)

Approved Concept A (`8dc2047`), implemented on `feature/home-showcase-1120`. The section is **off** until the flag is turned on. Merging this branch does not change the live homepage.

## What merge would add (flag still OFF)

- The Crystal Coast homepage is unchanged. `/showcase.js` returns 404.
- Two new public, read-only, cached endpoints (non-sensitive data only):
  - `GET /api/home-wind` — current NOAA GFS 10 m wind snapshot for the Crystal Coast box. No `ahead`, no HRRR, no bbox parameters. Server cache 30 minutes; `Cache-Control: public, max-age=600`.
  - `GET /api/home-coast` — Census 1:500k coastline (low-res, public domain). Static file; `Cache-Control: public, max-age=86400`.
- `/wind` and `/radar` are publicly reachable (GFS / WeatherAPI viewers), indexable, and listed in the sitemap now that this showcase is launched. `/api/wind-grid` is public in a GFS-only mode (ahead 0/3/6/9/12). `?model=hrrr`, `/lab/wind`, and fixture tiles stay preview-gated. The WeatherAPI key and signed tile URLs stay on the server.

## Activation (needs Ed's approval)

1. This branch must already be the running Render build (or be deployed first, still with the flag off). Do not deploy between 5:00 and 5:45 AM ET.
2. In the Render dashboard, on the existing web service, set environment variable `HOME_SHOWCASE` to `1`. No new keys, no DNS, domain, or plan changes.
3. Render restarts the service when the env var is saved. After it is up, the Crystal Coast homepage (`/` and `/?region=crystal-coast`) shows the Wind & Radar instruments. Other regions are unchanged.
4. Check: the section appears below Conditions at a Glance; labels read MODEL FORECAST · GFS and OBSERVED with ET times; `/showcase.js` returns 200; the Open links load `/wind` and `/radar` (200). Those viewers are indexable and listed in the sitemap.

## Deactivation

Set `HOME_SHOWCASE` to `0` (or delete it) and save. The homepage returns to the previous layout. The two public data endpoints remain available.

## Flag values

On: `1`, `true`, `on`, `yes` (any case). Anything else, including unset, is off.
