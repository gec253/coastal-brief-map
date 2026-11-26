"""Current official NWS alert status for public alert displays (Ed t487u, Nov 26, 2026).

Pure functions over api.weather.gov alert features. Nothing here fetches on its own; callers pass a
`fetch(url) -> dict | None` function. Used by:

* the Morning Brief "Status now" section (brief.py): the 5:15 AM list stays as issued, and each
  issued product is reconciled against the current feed by following NWS links (replacedBy,
  references) and VTEC event identity (office.phenomenon.significance.ETN);
* the public conditions alert strip (sprint_home.py): UPCOMING vs IN EFFECT labels with the
  official start time, and in-region zone names when one event name appears more than once;
* the Coastal Flood Warning note next to predicted tides (sprint_home.py, brief.py).

Principle (Ed t484u): missing data is uncertainty, never evidence of safety. A warning from the
issued list is only called ended when the current feed was read cleanly AND its NWS record chain
was followed to the end with no current replacement. Otherwise it is "status unconfirmed".

The advertising safeguard (server.evaluate_ads) has its own parser and is not used or changed here.
"""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
ALERTS_BASE = "https://api.weather.gov/alerts/"
MAX_CHAIN = 6            # replacedBy hops followed per issued product
LOOKUP_BUDGET_S = 10.0   # wall-clock budget for all record lookups on one page view

_VTEC_RE = re.compile(r"^/([OTEX])\.([A-Z]{3})\.([A-Z]{4})\.([A-Z]{2})\.([A-Z])\.(\d{4})\.(\d{6}T\d{4}Z)-(\d{6}T\d{4}Z)/$")
_UGC_RE = re.compile(r"^[A-Z]{2}[CZ]\d{3}$")
_REPLACED_RE = re.compile(r"^\s*The .{0,80}? has been (replaced|cancelled|canceled)\b", re.I)
TERMINAL_ACTIONS = ("CAN", "EXP")
CONTINUE_ACTIONS = ("CON", "EXT", "EXA", "EXB", "NEW", "COR", "UPG")

UNCONFIRMED_TEXT = "Status unconfirmed — check NWS"
FLOOD_TIDE_NOTE = ("Predicted tides do not include storm surge or other weather-driven water levels.")


# ---------------------------------------------------------------- parsing

def parse_iso(s) -> datetime | None:
    if not s or not isinstance(s, (str, datetime)):
        return None
    if isinstance(s, datetime):
        dt = s
    else:
        try:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def et_clock(s, now: datetime | None = None) -> str:
    """'4:00 PM ET' today, 'Fri 1:00 PM ET' on any other day (America/New_York)."""
    dt = parse_iso(s)
    if not dt:
        return ""
    loc = dt.astimezone(ET)
    today = (now or datetime.now(timezone.utc)).astimezone(ET).date()
    clock = loc.strftime("%-I:%M %p") + " ET"
    return clock if loc.date() == today else loc.strftime("%a ") + clock


def parse_vtec(strings) -> list[dict]:
    out = []
    for s in strings or []:
        m = _VTEC_RE.match(str(s).strip()) if isinstance(s, str) else None
        if not m:
            continue
        _cls, action, office, phen, sig, etn = m.groups()[:6]
        out.append({"action": action, "office": office, "phen": phen, "sig": sig, "etn": etn,
                    "key": "%s.%s.%s.%s" % (office, phen, sig, etn)})
    return out


