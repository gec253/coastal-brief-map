# Public /wind and /radar (Stage 2)

Implemented on `feature/public-viewers-1120`. **Not merged or deployed.** `HOME_SHOWCASE` stays off.

## What is public

- `/wind` and its CSS/JS, `/wind/engine.js` (shared particle engine; `/lab/wind.js` stays private), `/wind/coast-lo.json` and `/wind/coast-hi.json`.
- `/api/wind-grid` in a GFS-only mode for ahead steps 0, 3, 6, 9 and 12 (30-minute server cache, `public, max-age=600`). Error JSON has no `detail` field.
- `/radar` and its CSS/JS, and `/api/radar-view`. `/api/radar` and the tile proxy were already public.

## What stays private

- `?model=hrrr` on `/wind` and `/api/wind-grid` (404 without the preview cookie or `WIND_PARTICLES_ENABLED`; still works with the cookie).
- `/lab/wind`, `/lab/wind.js`, `/lab/tiles`, `/preview`, fixture tiles, admin, and other labs.
- `/api/radar/usage` (preview cookie only).
- `WEATHERAPI_KEY`, `PREVIEW_KEY`, and signed WeatherAPI tile URLs.

## Indexing

`/wind` and `/radar` are public and indexable (`index, follow` in the HTML meta and `X-Robots-Tag`) and are listed in `sitemap.xml`. `robots.txt` remains `Allow: /`. `/lab/wind` and other private pages stay `noindex` or 404.

## Rate limits (per client IP)

Sized from a real `/radar` load: 25 observed + 12 nowcast frames × about 9 tiles at native z7 ≈ 333 requests, plus pans and zooms (a pan can refetch tiles for every loaded layer).

| Endpoint | Limit | Window |
|---|---|---|
| `/api/radar/tile/...` | 2,400 | 5 minutes |
| `/api/radar`, `/api/radar-view` | 60 | 1 minute |
| `/api/wind-grid` | 30 | 1 minute |

Over the limit: HTTP 429, `Retry-After`, JSON `{ok: false, reason: "rate_limit"}`. Client IP is `CF-Connecting-IP` when present, otherwise the leftmost valid `X-Forwarded-For` hop (Render / Cloudflare).

## Upstream 429 / failure

Observed tiles may be reused while they are ≤ 60 minutes old (WeatherAPI current-conditions cap). Nowcast tiles only within 180 s. The viewer shows a clear “temporarily limited” message and never paints a half-drawn or invented frame. `/preview?key=` and similar query values are redacted in request logs.

Access logs use the same client IP as the limiter (`CF-Connecting-IP`, else the leftmost `X-Forwarded-For`), not the Render proxy peer (`127.0.0.1`). To verify the limiter on production, send at least 31 `/api/wind-grid` requests from one stable client IP (a single HTTP keep-alive connection is enough). Opening a new connection per request from a rotating egress pool (Cloudflare privacy/proxy addresses, some CGNAT test beds) will not fill one bucket and can look like the limiter is off.
