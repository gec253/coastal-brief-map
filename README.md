# Coastal Brief map — how to put this on the internet

This folder is a working test of the public Coastal Brief map. It shows NOAA wind, waves, and water temperature over a light map or a NOAA nautical chart. It is not the finished website, and it is not weather, surf, or fishing advice.

You do not need to be a programmer. The steps below use a web browser. Pricing below was checked on the companies’ own sites on Tuesday, November 10, 2026 (evening, Eastern Time).

## What you are aiming for

A public web address, such as `https://something.onrender.com`, that opens this map. After it is up, send that address back so the map can be checked live.

## Which host to use, and what it costs

This project is a small Python program. It has to sit in front of NOAA’s map services (a proxy) so the map works in a browser, and it keeps a short-term copy of tiles (a cache). The simplest realistic place to run that program is **Render**.

**Costs, verified November 10, 2026:**

1. **GitHub** (where the files live so Render can copy them): a free personal account. $0. Sign up at https://github.com/signup
2. **Render** Hobby workspace: $0 per month, plus whatever compute you pick. Source: https://render.com/pricing
3. **Render Free web service:** $0. Official page: https://render.com/docs/free
   - Render’s own docs say: do not use Free for production. It is fine for this first public test.
   - After 15 minutes with no visitors, the site goes to sleep. The next visitor waits about one minute while it wakes up. Render shows a loading page during that wake-up.
   - You get 750 free instance hours per month (sleeping time does not count). At the start of each month the 750 hours reset.
   - The Hobby plan includes 5 GB of outgoing traffic per month, then $0.15 per GB. A quiet test should stay under 5 GB. If you ever go over and have not added a card, Render may pause Free services for the rest of the month.
   - Files saved on the server (including the tile cache) are wiped when the service sleeps or restarts. That is expected. The map just fetches a fresh copy from NOAA.
4. **If you later want the site always awake:** on the same Render service, change the compute plan from Free to the plan Render lists as **“Less than 1 CPU”**, **$7 per month**, 512 MB RAM (plan id `0.5c-512mb`). Source: https://render.com/pricing
5. You do **not** need a paid custom domain for this first test. Render gives you a free `onrender.com` address.

**Other hosts I checked and am not asking you to use:**

- **Cloudflare Workers** free plan is $0 and stays awake (100,000 requests per day). Their pricing page was last updated October 2, 2026: https://developers.cloudflare.com/workers/platform/pricing/ That would be a good long-term fit, but it would mean rewriting this Python program in a different language. I did not do that, so it is not the path for this first launch.
- **Fly.io** no longer has an ongoing free tier for new accounts. New accounts get a $1 trial for up to 7 days, then pay-as-you-go. The smallest always-on machine is about $2.19 to $3.69 a month, plus data transfer. Setup is more technical (a command-line tool). Sources: https://fly.io/pricing and https://docs.fly.io/about/free-trial

## Files to upload (and what to leave out)

Upload only these:

- `index.html`
- `app.js`
- `styles.css`
- `server.py`
- `README.md`
- `Procfile`
- `render.yaml`
- `requirements.txt`
- the whole `data` folder (`snapshot.json`, `ads.json`, `windspd-colors.json`, `tide-stations.json`)
- the whole `vendor` folder (the Leaflet map library)

Do **not** upload the screenshot images (`phone-*.png`, `desktop-*.png`), `playwright-results.json`, or `TEST-LOG.md`. Those are test notes, and the pictures would make the upload slow.

## Step-by-step

Button names can change. If a screen does not match what is written here, stop and send a screenshot of that screen rather than guessing.

### A. Create a free GitHub account and put the files there

1. Open https://github.com/signup and create a free personal account. You will need an email address and a password. Confirm the email if GitHub asks you to.
2. After you are signed in, click **New** (or **New repository**) to create a repository.
3. Name it `coastal-brief-map`. Leave it **Public** (Render’s free plan can connect to a public repo without extra setup). Do not add a README, .gitignore, or license on this screen — we already have those files. Click the button to create the repository.
4. On the empty repository page, look for **uploading an existing file** or the **Add file** menu, then **Upload files**.
5. Drag in the files and folders listed above. Keep the same folder shape: `data` and `vendor` should still be folders, not a flat pile of files.
6. At the bottom, click the green button to commit (save) the files. Wait until GitHub shows the file list.

### B. Create a Render account and attach that repository

