# Morning Brief (private build, not live)

`/brief?region=<id>` (page) and `/api/brief?region=<id>` (JSON) return 404 unless `MORNING_BRIEF_ENABLED=1`.
The flag is **not** set on Render. Code: `brief.py`, two routes in `server.py`. The brief never contains market
or Finviz data; it only reads the site's own conditions and freshwater assemblers.

## What a brief contains
1. **Issue time and data freshness at the top**: when it was built, why (scheduled / on request / rebuilt),
   word count, and the time of every reading it used (stale readings flagged).
2. Advisories (NWS), wind with the ~10 h trend from the NDBC station history, seas with the ~10 h trend,
   swell, pressure with the ~10 h change at the wind station, the first sentence of the NWS marine forecast,
   rain chance and high, the day's tides (MLLW), inshore and offshore water temperature.
   Freshwater regions (only when they are enabled): alerts, lake level vs guide curve, dam release, inflows,
   water temp, observed and forecast rain, weather.
3. **Captain's take, labeled "interpretation"**: up to four sentences chosen by fixed rules from the numbers
   (advisory in effect, wind eased/built ≥ 4 kt, short-period seas ≥ 3 ft, NWS text says diminishing/building,
   offshore vs inshore water ≥ 3 °F apart, lake ≥ 3 ft below guide curve, very low release). No LLM, no
   fishing claims, no observations that are not in the data.
4. Anything that could not be fetched is listed as "Not available at issue time", never guessed.

Target 120–200 words. Today's samples: Crystal Coast 185, Hatteras 177, Falls Lake 131.

## Scheduling (as built, no new services)
- With the flag on, `server.py` starts one daemon thread. It sleeps until **5:15 AM ET**, builds every enabled
  region (Crystal Coast, Hatteras; plus freshwater preview regions when `FRESHWATER_ENABLED=1`), and retries any
  region with missing sections every 3 minutes until **5:30 AM ET**. Building reuses the same cached fetchers as
  the live dashboard, so it does not slow or replace the live instruments, which keep refreshing all day.
- A brief "day" runs from 5:15 AM ET to 5:14 AM the next day.
- **On-request fallback**: if no brief exists for the current day when someone asks (the server was asleep at
  5:15 or restarted), it is built on the spot and labeled "Built on request because the 5:15 AM scheduled build
  did not run". It is then served to everyone else for the rest of the day.
- **Persistence**: in memory plus `cache/briefs/<region>.json`. Render's disk is ephemeral, so a restart loses
  the file; the next request rebuilds from current data and is labeled "rebuilt". It is not the 5:15 snapshot.

## Failure and staleness
| Situation | What readers see |
|---|---|
| Scheduled build ran | Brief labeled "Prepared on schedule at 5:15 AM ET" |
| Server asleep at 5:15 | First visit builds it, labeled "Built on request…" with the real build time |
| A source is down at build time | That line is left out and listed under "Not available at issue time" |
| A reading is older than its station's normal gap | Its time is shown with a red "stale" tag |
| Everything upstream is down, earlier brief exists | Earlier brief, with "Today's brief could not be built; this is the brief from …" |
| Nothing available at all | 503 with "The morning brief is unavailable right now. Live readings are on the conditions page." |
| Region not enabled | 404 |

Tested locally 13 Nov 2026 with live data: on-request build, memory reuse, reload from disk after a simulated
restart, next-day upstream failure (stale notice), empty store plus failure (503), disabled region (404), and the
scheduler firing at a patched time (both regions written with reason "scheduled").

## The catch, and what Ed must approve to go live
If the Render service spins down when idle, nothing runs at 5:15 and every day's brief will be built on the
first visit instead, at whatever time that is. To guarantee a 5:30 publish, one of these is needed:

| Option | Cost | Notes |
|---|---|---|
| A. Keep as is (on-request) | $0 | Honest labeling, but "published by 5:30" is not guaranteed |
| B. Free external ping at 5:16 ET (GitHub Actions scheduled workflow in the existing repo, or cron-job.org) hitting `/api/brief` for each region | $0 | Wakes the service and builds the brief. GitHub's schedule can run 5–30 min late at busy times; cron-job.org is a new account (Ed would create it) |
| C. Render Cron Job | Paid (Render bills cron jobs per run-minute, with a monthly minimum) | Most reliable; a new paid service and a hosting change, so needs Ed |
| D. Durable storage for briefs (e.g. a `briefs` table in the Supabase project planned for photos) | Free tier | Keeps the exact 5:15 brief across restarts; needs the Supabase project Ed hasn't created yet |

