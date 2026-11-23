"""Presentation helpers for the Morning Brief refinement (t440u).

These functions format already-fetched official data. They do not fetch
anything and do not change a stored brief snapshot when used at render time.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

# NWS marine period names that mean "later today / tonight / tomorrow".
_OUTLOOK_NAMES = ("Tonight", "This Evening", "Tuesday", "Tue", "Tuesday Night")
_NIGHT_NAMES = ("Tonight", "Overnight", "This Evening", "This Morning")  # This Morning can be pre-dawn
_DAYTIME_NAMES = ("Today", "This Afternoon")


def _parse_iso(s) -> datetime | None:
    if not s:
        return None
    if isinstance(s, datetime):
        dt = s
    else:
        try:
            dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def when_et(s, always_weekday=True) -> str:
    """'Tue 6:00 AM ET' — weekday is always included so an end time is never bare."""
    dt = _parse_iso(s)
    if not dt:
        return ""
    local = dt.astimezone(ET)
    clock = local.strftime("%-I:%M %p").lstrip("0") if False else local.strftime("%-I:%M %p")
    if always_weekday:
        return local.strftime("%a ") + clock + " ET"
    return clock + " ET"


def _short_area(area: str | None) -> str:
    if not area:
        return ""
    text = re.sub(r"\s+", " ", area).strip()
    # Keep official wording; trim a trailing period; don't invent a shorter name.
    return text.rstrip(".")


def classify_alert(alert: dict, now: datetime) -> str:
    """'upcoming' if onset is after now, else 'current'."""
    onset = _parse_iso(alert.get("onset") or alert.get("effective"))
    if onset is not None and onset > now:
        return "upcoming"
    return "current"


def format_alert_line(alert: dict, now: datetime) -> dict | None:
    """One CURRENT or UPCOMING hazard line with start, end, and affected waters."""
    event = (alert.get("event") or "").strip()
    if not event:
        return None
    status = classify_alert(alert, now)
    onset = _parse_iso(alert.get("onset") or alert.get("effective"))
    ends = _parse_iso(alert.get("ends") or alert.get("expires"))
    area = _short_area(alert.get("areas") or alert.get("areaDesc") or "")
    start = when_et(onset) if onset else ""
    end = when_et(ends) if ends else ""
    if status == "upcoming":
        if start and end:
            text = "%s begins %s until %s" % (event, start, end)
        elif start:
            text = "%s begins %s" % (event, start)
        else:
            text = "%s (upcoming)" % event
    else:
        if end:
            text = "%s now in effect until %s" % (event, end)
        else:
            text = "%s now in effect" % event
    if area:
        text = "%s — %s" % (text, area)
    return {
        "event": event,
        "status": status,
        "onset": onset.isoformat() if onset else None,
        "ends": ends.isoformat() if ends else None,
        "areas": area,
        "text": text + ".",
    }


def format_hazards(alerts_block: dict, now: datetime) -> dict:
    """Group official (already status=actual) alerts into current vs upcoming."""
    if (alerts_block or {}).get("status") != "ok":
        return {"status": "unknown", "current": [], "upcoming": [], "line": "NWS advisories were not available at issue time."}
    items = list((alerts_block or {}).get("items") or [])
    # Dedup by event + onset + ends + area so two zones with the same window can be joined.
    seen = set()
    grouped = {}
    for a in items:
        onset = a.get("onset") or a.get("effective")
        ends = a.get("ends") or a.get("expires")
        area = _short_area(a.get("areas") or a.get("areaDesc") or "")
        key = (a.get("event"), onset, ends)
        if key in grouped and area and area not in (grouped[key].get("areas") or ""):
            prev = grouped[key]["areas"]
            grouped[key]["areas"] = (prev + "; " + area) if prev else area
            continue
        if key in seen:
            continue
        seen.add(key)
        grouped[key] = dict(a)
        grouped[key]["areas"] = area
    current, upcoming = [], []
    for a in grouped.values():
        row = format_alert_line(a, now)
        if not row:
            continue
        (upcoming if row["status"] == "upcoming" else current).append(row)
    if not current and not upcoming:
        return {"status": "clear", "current": [], "upcoming": [],
                "line": "No NWS marine advisories for this area."}
    parts = []
    if current:
        parts.append("CURRENT: " + " ".join(r["text"] for r in current))
    if upcoming:
        parts.append("UPCOMING: " + " ".join(r["text"] for r in upcoming))
    return {"status": "active", "current": current, "upcoming": upcoming, "line": " ".join(parts)}


def format_fresh_alerts(alerts_block: dict, now: datetime) -> dict:
    """Same grouping for Falls Lake (no marine wording in the empty state)."""
    base = format_hazards(alerts_block, now)
    if base["status"] == "clear":
        base["line"] = "No NWS alerts at the dam."
    elif base["status"] == "unknown":
        base["line"] = "NWS alerts were not available at issue time."
    return base


_DETERIORATE_RE = re.compile(r"\b(increas|build|strengthen|deteriorat|worsen|gale|storm)\w*\b", re.I)
_EASE_RE = re.compile(r"\b(diminish|subsid|eas(e|ing)|relax|lighten)\w*\b", re.I)


def deterioration_within(alerts: list, marine: dict, now: datetime, hours: int = 48) -> bool:
    """True if a watch/warning/advisory begins, or marine winds/seas increase, within hours."""
    horizon = now.timestamp() + hours * 3600
    for a in alerts or []:
        ev = (a.get("event") or "").lower()
        if not any(k in ev for k in ("watch", "warning", "advisory")):
            continue
        onset = _parse_iso(a.get("onset") or a.get("effective"))
        if onset is None:
            # Already in effect counts as current hazard, not future deterioration,
            # but a current warning still means we must not say things are easing overall.
            if any(k in ev for k in ("warning", "watch")):
                return True
            continue
        if now < onset and onset.timestamp() <= horizon:
            return True
        if onset <= now and any(k in ev for k in ("warning", "watch", "advisory")):
            # An active SCA/Gale Watch already in its hazard window.
            if "watch" in ev or "warning" in ev:
                return True
    for p in (marine or {}).get("periods") or []:
        name = p.get("name") or ""
        text = p.get("text") or ""
        # Skip the opening "Today/This Afternoon" easing clause; later periods matter.
        if name in ("Today", "This Afternoon", "This Morning"):
            continue
        if _DETERIORATE_RE.search(text or ""):
            return True
    return False


def take_easing_allowed(alerts: list, marine: dict, now: datetime) -> bool:
    """Today's marine discussion may mention easing only if nothing significant deteriorates in 24–48 h."""
    return not deterioration_within(alerts, marine, now, hours=48)


