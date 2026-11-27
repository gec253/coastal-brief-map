"""Bundled observed-wind stations for the North Carolina coast and sounds (Phase B2).

One in-memory catalog (data/wind-stations.json) plus GET /api/wind-stations.
Reuses conditions.py fetch helpers, cache hooks, TTLs and freshness windows
read-only. Does not modify conditions.py, does not call resolve_reading (so
the Hatteras / regional backup is never applied), and never fills a station
from GFS or another station.

Freshness (from conditions.py, not a new scale):
  TTL_OBS = 6 min (CO-OPS and NWS upstream cache)
  TTL_NDBC = 8 min (NDBC upstream cache)
  ASSEMBLED_TTL = 90 s (in-memory bundle)
  STALE_MIN['wind'] = 75 min; STALE_MIN['harborWind'] = 45 min
  staleAfterMin on a station may only lengthen the window (e.g. 41064 = 130)
  MAX_AGE_H = 12 hours — older than that is unavailable, not stale
  Status: fresh / stale / unavailable / gust_only (speed null, gust present;
  never copy gust into speed).

Standard library only. Bounded concurrency and a 3.5 s overall budget so a
slow NOAA feed cannot stall /wind or /api/wind-grid.
"""
from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import conditions

ROOT = Path(__file__).resolve().parent
CATALOG_PATH = ROOT / "data" / "wind-stations.json"
NDBC_BULK_URL = "https://www.ndbc.noaa.gov/data/latest_obs/latest_obs.txt"
UA = "TheCoastalBrief/1.0 (+https://thecoastalbrief.com; coastal conditions site)"

BUDGET_S = 3.5
SOURCE_TIMEOUT_S = 2.0
MAX_WORKERS = 6
HTTP_CACHE_S = conditions.ASSEMBLED_TTL  # 90 s, aligned with the assembled bundle

_SOURCE = {
    "ndbc": "NOAA NDBC",
    "coops": "NOAA NOS CO-OPS",
    "nws": "NWS ASOS/AWOS",
}

_POOL = ThreadPoolExecutor(max_workers=MAX_WORKERS, thread_name_prefix="wind-st")
_LOCK = threading.Lock()
_ASSEMBLED: tuple[float, dict] | None = None
_LAST_GOOD: tuple[float, dict] | None = None
_CATALOG: dict | None = None

# Tests may replace this with a fixture fetcher: (url) -> (status, body) | None.
_fetch_override = None


def load_catalog() -> dict:
    global _CATALOG
    if _CATALOG is None:
        _CATALOG = json.loads(CATALOG_PATH.read_text())
    return _CATALOG


def catalog_stations() -> list[dict]:
    return list(load_catalog()["stations"])


def dropped_ids() -> set[str]:
    out: set[str] = set()
    for row in load_catalog().get("deduped") or []:
        dropped = row.get("dropped")
        if isinstance(dropped, str):
            out.add(dropped)
        elif isinstance(dropped, list):
            out.update(dropped)
    out.update(load_catalog().get("excluded") or [])
    return out


def reset_cache() -> None:
    """Test helper: drop in-memory assembled / last-good snapshots."""
    global _ASSEMBLED, _LAST_GOOD
    with _LOCK:
        _ASSEMBLED = None
        _LAST_GOOD = None


# ---------- short-timeout fetch (does not use the 45 s saltwater default) ----------

def _hook(name: str):
    fn = (conditions._hooks or {}).get(name)
    return fn if callable(fn) else None


def _fetch_url(url: str, timeout: float = SOURCE_TIMEOUT_S) -> tuple[int, bytes]:
    if _fetch_override is not None:
        got = _fetch_override(url)
        if got is None:
            return 502, b""
        return int(got[0]), got[1] if isinstance(got[1], bytes) else got[1].encode()
    headers = {"User-Agent": UA, "Accept": "application/json, text/plain, */*"}
    try:
        req = Request(url, headers=headers)
        with urlopen(req, timeout=timeout) as resp:
            return int(getattr(resp, "status", 200) or 200), resp.read()
    except HTTPError as e:
        try:
            body = e.read() or b""
        except Exception:
            body = b""
        return int(e.code), body
    except (URLError, TimeoutError, OSError):
        return 502, b""


def _get(url: str, ttl: int) -> bytes | None:
    """Cached GET with a short timeout. Failures are not stored as fresh.
    An expired last-good body may be returned so observation times stay honest.

    When a test supplies `_fetch_override`, skip the shared disk cache so
    fixtures are the only source.
    """
    if _fetch_override is None:
        cache_get = _hook("cache_get")
        if cache_get:
            hit = cache_get(url)
            if hit and hit[0] == 200 and hit[2]:
                return hit[2]
    status, body = _fetch_url(url)
    if status == 200 and body:
        if _fetch_override is None:
            put = _hook("cache_put_ttl")
            if put:
                try:
                    put(url, ttl, body)
                except Exception:
                    pass
        return body
    if _fetch_override is None:
        cache_any = _hook("cache_get_any")
        if cache_any:
            old = cache_any(url)
            if old and old[0] == 200 and old[2]:
                return old[2]
    return None


