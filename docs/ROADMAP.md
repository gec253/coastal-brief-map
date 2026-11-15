# The Coastal Brief: development roadmap

Set by Ed Cogdell, Nov 13, 2026. "From the rivers to the sounds to the sea."
Updated Nov 14, 2026, with Ed's approval, to match the live site.

## Goal
Cover the whole North Carolina coast, from Corolla to Sunset Beach and out to offshore waters, with freshwater lakes and rivers as an equal pillar.

## Rules
- New regions are built privately first, at the same quality and function as the Crystal Coast and Hatteras dashboards.
- No new region goes public without Ed's review and approval.
- Use only geographically appropriate NOAA/NWS/USGS sources. Never present distant conditions as local; a station that isn't local is labeled with its real location.
- Build on the existing region architecture (data/regions.json, conditions.py). Don't create a parallel system.
- Scout alone merges and deploys. Specialists work on local branches.
- Making a region public on the map does not give it a Morning Brief. A public brief needs Ed's OK.

## Coastal expansion order
1. Wilmington / Wrightsville Beach: public Nov 14, 2026.
2. Nags Head / Outer Banks: public Nov 14, 2026.
3. Emerald Isle: public Nov 14, 2026 (town of Emerald Isle only; Swansboro is not included).
4. Topsail: public Nov 14, 2026 (Topsail Island, New River Inlet to New Topsail Inlet).
5. Carolina Beach / Kure Beach — next private preview, then Ed's review.
6. Corolla / Duck
7. The remaining NC beaches and coastal communities, in later waves

## Freshwater (in parallel)
Public: Falls Lake, Jordan Lake, Neuse River (Falls Dam to Goldsboro). Falls Lake has a public Morning Brief. There is no Morning Brief yet for Jordan Lake or the Neuse River. Next steps continue alongside the coastal work.

## Design
Live Nov 14, 2026 (Ed approved): Chartroom Folio homepage on public / (origin/main fb5041a), including the map region-zoom fix and the phone map overlay fix. Also live earlier that day: newspaper masthead with compact sticky folio, region picker, header Morning Brief link, and the 1200x630 share image (branding/og-masthead.jpg; og-preview.png kept). No chart texture on phones. See docs/IDENTITY.md.

Catch Wall, /lake, and Morning Brief pages have not yet been restyled in the Folio instrument look.

A lab mobile Lighthouse run on the live Folio homepage after fb5041a scored Performance 99, LCP 1.1s, CLS 0. A live PageSpeed phone check is planned for Nov 15.

## Live now (Nov 14, 2026)
Public saltwater dashboards: Crystal Coast, Hatteras, Wilmington, Nags Head, Emerald Isle, and Topsail.
Public freshwater pages: Falls Lake, Jordan Lake, and Neuse River.
Morning Briefs are public for Crystal Coast, Hatteras, and Falls Lake only. Preview briefs for Wilmington, Nags Head, Emerald Isle, and Topsail are cookie-gated, not published, and not archived.
Catch Wall uploads are on; every photo is moderated in /admin before it appears.
Also live Nov 14: robots.txt and sitemap.xml (public pages only), and AMZ152 shown alongside AMZ154 on the Hatteras marine tile.
Automatic Morning Brief publication for Crystal Coast and Hatteras is authorized through Nov 20, 2026, unless Ed extends it.
