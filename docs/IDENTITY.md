# Visual identity prototype

Branch `design/identity`. Local design prototype only — not for production deploy.

## Intent

A traditional newspaper masthead for The Coastal Brief: typographic serif nameplate on deep navy, warm ivory type, restrained brass rules, and a faint public-domain NOAA nautical-chart texture. Personality lives in the instrument tiles; chrome stays restrained. No photos, no cartoon ornaments, no new paid fonts.

## Type

Existing self-hosted SIL OFL 1.1 faces in `/fonts`, with license texts already committed:

- **Fraunces** — nameplate and mission (`OFL-Fraunces.txt`)
- **Source Sans 3** — UI, dateline, body (`OFL-SourceSans3.txt`)
- **Barlow Condensed** — instrument numerals (`OFL-BarlowCondensed.txt`)

No faces were added. Metric-adjusted fallback families (`size-adjust`, `ascent-override`, `descent-override`, `line-gap-override`) sit behind each so first paint does not shift the masthead or tiles. `font-display: optional` with metric-adjusted fallbacks (no font preloads on the homepage, so the fonts do not contend with render-blocking CSS). The compact folio nameplate is set so “The Coastal Brief” reads in full at 360–390px (the Region kicker is hidden at that width so the picker can shrink; region *names* may still ellipsize).

## Masthead and sticky folio

Deep navy (`#071C29`) with warm ivory (`#F3E6D0`) and brass (`#C4A36A`) rules. The full masthead (nameplate, ET dateline, region line, “From the rivers to the sounds to the sea”, and — from 761px, where it fits — “Corolla to Sunset Beach, inland rivers and lakes to offshore waters”) is in normal flow and scrolls away. Height at 390px is kept modest so the conditions tiles remain the LCP element.

A compact folio bar under it is always in the document flow at a reserved 52px and is `position: sticky`. It holds the small nameplate, the region picker, and the Morning Brief link. A light shadow is always on — no scroll listener, no IntersectionObserver, no main-thread work at load for the stickiness. `identity.js` is not loaded on the homepage (dashboard.js + region-nav.js already bind the picker and update the region line). It is loaded only on lake and gallery pages. The homepage compact folio is solid navy; the chart texture is reserved for the masthead. `prefers-reduced-motion` disables transitions.

The dateline is filled in America/New_York by the server (`_apply_dateline`). The line has a reserved height, nowrap, and ellipsis.

## Chart texture

A decorative, very low-contrast CSS background only — not content, not the LCP element, not for navigation.

- File: `/branding/masthead-chart.webp` (sparse white linework on transparent, 800×240, 13.2 KB). The masthead inlines this as a CSS data URI under a navy veil (~16% residual contrast) so it is a decorative background with no extra image request and is not an LCP image resource. The same file is also requested by `/brief.css` for the brief chrome.
- Source chart: **NOAA Chart 11545**, *Beaufort Inlet and Part of Core Sound; Lookout Bight*, scale 1:40,000, 2023 (final raster edition, image `11545-8-2023`), published by NOAA Office of Coast Survey (NOAA-NOS).
- Record: https://www.historicalcharts.noaa.gov/image.php?filename=11545-8-2023
- JPEG: https://www.historicalcharts.noaa.gov/jpgs/11545-8-2023.jpg
- Collection: NOAA Office of Coast Survey Historical Map & Chart Collection, https://historicalcharts.noaa.gov/
- Rights: U.S. government work; the collection is public domain / CC0 1.0 (NOAA waives copyright worldwide). Historical charts are **not for navigation**. This crop is a faded ornament only and must not be treated as a chart or as a chart-use implication.

The texture is a crop of the Lookout Bight inset (the Cape Lookout hook, compass rose, and soundings), converted to faint linework and drawn at 16% opacity over navy so ivory type stays well above WCAG AA in both themes (the masthead itself stays navy in light and dark).

## Regions

The region line and picker are driven from the region list (`CoastalRegionNav.defaultCatalog()`, or `/api/regions` plus the freshwater list on the homepage). Freshwater options still go to `/lake?region=<id>`. The Morning Brief href still follows `brief-link.js`. The kill switch still strips `#nav-brief`.

## Palette

Deep navy, warm ivory, restrained brass, with Atlantic / Pamlico / marsh / dock / sand / sunrise tokens kept for the tiles. Light and dark both target WCAG AA on masthead text; interactive targets are 44px with a visible brass focus ring.

## What was not changed

`brief.py` build logic, `.github/`, Morning Brief automation, data labels (including seas vs swell and observed vs forecast), `/api/regions` (saltwater-only), and the public OG image file are untouched.

## Open Graph card

On the `design/og-image` branch only. The public file `branding/og-preview.png` is not replaced.

A 1200×630 card at `branding/og-masthead.jpg` (JPEG quality 90, under 300 KB) uses the same navy, ivory, brass, and NOAA Chart 11545 texture as the masthead. “THE COASTAL BRIEF” is set in the existing SIL OFL Fraunces, with the mission line “From the rivers to the sounds to the sea.” Type, vector rules, and the public-domain chart only. Important type sits in a centered 630×630 safe area so 1.91:1 and square-ish crops (iMessage, Facebook, X `summary_large_image`, LinkedIn) still read.

Reproduce with `node branding/render-og-masthead.js` from `branding/og-masthead.html`. Public pages (`/`, `/catch-wall`, `/coastal-life`, `/photos`, `/brief?region=…`, `/lake?region=…`) point `og:image` and `twitter:image` at `https://thecoastalbrief.com/branding/og-masthead.jpg` and include width, height, and alt.
