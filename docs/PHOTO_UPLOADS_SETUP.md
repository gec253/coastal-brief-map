# Photo submissions: setup guide

Product spec: `docs/CATCH_WALL_UPLOAD.md`. This guide is the ops checklist.

Status as of 14 Nov 2026: the code is in the repo, public uploads stay
**switched off**, and the Supabase project plus the Render URL, secret key,
and Pillow build command are already in place. Do not set
`PHOTO_UPLOADS_ENABLED` until Ed has finished a private test and says to
publish. With the flag unset, the public still sees no Share button, and
submit and admin routes 404 without the private preview cookie. In a
browser that has opened `/preview?key=…`, the Share form, `/admin`, and
`/preview/photos-check` work so Ed can test without turning the feature
on for everyone.

Nothing in this guide costs money. Every step uses a free tier. Do the steps in order.
Never paste a key into the repo, a chat, or a ticket. Keys go only into Render's
Environment page (and, if you run the check locally, your own shell).

## How it works (one paragraph)

A visitor picks Fishing or Coastal Life, chooses a photo (tap to pick, or
drag and drop), enters a name, and ticks the permission and age boxes. They
can hide the name on the public site with the anonymous toggle; the name is
still kept for Ed's review. The server does not use a CAPTCHA unless both
Turnstile keys are later set. It checks the file's real bytes (JPEG, PNG,
WebP, or iPhone HEIC), caps size (10 MB) and pixels (50 MP), applies the
camera orientation, rebuilds the image from pixels only (EXIF, GPS, camera
data are dropped), and writes four WebP files (400, 800, 1600 px wide and a
240 px thumbnail) to a **private** Supabase bucket, plus one row in a table
with `status = 'pending'`. Nothing is public yet. On `/admin` you sign in
with your password, review, edit category, caption, species, region,
location, date, name, or the anonymous flag, then Approve (files are copied
to the **public** bucket and the private copies deleted), Reject (private
files deleted), or later Remove a published photo (public files deleted).
Approved photos appear on their own gallery and on All photos within about
a minute. Tick "Feature on the home page" on a published photo to show it
in the home page strip (the first four featured photos are used).

Uploads never touch Render's disk or the repo, so deploys and restarts lose nothing.

## 1. Supabase project (free tier)

1. Sign in at https://supabase.com/dashboard and create a project (any name, e.g.
   `coastal-brief`, region US East). Save the database password in your password manager.
2. **Project Settings → API Keys.** Note the Project URL (`https://<ref>.supabase.co`).
   Create or copy a **secret key** (`sb_secret_...`). This key bypasses all row-level
   security. It goes only into Render as `SUPABASE_SECRET_KEY`; never into the browser,
   the repo, or a message. (A legacy `service_role` key also works, as
   `SUPABASE_SERVICE_ROLE_KEY`, but Supabase is retiring those keys at the end of 2026.)
3. **SQL Editor → New query**, paste everything below, and Run:

```sql
-- Buckets: pending is private, approved is public-read by URL only.
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values
  ('photos-pending',  'photos-pending',  false, 5242880, array['image/webp']),
  ('photos-approved', 'photos-approved', true,  5242880, array['image/webp'])
on conflict (id) do nothing;

-- One row per submission.
create table if not exists public.photo_submissions (
  id            uuid primary key,
  created_at    timestamptz not null default now(),
  status        text not null default 'pending'
                check (status in ('pending', 'approved', 'rejected', 'removed')),
  category      text not null check (category in ('fishing', 'life')),
  display_name  text check (char_length(display_name) <= 40),
  species       text check (char_length(species) <= 60),
  location      text check (char_length(location) <= 60),
  caption       text check (char_length(caption) <= 280),
  width         integer not null check (width > 0),
  height        integer not null check (height > 0),
  featured      boolean not null default false,
  consent_at    timestamptz not null,
  ip_hash       text,           -- salted hash for abuse control; the raw IP is never stored
  reviewed_at   timestamptz
);
create index if not exists photo_submissions_status_idx
  on public.photo_submissions (status, category, created_at desc);
create index if not exists photo_submissions_featured_idx
  on public.photo_submissions (featured) where featured;

-- Lock the table: row-level security on, no policies, no grants to browser roles.
-- Only the server (secret key) can read or write it.
alter table public.photo_submissions enable row level security;
revoke all on table public.photo_submissions from anon, authenticated;
```

If the table was already created from an earlier version of this SQL, run the
following in the SQL Editor as well. It is safe to run more than once. This
adds columns the site now writes: water type, the anonymous flag, the date
taken, and an optional region. Ed runs this by hand; the app never changes
the database schema itself.

