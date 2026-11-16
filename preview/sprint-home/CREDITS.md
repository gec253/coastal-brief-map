# Sprint homepage preview: photo credits and sources

Preview only (`/preview/home-*`, cookie-gated, noindex). Nothing here is deployed.

The daily featured-photo rotation lives in `static/featured-photos/` (manifest: `photo-rotation.json`). Only landscape photographs with `approved: true` rotate, one per America/New_York calendar day. Community Catch Wall and Coastal Life photographs stay in the mosaic; they are not part of the daily rotation.

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

These are approved Catch Wall and Coastal Life uploads. They are read through the same approved-photo lookup the site already uses. They stay in the Catch Wall / Coastal Life mosaic only; they are not in the daily featured-photo rotation.

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

## Daily featured photo rotation (`static/featured-photos/`)

Rights-verified North Carolina photographs for the private Hybrid featured-photo prototype on `scout/photo-rotation`. Captions, locations, photographer names and licenses are taken from the source pages (date accessed 15 November 2026, America/New_York). No stock, AI-generated, or scraped images. Fall Lake imagery is labeled Falls Lake only; Jordan Lake imagery is labeled Jordan Lake only.

Shipped derivatives are AVIF, WebP and JPEG at 640, 1024 and 1600 pixels wide, plus a tiny blurred placeholder. A 2400-pixel set is included only when the JPEG is under about 400 KB. Variants were resized and re-encoded only (Lanczos), except Falls Lake (documented 4:3 crop, no further grade in this folder) and crabbing at Lake Mattamuskeet (see that entry).

On the page, CC BY and CC BY-SA credits link the photographer to the source page and the license name to the license deed.

### bodie-sunrise

- **Category:** heritage
- **Location (as stated by the source):** Bodie Island Lighthouse, Cape Hatteras National Seashore, North Carolina
- **Description / caption:** Sunrise at the Bodie Island Lighthouse, October 13, 2023.
- **Date of photograph:** October 13, 2023
- **Photographer / author:** National Park Service, Cape Hatteras National Seashore
- **Credit shown on the page:** "Photo: National Park Service, Cape Hatteras National Seashore (public domain)"
- **License:** Public domain
- **Source page:** https://npgallery.nps.gov/AssetDetail/3011f0d3-bb6a-4b82-8fef-ca0b654e8040
- **Original dimensions:** 1600 × 1200
- **Date accessed:** 2026-11-15 (America/New_York)

Derivatives in `static/featured-photos/bodie-sunrise/`:

| file | size | sha256 |
|---|---|---|
| bodie-sunrise-placeholder.jpg | 32×24 | f4085e3f20bb07a5608875996fddb02cd9ac5a12d07ba51df4e66369c0793425 |
| bodie-sunrise-640.avif | 640×480 | 561be542b26f6f481219b42186cb4b854a50c079fa85f9b09745e0774fb72370 |
| bodie-sunrise-640.webp | 640×480 | 2b89626a7045be6ceb0384f24b1524c42aa9d6072438ba3ef5f44f475aa1f66b |
| bodie-sunrise-640.jpg | 640×480 | 98f18861544c0ddf0faa39d1da20a6d01cff6ccab2c5d75a540625796eff5248 |
| bodie-sunrise-1024.avif | 1024×768 | e53130bfc336f9eee3fbfe9915dfac335c4a5e000a7cece4b9fb0331ae308607 |
| bodie-sunrise-1024.webp | 1024×768 | d69e4fda6a642a47956dced87698e6137c3ba0c32aa80346c86b81820949dbce |
| bodie-sunrise-1024.jpg | 1024×768 | ee58604f0aefeb11737d4360fef2811cd65b28cfd489bc34494f93b61818b8c1 |
| bodie-sunrise-1600.avif | 1600×1200 | 895ff1638f9049d553d12813206d83716c19472dd8fdb04e5a5e6c3320428c54 |
| bodie-sunrise-1600.webp | 1600×1200 | 1237cd8824f0b3430fa9a5a632cbace3818161b7afb1d82713f95fd5a4803532 |
| bodie-sunrise-1600.jpg | 1600×1200 | c818f783a8b8b42da0964df16db72f6f9d8fa5647b0f02b4ab49d6bbf8da34f4 |

### cape-lookout-sunrise

- **Category:** heritage
- **Location (as stated by the source):** Cape Lookout Lighthouse, Cape Lookout National Seashore, North Carolina
- **Description / caption:** The Cape Lookout Lighthouse on Cape Lookout National Seashore at sunrise, on the way out to sea.
- **Date of photograph:** June 24, 2019
- **Photographer / author:** Ldicktel
- **Credit shown on the page:** "Photo: Ldicktel, CC BY-SA 4.0"
- **License:** CC BY-SA 4.0, https://creativecommons.org/licenses/by-sa/4.0/
- **Attribution:** the photographer's name links to the source page; the license name links to the license deed.
- **Source page:** https://commons.wikimedia.org/wiki/File:Cape_Lookout_at_sunrise.jpg
- **Original dimensions:** 4032 × 3024
- **Date accessed:** 2026-11-15 (America/New_York)

Derivatives in `static/featured-photos/cape-lookout-sunrise/`:

| file | size | sha256 |
|---|---|---|
| cape-lookout-sunrise-placeholder.jpg | 32×24 | 53c782e8ac2d7fba173f412e8d67d1a329e1801afce99e8f6dbf8cdebb30ea92 |
| cape-lookout-sunrise-640.avif | 640×480 | 373f7e93aaad7eb21192e8b84f95980c013bc76a109da124994c2efe05ee5bf2 |
| cape-lookout-sunrise-640.webp | 640×480 | 1a4966747efd963b208b0ee7ac2af2ca3039ac7aa5cafcfdacd17b3828f854ea |
| cape-lookout-sunrise-640.jpg | 640×480 | e20ecc44e431cc86a07751b6a4802b9cbf257e4f60e81512c4af6e8fa7ffe586 |
| cape-lookout-sunrise-1024.avif | 1024×768 | 32e8b9002bbc720dc62d167a49042b7b91c07288d34f0407a864a046e958d7d8 |
| cape-lookout-sunrise-1024.webp | 1024×768 | 966175fe1ea16e7aab5444acfd9d3ed8ebc0e318670da63bd2f27b41c4fd35b8 |
| cape-lookout-sunrise-1024.jpg | 1024×768 | 54719b9ba01804092e2f2297decb538c92ee7943e03f7c1ad71037850fe802e9 |
| cape-lookout-sunrise-1600.avif | 1600×1200 | febd41cf3d12ecaaa972fb71e27e5371ddbe5676fc631374545eaaf8a3a9826c |
| cape-lookout-sunrise-1600.webp | 1600×1200 | d05e5bca64e9b7c4ffa4ae6720df82137c148e52d4941980e3a43d1b30d34fee |
| cape-lookout-sunrise-1600.jpg | 1600×1200 | 5f1df5eb0118c91269959cd46f6b7958328d057a3eeaa40ea095b6218dde8e94 |

### cape-hatteras-lighthouse

- **Category:** heritage
- **Location (as stated by the source):** Cape Hatteras Light Station, Cape Hatteras National Seashore, Buxton, North Carolina
- **Description / caption:** Cape Hatteras Light Station, Cape Hatteras National Seashore, Buxton, North Carolina.
- **Photographer / author:** Ken Lund
- **Credit shown on the page:** "Photo: Ken Lund, CC BY-SA 2.0"
- **License:** CC BY-SA 2.0, https://creativecommons.org/licenses/by-sa/2.0/
- **Attribution:** the photographer's name links to the source page; the license name links to the license deed.
- **Source page:** https://commons.wikimedia.org/wiki/File:Cape_Hatteras_Light_Station_(Lighthouse),_Cape_Hatteras_National_Seashore,_Buxton,_North_Carolina_(14268133980).jpg
- **Original dimensions:** 4000 × 3000
- **Date accessed:** 2026-11-15 (America/New_York)

Derivatives in `static/featured-photos/cape-hatteras-lighthouse/`:

| file | size | sha256 |
|---|---|---|
| cape-hatteras-lighthouse-placeholder.jpg | 32×24 | 5b47ff30f87f52d999b4f6509e9901b14761dc4ee5b9de3d36e2a6cac9cc2b91 |
| cape-hatteras-lighthouse-640.avif | 640×480 | efba60f6f6e7e4dcd164fd7912aba9a7c1c20874085ce1c34cb5106ed766244f |
| cape-hatteras-lighthouse-640.webp | 640×480 | 6683e5a5264ed702e5303c7dfd46afae7d2a1469637e34150ada58aea45d6f78 |
| cape-hatteras-lighthouse-640.jpg | 640×480 | 458d9b4f8c57b74fab64359b80b177eb4b3200a6953a4cef2c9d40145c53a7c8 |
| cape-hatteras-lighthouse-1024.avif | 1024×768 | b99ead252f45b65e7e40545cc87e9ddb29e697ea7484c17ba6260d808be27fba |
| cape-hatteras-lighthouse-1024.webp | 1024×768 | 2f8d23b33d80a5ab1e75951a9c79c6b6dcb51edec1119b5e63e67fe408fccc54 |
| cape-hatteras-lighthouse-1024.jpg | 1024×768 | 50daa684d5dc65e023fbfb24fecfd0fa354934181316de7938213c85722072ae |
| cape-hatteras-lighthouse-1600.avif | 1600×1200 | bd8e689c31d20c5b944ae5e8a21aad46bd8a42b3c88f70f1cdfd5c4a40eb688a |
| cape-hatteras-lighthouse-1600.webp | 1600×1200 | 61aa80c539b4e4fe166b6fd89c5a869fb63f10abad1f6c8c7288d609e470665a |
| cape-hatteras-lighthouse-1600.jpg | 1600×1200 | 15a20e11c71adffb4f2c6d56a4c9880c0fcf11f39afe19d63ba055b173114a06 |
| cape-hatteras-lighthouse-2400.avif | 2400×1800 | c2dda8d7118ecf6e275e51d316966c8afc94978c2efebae046255481c065bf32 |
| cape-hatteras-lighthouse-2400.webp | 2400×1800 | a7f0c4649e852604000688248457bd028fa4c37008ba93a0ed26b1e5a27e19de |
| cape-hatteras-lighthouse-2400.jpg | 2400×1800 | 9f247cce624101a5672675a4afa931d4d9616ba551415dbc47c135849ccbccca |

### currituck-beach-light

