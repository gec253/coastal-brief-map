# Night-strip prototype: image credits (design/night-strip-1119, private)

Preview only: the strip renders only with `?strip=natural` or `?strip=tint` on the homepage. Nothing here is deployed.

## Coastal photo strip: Ed Cogdell (owner-supplied, approved)

- **Photographer / owner:** Ed Cogdell, The Coastal Brief. Supplied by Ed through Scout on Nov 19, 2026 and approved for site use.
- **Credit shown in the strip:** "Photo: Ed Cogdell / The Coastal Brief"
- **What it shows:** sound-side water, two long wooden docks, marsh grass and red glasswort in the foreground, wide sky. No boat.
- **Location:** not confirmed, so no place name appears in the caption or alt text.
- **Original:** `ed-sound-docks-marsh.jpg`, 1500 × 532 JPEG, 182,031 bytes,
  SHA-256 `679293a60d29dc4b1d6c3f1329cb8282f24182f4fb43b1bcd182c1466431005c`. Kept out of git (it carries camera
  EXIF; only derivatives are committed). Held at `/workspace/design-night-1119/source/` on the design box.
- **Processing:** crop, resize and compression only (Pillow, LANCZOS; EXIF not copied to derivatives). The
  Carolina-blue treatment is a CSS overlay (`#4B9CD3`, `mix-blend-mode: color`, 38%) plus a light CSS
  filter; the files themselves are not tinted or retouched.

| file | crop of original (x0, y0, x1, y1) | size | use |
|---|---|---|---|
| docks-phone-800.webp / .jpg | 0, 150, 1500, 489 (4.42:1) | 800 × 181 | phones (< 640px) |
| docks-phone-1200.webp / .jpg | same | 1200 × 271 | phones, 2x/3x |
| docks-wide-1000.webp / .jpg | 0, 198, 1500, 403 (7.32:1) | 1000 × 137 | 640px and up |
| docks-wide-1500.webp / .jpg | same | 1500 × 205 | 640px and up, 2x |

## Masthead chart texture (existing asset, unchanged)

`/branding/masthead-chart.webp`: crop of NOAA Chart 11545 (Beaufort Inlet and Part of Core Sound; Lookout Bight),
NOAA Office of Coast Survey Historical Map & Chart Collection, public domain / CC0. Not for navigation. See
`docs/IDENTITY.md`. With `?chart=1` the prototype draws it faintly behind the nameplate on phones as well.