1. Open https://render.com and sign up. The easiest path is **Sign up with GitHub**, so Render can see the repository you just made. Official start of this flow: https://render.com/docs/free (under “Create a Free instance”) and Render’s first-deploy guide.
2. In the Render Dashboard, click **New**.
3. Choose **Web Service**.
4. Connect the `coastal-brief-map` GitHub repository when Render asks which repo to use.
5. If Render asks you to fill in settings by hand:
   - Language / runtime: **Python**
   - Branch: `main` (or `master`, if that is what GitHub shows)
   - Build command: leave this **blank**
   - Start command: `python server.py`
   - Instance / compute plan: **Free**
6. There is a `render.yaml` file in the folder that already lists those settings. If Render offers to use a Blueprint or detects that file, you can let it. If it does not, the hand-filled values in step 5 are enough.
7. Click the button to deploy / create the web service.
8. Wait. The first build often takes a few minutes. You want a status that says the deploy succeeded or the service is live — not “failed.”
9. Render will show a public URL, usually ending in `.onrender.com`. Open it in your browser. The first visit on the Free plan can take about a minute.

### C. What “working” looks like

- The page title is “Coastal Brief.”
- Condition numbers (waves, wind, water, pressure, tide) appear near the top.
- Scroll down to the map. On a phone, tap **Tap to use map**.
- You can switch **Wind**, **Waves**, and **Water temp**.
- You can switch **Light map** and **Nautical chart**.
- Under the map, the wind legend is labeled in knots (0, 20, 40, 60, 80, 100).
- You may see “Loading water temps…” for a few seconds the first time you pick Water temp. That is expected.

### D. What to send back

Please send:

1. The public URL (the `onrender.com` address).
2. A screenshot of the Render page that shows the service is live.
3. A few phone pictures of the live page: Wind, Waves, Water temp, and one with **Nautical chart** turned on.
4. If anything failed: a screenshot of the failed screen, or the exact error text. Do not try to “fix” GitHub or Render settings by guessing.


## Weather radar (optional)

The Radar layer uses WeatherAPI.com’s Radar API (NOAA MRMS tiles for the United States). It is available on their **Pro+** plan and up, listed at **$25 per month** on https://www.weatherapi.com/pricing (checked Thursday, November 12, 2026).

To make radar appear on the live site:

1. In the Render Dashboard, open the **Coastal Brief Map Server** service.
2. Open the **Environment** tab.
3. Add an environment variable named `WEATHERAPI_KEY`.
4. Paste **only the API key** (not a curl command or a full URL).
5. Save. Render will restart the service.

The key stays on the server. The browser never sees it. Tiles are requested through this site’s own `/api/radar` path.

If `WEATHERAPI_KEY` is missing, or the key is not on a Pro+ (or higher) plan, the Radar button shows a “Radar coming soon” note. Wind, waves, water temperature, the nautical chart, and tide search still work.

WeatherAPI’s terms allow commercial use on paid plans. Their radar docs ask you to show the `attribution` string they return (this site does that on the map). Radar is general information only and is not a substitute for official NWS marine forecasts.

## What you do not need to do yet

- Do not apply for Google AdSense for this step. The site already has its own ads-on/off file (`data/ads.json`). The program updates that file from official NWS alerts. AdSense is a later conversation.
- Do not buy a custom domain yet.
- Do not pay for the $7 plan until you have seen the free URL work and you want the site to stay awake.
- Do not edit `server.py` or the other code files unless asked.

## If the map is slow or blank after it has been idle

On the Free plan that is usually the one-minute wake-up. Wait, then refresh once. If it is still blank after two minutes, send a screenshot.

## The ad-pause rule (already in the program)

You do not have to run this yourself. For the record:

- A **gale warning** or anything stronger (storm warning, hurricane-force wind warning), or a **tropical storm warning** or **hurricane warning**, for North Carolina coastal marine zones, turns ads **off**.
- A **small craft advisory** does not turn ads all the way off. It only reduces ad density on the affected region’s pages (Outer Banks / northern sounds, Crystal Coast / central waters, or Cape Fear / southern waters).
- After a hard pause, ads stay off until **12 hours** have passed with no qualifying warning.
- Storm mode for the public site is still a separate switch and still needs your confirmation. It is not flipped automatically by this flag.

## Conditions at a glance — regions and stations

The dashboard reads `/api/conditions?region=<id>`. The server (`conditions.py`) builds it from `data/regions.json`:

- Each region lists, for every reading, the stations to use in order of preference. The first station with a fresh report wins, and the page names it.
- Readings older than their normal reporting gap are marked stale with their time. Readings older than 12 hours are shown as unavailable. Nothing is filled in.
- Upstream calls are cached on disk: about 6–8 minutes for observations, 30 minutes for NWS forecasts, 5 minutes for alerts, 6 hours for tide predictions.

To add a region, add an entry to `regions` (and any new stations to `stations`), check every source against live data, then set `"enabled": true`. Only enabled regions appear in the selector.