- **Category:** heritage
- **Location (as stated by the source):** Currituck Beach Lighthouse
- **Description / caption:** Currituck Beach Lighthouse.
- **Date of photograph:** September 1, 2012
- **Photographer / author:** Stryker33
- **Credit shown on the page:** "Photo: Stryker33, CC BY-SA 3.0"
- **License:** CC BY-SA 3.0, https://creativecommons.org/licenses/by-sa/3.0/
- **Attribution:** the photographer's name links to the source page; the license name links to the license deed.
- **Source page:** https://commons.wikimedia.org/wiki/File:Currituck_Beach_Light.JPG
- **Original dimensions:** 3296 × 1854
- **Date accessed:** 2026-11-15 (America/New_York)
- **Notes:** The source names the subject as Currituck Beach Lighthouse and does not state a town.

Derivatives in `static/featured-photos/currituck-beach-light/`:

| file | size | sha256 |
|---|---|---|
| currituck-beach-light-placeholder.jpg | 32×18 | dfc785420d197457d0c1f1d9099ec6c3dd95b24a5b4b8032e02dc0c8a248ff52 |
| currituck-beach-light-640.avif | 640×360 | 3f3cdab5f8ae9ba55e1abaa063c1f6537cd3d57d98de36ea897ce5122dac28e4 |
| currituck-beach-light-640.webp | 640×360 | c5822f0b1932ad0e3076de7a20d04be4bb6d3363319f048a32724467aefe5525 |
| currituck-beach-light-640.jpg | 640×360 | dc1245ee031246a838e08c2bd184ef7d1984e2c6037a1a6bbda0e1e5be22f97d |
| currituck-beach-light-1024.avif | 1024×576 | a017d95bf7900b691bff3edb39cdd48415e4898bac41e7a4e87af1354b0925fd |
| currituck-beach-light-1024.webp | 1024×576 | aab5ec6d36f439cefa652eb5a496eb48a4c395bfa94c663422a52adcc69b9d13 |
| currituck-beach-light-1024.jpg | 1024×576 | 8ab48d07c17c8808fc228ee1ed869ffe7bf74be0985e8f185ba8b06c3260a130 |
| currituck-beach-light-1600.avif | 1600×900 | ac32c39db6f1e38cab7ff83829887006d46a09510754d48cd791a4cc6aca332a |
| currituck-beach-light-1600.webp | 1600×900 | 312e683e5e292cb94115eef635257c0f4cb7a70683491f3d3202fed684d54da7 |
| currituck-beach-light-1600.jpg | 1600×900 | 4fd4d702753d8ff4cbdaf011d5ec7e635c6bd98ffe9982cd53d5f02d491946ff |

### oak-island-light

- **Category:** heritage
- **Location (as stated by the source):** Oak Island Lighthouse, Caswell Beach, North Carolina
- **Description / caption:** Oak Island Lighthouse at Caswell Beach, North Carolina.
- **Date of photograph:** August 3, 2016
- **Photographer / author:** Thomas Shaw
- **Credit shown on the page:** "Photo: Thomas Shaw, CC BY-SA 4.0"
- **License:** CC BY-SA 4.0, https://creativecommons.org/licenses/by-sa/4.0/
- **Attribution:** the photographer's name links to the source page; the license name links to the license deed.
- **Source page:** https://commons.wikimedia.org/wiki/File:Oak_Island_Light_North_Carolina.jpg
- **Original dimensions:** 6000 × 4000
- **Date accessed:** 2026-11-15 (America/New_York)

Derivatives in `static/featured-photos/oak-island-light/`:

| file | size | sha256 |
|---|---|---|
| oak-island-light-placeholder.jpg | 32×21 | 52c414e153f3765afe36f636154927e8c82b7d47e0bae396cf2bebb915291438 |
| oak-island-light-640.avif | 640×427 | 8ac4000e7d111cbdc8a89dc14938c8c61a34e3ff2d92763c1c413bbd82caebcc |
| oak-island-light-640.webp | 640×427 | 4534d63cbead62a99963b31f6f2b6e671b76bf7b730121d1de0cff182b7cede4 |
| oak-island-light-640.jpg | 640×427 | eb4463cb1ed56c6876e522f5f351ed08cb90c5076edd9db0c82c98ec333b96ac |
| oak-island-light-1024.avif | 1024×683 | 6d4641e77f0fa56189467e25f8b2305962d57c31a42d708aa3b1ef64c75e3f85 |
| oak-island-light-1024.webp | 1024×683 | b45dd956d84b50be89df8e754cb5d89ecc7ae7760475c4dbcdde1271a7b3c061 |
| oak-island-light-1024.jpg | 1024×683 | c53b39e167546f50612ad03790ca9c59421fd1b09ea0e1e0d99620a5163bc664 |
| oak-island-light-1600.avif | 1600×1067 | adbf9a6d28beb0370870b1bb555f82eca8cd5a2d313b9805788b65a59fdc0c4d |
| oak-island-light-1600.webp | 1600×1067 | 45b82850823d77f773daf8c5202eef0b6ea2955255b2f6f1d66650743741be7a |
| oak-island-light-1600.jpg | 1600×1067 | 4f0a660fe8c7ab8991c06c99099845521a3c6ccfe2c799b36b6288635c9b2abe |

### autumn-sunrise-caha

- **Category:** lifestyle
- **Location (as stated by the source):** Cape Hatteras National Seashore, North Carolina
- **Description / caption:** The sun over the Atlantic Ocean at Cape Hatteras National Seashore.
- **Date of photograph:** November 21, 2013
- **Photographer / author:** Cape Hatteras National Seashore (U.S. National Park Service)
- **Credit shown on the page:** "Photo: U.S. National Park Service, Cape Hatteras National Seashore (public domain)"
- **License:** Public domain
- **Source page:** https://commons.wikimedia.org/wiki/File:Autumn_Sunrise_(14943845957).jpg
- **Original dimensions:** 4718 × 2653
- **Date accessed:** 2026-11-15 (America/New_York)

Derivatives in `static/featured-photos/autumn-sunrise-caha/`:

| file | size | sha256 |
|---|---|---|
| autumn-sunrise-caha-placeholder.jpg | 32×18 | c234de42b8fdf34421cf3441573961a73049ce385b9b8c7409ad8894ebd65d70 |
| autumn-sunrise-caha-640.avif | 640×360 | 3d408502f7ae7eee8526b8a4ffd49bc9bdec488c04ac4259b4d22a89bce156a7 |
| autumn-sunrise-caha-640.webp | 640×360 | 088a177994e459f00a85b6132b37703a1653a47c8073538ac1ac280bd56962ec |
| autumn-sunrise-caha-640.jpg | 640×360 | 547cbbaa14226d0331d64818cbafa341cd3f2b9f7720751f51afc2305f3b5264 |
| autumn-sunrise-caha-1024.avif | 1024×576 | b2bd0d06da0aa82d5129256bc9377708edc6e7bf9f449ac1d7a968b71b5df38a |
| autumn-sunrise-caha-1024.webp | 1024×576 | 85e16591c3dc6a70c7e021395fad9d93e8bc0c38c4027faa2dc38458cc0cfb81 |
| autumn-sunrise-caha-1024.jpg | 1024×576 | fc394bc00473363ecefe06ed186fdb44a012c146b4b86e184e643f7a4a486096 |
| autumn-sunrise-caha-1600.avif | 1600×900 | a603973fe10636724c646fe3c1bec8e5948289cc4b7d18994b92a0f348c68cfe |
| autumn-sunrise-caha-1600.webp | 1600×900 | e7c9d2d0b1c0870414c21eecad8c15a1504dd21fd3f8d048675f62a0c6deef6e |
| autumn-sunrise-caha-1600.jpg | 1600×900 | 7789124824e4aa28b3fb8fce3379052041a0dd84452c3e5bbdac0f05053b6f69 |
| autumn-sunrise-caha-2400.avif | 2400×1350 | e37ad01460d153983c59a8dcb3ccf01b00739949bc1d3e96e182b2c81ade1123 |
| autumn-sunrise-caha-2400.webp | 2400×1350 | de2a26b50e695b02f84c6a8ed8b69185b998d05cb53a87eddf3e81f2befd9afa |
| autumn-sunrise-caha-2400.jpg | 2400×1350 | 3178c505d3756c221756b8f91a8bc0172f584fdfe5fda51bdb0d8b09eee03cbb |

### dawn-at-topsail

- **Category:** lifestyle
- **Location (as stated by the source):** Topsail Island, North Carolina
- **Description / caption:** Pre-sunrise at Topsail Island, North Carolina.
- **Date of photograph:** June 24, 2014
- **Photographer / author:** William Poteat
- **Credit shown on the page:** "Photo: William Poteat, CC BY-SA 4.0"
- **License:** CC BY-SA 4.0, https://creativecommons.org/licenses/by-sa/4.0/
- **Attribution:** the photographer's name links to the source page; the license name links to the license deed.
- **Source page:** https://commons.wikimedia.org/wiki/File:Dawn_at_Topsail.jpg
- **Original dimensions:** 3872 × 2592
- **Date accessed:** 2026-11-15 (America/New_York)

Derivatives in `static/featured-photos/dawn-at-topsail/`:

| file | size | sha256 |
|---|---|---|
| dawn-at-topsail-placeholder.jpg | 32×21 | 44b132f5830d32202c3fd304dfd4d47da5d15fffb942c81d62c62dcbd502c4f4 |
| dawn-at-topsail-640.avif | 640×428 | 41e80c20fbe11732895592fe1e8af1e3944f9341fac833d3fa6b16680780341a |
| dawn-at-topsail-640.webp | 640×428 | 35f457b157be0b805efceb847a1ca053642cd68aa24890b4f6d785e2d399c413 |
| dawn-at-topsail-640.jpg | 640×428 | 1c6e87ef0853ff0f3527f82d0a041432fc69ebef8101832abc61f0804c868c24 |
| dawn-at-topsail-1024.avif | 1024×685 | 8b336fb50ce9340314d0d844f973efe36e2cd32b4c662168429e0494864125e2 |
| dawn-at-topsail-1024.webp | 1024×685 | fd4fb1b53ffe4f4fad6033347f18152808bd2d4134b4ddbc0efca465867419a9 |
| dawn-at-topsail-1024.jpg | 1024×685 | 33fd1c9458d3e5dda47a04c062e5b5b8ed3596c8836b6fab11aaf0989ee5c890 |
| dawn-at-topsail-1600.avif | 1600×1071 | e46773b5b45c196337f9aae4f2e3dc5d122be118efdbb7b2a82a6c8c1f86a4c5 |
| dawn-at-topsail-1600.webp | 1600×1071 | c073d2c52b7e2d3f2c05d8524f67ba419954bdff8926a314d09bb5b0b6cb2d3f |
| dawn-at-topsail-1600.jpg | 1600×1071 | 24907f510c87388f0349a77461781857789e3f0ed87e558607ae21f91bfcdf8d |
| dawn-at-topsail-2400.avif | 2400×1607 | 84a234413c1e51d625d11339af28e3d632bbd388370b7b303024e172cd93de61 |
| dawn-at-topsail-2400.webp | 2400×1607 | 97faed6b1ac36c6070e61ebe040657ca5677a5adbd12e87125ec8a965a82c0c9 |
| dawn-at-topsail-2400.jpg | 2400×1607 | 5d96f2d76af13fb42ab355bf905f3380683f5f449ae27883413cc525d0ff031a |

