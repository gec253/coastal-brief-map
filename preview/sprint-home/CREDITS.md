# Sprint homepage preview: photo credits and sources

Preview only (`/preview/home-*`, cookie-gated, noindex). Nothing here is deployed.

## Bodie Island Lighthouse at sunrise (local files, public domain)

- **Source page:** https://npgallery.nps.gov/AssetDetail/3011f0d3-bb6a-4b82-8fef-ca0b654e8040
- **Publisher:** National Park Service, NPGallery
- **PhotoCredit field:** "Cape Hatteras National Seashore". The credit goes to the park unit. No individual photographer is named, and there is no public contributor or third-party copyright holder.
- **Constraints field:** "Public domain:Full Granting Rights"
- **Access:** Public Can View
- **Created:** October 13, 2023
- **Original:** 1600 × 1200 PNG
- **Checked:** November 15, 2026
- **Credit shown on the page:** "Photo: National Park Service, Cape Hatteras National Seashore (public domain)"
- **Conditions:** NPS public-domain works need no license. Keep the NPS credit as a courtesy. Do not imply that NPS endorses The Coastal Brief. Do not crop or edit in a way that misrepresents the scene.
- **Derivatives in `photos/`:** These were resized and re-encoded only, with no retouching.

| file | size | sha256 |
|---|---|---|
| bodie-sunrise-800.avif | 800×600 | 692847c674a5d74a7790e96b65a7f73dc96ed4840d7ba373a7db3cb38ea109e9 |
| bodie-sunrise-800.webp | 800×600 | 9a27a82b485d8e20420bcb9e6d7b8a9f29768c6c981251c52d12de8b6cd8c77a |
| bodie-sunrise-1280.avif | 1280×960 | 2b1b29e0f804c1b07fc95fb9f905e10e941eab1f8d53bd65537d609a4d64005a |
| bodie-sunrise-1280.webp | 1280×960 | 5ad828d8f5edebdae1d86b55ac5f8a811996f27218d4ff90c4cb98db2e439c2c |

The `<img>` tags declare the original 1600×1200 ratio as width/height, so the layout never shifts.

## Fishing pier, Falls Lake, North Carolina (local files, CC BY-SA 2.0)

- **Title:** "Falls Lake"
- **Author:** Sergiy Galyonkin
- **Date:** March 5, 2023
- **Source:** https://www.flickr.com/photos/sergesegal/52741376400/
- **License:** Creative Commons Attribution-ShareAlike 2.0 Generic (CC BY-SA 2.0), https://creativecommons.org/licenses/by-sa/2.0/
- **Original file used:** `/workspace/falls-lake/Falls_Lake_Galyonkin_52741376400.jpg`, 9528 × 6328 px. Ed's pick, supplied through Scout. I downloaded nothing.
- **Original SHA-256:** 54e27cdd2b952fe432de46c362ee237c0d43fe28e2830fa81a75ecc5f7d78f25 (checked before any processing on Nov 15, 2026)
- **Caption shown:** "Fishing pier, Falls Lake, North Carolina". The county isn't stated, because Falls Lake spans three counties and the pier's county isn't verified.
- **Credit shown:** "Photo: Sergiy Galyonkin, CC BY-SA 2.0 (cropped and adjusted)"
  - "Sergiy Galyonkin" links to the Flickr source.
  - "CC BY-SA 2.0" links to the license deed.
  - Both links have 44 px-tall tap areas.
- **Changes made (this is an adaptation):**
  - **Crop:** x=2466, y=186, w=5208, h=3906 in original pixels (4:3), centred on the pier, the people, the still water and the woods. It removes the photographer's watermark at lower left and the rocky low-water foreground. Part of the riprap shoreline at the pier's right still shows at the bottom right.
  - **Colour:** gentle neutral correction back toward natural, done the same way across the whole frame:
    - per-channel levels, black point R12 G12 B5 and white point R248 G252 B248
    - gamma 1.07 (v7final: a very subtle extra lift to shadows and midtones, from R14 G14 B6 / gamma 1.04)
    - saturation 0.92, a luma-preserving blend toward Rec.709 grey
  - No added saturation, sharpening, vignette, filters or local edits. Resized with Lanczos.
  - The exact parameters are in `falls-lake-grade-params.json`, and the script that applied them is `falls_lake_grade.py`.