# ---------- parsers ----------

def parse_ndbc_bulk(text: str) -> dict[str, dict]:
    """Parse NDBC latest_obs.txt (WSPD/GST in m/s) into per-station English-unit dicts."""
    out: dict[str, dict] = {}
    if not text:
        return out
    head = None
    for ln in text.splitlines():
        if not ln.strip():
            continue
        if ln.startswith("#"):
            cols = ln.lstrip("#").split()
            if "STN" in cols or (cols and cols[0] in ("STN", "YY", "YYYY")):
                # Prefer the line that names STN + WSPD.
                if "WSPD" in cols or "STN" in cols:
                    head = cols
            continue
        if not head:
            continue
        parts = ln.split()
        if len(parts) < 8:
            continue
        rec = {head[i]: parts[i] for i in range(min(len(head), len(parts)))}
        sid = (rec.get("STN") or rec.get("STATION") or parts[0] or "").upper()
        if not sid:
            continue
        try:
            year = int(rec.get("YYYY") or rec.get("YY") or rec.get("YEAR"))
            if year < 100:
                year += 2000
            mo = int(rec.get("MM") or rec.get("MO") or rec.get("MONTH"))
            dy = int(rec.get("DD") or rec.get("DY") or rec.get("DAY"))
            hh = int(rec.get("hh") or rec.get("HH") or rec.get("HR") or 0)
            mn = int(rec.get("mm") or rec.get("MI") or rec.get("MN") or 0)
            dt = datetime(year, mo, dy, hh, mn, tzinfo=timezone.utc)
        except (TypeError, ValueError, KeyError):
            continue

        def msv(key):
            raw = rec.get(key)
            if raw is None or raw in ("MM", "N/A", "n/a", "--"):
                return None
            try:
                return float(raw)
            except ValueError:
                return None

        wspd_ms, gst_ms, wdir = msv("WSPD"), msv("GST"), msv("WDIR")
        parsed = {"_dt": dt, "url": NDBC_BULK_URL}
        if wdir is not None:
            parsed["WDIR"] = wdir
        if wspd_ms is not None:
            parsed["WSPD_kt"] = wspd_ms * conditions.MS_TO_KT
        if gst_ms is not None:
            parsed["GST_kt"] = gst_ms * conditions.MS_TO_KT
        out[sid] = parsed
    return out


def _nws_to_kt(prop: dict | None) -> float | None:
    if not prop or prop.get("value") is None:
        return None
    try:
        val = float(prop["value"])
    except (TypeError, ValueError):
        return None
    unit = (prop.get("unitCode") or prop.get("uom") or "").replace("unit:", "").lower()
    if unit in ("kt", "kn", "knot", "knots"):
        return val
    if "m_s" in unit or unit in ("m/s", "mps"):
        return val * conditions.MS_TO_KT
    if "mi_h" in unit or unit in ("mph", "mi/h"):
        return val * conditions.MPH_TO_KT
    # NWS default is km/h.
    return val * 0.539957


