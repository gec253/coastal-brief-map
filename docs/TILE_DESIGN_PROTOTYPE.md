# Tile design prototype (private)

`/lab/tiles` returns 404 unless `TILES_LAB_ENABLED=1` (not set on Render). Files: `tiles-lab.html`
(self-contained CSS), `tiles-lab.js`. Nothing on the public site uses them. **Nothing is rolled out;
Ed approves before any of this touches the real dashboard.**

Screenshots: `/workspace/tiles-proto-{phone,desktop}-{light,dark}.png`, side by side with production in
`/workspace/tiles-compare-{phone,desktop}-{light,dark}.png`.

## Creative direction

*A premium North Carolina water publication that carries professional instruments.* The page itself stays
quiet (plain warm paper or deep night background, no framing ornament) so AdSense can later sit around it
without clashing. The personality lives inside the tiles and in short editorial moments between sections.

**One system.** Every tile has the same skeleton: a small tracked-caps name, an Observed / Forecast /
Predicted / Sample chip, one big Barlow Condensed reading with its unit, two supporting lines, a small
instrument drawing, and a ruled footer with the source (linked) and the reading time in ET. Same 16 px
radius, a hairline border, an inner top highlight, a two-layer soft shadow, and a faint corner glow.

**Each instrument its own identity** (layered gradient + one generated SVG texture + its own accent):

| Tile | Palette | Texture / drawing | Data shown |
|---|---|---|---|
| Wind | atmospheric blue-gray | faint streamlines drifting slowly (38 s loop; off with reduced motion, paused off-screen) | speed, gust, from-direction and degrees, 10°-tick compass with a "from" marker |
| Swell | deep Atlantic blue | long, widely spaced contour swells | height, period, direction, and a profile drawn to scale from the period (deep-water wavelength ≈ 1.56·T², labeled as an estimate) |
| Seas | Pamlico Sound green-blue | tight crossing chop pattern, short-period wave line | significant height, dominant period, direction, NDBC steepness, 0–12 ft sea meter |
| Tide | warm coastal sand | none; the day's curve is the art | latest observed level, rising/falling, next high/low, predicted curve with the observed line over it, the day's four events |
| Water temp | aquatic teal whose hue warms with the reading | ripple rings in the corner | inlet reading °F and °C, offshore buoy, 40–85 °F scale with both marked |
| Freshwater | muted river green, earth, a dock-wood rule | wooded-bank contour lines | lake elevation (never "depth"), distance from guide curve, pool bar with the 251.5 ft guide marked, dam release, water temp, 7-day change |

Palette references used: deep Atlantic blue `#0B2A3D`, Pamlico Sound green `#2F6A62`, marsh grass `#6E7F45`,
weathered dock wood `#7A5C43`, warm coastal sand `#EFE4CF`, sunrise gold `#C9932E` (reserved for highlights).

**Central-page personality.** Section transitions name the water: *The coast · Ocean*, *Sound & inlet ·
Tide and water*, *River & lake · Falls Lake*, each with its own thin divider line (open swell, dashed
channel markers, two river banks). Under each, a one-line editorial moment in Fraunces italic, tagged
"From the readings" and built only from the numbers on screen (for example "13 kt from the NW at Cape
Lookout, with 4.9 ft seas every 5 s in Onslow Bay: short-period wind waves more than groundswell.").
No photos, testimonials or local observations are invented. Both taglines are kept: "More than the
forecast. It's a way of life." and "From the rivers to the sounds to the sea."

**Advisories first, ads never in between.** The NWS advisory ribbon sits above every tile. Two inactive,
clearly labeled placeholders show where ads could go: a responsive slot after the ocean group and a
300×250 after all conditions. Both reserve their height up front. No ad code is loaded or activated.

**Imagery.** Every texture is an inline SVG data URI (a few hundred bytes each). No photos, no AI imagery.
If photos are wanted later, only documented public-domain NOAA/USFWS/NPS images with credit, kept out
from behind readings.

## Accessibility
WCAG contrast measured against both ends of each tile gradient: big readings 10.0–13.6:1, secondary text
4.9–8.5:1, chips and accents 5.0–8.8:1 (light accents for seas, temp and freshwater were darkened to pass).
Reduced motion stops the wind drift and needle transition. All drawings have text equivalents.

## Performance (measured 13 Nov 2026 on this box)

| | Prototype `/lab/tiles` | Homepage `/` (for reference) |
|---|---|---|
| Lighthouse mobile performance | 96, 96 | 85–89 |
| FCP / LCP | 1.8–2.0 s / 2.4 s | 2.4–3.0 s / 3.4–3.5 s |
| CLS (Lighthouse) | 0 | 0.003 |
| TBT | 30–140 ms | 0 ms |
| Total transfer | 228 KB (mostly fonts + API JSON) | 442 KB (map, tiles, fonts) |

The page is not a like-for-like replacement (no map), so the useful numbers are the **costs the tile
styling would add** to the real dashboard:
- CSS: the tile system is about 10.7 KB raw / 3.1 KB gzipped, of which the SVG textures (light and dark) are 3.3 KB raw.
- JS: renderers are ~19.6 KB raw / 6.7 KB gzipped, but most of that duplicates what `dashboard.js` already
  does; merged, the added JS would be the compass, swell, meter and pool drawings, roughly 2–3 KB gzipped.
- No new requests, fonts or images. Textures are CSS backgrounds on a pseudo-element, painted once per tile.
- Paint: one composited animation (wind texture `transform`, GPU layer, ~0 main-thread cost); paused off
  screen and with reduced motion. `contain: layout paint` on each tile keeps repaints local.
- Playwright CLS on the prototype after reserving loaded heights: 0 at 390, ≤0.0007 at 768/820/1024/1280,
  light and dark. Early versions hit 0.33 in Lighthouse because the top bar wrapped once webfonts loaded;
  fixed by not letting it wrap.

## If Ed likes it: rollout plan (needs approval)
1. Pick per-tile identities to keep (they are independent).
2. Port the CSS into `styles.css` behind a `data-tiles="v2"` attribute, reuse `dashboard.js` data, and A/B
   screenshots plus CLS and Lighthouse at 390/768/820/1024/1280 light and dark before deploy.
3. Keep the current compass size on desktop (the production compass is larger and reads well there).
