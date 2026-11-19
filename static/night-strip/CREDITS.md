# Final night-strip prototype (private, local only)

Opt-in: `?strip=1&night=1` (natural photo and chart, in day or night; Coastal blue tokens paint in dark mode only).
`?strip=natural` is an alias for `?strip=1`; `?night=b` is an alias for `?night=1`. No A, daytime tint option, or phone chart gate.
Night only: a single continuous CSS overlay, #0F2B44 at 38% opacity, softens both photo halves; the credit remains above it.
Image files, crops and dimensions are unchanged by this presentation layer.
Plain `/` has no extra image requests or strip element. Nothing is deployed.

## Ed Cogdell photograph

- Photographer / owner: Ed Cogdell, The Coastal Brief. Owner-supplied November 19, 2026, approved for site use.
- Credit shown exactly: **Photo: Ed Cogdell / The Coastal Brief**
- Sound-side water, two wooden docks, marsh grass and red glasswort; no boat. Location unconfirmed.
- Original: `/workspace/design-night-1119/source/ed-sound-docks-marsh.jpg`, 1500 × 532, 182,031 bytes;
  SHA-256 `679293a60d29dc4b1d6c3f1329cb8282f24182f4fb43b1bcd182c1466431005c`. Original / EXIF not committed.
- Processing: crop, Lanczos resize and compression only. No tint, color adjustments, retouching, or generated pixels.
- Phone crop moved down 44 px: (0,194,1500,532), previously (0,150,1500,489).
- Tablet/wide crop moved down 64 px and grew 14 px taller: (0,262,1500,481), previously (0,198,1500,403).
  This reveals more red marsh while retaining the docks and water. At widths other than 390/768, cover-fit uses 75% vertical position.
- Each crop is cut at original x=750 into left/right halves that reconstruct one continuous photo.
  Two half-width `<picture>` elements stay smaller than the forecast text (LCP), without reducing visible strip size.
  Images preload in `<head>` with media-matched AVIF srcsets, high priority, explicit dimensions, async decoding; no lazy-loading.
- Phone total rendered sizes: 390×88, 780×176, 1170×264 (1x/2x/3x at 390 CSS px).
- Tablet total rendered sizes: 768×112, 1536×224, 2304×336 (1x/2x/3x at 768 CSS px).
  The 2x/3x versions are Lanczos resized from the 1500px original, not additional captured detail.
  WebP and JPEG fallback for every candidate.
- Compression (AVIF / WebP / JPEG quality): 1x 60/78/80, intermediate 50/70/74, high-density 42/62/68.

| File | Dimensions | Bytes |
|---|---:|---:|
| docks-phone-l-195.avif | 195 × 88 | 2,741 |
| docks-phone-l-195.jpg | 195 × 88 | 3,991 |
| docks-phone-l-195.webp | 195 × 88 | 2,520 |
| docks-phone-l-390.avif | 390 × 176 | 5,606 |
| docks-phone-l-390.jpg | 390 × 176 | 11,226 |
| docks-phone-l-390.webp | 390 × 176 | 6,664 |
| docks-phone-l-585.avif | 585 × 264 | 7,219 |
| docks-phone-l-585.jpg | 585 × 264 | 19,384 |
| docks-phone-l-585.webp | 585 × 264 | 11,468 |
| docks-phone-r-195.avif | 195 × 88 | 2,873 |
| docks-phone-r-195.jpg | 195 × 88 | 4,059 |
| docks-phone-r-195.webp | 195 × 88 | 2,526 |
| docks-phone-r-390.avif | 390 × 176 | 5,733 |
| docks-phone-r-390.jpg | 390 × 176 | 11,075 |
| docks-phone-r-390.webp | 390 × 176 | 6,300 |
| docks-phone-r-585.avif | 585 × 264 | 6,844 |
| docks-phone-r-585.jpg | 585 × 264 | 18,327 |
| docks-phone-r-585.webp | 585 × 264 | 10,164 |
| docks-wide-l-1152.avif | 1152 × 336 | 13,012 |
| docks-wide-l-1152.jpg | 1152 × 336 | 38,828 |
| docks-wide-l-1152.webp | 1152 × 336 | 20,958 |
| docks-wide-l-384.avif | 384 × 112 | 6,175 |
| docks-wide-l-384.jpg | 384 × 112 | 9,090 |
| docks-wide-l-384.webp | 384 × 112 | 6,152 |
| docks-wide-l-768.avif | 768 × 224 | 11,215 |
| docks-wide-l-768.jpg | 768 × 224 | 24,493 |
| docks-wide-l-768.webp | 768 × 224 | 14,008 |
| docks-wide-r-1152.avif | 1152 × 336 | 12,378 |
| docks-wide-r-1152.jpg | 1152 × 336 | 37,110 |
| docks-wide-r-1152.webp | 1152 × 336 | 19,256 |
| docks-wide-r-384.avif | 384 × 112 | 6,277 |
| docks-wide-r-384.jpg | 384 × 112 | 9,194 |
| docks-wide-r-384.webp | 384 × 112 | 6,292 |
| docks-wide-r-768.avif | 768 × 224 | 10,619 |
| docks-wide-r-768.jpg | 768 × 224 | 23,896 |
| docks-wide-r-768.webp | 768 × 224 | 13,198 |

## NOAA chart texture

Derived from existing `/branding/masthead-chart.webp`: NOAA Chart 11545, Beaufort Inlet and Part of Core Sound;
Lookout Bight. NOAA Office of Coast Survey Historical Map & Chart Collection; public domain / CC0. Not for navigation.
See `docs/IDENTITY.md`. The Nov 14 phone restriction is superseded **only for this opt-in combination** by Ed's November 19 approval.
`chart-560.webp`: 560×168, 7,370 bytes, resized from existing 800×240 / 13,466 byte crop,
thresholded alpha (the original is a 1-bit white mask), lossless WebP. Same faint opacity, smaller download on phones;
tablets retain the original texture. No additional service, font, or photography.