def record(feature) -> dict | None:
    """One validated NWS alert record, or None when the record cannot be trusted."""
    if not isinstance(feature, dict):
        return None
    p = feature.get("properties") if isinstance(feature.get("properties"), dict) else None
    if p is None and isinstance(feature.get("id"), str) and "event" in feature:
        p = feature   # an /alerts/{id} body already unwrapped
    if not isinstance(p, dict):
        return None
    aid = p.get("id") or feature.get("id")
    event = p.get("event")
    geo = p.get("geocode") if isinstance(p.get("geocode"), dict) else {}
    ugc = geo.get("UGC")
    if not isinstance(aid, str) or not aid or not isinstance(event, str) or not event.strip():
        return None
    if not isinstance(ugc, list) or not ugc or not all(isinstance(z, str) and _UGC_RE.match(z) for z in ugc):
        return None
    for k in ("sent", "effective", "onset", "ends", "expires"):
        v = p.get(k)
        if v is not None and parse_iso(v) is None:
            return None
    if parse_iso(p.get("sent")) is None:
        return None
    params = p.get("parameters") if isinstance(p.get("parameters"), dict) else {}
    vtec_raw = params.get("VTEC") or []
    if not isinstance(vtec_raw, list):
        return None
    vtec = parse_vtec(vtec_raw)
    if vtec_raw and not vtec:
        return None   # VTEC present but unreadable
    refs = []
    for r in p.get("references") or []:
        if isinstance(r, dict) and isinstance(r.get("identifier"), str):
            refs.append(r["identifier"])
    area_parts = [a.strip().rstrip(".") for a in (p.get("areaDesc") or "").split(";") if a.strip()]
    names = {z: area_parts[i] for i, z in enumerate(ugc)} if len(area_parts) == len(ugc) else {}
    rb = p.get("replacedBy")
    return {
        "id": aid, "event": event.strip(), "status": p.get("status") or "Actual",
        "messageType": p.get("messageType") or "", "sent": p.get("sent"),
        "onset": p.get("onset"), "effective": p.get("effective"),
        "ends": p.get("ends"), "expires": p.get("expires"),
        "ugc": list(ugc), "names": names, "areaDesc": p.get("areaDesc") or "",
        "vtec": vtec, "keys": sorted({v["key"] for v in vtec}), "refs": refs,
        "replacedBy": rb.rsplit("/", 1)[-1] if isinstance(rb, str) and rb else None,
        "replacedAt": p.get("replacedAt"), "sender": p.get("senderName") or "",
        "severity": p.get("severity") or "", "headline": p.get("headline") or "",
        "textReplaced": bool(_REPLACED_RE.search(p.get("headline") or "") or _REPLACED_RE.search(p.get("description") or "")),
    }


def start_of(r: dict):
    """Official start time: onset, else effective."""
    return r.get("onset") or r.get("effective")


def is_terminal(r: dict) -> bool:
    """A cancellation or expiration message (it ends the event; it is not a hazard in effect)."""
    if r.get("messageType") == "Cancel":
        return True
    acts = [v["action"] for v in r.get("vtec") or []]
    return bool(acts) and all(a in TERMINAL_ACTIONS for a in acts)


def phase(r: dict, now: datetime) -> str:
    """'upcoming' (issued, not yet effective), 'in_effect', or 'ended' (official end has passed).

    A missing end time never ends a record that is still in the active feed."""
    st, en = parse_iso(start_of(r)), parse_iso(r.get("ends"))
    if en is not None and en <= now:
        return "ended"
    if st is not None and st > now:
        return "upcoming"
    return "in_effect"


# ---------------------------------------------------------------- current feed

def read_feed(body, zones=None) -> dict:
    """Validate an /alerts/active body. trusted=False when the body, or any record in it, is unreadable."""
    if not isinstance(body, dict) or not isinstance(body.get("features"), list):
        return {"ok": False, "trusted": False, "records": [], "bad": 0}
    recs, bad, seen = [], 0, set()
    for f in body["features"]:
        r = record(f)
        if r is None:
            bad += 1
            continue
        if r["status"] != "Actual" or r["id"] in seen:
            continue
        seen.add(r["id"])
        recs.append(r)
    if zones:
        zs = set(zones)
        recs = [r for r in recs if zs & set(r["ugc"])]
    return {"ok": True, "trusted": bad == 0, "records": recs, "bad": bad}


def current_records(feed: dict, now: datetime) -> list[dict]:
    """Records in effect or upcoming. Cancellations/expirations are evidence, not hazards. A record
    NWS marks replaced is skipped only when its replacement is in the same feed (never hidden)."""
    recs = feed.get("records") or []
    ids = {r["id"] for r in recs}
    out = []
    for r in recs:
        if is_terminal(r):
            continue
        if (r.get("replacedBy") and r["replacedBy"] in ids) or (r.get("textReplaced") and not r.get("keys")):
            continue
        if phase(r, now) == "ended":
            continue
        out.append(r)
    return out


