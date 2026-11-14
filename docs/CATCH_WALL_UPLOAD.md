# Catch Wall photo submissions

Status: **spec only.** Public uploads stay off. This document describes how
visitor photo submissions should work on thecoastalbrief.com, using Ed's
approved decisions (14 Nov 2026). Nothing here is turned on, and nothing is
deployed from this branch.

The site already has a complete, flag-gated submission and moderation system
(`PHOTO_UPLOADS_ENABLED`, default off). This spec keeps that system and lists
the changes needed to match Ed's decisions. It does not invent a second
pipeline.

Companion ops guide: `docs/PHOTO_UPLOADS_SETUP.md` (how to create storage,
set keys, and flip the flag — only after Ed approves those steps).

## What exists today

Built and deployed, switched off. With the flag unset, `/api/photos/submit`,
`/admin`, and every `/api/admin/*` route return 404 without reading a request
body. The Catch Wall, Coastal Life, and All photos pages say "Photo sharing
opens soon." Approved-photo galleries work only if a storage backend is
configured; otherwise they show the empty state.

Already in the repo:

- `photos.py` — submit, image checks, EXIF/GPS stripping, WebP sizes, rate
  limits, honeypot, admin password sessions, `photos.admin_action`
  (edit / approve / reject / remove).
- `server.py` — `/api/photos/config`, `/api/photos`, `/api/photos/submit`,
  `/admin`, `/api/admin/*`. Flag-off routes 404 before reading the body.
- `catch-wall.html` + `gallery.js` + `styles.css` — galleries, lightbox, and
  a share form (file picker, no drag-and-drop yet).
- `admin.html` — sign-in and review UI, `noindex`.
- `tests/test_photos.py` — flag off, format sniffing, EXIF strip, honeypot,
  rate limits, full moderation flow, admin auth. (`test_heic` needs
  pillow-heif; it is the one allowed failure.)
- `requirements-photos.txt` — Pillow and pillow-heif. Not installed in
  production today: `render.yaml` still has an empty build command.

How the current code behaves, compared with this spec:

| Topic | Today | This spec |
| --- | --- | --- |
| Moderation | Queue; Ed approves before anything is public | Keep |
| Credit | Name is optional; no anonymous toggle | Name by default; optional anonymous toggle |
| File size | 15 MB | 10 MB |
| Formats accepted | JPEG, PNG, WebP, HEIC | JPEG, PNG, WebP; keep HEIC on intake (see open questions) |
| Derivatives | WebP at 400, 800, 1600 px + 240 px thumb | Add AVIF alongside WebP, like the homepage photos |
| Date taken | Not collected | Optional date field |
| Region | Free-text location only | Optional region plus free-text location |
| Age / permission | Not collected | Short note and a required checkbox |
| Spam | Honeypot + per-IP limits + Cloudflare Turnstile | Honeypot + per-IP and per-session limits; no CAPTCHA at launch |
| Drag-and-drop | File picker / camera only | Add drag-and-drop on the same field |
| Storage | Coded for Supabase; not required to have been created yet | Still the recommendation; needs Ed's OK to set up |
| Feature flag | `PHOTO_UPLOADS_ENABLED`, default off | Keep this name; do not add a second flag |

Admin auth already exists and should be reused: a long password hashed with
scrypt (`PHOTO_ADMIN_PASSWORD_HASH`), an HMAC-signed HttpOnly / Secure /
SameSite=Strict cookie (`cb_admin`, 8 hours), a per-session CSRF token, a
same-origin check, and a login limit of 6 tries per 15 minutes per
connection. There is no separate admin email account and none is needed.

## User flow (mobile first)

Designed for a phone, where most Catch Wall photos will be taken and sent.
The same form works on a tablet or desktop.

1. On `/catch-wall`, `/coastal-life`, or `/photos`, the visitor sees
   **Share your photo** only if the flag is on and storage is configured.
   Otherwise the page still says "Photo sharing opens soon."
2. Tapping the button opens a full-height dialog (not a new account, not a
   new page). A short line at the top says photos are reviewed before they
   appear, no account is needed, and location data is removed from the file.
