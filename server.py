#!/usr/bin/env python3
"""Minimal deploy-ready proxy + cache for the Coastal Brief map.

Serves the static test page and forwards requests only to a short allowlist
of NOAA/NWS hosts. Caches tiles and JSON on disk. Reads live NWS alerts and
writes data/ads.json using the site's ad-pause rule.

No third-party packages. Python 3.11+ standard library only.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import html
import json
import os
import posixpath
import re
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse, quote_plus, unquote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
CACHE_DIR = ROOT / "cache"
ADS_PATH = ROOT / "data" / "ads.json"
TIDE_STATIONS_PATH = ROOT / "data" / "tide-stations.json"
NOMINATIM = "https://nominatim.openstreetmap.org"
TIDE_APP = "CoastalBriefMapTest"
# Predictions change slowly; cache longer than live observations.
TIDE_PRED_TTL = 6 * 60 * 60
GEOCODE_TTL = 7 * 24 * 60 * 60
GEO_LOCK = threading.Lock()
_GEO_LAST = 0.0
UA = "TheCoastalBrief/1.0 (+https://thecoastalbrief.com; coastal conditions site)"

# Only these origins may be proxied (SSRF guard). Keys are URL prefixes.
PROXIES = {
    "ndfd": "https://digital.weather.gov",
    "sst": "https://coastwatch.pfeg.noaa.gov",
    "sstfb": "https://coastwatch.noaa.gov",
    "enc": "https://gis.charttools.noaa.gov",
    "ndbc": "https://www.ndbc.noaa.gov",
    "nws": "https://api.weather.gov",
    "tides": "https://api.tidesandcurrents.noaa.gov",
}

# Cache lifetime in seconds. Forecast tiles change often; charts do not.
TTL = {
    "ndfd": 15 * 60,
    "sst": 60 * 60,
    "sstfb": 60 * 60,
    "enc": 24 * 60 * 60,
    "ndbc": 10 * 60,
    "nws": 5 * 60,
    "tides": 15 * 60,
    "tides_pred": 6 * 60 * 60,
    "geocode": 7 * 24 * 60 * 60,
    "radar_json": 3 * 60,
    "radar_tile": 50 * 60,   # WeatherAPI terms: current conditions max 60 min (50 min here + 10 min browser)
    "default": 10 * 60,
}

HOP_BY_HOP = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade",
}

# Official NWS marine zones for MHX (Newport/Morehead City) and ILM
# (Wilmington). Names were read from api.weather.gov/zones/forecast/{id}
# and office responsibleForecastZones on 10 Nov 2026. Purely South Carolina
# ILM waters (AMZ254, AMZ256, AMZ284) are left out on purpose.
REGIONS = {
    "north": {
        "label": "Outer Banks and northern sounds",
        "zones": [
            "AMZ150", "AMZ152", "AMZ154", "AMZ180", "AMZ182", "AMZ184",
            "AMZ131", "AMZ135", "AMZ230", "AMZ231",
        ],
    },
    "central": {
        "label": "Crystal Coast and central waters",
        "zones": [
            "AMZ156", "AMZ158", "AMZ186", "AMZ188", "AMZ136", "AMZ137",
        ],
    },
    "south": {
        "label": "Cape Fear and southern waters",
        "zones": ["AMZ250", "AMZ252", "AMZ280"],
    },
}

ALL_MARINE_ZONES = {z for meta in REGIONS.values() for z in meta["zones"]}

# Hard pause: gale warning or anything stronger, or a tropical storm /
# hurricane warning. Watches do not hard-pause. Small Craft Advisory is soft.
HARD_PAUSE_EVENTS = {
    "gale warning",
    "storm warning",
    "hurricane force wind warning",
    "hurricane-force wind warning",
    "tropical storm warning",
    "hurricane warning",
    "extreme wind warning",
}
SOFT_EVENTS = {
    "small craft advisory",
    "small craft advisory for winds",
    "small craft advisory for hazardous seas",
    "small craft advisory for rough bar",
}

RESUME_AFTER = timedelta(hours=12)
ADS_LOCK = threading.Lock()
CACHE_LOCK = threading.Lock()
MAX_CACHE_BYTES = 400 * 1024 * 1024


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def safe_join(base: str, rest: str) -> str | None:
    """Join a path onto an allowlisted origin; reject scheme/host tricks."""
    rest = rest.lstrip("/")
    if ".." in rest.split("/"):
        return None
    if rest.startswith("http:") or rest.startswith("https:"):
        return None
    joined = base.rstrip("/") + ("/" + rest if rest else "")
    parsed = urlparse(joined)
    allowed = urlparse(base)
    if parsed.scheme != allowed.scheme or parsed.netloc != allowed.netloc:
        return None
    posixpath.normpath(parsed.path or "/")
    return joined


def cache_paths(url: str) -> tuple[Path, Path]:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
    folder = CACHE_DIR / digest[:2]
    return folder / digest, folder / (digest + ".meta.json")


def cache_get(url: str) -> tuple[int, str, bytes] | None:
    body_path, meta_path = cache_paths(url)
    if not body_path.is_file() or not meta_path.is_file():
        return None
    try:
        meta = json.loads(meta_path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    if time.time() > float(meta.get("expires", 0)):
        return None
    try:
        return int(meta.get("status", 200)), str(meta.get("ctype", "application/octet-stream")), body_path.read_bytes()
    except OSError:
        return None


def cache_put(url: str, key: str, status: int, ctype: str, body: bytes) -> None:
    if status != 200 or not body:
        return
    ttl = TTL.get(key, TTL["default"])
    body_path, meta_path = cache_paths(url)
    try:
        body_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = body_path.with_suffix(".tmp")
        tmp.write_bytes(body)
        tmp.replace(body_path)
        meta_path.write_text(json.dumps({
            "url": url,
            "status": status,
            "ctype": ctype,
            "expires": time.time() + ttl,
            "stored": time.time(),
            "bytes": len(body),
        }))
    except OSError:
        return
    _prune_cache()


IMAGE_PROXIES = {"ndfd", "sst", "sstfb", "enc"}


def _looks_like_image_request(url: str) -> bool:
    low = url.lower()
    return low.split("?")[0].endswith((".png", ".jpg", ".jpeg")) or "format=image" in low or "request=getmap" in low


def _is_image(ctype: str, body: bytes) -> bool:
    if not body:
        return False
    if body[:8] == b"\x89PNG\r\n\x1a\n" or body[:3] == b"\xff\xd8\xff" or body[:4] == b"GIF8":
        return True
    return False


def cache_get_any(url: str) -> tuple[int, str, bytes] | None:
    """Last cached copy even if expired. Used only as an outage fallback."""
    body_path, meta_path = cache_paths(url)
    try:
        meta = json.loads(meta_path.read_text())
        return int(meta.get("status", 200)), str(meta.get("ctype", "application/octet-stream")), body_path.read_bytes()
    except (OSError, json.JSONDecodeError, ValueError):
        return None


def cache_entry(url: str) -> dict | None:
    """Cached body plus stored/expires times, even if the TTL has passed. None if missing."""
    body_path, meta_path = cache_paths(url)
    try:
        meta = json.loads(meta_path.read_text())
        body = body_path.read_bytes()
        stored = float(meta.get("stored") or 0)
        expires = float(meta.get("expires") or 0)
        status = int(meta.get("status", 200))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return None
    if not body:
        return None
    return {
        "status": status,
        "ctype": str(meta.get("ctype", "application/octet-stream")),
        "body": body,
        "stored": stored,
        "expires": expires,
        "age": (time.time() - stored) if stored else None,
    }


# Only public site assets are served from the repo folder; source, config,
# docs, and test fixtures are not.
_STATIC_EXT = {".html", ".css", ".js", ".svg", ".png", ".jpg", ".jpeg", ".webp", ".avif", ".ico",
               ".woff2", ".json", ".txt", ".xml", ".webmanifest", ".map"}
_STATIC_DENY_PREFIX = ("/.", "/admin", "/preview/", "/branding/og-masthead.html", "/branding/render-og-masthead.", "/wind-lab.", "/wind.", "/wind-viewer.", "/wind-coast", "/radar.", "/radar-", "/showcase.", "/lake.", "/tiles-lab.", "/docs/", "/tests/", "/scripts/", "/__pycache__/", "/requirements")


def _static_allowed(path: str) -> bool:
    p = posixpath.normpath(unquote(path or "/"))
    if path.endswith("/") and not p.endswith("/"):
        p += "/"
    if p in ("/", "/index.html"):
        return True
    if any(p.startswith(d) for d in _STATIC_DENY_PREFIX) or "/." in p:
        return False
    return posixpath.splitext(p)[1].lower() in _STATIC_EXT


def hmac_compare(a: str, b: str) -> bool:
    import hmac
    return bool(a) and hmac.compare_digest(a.encode(), b.encode())


SST_TIME_DEFAULTS = {"mur": "2026-11-09T09:00:00Z", "blended": "2026-11-08T12:00:00Z"}
_SST_TIME_CACHE: dict = {}


def sst_latest_times() -> dict:
    """Latest analysis time for each SST product, read from ERDDAP griddap.
    Falls back to the last good answer, then to known-good dates."""
    now = time.time()
    hit = _SST_TIME_CACHE.get("v")
    if hit and now - hit[0] < 3600:
        return hit[1]
    out = {"ok": True, "source": "ERDDAP griddap time[last]"}
    for key, url in (
        ("mur", "https://coastwatch.pfeg.noaa.gov/erddap/griddap/jplMURSST41.csv?time%5Blast%5D"),
        ("blended", "https://coastwatch.noaa.gov/erddap/griddap/noaacwBLENDEDsstDNDaily.csv?time%5Blast%5D"),
    ):
        val = None
        try:
            status, _ct, body = fetch_url(url, tries=2)
            if status == 200:
                lines = body.decode("utf-8", "replace").strip().splitlines()
                cand = lines[-1].strip() if lines else ""
                if re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", cand):
                    val = cand
        except Exception:
            val = None
        if not val:
            val = ((hit[1] if hit else {}) or {}).get(key) or SST_TIME_DEFAULTS[key]
            out.setdefault("fallback", []).append(key)
        out[key] = val
    _SST_TIME_CACHE["v"] = (now, out)
    return out


def _recent_image_copy(url: str, max_age_s: int):
    """Last good image stored for this exact URL, if it is recent enough."""
    body_path, meta_path = cache_paths(url)
    try:
        meta = json.loads(meta_path.read_text())
        if time.time() - float(meta.get("stored", 0)) > max_age_s:
            return None
        body = body_path.read_bytes()
        ctype = str(meta.get("ctype", "image/png"))
        return (ctype, body) if _is_image(ctype, body) else None
    except (OSError, json.JSONDecodeError, ValueError):
        return None


def cache_put_ttl(url: str, ttl: int, body: bytes, ctype: str = "application/octet-stream") -> None:
    if not body:
        return
    body_path, meta_path = cache_paths(url)
    with CACHE_LOCK:
        try:
            body_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = body_path.with_suffix(".tmp%d" % threading.get_ident())
            tmp.write_bytes(body)
            tmp.replace(body_path)
            meta_path.write_text(json.dumps({
                "url": url, "status": 200, "ctype": ctype,
                "expires": time.time() + ttl, "stored": time.time(), "bytes": len(body),
            }))
        except OSError:
            return
        _prune_cache()


PRUNE_INTERVAL_S = 300
_PRUNE_STATE = {"last": 0.0}


def _prune_cache(force: bool = False) -> None:
    """Drop oldest cached files if the folder grows past the cap. Scans the whole cache folder, so it runs
    at most every PRUNE_INTERVAL_S (it used to run on every write: ~60 ms CPU per cold radar tile with a
    few thousand cached files, which on a 0.1-CPU instance capped cold tiles at ~2-3 a second)."""
    now = time.time()
    if not force and now - _PRUNE_STATE["last"] < PRUNE_INTERVAL_S:
        return
    _PRUNE_STATE["last"] = now
    try:
        files = [p for p in CACHE_DIR.rglob("*") if p.is_file() and not p.name.endswith(".tmp")]
        total = sum(p.stat().st_size for p in files)
    except OSError:
        return
    if total <= MAX_CACHE_BYTES:
        return
    files.sort(key=lambda p: p.stat().st_mtime)
    for p in files:
        try:
            total -= p.stat().st_size
            p.unlink(missing_ok=True)
        except OSError:
            continue
        if total <= MAX_CACHE_BYTES * 0.8:
            break


def fetch_url(url: str, tries: int = 4) -> tuple[int, str, bytes]:
    """GET with backoff. Retries 502/503 and network errors. Does not change the URL."""
    headers = {"User-Agent": UA, "Accept": "*/*"}
    last_status, last_ctype, last_body = 502, "text/plain; charset=utf-8", b"upstream error"
    for attempt in range(tries):
        try:
            req = Request(url, headers=headers)
            with urlopen(req, timeout=45) as resp:
                body = resp.read()
                status = getattr(resp, "status", 200)
                ctype = resp.headers.get("Content-Type", "application/octet-stream")
                return status, ctype, body
        except HTTPError as e:
            last_body = e.read() or b""
            last_status = e.code
            last_ctype = e.headers.get("Content-Type", "text/plain") if e.headers else "text/plain"
            if last_status in (502, 503, 504) and attempt < tries - 1:
                time.sleep(0.8 * (2 ** attempt))
                continue
            return last_status, last_ctype, last_body
        except (URLError, TimeoutError, OSError) as e:
            last_status, last_ctype, last_body = 502, "text/plain; charset=utf-8", ("upstream error: %s" % e).encode()
            if attempt < tries - 1:
                time.sleep(0.8 * (2 ** attempt))
                continue
            return last_status, last_ctype, last_body
    return last_status, last_ctype, last_body


def _ugc_from_alert(props: dict) -> set[str]:
    codes: set[str] = set()
    geocode = props.get("geocode") or {}
    for raw in geocode.get("UGC") or []:
        if isinstance(raw, str):
            codes.add(raw.split("-")[-1] if ":" in raw else raw)
    for key in ("affectedZones",):
        for item in props.get(key) or []:
            if isinstance(item, str) and "/" in item:
                codes.add(item.rstrip("/").split("/")[-1])
    return codes


def evaluate_ads(existing: dict | None = None) -> dict:
    """Apply the approved ad-pause rule to live NWS alerts for NC marine zones."""
    url = "https://api.weather.gov/alerts/active?area=NC&status=actual"
    status, ctype, body = fetch_url(url, tries=3)
    alerts_out = []
    hard_hits = []
    soft_regions: set[str] = set()
    fetch_ok = status == 200
    if fetch_ok:
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            payload = {}
            fetch_ok = False
        for feat in payload.get("features") or []:
            props = feat.get("properties") or {}
            if (props.get("status") or "Actual") != "Actual":
                continue  # NWS test/exercise/draft messages are never real alerts
            event = (props.get("event") or "").strip()
            ev_l = event.lower()
            codes = _ugc_from_alert(props)
            marine = sorted(codes & ALL_MARINE_ZONES)
            is_tropical = ev_l in {"tropical storm warning", "hurricane warning"}
            is_hard = ev_l in HARD_PAUSE_EVENTS
            is_soft = ev_l in SOFT_EVENTS or ev_l.startswith("small craft advisory")
            # Tropical warnings: also count if issued for any NC area, because
            # NWS often attaches them to land counties rather than AMZ IDs.
            touches_rule = bool(marine) or (is_tropical and ev_l in {"tropical storm warning", "hurricane warning"})
            if not (is_hard or is_soft):
                continue
            if is_hard and not touches_rule:
                continue
            if is_soft and not marine:
                continue
            rec = {
                "event": event,
                "severity": props.get("severity"),
                "headline": props.get("headline"),
                "zones": marine,
                "ends": props.get("ends") or props.get("expires"),
                "id": props.get("id") or feat.get("id"),
            }
            alerts_out.append(rec)
            if is_hard and touches_rule:
                hard_hits.append(rec)
            elif is_soft:
                for region, meta in REGIONS.items():
                    if codes & set(meta["zones"]):
                        soft_regions.add(region)

    previous = existing or {}
    settled_since = parse_iso(previous.get("settledSince"))
    now = now_utc()
    reasons = []

    if not fetch_ok:
        # Keep the last known flag rather than guessing. Say so.
        kept = dict(previous) if previous else {
            "adsOn": True, "mode": "full", "hardPause": False,
            "reducedRegions": [], "reasons": [], "settledSince": None,
            "resumeAfter": None, "alerts": [],
        }
        kept["evaluatedAt"] = iso(now)
        kept["reasons"] = list(kept.get("reasons") or []) + [
            "Could not refresh NWS alerts (HTTP %s). Left the previous ads flag as-is." % status
        ]
        kept["fetchOk"] = False
        return kept

    if hard_hits:
        settled_since = None
        resume_after = None
        ads_on = False
        hard_pause = True
        mode = "paused"
        for rec in hard_hits:
            names = ", ".join(rec["zones"]) or "NC (tropical warning)"
            reasons.append("%s is in effect for %s." % (rec["event"], names))
        reasons.append("Ads stay off until 12 hours after these warnings end.")
    else:
        hard_pause = False
        if previous.get("hardPause") or previous.get("mode") == "paused":
            if settled_since is None:
                settled_since = now
        if settled_since is not None:
            resume_after_dt = settled_since + RESUME_AFTER
            if now < resume_after_dt:
                ads_on = False
                mode = "paused"
                reasons.append(
                    "No gale-or-stronger or tropical warning right now. Ads stay off until %s ET (12 hours after conditions settled)."
                    % _to_et(resume_after_dt)
                )
            else:
                ads_on = True
                settled_since = None
                resume_after_dt = None
                mode = "full"
        else:
            ads_on = True
            resume_after_dt = None
            mode = "full"
        resume_after = iso(resume_after_dt) if settled_since and not ads_on else (iso(resume_after_dt) if 'resume_after_dt' in dir() and resume_after_dt else None)

    if ads_on and soft_regions:
        mode = "reduced"
        labels = [REGIONS[r]["label"] for r in sorted(soft_regions)]
        reasons.append(
            "Small craft advisory is in effect. Reduce ad density on: " + "; ".join(labels) + "."
        )
    if ads_on and not reasons:
        reasons.append("No gale-or-stronger warning, tropical storm/hurricane warning, or small craft advisory on NC coastal marine zones.")

    # Fix resume_after if we paused for 12h
    if hard_hits:
        resume_after = None
    elif not hard_pause and settled_since and not ads_on:
        resume_after = iso(settled_since + RESUME_AFTER)
    elif ads_on:
        resume_after = None

    reduced = sorted(soft_regions) if ads_on else []
    return {
        "adsOn": ads_on,
        "mode": mode,
        "hardPause": hard_pause,
        "reducedRegions": reduced,
        "reasons": reasons,
        "evaluatedAt": iso(now),
        "settledSince": iso(settled_since),
        "resumeAfter": resume_after,
        "alerts": alerts_out,
        "fetchOk": True,
    }


def _to_et(dt: datetime) -> str:
    try:
        from zoneinfo import ZoneInfo
        local = dt.astimezone(ZoneInfo("America/New_York"))
        return local.strftime("%-I:%M %p %Z on %b %-d, %Y")
    except Exception:
        return iso(dt) or ""


def load_ads() -> dict:
    if ADS_PATH.is_file():
        try:
            return json.loads(ADS_PATH.read_text())
        except (OSError, json.JSONDecodeError):
            return {}
    return {}


def ads_stale(data: dict, max_age: int = 5 * 60) -> bool:
    ts = parse_iso(data.get("evaluatedAt"))
    if ts is None:
        return True
    return (now_utc() - ts).total_seconds() > max_age


def get_ads(force: bool = False) -> dict:
    with ADS_LOCK:
        current = load_ads()
        if not force and current and not ads_stale(current):
            return current
        updated = evaluate_ads(current)
        try:
            ADS_PATH.parent.mkdir(parents=True, exist_ok=True)
            tmp = ADS_PATH.with_suffix(".tmp")
            tmp.write_text(json.dumps(updated, indent=2))
            tmp.replace(ADS_PATH)
        except OSError:
            pass
        return updated



def load_tide_stations() -> dict:
    if not TIDE_STATIONS_PATH.is_file():
        return {"stations": [], "aliases": []}
    try:
        return json.loads(TIDE_STATIONS_PATH.read_text())
    except (OSError, json.JSONDecodeError):
        return {"stations": [], "aliases": []}


def tide_station_index() -> dict:
    data = load_tide_stations()
    return {str(s.get("id")): s for s in data.get("stations") or []}


def _ymd_ok(value: str) -> bool:
    if not value or len(value) != 8 or not value.isdigit():
        return False
    try:
        datetime.strptime(value, "%Y%m%d")
        return True
    except ValueError:
        return False


def fetch_tide_predictions(station_id: str, begin: str, end: str, interval: str) -> tuple[int, dict | None, str]:
    params = (
        "product=predictions&application=%s&begin_date=%s&end_date=%s"
        "&datum=MLLW&station=%s&time_zone=lst_ldt&units=english"
        "&interval=%s&format=json" % (TIDE_APP, begin, end, station_id, interval)
    )
    url = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter?" + params
    cached = cache_get(url)
    if cached:
        status, _ctype, body = cached
    else:
        status, _ctype, body = fetch_url(url, tries=3)
        if status == 200:
            with CACHE_LOCK:
                cache_put(url, "tides_pred", status, "application/json", body)
    if status != 200:
        return status, None, "NOAA Tides & Currents returned HTTP %s." % status
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return 502, None, "NOAA Tides & Currents returned a response that could not be read."
    if payload.get("error"):
        msg = payload["error"]
        if isinstance(msg, dict):
            msg = msg.get("message") or str(msg)
        return 404, payload, str(msg)
    return 200, payload, ""


def handle_tides(query: str) -> tuple[int, dict]:
    qs = parse_qs(query or "")
    station_id = (qs.get("station") or [""])[0].strip()
    begin = (qs.get("begin") or [""])[0].strip()
    end = (qs.get("end") or [""])[0].strip()
    curve_day = (qs.get("curve") or [begin])[0].strip()
    stations = tide_station_index()
    meta = stations.get(station_id)
    if not meta:
        return 404, {"ok": False, "error": "That tide station is not in the North Carolina coastal list."}
    if not _ymd_ok(begin) or not _ymd_ok(end):
        return 400, {"ok": False, "error": "Choose a start and end date."}
    try:
        bdt = datetime.strptime(begin, "%Y%m%d")
        edt = datetime.strptime(end, "%Y%m%d")
    except ValueError:
        return 400, {"ok": False, "error": "Those dates are not valid."}
    if edt < bdt:
        return 400, {"ok": False, "error": "The end date is before the start date."}
    if (edt - bdt).days > 10:
        return 400, {"ok": False, "error": "Please ask for at most 10 days at a time."}
    today = datetime.now(timezone.utc).date()
    # Allow yesterday through ~31 days ahead (plan-a-trip window).
    if bdt.date() < today - timedelta(days=1) or edt.date() > today + timedelta(days=32):
        return 400, {"ok": False, "error": "Tide dates must fall between yesterday and the next 30 days."}
    status, payload, err = fetch_tide_predictions(station_id, begin, end, "hilo")
    if status != 200 or not payload:
        return status if status >= 400 else 502, {"ok": False, "error": err or "Could not load tide predictions."}
    preds = payload.get("predictions") or []
    curve = []
    if _ymd_ok(curve_day):
        cstatus, cpayload, _cerr = fetch_tide_predictions(station_id, curve_day, curve_day, "15")
        if cstatus == 200 and cpayload:
            curve = cpayload.get("predictions") or []
    source = "https://tidesandcurrents.noaa.gov/stationhome.html?id=%s" % station_id
    return 200, {
        "ok": True,
        "station": meta,
        "begin": begin,
        "end": end,
        "curveDay": curve_day,
        "predictions": preds,
        "curve": curve,
        "datum": "MLLW",
        "units": "feet",
        "timeZone": "lst_ldt",
        "sourceName": "NOAA Tides & Currents",
        "sourceUrl": source,
        "subordinate": bool(meta.get("subordinate")),
        "referenceId": meta.get("referenceId"),
    }


def handle_geocode(query: str) -> tuple[int, dict]:
    """Nominatim lookup through this server. Census onelineaddress needs a street
    number, so it is not useful for town/inlet/beach names. Respects the
    Nominatim 1 request/second policy and caches results."""
    global _GEO_LAST
    qs = parse_qs(query or "")
    q = (qs.get("q") or [""])[0].strip()
    if len(q) < 3:
        return 400, {"ok": False, "error": "Type at least a few letters of a place name."}
    # Keep the query in-region; don't let this become a general geocoder.
    look = q
    low = q.lower()
    if "north carolina" not in low and ", nc" not in low and low[-3:] != " nc" and ", sc" not in low and ", va" not in low:
        look = q + ", North Carolina"
    url = (
        NOMINATIM + "/search?q=" + quote_plus(look)
        + "&format=json&limit=5&countrycodes=us&addressdetails=0"
    )
    cached = cache_get(url)
    if cached:
        status, _ctype, body = cached
    else:
        with GEO_LOCK:
            wait = 1.05 - (time.time() - _GEO_LAST)
            if wait > 0:
                time.sleep(wait)
            status, _ctype, body = fetch_url(url, tries=2)
            _GEO_LAST = time.time()
        if status == 200:
            with CACHE_LOCK:
                cache_put(url, "geocode", status, "application/json", body)
    if status != 200:
        return 502, {"ok": False, "error": "The place-name lookup is unavailable right now. Try a station or town name from the list."}
    try:
        rows = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return 502, {"ok": False, "error": "The place-name lookup returned a response that could not be read."}
    matches = []
    for row in rows or []:
        try:
            lat = float(row.get("lat"))
            lon = float(row.get("lon"))
        except (TypeError, ValueError):
            continue
        # NC coast plus nearby VA/SC border
        if not (33.40 <= lat <= 36.95 and -79.30 <= lon <= -75.30):
            continue
        matches.append({
            "label": row.get("display_name") or look,
            "lat": lat,
            "lng": lon,
            "type": row.get("type") or row.get("class"),
        })
    return 200, {"ok": True, "query": q, "matches": matches, "provider": "Nominatim (OpenStreetMap)"}



# WeatherAPI Radar (Pro+). Key stays on the server. Never log it.
WEATHERAPI_ORIGIN = "https://api.weatherapi.com"
RADAR_Q = "34.72,-76.65"  # fixed central coastal NC
RADAR_JSON_TTL = 3 * 60
RADAR_LOCK = threading.Lock()
_RADAR_MEM = {
    "fetched_at": 0.0,
    "tile_url": None,
    "tile_url_expires_epoch": 0,
    "client": None,
    "error": None,
}



# In-memory + best-effort on-disk counter for actual upstream radar.json calls.
# Render's free disk is wiped on restart, so counts reset then. Process start
# time is included in /api/radar/usage so a reader can tell.
RADAR_USAGE_PATH = ROOT / "data" / "radar-usage.json"
USAGE_LOCK = threading.Lock()
PROCESS_STARTED = now_utc()
_USAGE_LOADED = False
_RADAR_USAGE = {
    "date_et": "",
    "upstream_calls_today": 0,
    "cache_hits_today": 0,
    "errors_today": 0,
}


def _et_now() -> datetime:
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo("America/New_York"))


def _date_et() -> str:
    return _et_now().date().isoformat()


def _usage_reset(date_et: str) -> None:
    _RADAR_USAGE["date_et"] = date_et
    _RADAR_USAGE["upstream_calls_today"] = 0
    _RADAR_USAGE["cache_hits_today"] = 0
    _RADAR_USAGE["errors_today"] = 0


def _usage_load() -> None:
    """Load today's counts from disk if the file is still there."""
    global _USAGE_LOADED
    _USAGE_LOADED = True
    try:
        data = json.loads(RADAR_USAGE_PATH.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return
    if not isinstance(data, dict):
        return
    today = _date_et()
    if data.get("date_et") != today:
        return
    try:
        _RADAR_USAGE["date_et"] = today
        _RADAR_USAGE["upstream_calls_today"] = int(data.get("upstream_calls_today") or 0)
        _RADAR_USAGE["cache_hits_today"] = int(data.get("cache_hits_today") or 0)
        _RADAR_USAGE["errors_today"] = int(data.get("errors_today") or 0)
    except (TypeError, ValueError):
        _usage_reset(today)


def _usage_save() -> None:
    """Best-effort persist. Ignore disk errors; memory still has the counts."""
    payload = {
        "date_et": _RADAR_USAGE["date_et"],
        "upstream_calls_today": _RADAR_USAGE["upstream_calls_today"],
        "cache_hits_today": _RADAR_USAGE["cache_hits_today"],
        "errors_today": _RADAR_USAGE["errors_today"],
    }
    try:
        RADAR_USAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = RADAR_USAGE_PATH.with_name("radar-usage.json.tmp")
        tmp.write_text(json.dumps(payload), encoding="utf-8")
        tmp.replace(RADAR_USAGE_PATH)
    except OSError:
        pass


def _usage_ensure_today() -> None:
    global _USAGE_LOADED
    if not _USAGE_LOADED:
        _usage_load()
        _USAGE_LOADED = True
    today = _date_et()
    if _RADAR_USAGE["date_et"] != today:
        _usage_reset(today)


def record_radar_cache_hit() -> None:
    with USAGE_LOCK:
        _usage_ensure_today()
        _RADAR_USAGE["cache_hits_today"] += 1
        _usage_save()


def record_radar_upstream(*, error: bool) -> None:
    with USAGE_LOCK:
        _usage_ensure_today()
        _RADAR_USAGE["upstream_calls_today"] += 1
        if error:
            _RADAR_USAGE["errors_today"] += 1
        _usage_save()


def radar_usage_payload() -> dict:
    with USAGE_LOCK:
        _usage_ensure_today()
        started = PROCESS_STARTED.astimezone(_et_now().tzinfo).replace(microsecond=0)
        payload = {
            "date_et": _RADAR_USAGE["date_et"],
            "upstream_calls_today": _RADAR_USAGE["upstream_calls_today"],
            "cache_hits_today": _RADAR_USAGE["cache_hits_today"],
            "errors_today": _RADAR_USAGE["errors_today"],
            "since_restart": started.isoformat(),
            "key_configured": bool(weatherapi_key()),
        }
        _usage_save()
        return payload


def weatherapi_key() -> str | None:
    """Read WEATHERAPI_KEY. Also accept a curl/URL paste that contains key=."""
    raw = (os.environ.get("WEATHERAPI_KEY") or "").strip()
    if not raw:
        return None
    m = re.search(r"(?:[?&]key=)([^&\"'\s]+)", raw, re.I)
    if m:
        key = m.group(1).strip()
        return key or None
    raw = raw.strip('"').strip("'")
    if "://" in raw or " " in raw:
        return None
    if len(raw) >= 16:
        return raw
    return None


def _redact_weather(s: str) -> str:
    key = weatherapi_key()
    if key:
        s = s.replace(key, "[REDACTED_KEY]")
    s = re.sub(r"([?&]k=)[^&]+", r"\1[REDACTED]", s)
    s = re.sub(r"([?&]s=)[^&]+", r"\1[REDACTED]", s)
    return s


def fetch_url_quiet(url: str, tries: int = 3) -> tuple[int, str, bytes]:
    """GET that never puts the request URL (which may hold a key) into error text."""
    headers = {"User-Agent": UA, "Accept": "*/*"}
    last_status, last_ctype, last_body = 502, "text/plain; charset=utf-8", b"upstream error"
    for attempt in range(tries):
        try:
            req = Request(url, headers=headers)
            with urlopen(req, timeout=45) as resp:
                body = resp.read()
                status = getattr(resp, "status", 200)
                ctype = resp.headers.get("Content-Type", "application/octet-stream")
                return status, ctype, body
        except HTTPError as e:
            last_body = e.read() or b""
            last_status = e.code
            last_ctype = e.headers.get("Content-Type", "text/plain") if e.headers else "text/plain"
            if last_status in (502, 503, 504) and attempt < tries - 1:
                time.sleep(0.8 * (2 ** attempt))
                continue
            return last_status, last_ctype, last_body
        except (URLError, TimeoutError, OSError):
            last_status, last_ctype, last_body = 502, "text/plain; charset=utf-8", b"upstream error"
            if attempt < tries - 1:
                time.sleep(0.8 * (2 ** attempt))
                continue
            return last_status, last_ctype, last_body
    return last_status, last_ctype, last_body


def _client_radar_payload(data: dict, tile_url: str) -> dict:
    radar = data.get("radar") or {}
    frames = []
    for fr in radar.get("frames") or []:
        if not isinstance(fr, dict):
            continue
        time_code = str(fr.get("time") or "")
        if not re.fullmatch(r"\d{12}", time_code):
            continue
        typ = fr.get("type") if fr.get("type") in ("observed", "nowcast") else "observed"
        rec = {"time": time_code, "type": typ}
        try:
            rec["time_epoch"] = int(fr.get("time_epoch"))
        except (TypeError, ValueError):
            pass
        frames.append(rec)
    sources = []
    for src in radar.get("sources") or []:
        if not isinstance(src, dict):
            continue
        sources.append({
            "id": src.get("id"),
            "name": src.get("name"),
            "nowcast_minutes": src.get("nowcast_minutes"),
            "bounds": src.get("bounds"),
        })
    legend = []
    for row in radar.get("legend") or []:
        if isinstance(row, dict) and "color" in row:
            legend.append({"from_mm_h": row.get("from_mm_h"), "color": row.get("color")})
    try:
        min_zoom = int(radar.get("min_zoom", 0))
        max_zoom = int(radar.get("max_zoom", 11))
        tile_size = int(radar.get("tile_size", 256))
    except (TypeError, ValueError):
        min_zoom, max_zoom, tile_size = 0, 11, 256
    return {
        "ok": True,
        "available": bool(radar.get("available")),
        "covered": bool(radar.get("covered")),
        "tile_url": "/api/radar/tile/{z}/{x}/{y}.png?t={time}",
        "min_zoom": min_zoom,
        "max_zoom": max_zoom,
        "tile_size": tile_size,
        "frames": frames,
        "legend": legend,
        "attribution": radar.get("attribution") or "Radar: NOAA/NSSL MRMS and WeatherAPI.com.",
        "sources": sources,
        "disclaimer": (
            "Radar is for general information only and can be incomplete or late. "
            "It is not a substitute for official National Weather Service marine forecasts and advisories. "
            "Do not rely on it as the only source for safety decisions."
        ),
    }


def _refresh_radar_mem(force: bool = False) -> dict:
    """Fetch radar.json if needed. Stores the signed tile template in memory only."""
    key = weatherapi_key()
    if not key:
        return {
            "ok": False,
            "available": False,
            "reason": "coming_soon",
            "message": "Radar coming soon",
        }
    now = time.time()
    with RADAR_LOCK:
        mem = _RADAR_MEM
        signed_ok = bool(mem.get("tile_url")) and now < (float(mem.get("tile_url_expires_epoch") or 0) - 120)
        fresh = mem.get("client") and (now - float(mem.get("fetched_at") or 0) < RADAR_JSON_TTL) and signed_ok
        if fresh and not force:
            record_radar_cache_hit()
            return mem["client"]
        url = WEATHERAPI_ORIGIN + "/v1/radar.json?key=" + key + "&q=" + RADAR_Q
        status, ctype, body = fetch_url_quiet(url, tries=3)
        upstream_error = True
        try:
            if status != 200:
                sys.stderr.write("radar.json upstream HTTP %s\n" % status)
                quota = status == 429
                if quota:
                    note_radar_feed(
                        "quota",
                        "Radar is temporarily limited. Showing cached observed frames where available.",
                    )
                else:
                    note_radar_feed(
                        "upstream",
                        "Radar is unavailable right now. Showing cached observed frames where available.",
                    )
                if mem.get("client") and signed_ok:
                    return mem["client"]
                if quota:
                    return {
                        "ok": False, "available": False, "reason": "quota",
                        "message": "Radar is temporarily limited. Try again in a few minutes. No old frames are shown in their place.",
                    }
                msg = "Radar is unavailable right now."
                try:
                    err = json.loads(body.decode("utf-8")).get("error") or {}
                    code = err.get("code")
                    if code == 2009:
                        note_radar_feed(None)
                        return {"ok": False, "available": False, "reason": "coming_soon", "message": "Radar coming soon"}
                except (UnicodeDecodeError, json.JSONDecodeError, AttributeError):
                    pass
                return {"ok": False, "available": False, "reason": "upstream", "message": msg}
            try:
                data = json.loads(body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                return {"ok": False, "available": False, "reason": "upstream", "message": "Radar is unavailable right now."}
            if data.get("error"):
                code = (data.get("error") or {}).get("code")
                if code == 2009:
                    return {"ok": False, "available": False, "reason": "coming_soon", "message": "Radar coming soon"}
                return {"ok": False, "available": False, "reason": "upstream", "message": "Radar is unavailable right now."}
            radar = data.get("radar") or {}
            tile_url = radar.get("tile_url") or ""
            if not tile_url.startswith("https://api.weatherapi.com/v1/radar/tile/"):
                return {"ok": False, "available": False, "reason": "upstream", "message": "Radar is unavailable right now."}
            try:
                expires = int(radar.get("tile_url_expires_epoch") or 0)
            except (TypeError, ValueError):
                expires = 0
            client = _client_radar_payload(data, tile_url)
            mem["fetched_at"] = now
            mem["tile_url"] = tile_url
            mem["tile_url_expires_epoch"] = expires if expires else now + 2 * 60 * 60
            mem["client"] = client
            mem["error"] = None
            upstream_error = False
            note_radar_feed(None)
            _start_radar_prewarm(client)
            return client
        finally:
            record_radar_upstream(error=upstream_error)


def handle_radar_meta() -> tuple[int, dict]:
    payload = _refresh_radar_mem(force=False)
    status = 200 if payload.get("ok") or payload.get("reason") == "coming_soon" else 502
    return status, payload


def _valid_radar_tile(z: str, x: str, y: str, t: str) -> bool:
    if not re.fullmatch(r"\d{12}", t or ""):
        return False
    try:
        zi, xi, yi = int(z), int(x), int(y)
    except ValueError:
        return False
    if zi < 0 or zi > 12:
        return False
    max_t = 2 ** zi
    if xi < 0 or yi < 0 or xi >= max_t or yi >= max_t:
        return False
    return True


def fetch_radar_tile(z: str, x: str, y: str, t: str) -> tuple[int, str, bytes]:
    status, ctype, body, _info = fetch_radar_tile_ex(z, x, y, t)
    return status, ctype, body


def fetch_radar_tile_ex(z: str, x: str, y: str, t: str) -> tuple[int, str, bytes, dict]:
    """Fetch a radar tile, reusing a terms-allowed stale copy when upstream fails.

    info["cache"] is "fresh", "stale", or None. A stale tile is a real observed
    (or still-valid nowcast) image, never a placeholder.
    """
    if not weatherapi_key():
        return 503, "application/json; charset=utf-8", json.dumps({
            "ok": False, "reason": "coming_soon", "message": "Radar coming soon"
        }).encode("utf-8"), {"cache": None, "reason": "coming_soon"}
    if not _valid_radar_tile(z, x, y, t):
        return 400, "text/plain; charset=utf-8", b"invalid tile", {"cache": None}
    cache_key_url = "radar-cache://tile/%s/%s/%s/%s" % (z, x, y, t)
    cached = cache_get(cache_key_url)
    if cached:
        return cached[0], cached[1], cached[2], {"cache": "fresh"}
    with _TILE_INFLIGHT_LOCK:
        ev = _TILE_INFLIGHT.get(cache_key_url)
        owner = ev is None
        if owner:
            ev = _TILE_INFLIGHT[cache_key_url] = threading.Event()
    if not owner:
        ev.wait(30)
        cached = cache_get(cache_key_url)
        if cached:
            return cached[0], cached[1], cached[2], {"cache": "fresh"}
        stale = stale_radar_tile(z, x, y, t)
        if stale:
            return stale[0], stale[1], stale[2], {"cache": "stale"}
    try:
        return _fetch_radar_tile_upstream(z, x, y, t, cache_key_url)
    finally:
        if owner:
            with _TILE_INFLIGHT_LOCK:
                _TILE_INFLIGHT.pop(cache_key_url, None)
            ev.set()


_TILE_INFLIGHT: dict = {}
_TILE_INFLIGHT_LOCK = threading.Lock()


def _tile_error(status: int, reason: str, message: str) -> tuple[int, str, bytes, dict]:
    payload = {"ok": False, "reason": reason, "message": message}
    return status, "application/json; charset=utf-8", json.dumps(payload).encode("utf-8"), {"cache": None, "reason": reason}


def _fetch_radar_tile_upstream(z: str, x: str, y: str, t: str, cache_key_url: str) -> tuple[int, str, bytes, dict]:
    meta = _refresh_radar_mem(force=False)
    if not meta.get("ok"):
        stale = stale_radar_tile(z, x, y, t)
        if stale and meta.get("reason") != "coming_soon":
            reason = "quota" if meta.get("reason") == "quota" else "upstream"
            note_radar_feed(reason, "Radar is temporarily limited. Showing cached observed frames where available.")
            return stale[0], stale[1], stale[2], {"cache": "stale", "reason": reason}
        status = 503 if meta.get("reason") == "coming_soon" else (429 if meta.get("reason") == "quota" else 502)
        return _tile_error(status, meta.get("reason") or "upstream", meta.get("message") or "Radar is unavailable right now.")
    with RADAR_LOCK:
        template = _RADAR_MEM.get("tile_url") or ""
    if not template or "{z}" not in template or "{time}" not in template:
        stale = stale_radar_tile(z, x, y, t)
        if stale:
            return stale[0], stale[1], stale[2], {"cache": "stale", "reason": "upstream"}
        return 502, "text/plain; charset=utf-8", b"radar tile template missing", {"cache": None, "reason": "upstream"}
    url = template.replace("{z}", z).replace("{x}", x).replace("{y}", y).replace("{time}", t)
    status, ctype, body = fetch_url_quiet(url, tries=3)
    if status == 200 and body:
        cache_put_ttl(cache_key_url, radar_tile_ttl(t), body, ctype or "image/png")
        return status, ctype or "image/png", body, {"cache": "fresh"}
    if status == 429:
        note_radar_feed("quota", "Radar is temporarily limited. Showing cached observed frames where available.")
        reason, message = "quota", "Radar is temporarily limited. Try again in a few minutes."
        fail_status = 429
    else:
        note_radar_feed("upstream", "Radar is unavailable right now. Showing cached observed frames where available.")
        reason, message = "upstream", "Radar is unavailable right now."
        fail_status = 502 if status >= 500 or status == 0 else status
    stale = stale_radar_tile(z, x, y, t)
    if stale:
        return stale[0], stale[1], stale[2], {"cache": "stale", "reason": reason}
    return _tile_error(fail_status, reason, message)


# Prewarm: after each radar.json refresh, fetch the observed frames' tiles for the viewer's default phone
# view (z7, 3x3 tiles over the NC coast), newest first, 2 at a time. Bounded: at most 25 frames x 9 tiles,
# and only tiles not already cached (normally just the newest frame's 9). Tiles are not API calls.
RADAR_PREWARM_TILES = [(7, x, y) for x in (35, 36, 37) for y in (49, 50, 51)]
RADAR_PREWARM_MAX = 25 * 9
_PREWARM = {"running": False}


def _radar_prewarm_enabled() -> bool:
    flag = (os.environ.get("RADAR_PREWARM") or "").strip()
    if flag:
        return flag == "1"
    return bool(os.environ.get("RENDER") or os.environ.get("RENDER_SERVICE_ID"))


def _start_radar_prewarm(client: dict) -> None:
    if not _radar_prewarm_enabled() or _PREWARM["running"]:
        return
    times = [f.get("time") for f in (client.get("frames") or []) if f.get("type") == "observed"][::-1]
    jobs = [(t, z, x, y) for t in times for (z, x, y) in RADAR_PREWARM_TILES]
    jobs = [j for j in jobs if not cache_get("radar-cache://tile/%s/%s/%s/%s" % (j[1], j[2], j[3], j[0]))][:RADAR_PREWARM_MAX]
    if not jobs:
        return
    _PREWARM["running"] = True

    def run():
        try:
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(2) as ex:
                list(ex.map(lambda j: fetch_radar_tile(str(j[1]), str(j[2]), str(j[3]), j[0]), jobs))
        except Exception:   # never let a warm-up problem reach the request path
            pass
        finally:
            _PREWARM["running"] = False
    threading.Thread(target=run, name="radar-prewarm", daemon=True).start()


def radar_tile_ttl(t: str) -> int:
    """Observed tiles never change (2 h cache). Nowcast tiles for the same time are re-issued with each
    radar.json update (verified Nov 20, 2026), so they only live as long as the frame list (180 s)."""
    with RADAR_LOCK:
        frames = (_RADAR_MEM.get("client") or {}).get("frames") or []
    for f in frames:
        if f.get("time") == t and f.get("type") == "nowcast":
            return RADAR_JSON_TTL
    return TTL["radar_tile"]


# WeatherAPI terms cap current (observed) imagery at 60 minutes. Nowcast tiles
# are re-issued with each radar.json (180 s), so a stale nowcast may only be
# reused within that window.
OBSERVED_TILE_MAX_AGE = 60 * 60
NOWCAST_TILE_MAX_AGE = RADAR_JSON_TTL

# Public API rate limits, sized from real /radar loading:
# 25 observed + 12 nowcast frames × ~9 tiles at native z7 ≈ 333 requests for a
# full load. A pan/zoom can refetch tiles for every loaded layer (another ~333).
# A typical session with several pans, a zoom, and a 3-minute refresh stays
# under 2,000. 2,400 / 5 minutes leaves headroom without letting one IP crawl
# the tile space. Meta and wind-grid limits cover dashboard + viewer refresh
# and the five GFS ahead steps, with retries.
API_TILE_LIMIT, API_TILE_WINDOW = 2400, 300
API_RADAR_META_LIMIT, API_RADAR_META_WINDOW = 60, 60
API_WIND_GRID_LIMIT, API_WIND_GRID_WINDOW = 30, 60


class SlidingWindowLimiter:
    """Per-key sliding window. Returns (allowed, retry_after_seconds)."""

    def __init__(self):
        self._hits: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def check(self, key: str, limit: int, window_s: int, now: float | None = None) -> tuple[bool, int]:
        now = time.time() if now is None else now
        with self._lock:
            hits = [t for t in self._hits.get(key, []) if now - t < window_s]
            if len(hits) >= limit:
                self._hits[key] = hits
                retry = int(max(1, window_s - (now - hits[0]) + 0.999))
                return False, retry
            hits.append(now)
            self._hits[key] = hits
            if len(self._hits) > 8000:
                for k in list(self._hits)[:2000]:
                    self._hits.pop(k, None)
            return True, 0

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


API_LIMITS = SlidingWindowLimiter()

_VALID_IP = re.compile(
    r"^(?:(?:\d{1,3}\.){3}\d{1,3}|[0-9a-fA-F:]+)$"
)

# Query keys whose values must never appear in request logs.
_SENSITIVE_QS = re.compile(
    r"(?i)([?&])(key|token|preview|preview_key|password|passwd|secret|auth|"
    r"access_token|api_key|apikey|authorization)=([^&\s]*)"
)


def redact_request_text(s: str) -> str:
    """Replace sensitive query values (key, token, preview, …) with REDACTED."""
    if not s or ("?" not in s and "&" not in s and "=" not in s):
        # still run the regex — cheap, and request lines always have a path
        pass
    return _SENSITIVE_QS.sub(r"\1\2=REDACTED", s)


def valid_ip(value: str) -> bool:
    v = (value or "").strip()
    if not v or not _VALID_IP.match(v):
        return False
    if ":" in v:
        return True
    parts = v.split(".")
    return len(parts) == 4 and all(p.isdigit() and 0 <= int(p) <= 255 for p in parts)


def client_ip_from_headers(headers, fallback: str = "") -> str:
    """Client IP behind Render / Cloudflare.

    Prefer CF-Connecting-IP when present. Otherwise use the leftmost valid
    X-Forwarded-For hop (the original client when each proxy appends). Render
    sets X-Forwarded-For to the connecting IP; a spoofed leftmost value is
    rejected if it isn't a well-formed address. Fall back to the socket peer.
    """
    cf = (headers.get("CF-Connecting-IP") or headers.get("Cf-Connecting-Ip") or "").strip()
    if valid_ip(cf):
        return cf
    xff = headers.get("X-Forwarded-For") or headers.get("X-Forwarded-for") or ""
    for part in xff.split(","):
        ip = part.strip()
        if valid_ip(ip):
            return ip
    return (fallback or "").strip()[:64]


# Last WeatherAPI/upstream restriction, for a clear in-viewer message.
_RADAR_FEED = {"limited": False, "reason": None, "message": "", "at": 0.0}
_RADAR_FEED_LOCK = threading.Lock()
_FEED_HOLD = 5 * 60


def note_radar_feed(reason: str | None, message: str = "") -> None:
    with _RADAR_FEED_LOCK:
        if reason:
            _RADAR_FEED.update({"limited": True, "reason": reason, "message": message, "at": time.time()})
        else:
            _RADAR_FEED.update({"limited": False, "reason": None, "message": "", "at": time.time()})


def radar_feed_status() -> dict:
    with _RADAR_FEED_LOCK:
        if not _RADAR_FEED["limited"] or (time.time() - float(_RADAR_FEED["at"] or 0)) > _FEED_HOLD:
            return {"limited": False}
        return {
            "limited": True,
            "limit_reason": _RADAR_FEED["reason"],
            "limit_message": _RADAR_FEED["message"],
        }


def _apply_feed_status(payload: dict) -> dict:
    """Attach a limited-feed flag without inventing frames or overriding a plan state."""
    if not isinstance(payload, dict):
        return payload
    out = dict(payload)
    st = radar_feed_status()
    if not st.get("limited"):
        return out
    out["limited"] = True
    out["limit_reason"] = st.get("limit_reason")
    out["limit_message"] = st.get("limit_message") or (
        "Radar is temporarily limited. Showing cached observed frames where available. "
        "Incomplete or forecast frames are not shown."
    )
    return out


def radar_tile_is_nowcast(t: str) -> bool:
    with RADAR_LOCK:
        frames = (_RADAR_MEM.get("client") or {}).get("frames") or []
    for f in frames:
        if f.get("time") == t and f.get("type") == "nowcast":
            return True
    return False


def stale_radar_tile(z: str, x: str, y: str, t: str) -> tuple[int, str, bytes] | None:
    """Reuse a cached tile only while WeatherAPI terms still allow it.

    Observed: age ≤ 60 minutes. Nowcast: age ≤ 180 s. Never invent a tile.
    """
    cache_key_url = "radar-cache://tile/%s/%s/%s/%s" % (z, x, y, t)
    ent = cache_entry(cache_key_url)
    if not ent or ent["status"] != 200 or not ent["body"]:
        return None
    age = ent["age"]
    if age is None or age < 0:
        return None
    limit = NOWCAST_TILE_MAX_AGE if radar_tile_is_nowcast(t) else OBSERVED_TILE_MAX_AGE
    if age > limit:
        return None
    if not _is_image(ent["ctype"], ent["body"]):
        return None
    return ent["status"], ent["ctype"], ent["body"]


import conditions  # noqa: E402
import homepage_boot  # noqa: E402
import photos  # noqa: E402
import catch_wall_public  # noqa: E402
import catch_wall_preview  # noqa: E402
import windgrid  # noqa: E402
import hrrrgrid  # noqa: E402
import radarview  # noqa: E402
import showcase  # noqa: E402  (homepage Wind & Radar section; HOME_SHOWCASE flag, default off)
import freshwater  # noqa: E402
import brief  # noqa: E402
import wave_intro  # noqa: E402
import sprint_home  # noqa: E402
import photo_rotation  # noqa: E402
import site_chrome  # noqa: E402

# Header "Morning Brief" link is in the HTML behind this marker. When the kill
# switch is on (MORNING_BRIEF_ENABLED=0/false/off), strip it so the nav never
# points at a 404. The brief is on by default, so public pages keep the link.
_BRIEF_NAV_RE = re.compile(br"<!--brief-nav-->.*?<!--/brief-nav-->", re.S)

def _apply_brief_nav(data: bytes) -> bytes:
    if brief.flag_on():
        return data
    return _BRIEF_NAV_RE.sub(b"", data, count=1)


_DATELINE_RE = re.compile(br"<!--dateline-->.*?<!--/dateline-->", re.S)


def _dateline_html() -> bytes:
    """Publication dateline in America/New_York, reserved in the masthead."""
    now = datetime.now(ZoneInfo("America/New_York"))
    label = "%s, %s %d, %d · Eastern Time" % (
        now.strftime("%A"),
        now.strftime("%B"),
        now.day,
        now.year,
    )
    iso = now.date().isoformat()
    return b'<time datetime="%s">%s</time>' % (iso.encode("ascii"), html.escape(label).encode("utf-8"))


def _apply_dateline(data: bytes) -> bytes:
    if b"<!--dateline-->" not in data:
        return data
    return _DATELINE_RE.sub(_dateline_html(), data, count=1)


def _apply_chrome(data: bytes) -> bytes:
    return _apply_dateline(_apply_brief_nav(data))


def _preview_dateline_html() -> bytes:
    """Preview-only dateline: full label plus a short phone form (SAT · NOV 14, 2026)."""
    now = datetime.now(ZoneInfo("America/New_York"))
    full = "%s, %s %d, %d · Eastern Time" % (
        now.strftime("%A"),
        now.strftime("%B"),
        now.day,
        now.year,
    )
    short = "%s · %s %d, %d" % (
        now.strftime("%a"),
        now.strftime("%b"),
        now.day,
        now.year,
    )
    iso = now.date().isoformat()
    return (
        b'<time datetime="%s">'
        b'<span class="mast-date-full">%s</span>'
        b'<span class="mast-date-short">%s</span>'
        b"</time>"
    ) % (
        iso.encode("ascii"),
        html.escape(full).encode("utf-8"),
        html.escape(short).encode("utf-8"),
    )


def _apply_preview_dateline(data: bytes) -> bytes:
    """Swap the public dateline in the concept masthead only; public pages are unchanged."""
    return re.sub(
        br'(<p class="mast-dateline" id="mast-dateline">)\s*<time datetime="[^"]*">[^<]*</time>',
        br"\1" + _preview_dateline_html(),
        data,
        count=1,
    )


# Private masthead concepts. Public pages never include this markup or CSS.
MASTHEAD_CONCEPTS = ("a", "b", "c")
MASTHEAD_DIR = ROOT / "preview" / "masthead"
_MASTHEAD_META = b'<div class="wrap">\n      <div class="meta-row">'
_MASTHEAD_PLAY = b"""<script>
(function(){
  var c = document.documentElement.getAttribute("data-concept") || "c";
  var key = "cb-mast-reveal-" + c;
  var force = /(?:\\?|&)play=1(?:&|$)/.test(location.search || "");
  var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (reduce) return;
  try {
    if (force || !sessionStorage.getItem(key)) {
      document.documentElement.classList.add("mast-play");
      if (!force) sessionStorage.setItem(key, "1");
    }
  } catch (e) {}
})();
</script>
"""
_MASTHEAD_DOCK = """<div id="mast-preview-dock" class="mast-preview-dock" hidden>
  <span class="pv-lab">Private preview</span>
  <a href="/preview/masthead?c=a" data-c="a">A Editorial</a>
  <a href="/preview/masthead?c=b" data-c="b">B Nautical</a>
  <a href="/preview/masthead?c=c" data-c="c">C Hybrid</a>
  <button type="button" id="mast-replay">Replay</button>
</div>
<script>
(function(){
  var dock = document.getElementById("mast-preview-dock");
  if (!dock) return;
  dock.hidden = false;
  var c = document.documentElement.getAttribute("data-concept") || "c";
  var on = dock.querySelector('a[data-c="'+c+'"]');
  if (on) on.className += " is-on";
  var btn = document.getElementById("mast-replay");
  if (!btn) return;
  btn.addEventListener("click", function(){
    var key = "cb-mast-reveal-" + c;
    try { sessionStorage.removeItem(key); } catch (e) {}
    var html = document.documentElement;
    html.classList.remove("mast-play");
    void html.offsetWidth;
    html.classList.add("mast-play");
    document.querySelectorAll(".wave-swell, .wave-settle, .wave-glint, .mast-sheen").forEach(function(el){
      var prev = el.style.animation;
      el.style.animation = "none";
      void el.offsetWidth;
      el.style.animation = prev;
    });
  });
})();
</script>
"""



def _preview_style_tag(*paths: Path) -> bytes:
    """One inlined stylesheet for a private preview; avoids an extra CSS request."""
    chunks = []
    for path in paths:
        chunks.append(path.read_text(encoding="utf-8"))
    css = "\n".join(chunks)
    return b'  <style id="preview-css">\n' + css.encode("utf-8") + b"\n  </style>\n"


def _masthead_preview_html(concept: str, shot: bool = False, dock: str | None = None, css_files: list[Path] | None = None, extra_attrs: bytes = b"") -> bytes:
    """Homepage with a concept masthead swapped in. Comparison previews stay private."""
    if concept not in MASTHEAD_CONCEPTS:
        concept = "c"
    src = (ROOT / "index.html").read_bytes()
    header = (MASTHEAD_DIR / "header.html").read_bytes().strip()
    start = src.find(b'<header class="site"')
    mid = src.find(_MASTHEAD_META)
    if start < 0 or mid < 0 or mid < start:
        raise RuntimeError("masthead preview: unexpected index.html shape")
    data = src[:start] + header + b"\n\n    " + src[mid:]
    attrs = b' data-preview data-concept="%s"' % concept.encode("ascii")
    if extra_attrs:
        attrs += extra_attrs
    if shot:
        attrs += b" data-shot"
    data = data.replace(b'<html lang="en" data-tiles="v2">', b'<html lang="en" data-tiles="v2"' + attrs + b">", 1)
    # Inline preview CSS so the page does not pay an extra stylesheet request (FCP).
    inject = _preview_style_tag(*(css_files or (MASTHEAD_DIR / "masthead.css",)))
    inject += b'  <meta name="robots" content="noindex, nofollow">\n  ' + _MASTHEAD_PLAY
    needle = b'  <link rel="stylesheet" href="styles.css">\n'
    if needle not in data:
        raise RuntimeError("masthead preview: stylesheet link missing")
    data = data.replace(needle, needle + inject, 1)
    if not shot:
        dock_html = _MASTHEAD_DOCK if dock is None else dock
        data = data.replace(b"</body>", dock_html.encode("utf-8") + b"\n</body>", 1)
    # Page is served from /preview/masthead, so homepage-relative assets must be rooted.
    for a, b in (
        (b'href="styles.css"', b'href="/styles.css"'),
        (b'src="region-nav.js"', b'src="/region-nav.js"'),
        (b'src="dashboard.js"', b'src="/dashboard.js"'),
        (b'src="app.js"', b'src="/app.js"'),
        (b'src="coast-strip.js"', b'src="/coast-strip.js"'),
    ):
        data = data.replace(a, b)
    return _apply_preview_dateline(_apply_chrome(data))


def _public_home_html(region_id: str | None = None, preview: bool = False) -> bytes:
    """Public homepage: Chartroom Folio (masthead A, conditions first, credited photo, rail)."""
    return _folio_home_html(region_id, gated=False, assemble_preview=preview)


# Private photo-led homepage concepts. Final = Magazine layout on masthead A.
# The public homepage uses the same photos via /featured/.
HOME_CONCEPTS = ("cinematic", "magazine", "final")
HOME_DIR = ROOT / "preview" / "home"
HOME_PHOTOS_DIR = HOME_DIR / "photos"
HOME_PHOTOS_JSON = ROOT / "data" / "featured-photos.json"
_HOME_PHOTO_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*-w(?:800|1280|1600|1920)\.(?:avif|webp)$")


def _load_featured_photos() -> list[dict]:
    raw = json.loads(HOME_PHOTOS_JSON.read_text(encoding="utf-8"))
    return list(raw.get("photos") or [])


def _featured_photo(photo_id: str | None = None) -> dict:
    """Pinned/default photograph, or a stable per-day pick. Optional id override for the preview."""
    photo_list = _load_featured_photos()
    if not photo_list:
        raise RuntimeError("featured photos list is empty")
    by_id = {p.get("id"): p for p in photo_list if p.get("id")}
    if photo_id and photo_id in by_id:
        return by_id[photo_id]
    for item in photo_list:
        if item.get("default") or item.get("pinned"):
            return item
    now = datetime.now(ZoneInfo("America/New_York"))
    return photo_list[now.timetuple().tm_yday % len(photo_list)]


def _home_photo_band_html(home: str, photo: dict, public: bool = False) -> bytes:
    src = str(photo.get("src") or ("/preview/home/photos/" + str(photo.get("id") or "")))
    if public:
        src = src.replace("/preview/home/photos/", "/featured/")
    widths = [int(w) for w in (photo.get("widths") or [800, 1280]) if int(w) > 0]
    if 800 not in widths:
        widths = [800] + widths

    def srcset(ext: str) -> str:
        return ", ".join("%s-w%s.%s %sw" % (src, w, ext, w) for w in widths)

    alt = html.escape(str(photo.get("alt") or ""), quote=True)
    credit_line = html.escape(str(photo.get("credit_line") or photo.get("credit") or "Photograph"))
    source_url = html.escape(str(photo.get("source_url") or ""), quote=True)
    kicker = html.escape(str(photo.get("kicker") or ""))
    title = html.escape(str(photo.get("title") or ""))
    focal = html.escape(str(photo.get("focal") or "50% 50%"), quote=True)
    iw = int(photo.get("width") or 1600)
    ih = int(photo.get("height") or 1067)
    sizes = "(min-width: 900px) 58vw, 100vw" if home == "magazine" else "100vw"
    fallback = "%s-w800.webp" % src
    markup = """<section class="home-photo-band" aria-label="Featured photograph">
  <div class="home-photo-frame">
    <picture>
      <source type="image/avif" srcset="%s" sizes="%s">
      <source type="image/webp" srcset="%s" sizes="%s">
      <img src="%s" alt="%s" width="%d" height="%d" fetchpriority="high" decoding="async" style="object-position:%s">
    </picture>
  </div>
  <div class="home-photo-copy">
    <p class="home-photo-kicker">%s</p>
    <p class="home-photo-title">%s</p>
    <p class="home-photo-credit"><a href="%s" rel="noopener noreferrer">%s</a></p>
    <a class="home-photo-jump" href="#conditions">Today’s conditions</a>
  </div>
</section>
""" % (srcset("avif"), sizes, srcset("webp"), sizes, fallback, alt, iw, ih, focal, kicker, title, source_url, credit_line)
    return markup.encode("utf-8")


def _home_layout(home: str) -> str:
    return "magazine" if home == "final" else home


def _home_masthead(home: str, mast: str | None) -> str:
    if mast in MASTHEAD_CONCEPTS:
        return mast
    return "a" if home == "final" else "c"


def _home_preview_dock(home: str, photo: dict, photo_list: list[dict], mast: str) -> str:
    pid = html.escape(str(photo.get("id") or ""), quote=True)
    views = (
        ("final", "Final", "/preview/home?c=final&photo=%s" % pid),
        ("cinematic", "Cinematic", "/preview/home?c=cinematic&photo=%s" % pid),
        ("magazine", "Magazine (C)", "/preview/home?c=magazine&photo=%s" % pid),
    )
    view_links = []
    for key, label, href in views:
        on = ' class="is-on"' if key == home else ""
        view_links.append('<a href="%s"%s>%s</a>' % (href, on, label))
    mast_links = []
    for key, label in (("a", "Masthead A"), ("b", "Masthead B"), ("c", "Masthead C")):
        mast_links.append('<a href="/preview/masthead?c=%s">%s</a>' % (key, label))
    photo_links = []
    for item in photo_list:
        item_id = str(item.get("id") or "")
        on = ' class="is-on"' if item_id == photo.get("id") else ""
        label = html.escape(str(item.get("title") or item_id))
        href = "/preview/home?c=%s&m=%s&photo=%s" % (home, mast, html.escape(item_id, quote=True))
        photo_links.append('<a href="%s"%s>%s</a>' % (href, on, label))
    return """<div id="mast-preview-dock" class="mast-preview-dock" hidden>
  <span class="pv-lab">Private preview</span>
  %s
  <span class="pv-sep" aria-hidden="true">·</span>
  %s
  <span class="pv-sep" aria-hidden="true">·</span>
  %s
  <button type="button" id="mast-replay">Replay</button>
</div>
<script>
(function(){
  var dock = document.getElementById("mast-preview-dock");
  if (!dock) return;
  dock.hidden = false;
  var c = document.documentElement.getAttribute("data-concept") || "a";
  var btn = document.getElementById("mast-replay");
  if (!btn) return;
  btn.addEventListener("click", function(){
    var key = "cb-mast-reveal-" + c;
    try { sessionStorage.removeItem(key); } catch (e) {}
    var html = document.documentElement;
    html.classList.remove("mast-play");
    void html.offsetWidth;
    html.classList.add("mast-play");
    document.querySelectorAll(".wave-swell, .wave-settle, .wave-glint, .mast-sheen").forEach(function(el){
      var prev = el.style.animation;
      el.style.animation = "none";
      void el.offsetWidth;
      el.style.animation = prev;
    });
  });
})();
</script>
""" % ("\n  ".join(view_links), "\n  ".join(photo_links), "\n  ".join(mast_links))


def _home_preview_html(home: str, shot: bool = False, photo_id: str | None = None, mast: str | None = None) -> bytes:
    """Homepage photo preview. Comparison routes stay private; the public homepage uses _public_home_html."""
    if home not in HOME_CONCEPTS:
        home = "final"
    layout = _home_layout(home)
    mast = _home_masthead(home, mast)
    photo_list = _load_featured_photos()
    photo = _featured_photo(photo_id)
    dock = None if shot else _home_preview_dock(home, photo, photo_list, mast)
    extra = b' data-home="%s"' % layout.encode("ascii")
    if home == "final":
        extra += b" data-final"
    data = _masthead_preview_html(
        mast,
        shot=shot,
        dock=dock,
        css_files=[MASTHEAD_DIR / "masthead.css", HOME_DIR / "home.css"],
        extra_attrs=extra,
    )
    band = _home_photo_band_html(layout, photo)
    mid = data.find(_MASTHEAD_META)
    if mid < 0:
        raise RuntimeError("home preview: unexpected index.html shape")
    data = data[:mid] + band + b"\n    " + data[mid:]
    return data


IDENTITY_DIR = ROOT / "preview" / "identity"
_IDENTITY_COND_END = b'    </section>\n\n    <section class="panel tide-panel" id="tide-search"'
_IDENTITY_MOTTO_NEEDLE = (
    b'        <span class="mast-sheen"></span>\n      </div>\n    </div>\n  </div>\n</header>'
)
_IDENTITY_MOTTO_HTML = (
    b'        <span class="mast-sheen"></span>\n      </div>\n'
    b'      <p class="mast-motto">Know the Water. Live the Coast.</p>\n'
    b'    </div>\n  </div>\n</header>'
)
_IDENTITY_DOCK = """<div id="identity-preview-dock" class="id-preview-dock" hidden>
  <span class="pv-lab">Private preview</span>
  <span>Chartroom Folio</span>
  <a href="/preview">Hub</a>
  <button type="button" id="mast-replay">Replay wave</button>
</div>
<script>
(function(){
  var dock = document.getElementById("identity-preview-dock");
  if (!dock) return;
  dock.hidden = false;
  var btn = document.getElementById("mast-replay");
  if (!btn) return;
  btn.addEventListener("click", function(){
    var c = document.documentElement.getAttribute("data-concept") || "a";
    var key = "cb-mast-reveal-" + c;
    try { sessionStorage.removeItem(key); } catch (e) {}
    var html = document.documentElement;
    html.classList.remove("mast-play");
    void html.offsetWidth;
    html.classList.add("mast-play");
    document.querySelectorAll(".wave-swell, .wave-settle, .mast-sheen").forEach(function(el){
      var prev = el.style.animation;
      el.style.animation = "none";
      void el.offsetWidth;
      el.style.animation = prev;
    });
  });
})();
</script>
"""


def _folio_photo_html(photo: dict) -> bytes:
    """Slim credited strip for the identity preview. Lazy-loaded; never the LCP."""
    src = str(photo.get("src") or ("/preview/home/photos/" + str(photo.get("id") or "")))
    src = src.replace("/preview/home/photos/", "/featured/")
    widths = [int(w) for w in (photo.get("widths") or [800, 1280]) if int(w) > 0]
    if 800 not in widths:
        widths = [800] + widths

    def srcset(ext: str) -> str:
        return ", ".join("%s-w%s.%s %sw" % (src, w, ext, w) for w in widths)

    alt = html.escape(str(photo.get("alt") or ""), quote=True)
    credit_line = html.escape(str(photo.get("credit_line") or photo.get("credit") or "Photograph"))
    source_url = html.escape(str(photo.get("source_url") or ""), quote=True)
    kicker = html.escape(str(photo.get("kicker") or ""))
    title = html.escape(str(photo.get("title") or ""))
    focal = html.escape(str(photo.get("focal") or "50% 50%"), quote=True)
    iw = int(photo.get("width") or 1600)
    ih = int(photo.get("height") or 1067)
    sizes = "(min-width: 761px) 42vw, 100vw"
    fallback = "%s-w800.webp" % src
    markup = """<section class="folio-photo" aria-label="Featured photograph">
  <div class="folio-photo-frame">
    <picture>
      <source type="image/avif" srcset="%s" sizes="%s">
      <source type="image/webp" srcset="%s" sizes="%s">
      <img src="%s" alt="%s" width="%d" height="%d" loading="lazy" decoding="async" style="object-position:%s">
    </picture>
  </div>
  <div class="folio-photo-copy">
    <p class="folio-photo-kicker">%s</p>
    <p class="folio-photo-title">%s</p>
    <p class="folio-photo-credit"><a href="%s" rel="noopener noreferrer">%s</a></p>
  </div>
</section>
""" % (srcset("avif"), sizes, srcset("webp"), sizes, fallback, alt, iw, ih, focal, kicker, title, source_url, credit_line)
    return markup.encode("utf-8")


def _folio_rail_html() -> bytes:
    """One editorial card system. Links only to existing pages; salt and fresh equally."""
    return """<section class="folio-rail" aria-labelledby="folio-rail-h">
  <p class="folio-rail-kicker">From the rivers to the sounds to the sea</p>
  <h2 class="folio-rail-title" id="folio-rail-h">Life on the water</h2>
  <ul class="folio-cards">
    <li>
      <a class="folio-card" href="/catch-wall">
        <p class="folio-card-k">Catch Wall</p>
        <p class="folio-card-title">Catches from the coast</p>
        <p class="folio-card-dek">Community photos from saltwater days on the line.</p>
      </a>
    </li>
    <li>
      <a class="folio-card" href="/coastal-life">
        <p class="folio-card-k">Coastal Life</p>
        <p class="folio-card-title">Life along the water</p>
        <p class="folio-card-dek">Moments from the inlets, sounds, and beaches.</p>
      </a>
    </li>
    <li>
      <a class="folio-card" href="/lake">
        <p class="folio-card-k">Rivers and lakes</p>
        <p class="folio-card-title">Falls Lake and the Neuse</p>
        <p class="folio-card-dek">Lake level, dam release, and river stage — the same care as the coast.</p>
      </a>
    </li>
    <li>
      <a class="folio-card" href="/brief?region=crystal-coast" id="folio-brief">
        <p class="folio-card-k">Morning Brief</p>
        <p class="folio-card-title">Today’s briefing</p>
        <p class="folio-card-dek">The daily read for saltwater and freshwater regions.</p>
      </a>
    </li>
  </ul>
  <p class="folio-rail-note">Techniques, local features, and food will use this same card.</p>
</section>
""".encode("utf-8")



def _folio_water_cards() -> list[dict]:
    """Credited photographs for On the Water. Skip the pinned Bodie strip already above the map."""
    cards = []
    for photo in _load_featured_photos():
        if photo.get("id") == "bodie-sunrise" or photo.get("pinned") or photo.get("default"):
            continue
        cards.append(photo)
    return cards


def _folio_water_html() -> bytes:
    """Editorial discovery below the map: one featured photo, then compact credited cards."""
    photos = _folio_water_cards()
    if not photos:
        return b""

    items = []
    for i, photo in enumerate(photos):
        src = str(photo.get("src") or "").replace("/preview/home/photos/", "/featured/")
        alt = html.escape(str(photo.get("alt") or ""), quote=True)
        title = html.escape(str(photo.get("title") or ""))
        kicker = html.escape(str(photo.get("kicker") or "Place"))
        credit = html.escape(str(photo.get("credit_line") or photo.get("credit") or "Photograph"))
        url = html.escape(str(photo.get("source_url") or ""), quote=True)
        focal = html.escape(str(photo.get("focal") or "50% 50%"), quote=True)
        iw = int(photo.get("width") or 1600)
        ih = int(photo.get("height") or 1067)
        srcset_avif = "%s-w800.avif 800w, %s-w1280.avif 1280w" % (src, src)
        srcset_webp = "%s-w800.webp 800w, %s-w1280.webp 1280w" % (src, src)
        credit_html = (
            '<a href="%s" rel="noopener noreferrer">%s</a>' % (url, credit) if url else credit
        )
        featured_cls = " is-featured" if i == 0 else ""
        sizes = "(min-width: 1100px) 60vw, 100vw" if i == 0 else "120px"
        items.append("""<li>
  <article class="folio-water-card%s">
    <div class="folio-water-frame">
      <picture>
        <source type="image/avif" srcset="%s" sizes="%s">
        <source type="image/webp" srcset="%s" sizes="%s">
        <img src="%s-w800.webp" alt="%s" width="%d" height="%d" loading="lazy" decoding="async" style="object-position:%s">
      </picture>
    </div>
    <div class="folio-water-copy">
      <p class="folio-water-k">Place · %s</p>
      <h3>%s</h3>
      <p class="folio-water-credit">%s</p>
    </div>
  </article>
</li>
""" % (featured_cls, srcset_avif, sizes, srcset_webp, sizes, src, alt, iw, ih, focal, kicker, title, credit_html))

    markup = """<section class="folio-water" aria-labelledby="folio-water-h">
  <p class="folio-water-kicker">From the rivers to the sounds to the sea</p>
  <h2 class="folio-water-title" id="folio-water-h">On the water</h2>
  <p class="folio-water-dek">Places, catches, stories, and water culture from the coast and the inland rivers.</p>
  <ul class="folio-water-grid">
    %s
  </ul>
</section>
""" % "".join(items)
    return markup.encode("utf-8")


def _folio_fold_alerts(data: bytes) -> bytes:
    """Collapse long county/zone lists; keep event names, until-lines, and the NWS link."""

    def fold(m: re.Match[bytes]) -> bytes:
        head, meta = m.group(1), m.group(2).decode("utf-8")
        if " · " not in meta:
            return m.group(0)
        until, zones = meta.split(" · ", 1)
        parts = [z.strip() for z in zones.split(";") if z.strip()]
        if len(parts) < 2 and len(zones) < 28:
            return m.group(0)
        label = "%d zone%s" % (len(parts), "" if len(parts) == 1 else "s")
        return (
            b'<div class="al-item">'
            + head
            + b'<span class="al-meta">'
            + html.escape(until).encode("utf-8")
            + b"</span>"
            + b'<details class="al-zones"><summary>'
            + html.escape(label).encode("utf-8")
            + b"</summary><p>"
            + html.escape(zones).encode("utf-8")
            + b"</p></details></div>"
        )

    return re.sub(
        br'<div class="al-item">(<span class="al-dot"></span><span class="al-ev">[^<]*</span>)'
        br'<span class="al-meta">([^<]*)</span></div>',
        fold,
        data,
    )


_FOLIO_MAP_END = b'<p class="fine" id="map-status">Map has not loaded yet.</p>\n    </section>'

_FOLIO_UI_JS = """<script>
(function(){
  if (document.documentElement.getAttribute("data-home") !== "folio") return;

  function wrapAlerts(){
    var box = document.getElementById("dash-alert");
    if (!box) return;
    box.querySelectorAll(".al-item").forEach(function(item){
      if (item.querySelector("details.al-zones")) return;
      var meta = item.querySelector(".al-meta");
      if (!meta) return;
      var raw = (meta.textContent || "").trim();
      var cut = raw.indexOf(" · ");
      if (cut < 0) return;
      var until = raw.slice(0, cut).trim();
      var zones = raw.slice(cut + 3).trim();
      if (!zones) return;
      var parts = zones.split(";").map(function(s){ return s.trim(); }).filter(Boolean);
      if (parts.length < 2 && zones.length < 28) return;
      meta.textContent = until;
      var det = document.createElement("details");
      det.className = "al-zones";
      var sum = document.createElement("summary");
      sum.textContent = parts.length + (parts.length === 1 ? " zone" : " zones");
      var p = document.createElement("p");
      p.textContent = zones;
      det.appendChild(sum);
      det.appendChild(p);
      meta.insertAdjacentElement("afterend", det);
    });
  }

  function decorateInstruments(){
    document.querySelectorAll("#conditions .inst").forEach(function(el){
      if (el.querySelector(".folio-ticks")) return;
      var t = document.createElement("span");
      t.className = "folio-ticks";
      t.setAttribute("aria-hidden", "true");
      el.appendChild(t);
    });
  }

  wrapAlerts();
  decorateInstruments();
  document.addEventListener("cb:conditions", function(){ wrapAlerts(); decorateInstruments(); });
  if ("MutationObserver" in window) {
    var root = document.getElementById("conditions");
    if (root) new MutationObserver(decorateInstruments).observe(root, { childList: true, subtree: true });
  }
})();
</script>
""".encode("utf-8")

def _folio_home_html(
    region_id: str | None = None,
    *,
    gated: bool = False,
    photo_id: str | None = None,
    shot: bool = False,
    assemble_preview: bool = False,
) -> bytes:
    """Chartroom Folio homepage, shared by public / and cookie-gated /preview/identity."""
    src = (ROOT / "index.html").read_bytes()
    header = (MASTHEAD_DIR / "header.html").read_bytes().strip()
    start = src.find(b'<header class="site"')
    mid = src.find(_MASTHEAD_META)
    if start < 0 or mid < 0 or mid < start:
        raise RuntimeError("folio home: unexpected index.html shape")
    data = src[:start] + header + b"\n\n    " + src[mid:]
    attrs = b'<html lang="en" data-tiles="v2" data-concept="a" data-home="folio">'
    if gated:
        attrs = b'<html lang="en" data-tiles="v2" data-preview data-concept="a" data-home="folio">'
    data = data.replace(b'<html lang="en" data-tiles="v2">', attrs, 1)
    inject = b""
    if gated:
        inject += b'  <meta name="robots" content="noindex, nofollow">\n'
    inject += b"  " + _MASTHEAD_PLAY
    # Preload the wordmark face so the nameplate is ready without a swap.
    inject += (
        b'  <link rel="preload" href="/fonts/fraunces-var.woff2" as="font" '
        b'type="font/woff2" crossorigin>\n'
    )
    needle = b'  <link rel="stylesheet" href="styles.css">\n'
    if needle not in data:
        raise RuntimeError("folio home: stylesheet link missing")
    data = data.replace(needle, needle + inject, 1)
    if b'class="mast-motto"' not in data:
        if _IDENTITY_MOTTO_NEEDLE not in data:
            raise RuntimeError("folio home: mast-wave close missing")
        data = data.replace(_IDENTITY_MOTTO_NEEDLE, _IDENTITY_MOTTO_HTML, 1)
    data = data.replace(
        b'<p class="eyebrow">Live marine instruments</p>',
        b'<p class="eyebrow">Today\xe2\x80\x99s conditions</p>',
        1,
    )
    data = data.replace(
        b'<div class="map-placeholder skeleton" id="map-placeholder">Scroll to load the map\xe2\x80\xa6</div>',
        b'<div class="map-placeholder skeleton" id="map-placeholder">Map will load when you scroll here.</div>',
        1,
    )
    for a, b_ in (
        (b'href="styles.css"', b'href="/styles.css"'),
        (b'src="region-nav.js"', b'src="/region-nav.js"'),
        (b'src="dashboard.js"', b'src="/dashboard.js"'),
        (b'src="app.js"', b'src="/app.js"'),
        (b'src="coast-strip.js"', b'src="/coast-strip.js"'),
    ):
        data = data.replace(a, b_)
    data = _apply_preview_dateline(_apply_chrome(data))
    data = homepage_boot.inject(data, region_id, preview=assemble_preview)
    photo = _featured_photo(photo_id)
    strip = _folio_photo_html(photo) + b"\n    " + _folio_rail_html() + b"\n\n"
    mid = data.find(_IDENTITY_COND_END)
    if mid < 0:
        raise RuntimeError("folio home: conditions/tide boundary missing")
    data = data[:mid] + b"    " + strip + data[mid:]
    map_end = data.find(_FOLIO_MAP_END)
    if map_end < 0:
        raise RuntimeError("folio home: map section end missing")
    map_end += len(_FOLIO_MAP_END)
    data = data[:map_end] + b"\n    " + _folio_water_html() + b"\n" + data[map_end:]
    data = _folio_fold_alerts(data)
    data = data.replace(b"</body>", _FOLIO_UI_JS + b"</body>", 1)
    if gated and not shot:
        data = data.replace(b"</body>", _IDENTITY_DOCK.encode("utf-8") + b"\n</body>", 1)
    return data


def _identity_preview_html(region_id: str | None = None, photo_id: str | None = None, shot: bool = False) -> bytes:
    """Cookie-gated Chartroom Folio homepage. Same design as public /."""
    pv = bool(region_id and conditions.is_preview_salt_region(region_id))
    return _folio_home_html(
        region_id, gated=True, photo_id=photo_id, shot=shot, assemble_preview=pv
    )


def _folio_chrome(current: str) -> bytes:
    """The public Folio nameplate, motto, region picker, and site tabs."""
    header = (MASTHEAD_DIR / "header.html").read_bytes().strip()
    if _IDENTITY_MOTTO_NEEDLE not in header:
        raise RuntimeError("folio chrome: motto needle missing")
    header = header.replace(_IDENTITY_MOTTO_NEEDLE, _IDENTITY_MOTTO_HTML, 1)
    header = header.replace(b' aria-current="page"', b"", 1)
    tab = {
        "home": (
            b'<a href="/">Conditions</a>',
            b'<a href="/" aria-current="page">Conditions</a>',
        ),
        "brief": (
            b'<a href="/brief?region=crystal-coast" id="nav-brief">Morning Brief</a>',
            b'<a href="/brief?region=crystal-coast" id="nav-brief" aria-current="page">Morning Brief</a>',
        ),
        "catch-wall": (
            b'<a href="/catch-wall">Catch Wall</a>',
            b'<a href="/catch-wall" aria-current="page">Catch Wall</a>',
        ),
        "coastal-life": (
            b'<a href="/coastal-life">Coastal Life</a>',
            b'<a href="/coastal-life" aria-current="page">Coastal Life</a>',
        ),
    }.get(current)
    if tab:
        header = header.replace(tab[0], tab[1], 1)
    if current == "brief":
        toggle = (
            b'<button type="button" id="theme-toggle" class="theme-toggle" '
            b'aria-pressed="false" aria-label="Switch to dark mode">Dark mode</button>'
        )
        if toggle not in header:
            raise RuntimeError("folio chrome: theme toggle missing")
        print_btn = (
            b'<button type="button" class="mb-print" onclick="window.print()">'
            b"Print</button>\n      "
        )
        header = header.replace(toggle, print_btn + toggle, 1)
    return header


def _end_of_div(data: bytes, id_attr: bytes) -> int | None:
    i = data.find(id_attr)
    if i < 0:
        return None
    open_lt = data.rfind(b"<div", 0, i)
    if open_lt < 0:
        return None
    pos = open_lt
    depth = 0
    while pos < len(data):
        if data.startswith(b"</div>", pos):
            depth -= 1
            if depth == 0:
                return pos + len(b"</div>")
            pos += 6
        elif data.startswith(b"<div", pos):
            nxt = data[pos + 4 : pos + 5]
            if nxt in (b" ", b">", b"\n", b"\t", b"\r"):
                depth += 1
            pos += 4
        else:
            pos += 1
    return None


def _install_folio_chrome(data: bytes, current: str) -> bytes:
    """Replace a page header with the single Folio masthead and compact nav.

    Picker IDs (#region-nav, #rn-btn, #rn-menu, #nav-brief) come from
    header.html and are left unchanged. Does not edit brief.py.
    """
    chrome = _folio_chrome(current)
    start = data.find(b'<header class="site"')
    end = _end_of_div(data, b'id="compact-bar"')
    if start >= 0 and end is not None and end > start:
        return data[:start] + chrome + data[end:]
    mb = data.find(b'<header class="mb-top">')
    if mb >= 0:
        close = data.find(b"</header>", mb)
        if close >= 0:
            return data[:mb] + chrome + data[close + len(b"</header>") :]
    raise RuntimeError("folio chrome: header not found")


def _set_html_attr(data: bytes, name: bytes, value: bytes) -> bytes:
    """Add or replace a single html attribute without touching the rest."""
    m = re.search(br"<html\b([^>]*)>", data)
    if not m:
        return data
    attrs = m.group(1)
    pat = re.compile(br'\s' + re.escape(name) + br'="[^"]*"')
    if pat.search(attrs):
        attrs = pat.sub(b' ' + name + b'="' + value + b'"', attrs, count=1)
    else:
        attrs = attrs + b' ' + name + b'="' + value + b'"'
    return data[:m.start()] + b"<html" + attrs + b">" + data[m.end():]


_FRAUNCES_PRELOAD = (
    b'<link rel="preload" href="/fonts/fraunces-var.woff2" as="font" '
    b'type="font/woff2" crossorigin>'
)
_BRIEF_FONT_PRELOAD_RE = re.compile(
    br'[ \t]*<link rel="preload" href="/fonts/(?:source-sans-3-var|barlow-condensed-600|fraunces-var|fraunces-italic-var)\.woff2"[^>]*>\s*'
)


def _slim_brief_fonts(data: bytes) -> bytes:
    """Only the roman Fraunces wordmark is preloaded. Italic and body faces
    stay font-display: optional with metric fallbacks in brief.css."""
    data = _BRIEF_FONT_PRELOAD_RE.sub(b"", data)
    if _FRAUNCES_PRELOAD not in data:
        data = data.replace(b"<head>", b"<head>\n" + _FRAUNCES_PRELOAD, 1)
    return data


def _ensure_script(data: bytes, src: bytes) -> bytes:
    tag = b'<script src="' + src + b'" defer></script>'
    if tag in data or (b'src="' + src + b'"') in data:
        return data
    return data.replace(b"</body>", tag + b"\n</body>", 1)


_FOLIO_CHROME_CSS_LINK = b'<link rel="stylesheet" href="/folio-chrome.css">\n'


def _link_folio_chrome_css(data: bytes) -> bytes:
    """Load Folio chrome off the brief LCP path. Reserved heights are in brief.css."""
    if b'href="/folio-chrome.css"' in data:
        return data
    needle = b'<link rel="stylesheet" href="/brief.css">'
    if needle not in data:
        raise RuntimeError("public brief: brief.css link missing")
    return data.replace(needle, needle + b"\n  " + _FOLIO_CHROME_CSS_LINK, 1)


def _paint_public_brief(data: bytes) -> bytes:
    """Presentation-only Folio chrome on public /brief. brief.page() is unchanged."""
    data = _install_folio_chrome(data, "brief")
    data = _set_html_attr(data, b"data-concept", b"a")
    data = _slim_brief_fonts(data)
    data = _link_folio_chrome_css(data)
    if b'href="/styles.css"' in data or b'href="styles.css"' in data:
        raise RuntimeError("public brief must not load styles.css")
    data = _apply_preview_dateline(_apply_chrome(data))
    if b"cb-mast-reveal" not in data:
        data = data.replace(b"</head>", b"  " + _MASTHEAD_PLAY + b"</head>", 1)
    for src in (b"/region-nav.js", b"/brief-link.js", b"/identity.js"):
        data = _ensure_script(data, src)
    return data


_PUB_TOOLS_FROM = (
    '<button type="button" class="mb-print" onclick="window.print()">Print</button>\n'
    '      <button type="button" id="theme-toggle" class="theme-toggle" aria-pressed="false" aria-label="Switch to dark mode">Dark mode</button>'
)


def _polish_public_brief(data: bytes) -> bytes:
    """Presentation only: the approved brief-polish.css look on public /brief pages.
    Reuses brief_preview's styling helpers (icon print/theme buttons with the same labels,
    reading times folded into a details panel, the polish CSS). brief.page(), the brief's
    words, order, data and archive are untouched; the preview-only banner, region select
    and Captain's Take move are not applied. Any failure is logged and the unpolished
    page is served."""
    try:
        import brief_preview
        out = data.decode("utf-8")
        if '<body class="mb-page">' not in out:
            raise RuntimeError("public brief: body class missing")
        out = out.replace('<body class="mb-page">', '<body class="mb-page mb-polish">', 1)
        css = brief_preview._POLISH_CSS.read_text(encoding="utf-8")
        css = re.sub(r"/\*.*?\*/", "", css, flags=re.S).replace("body.mb-preview-brief", "body.mb-polish")
        if "mb-preview-brief" in css:
            raise RuntimeError("public brief: unexpected polish selector")
        out = out.replace("</head>", '<style id="brief-style">\n%s\n</style>\n</head>' % css.replace("</", "<\\/"), 1)
        out = brief_preview._compact_tools(out)
        # Public pages carry the two tool buttons in the Folio masthead row: same icon buttons,
        # same accessible names ("Print", "Switch to dark mode"), as on the approved preview.
        icons = brief_preview._TOOLS_TO.split("\n")[1:-1]
        if _PUB_TOOLS_FROM in out:
            out = out.replace(_PUB_TOOLS_FROM, "\n".join(l.strip() for l in icons), 1)
            out = out.replace('    btn.textContent=dark?"Light mode":"Dark mode";\n', "", 1)
        # a11y (axe on main): the Folio compact bar sat outside any landmark, and the visible
        # "Region" label was not part of the region button's accessible name (region-nav.js
        # sets aria-label to the region name; data-name-prefix makes it "Region: <name>" on
        # brief pages only). Markup attributes only; no visible change.
        out = out.replace('<div class="compact-bar mast-nav" id="compact-bar">',
                          '<div class="compact-bar mast-nav" id="compact-bar" role="region" aria-label="Region and sections">', 1)
        out = out.replace('<button type="button" class="rn-btn" id="rn-btn"', '<button type="button" class="rn-btn" id="rn-btn" data-name-prefix="Region: "', 1)
        out = brief_preview._wrap_reading_times(out)
        if brief_preview._DETAILS_SCRIPT_FROM in out:
            out = out.replace(brief_preview._DETAILS_SCRIPT_FROM, brief_preview._DETAILS_SCRIPT_TO, 1)
        return out.encode("utf-8")
    except Exception as e:
        sys.stderr.write("public brief polish failed, serving unpolished page: %r\n" % (e,))
        return data


_LAKE_ALERT_JS = """<script>
(function(){
  function wrapAlerts(){
    var box = document.getElementById("fw-alert");
    if (!box) return;
    box.querySelectorAll(".al-item").forEach(function(item){
      if (item.querySelector("details.al-zones")) return;
      var meta = item.querySelector(".al-meta");
      if (!meta) return;
      var raw = (meta.textContent || "").trim();
      var cut = raw.indexOf(" \u00b7 ");
      if (cut < 0) return;
      var until = raw.slice(0, cut).trim();
      var zones = raw.slice(cut + 3).trim();
      if (!zones) return;
      var parts = zones.split(";").map(function(s){ return s.trim(); }).filter(Boolean);
      if (parts.length < 2 && zones.length < 28) return;
      meta.textContent = until;
      var det = document.createElement("details");
      det.className = "al-zones";
      var sum = document.createElement("summary");
      sum.textContent = parts.length + (parts.length === 1 ? " zone" : " zones");
      var p = document.createElement("p");
      p.textContent = zones;
      det.appendChild(sum);
      det.appendChild(p);
      meta.insertAdjacentElement("afterend", det);
    });
  }
  wrapAlerts();
  var box = document.getElementById("fw-alert");
  if (box && "MutationObserver" in window) {
    new MutationObserver(wrapAlerts).observe(box, { childList: true, subtree: true });
  }
})();
</script>
""".encode("utf-8")



_LAKE_REGIONS = {b"falls-lake", b"jordan-lake", b"neuse-river", b"cape-fear-river"}


def _brief_nav_for(data: bytes, rid: str | None) -> bytes:
    """Server-render the header Morning Brief href for the page's region (brief-link.js keeps it in
    step after a picker change). Own brief when published, else that region's unavailable page."""
    if not rid:
        return data
    tgt = site_chrome.brief_target(rid)[0].encode("ascii", "ignore")
    data = data.replace(b'<a href="/brief?region=crystal-coast" id="nav-brief">',
                        b'<a href="/brief?region=' + tgt + b'" id="nav-brief">', 1)
    # The Map page's "Morning Brief" rail card follows the same rule.
    return data.replace(b'<a class="folio-card" href="/brief?region=crystal-coast" id="folio-brief">',
                        b'<a class="folio-card" href="/brief?region=' + tgt + b'" id="folio-brief">', 1)


def _paint_public_lake(data: bytes, region: str = "falls-lake") -> bytes:
    """Presentation-only Folio chrome and alert folding on public /lake."""
    data = _install_folio_chrome(data, "lake")
    data = _set_html_attr(data, b"data-concept", b"a")
    data = _set_html_attr(data, b"data-page", b"lake")
    rid = (region or "falls-lake").strip().lower().encode("ascii", "ignore")
    if rid not in _LAKE_REGIONS:
        rid = b"falls-lake"
    data = _set_html_attr(data, b"data-region", rid)
    data = _brief_nav_for(data, rid.decode("ascii"))
    # Server-rendered <title> follows the region (it was always "Falls Lake"; audit item 6).
    lake_name = {b"falls-lake": b"Falls Lake", b"jordan-lake": b"Jordan Lake", b"neuse-river": b"Neuse River",
                 b"cape-fear-river": b"Cape Fear River"}.get(rid, b"Falls Lake")
    data = data.replace(b"<title>Falls Lake \xc2\xb7 The Coastal Brief</title>",
                        b"<title>" + lake_name + b" \xc2\xb7 The Coastal Brief</title>", 1)
    if rid == b"cape-fear-river":
        data = data.replace(
            b'var n={ "falls-lake":"Falls Lake"',
            b'var n={ "cape-fear-river":"Cape Fear River","falls-lake":"Falls Lake"',
            1,
        )
        chip = (
            b'<a href="/lake?region=cape-fear-river">Cape Fear River</a>\n'
        )
        data = data.replace(
            b'<a href="/lake?region=neuse-river">Neuse River</a>',
            b'<a href="/lake?region=neuse-river">Neuse River</a>\n            ' + chip,
            1,
        )
        badge = (
            b'<p class="fw-meta" style="margin:8px 0 0"><span class="badge">Private preview</span> '
            b'Cookie-gated. Not on the public site, sitemap, or Morning Brief schedule.</p>\n        '
        )
        data = data.replace(
            b'<p class="dash-sub" id="fw-sub">',
            badge + b'<p class="dash-sub" id="fw-sub">',
            1,
        )
    data = _apply_preview_dateline(_apply_chrome(data))
    if b"cb-mast-reveal" not in data:
        data = data.replace(b"</head>", b"  " + _MASTHEAD_PLAY + b"</head>", 1)
    if b"details.al-zones" not in data:
        data = data.replace(b"</body>", _LAKE_ALERT_JS + b"\n</body>", 1)
    return data




def _catch_wall_critical_css() -> bytes:
    """Inline Folio chrome and Catch Wall CSS to avoid extra render-blocking requests."""
    chunks = []
    for name in ("folio-chrome.css", "catch-wall-public.css"):
        path = ROOT / name
        if path.is_file():
            chunks.append(path.read_text(encoding="utf-8"))
    css = "\n".join(chunks).replace("</", "<\\/")
    return b'  <style id="catch-wall-css">\n' + css.encode("utf-8") + b"\n  </style>\n"


def _paint_public_catch_wall(data: bytes, page: str, water: str = "all") -> bytes:
    """Server-render public /catch-wall, /coastal-life, and /photos from approved photos."""
    view = {"catch-wall": "catch", "coastal-life": "life", "photos": "all"}.get(page, "catch")
    water = catch_wall_public.parse_water(water)
    model = catch_wall_public.assemble(view, water)
    data = _install_folio_chrome(data, page)
    data = _set_html_attr(data, b"data-home", b"folio")
    data = _set_html_attr(data, b"data-concept", b"a")
    data = _set_html_attr(data, b"data-catch-wall", b"")
    data = re.sub(
        br'[ \t]*<link rel="preload" href="/fonts/fraunces-italic-var\.woff2"[^>]*>\s*',
        b"",
        data,
        count=1,
    )
    # LCP hints must precede font preloads and stylesheets, as on the v2 preview.
    hints = catch_wall_public.featured_preload_html(model).encode("utf-8")
    viewport = b'<meta name="viewport" content="width=device-width, initial-scale=1">'
    if hints and viewport in data:
        data = data.replace(viewport, viewport + b"\n  " + hints.strip(), 1)
    elif hints:
        data = data.replace(b"</head>", hints + b"</head>", 1)
    needle = b'<link rel="stylesheet" href="/styles.css">'
    if needle not in data:
        raise RuntimeError("public catch wall: styles.css link missing")
    # One extra render-blocking file is styles.css; inline Folio and wall CSS
    # so the page does not pay two more HTTP/1.0 round trips before first paint.
    if b'id="catch-wall-css"' not in data:
        data = data.replace(needle, needle + b"\n" + _catch_wall_critical_css(), 1)
    if b"cb-mast-reveal" not in data:
        data = data.replace(b"</head>", b"  " + _MASTHEAD_PLAY + b"</head>", 1)
    start = data.find(b'<div class="gal-head">')
    end = data.find(b"</main>")
    if start < 0 or end < start:
        raise RuntimeError("public catch wall: gallery block missing")
    data = data[:start] + catch_wall_public.main_html(model).encode("utf-8") + data[end:]
    boot = catch_wall_public.boot_script(model).encode("utf-8")
    old_js = b'  <script src="/gallery.js" defer></script>'
    new_js = boot + b'  <script src="/catch-wall-public.js" defer></script>'
    if old_js not in data:
        raise RuntimeError("public catch wall: gallery.js script missing")
    data = data.replace(old_js, new_js, 1)
    data = _apply_preview_dateline(_apply_chrome(data))
    for src in (b"/region-nav.js", b"/brief-link.js", b"/identity.js"):
        data = _ensure_script(data, src)
    return data


def _public_catch_wall_redesign(water: str = "all") -> bytes | None:
    """Public /catch-wall: the Catch Wall redesign (approved photos only, no preview chrome).
    Returns None, so the caller serves the previous render, when there is nothing to show
    (that page owns the empty and unavailable states) or when the render raises (logged)."""
    try:
        data = catch_wall_preview.public_page(water)
        if b'name="robots" content="index, follow"' not in data or b'class="pv-flag"' in data:
            raise RuntimeError("public catch wall render failed its own checks")
        return data
    except catch_wall_preview.NotReady:
        return None
    except Exception as e:  # never take the page down for a presentation change
        sys.stderr.write("public catch wall redesign failed, serving previous render: %r\n" % (e,))
        return None


# /catch-wall, /coastal-life and /photos share catch-wall.html. Give each its own
# share title and URL by swapping only these three tags; the page body is unchanged.
_SHARE_META = {
    "catch-wall": ("Catch Wall \u2014 The Coastal Brief", "https://thecoastalbrief.com/catch-wall"),
    "coastal-life": ("Coastal Life \u2014 The Coastal Brief", "https://thecoastalbrief.com/coastal-life"),
    "photos": ("Photos \u2014 Catch Wall &amp; Coastal Life \u2014 The Coastal Brief", "https://thecoastalbrief.com/photos"),
}
_OG_TITLE_RE = re.compile(br'(<meta property="og:title" content=")[^"]*(")')
_OG_URL_RE = re.compile(br'(<meta property="og:url" content=")[^"]*(")')
_TW_TITLE_RE = re.compile(br'(<meta name="twitter:title" content=")[^"]*(")')
_DOC_TITLE_RE = re.compile(br'(<title>)[^<]*(</title>)')


def _apply_share_meta(data: bytes, page: str) -> bytes:
    meta = _SHARE_META.get(page)
    if not meta:
        return data
    title = meta[0].encode("utf-8")
    url = meta[1].encode("ascii")
    data = _OG_TITLE_RE.sub(lambda m: m.group(1) + title + m.group(2), data, count=1)
    data = _TW_TITLE_RE.sub(lambda m: m.group(1) + title + m.group(2), data, count=1)
    data = _DOC_TITLE_RE.sub(lambda m: m.group(1) + title + m.group(2), data, count=1)  # tab title too
    data = _OG_URL_RE.sub(lambda m: m.group(1) + url + m.group(2), data, count=1)
    return data


# Public robots.txt and sitemap.xml. Flag-gated pages (Morning Brief, /lake)
# are listed only when their public flag is on, so the sitemap never advertises
# a 404. Jordan Lake and Neuse River have /lake?region= pages, not briefs.
SITE_ORIGIN = "https://thecoastalbrief.com"


def robots_body() -> bytes:
    return (
        "User-agent: *\n"
        "Allow: /\n"
        "\n"
        "Sitemap: %s/sitemap.xml\n" % SITE_ORIGIN
    ).encode("utf-8")


def public_sitemap_urls() -> list[str]:
    urls = [
        SITE_ORIGIN + "/",
        SITE_ORIGIN + "/dashboard",
        SITE_ORIGIN + "/catch-wall",
        SITE_ORIGIN + "/coastal-life",
        SITE_ORIGIN + "/photos",
    ]
    if brief.flag_on():
        urls += [
            SITE_ORIGIN + "/brief?region=crystal-coast",
            SITE_ORIGIN + "/brief?region=hatteras",
        ]
        if freshwater.flag_on():
            urls.append(SITE_ORIGIN + "/brief?region=falls-lake")
    if freshwater.flag_on():
        for rid in ("falls-lake", "jordan-lake", "neuse-river"):
            urls.append(SITE_ORIGIN + "/lake?region=" + rid)
    return urls


def sitemap_body() -> bytes:
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>\n',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n',
    ]
    for u in public_sitemap_urls():
        parts.append("  <url><loc>%s</loc></url>\n" % html.escape(u, quote=True))
    parts.append("</urlset>\n")
    return "".join(parts).encode("utf-8")


# ---------------------------------------------------------------- private preview access
# /preview?key=<PREVIEW_KEY> sets an HttpOnly cookie that unlocks the flagged previews (/lab/wind,
# /lab/tiles, /preview/masthead, and any not-yet-public saltwater dashboard) in that browser only. The key lives only in
# the PREVIEW_KEY env var on Render; the cookie holds an HMAC of it, so rotating the key locks every
# browser out. Without the key set, /preview is 404. Public freshwater and Morning Brief pages do not
# need the cookie.
PREVIEW_COOKIE = "cb_preview"
PREVIEW_DAYS = 60


def _preview_secret() -> str:
    k = (os.environ.get("PREVIEW_KEY") or "").strip()
    return k if len(k) >= 24 else ""


def _preview_cookie_value(k: str) -> str:
    return hmac.new(k.encode(), b"coastal-brief-preview-v1", hashlib.sha256).hexdigest()


def _flag(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() in ("1", "true", "on", "yes")


PREVIEW_HUB = """<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow"><title>Private previews · The Coastal Brief</title><link rel="stylesheet" href="/styles.css">
<style>body{background:var(--d-panel);color:var(--d-ink)}.pv{max-width:560px;margin:0 auto;padding:18px 16px 40px}
.pv h1{font:600 1.6rem/1.1 var(--f-display);margin:10px 0 4px}.pv p{color:var(--d-ink-2)}
.pv a.card{display:block;padding:14px 16px;margin:10px 0;border:1px solid var(--d-edge);border-radius:12px;background:var(--d-inst);color:var(--d-ink);text-decoration:none}
.pv a.card b{display:block;font-size:1.05rem}.pv a.card span{font-size:.86rem;color:var(--d-ink-2)}
.pv .badge{display:inline-block;font:700 .7rem/1.6 var(--f-ui);letter-spacing:.1em;text-transform:uppercase;color:#fff;background:#8c2f23;padding:2px 8px;border-radius:3px}</style></head>
<body><main class="pv"><span class="badge">Private preview · this browser only</span><h1>Previews</h1>
<p>These pages are unlocked for this browser for %d days. The wind and tile labs still return “not found” to the public. The Morning Brief, the public freshwater pages and the public saltwater dashboards (Crystal Coast, Hatteras, Wilmington, Nags Head, Emerald Isle and Topsail) are public. Carolina Beach / Kure Beach, Corolla / Duck and the Cape Fear River stay on this preview hub.</p>
<a class="card" href="/lake"><b>Falls Lake</b><span>Freshwater dashboard: lake level vs guide curve, dam release, inflows, rain, river gauges</span></a>
<a class="card" href="/lake?region=jordan-lake"><b>Jordan Lake</b><span>Pool vs 216.0 ft guide curve, release plus local runoff, Haw inflow</span></a>
<a class="card" href="/lake?region=neuse-river"><b>Neuse River</b><span>Falls Dam to Goldsboro: stage, flow and NWS flood stages (Smithfield is stage only)</span></a>
<a class="card" href="/brief?region=crystal-coast"><b>Morning Brief · Crystal Coast</b><span>Today's brief, built from live readings</span></a>
<a class="card" href="/brief?region=hatteras"><b>Morning Brief · Hatteras</b><span>Today's brief, built from live readings</span></a>
<a class="card" href="/brief?region=falls-lake"><b>Morning Brief · Falls Lake</b><span>Freshwater version</span></a>
<a class="card" href="/preview/brief/wilmington"><b>Preview brief · Wilmington</b><span>Private Morning Brief preview, built on request. Not published or archived.</span></a>
<a class="card" href="/preview/brief/nags-head"><b>Preview brief · Nags Head</b><span>Private Morning Brief preview, built on request. Not published or archived.</span></a>
<a class="card" href="/preview/brief/emerald-isle"><b>Preview brief · Emerald Isle</b><span>Private Morning Brief preview, built on request. Not published or archived.</span></a>
<a class="card" href="/preview/brief/topsail"><b>Preview brief · Topsail</b><span>Private Morning Brief preview, built on request. Not published or archived.</span></a>
<a class="card" href="/?region=carolina-kure"><b>Preview conditions · Carolina Beach / Kure Beach</b><span>Private dashboard preview. Cookie-gated; not in the public region list.</span></a>
<a class="card" href="/preview/brief/carolina-kure"><b>Preview brief · Carolina Beach / Kure Beach</b><span>Private Morning Brief preview, built on request. Not published or archived.</span></a>
<a class="card" href="/?region=corolla-duck"><b>Preview conditions · Corolla / Duck</b><span>Private dashboard preview, centered on Duck. Cookie-gated; not in the public region list.</span></a>
<a class="card" href="/preview/brief/corolla-duck"><b>Preview brief · Corolla / Duck</b><span>Private Morning Brief preview, built on request. Not published or archived.</span></a>
<a class="card" href="/preview/brief/jordan-lake"><b>Preview brief · Jordan Lake</b><span>Private Morning Brief preview, built on request. Not published or archived.</span></a>
<a class="card" href="/preview/brief/neuse-river"><b>Preview brief · Neuse River</b><span>Private Morning Brief preview, built on request. Not published or archived.</span></a>
<a class="card" href="/lake?region=cape-fear-river"><b>Cape Fear River</b><span>Private preview: Lillington to Lock 1, main-stem stage and flow, NWPS forecasts. Cookie-gated, not public.</span></a>
<a class="card" href="/preview/brief/cape-fear-river"><b>Preview brief · Cape Fear River</b><span>Private Morning Brief preview, built on request. Not published or archived.</span></a>
<a class="card" href="/wind"><b>Wind viewer</b><span>Dedicated animated model wind (NOAA GFS forecast), private review</span></a>
<a class="card" href="/lab/wind"><b>Wind flow</b><span>Animated model wind (NOAA GFS forecast)</span></a>
<a class="card" href="/lab/tiles"><b>Tile designs</b><span>The instrument tile prototype</span></a>
<a class="card" href="/preview/masthead?c=c"><b>Masthead concepts</b><span>Three directions for a cinematic gold wave-to-masthead reveal (A editorial, B nautical, C hybrid). Replay from the bar at the bottom.</span></a>
<a class="card" href="/preview/home"><b>Homepage (Ed's pick)</b><span>Classic Coastal Editorial masthead (A) with the Modern Coastal Magazine layout and the Bodie Island sunrise. Compare Cinematic and the other mastheads from the bar at the bottom.</span></a>
<a class="card" href="/preview/identity"><b>Chartroom Folio</b><span>Visual identity sprint: stronger nameplate, conditions as one instrument panel, a slim credited photo strip after the readings, and one editorial card for saltwater and freshwater.</span></a>
<a class="card" href="/preview/intro?play=1"><b>Wave intro</b><span>Private signature intro over the public homepage. Plays on a new visit, not within 12 hours or from an in-site link. Use ?play=1 to review. Skip or press Escape.</span></a>
<a class="card" href="/preview/home-heritage"><b>Homepage concept A · Heritage</b><span>Private sprint concept: Carolina maritime heritage, live instruments first.</span></a>
<a class="card" href="/preview/home-editorial"><b>Homepage concept B · Editorial</b><span>Private sprint concept: magazine grid, photo-led, live instruments first.</span></a>
<a class="card" href="/preview/catch-wall"><b>Catch Wall redesign</b><span>Private preview: the Catch Wall as editorial photo pages, saltwater and freshwater side by side.</span></a>
<a class="card" href="/preview/home-hybrid"><b>Homepage concept C · Hybrid</b><span>Private sprint concept: heritage instruments with an editorial grid.</span></a>
<a class="card" href="/catch-wall"><b>Catch Wall photo submissions</b><span>Private test: the Share form and the review page work in this browser, even while public uploads stay off. Photos you send wait in the pending queue until you approve them.</span></a>
<a class="card" href="/preview/photos-check"><b>Photo setup check</b><span>A private status report: storage, image tools, and the pending queue. It never shows keys.</span></a>
<p><a href="/preview?lock=1">Lock this browser again</a></p></main></body></html>""" % PREVIEW_DAYS

conditions.install(cache_get, cache_get_any, cache_put_ttl, lambda url: fetch_url(url, tries=2))


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def log_message(self, fmt, *args):
        out = []
        for a in args:
            out.append(redact_request_text(a) if isinstance(a, str) else a)
        try:
            msg = (fmt % tuple(out)) if args else fmt
        except (TypeError, ValueError):
            msg = fmt
        if isinstance(msg, str):
            msg = redact_request_text(msg)
        sys.stderr.write("%s - %s\n" % (self.address_string(), msg))

    def end_headers(self):
        # Default for static files. Proxy/API responses set their own cache header first.
        if getattr(self, "_static_cache", None):
            self.send_header("Cache-Control", self._static_cache)
            self._static_cache = None
        elif not getattr(self, "_cache_header_sent", False):
            self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_HEAD(self):
        parsed = urlparse(self.path)
        if not (parsed.path.startswith("/api/") or parsed.path in ("/catch-wall", "/catch-wall/")) and not _static_allowed(parsed.path):
            self.send_error(404, "not found")
            return
        return super().do_HEAD()

    def _preview_ok(self) -> bool:
        k = _preview_secret()
        if not k:
            return False
        want = _preview_cookie_value(k)
        for part in (self.headers.get("Cookie") or "").split(";"):
            name, _, val = part.strip().partition("=")
            if name == PREVIEW_COOKIE and hmac.compare_digest(val, want):
                return True
        return False

    def _preview_route(self, parsed):
        k = _preview_secret()
        if not k:
            return self.send_error(404, "not found")
        q = parse_qs(parsed.query)
        secure = "; Secure" if (self.headers.get("X-Forwarded-Proto") or "").lower() == "https" else ""
        if q.get("lock"):
            ck = "%s=; Max-Age=0; Path=/; HttpOnly; SameSite=Lax%s" % (PREVIEW_COOKIE, secure)
            return self._send_private(None, "text/html; charset=utf-8", b"<p>Locked. Previews are hidden in this browser again.</p>", 200, [("Set-Cookie", ck)])
        given = (q.get("key") or [""])[0]
        if given:
            if not hmac.compare_digest(given.encode(), k.encode()):
                time.sleep(0.5)
                return self.send_error(404, "not found")
            ck = "%s=%s; Max-Age=%d; Path=/; HttpOnly; SameSite=Lax%s" % (PREVIEW_COOKIE, _preview_cookie_value(k), PREVIEW_DAYS * 86400, secure)
            # redirect so the key does not stay in the address bar or history entry
            self.send_response(303)
            self.send_header("Location", "/preview")
            self.send_header("Set-Cookie", ck)
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Robots-Tag", "noindex, nofollow")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if not self._preview_ok():
            return self.send_error(404, "not found")
        return self._send_private(None, "text/html; charset=utf-8", PREVIEW_HUB.encode())

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/robots.txt":
            return self._send_bytes(robots_body(), "text/plain; charset=utf-8", cache_s=300)
        if parsed.path == "/sitemap.xml":
            return self._send_bytes(sitemap_body(), "application/xml; charset=utf-8", cache_s=300)
        if parsed.path.startswith("/catch-wall-media/"):
            parsed_media = catch_wall_public.parse_media_path(parsed.path)
            body = catch_wall_public.media_bytes(*parsed_media) if parsed_media else None
            if not body:
                return self.send_error(404, "not found")
            return self._send_bytes(body, "image/webp", cache_s=300)
        if parsed.path.startswith("/featured/"):
            name = posixpath.basename(unquote(parsed.path))
            if not _HOME_PHOTO_RE.match(name):
                return self.send_error(404, "not found")
            path = (HOME_PHOTOS_DIR / name).resolve()
            try:
                path.relative_to(HOME_PHOTOS_DIR.resolve())
            except ValueError:
                return self.send_error(404, "not found")
            if not path.is_file():
                return self.send_error(404, "not found")
            ctype = "image/avif" if path.suffix.lower() == ".avif" else "image/webp"
            return self._send_file(path, ctype)
        if parsed.path == "/preview":
            return self._preview_route(parsed)
        if parsed.path == "/preview/photos-check":
            if not self._preview_ok():
                return self.send_error(404, "not found")
            return self._json_private(photos.diagnostics())
        if parsed.path.startswith("/preview/brief/"):
            # Private preview Morning Briefs (coastal four, plus Jordan Lake, Neuse River and Cape Fear). Same cookie as
            # /preview; 404 without it. Built in memory, never stored or archived, never on /brief.
            if not self._preview_ok():
                return self.send_error(404, "not found")
            import brief_preview
            status, b = brief_preview.get(parsed.path[len("/preview/brief/"):].strip("/"))
            if status != 200:
                return self._send_private(None, "text/html; charset=utf-8", ("<p>%s</p>" % html.escape(b.get("error", ""))).encode(), status)
            return self._send_private(None, "text/html; charset=utf-8", brief_preview.page(b).encode())
        if parsed.path == "/preview/masthead" or parsed.path == "/preview/masthead.css":
            return self._masthead_preview_route(parsed)
        if parsed.path == "/preview/home" or parsed.path == "/preview/home.css" or parsed.path.startswith("/preview/home/photos/"):
            return self._home_preview_route(parsed)
        if parsed.path == "/preview/identity" or parsed.path == "/preview/identity.css":
            return self._identity_preview_route(parsed)
        if parsed.path == "/preview/intro":
            return self._wave_intro_route(parsed)
        if parsed.path == catch_wall_preview.ROUTE:
            # Private Catch Wall redesign. Same cookie as /preview; 404 without it. Presentation only.
            if not self._preview_ok():
                return self.send_error(404, "not found")
            try:
                data = catch_wall_preview.page()
            except Exception as e:
                sys.stderr.write("catch wall preview failed: %s\n" % e)
                return self.send_error(500, "preview failed")
            return self._send_private(None, "text/html; charset=utf-8", data)
        if parsed.path in sprint_home.ROUTES:
            return self._sprint_home_route(parsed)
        if parsed.path.startswith(sprint_home.PHOTO_ROUTE):
            if not self._preview_ok():
                return self.send_error(404, "not found")
            path = sprint_home.photo_path(parsed.path)
            if not path:
                return self.send_error(404, "not found")
            return self._send_file(path, "image/avif" if path.suffix == ".avif" else "image/webp")
        if parsed.path.startswith(photo_rotation.ROUTE):
            # Daily featured photo files: only files the active manifest references.
            path = photo_rotation.file_for(parsed.path[len(photo_rotation.ROUTE):])
            if not path:
                return self.send_error(404, "not found")
            self._static_cache = "public, max-age=86400"
            ctype = {".avif": "image/avif", ".webp": "image/webp"}.get(path.suffix, "image/jpeg")
            return self._send_file(path, ctype)
        if parsed.path.startswith(sprint_home.PUBLIC_PHOTO_ROUTE):
            # Public homepage photos: the approved files only (strict name pattern, one folder, no listing).
            path = sprint_home.photo_path(parsed.path, sprint_home.PUBLIC_PHOTO_ROUTE)
            if not path:
                return self.send_error(404, "not found")
            self._static_cache = "public, max-age=86400"
            return self._send_file(path, "image/avif" if path.suffix == ".avif" else "image/webp")
        # /?region=falls-lake (etc.) should open the lake page, not break the saltwater dashboard.
        # "/" is the Hybrid homepage; the previous dashboard (map, tides, 7-day) lives at /dashboard
        # with the same region handling.
        if parsed.path in ("/", "/index.html", "/dashboard", "/dashboard/"):
            rid = (parse_qs(parsed.query).get("region") or [""])[0].strip()
            if rid in ("falls-lake", "jordan-lake", "neuse-river") and parsed.path in ("/", "/index.html") and freshwater.flag_on():
                # Public lakes and the Neuse open the Hybrid page in freshwater mode; /lake?region= is unchanged.
                return self._send_public_home(rid)
            if rid in ("falls-lake", "jordan-lake", "neuse-river") and (freshwater.flag_on() or self._preview_ok()):
                self.send_response(303)
                self.send_header("Location", "/lake?region=%s" % rid)
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            # Cookie-gated freshwater preview (Cape Fear River): same cookie as /preview. Public 404s.
            if freshwater.is_preview_region(rid):
                if not self._preview_ok():
                    # same page as an unknown id, so a private id is not confirmed
                    return self._send_private(None, "text/html; charset=utf-8", site_chrome.region_not_found_page(), 404)
                self.send_response(303)
                self.send_header("Location", "/lake?region=%s" % rid)
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            # Not-yet-public saltwater regions: same cookie as /preview. Public 404s.
            if conditions.is_preview_salt_region(rid):
                if not self._preview_ok():
                    # same page as an unknown id, so a private id is not confirmed
                    return self._send_private(None, "text/html; charset=utf-8", site_chrome.region_not_found_page(), 404)
                data = _public_home_html(rid, preview=True)
                if b'name="robots"' not in data:
                    data = data.replace(b"<head>", b'<head>\n  <meta name="robots" content="noindex, nofollow">', 1)
                else:
                    data = data.replace(b'name="robots" content="index, follow"', b'name="robots" content="noindex, nofollow"')
                return self._send_private(None, "text/html; charset=utf-8", data)
            if rid and rid not in sprint_home.public_salt_ids():
                # Unknown, disabled or not-public id: a clear not-found page, never Crystal Coast data
                # under another name (launch audit item 7). The id itself is not echoed.
                return self._send_private(None, "text/html; charset=utf-8", site_chrome.region_not_found_page(), 404)
            if parsed.path in ("/", "/index.html"):
                return self._send_public_home(rid or None, sc=showcase.variant(parse_qs(parsed.query), rid))
            return self._send_html(ROOT / "index.html", region_id=rid or None)
        if parsed.path == "/api/brief/wake":
            # Daily wake-up ping (GitHub Actions, 5:16 AM ET). Builds today's briefs if missing; returns no
            # brief content, so it publishes nothing. Idempotent: at most one build per region per day.
            # Runs when the brief is on (the default) or a preview key is set.
            if not (brief.flag_on() or _preview_secret()):
                return self.send_error(404, "not found")
            return self._json_private(brief.wake(include_fresh=freshwater.flag_on() or bool(_preview_secret())))
        if parsed.path in ("/catch-wall", "/catch-wall/"):
            return self._send_html(ROOT / "catch-wall.html", share="catch-wall")
        if parsed.path in ("/feedback", "/feedback/"):
            return self._feedback_get(parsed)
        if parsed.path == "/api/health":
            return self._send_json({"ok": True})
        if parsed.path == "/api/snapshot":
            return self._send_file(ROOT / "data" / "snapshot.json", "application/json")
        if parsed.path == "/api/ads":
            force = "refresh=1" in (parsed.query or "")
            return self._send_json(get_ads(force=force), cache_s=60)
        if parsed.path == "/api/tide-stations":
            return self._send_file(TIDE_STATIONS_PATH, "application/json")
        if parsed.path == "/api/tides":
            status, payload = handle_tides(parsed.query)
            return self._send_json(payload, cache_s=60, status=status)
        if parsed.path == "/api/geocode":
            status, payload = handle_geocode(parsed.query)
            return self._send_json(payload, cache_s=300, status=status)
        if parsed.path == "/api/regions":
            # Public clients always see the current public saltwater list.
            # A preview-cookie browser also gets the not-yet-public regions, so
            # the dashboard dropdown can open them. The public list is unchanged.
            pv = self._preview_ok()
            return self._send_json(conditions.listed_regions(preview=pv), cache_s=0 if pv else 300)
        if parsed.path == "/api/conditions":
            rid = (parse_qs(parsed.query or "").get("region") or [""])[0].strip()
            try:
                status, payload = conditions.assemble(rid or None, preview=self._preview_ok())
            except Exception as e:  # keep the page up if one feed misbehaves
                sys.stderr.write("conditions failed: %s\n" % e)
                status, payload = 502, {"ok": False, "error": "Conditions are unavailable right now."}
            if self._preview_ok() and (status != 200 or conditions.is_preview_salt_region(rid)):
                # Preview-only data is never marked publicly cacheable.
                return self._json_private(payload, status)
            return self._send_json(payload, cache_s=60, status=status)
        if parsed.path in ("/coastal-life", "/coastal-life/", "/photos", "/photos/"):
            return self._send_html(ROOT / "catch-wall.html", share=parsed.path.strip("/"))
        if parsed.path == "/api/photos/config":
            pv = self._preview_ok()
            cfg = photos.public_config(preview=pv)
            if pv:
                return self._json_private(cfg)
            return self._send_json(cfg, cache_s=60)
        if parsed.path == "/api/photos":
            q = parse_qs(parsed.query or "")
            view = (q.get("view") or ["all"])[0]
            feat = (q.get("featured") or [""])[0] == "1"
            return self._send_json(photos.public_photos(view, feat), cache_s=60)
        if parsed.path in ("/admin", "/admin/"):
            if not photos.admin_available(self._preview_ok()):
                return self.send_error(404, "not found")
            return self._send_private(ROOT / "admin.html", "text/html; charset=utf-8")
        if parsed.path.startswith("/api/admin/"):
            return self._admin_get(parsed)
        if parsed.path.startswith("/fake-storage/approved/"):
            return self._fake_storage(parsed)
        if parsed.path in ("/lake", "/lake.js", "/api/freshwater"):
            # Freshwater pages are on by default. FRESHWATER_ENABLED=0/false/off is the kill switch.
            # Cape Fear River is a cookie-gated preview: public requests 404 even when the flag is on.
            public = freshwater.flag_on()
            q_rid = (parse_qs(parsed.query or "").get("region") or ["falls-lake"])[0].strip() or "falls-lake"
            preview_fw = freshwater.is_preview_region(q_rid)
            if preview_fw:
                if not self._preview_ok():
                    return self.send_error(404, "not found")
            elif not (public or self._preview_ok()):
                return self.send_error(404, "not found")
            robots = "noindex, nofollow" if (preview_fw or not public) else "index, follow"
            if parsed.path == "/lake":
                data = _paint_public_lake((ROOT / "lake.html").read_bytes(), region=q_rid)
                if robots.startswith("noindex"):
                    data = data.replace(
                        b'name="robots" content="index, follow"',
                        b'name="robots" content="noindex, nofollow"',
                    )
                return self._send_private(ROOT / "lake.html", "text/html; charset=utf-8", data, robots=robots)
            if parsed.path == "/lake.js":
                return self._send_private(ROOT / "lake.js", "text/javascript; charset=utf-8", robots=robots)
            status, payload = freshwater.assemble(q_rid)
            if preview_fw:
                return self._json_private(payload, status)
            return self._send_json(payload, cache_s=0, status=status)
        if parsed.path in ("/brief", "/api/brief"):
            # Saltwater Morning Brief is on by default. MORNING_BRIEF_ENABLED=0/false/off is the
            # kill switch. The Falls Lake brief is public when freshwater is also on (the default).
            # Linked from the site header when this flag is on (stripped when it is off).
            pv = self._preview_ok()
            if not (brief.flag_on() or pv):
                return self.send_error(404, "not found")
            q = parse_qs(parsed.query)
            rid = (q.get("region") or [""])[0] or "crystal-coast"
            include_fresh = freshwater.flag_on() or pv
            status, b = brief.get(rid, include_fresh=include_fresh)
            if parsed.path == "/api/brief":
                return self._json_private(b, status)
            if status == 404:
                # A region without a public brief: a real page with the site nav and links to the
                # briefs that exist (launch audit item 5). Private ids are never named.
                return self._send_private(None, "text/html; charset=utf-8", site_chrome.no_brief_page(rid), 404)
            if status != 200:
                return self._send_private(None, "text/html; charset=utf-8", site_chrome.page(
                    "Morning Brief unavailable", "Morning Brief unavailable",
                    "<p>%s</p>" % html.escape(b.get("error", "")), current="brief", brief_rid=rid), status)
            water = b.get("waterType") or ""
            rid_final = b.get("regionId") or (b.get("region") or {}).get("id") or rid
            # Indexable when the brief is on for the public. Falls Lake also needs the freshwater
            # flag (kill switch or preview-only stays noindex). No Jordan/Neuse briefs.
            is_fresh = water == "freshwater" or rid_final == "falls-lake"
            public = brief.flag_on() and (freshwater.flag_on() if is_fresh else True)
            # No ad creative is wired into the brief yet, so never reserve an
            # empty gap. When ads are hooked up, pass ads_on from get_ads()
            # (adsOn and mode != paused) and place the slot below advisories.
            body = brief.page(b, include_fresh=include_fresh, public=public, ads_on=False)
            robots = "index, follow" if public else "noindex, nofollow"
            return self._send_private(
                None,
                "text/html; charset=utf-8",
                _polish_public_brief(_paint_public_brief(body.encode("utf-8"))),
                robots=robots,
            )
        if parsed.path in ("/lab/tiles", "/lab/tiles.js"):
            # Tile design prototype, off unless TILES_LAB_ENABLED=1. Not linked from the site.
            if not (_flag("TILES_LAB_ENABLED") or self._preview_ok()):
                return self.send_error(404, "not found")
            if parsed.path == "/lab/tiles":
                return self._send_private(ROOT / "tiles-lab.html", "text/html; charset=utf-8")
            return self._send_private(ROOT / "tiles-lab.js", "text/javascript; charset=utf-8")
        if parsed.path.startswith("/radar/fixture-tile/"):
            # Test-only fixture tiles: never on Render; 404 without the preview cookie or lab flag.
            pv = self._preview_ok()
            if not ((_flag("WIND_PARTICLES_ENABLED") or pv) and radarview.fixture_mode()):
                return self.send_error(404, "not found")
            m = re.fullmatch(r"/radar/fixture-tile/(\d+)/(\d+)/(\d+)\.png", parsed.path)
            body = radarview.fixture_tile(m.group(1), m.group(2), m.group(3), (parse_qs(parsed.query).get("t") or [""])[0]) if m else None
            if body is None:
                return self.send_error(404, "not found")
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "private, max-age=86400")
            self.send_header("X-Robots-Tag", "noindex, nofollow")
            self._cache_header_sent = True
            self.end_headers()
            self.wfile.write(body)
            return
        if parsed.path in ("/radar", "/radar.css", "/radar/viewer.js", "/radar/player.js", "/api/radar-view"):
            # Public viewer (noindex until the homepage showcase is launched). Fixtures stay private.
            if parsed.path == "/radar":
                _st, _rp = radarview.view_payload(handle_radar_meta, allow_fixture=False)
                _rp = _apply_feed_status(_rp)
                page = radarview.page_html((ROOT / "radar.html").read_text(encoding="utf-8"), _rp)
                return self._send_public_view(None, "text/html; charset=utf-8", page.encode("utf-8"))
            if parsed.path == "/radar.css":
                return self._send_bytes((ROOT / "radar.css").read_bytes(), "text/css; charset=utf-8", cache_s=600)
            if parsed.path == "/radar/viewer.js":
                return self._send_bytes((ROOT / "radar-viewer.js").read_bytes(), "text/javascript; charset=utf-8", cache_s=600)
            if parsed.path == "/radar/player.js":
                return self._send_bytes((ROOT / "radar-player.js").read_bytes(), "text/javascript; charset=utf-8", cache_s=600)
            retry = self._rate_limit("radar-meta", API_RADAR_META_LIMIT, API_RADAR_META_WINDOW)
            if retry is not None:
                return self._send_rate_limited(retry)
            st, payload = radarview.view_payload(handle_radar_meta, allow_fixture=False)
            payload = _apply_feed_status(payload)
            return self._send_json(payload, cache_s=60 if payload.get("ok") else 0, status=st)
        if parsed.path in ("/lab/wind", "/lab/wind.js"):
            # Private laboratory. The public viewer loads the shared engine at /wind/engine.js.
            pv = self._preview_ok()
            if not (_flag("WIND_PARTICLES_ENABLED") or pv):
                return self.send_error(404, "not found")
            if parsed.path == "/lab/wind":
                return self._send_private(ROOT / "wind-lab.html", "text/html; charset=utf-8")
            return self._send_private(ROOT / "wind-lab.js", "text/javascript; charset=utf-8")
        if parsed.path == "/api/wind-grid":
            qs = parse_qs(parsed.query)
            try:
                ahead = int((qs.get("ahead") or ["0"])[0])
            except ValueError:
                ahead = 0
            ahead = ahead if ahead in windgrid.AHEAD_HOURS else 0
            want_hrrr = (qs.get("model") or [""])[0] == "hrrr"
            pv = self._preview_ok()
            if want_hrrr:
                if not (_flag("WIND_PARTICLES_ENABLED") or pv):
                    return self.send_error(404, "not found")
                g = hrrrgrid.latest_grid(ahead=ahead)
                if pv and not _flag("WIND_PARTICLES_ENABLED"):
                    return self._json_private(g, 200 if g.get("ok") else 502)
                return self._send_json(g, cache_s=600 if g.get("ok") else 60, status=200 if g.get("ok") else 502)
            retry = self._rate_limit("wind-grid", API_WIND_GRID_LIMIT, API_WIND_GRID_WINDOW)
            if retry is not None:
                return self._send_rate_limited(retry)
            g = windgrid.latest_grid(ahead=ahead)
            if not g.get("ok"):
                g = {"ok": False, "error": g.get("error") or "Model wind is unavailable right now."}
            return self._send_json(g, cache_s=600 if g.get("ok") else 60, status=200 if g.get("ok") else 502)
        if parsed.path in ("/wind", "/wind.css", "/wind/viewer.js", "/wind/coast.js", "/wind/engine.js", "/wind/coast-lo.json", "/wind/coast-hi.json"):
            qs = parse_qs(parsed.query)
            if parsed.path == "/wind" and (qs.get("model") or [""])[0] == "hrrr":
                if not (_flag("WIND_PARTICLES_ENABLED") or self._preview_ok()):
                    return self.send_error(404, "not found")
                return self._send_private(ROOT / "wind.html", "text/html; charset=utf-8")
            if parsed.path == "/wind":
                return self._send_public_view(ROOT / "wind.html", "text/html; charset=utf-8")
            if parsed.path == "/wind.css":
                return self._send_bytes((ROOT / "wind.css").read_bytes(), "text/css; charset=utf-8", cache_s=600)
            if parsed.path == "/wind/viewer.js":
                return self._send_bytes((ROOT / "wind-viewer.js").read_bytes(), "text/javascript; charset=utf-8", cache_s=600)
            if parsed.path == "/wind/coast.js":
                return self._send_bytes((ROOT / "wind-coast.js").read_bytes(), "text/javascript; charset=utf-8", cache_s=600)
            if parsed.path == "/wind/engine.js":
                return self._send_bytes((ROOT / "wind-lab.js").read_bytes(), "text/javascript; charset=utf-8", cache_s=600)
            name = "lo.json" if parsed.path.endswith("lo.json") else "hi.json"
            return self._send_bytes((ROOT / "wind-coast" / name).read_bytes(), "application/json; charset=utf-8", cache_s=86400)

        if parsed.path == "/showcase.js":
            if not showcase.enabled():
                return self.send_error(404, "not found")
            self._static_cache = "public, max-age=600"
            return self._send_bytes((ROOT / "showcase.js").read_bytes(), "text/javascript; charset=utf-8", cache_s=600)
        if parsed.path == "/api/home-wind":
            # Public GFS-only snapshot for the homepage instruments. Ignores query strings
            # (no ahead, no ?model=hrrr). windgrid caches the file 30 minutes, so repeats
            # cannot drive unbounded NOMADS calls. Browser cache 10 minutes.
            g = windgrid.latest_grid(ahead=0)
            if g.get("ok"):
                g = {k: g[k] for k in (
                    "ok", "kind", "source", "run", "valid", "forecastHour", "units",
                    "nx", "ny", "la1", "lo1", "dx", "dy", "scan", "ahead", "u", "v") if k in g}
            else:
                g = {"ok": False, "error": g.get("error") or "Model wind is unavailable right now."}
            return self._send_json(g, cache_s=600 if g.get("ok") else 60, status=200 if g.get("ok") else 502)
        if parsed.path == "/api/home-coast":
            # Public-domain Census 1:500k coastline (low-res), the file the homepage draws.
            # Static; no upstream fetch. High-res /wind/coast-hi.json stays private.
            data = (ROOT / "wind-coast" / "lo.json").read_bytes()
            return self._send_bytes(data, "application/json; charset=utf-8", cache_s=86400)
        if parsed.path == "/api/sst-time":
            return self._send_json(sst_latest_times(), cache_s=600)
        if parsed.path == "/api/radar/usage":
            if not self._preview_ok():
                return self.send_error(404, "not found")
            return self._json_private(radar_usage_payload(), 200)
        if parsed.path == "/api/radar":
            retry = self._rate_limit("radar-meta", API_RADAR_META_LIMIT, API_RADAR_META_WINDOW)
            if retry is not None:
                return self._send_rate_limited(retry)
            status, payload = handle_radar_meta()
            payload = _apply_feed_status(payload)
            return self._send_json(payload, cache_s=60, status=status)
        if parsed.path.startswith("/api/radar/tile/"):
            return self._radar_tile(parsed)
        if parsed.path.startswith("/proxy/"):
            return self._proxy(parsed)
        if not _static_allowed(parsed.path):
            self.send_error(404, "not found")
            return
        if parsed.path.startswith("/fonts/") and parsed.path.endswith(".woff2"):
            self._cache_header_sent = True
            self._static_cache = "public, max-age=31536000, immutable"
        return super().do_GET()

    # ------------------------------------------------------------ photos
    def _client_ip(self) -> str:
        peer = self.client_address[0] if self.client_address else ""
        return client_ip_from_headers(self.headers, peer)

    def _same_origin(self) -> bool:
        origin = self.headers.get("Origin")
        if not origin:
            return False
        host = (self.headers.get("X-Forwarded-Host") or self.headers.get("Host") or "").lower()
        return urlparse(origin).netloc.lower() == host


    def _masthead_preview_route(self, parsed):
        if not self._preview_ok():
            return self.send_error(404, "not found")
        if parsed.path == "/preview/masthead.css":
            css = MASTHEAD_DIR / "masthead.css"
            if not css.is_file():
                return self.send_error(404, "not found")
            return self._send_private(css, "text/css; charset=utf-8")
        q = parse_qs(parsed.query or "")
        concept = (q.get("c") or ["c"])[0].strip().lower()
        if concept not in MASTHEAD_CONCEPTS:
            concept = "c"
        shot = (q.get("shot") or [""])[0] == "1"
        try:
            data = _masthead_preview_html(concept, shot=shot)
        except Exception as e:
            sys.stderr.write("masthead preview failed: %s\n" % e)
            return self.send_error(500, "preview failed")
        return self._send_private(None, "text/html; charset=utf-8", data)

    def _home_preview_route(self, parsed):
        if not self._preview_ok():
            return self.send_error(404, "not found")
        if parsed.path == "/preview/home.css":
            css = HOME_DIR / "home.css"
            if not css.is_file():
                return self.send_error(404, "not found")
            return self._send_private(css, "text/css; charset=utf-8")
        if parsed.path.startswith("/preview/home/photos/"):
            name = posixpath.basename(unquote(parsed.path))
            if not _HOME_PHOTO_RE.match(name):
                return self.send_error(404, "not found")
            path = (HOME_PHOTOS_DIR / name).resolve()
            try:
                path.relative_to(HOME_PHOTOS_DIR.resolve())
            except ValueError:
                return self.send_error(404, "not found")
            if not path.is_file():
                return self.send_error(404, "not found")
            ctype = "image/avif" if path.suffix.lower() == ".avif" else "image/webp"
            return self._send_private(path, ctype)
        q = parse_qs(parsed.query or "")
        home = (q.get("c") or ["final"])[0].strip().lower()
        if home not in HOME_CONCEPTS:
            home = "final"
        mast = (q.get("m") or [""])[0].strip().lower() or None
        photo_id = (q.get("photo") or [""])[0].strip() or None
        shot = (q.get("shot") or [""])[0] == "1"
        try:
            data = _home_preview_html(home, shot=shot, photo_id=photo_id, mast=mast)
        except Exception as e:
            sys.stderr.write("home preview failed: %s\n" % e)
            return self.send_error(500, "preview failed")
        return self._send_private(None, "text/html; charset=utf-8", data)

    def _identity_preview_route(self, parsed):
        if not self._preview_ok():
            return self.send_error(404, "not found")
        if parsed.path == "/preview/identity.css":
            css = IDENTITY_DIR / "identity.css"
            if not css.is_file():
                return self.send_error(404, "not found")
            return self._send_private(css, "text/css; charset=utf-8")
        q = parse_qs(parsed.query or "")
        photo_id = (q.get("photo") or [""])[0].strip() or None
        region_id = (q.get("region") or [""])[0].strip() or None
        shot = (q.get("shot") or [""])[0] == "1"
        try:
            data = _identity_preview_html(region_id, photo_id=photo_id, shot=shot)
        except Exception as e:
            sys.stderr.write("identity preview failed: %s\n" % e)
            return self.send_error(500, "preview failed")
        return self._send_private(None, "text/html; charset=utf-8", data)

    def _wave_intro_route(self, parsed):
        if not self._preview_ok():
            return self.send_error(404, "not found")
        q = parse_qs(parsed.query or "")
        region_id = (q.get("region") or [""])[0].strip() or None
        try:
            data = wave_intro.paint(_folio_home_html(region_id, gated=True, shot=True))
        except Exception as e:
            sys.stderr.write("wave intro preview failed: %s\n" % e)
            return self.send_error(500, "preview failed")
        return self._send_private(None, "text/html; charset=utf-8", data)


    def _send_public_home(self, rid, sc=None):
        """Public Hybrid homepage. If it cannot render, serve the dashboard so / never goes down."""
        try:
            data = sprint_home.page("hybrid", rid, public=True)
        except Exception as e:
            sys.stderr.write("hybrid home failed, serving dashboard: %s\n" % e)
            return self._send_html(ROOT / "index.html", region_id=rid)
        if sc:  # Concept A Wind & Radar section; only when HOME_SHOWCASE is on
            data = showcase.inject(data, sc, radar_meta=handle_radar_meta)
            self.send_response(200)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _sprint_home_route(self, parsed):
        if not self._preview_ok():
            return self.send_error(404, "not found")
        q = parse_qs(parsed.query or "")
        rid = (q.get("region") or [""])[0].strip()[:40] or None
        shot = (q.get("shot") or [""])[0] == "1"
        # Preview-only: ?date=YYYY-MM-DD or ?photo=<id> shows any day's featured photo (gated route).
        pday = (q.get("date") or [""])[0].strip()[:10] or None
        pid = (q.get("photo") or [""])[0].strip()[:64] or None
        try:
            data = sprint_home.page(sprint_home.ROUTES[parsed.path], rid, shot=shot, photo_day=pday, photo_id=pid)
        except Exception as e:
            sys.stderr.write("sprint home preview failed: %s\n" % e)
            return self.send_error(500, "preview failed")
        return self._send_private(None, "text/html; charset=utf-8", data)

    def _send_private(self, path: Path, ctype: str, data: bytes | None = None, status: int = 200, extra=None, robots: str = "noindex, nofollow"):
        if data is None:
            data = path.read_bytes()
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Frame-Options", "DENY")
        if robots:
            self.send_header("X-Robots-Tag", robots)
        self.send_header("Referrer-Policy", "no-referrer")
        for k, v in (extra or []):
            self.send_header(k, v)
        self.end_headers()  # Cache-Control: no-store (default)
        self.wfile.write(data)

    def _json_private(self, obj, status=200, cookie=None):
        extra = [("Set-Cookie", cookie)] if cookie else []
        return self._send_private(None, "application/json; charset=utf-8", json.dumps(obj).encode(), status, extra)

    def _admin_get(self, parsed):
        csrf = photos.read_session(self.headers.get("Cookie", ""))
        admin_on = photos.admin_available(self._preview_ok())
        if parsed.path == "/api/admin/session" and admin_on and not csrf:
            return self._json_private({"ok": False})
        if not admin_on or not csrf:
            return self._json_private({"ok": False, "error": "Sign in first."}, 401 if admin_on else 404)
        if parsed.path == "/api/admin/list":
            status = (parse_qs(parsed.query or "").get("status") or ["pending"])[0]
            try:
                return self._json_private(photos.admin_list(status))
            except photos.StorageError as e:
                sys.stderr.write("admin list: %s\n" % e)
                return self._json_private({"ok": False, "error": "Storage error."}, 502)
        if parsed.path == "/api/admin/feedback":
            import feedback
            return self._json_private(feedback.admin_list())
        if parsed.path == "/api/admin/session":
            return self._json_private({"ok": True, "csrf": csrf})
        m = re.fullmatch(r"/api/admin/image/([0-9a-f-]{36})/(thumb|400|800|1600)", parsed.path)
        if m:
            data = photos.admin_image(m.group(1), m.group(2))
            if data is None:
                return self._json_private({"ok": False}, 404)
            return self._send_private(None, "image/webp", data)
        return self._json_private({"ok": False}, 404)

    def _fake_storage(self, parsed):
        b = photos.backend()
        if not b or b.name != "fake":
            return self.send_error(404, "not found")
        key = unquote(parsed.path[len("/fake-storage/approved/"):])
        try:
            data = b.get(b.approved, key)
        except photos.StorageError:
            return self.send_error(404, "not found")
        self.send_response(200)
        self.send_header("Content-Type", "image/webp")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        parsed = urlparse(self.path)
        routes = ("/api/photos/submit", "/api/admin/login", "/api/admin/logout", "/api/admin/action",
                  "/api/feedback", "/feedback")
        if parsed.path not in routes:
            return self._json_private({"ok": False, "error": "Not found."}, 404)
        # Flag off (or not configured): refuse before reading any body.
        pv = self._preview_ok()
        if parsed.path in ("/api/feedback", "/feedback"):
            return self._feedback_post(parsed)
        if parsed.path == "/api/photos/submit" and not photos.uploads_available(pv):
            return self._json_private({"ok": False, "error": "Not found."}, 404)
        if parsed.path != "/api/photos/submit" and not photos.admin_available(pv):
            return self._json_private({"ok": False, "error": "Not found."}, 404)
        if not self._same_origin():
            return self._json_private({"ok": False, "error": "Cross-site request refused."}, 403)
        try:
            length = int(self.headers.get("Content-Length") or "0")
        except ValueError:
            length = -1
        cap = photos.MAX_BYTES + 256 * 1024 if parsed.path == "/api/photos/submit" else 64 * 1024
        if length < 0 or length > cap:
            self.close_connection = True
            return self._json_private({"ok": False, "error": "That file is larger than 10 MB."}, 413)
        body = self.rfile.read(length) if length else b""
        ip = self._client_ip()
        if parsed.path == "/api/photos/submit":
            sid = photos.read_submit_session(self.headers.get("Cookie", "")) or photos.new_submit_session()
            status, payload = photos.handle_submit(
                self.headers.get("Content-Type", ""), body, ip,
                preview=self._preview_ok(), session_id=sid,
            )
            return self._json_private(payload, status, photos.submit_cookie(sid))
        if parsed.path == "/api/admin/login":
            status, payload, cookie = photos.admin_login(body, ip)
            return self._json_private(payload, status, cookie)
        csrf = photos.read_session(self.headers.get("Cookie", ""))
        if not csrf:
            return self._json_private({"ok": False, "error": "Sign in first."}, 401)
        if not hmac_compare(self.headers.get("X-CSRF-Token", ""), csrf):
            return self._json_private({"ok": False, "error": "Session check failed. Reload the page."}, 403)
        if parsed.path == "/api/admin/logout":
            return self._json_private({"ok": True}, 200, photos.session_cookie("", clear=True))
        status, payload = photos.admin_action(body)
        return self._json_private(payload, status)

    def _feedback_get(self, parsed):
        import feedback
        q = parse_qs(parsed.query or "")
        sent = (q.get("sent") or [""])[0] == "1"
        values = {"page": (q.get("from") or [""])[0]}
        data = feedback.page_html(sent=sent, values=values)
        return self._send_bytes(data, "text/html; charset=utf-8")

    def _feedback_post(self, parsed):
        import feedback
        if not self._same_origin():
            return self._json_private({"ok": False, "error": "Cross-site request refused."}, 403)
        try:
            length = int(self.headers.get("Content-Length") or "0")
        except ValueError:
            length = -1
        if length < 0 or length > 64 * 1024:
            self.close_connection = True
            return self._json_private({"ok": False, "error": "That message is too long."}, 413)
        body = self.rfile.read(length) if length else b""
        data = feedback.parse_body(self.headers.get("Content-Type", ""), body)
        status, payload = feedback.submit(data, self._client_ip(), self.headers.get("User-Agent", ""))
        if parsed.path == "/feedback":
            html = feedback.page_html(sent=payload.get("ok"), error=payload.get("error") or "", values=data)
            self.send_response(200 if payload.get("ok") else status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(html)
            return
        return self._json_private(payload, status)

    def _send_html(self, path: Path, share: str | None = None, region_id: str | None = None, preview: bool = False):
        if not path.is_file():
            return self.send_error(404, "file not found")
        if path.name == "index.html":
            data = _brief_nav_for(_public_home_html(region_id, preview=preview), region_id)
        elif share == "catch-wall" and (redesign := _public_catch_wall_redesign(
                (parse_qs(urlparse(getattr(self, "path", "") or "").query).get("water") or ["all"])[0])) is not None:
            data = redesign  # complete page with its own title, canonical and share meta
            share = None
        elif share in ("catch-wall", "coastal-life", "photos"):
            q = parse_qs(urlparse(getattr(self, "path", "") or "").query)
            water = (q.get("water") or ["all"])[0]
            data = _paint_public_catch_wall(path.read_bytes(), share, water)
        else:
            data = _apply_chrome(path.read_bytes())
        if share:
            data = _apply_share_meta(data, share)
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_bytes(self, data: bytes, ctype: str, cache_s: int = 0):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        if cache_s:
            self.send_header("Cache-Control", "public, max-age=%s" % cache_s)
            self._cache_header_sent = True
        self.end_headers()
        self.wfile.write(data)

    def _send_file(self, path: Path, ctype: str):
        if not path.is_file():
            self.send_error(404, "file not found")
            return
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_json(self, obj: dict, cache_s: int = 0, status: int = 200):
        data = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        if cache_s:
            self.send_header("Cache-Control", "public, max-age=%s" % cache_s)
            self._cache_header_sent = True
        self.end_headers()
        self.wfile.write(data)


    def _rate_limit(self, bucket: str, limit: int, window_s: int):
        """Return Retry-After seconds if this client is over the limit, else None."""
        ip = self._client_ip() or "unknown"
        ok, retry = API_LIMITS.check("%s:%s" % (bucket, ip), limit, window_s)
        return None if ok else retry

    def _send_rate_limited(self, retry_after: int):
        retry_after = max(1, int(retry_after))
        payload = {
            "ok": False,
            "reason": "rate_limit",
            "error": "Too many requests. Please try again in a moment.",
            "retry_after": retry_after,
        }
        data = json.dumps(payload).encode("utf-8")
        self.send_response(429)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Retry-After", str(retry_after))
        self.send_header("Cache-Control", "no-store")
        self._cache_header_sent = True
        self.end_headers()
        self.wfile.write(data)

    def _send_public_view(self, path, ctype: str, data: bytes | None = None):
        """Public viewer HTML: reachable without a cookie, but noindex until the showcase launch."""
        if data is None:
            data = path.read_bytes()
        return self._send_private(None, ctype, data, robots="noindex, nofollow")

    def _radar_tile(self, parsed):
        # /api/radar/tile/{z}/{x}/{y}.png?t=yyyyMMddHHmm
        m = re.fullmatch(r"/api/radar/tile/(\d+)/(\d+)/(\d+)(?:\.png)?", parsed.path)
        if not m:
            self.send_error(404, "invalid radar tile path")
            return
        qs = parse_qs(parsed.query or "")
        t = (qs.get("t") or [""])[0].strip()
        retry = self._rate_limit("radar-tile", API_TILE_LIMIT, API_TILE_WINDOW)
        if retry is not None:
            return self._send_rate_limited(retry)
        status, ctype, body, info = fetch_radar_tile_ex(m.group(1), m.group(2), m.group(3), t)
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        if status == 429:
            self.send_header("Retry-After", "60")
        if info.get("cache") == "stale":
            self.send_header("X-Radar-Cache", "stale")
            # Short browser cache: this is a terms-allowed fallback, not a fresh immutable copy.
            self.send_header("Cache-Control", "public, max-age=60")
            self._cache_header_sent = True
        else:
            ttl = radar_tile_ttl(t) if status == 200 else 0
            if ttl:
                # Observed tiles never change for a time code: 10 min in the browser (server copy <= 50 min, so
                # any copy is <= 60 min old, per WeatherAPI's current-conditions cap). Nowcast: 180 s.
                self.send_header("Cache-Control", "public, max-age=600, immutable" if ttl == TTL["radar_tile"] else "public, max-age=%s" % ttl)
                self._cache_header_sent = True
            else:
                self.send_header("Cache-Control", "no-store")
                self._cache_header_sent = True
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _proxy(self, parsed):
        parts = parsed.path.split("/", 3)  # ['', 'proxy', '<key>', '<rest>']
        if len(parts) < 3 or parts[1] != "proxy" or parts[2] not in PROXIES:
            self.send_error(404, "unknown proxy prefix")
            return
        key = parts[2]
        rest = parts[3] if len(parts) > 3 else ""
        target = safe_join(PROXIES[key], rest)
        if target is None:
            self.send_error(400, "invalid proxy path")
            return
        query = parsed.query
        url = target + (("?" + query) if query else "")
        # Drop a browser retry param if one is present so the cache key stays stable.
        # (The current front end no longer appends _r=.)
        wants_image = key in IMAGE_PROXIES and _looks_like_image_request(url)
        stale_copy = False
        cached = cache_get(url)
        if cached and wants_image and not _is_image(cached[1], cached[2]):
            cached = None  # an error page was cached earlier; fetch again
        if cached:
            status, ctype, body = cached
            from_cache = True
        else:
            status, ctype, body = fetch_url(url)
            if status == 200 and wants_image and not _is_image(ctype, body):
                # ArcGIS/WMS servers sometimes answer 200 with an HTML or XML error page.
                status, ctype, body = fetch_url(url, tries=2)
                if status == 200 and not _is_image(ctype, body):
                    status, ctype, body = 502, "text/plain; charset=utf-8", b"upstream returned a non-image tile"
            from_cache = False
            if status == 200:
                with CACHE_LOCK:
                    cache_put(url, key, status, ctype, body)
            elif wants_image:
                # Upstream down or answering with an error page: reuse this exact
                # tile from the last few hours rather than leave a hole.
                old = _recent_image_copy(url, max_age_s=6 * 3600)
                if old:
                    status, ctype, body = 200, old[0], old[1]
                    from_cache = True
                    stale_copy = True
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        ttl = TTL.get(key, TTL["default"])
        if status == 200 and stale_copy:
            self.send_header("Cache-Control", "public, max-age=60")
        elif status == 200:
            self.send_header("Cache-Control", "public, max-age=%s" % ttl)
        else:
            self.send_header("Cache-Control", "no-store")
        self.send_header("X-Cache", "HIT" if from_cache else "MISS")
        self._cache_header_sent = True
        self.end_headers()
        if body:
            self.wfile.write(body)


def main():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _usage_load()
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default=os.environ.get("HOST", "0.0.0.0"))
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8765")))
    args = ap.parse_args()
    # Warm the ads flag once at startup so the first page load is fast.
    try:
        get_ads(force=True)
    except Exception as e:
        sys.stderr.write("ads warmup failed: %s\n" % e)
    try:
        catch_wall_public.warm_cache()
    except Exception as e:
        sys.stderr.write("catch-wall cache warmup failed: %s\n" % e)
    brief.start_scheduler()
    try:
        freshwater.start_warmer()
    except Exception as e:
        sys.stderr.write("freshwater warmer failed to start: %s\n" % e)
    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    print("Coastal Brief map at http://%s:%s/" % (args.host, args.port), flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped", flush=True)


if __name__ == "__main__":
    main()