def dedupe(recs: list[dict], zones=None) -> list[dict]:
    """One row per official event: same VTEC event (or same alert id when no VTEC), same start and
    end. Rows list the union of zones; local = in-region zones with NWS names. Never drops a row."""
    zs = list(zones or [])
    rows, by = [], {}
    for r in sorted(recs, key=lambda x: parse_iso(x.get("sent")) or datetime.min.replace(tzinfo=timezone.utc)):
        ident = tuple(r["keys"]) or ("id", r["id"])
        k = (r["event"], ident, start_of(r) or "", r.get("ends") or "")
        row = by.get(k)
        if row is None:
            row = by[k] = {"event": r["event"], "keys": list(r["keys"]), "ids": [], "start": start_of(r),
                           "ends": r.get("ends"), "expires": r.get("expires"), "ugc": [], "names": {},
                           "sent": r.get("sent"), "sender": r.get("sender"), "severity": r.get("severity"),
                           "headline": r.get("headline")}
            rows.append(row)
        row["ids"].append(r["id"])
        row["sent"] = r.get("sent")          # latest NWS update for this event
        row["headline"] = r.get("headline") or row["headline"]
        for z in r["ugc"]:
            if z not in row["ugc"]:
                row["ugc"].append(z)
        row["names"].update(r.get("names") or {})
    for row in rows:
        local = [z for z in row["ugc"] if z in zs] if zs else list(row["ugc"])
        row["localUgc"] = local
        row["local"] = [row["names"].get(z) or z for z in local]
    return rows


def label_for(row: dict, now: datetime) -> dict:
    """UPCOMING / IN EFFECT label with official times in ET."""
    ph = phase({"onset": row.get("start"), "ends": row.get("ends")}, now)
    st, en = row.get("start"), row.get("ends")
    if ph == "upcoming":
        when = "starts %s" % et_clock(st, now)
        if en:
            when += " · until %s" % et_clock(en, now)
        return {"phase": "upcoming", "tag": "Upcoming", "when": when,
                "sr": "Upcoming, not yet in effect. Starts %s." % et_clock(st, now)}
    when = ("until %s" % et_clock(en, now)) if en else "no end time given by NWS"
    return {"phase": "in_effect", "tag": "In effect", "when": when, "sr": "In effect now."}


# ---------------------------------------------------------------- issued-list reconciliation

def lookup_chains(ids, fetch, budget_s: float = LOOKUP_BUDGET_S, max_hops: int = MAX_CHAIN) -> dict:
    """Follow each id's replacedBy chain through /alerts/{id}. Returns {id: {"ok", "chain": [records]}}.
    ok=False when any hop fails, is malformed, loops, or runs past max_hops or the time budget."""
    ids = [i for i in dict.fromkeys(ids or []) if isinstance(i, str) and i]
    out = {}

    def one(aid):
        chain, seen, cur = [], set(), aid
        for _ in range(max_hops):
            if cur in seen:
                return {"ok": False, "chain": chain}
            seen.add(cur)
            try:
                body = fetch(ALERTS_BASE + cur)
            except Exception:
                body = None
            r = record(body) if isinstance(body, dict) else None
            if r is None or r["id"] != cur:
                return {"ok": False, "chain": chain}
            chain.append(r)
            if not r.get("replacedBy"):
                return {"ok": True, "chain": chain}
            cur = r["replacedBy"]
        return {"ok": False, "chain": chain}

    if not ids:
        return out
    ex = ThreadPoolExecutor(max_workers=min(6, len(ids)))
    futs = {ex.submit(one, i): i for i in ids}
    done, _pending = wait(futs, timeout=budget_s)
    for f, i in futs.items():
        out[i] = f.result() if f in done else {"ok": False, "chain": []}
    ex.shutdown(wait=False, cancel_futures=True)
    return out


def _ids_of(row: dict) -> list[str]:
    ids = [p.get("id") for p in row.get("products") or [] if isinstance(p, dict) and p.get("id")]
    if row.get("id"):
        ids.append(row["id"])
    return list(dict.fromkeys(ids))