### sea-oats-sunset-beach

- **Category:** lifestyle
- **Location (as stated by the source):** Sunset Beach, North Carolina
- **Description / caption:** Sea oats at Sunset Beach, North Carolina.
- **Photographer / author:** Ryan Hagerty
- **Credit shown on the page:** "Photo: Ryan Hagerty/USFWS (public domain)"
- **License:** Public domain
- **Source page:** https://www.fws.gov/media/sea-oats-sunset-beach-north-carolina-0
- **Original dimensions:** 5760 × 3840
- **Date accessed:** 2026-11-15 (America/New_York)

Derivatives in `static/featured-photos/sea-oats-sunset-beach/`:

| file | size | sha256 |
|---|---|---|
| sea-oats-sunset-beach-placeholder.jpg | 32×21 | c0771a5ea8203a0cd48e72b9d25a154abe50e386fee00cd32ae9bb8db5fa0aae |
| sea-oats-sunset-beach-640.avif | 640×427 | 43527332c996dcfcc41f7214cfdb2c609d0209887a4e15e95c9b8d96509326b8 |
| sea-oats-sunset-beach-640.webp | 640×427 | f37929d176c7568841d499396555516d7bdccf208802df69d24b29a8a588603b |
| sea-oats-sunset-beach-640.jpg | 640×427 | 397c208ac79778824452d351ad8eb65cc0245087da555ae97ccb8d2e3bfa98b9 |
| sea-oats-sunset-beach-1024.avif | 1024×683 | 42353ef57022c3a6a707e8e11c06a8c77d9c5fde88c4d99897476998d755b2ea |
| sea-oats-sunset-beach-1024.webp | 1024×683 | b796a427b8578975dd30f60d7b5bd425d3e44eb8ce89b0742bfa71c53bdb2a5a |
| sea-oats-sunset-beach-1024.jpg | 1024×683 | 8625526b62f0bdc4b5aa6d8ecb8d42960cd9bdacced2e5cd10f77aff879d59ac |
| sea-oats-sunset-beach-1600.avif | 1600×1067 | 31ed780444c87684f638c5d7165460d89bc33af77b09cb22d6abbf964f3f1a96 |
| sea-oats-sunset-beach-1600.webp | 1600×1067 | d97404c277403dc69046f1157697e238853149c8e06f3d0b0a33917e33216aa0 |
| sea-oats-sunset-beach-1600.jpg | 1600×1067 | 828993cccebc70e511f871d724b7b12839d83547f6ef1472f959015fb9f2da3f |
| sea-oats-sunset-beach-2400.avif | 2400×1600 | a1679f218e07e1135441d8cac36eaf9449bb14141a7f8465104efa07a57ed25c |
| sea-oats-sunset-beach-2400.webp | 2400×1600 | 6059d21af112cecbd31ec9f7b604208fae74e2a4839a48177ad99aab62e1607b |
| sea-oats-sunset-beach-2400.jpg | 2400×1600 | c72bf26e6d20a09bb112999bdc491da810a332fb84b31936dbddf64b5e1d8d31 |

### shrimp-boats-wanchese

- **Category:** saltwater
- **Location (as stated by the source):** Wanchese harbor, North Carolina
- **Description / caption:** Shrimp boats in the harbor at Wanchese, North Carolina.
- **Date of photograph:** May 2008
- **Photographer / author:** Geographer
- **Credit shown on the page:** "Photo: Geographer (public domain)"
- **License:** Public domain
- **Source page:** https://commons.wikimedia.org/wiki/File:Shrimp_Boats.JPG
- **Original dimensions:** 3872 × 2592
- **Date accessed:** 2026-11-15 (America/New_York)

Derivatives in `static/featured-photos/shrimp-boats-wanchese/`:

| file | size | sha256 |
|---|---|---|
| shrimp-boats-wanchese-placeholder.jpg | 32×21 | 208ee0649dc3b5b679ec7ee6bdeb7b8bedaac4d8a792919640d09fa5c2ade610 |
| shrimp-boats-wanchese-640.avif | 640×428 | 40ce42d2ab95c75e0e1c1aeac0a7213a15a158114eb71cb259c9964efbffd661 |
| shrimp-boats-wanchese-640.webp | 640×428 | d3a1d0d14af26d463e0977e8d22869acfa65ebc9a780a99ecd356543431d7463 |
| shrimp-boats-wanchese-640.jpg | 640×428 | 09ba5741752c5b36b60814917b4ab358f05adcfd10c57b59458f5f8bef61f6f1 |
| shrimp-boats-wanchese-1024.avif | 1024×685 | cfc87580f5c645f005617b0fb326ce769714a73173440033e4f4417747d42e9a |
| shrimp-boats-wanchese-1024.webp | 1024×685 | 4e06f9fae608e7b873105f804ee11f74f7cfa576c01e889d934045e4ad52134f |
| shrimp-boats-wanchese-1024.jpg | 1024×685 | af971c46442b638210deb84e555385fb6de77e978dca9612b92f07ee5a06239e |
| shrimp-boats-wanchese-1600.avif | 1600×1071 | c493bc2384ca0e0d78382679d99eb4d74a418fa0b1120fe3e6fa2426dd0cdcc9 |
| shrimp-boats-wanchese-1600.webp | 1600×1071 | 64f01f35e3bec2a815dac9ff1eb1c5a3bff478d213a358d2e61628a535695e29 |
| shrimp-boats-wanchese-1600.jpg | 1600×1071 | 70c9f7c6185ad70599810914fab54ec5550b0200f375f28c715fa11eb67e259d |

### bayboro-commercial-boats

- **Category:** saltwater
- **Location (as stated by the source):** Bay River, Bayboro, North Carolina
- **Description / caption:** Commercial fishing boats on the Bay River, Bayboro, North Carolina.
- **Date of photograph:** November 3, 2021
- **Photographer / author:** SaltySaltyTears
- **Credit shown on the page:** "Photo: SaltySaltyTears, CC0 1.0"
- **License:** CC0 1.0, https://creativecommons.org/publicdomain/zero/1.0/
- **Attribution:** the photographer's name links to the source page; the license name links to the license deed.
- **Source page:** https://commons.wikimedia.org/wiki/File:Commercial_fishing_boats_on_the_Bay_River,_Bayboro,_North_Carolina.jpg
- **Original dimensions:** 2050 × 1476
- **Date accessed:** 2026-11-15 (America/New_York)

Derivatives in `static/featured-photos/bayboro-commercial-boats/`:

| file | size | sha256 |
|---|---|---|
| bayboro-commercial-boats-placeholder.jpg | 32×23 | 78ddc9c7ba8b8bdb1ca9c7b972ff9bf6c24ba914bff10742c7f7f9072c48a64a |
| bayboro-commercial-boats-640.avif | 640×461 | db6a49221c415662215631aa8a1986e885f71090a2e7e97869a3390c69ff64b5 |
| bayboro-commercial-boats-640.webp | 640×461 | ed38ffef2aa96cecc3a187182add7624d97c298cc8815c470592fd19839f8d66 |
| bayboro-commercial-boats-640.jpg | 640×461 | 41380c206de95d3e7dd6b4f27faab2a8019f14c346139a84bd08419883a7e87f |
| bayboro-commercial-boats-1024.avif | 1024×737 | df5d7b42e378ef898b007b65921942d659a18e9e6ec93f06578c04996355fc26 |
| bayboro-commercial-boats-1024.webp | 1024×737 | a7e94fc2d8490a9ab69aed3b3dfa6a69dc48daba5fbe09a8c8319c3087d9931d |
| bayboro-commercial-boats-1024.jpg | 1024×737 | 114350f023659c45b2f6afb4c679af0514d0b18ad01d508f18bc18ab3bcc3de5 |
| bayboro-commercial-boats-1600.avif | 1600×1152 | beda99f212e938fbedd26a41699752167fa8dd41e2f9ac5490306308f4909baa |
| bayboro-commercial-boats-1600.webp | 1600×1152 | 2ffc499575515afccd406e39fb19b006dc72899ef26c9bde0a84fe894fa1161f |
| bayboro-commercial-boats-1600.jpg | 1600×1152 | faa520b330ccb00d78b92d7644ba2a8a467d6eb166e06bb715de217cd3d87fe5 |

### silver-lake-harbor

- **Category:** saltwater
- **Location (as stated by the source):** Silver Lake Harbor, Ocracoke Island, North Carolina
- **Description / caption:** Silver Lake Harbor, Ocracoke Island, North Carolina.
- **Date of photograph:** April 13, 2016
- **Photographer / author:** bobistraveling
- **Credit shown on the page:** "Photo: bobistraveling, CC BY 2.0"
- **License:** CC BY 2.0, https://creativecommons.org/licenses/by/2.0/
- **Attribution:** the photographer's name links to the source page; the license name links to the license deed.
- **Source page:** https://commons.wikimedia.org/wiki/File:Silver_Lake_Harbor_Ocracoke_Island_NC_0334_(26016019873).jpg
- **Original dimensions:** 4320 × 3240
- **Date accessed:** 2026-11-15 (America/New_York)

Derivatives in `static/featured-photos/silver-lake-harbor/`:

