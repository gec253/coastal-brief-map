"""Morning Brief "Status now": one overall visitor-facing time budget (Ed t491u, Nov 26, 2026).

brief.status_now_for() makes up to three kinds of NWS reads (active alerts, replacedBy lookups,
history). Each has its own timeout, so a hanging NWS could hold a brief page for ~26 s. Here the
whole check runs on a small bounded worker pool and the visitor waits at most BUDGET_S:

- finished in time            -> that verified result (checked just now)
- still running, but a verified result for the same brief is younger than FRESH_S
                               -> that result, shown with its own "checked" time
- otherwise                   -> "Status unconfirmed — check NWS" (no network, nothing old shown)

The check keeps running in the background (single-flight: at most one per brief, at most
MAX_INFLIGHT briefs at once, MAX_WORKERS threads, no queue beyond that) and stores its verified
result, so the next visitor gets it. Official-alert validation is unchanged: this module only
decides how long to wait and which complete result to show.
"""
from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout

BUDGET_S = 3.5          # total visitor-facing wait for all Status now NWS work on one page view
FRESH_S = 120.0         # same freshness window as server.ALERT_STATUS_TTL
MAX_WORKERS = 3         # background threads for status checks
MAX_INFLIGHT = 6        # distinct briefs being checked at once; more than this -> unconfirmed now

_POOL = ThreadPoolExecutor(max_workers=MAX_WORKERS, thread_name_prefix="brief-status")
_LOCK = threading.RLock()  # re-entrant: a done-callback may run inside status_now()
_INFLIGHT: dict = {}    # key -> (Future, monotonic start)
_VERIFIED: dict = {}    # key -> (monotonic time stored, result)


def _key(b: dict, status_now_for=None) -> tuple:
    # One entry per published brief (region + issue time) and checker; production has one checker.
    rid = b.get("regionId") or (b.get("region") or {}).get("id") or ""
    return (rid, b.get("issuedAt") or b.get("generatedAt") or "", id(status_now_for))


def _unconfirmed(b: dict, status_now_for) -> dict | None:
    # Same function with a fetch that never answers: every issued item reads "unconfirmed",
    # the Status now section says "Status unconfirmed — check NWS". No network, instant.
    try:
        return status_now_for(b, lambda url: None)
    except Exception:
        import brief
        from datetime import datetime, timezone
        return {"ok": False, "trusted": False, "checkedAt": datetime.now(timezone.utc).isoformat(), "current": [],
                "issued": [{"state": "unconfirmed", "tag": "Unconfirmed", "detail": "Status unconfirmed — check NWS."}
                           for _ in brief._issued_rows(b)], "coastalFlood": None}


def _done(key, fut) -> None:
    try:
        res = fut.result()
    except Exception:
        res = None
    with _LOCK:
        if (_INFLIGHT.get(key) or (None,))[0] is fut:
            del _INFLIGHT[key]
        if isinstance(res, dict) and res.get("ok"):
            _VERIFIED[key] = (time.monotonic(), res)


def _fresh(key):
    hit = _VERIFIED.get(key)
    if hit and time.monotonic() - hit[0] < FRESH_S:
        return hit[1]
    return None


def status_now(b: dict, fetch, status_now_for, budget_s: float = BUDGET_S) -> dict | None:
    """Status now for one brief page view, never waiting longer than budget_s."""
    key = _key(b, status_now_for)
    with _LOCK:
        cached = _fresh(key)
        if cached is not None:
            return cached
        fut, started = _INFLIGHT.get(key) or (None, None)
        if fut is None and len(_INFLIGHT) < MAX_INFLIGHT:
            started = time.monotonic()
            fut = _POOL.submit(status_now_for, b, fetch)
            _INFLIGHT[key] = (fut, started)
            fut.add_done_callback(lambda f, k=key: _done(k, f))
    if fut is not None:
        # Wait only what is left of this check's budget: during an outage the first visitor waits
        # the budget, later visitors to the same still-running check are not held again.
        wait = budget_s - (time.monotonic() - started)
        try:
            if wait > 0 or fut.done():
                return fut.result(timeout=max(wait, 0))
        except (FutureTimeout, Exception):
            pass
    with _LOCK:
        cached = _fresh(key)
    if cached is not None:
        return cached
    return _unconfirmed(b, status_now_for)


def _reset_for_tests() -> None:
    with _LOCK:
        _INFLIGHT.clear()
        _VERIFIED.clear()