Recommendation: B (GitHub Actions, no new account) plus D once Supabase exists. Before launch Ed also needs to
approve: turning on `MORNING_BRIEF_ENABLED` on Render, where the brief is linked from (homepage card vs. its own
page), and the Captain's take wording rules.

## Samples (13 Nov 2026, built on request, live data)
```
### Morehead City · Beaufort — issued Fri Nov 13, 9:39 AM ET ( on-request , 185 words)
Freshness: Wind 9:10 AM ET; Seas 8:56 AM ET; Barometer 9:30 AM ET; Water level 9:30 AM ET; Water temp 9:30 AM ET
- Advisories: Small Craft Advisory until 10:00 AM ET.
- Wind: 11 kt from the NW, gusting 16, at Cape Lookout; down from 17 kt 10 h earlier.
- Seas: 4.9 ft every 5 s from the W at Onslow Bay Outer (CDIP 217); easing from 6.2 ft 10 h earlier.
- Swell: 0.3 ft at 10 s from the SSW (split from the buoy spectrum).
- Pressure: 29.70 inHg, rising, up 3.8 hPa over 10 h at CLKN7.
- Marine forecast: Today: NW winds 15 to 20 kt with gusts up to 25 kt, diminishing to 10 to 15 kt late this morning and afternoon. (NWS AMZ158)
- Rain: 16% chance through tonight; sunny, high 63°F.
- Tides: low 3:27 AM ET (0.5 ft), high 10:13 AM ET (3.6 ft), low 4:29 PM ET (0.8 ft), high 10:29 PM ET (2.7 ft) at Beaufort, Duke Marine Lab, MLLW.
- Water temp: 66°F inshore (Beaufort, Duke Marine Lab), 70°F offshore (buoy 41159).
Captain's take (interpretation): NWS rates conditions hazardous to small craft until 10:00 AM ET. Wind has eased 6 kt over the past 10 h. Seas are short-period wind chop, so expect a steep, close-together ride. The NWS marine forecast has wind or seas easing later today.

### Hatteras Island — issued Fri Nov 13, 9:39 AM ET ( on-request , 177 words)
Freshness: Wind 8:50 AM ET; Seas 8:56 AM ET; Barometer 9:24 AM ET; Water level 9:24 AM ET; Water temp 9:24 AM ET
- Advisories: Small Craft Advisory until 10:00 AM ET.
- Wind: 21 kt from the WNW, gusting 25, at Diamond Shoals; about steady from 23 kt 10 h earlier.
- Seas: 5.6 ft every 6 s from the SSW at Cape Hatteras East (CDIP 250); building from 4.9 ft 10 h earlier.
- Swell: 0.3 ft at 10 s from the S (split from the buoy spectrum).
- Pressure: 29.69 inHg, rising, up 4 hPa over 10 h at 41025.
- Marine forecast: Today: W winds 15 to 20 kt with gusts up to 25 kt, diminishing to 10 to 15 kt late. (NWS AMZ154)
- Rain: 21% chance through tonight; sunny, high 58°F.
- Tides: low 5:11 AM ET (0.4 ft), high 11:08 AM ET (0.7 ft), low 6:03 PM ET (0.4 ft), high 11:58 PM ET (0.6 ft) at USCG Station Hatteras, MLLW.
- Water temp: 62°F inshore (USCG Station Hatteras), 69°F offshore (buoy 41120).
Captain's take (interpretation): NWS rates conditions hazardous to small craft until 10:00 AM ET. Seas are short-period wind chop, so expect a steep, close-together ride. The NWS marine forecast has wind or seas easing later today. Offshore water is 6°F warmer than inshore.

### Falls Lake — issued Fri Nov 13, 9:37 AM ET ( on-request , 131 words)
Freshness: Lake level 9:00 AM ET; Water temp 9:00 AM ET
- Alerts: Frost Advisory until Sat 8:00 AM ET; Freeze Watch until Sun 8:00 AM ET.
- Lake level: 245.07 ft (NGVD29), 6.43 ft below the 251.5 ft guide curve; -0.06 ft in 24 h.
- Dam release: 60 cfs below Falls Dam (regulated), below lowest daily mean for this date.
- Inflows: Eno River near Durham 5.4 cfs, much below normal; Flat River at Bahama 2.9 cfs, much below normal.
- Water temp: 62°F at the dam sensor.
- Rain: 0.00 in last 24 h at the dam; NWS forecast 0.01 in in next 24 h.
- Weather: Sunny, high 58°F, wind NW 6 to 10 mph.
Captain's take (interpretation): The lake is 6.4 ft below its guide curve, so more shoreline is exposed than usual; check NCWRC ramp notices before launching. Flow below the dam is very low for the date. Check the Frost Advisory before an early start.

```