def daytime_period(periods: list, now: datetime | None = None) -> dict | None:
    """The daytime high period: 'Today' if present, else the next isDaytime period.

    After late afternoon, when the first period is Tonight, this returns
    tomorrow's daytime period. Never returns an overnight period. If the
    payload has no daytime flags (legacy tests), a period named Today or
    This Afternoon is used; a nameless first period is used only when it
    is not clearly a night period.
    """
    periods = list(periods or [])
    if not periods:
        return None
    now = now or datetime.now(timezone.utc)
    local = now.astimezone(ET)

    def is_night(p):
        name = (p.get("name") or "").strip()
        if p.get("isDaytime") is False:
            return True
        if name in ("Tonight", "Overnight", "This Evening") or name.endswith("Night"):
            return True
        return False

    def is_day(p):
        name = (p.get("name") or "").strip()
        if p.get("isDaytime") is True:
            return True
        if name in _DAYTIME_NAMES or name in ("Monday", "Tuesday", "Wednesday", "Thursday",
                                              "Friday", "Saturday", "Sunday", "This Morning"):
            # "This Morning" is a daytime period in NWS grids once the sun is up;
            # it is not used as the daily high if a later "Today"/"This Afternoon" exists.
            return name != "This Morning"
        return False

    for p in periods:
        name = (p.get("name") or "").strip()
        if name == "Today" and not is_night(p):
            return p
    for p in periods:
        name = (p.get("name") or "").strip()
        if name == "This Afternoon":
            return p
    # After 6 PM ET (or whenever Today is gone), the next daytime period.
    for p in periods:
        if is_day(p) and not is_night(p):
            return p
    # Legacy payloads with no names and no isDaytime: use the first period
    # only if it does not look like night.
    first = periods[0]
    if first.get("name") in (None, "") and first.get("isDaytime") is None:
        return first
    return None


