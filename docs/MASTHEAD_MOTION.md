# Masthead motion spec

A reusable signature for The Coastal Brief: a thin gold line moves like an ocean swell across deep navy and settles into a masthead rule or horizon. The nameplate is already painted in the first frame (never `opacity: 0` on the type, so LCP is not held back). The motion is decorative, CSS/inline-SVG only, and finishes in one second or less.

This document is the motion spec for the three private concepts on `/preview/masthead?c=a|b|c` (`design/masthead-preview`). The same SVG mark and timings can later be reused for video and other media. Public pages are unchanged.

## Palette and mark

- Navy `#071C29`, ivory `#F3E6D0`, brass `#C4A36A`.
- Inline SVG, `viewBox="0 0 1200 36"`, two paths plus a glint:
  - `.wave-swell` — a shallow swell, `M0 20 C 140 20, 220 8, 360 14 S 560 30, 720 18 S 960 8, 1200 20`
  - `.wave-settle` — a straight horizon, `M0 20 L1200 20`
  - `.wave-glint` — a small gold circle that travels the path (`offset-path` / `offset-distance`)
- Reserved slot: 18–24px tall in every state (play, settled, reduced motion). Zero CLS.
- Texture (tablet and desktop only): existing NOAA Chart 11545 Lookout Bight crop, public domain / CC0, not for navigation. See `docs/IDENTITY.md`.

## Playback rules

- Whole reveal ≤ 1s. Easing: `cubic-bezier(0.22, 0.8, 0.28, 1)` for the draw, slightly softer on the glint.
- `prefers-reduced-motion: reduce` shows the finished masthead with `animation: none`.
- First visit in a session: a tiny inline script in the preview document adds `html.mast-play` before the header is parsed, then writes `sessionStorage['cb-mast-reveal-' + concept]`. Repeat visits and no-JS get the server-rendered final state.
- Region changes and in-site navigation do not replay. The preview **Replay** button clears the session flag and retriggers `mast-play`.
- The dashboard and weather data render immediately. Scripts are unchanged from the homepage.

## Concept timings

### A — Classic Coastal Editorial (~800ms)

A typesetter’s rule being pulled. No swell, no traveling glint.

| Layer | Start | Duration | Motion |
|---|---|---|---|
| `.wave-settle` | 0ms | 700ms | `stroke-dashoffset` 1400 → 0 |
| `.mast-sheen` | 80ms | 800ms | soft ivory wash across the already-painted nameplate, then gone |
| `.wave-swell`, `.wave-glint` | — | — | hidden |

Settled state: a straight brass rule under the name and tagline.

### B — Modern Nautical (~900ms)

The line *is* a horizon. It draws as a shallow swell and stays curved. A specular glint travels the curve.

| Layer | Start | Duration | Motion |
|---|---|---|---|
| `.wave-swell` | 0ms | 780ms | `stroke-dashoffset` 1400 → 0 |
| `.wave-glint` | 120ms | 800ms | `offset-distance` 0% → 100%, opacity 0–1–0 |
| `.wave-settle` | — | — | hidden |

Settled state: the gentle swell remains as the horizon under a left-aligned, uppercase nameplate.

### C — Coastal Editorial Hybrid, flagship (~1000ms)

A swell crosses, a glint travels, the curve settles into a straight rule, and a sheen passes over the type.

| Layer | Start | Duration | Motion |
|---|---|---|---|
| `.wave-swell` | 0ms | 640ms draw, then 280ms fade | dashoffset draw, then opacity 1 → 0 |
| `.wave-glint` | 140ms | 700ms | travels the swell path, then vanishes |
| `.wave-settle` | 480ms | 500ms | fades in while drawing, becomes the rule |
| `.mast-sheen` | 280ms | 700ms | stronger ivory specular across the nameplate |

Settled state: straight brass rule under the mixed-case Fraunces nameplate and italic tagline. This is the mark to reuse for video bumpers: hold 8–12 frames on the settled rule after the sheen exits.

## Implementation notes for other media

- Animate only `stroke-dashoffset`, `transform`, `opacity`, `offset-distance`, and `clip-path` / masks on decorative layers. Do not hide the nameplate with `opacity: 0`.
- Path length used for dashes is 1400 (longer than the 1200-wide viewBox so a swell is fully covered).
- iPhone Safari: `offset-path` is used only for the glint (B and C). The rule itself is stroke animation, which is widely supported. If `offset-path` is missing, the glint stays at opacity 0 and the draw still reads.
- Source CSS: `preview/masthead/masthead.css`. Source mark: `preview/masthead/header.html`.