```sql
-- Catch Wall columns added after the first setup (14 Nov 2026).
-- Safe to run more than once.

alter table public.photo_submissions
  add column if not exists water_type text;

update public.photo_submissions
  set water_type = 'saltwater'
  where water_type is null;

alter table public.photo_submissions
  alter column water_type set default 'saltwater';

do $$
begin
  if not exists (
    select 1 from pg_constraint where conname = 'photo_submissions_water_type_check'
  ) then
    alter table public.photo_submissions
      add constraint photo_submissions_water_type_check
      check (water_type is null or water_type in ('saltwater', 'freshwater'));
  end if;
end $$;

alter table public.photo_submissions
  add column if not exists anonymous boolean not null default false;

alter table public.photo_submissions
  add column if not exists taken_on date;

alter table public.photo_submissions
  add column if not exists region_id text;

do $$
begin
  if not exists (
    select 1 from pg_constraint where conname = 'photo_submissions_region_id_len'
  ) then
    alter table public.photo_submissions
      add constraint photo_submissions_region_id_len
      check (region_id is null or char_length(region_id) <= 40);
  end if;
end $$;
```

The code expects the table to be named `public.photo_submissions`. If the
table was created under a different name, either rename it or set
`SUPABASE_TABLE` in Render to that name.

   Storage needs **no policies**: with none, browser keys can't list, upload, or read the
   private bucket. Files in `photos-approved` can be fetched only by their exact URL,
   which the site gives out only for approved photos.

4. Check it: **Storage** shows both buckets, `photos-pending` marked Private and
   `photos-approved` marked Public. **Table Editor → photo_submissions** shows RLS enabled.

Free-tier note: Supabase pauses free projects after a week of inactivity (their
definition). Regular gallery traffic should count as activity, but that is not
guaranteed. If it ever pauses, galleries show their empty state (no errors) and the
Share button disappears until you press Restore in the Supabase dashboard.

## 2. Cloudflare Turnstile (optional, not used at launch)

Ed asked for no CAPTCHA at launch. Leave `TURNSTILE_SITE_KEY` and
`TURNSTILE_SECRET_KEY` unset. The form uses a hidden honeypot field plus
rate limits (5 per hour and 15 per day, per IP and per session, and 300
site-wide per day).

The Turnstile code stays in the repo, unused, so it can be switched on later
if spam gets through. To turn it on: add a Turnstile widget (hostnames
`thecoastalbrief.com` and `coastal-brief-map-server.onrender.com`, mode
Managed), then set both keys in Render. The widget loads only when a visitor
opens the Share form, and only if both keys are present. Submissions work
without them.

## 3. Admin password and session secret

On your own computer, in the repo folder (Python 3.11+ with Pillow is not needed for this):

```bash
python photos.py hash     # asks for a password (16+ characters) twice, prints scrypt$...
python photos.py secret   # prints a random 64-character session secret
```

Use a long, unique password from your password manager. Copy the two printed values
into Render in step 4. The password itself is never stored anywhere.

Why a password instead of a Supabase magic link: it needs no extra Supabase Auth setup,
email templates, redirect URLs, or third-party JavaScript on the admin page; it works
the same in iPhone Safari; and the server stays the only thing that holds the storage
key. Sign-in is rate-limited (6 tries per 15 minutes per connection), the session cookie
is HttpOnly, Secure, SameSite=Strict, signed with HMAC, and lasts 8 hours; every admin
action also needs a per-session CSRF token and a same-origin request.

## 4. Render settings

Render dashboard → the `coastal-brief-map-server` service.

**Settings → Build Command** (already set on 14 Nov 2026): it should be

```
pip install -r requirements-photos.txt
```

This installs Pillow and pillow-heif (iPhone HEIC). The rest of the site still needs no
packages; if this install ever fails, the site keeps running and uploads simply stay
off (no Pillow means the Share button never appears).

**Environment → Add environment variable** (names only; values from steps 1–3):

| Name | Value from |
| --- | --- |
| `SUPABASE_URL` | Supabase Project URL (already set) |
| `SUPABASE_SECRET_KEY` | Supabase secret key (`sb_secret_...`) (already set) |
| `PHOTO_ADMIN_PASSWORD_HASH` | output of `python photos.py hash` (needed for `/admin`) |
| `PHOTO_SESSION_SECRET` | output of `python photos.py secret` (needed for `/admin`) |
| `PHOTO_UPLOADS_ENABLED` | leave **unset** until Ed says to publish |
| `TURNSTILE_SITE_KEY` | optional; leave unset at launch |
| `TURNSTILE_SECRET_KEY` | optional; leave unset at launch |

Optional (defaults shown): `SUPABASE_PENDING_BUCKET=photos-pending`,
`SUPABASE_APPROVED_BUCKET=photos-approved`, `SUPABASE_TABLE=photo_submissions`.

Save. Render redeploys. With the flag still unset, nothing public changes.

## 5. Private test, then (later) turn it on

Public uploads stay off until Ed sets `PHOTO_UPLOADS_ENABLED=1`. You can test
first with the existing preview cookie.

### Private test mode (flag off)

1. Set `PHOTO_ADMIN_PASSWORD_HASH` and `PHOTO_SESSION_SECRET` in Render. Do not
   set `PHOTO_UPLOADS_ENABLED`. Redeploy.
