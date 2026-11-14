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
    "radar_tile": 2 * 60 * 60,
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


# Only public site assets are served from the repo folder; source, config,
# docs, and test fixtures are not.
_STATIC_EXT = {".html", ".css", ".js", ".svg", ".png", ".jpg", ".jpeg", ".webp", ".ico",
               ".woff2", ".json", ".txt", ".xml", ".webmanifest", ".map"}
_STATIC_DENY_PREFIX = ("/.", "/admin", "/wind-lab.", "/lake.", "/tiles-lab.", "/docs/", "/tests/", "/scripts/", "/__pycache__/", "/requirements")


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


def _prune_cache() -> None:
    """Drop oldest cached files if the folder grows past the cap."""
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
    url = "https://api.weather.gov/alerts/active?area=NC"
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
                if mem.get("client") and signed_ok:
                    return mem["client"]
                msg = "Radar is unavailable right now."
                try:
                    err = json.loads(body.decode("utf-8")).get("error") or {}
                    code = err.get("code")
                    if code == 2009:
                        msg = "Radar coming soon"
                        return {"ok": False, "available": False, "reason": "coming_soon", "message": msg}
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
    if not weatherapi_key():
        return 503, "application/json; charset=utf-8", json.dumps({
            "ok": False, "reason": "coming_soon", "message": "Radar coming soon"
        }).encode("utf-8")
    if not _valid_radar_tile(z, x, y, t):
        return 400, "text/plain; charset=utf-8", b"invalid tile"
    # Cache by z/x/y/time only — never by the signed upstream URL.
    cache_key_url = "radar-cache://tile/%s/%s/%s/%s" % (z, x, y, t)
    cached = cache_get(cache_key_url)
    if cached:
        return cached
    meta = _refresh_radar_mem(force=False)
    if not meta.get("ok"):
        status = 503 if meta.get("reason") == "coming_soon" else 502
        return status, "application/json; charset=utf-8", json.dumps(meta).encode("utf-8")
    with RADAR_LOCK:
        template = _RADAR_MEM.get("tile_url") or ""
    if not template or "{z}" not in template or "{time}" not in template:
        return 502, "text/plain; charset=utf-8", b"radar tile template missing"
    url = template.replace("{z}", z).replace("{x}", x).replace("{y}", y).replace("{time}", t)
    status, ctype, body = fetch_url_quiet(url, tries=3)
    if status == 200 and body:
        with CACHE_LOCK:
            cache_put(cache_key_url, "radar_tile", status, ctype or "image/png", body)
    return status, ctype or "image/png", body


import conditions  # noqa: E402
import photos  # noqa: E402
import windgrid  # noqa: E402
import freshwater  # noqa: E402
import brief  # noqa: E402

