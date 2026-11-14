# Morning Brief automation (unattended, Nov 14–20, 2026)

Ed authorized automatic publication of the Crystal Coast and Hatteras Morning Briefs for
**Nov 14–20, 2026 (Eastern)** with no daily approval (13 Nov 2026, 8:30 PM ET). Nothing in the code or the
workflow ever required a manual approval step; approval was a team practice, now waived for this window.
No security or quality check was removed. Validation was added.

## How it works

| Piece | Where | What it does |
|---|---|---|
| In-app scheduler | `brief.py` `_scheduler` / `run_window` | At 5:15 AM ET builds every enabled region; retries regions with missing sections every 3 min until 5:30. Skips regions that already have a complete brief for today. If the service starts between 5:15 and 5:30 it runs right away. |
| Wake endpoint | `GET /api/brief/wake` | Builds today's brief only for regions that lack one, in the background. Builds **nothing before 5:15 AM ET** and nothing after the window ends. Returns per-region status (today yes/no, issue time, validation, last error), never brief content. |
| Workflow | `.github/workflows/morning-brief-wake.yml` + `.github/scripts/morning_brief.py` | Keeps the Render service awake, wakes the build after 5:16, verifies each region, archives the briefs. Runs on GitHub's servers, so it does not depend on Ed, Scout, or any chat session. |
| Archive | branch `brief-archive` (never `main`, so no Render or Pages deploy) | `archive/YYYY-MM-DD/<region>.json` and `latest/<region>.json`. Started with the Nov 13 briefs. |
| Restart fallback | `brief._archived` | Render's disk is ephemeral. After a restart the server reads `latest/<region>.json` from raw.githubusercontent.com (6 s timeout, cached 10 min, checked for the right region and shape). If it is today's brief it is served as-is instead of being rebuilt; otherwise it is the dated fallback. |

Once per region per day: builds go through a per-region lock (`_ensure`), so a wake, a page view and the
scheduler at the same moment produce one build. Scheduler retries only replace an earlier brief from the same
day when the new one has no more missing sections.

## Schedule (Eastern)

GitHub cron is UTC and often 5–30+ minutes late (sometimes a run is dropped), so there are six triggers. The
guard uses `America/New_York` local time and acts only between **4:30 and 6:59 AM ET**, so it is correct in
EST and EDT. `concurrency: morning-brief` makes runs wait for each other (a newer pending run replaces an
older pending one, which shows as cancelled, not failed).

| UTC cron | In EST (Nov–Mar) | In EDT (Mar–Nov) |
|---|---|---|
| 08:35 | 3:35 skip | 4:35 main run |
| 08:50 | 3:50 skip | 4:50 main run |
| 09:16 | 4:16 skip | 5:16 backup |
| 09:35 | **4:35 main run** | 5:35 backup |
| 09:50 | **4:50 main run** | 5:50 backup |
| 10:16 | **5:16 backup** | 6:16 backup |

### Tomorrow, Sat Nov 14, 2026 (EST)

- 3:35, 3:50, 4:16 AM: EDT triggers start and skip in seconds.
- **4:35 AM** (or whenever GitHub starts it): guard passes; `/api/health` every 4 min wakes Render (cold start
  about a minute) and keeps it awake.
- **5:15 AM**: in-app scheduler builds Crystal Coast, Hatteras (and Falls Lake), each validated.
- **5:16 AM**: workflow calls `/api/brief/wake` (5 tries, 20 s apart, 120 s timeout); builds any region the
  scheduler missed. Then polls status each minute until both report today's issue, up to 5:32.
- About 5:16–5:33 AM: verify step fetches each `/api/brief`, writes the job summary, fails red if a required
  region is not published (only after checking all). Archive job then commits to `brief-archive`.
- 4:50 / 5:16 AM triggers: run after the first one finishes as idempotent backups (nothing rebuilt, archive
  unchanged).
- If GitHub starts the first run late (for example 5:25), it skips the keep-alive and wakes immediately;
  the brief is then labeled with its real build time and "built on request" if after 5:45.

## Validation before publish (`brief.validate`)