3. The visitor picks a photo:
   - On a phone: the file control opens the camera or the photo library.
   - On a desktop: they can click to browse or drag a file onto the dashed
     box. Drag-and-drop is a convenience, not the only path.
4. A preview of the file appears, with its name and size. If the file is
   over 10 MB or not a JPEG, PNG, or WebP (or HEIC, if that stays allowed),
   the form says so at once and does not send it.
5. They fill in the fields below, tick the required boxes, and tap
   **Send for review**.
6. The server checks everything again (never trust the browser), writes the
   cleaned images to the private pending bucket, and inserts a row with
   `status = 'pending'`. Nothing is public.
7. The dialog switches to: "Thanks. Your photo is awaiting approval." It
   will appear once it has been reviewed. Nothing else is needed from them.
8. Ed signs in at `/admin`, reviews the photo, edits text if needed, and
   Approves or Rejects. Approved files are copied to the public bucket and
   then the private copies are deleted. The photo shows up on its gallery
   and on All photos within about a minute.

The Share button and the submit route stay hidden and 404 when the flag is
off, so a visitor cannot discover or probe the form.

## Form fields

All labels are plain language. Optional fields are marked "optional."
Required fields use a 44 px target and a `16px` font so iPhone does not zoom.

| Field | Required | Notes |
| --- | --- | --- |
| Photo file | Yes | Camera, library, file picker, or drag-and-drop. `name="photo"`. |
| What kind of photo? | Yes | Fishing (Catch Wall) or Coastal Life. Same as today. |
| Which water? | Yes | Saltwater or Freshwater. Same as today. |
| Your name as shown | Yes, unless anonymous is on | Max 40 characters. This is the default: the name is shown as the credit. |
| Share anonymously | No, off by default | Toggle. When on, the public credit does not show a name. Recommended: still keep the name for Ed in the admin queue if they typed one; do not require it when the toggle is on. See open questions. |
| Species | No | Shown only for Fishing. Max 60 characters. Example: "Red drum." |
| Region | No | A list of the site's regions plus "Other / not listed." No map pin, no coordinates. |
| General location | No | Free text, max 60 characters. Example: "Cape Lookout," "Falls Lake." Not a street address. |
| Date the photo was taken | No | A date control, no time of day. Cannot be in the future. Stored as a calendar day only. |
| Caption | No | Max 280 characters. |
| Honeypot (`website`) | Must be empty | Hidden from people. See [Honeypot](#honeypot). |
| "I took this photo…" | Yes | Rights and display permission. See wording below. |
| Age / permission | Yes | See wording below. |

Consent checkbox, recommended wording:

> I took this photo, I have the right to share it, and I give The Coastal
> Brief permission to display it on this site. If other people are clearly
> identifiable in the photo, I have their permission too.

Age / permission note, shown next to a required checkbox:

> You must be 13 or older, or have a parent or guardian's permission, to
> share a photo.

The current form says "I took this photo or have permission to share it."
Ed asked for a checkbox confirming the submitter took the photo, so the
wording above is tighter. If Ed would rather keep the older "or have
permission" path (for a spouse sending a family photo, for example), that
is an open question.

No email field, no account, no phone number, no precise location.

## Validation (client and server)

The browser gives a fast "no" so a visitor is not waiting on a failed
upload. The server repeats every check and is the only authority.

**Client (gallery.js), before send:**

- A file is chosen.
- Size is at most 10 MB (`config.maxBytes` from `/api/photos/config`).
- The file's type, from the browser, looks like JPEG, PNG, or WebP (and
  HEIC if that stays allowed). This is a hint only.
- Category, water type, consent, and the age box are filled.
- Name is present unless the anonymous toggle is on.
- Date, if present, is not in the future.
- The honeypot is left empty (people never see it).

**Server (`photos.handle_submit`), after the flag and rate limits:**

- Multipart form, body capped at 10 MB plus a small overhead.
- Honeypot empty; consent and age boxes accepted; category and water type
  in the allowed lists.
- Name cleaned and required unless anonymous; all text fields stripped of
  control characters and clipped to their limits.