| file | size | sha256 |
|---|---|---|
| silver-lake-harbor-placeholder.jpg | 32×24 | 8a17a8c104a9e79d2066671a172f1654e6dda1c32cbdabde63c9846f328732d8 |
| silver-lake-harbor-640.avif | 640×480 | 45558d6823f711638f6fe20a11f757fdf60ddc8a225e17ab6222b788cb5d50a3 |
| silver-lake-harbor-640.webp | 640×480 | fd6204e877c047752c379995cb25f33dcd1524f4628288fd3389bce14df3f733 |
| silver-lake-harbor-640.jpg | 640×480 | c6afc3690ed4945b54bd984eb7a6e0918bab8bd2d06f78c11889f160ebdbc02e |
| silver-lake-harbor-1024.avif | 1024×768 | f50b286559e2a37607019d01c7a73d044a7074041ca4a06e40150f47a0f09445 |
| silver-lake-harbor-1024.webp | 1024×768 | 5654d2cedfed344ef36c867481b3bb791ac9d6fc9a29619bb3a4ecf3631c2d03 |
| silver-lake-harbor-1024.jpg | 1024×768 | e95a4c6b6e375332aa38ebf4f754f34cf38c23cfbd436479c90eeb7b7b8dfcff |
| silver-lake-harbor-1600.avif | 1600×1200 | 10a57cc2bffdeeac4a0aec87a6a229f8e9d047816d9c83be0c0d004fd793a70d |
| silver-lake-harbor-1600.webp | 1600×1200 | 3a7ad3e28822bea3eb7b62b5cc237b7762b730af8a8d077210a75ed4a92ea129 |
| silver-lake-harbor-1600.jpg | 1600×1200 | 9a22bfed7d1a91293602b2e40b6d546c26a9ecaa520d087f13c5b32f06942f40 |

### fishing-boat-oak-island-ferry

- **Category:** saltwater
- **Location (as stated by the source):** Photographed from the Oak Island Ferry, North Carolina
- **Description / caption:** A fishing boat, photographed from the Oak Island Ferry.
- **Date of photograph:** August 28, 2021
- **Photographer / author:** BobAMac5761
- **Credit shown on the page:** "Photo: BobAMac5761, CC BY-SA 4.0"
- **License:** CC BY-SA 4.0, https://creativecommons.org/licenses/by-sa/4.0/
- **Attribution:** the photographer's name links to the source page; the license name links to the license deed.
- **Source page:** https://commons.wikimedia.org/wiki/File:Fishing-Boat.jpg
- **Original dimensions:** 5209 × 3473
- **Date accessed:** 2026-11-15 (America/New_York)

Derivatives in `static/featured-photos/fishing-boat-oak-island-ferry/`:

| file | size | sha256 |
|---|---|---|
| fishing-boat-oak-island-ferry-placeholder.jpg | 32×21 | eddb8c84015414bc26b576fa89ede7d3a19e90f3ecc13b7e0d92b787f6df51af |
| fishing-boat-oak-island-ferry-640.avif | 640×427 | e74b91076ff18aeef49a7aabd3f0af5f8dd544642c660754087e954f0d6c2ad9 |
| fishing-boat-oak-island-ferry-640.webp | 640×427 | bd42d50141e9cfe0f3e091c2420bc1272c8811ef9281eaf5244ea5317362cc51 |
| fishing-boat-oak-island-ferry-640.jpg | 640×427 | db9b4a457351744547f6ffec342b4149984b08b6a15535a601d8a12325896842 |
| fishing-boat-oak-island-ferry-1024.avif | 1024×683 | df00c600f6542acf99a09941588c4c5457cf9fb09cc2c14ca1c298c01f008fd3 |
| fishing-boat-oak-island-ferry-1024.webp | 1024×683 | a3d5a73a372c3d52e8410eabaebb5532a7dec658d8c9be7d47744d3b004a0ecc |
| fishing-boat-oak-island-ferry-1024.jpg | 1024×683 | 7b9b705b3ac74d4ed4189108a5b6ed0921b8cdc29a450a814b0970588a8e95e0 |
| fishing-boat-oak-island-ferry-1600.avif | 1600×1067 | 4523f68fca972c5dffbd5eec7bcc434620f52129ec66a8e0bfd7aa20149ca3c2 |
| fishing-boat-oak-island-ferry-1600.webp | 1600×1067 | 2b77853c8d00cd7e44025453184e53acb815405b98d8214aea13e64137ee5e92 |
| fishing-boat-oak-island-ferry-1600.jpg | 1600×1067 | b1986c04da5573ad3c62f3705ee8ef218abc118996a3c0c2b390d2037796ff58 |

### swan-quarter-landing

- **Category:** saltwater
- **Location (as stated by the source):** Swan Quarter Landing, North Carolina
- **Description / caption:** Swan Quarter Landing, North Carolina.
- **Photographer / author:** Ingrid Lemme
- **Credit shown on the page:** "Photo: Ingrid Lemme (public domain)"
- **License:** Public domain
- **Source page:** https://commons.wikimedia.org/wiki/File:SQ_fast_boat.jpg
- **Original dimensions:** 3648 × 2736
- **Date accessed:** 2026-11-15 (America/New_York)

Derivatives in `static/featured-photos/swan-quarter-landing/`:

| file | size | sha256 |
|---|---|---|
| swan-quarter-landing-placeholder.jpg | 32×24 | ecb56243e1894af1d429832148a04f89145944305870cbb853340f9859082fab |
| swan-quarter-landing-640.avif | 640×480 | 30f6a41371090c9023f83edabd4818d3f84da3be7c0cefd09ce6b0c839b9114a |
| swan-quarter-landing-640.webp | 640×480 | a18d1c953c5eebc0855b082a66c4f42579e9dd22c57913ac2f7a3b18a48c9817 |
| swan-quarter-landing-640.jpg | 640×480 | 003c4625e5bb8a838d293aa607c1d03ee44cc9bb40ec82a569d9d6f02f570e72 |
| swan-quarter-landing-1024.avif | 1024×768 | ce63768eccb72b4e818cd7a0bc3587f75adc78d100d59b4ebd134a187f73e230 |
| swan-quarter-landing-1024.webp | 1024×768 | 3123e85901f757965d170d5489a3c951772d0ec76433e40b88091e4d6b9b03f1 |
| swan-quarter-landing-1024.jpg | 1024×768 | cd46c4c033cd88dc273c90983dd335f7c5e6cdb17e796ec758cfd9ccbf6ecee1 |
| swan-quarter-landing-1600.avif | 1600×1200 | 74e1713cd1a10ed490b7cf7585b8a85c32c4b736c2b5cc28af7388969ce64696 |
| swan-quarter-landing-1600.webp | 1600×1200 | f699551f2c733e5fa4627a18af8c5aff85d670f581bd45a82084489fe8fb0549 |
| swan-quarter-landing-1600.jpg | 1600×1200 | e054f361c6cd982128efc71cf26d234cb0157c233fbbd843420928e04133ea12 |

### oyster-boat-nc

- **Category:** heritage
- **Location (as stated by the source):** North Carolina
- **Description / caption:** Oyster boat in North Carolina.
- **Date of photograph:** between 1980 and 2006 (as stated by the Library of Congress)
- **Photographer / author:** Carol M. Highsmith
- **Credit shown on the page:** "Photo: Carol M. Highsmith, Library of Congress (public domain)"
- **License:** Public domain
- **Source page:** https://www.loc.gov/pictures/item/2011632094/
- **Original dimensions:** 6767 × 5411
- **Date accessed:** 2026-11-15 (America/New_York)
- **Notes:** The source page states only “North Carolina”; no town or harbor was added.

Derivatives in `static/featured-photos/oyster-boat-nc/`:

| file | size | sha256 |
|---|---|---|
| oyster-boat-nc-placeholder.jpg | 32×26 | fc872a69062cfaee2403607269688d5239d3877f53b9f249c8d4b4507db4c270 |
| oyster-boat-nc-640.avif | 640×512 | fe11e8e8a8deab029d8e28e681a8906b49f78931e5c2d469779ac95e47359f20 |
| oyster-boat-nc-640.webp | 640×512 | cfb8f019fbc1a5a2e491ea2a82da0f7ace5ff5d6d149a4a824353a64debb02ea |
| oyster-boat-nc-640.jpg | 640×512 | db092fbe425965f9326b0dab251cac9f1f6fff15470b8b28aca2f4fe24806649 |
| oyster-boat-nc-1024.avif | 1024×819 | b4275519783b22d95485d7cb99a47bcbea2910dd64dc84fc2f446988468ddf3a |
| oyster-boat-nc-1024.webp | 1024×819 | 27b7621a1c3a0009edad1fc04ae970672f04a55a03a7106b6298344ecac3d983 |
| oyster-boat-nc-1024.jpg | 1024×819 | c1b9c63982c4e2779dae7523701f550127ca2ef169923d6619b8c9e77f045c7b |
| oyster-boat-nc-1600.avif | 1600×1279 | 53b976032ec25be886d53cfce3f828cdfd256eb45aa1d975b420e320bedd6924 |
| oyster-boat-nc-1600.webp | 1600×1279 | 1f8cf080d27e05dc0b65216f30b537734be68cfae7516e8af69907e4a025c6b8 |
| oyster-boat-nc-1600.jpg | 1600×1279 | 386c81eaa03835325ca449eaf23df20b74c44b03aa45e1ba908213afd983298b |

### jennettes-pier

- **Category:** saltwater
- **Location (as stated by the source):** Jennette's Pier
- **Description / caption:** Jennette's Pier.
- **Date of photograph:** September 19, 2017
- **Photographer / author:** Roger Mulligan
- **Credit shown on the page:** "Photo: Roger Mulligan, CC BY 2.0"
- **License:** CC BY 2.0, https://creativecommons.org/licenses/by/2.0/
- **Attribution:** the photographer's name links to the source page; the license name links to the license deed.
- **Source page:** https://commons.wikimedia.org/wiki/File:Jennette%27s_Pier-3725-Edit_(36524404973).jpg
- **Original dimensions:** 3977 × 2679
- **Date accessed:** 2026-11-15 (America/New_York)
- **Notes:** The source does not state a town name, so none was added.

Derivatives in `static/featured-photos/jennettes-pier/`:

| file | size | sha256 |
|---|---|---|
| jennettes-pier-placeholder.jpg | 32×22 | 8933fa6d050b8fa1c5cfa6956e4214305d7aabe7ba6285c0c9526b2926488a8f |
| jennettes-pier-640.avif | 640×431 | 9c24201edef70743c550d2ec03b06c1b065f3c97a9420e439e6bbf5a006f9f0f |
| jennettes-pier-640.webp | 640×431 | cab420b8db736990bb4af095652d34cf04a15801708b28f236b0ddec370f2f27 |
| jennettes-pier-640.jpg | 640×431 | c8bc655d3b3d03e867ad3e9605ff1e6f7bbc231af4e0dc4b82d88ce1923331f3 |
| jennettes-pier-1024.avif | 1024×690 | 58020819e423db364c208189f5bae3c81f866cf3d53c4c1a1c935b3bc5dbd670 |
| jennettes-pier-1024.webp | 1024×690 | 4bdd03890c7f09bf2905917d7f6f96845e5d8bc4849f34ffb8e34be8c2c6b6b3 |
| jennettes-pier-1024.jpg | 1024×690 | 05ae24641dbdba6b481f49874d3586ef8dedaaf06032d4b2362fd6494475c607 |
| jennettes-pier-1600.avif | 1600×1078 | 2ae0dc5d02d43397bf7ab1eaf807188c65c90d787828c05a37e19841c41739ba |
| jennettes-pier-1600.webp | 1600×1078 | 085d1f422ac77c122c2615c5f9111c7b8ec6fd17117ca7009741854ac5b2c09a |
| jennettes-pier-1600.jpg | 1600×1078 | 95b6ad055a121cdb41ebd0a3c449f128ab67e282e4b2c0f6125edbc941a857b3 |

### duck-sunset

- **Category:** lifestyle
- **Location (as stated by the source):** Duck, North Carolina
- **Description / caption:** Sunset at Duck, North Carolina.
- **Date of photograph:** October 23, 2025
- **Photographer / author:** Watts
- **Credit shown on the page:** "Photo: Watts, CC BY 4.0"
- **License:** CC BY 4.0, https://creativecommons.org/licenses/by/4.0/
- **Attribution:** the photographer's name links to the source page; the license name links to the license deed.
- **Source page:** https://commons.wikimedia.org/wiki/File:Sunset_-_Duck_-_North_Carolina.jpg
- **Original dimensions:** 8962 × 5981
- **Date accessed:** 2026-11-15 (America/New_York)

Derivatives in `static/featured-photos/duck-sunset/`:

| file | size | sha256 |
|---|---|---|
| duck-sunset-placeholder.jpg | 32×21 | 25a94277037fa585e464d83040393a63db4b4f9bcced0308d1118f375af36860 |
| duck-sunset-640.avif | 640×427 | 2019dc8fd951c650353630780ddb1bd96dd5955def6002cef3f128c55050050a |
| duck-sunset-640.webp | 640×427 | 0146beadf1fd268237071de3215ca49f7e0d32c87d0556382fa51296f94afa92 |
| duck-sunset-640.jpg | 640×427 | 4fec248eaa98044a73387ab13d81c32cbd2439efdfd87d30fe60656e0e7445e6 |
| duck-sunset-1024.avif | 1024×683 | 8003e6b12a3fa3162d5b0c42ea3f2d8b2a560e943682807b0f50843ad0e0528c |
| duck-sunset-1024.webp | 1024×683 | ccd5f2f971d64c39bac771963a4b44013a8b5bc9d854f2a8f22828491899dd00 |
| duck-sunset-1024.jpg | 1024×683 | 8d4fcc8b002b0045e822d51b06cdfb56d1555d862d5c261e8a11127c0f8d023b |
| duck-sunset-1600.avif | 1600×1068 | c2b953d2cd46b23d21e8c4d03115990235d9a627e56ae90549be1f669d355155 |
| duck-sunset-1600.webp | 1600×1068 | 6d9726349d1a2af5dcba501ffa982ea0f2c5f3b62b53f562dab6a541f67bc88d |
| duck-sunset-1600.jpg | 1600×1068 | 2a4afa50dc4433ee84fc5176adef2d5e5c64f8da2fe45fe4840562a4707b22c8 |

### manteo-roanoke-marshes-light

- **Category:** heritage
- **Location (as stated by the source):** Manteo, North Carolina
- **Description / caption:** 2004 replica of the original Roanoke Marshes Light, in Manteo, North Carolina.
- **Date of photograph:** May 14, 2012
- **Photographer / author:** Morgan Riley
- **Credit shown on the page:** "Photo: Morgan Riley, CC BY 3.0"
- **License:** CC BY 3.0, https://creativecommons.org/licenses/by/3.0/
- **Attribution:** the photographer's name links to the source page; the license name links to the license deed.
- **Source page:** https://commons.wikimedia.org/wiki/File:New_Roanoke_Marshes_Light,_Manteo,_North_Carolina.JPG
- **Original dimensions:** 3264 × 2448
- **Date accessed:** 2026-11-15 (America/New_York)

Derivatives in `static/featured-photos/manteo-roanoke-marshes-light/`:

| file | size | sha256 |
|---|---|---|
| manteo-roanoke-marshes-light-placeholder.jpg | 32×24 | 1e3d3abc3f2b624500db4b585fcc8a0b96281611020527fde2f50f5096b1d4b5 |
| manteo-roanoke-marshes-light-640.avif | 640×480 | 9ca7a4ad4d1526ac4c6b087658d2c7a946414128142a998932c26247de99d597 |
| manteo-roanoke-marshes-light-640.webp | 640×480 | 70d6558be3c174cc6d25768cf63e3002f2c16f6c01fb48b3d0d71e2091ebd7e2 |
| manteo-roanoke-marshes-light-640.jpg | 640×480 | a26aed06473c17668649c49482f613458dcdf7dbc9ced40212f859baaf105617 |
| manteo-roanoke-marshes-light-1024.avif | 1024×768 | 52075d861bc56410f1f74ca801d256b800efd1bd9869ba17ded95e443f6c8b7c |
| manteo-roanoke-marshes-light-1024.webp | 1024×768 | e1e1aa1a295277cc0493e92c7e02431037904985a9adc659bce2d89219e832f1 |
| manteo-roanoke-marshes-light-1024.jpg | 1024×768 | 91a1f5f4d5f44b20990b14fcabeda5fb2387053de3effd6a8b0e76b80dcd4754 |
| manteo-roanoke-marshes-light-1600.avif | 1600×1200 | af803de8d62f64dcce6fbc22a1362213e170d60eec412a2938d555cfa57d4c2a |
| manteo-roanoke-marshes-light-1600.webp | 1600×1200 | b292d2a98d54b0b1d9d3b2996850c68484b8d2ec4b18b3c4384737147d4ebe70 |
| manteo-roanoke-marshes-light-1600.jpg | 1600×1200 | 48912fbf6fda2757a58aec23c60d0577fc1ef9e8afd6a521ec13b408504f9d99 |

### november-fishing-cape-point

- **Category:** saltwater
- **Location (as stated by the source):** Cape Point, Cape Hatteras National Seashore, North Carolina
- **Description / caption:** November fishing at Cape Point.
- **Date of photograph:** November 8, 2021
- **Photographer / author:** Cape Hatteras National Seashore (U.S. National Park Service)
- **Credit shown on the page:** "Photo: U.S. National Park Service, Cape Hatteras National Seashore (public domain)"
- **License:** Public domain
- **Source page:** https://commons.wikimedia.org/wiki/File:November_fishing_at_Cape_Point_(51682179413).jpg
- **Original dimensions:** 4032 × 3024
- **Date accessed:** 2026-11-15 (America/New_York)

Derivatives in `static/featured-photos/november-fishing-cape-point/`:

| file | size | sha256 |
|---|---|---|
| november-fishing-cape-point-placeholder.jpg | 32×24 | 66e8193769b9da576b3f3c29f2157bfe12695b07842d2e5a5f3a1dda7102e9a4 |
| november-fishing-cape-point-640.avif | 640×480 | 6aae011a5f5e7f5f1e9ca45a3fe3055aad8ab3c13153c9d22f7613c585bedf6b |
| november-fishing-cape-point-640.webp | 640×480 | 371a6ea370a42d7fd06a0509b786099e42fcadf6f658bde8889106c1d617b818 |
| november-fishing-cape-point-640.jpg | 640×480 | b7c0fd1da52cc6c13b56e8fcf28dd09f9ab1da0aa2548ce0c84ca00546379980 |
| november-fishing-cape-point-1024.avif | 1024×768 | e7bb1ceb0c900c933ba9e57b15f78786903a97d70d7fe42927a6987bf8f282bb |
| november-fishing-cape-point-1024.webp | 1024×768 | cc0decacfa0e50aec2e6c2ea93b4f9195a39cc766774c0eb4920cc0e13ad270a |
| november-fishing-cape-point-1024.jpg | 1024×768 | 93fa61945c80c674f96999904638565bdfca10d802c6792fc62ad193a63b5d57 |
| november-fishing-cape-point-1600.avif | 1600×1200 | 8eca32dc54225667b82c486c5f5478bfa654f43636e43fca8f87654889ce733e |
| november-fishing-cape-point-1600.webp | 1600×1200 | ea72f509a66a63e54f4bc099c1082ec9082a6c8de95ebd74e60c573f0f382508 |
| november-fishing-cape-point-1600.jpg | 1600×1200 | 8160c70927bdd1a7095cdc9aa4fd5ff3062057b8c7556a96efb89aa5f06fbd1d |

### surf-fishing-hatteras-pier

- **Category:** heritage
- **Location (as stated by the source):** Hatteras pier, Outer Banks, North Carolina
- **Description / caption:** Surf fishing from the Hatteras pier on North Carolina's Outer Banks.
- **Date of photograph:** between 1980 and 2006 (as stated by the Library of Congress)
- **Photographer / author:** Carol M. Highsmith
- **Credit shown on the page:** "Photo: Carol M. Highsmith, Library of Congress (public domain)"
- **License:** Public domain
- **Source page:** https://www.loc.gov/pictures/item/2011632387/
- **Original dimensions:** 6540 × 5053
- **Date accessed:** 2026-11-15 (America/New_York)

Derivatives in `static/featured-photos/surf-fishing-hatteras-pier/`:

