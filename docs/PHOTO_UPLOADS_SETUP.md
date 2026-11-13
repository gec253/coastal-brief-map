# Photo submissions: setup guide

Status: **built and deployed, switched off.** `PHOTO_UPLOADS_ENABLED` is not set in
production, so `/api/photos/submit`, `/admin`, and every `/api/admin/*` route answer
404 without reading a request body, and the galleries say "Photo sharing opens soon".

Nothing in this guide costs money. Every step uses a free tier. Do the steps in order.
Never paste a key into the repo, a chat, or a ticket. Keys go only into Render's
Environment page (and, if you run the check locally, your own shell).

## How it works (one paragraph)

A visitor picks Fishing or Coastal Life, chooses a photo, and ticks the permission box.
The server checks Cloudflare Turnstile, checks the file's real bytes (JPEG, PNG, WebP,
or HEIC), caps size (15 MB) and pixels (50 MP), applies the camera orientation,
rebuilds the image from pixels only (EXIF, GPS, camera data are dropped), and writes
four WebP files (400, 800, 1600 px wide and a 240 px thumbnail) to a **private**
Supabase bucket, plus one row in a table with `status = 'pending'`. Nothing is public
yet. On `/admin` you sign in with your password, review, edit category, caption,
species, location, or name, then Approve (files are copied to the **public** bucket and
the private copies deleted), Reject (private files deleted), or later Remove a
published photo (public files deleted). Approved photos appear on their own gallery
and on All photos within about a minute. Tick "Feature on the home page" on a published
photo to show it in the home page strip (the first four featured photos are used).

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

   Storage needs **no policies**: with none, browser keys can't list, upload, or read the
   private bucket. Files in `photos-approved` can be fetched only by their exact URL,
   which the site gives out only for approved photos.

4. Check it: **Storage** shows both buckets, `photos-pending` marked Private and
   `photos-approved` marked Public. **Table Editor → photo_submissions** shows RLS enabled.

Free-tier note: Supabase pauses free projects after a week of inactivity (their
definition). Regular gallery traffic should count as activity, but that is not
guaranteed. If it ever pauses, galleries show their empty state (no errors) and the
Share button disappears until you press Restore in the Supabase dashboard.

## 2. Cloudflare Turnstile (free)

1. Cloudflare dashboard → **Turnstile → Add widget**. Name: `Coastal Brief photos`.
   Hostnames: `thecoastalbrief.com` and `coastal-brief-map-server.onrender.com`.
   Widget mode: **Managed**. No pre-clearance needed.
2. Copy the **Site key** (public) and **Secret key** (server only).

The Turnstile script loads only when a visitor opens the Share form, never on the
dashboard pages.

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

**Settings → Build Command** (currently empty): set it to

```
pip install -r requirements-photos.txt
```

This installs Pillow and pillow-heif (iPhone HEIC). The rest of the site still needs no
packages; if this install ever fails, the site keeps running and uploads simply stay
off (no Pillow means the Share button never appears).

**Environment → Add environment variable** (names only; values from steps 1–3):

| Name | Value from |
| --- | --- |
| `SUPABASE_URL` | Supabase Project URL |
| `SUPABASE_SECRET_KEY` | Supabase secret key (`sb_secret_...`) |
| `TURNSTILE_SITE_KEY` | Turnstile site key |
| `TURNSTILE_SECRET_KEY` | Turnstile secret key |
| `PHOTO_ADMIN_PASSWORD_HASH` | output of `python photos.py hash` |
| `PHOTO_SESSION_SECRET` | output of `python photos.py secret` |
| `PHOTO_UPLOADS_ENABLED` | leave **unset** until step 5 |

Optional (defaults shown): `SUPABASE_PENDING_BUCKET=photos-pending`,
`SUPABASE_APPROVED_BUCKET=photos-approved`, `SUPABASE_TABLE=photo_submissions`.

Save. Render redeploys. With the flag still unset, nothing public changes.

## 5. Turn it on

1. (Recommended) Run the self-test on your computer with the same values exported in
   your shell (it prints only "set"/"MISSING", never a key):

   ```bash
   pip install -r requirements-photos.txt
   export SUPABASE_URL=... SUPABASE_SECRET_KEY=... TURNSTILE_SITE_KEY=... TURNSTILE_SECRET_KEY=...
   export PHOTO_ADMIN_PASSWORD_HASH='scrypt$...' PHOTO_SESSION_SECRET=... PHOTO_UPLOADS_ENABLED=1
   python photos.py check
   ```

   You want: backend supabase, table reachable, pending write/read/delete ok,
   "pending bucket is private", uploads active True, admin page True.
2. In Render → Environment, add `PHOTO_UPLOADS_ENABLED` = `1`. Save (redeploys).
3. Open https://thecoastalbrief.com/catch-wall on your phone: "Share your photo" appears.
   Send one of your own photos. You should see "Thanks. Your photo is awaiting approval."
4. Open https://thecoastalbrief.com/admin, sign in, approve it, and check it appears on
   the Catch Wall (or Coastal Life) and All photos. Then try Remove.

**To turn it off again:** delete `PHOTO_UPLOADS_ENABLED` in Render (or set it to `0`).
Submissions and the admin page stop at once; already-approved photos stay visible
(they are read from Supabase). To hide everything, also remove `SUPABASE_URL`.

## Limits built in

- 15 MB per file, 50 megapixels, at least 320 px on the short side; JPEG, PNG, WebP, HEIC.
- 5 submissions per connection per hour, 15 per day, 300 site-wide per day.
- Name 40, species 60, location 60, caption 280 characters. Species is kept only for Fishing.
- A hidden honeypot field plus Turnstile on every submission.
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

The fake backend stores files in `PHOTO_FAKE_DIR`, skips Turnstile, and refuses to start
when the `RENDER` environment variable is present, so it can't run in production.