# ---------------------------------------------------------------- private preview access
# /preview?key=<PREVIEW_KEY> sets an HttpOnly cookie that unlocks the flagged previews (/lake, /lab/wind,
# /lab/tiles, /brief) in that browser only. The key lives only in the PREVIEW_KEY env var on Render; the
# cookie holds an HMAC of it, so rotating the key locks every browser out. Without the key set, /preview is 404.
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
<p>These pages are unlocked for this browser for %d days. The public still gets “not found”, and nothing here is linked from the site.</p>
<a class="card" href="/lake"><b>Falls Lake</b><span>Freshwater dashboard: lake level vs guide curve, dam release, inflows, rain, river gauges</span></a>
<a class="card" href="/lake?region=jordan-lake"><b>Jordan Lake</b><span>Pool vs 216.0 ft guide curve, release plus local runoff, Haw inflow</span></a>
<a class="card" href="/lake?region=neuse-river"><b>Neuse River</b><span>Falls Dam to Goldsboro: stage, flow and NWS flood stages (Smithfield is stage only)</span></a>
<a class="card" href="/brief?region=crystal-coast"><b>Morning Brief · Crystal Coast</b><span>Today's brief, built from live readings</span></a>
<a class="card" href="/brief?region=hatteras"><b>Morning Brief · Hatteras</b><span>Today's brief, built from live readings</span></a>
<a class="card" href="/brief?region=falls-lake"><b>Morning Brief · Falls Lake</b><span>Freshwater version</span></a>
<a class="card" href="/lab/wind"><b>Wind flow</b><span>Animated model wind (NOAA GFS forecast)</span></a>
<a class="card" href="/lab/tiles"><b>Tile designs</b><span>The instrument tile prototype</span></a>
<p><a href="/preview?lock=1">Lock this browser again</a></p></main></body></html>""" % PREVIEW_DAYS

conditions.install(cache_get, cache_get_any, cache_put_ttl, lambda url: fetch_url(url, tries=2))


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

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
        if parsed.path == "/preview":
            return self._preview_route(parsed)
        if parsed.path == "/api/brief/wake":
            # Daily wake-up ping (GitHub Actions, 5:16 AM ET). Builds today's briefs if missing; returns no
            # brief content, so it publishes nothing. Idempotent: at most one build per region per day.
            # Runs when the brief is on (the default) or a preview key is set.
            if not (brief.flag_on() or _preview_secret()):
                return self.send_error(404, "not found")
            return self._json_private(brief.wake(include_fresh=freshwater.flag_on() or bool(_preview_secret())))
        if parsed.path in ("/catch-wall", "/catch-wall/"):
            return self._send_file(ROOT / "catch-wall.html", "text/html; charset=utf-8")
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
            return self._send_json(conditions.public_regions(), cache_s=300)
        if parsed.path == "/api/conditions":
            rid = (parse_qs(parsed.query or "").get("region") or [""])[0].strip()
            try:
                status, payload = conditions.assemble(rid or None)
            except Exception as e:  # keep the page up if one feed misbehaves
                sys.stderr.write("conditions failed: %s\n" % e)
                status, payload = 502, {"ok": False, "error": "Conditions are unavailable right now."}
            return self._send_json(payload, cache_s=60, status=status)
        if parsed.path in ("/coastal-life", "/coastal-life/", "/photos", "/photos/"):
            return self._send_file(ROOT / "catch-wall.html", "text/html; charset=utf-8")
        if parsed.path == "/api/photos/config":
            return self._send_json(photos.public_config(), cache_s=60)
        if parsed.path == "/api/photos":
            q = parse_qs(parsed.query or "")
            view = (q.get("view") or ["all"])[0]
            feat = (q.get("featured") or [""])[0] == "1"
            return self._send_json(photos.public_photos(view, feat), cache_s=60)
        if parsed.path in ("/admin", "/admin/"):
            if not photos.admin_configured():
                return self.send_error(404, "not found")
            return self._send_private(ROOT / "admin.html", "text/html; charset=utf-8")
        if parsed.path.startswith("/api/admin/"):
            return self._admin_get(parsed)
        if parsed.path.startswith("/fake-storage/approved/"):
            return self._fake_storage(parsed)
        if parsed.path in ("/lake", "/lake.js", "/api/freshwater"):
            # Private freshwater preview, off unless FRESHWATER_ENABLED=1. Not linked from the site.
            if not (freshwater.flag_on() or self._preview_ok()):
                return self.send_error(404, "not found")
            if parsed.path == "/lake":
                return self._send_private(ROOT / "lake.html", "text/html; charset=utf-8")
            if parsed.path == "/lake.js":
                return self._send_private(ROOT / "lake.js", "text/javascript; charset=utf-8")
            rid = (parse_qs(parsed.query).get("region") or ["falls-lake"])[0]
            status, payload = freshwater.assemble(rid)
            return self._send_json(payload, cache_s=0, status=status)
        if parsed.path in ("/brief", "/api/brief"):
            # Saltwater Morning Brief is on by default. MORNING_BRIEF_ENABLED=0/false/off is the
            # kill switch. Falls Lake stays private (freshwater flag or preview cookie).
            # Not linked from the homepage or header.
            pv = self._preview_ok()
            if not (brief.flag_on() or pv):
                return self.send_error(404, "not found")
            q = parse_qs(parsed.query)
            rid = (q.get("region") or [""])[0] or "crystal-coast"
            include_fresh = freshwater.flag_on() or pv
            status, b = brief.get(rid, include_fresh=include_fresh)
            if parsed.path == "/api/brief":
                return self._json_private(b, status)
            if status != 200:
                return self._send_private(None, "text/html; charset=utf-8", ("<p>%s</p>" % html.escape(b.get("error", ""))).encode(), status)
            water = b.get("waterType") or ""
            rid_final = b.get("regionId") or (b.get("region") or {}).get("id") or rid
            # Indexable only when the brief is on for the public and this is not a freshwater page.
            # Preview-only (kill switch) and Falls Lake stay noindex.
            public = brief.flag_on() and water != "freshwater" and rid_final != "falls-lake"
            # No ad creative is wired into the brief yet, so never reserve an
            # empty gap. When ads are hooked up, pass ads_on from get_ads()
            # (adsOn and mode != paused) and place the slot below advisories.
            body = brief.page(b, include_fresh=include_fresh, public=public, ads_on=False)
            robots = "index, follow" if public else "noindex, nofollow"
            return self._send_private(None, "text/html; charset=utf-8", body.encode(), robots=robots)
        if parsed.path in ("/lab/tiles", "/lab/tiles.js"):
            # Tile design prototype, off unless TILES_LAB_ENABLED=1. Not linked from the site.
            if not (_flag("TILES_LAB_ENABLED") or self._preview_ok()):
                return self.send_error(404, "not found")
            if parsed.path == "/lab/tiles":
                return self._send_private(ROOT / "tiles-lab.html", "text/html; charset=utf-8")
            return self._send_private(ROOT / "tiles-lab.js", "text/javascript; charset=utf-8")
        if parsed.path in ("/lab/wind", "/lab/wind.js", "/api/wind-grid"):
            # Prototype, off unless WIND_PARTICLES_ENABLED=1. Not linked from the site.
            pv = self._preview_ok()
            if not (_flag("WIND_PARTICLES_ENABLED") or pv):
                return self.send_error(404, "not found")
            if parsed.path == "/lab/wind":
                return self._send_private(ROOT / "wind-lab.html", "text/html; charset=utf-8")
            if parsed.path == "/lab/wind.js":
                return self._send_private(ROOT / "wind-lab.js", "text/javascript; charset=utf-8")
            g = windgrid.latest_grid()
            if pv and not _flag("WIND_PARTICLES_ENABLED"):
                return self._json_private(g, 200 if g.get("ok") else 502)
            return self._send_json(g, cache_s=600 if g.get("ok") else 60, status=200 if g.get("ok") else 502)
        if parsed.path == "/api/sst-time":
            return self._send_json(sst_latest_times(), cache_s=600)
        if parsed.path == "/api/radar/usage":
            return self._send_json(radar_usage_payload(), cache_s=0)
        if parsed.path == "/api/radar":
            status, payload = handle_radar_meta()
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
        ip = self.headers.get("CF-Connecting-IP") or (self.headers.get("X-Forwarded-For") or "").split(",")[0]
        return (ip or self.client_address[0] or "").strip()[:64]

    def _same_origin(self) -> bool:
        origin = self.headers.get("Origin")
        if not origin:
            return False
        host = (self.headers.get("X-Forwarded-Host") or self.headers.get("Host") or "").lower()
        return urlparse(origin).netloc.lower() == host

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
        if parsed.path == "/api/admin/session" and photos.admin_configured() and not csrf:
            return self._json_private({"ok": False})
        if not photos.admin_configured() or not csrf:
            return self._json_private({"ok": False, "error": "Sign in first."}, 401 if photos.admin_configured() else 404)
        if parsed.path == "/api/admin/list":
            status = (parse_qs(parsed.query or "").get("status") or ["pending"])[0]
            try:
                return self._json_private(photos.admin_list(status))
            except photos.StorageError as e:
                sys.stderr.write("admin list: %s\n" % e)
                return self._json_private({"ok": False, "error": "Storage error."}, 502)
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
        routes = ("/api/photos/submit", "/api/admin/login", "/api/admin/logout", "/api/admin/action")
        if parsed.path not in routes:
            return self._json_private({"ok": False, "error": "Not found."}, 404)
        # Flag off (or not configured): refuse before reading any body.
        if parsed.path == "/api/photos/submit" and not photos.uploads_active():
            return self._json_private({"ok": False, "error": "Not found."}, 404)
        if parsed.path != "/api/photos/submit" and not photos.admin_configured():
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
            return self._json_private({"ok": False, "error": "That file is larger than 15 MB."}, 413)
        body = self.rfile.read(length) if length else b""
        ip = self._client_ip()
        if parsed.path == "/api/photos/submit":
            status, payload = photos.handle_submit(self.headers.get("Content-Type", ""), body, ip)
            return self._json_private(payload, status)
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


    def _radar_tile(self, parsed):
        # /api/radar/tile/{z}/{x}/{y}.png?t=yyyyMMddHHmm
        m = re.fullmatch(r"/api/radar/tile/(\d+)/(\d+)/(\d+)(?:\.png)?", parsed.path)
        if not m:
            self.send_error(404, "invalid radar tile path")
            return
        qs = parse_qs(parsed.query or "")
        t = (qs.get("t") or [""])[0].strip()
        status, ctype, body = fetch_radar_tile(m.group(1), m.group(2), m.group(3), t)
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        ttl = TTL.get("radar_tile", 600) if status == 200 else 0
        if ttl:
            self.send_header("Cache-Control", "public, max-age=%s" % ttl)
            self._cache_header_sent = True
        else:
            self.send_header("Cache-Control", "no-store")
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
    brief.start_scheduler()
    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    print("Coastal Brief map at http://%s:%s/" % (args.host, args.port), flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped", flush=True)


if __name__ == "__main__":
    main()