def parse_nws_obs(body: bytes, url: str) -> dict | None:
    try:
        p = json.loads(body.decode("utf-8")).get("properties") or {}
    except (UnicodeDecodeError, json.JSONDecodeError, AttributeError):
        return None
    t = p.get("timestamp")
    if not t:
        return None
    try:
        dt = datetime.fromisoformat(str(t).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    speed = _nws_to_kt(p.get("windSpeed"))
    gust = _nws_to_kt(p.get("windGust"))
    direc = None
    wd = p.get("windDirection") or {}
    if wd.get("value") is not None:
        try:
            direc = float(wd["value"])
        except (TypeError, ValueError):
            direc = None
    return {"_dt": dt, "WSPD_kt": speed, "GST_kt": gust, "WDIR": direc, "url": url}


def parse_coops_wind(body: bytes, url: str) -> dict | None:
    try:
        data = json.loads(body.decode("utf-8")).get("data") or []
    except (UnicodeDecodeError, json.JSONDecodeError, AttributeError):
        return None
    if not data:
        return None
    row = data[-1]
    dt = conditions.coops_time(row.get("t"))
    if not dt:
        return None
    s, g, d = conditions.fnum(row.get("s")), conditions.fnum(row.get("g")), conditions.fnum(row.get("d"))
    return {"_dt": dt, "WSPD_kt": s, "GST_kt": g, "WDIR": d, "url": url}


# ---------- status ----------

def classify(parsed: dict | None, stale_min: int, now: datetime) -> tuple[str, dict]:
    """Return (status, wind-dict). wind values are omitted when unavailable."""
    empty = {"speedKt": None, "gustKt": None, "dirDeg": None, "dirCompass": None}
    if not parsed or not parsed.get("_dt"):
        return "unavailable", empty
    dt = parsed["_dt"]
    age_min = (now - dt).total_seconds() / 60.0
    speed, gust, direc = parsed.get("WSPD_kt"), parsed.get("GST_kt"), parsed.get("WDIR")
    wind = {
        "speedKt": conditions.r1(speed) if speed is not None else None,
        "gustKt": conditions.r1(gust) if gust is not None else None,
        "dirDeg": direc,
        "dirCompass": conditions.compass(direc) if direc is not None else None,
    }
    if age_min > conditions.MAX_AGE_H * 60:
        # Too old to show as current; drop the numbers.
        return "unavailable", empty
    if wind["speedKt"] is None and wind["gustKt"] is not None:
        return "gust_only", wind
    if wind["speedKt"] is None:
        return "unavailable", empty
    if age_min <= stale_min:
        return "fresh", wind
    return "stale", wind


def _stale_min(meta: dict) -> int:
    kind = meta.get("kindWind") or "wind"
    sid = meta.get("id")
    # stale_after_min reads staleAfterMin off a stations dict; pass a one-key map.
    return conditions.stale_after_min(kind, sid, {sid: meta})


def _station_row(meta: dict, parsed: dict | None, now: datetime, from_cache: bool = False) -> dict:
    status, wind = classify(parsed, _stale_min(meta), now)
    dt = (parsed or {}).get("_dt")
    typ = meta["type"]
    row = {
        "id": meta["id"],
        "name": meta["name"],
        "type": typ,
        "kind": "observed",
        "lat": meta["lat"],
        "lon": meta["lon"],
        "status": status,
        "observedAt": conditions.iso(dt) if dt else None,
        "source": _SOURCE[typ],
        "sourceUrl": (parsed or {}).get("url") or meta.get("url"),
        "wind": wind,
        "ageMin": round((now - dt).total_seconds() / 60.0, 1) if dt else None,
        "staleAfterMin": _stale_min(meta),
    }
    if meta.get("optional"):
        row["optional"] = True
    if from_cache:
        row["fromCache"] = True
    return row


# ---------- assemble ----------

def _ndbc_ids(catalog: list[dict]) -> list[str]:
    return [s["id"] for s in catalog if s["type"] == "ndbc"]


def _fetch_ndbc(catalog: list[dict]) -> dict[str, dict]:
    found: dict[str, dict] = {}
    body = _get(NDBC_BULK_URL, conditions.TTL_NDBC)
    if body:
        try:
            found.update(parse_ndbc_bulk(body.decode("utf-8", "replace")))
        except Exception:
            found = {}
    wanted = set(_ndbc_ids(catalog))
    missing = [sid for sid in wanted if sid not in found or not found[sid].get("_dt")]
    for sid in missing:
        url = "https://www.ndbc.noaa.gov/data/latest_obs/%s.txt" % sid.lower()
        raw = _get(url, conditions.TTL_NDBC)
        if not raw:
            continue
        try:
            parsed = conditions.parse_ndbc_latest_obs(raw.decode("utf-8", "replace"))
        except Exception:
            parsed = None
        if parsed:
            parsed["url"] = url
            found[sid] = parsed
    return {sid: found[sid] for sid in wanted if sid in found}


def _fetch_one_coops(sid: str) -> tuple[str, dict | None]:
    url = conditions.coops_url(sid, "wind", "date=latest")
    raw = _get(url, conditions.TTL_OBS)
    return sid, parse_coops_wind(raw, url) if raw else None


def _fetch_one_nws(sid: str) -> tuple[str, dict | None]:
    url = "https://api.weather.gov/stations/%s/observations/latest" % sid
    raw = _get(url, conditions.TTL_OBS)
    return sid, parse_nws_obs(raw, url) if raw else None


def assemble(now: datetime | None = None, catalog: list[dict] | None = None,
             fetch=None, budget_s: float = BUDGET_S) -> dict:
    """Build the observed-stations bundle. Safe to call from the request thread.

    `fetch`, if set, is a test hook (url) -> (status, body). `budget_s` caps
    how long this call waits on upstreams; last-good rows fill the rest.
    """
    global _ASSEMBLED, _LAST_GOOD, _fetch_override
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    stations_meta = catalog if catalog is not None else catalog_stations()

    with _LOCK:
        hit = _ASSEMBLED
        if hit and (time.time() - hit[0]) < conditions.ASSEMBLED_TTL and fetch is None:
            # Recompute ages/status from stored observation times so labels stay honest.
            return _refresh_ages(hit[1], now)

    prev_override = _fetch_override
    if fetch is not None:
        _fetch_override = fetch
    t0 = time.time()
    try:
        parsed_map: dict[str, dict] = {}
        # NDBC bulk first (one GET covers every buoy / C-MAN in the catalog).
        # Then CO-OPS + NWS in the remaining budget, concurrently.
        try:
            parsed_map.update(_fetch_ndbc(stations_meta))
        except Exception:
            pass
        remaining = max(0.05, budget_s - (time.time() - t0))
        jobs = []
        for meta in stations_meta:
            if meta["type"] == "coops":
                jobs.append(_POOL.submit(_fetch_one_coops, meta["id"]))
            elif meta["type"] == "nws":
                jobs.append(_POOL.submit(_fetch_one_nws, meta["id"]))
        done, not_done = wait(jobs, timeout=remaining)
        for fut in done:
            try:
                sid, parsed = fut.result()
                if parsed:
                    parsed_map[sid] = parsed
            except Exception:
                continue
        # Leave not_done futures running so a late 200 can fill the disk cache
        # for the next visitor; do not wait on them.
    finally:
        _fetch_override = prev_override
    elapsed_ms = int((time.time() - t0) * 1000)

    last_rows = {}
    with _LOCK:
        if _LAST_GOOD:
            last_rows = {s["id"]: s for s in (_LAST_GOOD[1].get("stations") or [])}

    rows = []
    used_cache = False
    got_live = False
    for meta in stations_meta:
        parsed = parsed_map.get(meta["id"])
        if parsed:
            rows.append(_station_row(meta, parsed, now, from_cache=False))
            got_live = True
            continue
        prev = last_rows.get(meta["id"])
        if prev and prev.get("observedAt"):
            # Re-hydrate a last-good observation and reclassify against `now`.
            try:
                dt = datetime.fromisoformat(prev["observedAt"].replace("Z", "+00:00"))
            except ValueError:
                dt = None
            wind = prev.get("wind") or {}
            revived = {"_dt": dt, "url": prev.get("sourceUrl")} if dt else None
            if revived and wind:
                revived["WSPD_kt"] = wind.get("speedKt")
                revived["GST_kt"] = wind.get("gustKt")
                revived["WDIR"] = wind.get("dirDeg")
            rows.append(_station_row(meta, revived, now, from_cache=True))
            used_cache = True
        else:
            rows.append(_station_row(meta, None, now, from_cache=False))

    usable = [r for r in rows if r["status"] in ("fresh", "stale", "gust_only")]
    if not usable:
        # Nothing current enough to show. Prefer last-good bundle with a flag
        # over inventing values. If there is no last-good, the feed is down.
        with _LOCK:
            if _LAST_GOOD:
                payload = _refresh_ages(_LAST_GOOD[1], now)
                payload = dict(payload)
                payload["staleCache"] = True
                payload["elapsedMs"] = elapsed_ms
                payload["generatedAt"] = conditions.iso(now)
                return payload
        return {
            "ok": False,
            "kind": "observed",
            "error": "Observed stations unavailable right now.",
            "generatedAt": conditions.iso(now),
            "staleCache": False,
            "elapsedMs": elapsed_ms,
            "stations": rows,
        }

    payload = {
        "ok": True,
        "kind": "observed",
        "source": "NOAA NDBC, NOS CO-OPS, and NWS station observations",
        "generatedAt": conditions.iso(now),
        "staleCache": bool(used_cache and not got_live),
        "elapsedMs": elapsed_ms,
        "stations": rows,
    }
    with _LOCK:
        _ASSEMBLED = (time.time(), payload)
        if got_live or not _LAST_GOOD:
            _LAST_GOOD = (time.time(), payload)
    return payload


def _refresh_ages(payload: dict, now: datetime) -> dict:
    """Recompute ageMin/status from stored observation times without refetching."""
    by_id = {s["id"]: s for s in catalog_stations()}
    rows = []
    for old in payload.get("stations") or []:
        meta = by_id.get(old["id"])
        if not meta:
            continue
        dt = None
        if old.get("observedAt"):
            try:
                dt = datetime.fromisoformat(old["observedAt"].replace("Z", "+00:00"))
            except ValueError:
                dt = None
        wind = old.get("wind") or {}
        parsed = {"_dt": dt, "url": old.get("sourceUrl")} if dt else None
        if parsed:
            parsed["WSPD_kt"] = wind.get("speedKt")
            parsed["GST_kt"] = wind.get("gustKt")
            parsed["WDIR"] = wind.get("dirDeg")
        rows.append(_station_row(meta, parsed, now, from_cache=old.get("fromCache", False)))
    out = dict(payload)
    out["stations"] = rows
    out["generatedAt"] = conditions.iso(now)
    return out