| file | size | sha256 |
|---|---|---|
| surf-fishing-hatteras-pier-placeholder.jpg | 32×25 | a4e1d31bb885a3b7cf39ad81f1c4f713b794ef2962d7f31d99f52f8fb80cf0d2 |
| surf-fishing-hatteras-pier-640.avif | 640×494 | 7c9f3bc5c1c4f15530297ba7340a91ca07726f969d316d1a1ecc192735d8109f |
| surf-fishing-hatteras-pier-640.webp | 640×494 | f6dc8960ae67f56b6489972721cba60e5f88dcb5368e6c36e5c9d14ebe393aa7 |
| surf-fishing-hatteras-pier-640.jpg | 640×494 | 0f008065e4d015143398cfba7b6aababb23ff3ff1485e20c08dd708f45361502 |
| surf-fishing-hatteras-pier-1024.avif | 1024×791 | ff8dc10169c25d9e51d5810f5828fbe5a8381aedb66c71689b65d981d5c8c764 |
| surf-fishing-hatteras-pier-1024.webp | 1024×791 | 1f3e7b555cfc5cb3467a3c872e136019d0a34f0e2c2ce3a805d20003569ad88b |
| surf-fishing-hatteras-pier-1024.jpg | 1024×791 | ab5a3df9f602d43fb5f6eab01dbae9fb32e3673201ee5d677dfa144bd1fdfc59 |
| surf-fishing-hatteras-pier-1600.avif | 1600×1236 | 8196536e15a73f0325da1a77ed520420224695bb1d4a2f27eef2a4a6965d219d |
| surf-fishing-hatteras-pier-1600.webp | 1600×1236 | fb77dabca1d5da84276bfe09759ceefd93e1fd8a41b6d6af51031914333925c6 |
| surf-fishing-hatteras-pier-1600.jpg | 1600×1236 | a672e63f3a41c2b6120e1f5b1e8f23bf15116c7b421463548681426631e08e69 |

### currituck-banks-reserve

- **Category:** lifestyle
- **Location (as stated by the source):** Currituck Banks Reserve
- **Description / caption:** View of the sound from the Currituck Banks Reserve.
- **Date of photograph:** August 16, 2026
- **Photographer / author:** Indy beetle
- **Credit shown on the page:** "Photo: Indy beetle, CC0 1.0"
- **License:** CC0 1.0, https://creativecommons.org/publicdomain/zero/1.0/
- **Attribution:** the photographer's name links to the source page; the license name links to the license deed.
- **Source page:** https://commons.wikimedia.org/wiki/File:Currituck_Banks_Reserve_view.jpg
- **Original dimensions:** 5712 × 4284
- **Date accessed:** 2026-11-15 (America/New_York)

Derivatives in `static/featured-photos/currituck-banks-reserve/`:

| file | size | sha256 |
|---|---|---|
| currituck-banks-reserve-placeholder.jpg | 32×24 | 05f91c8b5b6d0c5f3eee0ab28194bbbd858596c309ed5766f268e142399ee5fc |
| currituck-banks-reserve-640.avif | 640×480 | 1b45c5e7a4fe4c3f181660ffb89f36fbc0b77348ad47d7951ce220d649d71913 |
| currituck-banks-reserve-640.webp | 640×480 | 74ddd0ca5c26cb5a415b6dd7eaadfabd4af1bb36ca36827957b93e4d187b7895 |
| currituck-banks-reserve-640.jpg | 640×480 | fafcae4891fc399498734c2fa9aaa8349bc33e7aef4f74b1b8eadb3ab2641a0d |
| currituck-banks-reserve-1024.avif | 1024×768 | 84efbcfc18cec36fb78723815dfa2a4aeee906736a8d0ce6037ef717c1a2f90f |
| currituck-banks-reserve-1024.webp | 1024×768 | 89d75a1f7b1f92f3ec14e0a843f6bd9b8e9e0a241367de9decc0b7e27f001bdf |
| currituck-banks-reserve-1024.jpg | 1024×768 | 2cce0871a64cb3179a25b7c60462cd8d48b54d64289043125f3d91def2a53aa4 |
| currituck-banks-reserve-1600.avif | 1600×1200 | 16ec0b080ee88dd00ce267603fa3b40239101e5a0b5c05ccb13915a798bd4b20 |
| currituck-banks-reserve-1600.webp | 1600×1200 | bedf3d74dd1054ede12a13cb1840d067fa86afae64671dab96d8bcfcad54c8da |
| currituck-banks-reserve-1600.jpg | 1600×1200 | 9dad0fda92ea22b52c5224d63ec771e67734944c3c98c89bc19f137b90edb64e |

### salt-marsh-new-hanover

- **Category:** lifestyle
- **Location (as stated by the source):** New Hanover County, North Carolina
- **Description / caption:** Salt marsh with tidal pools and the sound beyond, New Hanover County, North Carolina.
- **Date of photograph:** March 26, 2023
- **Photographer / author:** Z3lvs
- **Credit shown on the page:** "Photo: Z3lvs, CC0 1.0"
- **License:** CC0 1.0, https://creativecommons.org/publicdomain/zero/1.0/
- **Attribution:** the photographer's name links to the source page; the license name links to the license deed.
- **Source page:** https://commons.wikimedia.org/wiki/File:Salt_marsh_with_tidal_pools_and_the_sound_beyond,_New_Hanover_County,_North_Carolina.jpg
- **Original dimensions:** 4032 × 3024
- **Date accessed:** 2026-11-15 (America/New_York)

Derivatives in `static/featured-photos/salt-marsh-new-hanover/`:

| file | size | sha256 |
|---|---|---|
| salt-marsh-new-hanover-placeholder.jpg | 32×24 | 7c744989b0a679eb9f0ecda7e1e9e5a680a665f760ba0364b4f6c3c447abc11e |
| salt-marsh-new-hanover-640.avif | 640×480 | 1f8bed45078120f0bc9648afba5b8b289e89fabceebea3bb9f80dd7bddecdc2b |
| salt-marsh-new-hanover-640.webp | 640×480 | 1a0ceee0090cae121b5374198b8da8ab446a260a646de9e171af3c46e1b937f5 |
| salt-marsh-new-hanover-640.jpg | 640×480 | 3d829975bb963b5cd85d76069f5e04fe09ce0a494f3c5d1b3dad6b1db1e18892 |
| salt-marsh-new-hanover-1024.avif | 1024×768 | 70eb6f852aac450400f75c8a38ab1f61a61b5cbc291e270fcd07b170e81e3f5e |
| salt-marsh-new-hanover-1024.webp | 1024×768 | c11e2c4125e2cec0e72d14a57d363371d8840cdb24cdbf7572e408127d054bf6 |
| salt-marsh-new-hanover-1024.jpg | 1024×768 | 195c25ee89918caaf7719ce440a870986d77008b842444d2c041ac1089daf5d3 |
| salt-marsh-new-hanover-1600.avif | 1600×1200 | 581212f6ded77b28ba7740687a54b25fc611b757f5ed30f9954dce5d92e87782 |
| salt-marsh-new-hanover-1600.webp | 1600×1200 | a2430d46a85961426a53957fe3bb7da76925ec8b7060ca33ca616ad98695b66b |
| salt-marsh-new-hanover-1600.jpg | 1600×1200 | 21995428a493b54b3899c9f8624bce906cb8f3a9db133fddfac9801cc5156536 |

### falls-lake-pier

- **Category:** freshwater
- **Location (as stated by the source):** Falls Lake, North Carolina
- **Description / caption:** Fishing pier, Falls Lake, North Carolina.
- **Date of photograph:** March 5, 2023
- **Photographer / author:** Sergiy Galyonkin
- **Credit shown on the page:** "Photo: Sergiy Galyonkin, CC BY-SA 2.0 (cropped from the original)"
- **License:** CC BY-SA 2.0, https://creativecommons.org/licenses/by-sa/2.0/
- **Attribution:** the photographer's name links to the source page; the license name links to the license deed.
- **Source page:** https://www.flickr.com/photos/sergesegal/52741376400/
- **Original dimensions:** 5208 × 3906
- **Date accessed:** 2026-11-15 (America/New_York)
- **Notes:** Cropped from Sergiy Galyonkin's original (x=2466, y=186, w=5208, h=3906, 4:3) to remove the watermark and the rocky low-water foreground. This folder's derivatives are the crop only; they were not colour-graded. The colour-adjusted Falls Lake hero used on the freshwater Falls Lake view remains the existing files in `preview/sprint-home/photos/`. This photograph is labeled Falls Lake only, never Jordan Lake.

Derivatives in `static/featured-photos/falls-lake-pier/`:

| file | size | sha256 |
|---|---|---|
| falls-lake-pier-placeholder.jpg | 32×24 | 459fffa483c9602ab11c6003416a58550e0c8cdcc64833b350f40a4bf50fb648 |
| falls-lake-pier-640.avif | 640×480 | ea7f4c5e0a76da31348040006c68793eb39953efede42086efa8803348aeeb5a |
| falls-lake-pier-640.webp | 640×480 | 7b00e2f0d34b148fab1f143a4a6979f4a0a1ef0a34a5026bb11454b3fd81c2f9 |
| falls-lake-pier-640.jpg | 640×480 | 0798364260583818a1e89249b70ca48dd318ce8d7d07e3a3c4ac384de69bc3ee |
| falls-lake-pier-1024.avif | 1024×768 | 778c77dacd6baa357b1eb6e169a90ae2d21a9aa824e23277589248098ffa08bd |
| falls-lake-pier-1024.webp | 1024×768 | 84635469e18dcb7087aa504e2eae02b44c88fc38cd9fcb463228675b574c1460 |
| falls-lake-pier-1024.jpg | 1024×768 | 5335866ab827ccc454185783652ff5e09885d2d92353b715c16488b29662b4f0 |
| falls-lake-pier-1600.avif | 1600×1200 | 59e3797768f451ab5a501c95dd8884ab86875431a79038bf741585aa9e2b0d43 |
| falls-lake-pier-1600.webp | 1600×1200 | 9f3bb0c5002c62645d0c3043e4585a569f9910b1f2c590d8491fe970e05bc96b |
| falls-lake-pier-1600.jpg | 1600×1200 | 4f2c62fe3114d681f5635275adcbab283a32ea5634a59b948f6324036b009e03 |

### jordan-lake-ebenezer

- **Category:** freshwater
- **Location (as stated by the source):** Jordan Lake State Recreation Area, Ebenezer Church area, North Carolina
- **Description / caption:** Shoreline of Jordan Lake at the Ebenezer Church area, Jordan Lake State Recreation Area.
- **Date of photograph:** October 1, 2013
- **Photographer / author:** Gerry Dincher
- **Credit shown on the page:** "Photo: Gerry Dincher, CC BY-SA 2.0"
- **License:** CC BY-SA 2.0, https://creativecommons.org/licenses/by-sa/2.0/
- **Attribution:** the photographer's name links to the source page; the license name links to the license deed.
- **Source page:** https://commons.wikimedia.org/wiki/File:Jordan_Lake_from_Ebenezer_Church_shore.jpg
- **Original dimensions:** 3648 × 2736
- **Date accessed:** 2026-11-15 (America/New_York)
- **Notes:** This photograph is labeled Jordan Lake only, never Falls Lake.

