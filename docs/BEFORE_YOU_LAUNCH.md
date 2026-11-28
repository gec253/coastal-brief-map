# Before You Launch (Phase 3B, private preview)

Private only: `/preview/before-you-launch/<ramp-id>` for the 79 pilot ramps, behind the existing preview cookie.
Without the cookie every path (page, `.json`, `byl.css`, `byl.js`) is 404. Pages are noindex, no-store, and not in the sitemap.

- `byl_data.py`: the data layer. It reads only `publishable` stations from `stations/ramp_stations.json`. Each source has its own cache TTL, timeout, concurrency limit and failure backoff:
  - NWS forecast 30 min, NWS alerts 5 min, USGS 10 min, USACE 6 h, CO-OPS 6 h.
- Stale thresholds:
  - USGS is Stale after 3 h and not shown after 24 h.
  - USACE is Stale after 36 h and not shown after 7 days.
  - The NWS forecast is Stale after 12 h and not shown after 36 h.
- `byl_page.py`: Summer's approved layout (design/before-you-launch @ c2a0d01).
  - The server renders the shell (recorded access, regulations, computed sun and moon). Readings arrive asynchronously and replace skeletons.
  - A failed source becomes an Unavailable card. Nothing is filled in.

## Labels
Observed, Forecast, Predicted, Related station, Computed, Stale, Unavailable, Recorded status (access).

## Integrity
- Access is the recorded status and never a live check. Missing data is uncertainty, not a sign of safety.
- Ramps with an unresolved water class (10) still get the NWS forecast, alerts and sun/moon. Water readings are withheld there.
- Freshwater pages (reservoir, natural lake, river) drop marine alerts.
- `downstream_river_flow` is labelled "River flow below the dam (measured)". No `dam_release_reported` source is verified, so none is shown.
- No Duke, Dominion, TVA or Cube readings are shown.

## Mockup reconciliation (what the pages really get)

| Instrument | Union Point (New Bern) | Cedar Point |
|---|---|---|
| NWS point forecast | Yes | Yes |
| NWS alerts (point) | Yes (estuary, so marine alerts are allowed) | Yes |
| Water level (observed) | Unavailable: no reviewed same-water gauge (Pollocksville rejected; no active USGS or CO-OPS level gauge near New Bern) | Not in the inventory |
| Tide predictions | Omitted: wind-driven water | Yes: Swansboro 8656613, same water, 0.8 mi |
| Observed wind | Unavailable: no reviewed station | Unavailable: no reviewed station |
| Marine / sound forecast | Unavailable: marine zone not reviewed | Unavailable: marine zone not reviewed |
| Water temperature | Unavailable | Unavailable |
| Sun & moon | Computed | Computed |
| Regulations | NCDMF and NCWRC, with an explanation (jurisdiction unresolved) | NCDMF (coastal) |