- Region, if sent, must be a known region id or `other`.
- Date, if sent, must be `YYYY-MM-DD`, not in the future, and not before
  1950.
- The file's real bytes are sniffed (`photos.sniff`), not the extension
  and not the `Content-Type` header: JPEG (`FF D8 FF`), PNG (8-byte
  signature), WebP (`RIFF…WEBP`). HEIC uses the `ftyp` brands if it stays
  allowed. Anything else is rejected, including GIF, PDF, HTML, and
  truncated JPEG junk.
- Size cap 10 MB; short side at least 320 px; at most 50 megapixels
  (`Image.MAX_IMAGE_PIXELS` plus a pixel-count check) so a crafted
  "decompression bomb" cannot blow memory.
- Animated images are rejected (except the existing still-HEIC / MPO
  cases if HEIC stays).
- Camera orientation is applied, then the image is rebuilt from pixels
  only. EXIF, GPS, camera make, and XMP do not survive. This already
  exists and should be kept.
- Output: AVIF and WebP at 400, 800, and 1600 px wide (never upscaled),
  plus a 240 px WebP thumbnail for the admin list. If the server cannot
  encode AVIF, it should still accept the photo and store WebP only, not
  fail the upload.
- On any storage error, pending objects for that id are deleted and the
  visitor sees a retry message. The row is not left half-written as
  approved.

## Moderation queue and Ed's approve/reject UI

Nothing a visitor sends is public until Ed approves it. There is no
auto-publish, including early on.

The admin page is `/admin`. It is `noindex`, is not linked from the public
site, and 404s when the flag is off or admin is not configured. Pending
images are not on a public URL; the page streams them through
`/api/admin/image/<id>/…` only to a signed-in session.

Tabs, already built: Pending, Published, Rejected, Removed.

On a pending card Ed can:

- See the photo, when it was sent (Eastern Time), pixel size, and the
  submitter name even if the public credit will be anonymous.
- Edit category, water, species, location, region, date, caption, and the
  name shown.
- Flip the anonymous flag if the name should or should not appear.
- **Approve and publish** — copies files to the public bucket, marks the
  row approved, deletes the private copies.
- **Reject** — deletes the private files, marks rejected. A rejected photo
  cannot later be approved without a new submission.

On a published card Ed can edit the same text, tick **Feature on the home
page** (the first four featured photos feed the home strip, already built),
or **Remove from the site** (public files deleted, status `removed`).
Remove is the takedown action once a photo is live.

Every write uses the CSRF token and a same-origin POST. Approve saves any
edits first so the published text is the corrected version.

## Credit display

On the gallery tile and in the lightbox:

- Line 1 (the "what"): species, location, and the date taken, if present,
  joined with a middot. Example: `Red drum · Cape Lookout · 12 Nov 2026`.
- Line 2 (the "who"): `Photo: {name}` when the submission is not
  anonymous and a name was given.
- When anonymous (or no name): omit the "who" line. Do not invent a
  byline. See open questions if Ed would rather show "Photo: a visitor."

Alt text stays descriptive and does not include a name when anonymous:
species or "Fishing photo" / "Coastal life photo," then location and
caption if any.

Photos stay the property of the people who took them. The gallery footer
already says this; keep that line.

## Rate limits

No CAPTCHA at launch. Limits apply to both the connection and a short
submission session.

| Limit | Number | Window |
| --- | --- | --- |
| Per IP | 5 | 1 hour |
| Per IP | 15 | 1 day |
| Per session | 5 | 1 hour |
| Per session | 15 | 1 day |
| Whole site | 300 | 1 day |

The IP is the Cloudflare `CF-Connecting-IP` header (already used), hashed
with a server secret before it is stored. The raw IP is never written to
the database.

The session is a new `cb_submit` cookie, not the admin cookie: a random
id, HttpOnly, Secure in production, SameSite=Strict, lasting 30 days. It
is not a login. If the visitor has no cookie yet, the server sets one and
still applies the IP limit. Clearing cookies does not bypass the IP cap.

Over the per-connection or per-session cap: HTTP 429, "Too many
submissions from this connection. Please try again later." Over the site
cap: HTTP 503, "Submissions are paused for today."