Derivatives in `static/featured-photos/jordan-lake-ebenezer/`:

| file | size | sha256 |
|---|---|---|
| jordan-lake-ebenezer-placeholder.jpg | 32×24 | 6369eebf5e49f2f852e7758921b64d1d9fb957d52cd8dc271b033a3f9aa0b8fa |
| jordan-lake-ebenezer-640.avif | 640×480 | 6ea9709a140185ef3de8962df85012f54bfe9277c5fcea509728227ab59bc355 |
| jordan-lake-ebenezer-640.webp | 640×480 | 18a266caa7f5a16222067fe185564829f77be258909a9d93ebef2c40aaaadfc7 |
| jordan-lake-ebenezer-640.jpg | 640×480 | ae0c9870269a172ae431d907d82fb7da56d1d9eba0caeeb89e9fddd8a6fec5d7 |
| jordan-lake-ebenezer-1024.avif | 1024×768 | 53e20d25751a58e24788beae1eeb2082428e0c0a0f925f1c0d9f215bc09d9a20 |
| jordan-lake-ebenezer-1024.webp | 1024×768 | f36caabbd17e6a891725fb1aa6add9de9fbbc21eadbe3086d3555bce46ce8e5f |
| jordan-lake-ebenezer-1024.jpg | 1024×768 | b8b2bcae8584e544bad7ba7a31cfaa1a45e416f226c23c57aa4dd2198c55d90e |
| jordan-lake-ebenezer-1600.avif | 1600×1200 | 3e11a1044612fac35441a380305f9d7dca1ddf7519c67d3fbb1413930e114342 |
| jordan-lake-ebenezer-1600.webp | 1600×1200 | 1a6f533fe7d581617cbf29543f6608462e0ea6360e612d493db6617d124277d7 |
| jordan-lake-ebenezer-1600.jpg | 1600×1200 | 4af45c9b57e2c555a39b332fd7b8519712d3ac304dde3d150e44b6e7f79d478b |

### fontana-lake-dock

- **Category:** freshwater
- **Location (as stated by the source):** Fontana Lake, Fontana Dam, North Carolina
- **Description / caption:** Dock on Fontana Lake at Fontana Dam, North Carolina.
- **Date of photograph:** August 8, 2021
- **Photographer / author:** Warren LeMay
- **Credit shown on the page:** "Photo: Warren LeMay, CC BY-SA 2.0"
- **License:** CC BY-SA 2.0, https://creativecommons.org/licenses/by-sa/2.0/
- **Attribution:** the photographer's name links to the source page; the license name links to the license deed.
- **Source page:** https://commons.wikimedia.org/wiki/File:Dock,_Fontana_Lake,_Fontana_Dam,_NC.jpg
- **Original dimensions:** 3976 × 2982
- **Date accessed:** 2026-11-15 (America/New_York)

Derivatives in `static/featured-photos/fontana-lake-dock/`:

| file | size | sha256 |
|---|---|---|
| fontana-lake-dock-placeholder.jpg | 32×24 | f2e337cde9d114b526454344284c4dba27ebaaa97c71b243a2532b5ffdbbf3de |
| fontana-lake-dock-640.avif | 640×480 | 94128081d35c33178fda52e792024bc59aa408d322c3639c21783d739ad71031 |
| fontana-lake-dock-640.webp | 640×480 | bdd3a17d73708ee01df6d35a954c38286108711a555ac5c1fa93988f93e22699 |
| fontana-lake-dock-640.jpg | 640×480 | 7f4ada9847d42f1e1efb849107adcc190aaa247ac25fafffe9dfdfc6f6df1c19 |
| fontana-lake-dock-1024.avif | 1024×768 | d99668a57e1f40e2b1fe69e1c0f76ce61285399c0cd3b082d0927906a534027b |
| fontana-lake-dock-1024.webp | 1024×768 | 160e281ba89d7d1fe666ef17178796b4f0bce95d993bc21701c0d81326a54720 |
| fontana-lake-dock-1024.jpg | 1024×768 | 0fa22617d11557d73d7504346cdd44c32b9e362be572b36583f84ea97c823174 |
| fontana-lake-dock-1600.avif | 1600×1200 | fafe3866c667a1eb92f416d2b561049874e3057c6bf74aefe46c27eb17e84658 |
| fontana-lake-dock-1600.webp | 1600×1200 | 47ab8a5aa9358da8f5d217dc9f203b0c55f98f4892123eb0c1ab224bf9df21b3 |
| fontana-lake-dock-1600.jpg | 1600×1200 | 14df4e05eb4a803b4ba5b06f498c541756df25ccfad3c45621772573312a1af8 |

### linville-falls

- **Category:** freshwater
- **Location (as stated by the source):** Linville Falls, Linville Gorge, Burke County, North Carolina
- **Description / caption:** Linville Falls, seen from just downstream on the Linville River in the Linville Gorge.
- **Date of photograph:** June 1, 2008
- **Photographer / author:** Ken Thomas
- **Credit shown on the page:** "Photo: Ken Thomas (public domain)"
- **License:** Public domain
- **Source page:** https://commons.wikimedia.org/wiki/File:Linville_Falls-27527-3.jpg
- **Original dimensions:** 2000 × 1500
- **Date accessed:** 2026-11-15 (America/New_York)

Derivatives in `static/featured-photos/linville-falls/`:

| file | size | sha256 |
|---|---|---|
| linville-falls-placeholder.jpg | 32×24 | f595fd49ca51f5ddc07c2a5a9afee918b3e418271514bf2c82b17f1824725026 |
| linville-falls-640.avif | 640×480 | 3c363aac0981790fc47591f01cf1c2ea741ba95093f3bf3d7e3c088a67b49f27 |
| linville-falls-640.webp | 640×480 | d04067d1236a8e9f630ab41e41b30ad0b5375274a48b670abd031fcbb221aea6 |
| linville-falls-640.jpg | 640×480 | 731679c50c8cd125ef876c1310e94223d9abfc9d997a2d44c406c358506e50b1 |
| linville-falls-1024.avif | 1024×768 | 104895bb1cc26e4702e09edf369110731eacafdeb0b70399b65fcc5b57f9d984 |
| linville-falls-1024.webp | 1024×768 | 6b11b08a57e03a2447a0bd3ba1598c870134d378f1c92efe0bab41fffde185b3 |
| linville-falls-1024.jpg | 1024×768 | 74de1d54c381107a0ee689553e585bb6de843d8d4ab56ee39dd93ed4dd9727ef |
| linville-falls-1600.avif | 1600×1200 | 3df0bb5f7407089b2be501f5c2c8f43c7be0a8d570ab63a730c50a72cd144166 |
| linville-falls-1600.webp | 1600×1200 | bd627624cad334e31df6b2b4b353c5e292e170d7316fd94787ced3c7a88ed0f3 |
| linville-falls-1600.jpg | 1600×1200 | 04d70ee4e308e9e836acce2b1518c3b13f62504eedf99c1d6587cd33f77779bb |

### neuse-river-cliffs

- **Category:** freshwater
- **Location (as stated by the source):** Cliffs of the Neuse State Park, North Carolina
- **Description / caption:** View across the Neuse River from the overlook in Cliffs of the Neuse State Park, North Carolina.
- **Date of photograph:** November 14, 2020
- **Photographer / author:** Fredlyfish4
- **Credit shown on the page:** "Photo: Fredlyfish4, CC BY-SA 4.0"
- **License:** CC BY-SA 4.0, https://creativecommons.org/licenses/by-sa/4.0/
- **Attribution:** the photographer's name links to the source page; the license name links to the license deed.
- **Source page:** https://commons.wikimedia.org/wiki/File:Neuse_River_at_Cliffs_of_the_Neuse_State_Park_2020.jpg
- **Original dimensions:** 4606 × 1798
- **Date accessed:** 2026-11-15 (America/New_York)

Derivatives in `static/featured-photos/neuse-river-cliffs/`:

| file | size | sha256 |
|---|---|---|
| neuse-river-cliffs-placeholder.jpg | 32×12 | 70110961e81751fb45b44402c3fb498bbd6e5ab5f4bba4c4dc1b79ea2451b0f4 |
| neuse-river-cliffs-640.avif | 640×250 | a5a70f9ed6c9bb47552cce33752d6a6cca718aa8618892dc3fd27bdcfbe6a0f7 |
| neuse-river-cliffs-640.webp | 640×250 | 3cfb25b56e8733cc2d2bcc2d36f114eb644aaf6a6318546c85cfc77e331e9a99 |
| neuse-river-cliffs-640.jpg | 640×250 | 9c13a4d0f9dbedcc54ed966183e05e83de8c15412673ce998201d440d061bd41 |
| neuse-river-cliffs-1024.avif | 1024×400 | 9ba13a9a277343b1bb7f13c3831e81066e005de5597851a09607817ca36d9b24 |
| neuse-river-cliffs-1024.webp | 1024×400 | 36ce86d605666b6645657efa821d686fd2c9f636158f196cb9a420806c3af6f1 |
| neuse-river-cliffs-1024.jpg | 1024×400 | 078f3938281b946f7dcee566db6a30e35ea31f3fa51a9e35986131974e1950df |
| neuse-river-cliffs-1600.avif | 1600×625 | db14b0fa4bfa2ff8f80040eebb2a757bc1e1aaa4b482ed201fadaf139ce938e5 |
| neuse-river-cliffs-1600.webp | 1600×625 | 6e4ec79e2bb6a8ce407ea73032d45faff5f61dcad53eeb02f17edfe06aaac5d6 |
| neuse-river-cliffs-1600.jpg | 1600×625 | 10530b36740e0e1759842fa0e1b421b1b3ab9bcb753f5570f80d9a39f3a210d0 |

### cape-fear-southport

- **Category:** freshwater
- **Location (as stated by the source):** Cape Fear River, Southport, North Carolina
- **Description / caption:** The Cape Fear River at Southport.
- **Date of photograph:** June 8, 2015
- **Photographer / author:** David Broad
- **Credit shown on the page:** "Photo: David Broad, CC BY 3.0"
- **License:** CC BY 3.0, https://creativecommons.org/licenses/by/3.0/
- **Attribution:** the photographer's name links to the source page; the license name links to the license deed.
- **Source page:** https://commons.wikimedia.org/wiki/File:Cape_Fear_River_-_Southport_-_panoramio.jpg
- **Original dimensions:** 4288 × 2848
- **Date accessed:** 2026-11-15 (America/New_York)