Critical (the new brief is **not stored or shown**):
- region id and name match `data/regions.json`; location (anchor) matches;
- marine zone is the configured one (Crystal Coast AMZ158, Hatteras AMZ154);
- issue date is today's (ET; before 5:15 it is still yesterday's) and the issue timestamp is current (±10 min);
- at least one NWS forecast (marine or point) is present and no more than 24 h old;
- no more than half of the core sections are missing (advisories, wind, seas, marine forecast, tides, water temp).

Not critical, shown clearly: any single reading that is unavailable or stale is listed under "Not available
at issue time", stale ones with their last report time and "not used". Nothing is substituted. Forecasts
older than 24 h are listed as stale and not used. `validation.status` is `ok` or `partial`.

When a critical check fails: the page shows the last valid brief with its own date and the notice "Today's
brief could not be published because it did not pass the data checks. This is not today's brief…", or, if no
earlier brief exists anywhere, "The morning brief is unavailable right now." Region failures are independent
everywhere (scheduler, wake, page views, workflow verify, archive).

## Authorization window

- `brief.AUTO_PUBLISH_UNTIL = "2026-11-20"` (override: Render env `MORNING_BRIEF_AUTO_UNTIL=YYYY-MM-DD`).
- Workflow `AUTO_UNTIL` defaults to `2026-11-20` (override: repo variable `MORNING_BRIEF_AUTO_UNTIL`).
- From **Sat Nov 21, 12:00 AM ET**: the workflow skips (also manual runs), the scheduler and wake build nothing,
  and **page views build nothing**. Before 5:15 AM on Nov 21 the Nov 20 brief is still the current issue. After
  that the page shows the Nov 20 brief, clearly dated, with "Automatic Morning Brief publication is paused (the
  authorized period ended Nov 20, 2026). This is the last published brief…". If the server has restarted it
  uses the archived copy; if there is none, an unavailable message. Existing briefs are never deleted.
- To extend (Ed's OK required): change both dates in one commit, or set both overrides.

## Kill switch

`MORNING_BRIEF_ENABLED=0` on Render turns off the brief pages, the wake endpoint (404, which the workflow
reports without failing) and the scheduler. Disabling the workflow in GitHub Actions stops the runs.

## Safe testing

- `tests/test_brief_automation.py` (offline, injected clock, fake data, temp store): normal build, wrong zone,
  no forecast, majority missing, wrong date/time/name/location, stale readings named, old forecast not used,
  one region failing in wake and scheduler, once-per-day builds, concurrent requests, wake before 5:15,
  window end (Nov 21), archive fallback, workflow guard for every cron in EST and EDT, verify checks every
  region before failing, late/old detection, archive writes only today's valid briefs, keep-alive timing.
- Workflow linted with actionlint 1.7.12. Archive git step tested against a local bare repo (creates the
  orphan branch once, then "Nothing new to archive"; `main` untouched).
- A manual `workflow_dispatch` is safe: before 5:15 AM ET it only pings; after 5:15 it builds only a missing
  brief for today (the same thing a page view does) and archives it. It cannot publish a test brief.

## What can still go wrong

- **GitHub**: scheduled runs can be late or dropped under load (six triggers, starting 40 min early); an
  Actions outage. Scheduled workflows are disabled after 60 days without repo activity (not an issue this week).
- **Render**: outage or a slow/failed cold start. If the service is down at 5:15–5:33 nothing is published until
  it is back; the first visit afterwards builds it (labeled on request). A deploy during 5:15–5:30 restarts the
  service; the brief is rebuilt or taken from the archive.
- **Data sources** (NDBC, CO-OPS, api.weather.gov): partial outages show as "not available"; a big outage
  fails validation and the last valid brief is shown, dated.
- **raw.githubusercontent.com** unavailable: the restart fallback is skipped; behavior is as before.
- The workflow uses GitHub's built-in Actions token (`contents: write` only on the archive job), not Ed's
  personal token, so that token's Feb 11, 2027 expiry does not affect it.
- Render plan is not verified (render.yaml says free). On a paid plan the keep-alive pings are harmless.