- **License of the adaptation:** the cropped and colour-adjusted image is itself licensed **CC BY-SA 2.0** (share-alike). Anyone may reuse it under the same terms, with attribution to Sergiy Galyonkin and a note of the changes.
- **Where it appears:** it is the hero photo on the Falls Lake view only (Jordan Lake shows no lake hero) and fills the wide mosaic cell on river views (Neuse River). It is not used on saltwater views.
- **Derivatives in `photos/`:**

| file | size | sha256 |
|---|---|---|
| falls-lake-pier-800.avif | 800×600 | 63d7d5f7784bcfa2c1bbd28a043b6745cf2f1c532ac26e80181ce2aa968dfdea |
| falls-lake-pier-800.webp | 800×600 | 0b6bdd0ee2ba3425dfa7b6372214f85c20047e7a8aed369c24b20d4f656e44d7 |
| falls-lake-pier-1280.avif | 1280×960 | a58b58dd560d0a068e91e69c16ce970b1a0bd97c6fe32c9761687de7e52128dc |
| falls-lake-pier-1280.webp | 1280×960 | 92450b1bd5ff2e8eaef083bc7d2137aef83d026116b3b5c67079f0d0eff95500 |

## Community photos (served from the existing approved store, not copied here)

These are approved Catch Wall and Coastal Life uploads. They are read through the same approved-photo lookup the site already uses.

Credit rule:
- Show the submitter's name only when the record stores one: "Photo: {name} · {collection}".
- Otherwise show "Community photo · Catch Wall" or "Community photo · Coastal Life".
- Never invent a name.

| id (prefix) | collection | caption as stored | used in hybrid |
|---|---|---|---|
| 3e41ed83 | Catch Wall | Red Drum · New Bern · Neuse River | mosaic (lead) |
| bcd8fba5 | Catch Wall | Striped Bass · Roanoke River | mosaic |
| caec2542 | Coastal Life | Rx Chicken & Oysters · Wilmington · Wrightsville Beach | mosaic |
| a225cada | Catch Wall | Weldon | mosaic (salt), horizon (fresh) |
| 89eef7f7 | Coastal Life | location "Rx Chicken & Oysters", region "Wilmington · Wrightsville Beach", caption empty (same fields as caec2542) | mosaic (tall cell), shown with its stored caption; because it repeats caec2542's, the location is shown once (on the first frame) and this frame carries only its credit |

Per Ed (Nov 15, 2026), the 89eef7f7 caption stays as stored; there is no caption override. Nothing was written to the submission, moderation data or Supabase.

No AI, stock or scraped images are used anywhere.

## JPEG fallbacks for the daily featured photo (design/photo-rotation)

Re-encoded from the existing 1280 WebP derivatives above (quality 80, progressive; 800 px by Lanczos resize). No new source images, no retouching. Same credits and licenses as above.

| file | size | sha256 |
|---|---|---|
| bodie-sunrise-1280.jpg | 1280×960 | aaeb9821c3749f9db06a7120ca7eb8ef11f709519df98a58e820b42dc4aac6fe |
| bodie-sunrise-800.jpg | 800×600 | 23dad49f682bc2492aa6a2a5faba0bdf5dffdba1dce50b181761f99183d22f26 |
| falls-lake-pier-1280.jpg | 1280×960 | 16837d123a0901271e25107ca9623dc272300383fd55bdcd4e26097187116844 |
| falls-lake-pier-800.jpg | 800×600 | 562a26b0fa09e7d798b53f7db3665e0c93002536956d334dd865d545ac94b450 |