Derivatives in `static/featured-photos/cape-fear-southport/`:

| file | size | sha256 |
|---|---|---|
| cape-fear-southport-placeholder.jpg | 32×21 | 3e319bb101c2c02fb083621d56a04b447986753dd11300c0bea3b72bb7e2804c |
| cape-fear-southport-640.avif | 640×425 | 19c1402c1cb07bf89ad39660ebf529932f494e10f5406286da651400c9d47f4f |
| cape-fear-southport-640.webp | 640×425 | bf01933977be18399800f576ed5626a4d1f813efa87e9cce931b1ce4f7c6e330 |
| cape-fear-southport-640.jpg | 640×425 | 894b6ef6b137cbba33bc33f8ef595cb1ab7fa8d05236ef84f4e2ca7ce6419c8c |
| cape-fear-southport-1024.avif | 1024×680 | d48af5f5bc135d7dc96c874027c34061195ec6446098ace9c5f81ae6714e0d3d |
| cape-fear-southport-1024.webp | 1024×680 | 506880fe914cc2b4e99c66c9bd1a91e39a15706a4eb611437b97fa22de209b01 |
| cape-fear-southport-1024.jpg | 1024×680 | 7e0fefdd58980bca069bce66c3ae71a78ae6754bf31e4da8f664819910927d4b |
| cape-fear-southport-1600.avif | 1600×1063 | de744759bd8455e52cff6554128ac4747db78cd8051dbe3c617e2dbe911a1e44 |
| cape-fear-southport-1600.webp | 1600×1063 | b6fdac5b1354454be52f09e5398189d8211e6cb4d8c323e301c5673697ba0286 |
| cape-fear-southport-1600.jpg | 1600×1063 | 9521940d0df537fc24818fb1ea4c43958a2868eecbeed43341941e6f5fad9137 |
| cape-fear-southport-2400.avif | 2400×1594 | 405c0739b6e5aa1495e7b952f548a476d0462342b6796b421b4a7454978cea2f |
| cape-fear-southport-2400.webp | 2400×1594 | 8245719090db676dd6e68cd746405ecdbd355b37f184152e6a0fb9495a980c84 |
| cape-fear-southport-2400.jpg | 2400×1594 | 04aa7cb5a353ed5a6c6c5747fd108f35f28afba7871511c26e1ff55d9b3817ae |

### mattamuskeet-sunset

- **Category:** freshwater
- **Location (as stated by the source):** Mattamuskeet National Wildlife Refuge, North Carolina
- **Description / caption:** Sunset at Lake Mattamuskeet.
- **Date of photograph:** June 15, 2013
- **Photographer / author:** Allie Stewart
- **Credit shown on the page:** "Photo: Allie Stewart/USFWS (public domain)"
- **License:** Public domain
- **Source page:** https://commons.wikimedia.org/wiki/File:Sunset_at_Lake_Mattamuskeet_(12331105795).jpg
- **Original dimensions:** 4000 × 3000
- **Date accessed:** 2026-11-15 (America/New_York)

Derivatives in `static/featured-photos/mattamuskeet-sunset/`:

| file | size | sha256 |
|---|---|---|
| mattamuskeet-sunset-placeholder.jpg | 32×24 | 31d7d04bae109e05bad06ae4cc5e4054701f36a3d7b5a6af990c20022a27010c |
| mattamuskeet-sunset-640.avif | 640×480 | f297da1c949b6245eff57632144a34aaa2ddf0f51fca492053795f30300c1c1c |
| mattamuskeet-sunset-640.webp | 640×480 | 845338ae652217d60de23a92c7160b42cc8ec096556c8c19fdd3b73c5b3563e2 |
| mattamuskeet-sunset-640.jpg | 640×480 | 1ad21a17a00352cc78ec683b63754343b4e38d223c85c78985fd8ecdde59613d |
| mattamuskeet-sunset-1024.avif | 1024×768 | f9221b7fee0c2d4fb3d21b3a1131c6f0e44cbf1b0098a97e9fca6f7e47b9223e |
| mattamuskeet-sunset-1024.webp | 1024×768 | e308f2fc32d318c4e1ce056d5ec6a9d02b8210bf3e79ad25c757f28960ae6a2e |
| mattamuskeet-sunset-1024.jpg | 1024×768 | 2bd3872bd787f045b64b50a65e7a8f232df00174b0cefa4ffe06fe090781a0ab |
| mattamuskeet-sunset-1600.avif | 1600×1200 | 2b129a00dbe2ab8174b63ed758c43081c918503480920e08a035094376667492 |
| mattamuskeet-sunset-1600.webp | 1600×1200 | 9e8a4d89fe82660bfbbd070c8490c7a186542fa02b17fb169ee77d45f5ab4476 |
| mattamuskeet-sunset-1600.jpg | 1600×1200 | c9822140b0fe137e36594543e2fdec64141e035ac88c727852ba02c6c2cc3f9f |

### nantahala-family

- **Category:** lifestyle
- **Location (as stated by the source):** Nantahala River
- **Description / caption:** A family silhouette on the Nantahala River.
- **Date of photograph:** July 25, 2010
- **Photographer / author:** joiseyshowaa
- **Credit shown on the page:** "Photo: joiseyshowaa, CC BY-SA 2.0"
- **License:** CC BY-SA 2.0, https://creativecommons.org/licenses/by-sa/2.0/
- **Attribution:** the photographer's name links to the source page; the license name links to the license deed.
- **Source page:** https://commons.wikimedia.org/wiki/File:A_family_silhouette_-_Nantahala_River_(6241324149).jpg
- **Original dimensions:** 2168 × 1456
- **Date accessed:** 2026-11-15 (America/New_York)

Derivatives in `static/featured-photos/nantahala-family/`:

| file | size | sha256 |
|---|---|---|
| nantahala-family-placeholder.jpg | 32×21 | 7ed24de7f44429b2affa13aa698faa8d720e87c5484a694d32183e91b747730d |
| nantahala-family-640.avif | 640×430 | 61ea4127650b4d96d85d939178769cdb24027187c6b8b2bf93fab7f0c7197bcb |
| nantahala-family-640.webp | 640×430 | ff155581e7e40119e87e61fef07921a4dd3d66ea5352d70ae199e5593b1c2be6 |
| nantahala-family-640.jpg | 640×430 | 9dd0e5ba4fea0399b8631f104f084d743ae4ea55342058b1b60ce2625527aa88 |
| nantahala-family-1024.avif | 1024×688 | 4cb6b7110d40bfd580ee5b36e06d48ed5861f380e657b4c7c2d82525a9bdab1b |
| nantahala-family-1024.webp | 1024×688 | 8216c6d24a11fa10a3945ace8d80ef20115d970fdf1e43835e54e948c3cba7d2 |
| nantahala-family-1024.jpg | 1024×688 | f358b984df1d6ab7a8d1a3fdc120f46ad4f787d2513172dd7aa6f591bd1e86d2 |
| nantahala-family-1600.avif | 1600×1075 | f6df70c6b3bf4dd12e3eafc2109b3b488341c0635b1172725707159fa3979f20 |
| nantahala-family-1600.webp | 1600×1075 | 5b9ebd1e1622f8c467f1ce3893091828791a84b2bbd7a493a1f9d1c4d365ca2c |
| nantahala-family-1600.jpg | 1600×1075 | 3bb25e56aa8c22a9f331f4e66a560fd8bd9f8e52d5f31e20aa6891db61471e40 |

### crabbing-mattamuskeet

- **Status:** held out of the daily rotation (`approved: false`). Upright this photograph is portrait (2988×5312). The original file carried EXIF orientation 8, which rotated the already-upright pixels onto their side. Variants were regenerated from the raw upright pixels with orientation stripped. Ed asked for landscape photos only, so this entry stays approved:false and is not in the daily rotation.
- **Location (as stated by the source):** Lake Mattamuskeet, North Carolina
- **Description / caption:** Crabbing the canals and Lake Mattamuskeet.
- **Date of photograph:** August 28, 2015
- **Photographer / author:** U.S. Fish and Wildlife Service (Southeast Region)
- **Credit shown on the page:** "Photo: U.S. Fish and Wildlife Service (public domain)"
- **License:** Public domain
- **Source page:** https://commons.wikimedia.org/wiki/File:Crabbing_Mattamuskeet_(26334453213).jpg
- **Original dimensions:** 2988 × 5312
- **Date accessed:** 2026-11-15 (America/New_York)

Derivatives in `static/featured-photos/crabbing-mattamuskeet/`:

| file | size | sha256 |
|---|---|---|
| crabbing-mattamuskeet-placeholder.jpg | 32×57 | 76afa17cb6f99310ed7a06fb4795654602d14b0f877fc3f44b889260510d36b8 |
| crabbing-mattamuskeet-640.avif | 640×1138 | a77b52dd26be1ce450d86ebf94a2a06dafd8dfdc2ae417a55be8ae3058361a2d |
| crabbing-mattamuskeet-640.webp | 640×1138 | 1f3658261cb462a8ae1e66000b95a53ec3a9c7c97c5b72910e77ff1dc402eddb |
| crabbing-mattamuskeet-640.jpg | 640×1138 | acedf2761bc9a9b0547234cf4090eee440af480a259c6977ac258846c159da58 |
| crabbing-mattamuskeet-1024.avif | 1024×1820 | 0ebeb5d394f2580a26c26de94c11aad57dd0acee16d9cfda88af64e17e9c4dc3 |
| crabbing-mattamuskeet-1024.webp | 1024×1820 | 2618e143c7640ffb2af0e67a656f634eb70119f4fdb69c63574a19c1d6554f73 |
| crabbing-mattamuskeet-1024.jpg | 1024×1820 | 21d0050fde4aa8ffbee1a8e52bf9744172e535c6a6986a79911496ade20923b1 |
| crabbing-mattamuskeet-1600.avif | 1600×2844 | d4cd04d0e934c1c360259dfea4cbcf6f88c317ab0f7b975d905204e734a23da4 |
| crabbing-mattamuskeet-1600.webp | 1600×2844 | fa25a60b795b67f842ee6101bcb5b6e32d0b8b1c88ec188831fb617764e462be |
| crabbing-mattamuskeet-1600.jpg | 1600×2844 | 933624331bff3ee2136a81a5783f1f96d7c79a7139f87a9ea8f4630446147fed |