def _zones_of(row: dict, zones) -> list[str]:
    ugc = list(row.get("localUgc") or [])
    if not ugc:
        allz = list(row.get("ugc") or [])
        for p in row.get("products") or []:
            for z in (p or {}).get("ugc") or []:
                if z not in allz:
                    allz.append(z)
        ugc = [z for z in allz if not zones or z in zones] or allz
    return ugc


def reconcile(row: dict, feed: dict, current: list[dict], chains: dict | None, now: datetime, zones=None,
              history: list[dict] | None = None) -> dict:
    """Status now for one row of the issued list.

    states: in_effect, upcoming, updated (same event, new NWS times), upgraded / replaced (NWS linked a
    different product), cancelled, ended, unconfirmed. `detail` is short plain text for the page."""
    if not feed.get("ok"):
        return {"state": "unconfirmed", "tag": "Unconfirmed", "detail": UNCONFIRMED_TEXT + " (current NWS alerts could not be read)."}
    ids = set(_ids_of(row))
    L = set(_zones_of(row, zones))
    chains = chains or {}
    chain_recs, chain_ok = [], bool(ids)
    for i in ids:
        c = chains.get(i)
        if c is None:
            chain_ok = False
            continue
        chain_recs.extend(c.get("chain") or [])
        chain_ok = chain_ok and bool(c.get("ok"))
    chain_ids = ids | {r["id"] for r in chain_recs}
    chain_keys = {k for r in chain_recs for k in r["keys"]}
    upg = any(v["action"] == "UPG" for r in chain_recs for v in r["vtec"])

    matches = []
    for r in current:
        if not (L & set(r["ugc"])) and L:
            continue
        linked = r["id"] in chain_ids or bool(set(r["refs"]) & chain_ids)
        same_event = bool(chain_keys & set(r["keys"]))
        if linked or same_event:
            matches.append(r)
    covered = set()
    for r in matches:
        covered |= (set(r["ugc"]) & L) if L else set(r["ugc"])
    left = L - covered

    def times(r):
        return label_for({"start": start_of(r), "ends": r.get("ends")}, now)

    parts, state = [], None
    if matches:
        latest = max(matches, key=lambda r: parse_iso(r.get("sent")) or now)
        lab = times(latest)
        same = latest["event"] == row.get("event")
        if not same:
            state = "upgraded" if upg else "replaced"
            parts.append("%s by NWS %s: %s %s." % ("Upgraded" if upg else "Replaced", et_clock(latest.get("sent"), now),
                                                 latest["event"], lab["when"]))
        else:
            moved = parse_iso(latest.get("ends")) != parse_iso(row.get("ends"))
            if lab["phase"] == "upcoming":
                state = "upcoming"
            else:
                state = "updated" if moved else "in_effect"
            if latest["id"] not in ids:
                parts.append("NWS update %s: %s %s." % (et_clock(latest.get("sent"), now), lab["tag"].lower(), lab["when"]))
            else:
                parts.append("%s %s." % (lab["tag"], lab["when"]))
    if left or not matches:
        # Zones with no current match: only call them ended/cancelled with official evidence.
        evidence = list(chain_recs)
        for r in list(history or []) + list(feed.get("records") or []):
            if set(r["keys"]) & chain_keys and r not in evidence:
                evidence.append(r)
        scope = left if left else L
        hit = lambda r: (not scope) or bool(set(r["ugc"]) & scope)
        term = [r for r in evidence if is_terminal(r) and hit(r)]
        term_zones = set()
        for r in term:
            term_zones |= set(r["ugc"])
        cancelled = [r for r in term if r.get("messageType") == "Cancel" or any(v["action"] == "CAN" for v in r["vtec"])]
        covering = [r for r in evidence if not is_terminal(r) and hit(r)]
        latest = max(covering, key=lambda r: parse_iso(r.get("sent")) or now) if covering else None
        ends_dt = parse_iso((latest or {}).get("ends") or row.get("ends"))
        all_term = bool(term) and (not scope or scope <= term_zones)
        if not feed.get("trusted"):
            sub = "unconfirmed"
        elif all_term:
            sub = "cancelled" if cancelled else "ended"
        elif chain_ok and ends_dt is not None and ends_dt <= now:
            sub = "ended"
        else:
            sub = "unconfirmed"   # not in the current feed, but nothing official says it ended
        where = (" for %s" % ", ".join(sorted(left))) if (matches and left) else ""
        if sub == "unconfirmed":
            parts.append(UNCONFIRMED_TEXT + where + ".")
        elif sub == "cancelled":
            c = max(cancelled, key=lambda r: parse_iso(r.get("sent")) or now)
            parts.append("Cancelled by NWS %s%s." % (et_clock(c.get("sent"), now), where))
        elif all_term:
            t = max(term, key=lambda r: parse_iso(r.get("sent")) or now)
            parts.append("Ended (NWS %s)%s; no current replacement." % (et_clock(t.get("sent"), now), where))
        else:
            parts.append("No longer in effect%s; no current NWS replacement found." % where)
        if state is None:
            state = sub
    tags = {"in_effect": "In effect", "upcoming": "Upcoming", "updated": "Updated", "upgraded": "Upgraded",
            "replaced": "Replaced", "cancelled": "Cancelled", "ended": "Ended", "unconfirmed": "Unconfirmed"}
    return {"state": state, "tag": tags[state], "detail": " ".join(parts),
            "matches": [r["id"] for r in matches]}