Admin login stays at 6 tries per 15 minutes per connection.

These counters live in memory on the web process, as they do today. A
Render restart resets them, which is slightly looser for a short window
and is acceptable at launch. Do not add a database just for counters.

## Honeypot

Keep the existing hidden field: `name="website"`, visually and for
assistive tech moved off-screen (`position: absolute; left: -9999px`),
`tabindex="-1"`, `autocomplete="off"`, labeled "Leave this empty." If it
has any value, the server returns 400 with a generic "Could not accept
that submission" and does not store the file. People never see the field.

## Privacy

- Rebuild every image from pixels so EXIF, GPS, and camera metadata are
  destroyed. Tests already assert that "GPS" and the camera make are gone
  from the output bytes.
- Do not store map coordinates, a street address field, or the raw IP.
- Location on the site is a region and/or a general place name only.
- The date field is a calendar day, not a timestamp from the camera.
  Do not silently copy the EXIF date into the database (the visitor types
  it if they want it shown).
- Pending files are private. Public URLs exist only for approved
  derivatives.
- The admin page and API are `noindex` / `Cache-Control: no-store`.

## Takedown path

Two paths, no new email account:

1. **Ed already logged in:** on a published photo, **Remove from the site**
   deletes the public files and marks the row `removed`. It disappears from
   the galleries at the next cache refresh (about a minute).
2. **Public request:** a short line in the gallery footer, "If this is
   your photo, or you are in it, and you want it taken down, you can send
   a removal request." That opens a small form (photo page or id, name,
   a short message). The form is rate-limited like submissions, has the
   same honeypot, and lands in the admin UI as a takedown request for Ed
   to act on with Remove. No auto-delete.

If Ed would rather be reached some other way he already uses, the footer
can point there instead. See open questions.

## Feature flag

Keep **`PHOTO_UPLOADS_ENABLED`**. It is already wired. Default is off
(unset, `0`, `false`, or `off`). Uploads turn on only when the value is
`1`, `true`, `yes`, or `on`, and a storage backend and Pillow are present.

Do not add a second flag such as `CATCH_UPLOADS_ENABLED`. Two names would
make it too easy to turn the wrong thing on.

With the flag off:

- `/api/photos/submit` and all `/api/admin/*` routes, and `/admin`, return
  404 and do not read a body.
- `/api/photos/config` reports `{ "uploads": false }`.
- The Share button stays hidden; the page says "Photo sharing opens soon."

Turning it on in production is a separate step, only after Ed has seen a
private test and has approved the storage setup and the Render build
command. To turn it off again, delete the variable or set it to `0`.
Already-approved photos would stay visible if storage is still configured;
removing `SUPABASE_URL` would hide them.

## Storage (the key open question)

The site runs on Render as a **free** web service (`render.yaml`:
`plan: free`, empty build command). Render's own docs (checked 14 Nov
2026) say a free web service has an **ephemeral** disk: any file written
locally is lost on deploy, restart, or when the service sleeps after 15
minutes idle. Free services cannot attach a persistent disk.

So visitor photos cannot live on the Render box. They have to live in a
store that survives restarts. Creating that store is a new database and
storage change, and Ed's standing rule is that this needs his approval.
This branch does not create it and does not change Render config.

Options (costs checked 13–14 Nov 2026):

