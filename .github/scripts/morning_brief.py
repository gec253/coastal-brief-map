#!/usr/bin/env python3
"""Morning Brief automation steps for GitHub Actions (stdlib only; public endpoints, no secrets).

  guard    decide whether this run should act (Eastern time window + authorization end date)
  run      keep the Render service awake until 5:16 AM ET, call /api/brief/wake, wait for the build
  verify   check every required region's /api/brief, write the job summary, exit 1 if one did not publish
  archive  copy today's valid briefs into an archive directory (the brief-archive branch checkout)

All Eastern-time logic uses America/New_York, so it is correct in both EST and EDT.
For tests, NOW (ISO time) overrides the clock and SITE overrides the base URL.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
SITE = os.environ.get("SITE", "https://thecoastalbrief.com").rstrip("/")
REQUIRED = (os.environ.get("REGIONS") or "crystal-coast hatteras").split()
EXTRA = (os.environ.get("EXTRA_REGIONS") or "falls-lake").split()  # archived, reported, never fails the job
AUTO_UNTIL = (os.environ.get("AUTO_UNTIL") or "2026-11-20").strip()
WINDOW = ((4, 30), (6, 59))   # scheduled runs act only between 4:30 and 6:59 AM Eastern
WAKE_AT = (5, 16)              # the server builds nothing before 5:15
PUBLISH_BY = (5, 30)
KEEPALIVE_S = 240              # Render Free sleeps after about 15 idle minutes
UA = "TheCoastalBrief-automation/1.0 (+https://github.com/gec253/coastal-brief-map)"


def now() -> datetime:
    v = os.environ.get("NOW")
    return datetime.fromisoformat(v).astimezone(timezone.utc) if v else datetime.now(timezone.utc)


def et(d: datetime | None = None) -> datetime:
    return (d or now()).astimezone(ET)


def log(msg: str) -> None:
    print("[%s] %s" % (et().strftime("%H:%M:%S %Z"), msg), flush=True)


def out(key: str, val: str) -> None:
    p = os.environ.get("GITHUB_OUTPUT")
    if p:
        with open(p, "a") as f:
            f.write("%s=%s\n" % (key, val))


def summary(md: str) -> None:
    p = os.environ.get("GITHUB_STEP_SUMMARY")
    if p:
        with open(p, "a") as f:
            f.write(md + "\n")
    print(md)


def http(path: str, timeout: int = 120, tries: int = 1, pause: int = 20):
    """GET SITE+path. Returns (status, parsed JSON or None). Never raises."""
    last = (0, None)
    for i in range(tries):
        try:
            req = urllib.request.Request(SITE + path, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                body = r.read(2_000_000)
                code = r.status
        except urllib.error.HTTPError as e:
            code, body = e.code, e.read(200_000)
        except Exception as e:  # timeout, DNS, connection reset (cold start)
            log("%s attempt %d: %s" % (path, i + 1, type(e).__name__))
            code, body = 0, b""
        try:
            data = json.loads(body.decode("utf-8")) if body else None
        except ValueError:
            data = None
        last = (code, data)
        if code == 200 or code == 404:
            return last
        if i + 1 < tries:
            time.sleep(pause)
    return last


def decide(event: str, d: datetime | None = None, until: str = AUTO_UNTIL) -> tuple[bool, str]:
    e = et(d)
    if e.strftime("%Y-%m-%d") > until:
        return False, "Automatic publication ended after %s (ET). Ed must authorize an extension." % until
    if event == "workflow_dispatch":
        return True, "Manual run: wakes and verifies only; the server builds nothing before 5:15 AM ET."
    if WINDOW[0] <= (e.hour, e.minute) <= WINDOW[1]:
        return True, "Scheduled run inside the 4:30-6:59 AM ET window."
    return False, "Skipping: this cron is for the other half of the DST year (%s)." % e.strftime("%H:%M %Z")


def cmd_guard() -> int:
    go, why = decide(os.environ.get("EVENT", ""))
    log("Eastern time now: %s. %s" % (et().strftime("%Y-%m-%d %H:%M %Z"), why))
    out("go", "1" if go else "0")
    out("today", et().strftime("%Y-%m-%d"))
    return 0


def _at(e: datetime, hm) -> datetime:
    return e.replace(hour=hm[0], minute=hm[1], second=0, microsecond=0)


def cmd_run() -> int:
    """Keep the service awake until 5:16 ET, wake, then wait until both briefs report today (max ~5:32)."""
    start = et()
    if (start.hour, start.minute) < WAKE_AT:
        log("Keeping the site awake until %d:%02d AM ET." % WAKE_AT)
    while et() < _at(et(), WAKE_AT):
        code, _ = http("/api/health", timeout=90, tries=3, pause=15)
        log("health HTTP %s" % code)
        time.sleep(max(1, min(KEEPALIVE_S, (_at(et(), WAKE_AT) - et()).total_seconds())))
    code, data = http("/api/brief/wake", timeout=120, tries=5, pause=20)
    log("wake HTTP %s %s" % (code, json.dumps(data)[:600] if data else ""))
    if code == 404:
        log("The brief is switched off on the server (MORNING_BRIEF_ENABLED=0).")
        return 0
    if code != 200:
        log("Wake did not succeed after 5 tries; verify will still check each region.")
        return 0  # verify decides pass/fail per region
    deadline = max(_at(et(), (PUBLISH_BY[0], PUBLISH_BY[1] + 2)), et() + timedelta(minutes=4))
    while et() < deadline:
        regs = (data or {}).get("regions") or {}
        if all((regs.get(r) or {}).get("today") for r in REQUIRED):
            log("Both briefs report today's issue.")
            return 0
        time.sleep(60)
        code, data = http("/api/brief/wake", timeout=90, tries=2, pause=15)
        log("status HTTP %s %s" % (code, json.dumps((data or {}).get("regions"))[:600]))
    return 0


def check(rid: str, today: str):
    """Fetch and judge one region. Returns (published: bool, row dict, brief or None). Never raises."""
    code, b = http("/api/brief?region=%s" % rid, timeout=150, tries=3, pause=20)
    row = {"region": rid, "http": code, "issueDate": None, "issued": None, "reason": None, "validation": None,
           "missing": None, "result": ""}
    if code != 200 or not isinstance(b, dict) or not b.get("ok"):
        row["result"] = "NOT PUBLISHED: %s" % ((b or {}).get("error") if isinstance(b, dict) else "no response")
        return False, row, None
    row.update(issueDate=b.get("issueDate"), reason=b.get("reason"),
               validation=(b.get("validation") or {}).get("status"), missing=", ".join(b.get("missing") or []) or "none")
    try:
        ie = datetime.fromisoformat(b["issuedAt"]).astimezone(ET)
        row["issued"] = ie.strftime("%a %b %-d %-I:%M %p ET")
    except (KeyError, TypeError, ValueError):
        ie = None
    if b.get("regionId") != rid:
        row["result"] = "NOT PUBLISHED: wrong region returned"
        return False, row, None
    if b.get("staleNotice") or b.get("issueDate") != today:
        row["result"] = "NOT PUBLISHED: showing an older brief (%s)" % (b.get("staleNotice") or b.get("issueDate"))
        return False, row, None
    if ie is None:
        row["result"] = "NOT PUBLISHED: no issue time"
        return False, row, None
    late = (ie.hour, ie.minute) > PUBLISH_BY or ie.strftime("%Y-%m-%d") != today
    row["result"] = "published, LATE (after 5:30 AM ET)" if late else "published on time"
    return True, row, b


def cmd_verify() -> int:
    today = et().strftime("%Y-%m-%d")
    rows, failed = [], []
    for rid in REQUIRED + EXTRA:
        try:
            ok, row, _ = check(rid, today)
        except Exception as e:  # one region never stops the other
            ok, row = False, {"region": rid, "result": "NOT CHECKED: %s" % type(e).__name__}
        rows.append(row)
        if not ok and rid in REQUIRED:
            failed.append(rid)
    md = ["## Morning Brief %s (checked %s)" % (today, et().strftime("%-I:%M %p %Z")), "",
          "| Region | Result | Issued | Reason | Validation | Not available |", "|---|---|---|---|---|---|"]
    for r in rows:
        md.append("| %s%s | %s | %s | %s | %s | %s |" % (r["region"], "" if r["region"] in REQUIRED else " (info)", r.get("result"),
                  r.get("issued") or "-", r.get("reason") or "-", r.get("validation") or "-", r.get("missing") or "-"))
    md.append("")
    md.append("Required regions: %s. Automatic publication authorized through %s (ET)." % (", ".join(REQUIRED), AUTO_UNTIL))
    summary("\n".join(md))
    Path(os.environ.get("RESULTS", "brief-results.json")).write_text(json.dumps(rows, indent=1))
    if failed:
        print("::error::Morning Brief not published for: %s" % ", ".join(failed))
        return 1
    return 0


def cmd_archive(dest: str) -> int:
    """Write archive/YYYY-MM-DD/<region>.json and latest/<region>.json for today's valid briefs."""
    today = et().strftime("%Y-%m-%d")
    root = Path(dest)
    wrote = 0
    for rid in REQUIRED + EXTRA:
        try:
            ok, row, b = check(rid, today)
        except Exception as e:
            log("%s: not archived (%s)" % (rid, type(e).__name__))
            continue
        if not ok:
            log("%s: not archived (%s)" % (rid, row["result"]))
            continue
        day = root / "archive" / b["issueDate"]
        day.mkdir(parents=True, exist_ok=True)
        (root / "latest").mkdir(parents=True, exist_ok=True)
        text = json.dumps(b, indent=1, sort_keys=True, ensure_ascii=False) + "\n"
        (day / ("%s.json" % rid)).write_text(text)
        (root / "latest" / ("%s.json" % rid)).write_text(text)
        wrote += 1
        log("%s: archived %s issued %s" % (rid, b["issueDate"], row["issued"]))
    log("archived %d brief(s)" % wrote)
    return 0


if __name__ == "__main__":
    c = sys.argv[1] if len(sys.argv) > 1 else ""
    if c == "guard":
        sys.exit(cmd_guard())
    if c == "run":
        sys.exit(cmd_run())
    if c == "verify":
        sys.exit(cmd_verify())
    if c == "archive":
        sys.exit(cmd_archive(sys.argv[2] if len(sys.argv) > 2 else "."))
    print(__doc__)
    sys.exit(2)