2. On your phone or computer, open your usual private preview link
   (`/preview?key=…`) so this browser has the `cb_preview` cookie.
3. Open https://thecoastalbrief.com/preview/photos-check (same browser). You
   should get a JSON report. It never prints keys. You want: `pillow` true,
   `pillowHeif` true, `backendConfigured` true, `tableReachable` true,
   `pendingRoundTrip` true, `pendingBucketPrivate` true, `approvedBucketPublic`
   true, and `adminConfigured` true. `uploadsFlag` should be false.
4. Open https://thecoastalbrief.com/catch-wall in that same browser. "Share
   your photo" appears. Send one of your own photos. You should see "Thanks.
   Your photo is awaiting approval." In a browser without the preview cookie,
   the page still says "Photo sharing opens soon" and `/admin` is 404.
5. Open https://thecoastalbrief.com/admin in the preview browser, sign in,
   approve the photo, and check it appears on the Catch Wall (or Coastal Life)
   and All photos. Then try Remove.

The same check is also available on your computer (it prints only
"set"/"MISSING" or true/false, never a key):

```bash
pip install -r requirements-photos.txt
export SUPABASE_URL=... SUPABASE_SECRET_KEY=...
export PHOTO_ADMIN_PASSWORD_HASH='scrypt$...' PHOTO_SESSION_SECRET=...
python photos.py check
```

### Publishing (only when Ed says so)

In Render → Environment, add `PHOTO_UPLOADS_ENABLED` = `1`. Save (redeploys).
The Share button then appears for everyone, and `/admin` works without the
preview cookie.

**To turn it off again:** delete `PHOTO_UPLOADS_ENABLED` in Render (or set it
to `0`). Public submissions and the public admin page stop at once; a preview
cookie still unlocks them for a private test. Already-approved photos stay
visible (they are read from Supabase). To hide everything, also remove
`SUPABASE_URL`.

## Limits built in

- 10 MB per file, 50 megapixels, at least 320 px on the short side; JPEG, PNG, WebP, or iPhone HEIC.
- 5 submissions per IP per hour and 15 per day; the same caps per submission session; 300 site-wide per day.
- Name is required (max 40). Optional anonymous toggle hides it on the public site but keeps it for review. Species 60, location 60, caption 280. Species is kept only for Fishing.
- Optional region (from the site list, or Other) and optional date taken (typed, never auto-filled from the camera).
- A required rights checkbox ("I took this photo or have permission to share it") and a required 13-or-older checkbox.
- A hidden honeypot field. No CAPTCHA unless both Turnstile keys are later set.
- Pending files are never public; the admin page streams them through the server.

## Costs (checked 13 Nov 2026 on supabase.com/pricing and cloudinary.com/pricing)

Each approved photo is about 0.5 MB in total (four WebP sizes).

| Volume | Supabase | Cloudinary |
| --- | --- | --- |
| Launch: under ~1,000 photos, a few thousand gallery views a month | **$0** (Free: 1 GB storage, 5 GB egress + 5 GB cached egress) | $0 (Free: 25 credits; 1 credit = 1 GB storage or 1 GB bandwidth or 1,000 transformations) |
| Growing: ~2,000 photos, ~20,000 gallery views a month (~25–30 GB images served) | Free tier exceeded on egress → **Pro $25/month** (100 GB storage, 250 GB egress) | ~30 credits → **Plus $89/month** (225 credits) |
| Busy: ~10,000 photos, 100,000+ views (~150 GB served) | Pro $25/month, within quota | Plus $89/month, ~155 credits |

Recommendation: **Supabase**. It is already the database, stays free at launch, and the
first paid step is $25/month versus $89. Supabase Pro has a spend cap on by default.
Cloudinary's advantages (on-the-fly transforms, AI tagging) aren't needed because the
server makes the sizes once at upload.

A future saving, not built: serve approved images through the site's own domain so
Cloudflare's free cache absorbs most image traffic, which would keep Supabase egress near
zero and could keep the project on the free tier much longer.

## Testing locally (no accounts needed)

```bash
pip install -r requirements-photos.txt
python -m unittest tests.test_photos          # generated fixtures only
PHOTO_UPLOADS_ENABLED=1 PHOTO_BACKEND=fake PHOTO_FAKE_DIR=/tmp/cb-fake \
PHOTO_SESSION_SECRET=$(python photos.py secret) \
PHOTO_ADMIN_PASSWORD_HASH='<output of python photos.py hash>' \
python server.py --port 8800
```

The fake backend stores files in `PHOTO_FAKE_DIR`, does not use Turnstile, and
refuses to start when the `RENDER` environment variable is present, so it can't
run in production. To try private test mode locally, leave
`PHOTO_UPLOADS_ENABLED` unset, set `PREVIEW_KEY` to a 24+ character string, and
open `/preview?key=…` first.