| Option | Launch cost | Later cost | Fits the existing code? | Notes |
| --- | --- | --- | --- | --- |
| **1. Supabase Storage + one Postgres table (recommended)** | **$0** (Free: 1 GB storage, 5 GB egress + 5 GB cached egress) | About 2,000 photos and ~20,000 gallery views/month can exceed free egress → **Pro $25/month** (100 GB storage, 250 GB egress). Spend cap is on by default. | Yes. `photos.py` already talks to Supabase over HTTPS with the secret key; no SDK. Private `photos-pending` bucket, public `photos-approved` bucket, table `photo_submissions` with row-level security and no browser grants. | Free projects can pause after a week of inactivity. Gallery traffic should count as activity, but that is not guaranteed. Keys go only in Render's Environment page, never in the repo or in chat. |
| 2. Render persistent disk | Not possible on the free web service. Would need a paid instance (**$7/month** for "Less than 1 CPU") plus **$0.25 per GB per month** for the disk. | $7 + disk, ongoing. Adding a disk also turns off zero-downtime deploys. | No. Would need a new backend. | This is a Render configuration change and a new paid plan. Not recommended, and not to be done without Ed's approval. |
| 3. Files in the git repo or on the ephemeral disk | $0 | Lost on every restart; also bloats the repo and cannot hold pending (private) files safely. | No | Rejected. |
| 4. Cloudflare R2 | $0 at launch (10 GB storage/month and 10 million writes on the free tier; no egress fee for the usual path). | Stays cheap for a long time. | No. Would need a new backend in `photos.py`, plus somewhere to store the submission rows (R2 is files only). | A fair later alternative if Supabase egress becomes the problem. It is a new paid-account-capable service, so it still needs Ed's OK, and it is more work than using the code already written. |
| 5. Cloudinary | $0 on a small free credit bucket | Growing traffic → **Plus $89/month**. | No | Already compared in the setup guide. Not needed; the server makes the sizes once at upload. |

**Recommendation: option 1, the free Supabase project the code is already
written for.** It is $0 to start, it keeps pending files private, and it
survives Render sleeps and deploys. The first paid step, if the galleries
ever get that busy, is $25/month — ask Ed before upgrading.

A later saving, not built: serve approved images through thecoastalbrief.com
so Cloudflare's free cache takes most of the traffic and Supabase egress
stays low.

Before go-live, the SQL in `docs/PHOTO_UPLOADS_SETUP.md` also needs a
`water_type` column (the code already writes it) plus the new columns in
this spec (`anonymous`, `taken_on`, `region_id`). That schema change needs
Ed's approval too. Do not run it until he says so.

Also needed, no cost, but it is a Render setting change: set the service
build command to `pip install -r requirements-photos.txt` so Pillow is
installed. If that install ever failed, the site would keep running and
uploads would simply stay off. Ask before changing it. Do not edit
`render.yaml` in this work.

## Proposed file paths

No new top-level pages. Paths below are the files to change when Ed
approves implementation. This branch only adds the spec itself.

| File | Role |
| --- | --- |
| `docs/CATCH_WALL_UPLOAD.md` | This spec (new in this branch). |
| `docs/PHOTO_UPLOADS_SETUP.md` | Ops guide: 10 MB cap, optional Turnstile, new SQL columns, pointer to this spec. |
| `photos.py` | 10 MB cap; AVIF + WebP output; anonymous, date, region, age checkbox; session rate limit; Turnstile not required for launch. Keep `PHOTO_UPLOADS_ENABLED` off by default. |
| `tests/test_photos.py` | Cover the new fields, 10 MB, session limits, anonymous credit, AVIF when available, submit without Turnstile, flag still 404s when off. |
| `catch-wall.html` | Form fields, drag-and-drop target, 10 MB hint, no Turnstile widget at launch, age note, takedown footer line. |
| `gallery.js` | Client checks, drag-and-drop, credit line for anonymous and date, no CAPTCHA unless keys are later set. |
| `admin.html` | Show name / anonymous, date, and region; takedown-request list if that form is built. |
| `styles.css` | Drag-and-drop highlight and spacing for the new fields only. Do not restyle the galleries. |
| `server.py` | 10 MB error text; set/read the `cb_submit` cookie; optional takedown POST. Do not change public `/`, `/brief`, or map routes. |
| `requirements-photos.txt` | Already lists Pillow and pillow-heif; keep. AVIF should use what Pillow/pillow-heif already provide, not a new paid service. |

Do not add a new database client library, a new email service, or keys in
the repo. Do not commit `data/ads.json` (it can change under the live
server). Do not change `render.yaml`.

## Test plan

Run from the clone, with the flag off in the default environment (the
unit tests turn it on only inside the test process, using the local fake
backend, which refuses to start when `RENDER` is set):

```bash
python3 -m unittest discover -s tests
```