def format_outlook(marine: dict) -> str | None:
    """Tonight and tomorrow from the already-fetched marine zone forecast."""
    if (marine or {}).get("status") != "ok":
        return None
    periods = marine.get("periods") or []
    skips = {"Today", "This Afternoon", "This Morning", "Overnight"}
    picks = []
    for p in periods:
        name = (p.get("name") or "").strip()
        if not name or name in skips:
            continue
        text = (p.get("text") or "").strip()
        if not text:
            continue
        sentences = [s.strip() for s in re.split(r"(?<=\.)\s+", text) if s.strip()]
        clip = " ".join(sentences[:2]) if sentences else text
        picks.append("%s: %s" % (name, clip))
        if len(picks) >= 2:
            break
    if not picks:
        return None
    zone = marine.get("zone") or ""
    issued = ""
    upd = marine.get("updated")
    if upd:
        issued = when_et(upd)
    tail = "NWS %s" % zone if zone else "NWS"
    if issued:
        tail += ", issued %s" % issued
    return " ".join(picks) + " (%s)." % tail


def parse_tide_events(text: str, issued_at) -> list[dict]:
    """Parse the stored tides line into aware datetimes. Does not change the line."""
    evs = re.findall(r"(low|high)\s+(\d{1,2}:\d{2}\s+[AP]M)\s+ET\s+\(([-.\d]+)\s*ft\)", text or "", re.I)
    issued = _parse_iso(issued_at)
    if not evs or not issued:
        return []
    issued = issued.astimezone(ET)
    day = issued.date()
    out = []
    last = None
    for typ, tm, ft in evs:
        dt = datetime.strptime(tm, "%I:%M %p").replace(year=day.year, month=day.month, day=day.day, tzinfo=ET)
        if last is not None and dt < last:
            dt = dt + timedelta(days=1)
        last = dt
        out.append({"time": dt, "type": typ.lower(), "ft": ft, "label": tm})
    return out


def tide_view(text: str, issued_at, view_now: datetime) -> dict | None:
    """Display-time next/passed tide from the already-stored predictions.

    The stored snapshot is not modified. If the issued 'next' tide is still
    in the future, the result matches the issued next tide and adjusted is False.
    """
    evs = parse_tide_events(text, issued_at)
    if not evs:
        return None
    view = view_now.astimezone(ET) if view_now.tzinfo else view_now.replace(tzinfo=timezone.utc).astimezone(ET)
    issued = _parse_iso(issued_at).astimezone(ET)
    issued_next = next((e for e in evs if e["time"] > issued), evs[-1])
    future = [e for e in evs if e["time"] > view]
    passed = [e for e in evs if e["time"] <= view]
    if future:
        nxt = future[0]
        adjusted = nxt["time"] != issued_next["time"]
        return {
            "next": nxt,
            "passed": passed,
            "adjusted": adjusted,
            "note": "Updated at view time from NOAA predictions" if adjusted else None,
            "issued_next": issued_next,
        }
    return {
        "next": None,
        "passed": passed,
        "adjusted": True,
        "note": "Updated at view time from NOAA predictions",
        "issued_next": issued_next,
        "when": "last today",
        "last": evs[-1],
    }


def offshore_station(seas_or_swell_line: str, freshness: list | None, label: str) -> tuple[str, str]:
    """(station name or id, observation time) for a seas/swell glance subtitle."""
    line = seas_or_swell_line or ""
    stn = ""
    m = re.search(r"\bat\s+(.+?)(?:;|\.|$)", line)
    if m:
        stn = m.group(1).strip().rstrip(".")
    time = ""
    for f in freshness or []:
        if (f.get("label") or "").lower() == label.lower() and f.get("time"):
            time = f["time"]
            if f.get("station") and not stn:
                stn = f["station"]
            elif f.get("station") and f["station"] not in stn:
                # Prefer the named buoy plus the id if the name didn't include it.
                if re.fullmatch(r"\d{5}", str(f["station"])):
                    stn = "%s, buoy %s" % (stn, f["station"])
            break
    return stn, time


def seas_sub(line: str, freshness: list | None, kind: str = "Seas") -> str:
    """Glance subtitle that identifies the offshore buoy and observation time."""
    period = dir_ = ""
    if kind == "Seas":
        m = re.search(r"([\d.]+)\s*ft every (\d+)\s*s from the (\w+)", line or "")
        if m:
            period, dir_ = m.group(2), m.group(3)
            base = "every %s s · from %s" % (period, dir_)
        else:
            base = ""
    else:
        m = re.search(r"([\d.]+)\s*ft at ([\d.]+)\s*s from the (\w+)", line or "")
        if m:
            per = m.group(2).rstrip("0").rstrip(".") if "." in m.group(2) else m.group(2)
            base = "%s s · from %s" % (per, m.group(3))
        else:
            base = ""
    stn, when = offshore_station(line, freshness, kind)
    bits = [b for b in (base, ("offshore, " + stn) if stn else "offshore buoy", when) if b]
    return " · ".join(bits)
