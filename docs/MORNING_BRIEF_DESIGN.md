# Morning Brief presentation

Private presentation work for `/brief`, still behind `MORNING_BRIEF_ENABLED` or
a preview key. Wording, sources, station IDs and build rules in `brief.py` are
unchanged. Glance values are parsed from the existing brief lines, not
recalculated. Nothing here is public until the flag is turned on.

The region-picker / header navigation from the design prototype is **not**
included here. That waits for a baseline Lighthouse check on the homepage.

## Layout

The page is a short morning read: issue time and per-reading freshness first,
then a restrained advisory banner, a compact at-a-glance strip, the section
prose, an inactive ad placeholder, and the Captain’s take.

- **At a glance** uses the same typographic system as the Tiles v2 instruments
  (Barlow Condensed numbers, tracked-caps names, Observed / Predicted / Forecast
  chips). Seas and swell stay separate. “Tide next” is labeled **predicted**.
  Freshwater rain is **observed**; the NWS air high is **forecast**.
- **Advisories** sit in a reserved-height banner above the strip and above the
  ad slot. Clear and “could not check” states use a quieter treatment.
- **Full readings** (the prose sections under the strip) start **collapsed on
  phones (max-width 600px)** so the same numbers are not shown twice above the
  fold. The control is a native `<details>` / `<summary>` with a 44 px target.
  On tablet, desktop (min-width 601px) and in print, the sections are open.
- **Captain’s take** is set apart with a dock-wood rule and a visible
  **INTERPRETATION** label. The “not an observation / not a fishing report”
  line stays. NOAA non-endorsement and “not a fishing report” remain in the
  footer.
- **Share**: `og:` / Twitter tags (existing `branding/og-preview.png`, no new
  photos). **Print**: `@media print` in `brief.css` hides chrome and the ad
  slot, uses a white ink-saving layout, keeps the take with its label, and
  keeps the full readings open.
- **Themes**: light and dark, plus a muted river-green / earth palette when
  `data-water="freshwater"`. The brief loads `brief.css` only (not the
  dashboard stylesheet). Fonts are the ones already in `/fonts`.
- The in-page region links list Crystal Coast and Hatteras always; Falls Lake
  is linked only when freshwater preview is on (`include_fresh`).

## Files

- `brief.py` — `page()` markup, glance/advisory helpers, phone collapse
- `brief.css` — brief + print styles
- `server.py` — passes `include_fresh` into `page()` so Falls Lake is linked
  only when that preview is on
- `docs/MORNING_BRIEF_DESIGN.md` — this note
- `tests/test_brief_design.py`

Not in this change: `region-nav.js`, homepage `styles.css` / `index.html` /
`dashboard.js` nav work, or the additive `freshwater` list on `/api/regions`.
