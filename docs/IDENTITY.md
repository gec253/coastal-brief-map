# Visual identity prototype

Branch `design/identity`. Local design prototype only — not for production deploy.

## Intent

A traditional newspaper masthead for The Coastal Brief: typographic nameplate, publication dateline, region line, mission, and reach, with thin double rules. Personality lives in the instrument tiles; chrome stays restrained. No photos, no cartoon nautical ornaments, no new paid fonts.

## Type

Existing self-hosted SIL OFL 1.1 faces in `/fonts`, with license texts already committed:

- **Fraunces** — nameplate and mission (`OFL-Fraunces.txt`)
- **Source Sans 3** — UI, dateline, body (`OFL-SourceSans3.txt`)
- **Barlow Condensed** — instrument numerals (`OFL-BarlowCondensed.txt`)

No faces were added. Metric-adjusted fallback families (`size-adjust`, `ascent-override`, `descent-override`, `line-gap-override`) sit behind each so `font-display: swap` does not shift the masthead or tiles. Fraunces and Source Sans 3 are preloaded on the main pages.

## Masthead and sticky folio

The full masthead (nameplate, ET dateline, region line, “From the rivers to the sounds to the sea”, and — from 761px, where it fits — “Corolla to Sunset Beach, inland rivers and lakes to offshore waters”) is in normal flow and scrolls away.

A compact folio bar under it is always in the document flow at a reserved 52px height and is `position: sticky`. It holds the small nameplate, the region picker, and the Morning Brief link. When a 0-height sentinel above the bar leaves the viewport, an `is-stuck` class adds a shadow only — the in-flow height does not change. `IntersectionObserver` is used (no scroll listener). `prefers-reduced-motion` disables transitions.

The dateline is filled in America/New_York by the server (`_apply_dateline`) and refreshed in `identity.js` if needed. The line has a reserved height, nowrap, and ellipsis.

## Regions

The region line and picker are driven from the region list (`CoastalRegionNav.defaultCatalog()`, or `/api/regions` plus the freshwater list on the homepage). Names are not hardcoded in the masthead copy. Long names ellipsize in the folio button; the menu scrolls so later entries (Wilmington, Nags Head, and others) can be added to the same catalog without wrapping the bar or shifting layout. Freshwater options still go to `/lake?region=<id>`. The Morning Brief href still follows `brief-link.js` (crystal-coast, hatteras, or falls-lake; other freshwater ids fall back to crystal-coast). The kill switch still strips `#nav-brief`.

## Palette

Atlantic navy, Pamlico green, marsh grass, weathered dock, coastal sand, sunrise gold. Freshwater pages use muted river greens and earth (`data-water="freshwater"`). Light and dark both target WCAG AA; interactive targets are 44px with a visible focus ring.

## What was not changed

`brief.py` build logic, `.github/`, Morning Brief automation, data labels (including seas vs swell and observed vs forecast), and `/api/regions` (saltwater-only) are untouched.