Only `test_heic` may fail or error (it needs pillow-heif). Everything else
must pass, including the existing photo tests and the public-page byte
checks.

When the implementation work is later approved, add or extend tests for:

1. Flag off: submit and admin still 404; `/api/photos/config` has
   `uploads: false`.
2. Real byte sniffing: JPEG/PNG/WebP accepted; GIF, HTML, and truncated
   JPEG rejected; extension and `Content-Type` ignored.
3. 10 MB cap and the 50 MP decompression-bomb cap; images under 320 px
   rejected.
4. EXIF/GPS/camera make stripped; orientation applied; no upscaling.
5. AVIF and WebP derivatives (or WebP-only when AVIF encoding is missing).
6. Honeypot filled → 400, no row, no files.
7. Five submits in an hour from one IP or one session succeed, the sixth
   is 429; site-wide 300/day returns 503.
8. Name required when anonymous is off; public credit hidden when it is on;
   admin list still shows the name if one was given.
9. Date in the future rejected; region must be a known id or `other`.
10. Consent and age boxes required.
11. Full flow: pending is not public → edit → approve → appears on the
    right gallery → feature → remove deletes public files.
12. Reject cannot be approved later.
13. Admin: wrong password 401; sixth login try 429; tampered cookie
    refused; CSRF and cross-origin POSTs refused.
14. Fake backend refused when `RENDER` is set.

Manual check on a phone, only in a local or private environment with the
flag on and the fake backend: open the form, pick a photo from the camera
roll, send it, confirm the thank-you message, approve in `/admin`, and
confirm it appears on Catch Wall with the right credit. Confirm that
without the flag, the live site still says "Photo sharing opens soon" and
`/admin` is 404.

## Open questions for Ed

1. **Storage.** May we create a free Supabase project (new database and
   file store, $0 at launch) so photos survive Render restarts? This is
   the recommended path. The first paid step later would be $25/month, and
   we would ask before that.
2. **Render build command.** May we set the existing web service build
   command to `pip install -r requirements-photos.txt` so photo processing
   can run? No cost. We will not change `render.yaml` or any other Render
   setting until you say so.
3. **iPhone HEIC.** The brief asked for JPEG, PNG, and WebP only. iPhones
   shoot HEIC by default, and the server already converts HEIC to ordinary
   web images and strips metadata. May we keep accepting HEIC on the way
   in, so people do not have to convert a photo before sending it?
4. **Anonymous names.** When someone ticks "share anonymously," should we
   still collect a name for your review queue only, and hide it on the
   public page? Or skip the name entirely?
5. **Anonymous credit.** If there is no public name, should the tile show
   no byline (recommended), or "Photo: a visitor"?
6. **Consent wording.** Use the tighter "I took this photo" box, or keep
   "I took this photo or have permission to share it" for family members
   sending a photo they did not press the shutter on?
7. **Age box.** Is a required "I am 13 or older, or I have a parent or
   guardian's permission" checkbox all right?
8. **Date taken.** Optional, as written? And is it all right that we do
   not auto-fill it from the camera's hidden date?
9. **Region.** Is an optional region list (plus free-text location) what
   you want, or is free-text location enough?
10. **Takedown.** Is a short removal form that lands in your admin queue
    all right, or do you already have a contact path you would rather
    print in the footer?
11. **CAPTCHA later.** We will ship without Turnstile, as you asked. May
    we leave the unused code in place so it can be switched on later if
    spam gets through the honeypot and the rate limits?
12. **Has a Supabase project already been created** for this site, or is
    that still to do? (Keys must not be pasted in chat either way.)
13. **When to turn the flag on.** Recommendation: after you have approved
    the storage setup, the build command, and a private test with one of
    your own photos. Public sharing stays off until you say to publish it.

## What this branch does not do

- Does not push, deploy, or touch the Scout clone at
  `/workspace/coastal-brief-repo`.
- Does not set `PHOTO_UPLOADS_ENABLED`, change `render.yaml`, or add
  environment variables.
- Does not create a Supabase project, a disk, or any paid service.
- Does not commit `data/ads.json`.
- Does not turn on public uploads or change the live Catch Wall, homepage,
  map, or briefs.