def status_now(rows: list[dict], url: str, fetch, now: datetime | None = None, zones=None,
               budget_s: float = LOOKUP_BUDGET_S, history_url: str | None = None) -> dict:
    """Everything the brief's Status now section needs, from one active-feed read plus record lookups."""
    now = now or datetime.now(timezone.utc)
    try:
        body = fetch(url)
    except Exception:
        body = None
    feed = read_feed(body, zones)
    cur = current_records(feed, now) if feed["ok"] else []
    # Rows whose products are all still in the feed (same id) need no lookups.
    cur_ids = {r["id"] for r in cur}
    need = []
    for row in rows or []:
        ids = _ids_of(row)
        if not ids or not all(i in cur_ids for i in ids):
            need.extend(ids)
    chains = lookup_chains(need, fetch, budget_s=budget_s) if (feed["ok"] and need) else {}
    for row in rows or []:
        for i in _ids_of(row):
            if i in cur_ids and i not in chains:
                chains[i] = {"ok": True, "chain": [r for r in cur if r["id"] == i]}
    history = []
    if feed["ok"] and history_url and any(not (c or {}).get("ok") or len((c or {}).get("chain") or []) > 1
                                          or i not in cur_ids for i, c in chains.items()):
        # Positive evidence only (cancellations, expirations, interim updates since issue time).
        # A failed or partial history read never counts as "ended"; it just adds no evidence.
        try:
            hb = fetch(history_url)
        except Exception:
            hb = None
        if isinstance(hb, dict) and isinstance(hb.get("features"), list):
            history = [r for r in (record(f) for f in hb["features"]) if r and r["status"] == "Actual"]
    recon = [reconcile(r, feed, cur, chains, now, zones, history) for r in rows or []]
    current_rows = dedupe(cur, zones)
    for row in current_rows:
        row.update(label=label_for(row, now))
    return {"ok": feed["ok"], "trusted": feed["trusted"], "checkedAt": now.isoformat(), "history": len(history),
            "current": current_rows, "issued": recon, "bad": feed["bad"],
            "coastalFlood": coastal_flood_active(current_rows, now)}


# ---------------------------------------------------------------- coastal flood note

def coastal_flood_active(rows, now: datetime) -> dict | None:
    """The Coastal Flood Warning row (in effect or upcoming) among current rows, else None."""
    for r in rows or []:
        if (r.get("event") or "") == "Coastal Flood Warning":
            ph = phase({"onset": r.get("start") or r.get("onset"), "ends": r.get("ends")}, now)
            if ph != "ended":
                return {"phase": ph, "ends": r.get("ends"), "start": r.get("start") or r.get("onset")}
    return None
