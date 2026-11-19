"""Gridded 10 m wind (U/V) from NOAA GFS 0.25° via the NOMADS GRIB filter.

PRIVATE, OFF BY DEFAULT (env WIND_PARTICLES_ENABLED or the preview cookie); feeds /lab/wind and /wind. Standard library only:
the NOMADS filter returns a sub-region with simple packing (GRIB2 data template
5.0) on a regular lat/lon grid (template 3.0), which is small enough to decode
here without eccodes. Values are a MODEL FORECAST, never observations.
"""
from __future__ import annotations

import datetime as dt
import math
import struct
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BBOX = {"toplat": 37.5, "bottomlat": 32.5, "leftlon": -80.0, "rightlon": -73.0}
FILTER = "https://nomads.ncep.noaa.gov/cgi-bin/filter_gfs_0p25_1hr.pl"
UA = "TheCoastalBrief/1.0 (wind prototype; thecoastalbrief.com)"

_cache: dict = {}
_lock = threading.Lock()


def _sm_int(b: bytes) -> int:
    """GRIB sign-magnitude integer."""
    v = int.from_bytes(b, "big")
    top = 1 << (len(b) * 8 - 1)
    return -(v & (top - 1)) if v & top else v


def decode(data: bytes) -> list[dict]:
    """Decode GRIB2 messages with grid template 3.0 and data template 5.0 only."""
    out, pos = [], 0
    while True:
        start = data.find(b"GRIB", pos)
        if start < 0:
            break
        if data[start + 7] != 2:
            raise ValueError("not GRIB2")
        total = int.from_bytes(data[start + 8:start + 16], "big")
        msg = data[start:start + total]
        i = 16
        rec: dict = {}
        grid = pack = None
        while i < len(msg) - 4:
            if msg[i:i + 4] == b"7777":
                break
            ln = int.from_bytes(msg[i:i + 4], "big")
            sec = msg[i + 4]
            s = msg[i:i + ln]
            if sec == 1:
                y = int.from_bytes(s[12:14], "big")
                rec["ref"] = dt.datetime(y, s[14], s[15], s[16], s[17], s[18], tzinfo=dt.timezone.utc)
            elif sec == 3:
                if int.from_bytes(s[12:14], "big") != 0:
                    raise ValueError("unsupported grid template")
                ni, nj = int.from_bytes(s[30:34], "big"), int.from_bytes(s[34:38], "big")
                la1, lo1 = _sm_int(s[46:50]) / 1e6, _sm_int(s[50:54]) / 1e6
                la2, lo2 = _sm_int(s[55:59]) / 1e6, _sm_int(s[59:63]) / 1e6
                di, dj = int.from_bytes(s[63:67], "big") / 1e6, int.from_bytes(s[67:71], "big") / 1e6
                grid = {"nx": ni, "ny": nj, "la1": la1, "lo1": lo1, "la2": la2, "lo2": lo2, "dx": di, "dy": dj, "scan": s[71]}
            elif sec == 4:
                rec["cat"], rec["num"] = s[9], s[10]
                unit, ft = s[17], int.from_bytes(s[18:22], "big")
                rec["fhour"] = ft if unit == 1 else ft / 60 if unit == 0 else None
            elif sec == 5:
                if int.from_bytes(s[9:11], "big") != 0:
                    raise ValueError("unsupported packing")
                pack = {"n": int.from_bytes(s[5:9], "big"), "R": struct.unpack(">f", s[11:15])[0],
                        "E": _sm_int(s[15:17]), "D": _sm_int(s[17:19]), "bits": s[19]}
            elif sec == 6:
                if s[5] != 255:
                    raise ValueError("bitmaps not supported")
            elif sec == 7:
                raw = s[5:]
                n, bits = pack["n"], pack["bits"]
                scale2, scale10 = 2.0 ** pack["E"], 10.0 ** pack["D"]
                if bits == 0:
                    vals = [pack["R"] / scale10] * n
                else:
                    big = int.from_bytes(raw, "big")
                    tot = len(raw) * 8
                    mask = (1 << bits) - 1
                    vals = [(pack["R"] + ((big >> (tot - bits * (k + 1))) & mask) * scale2) / scale10 for k in range(n)]
                rec["values"] = vals
            i += ln
        rec["grid"] = grid
        out.append(rec)
        pos = start + total
    return out


def _fetch(url: str) -> bytes:
    req = Request(url, headers={"User-Agent": UA})
    with urlopen(req, timeout=25) as r:
        return r.read()


KT_PER_MS = 1.943844
AHEAD_HOURS = (0, 3, 6, 9, 12)   # forecast-hour steps offered by /wind (each one NOMADS file, cached)
_DIRS = ("N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW")


def speed_kt(u: float, v: float) -> float:
    """Wind speed in knots from U/V in m/s."""
    return (u * u + v * v) ** 0.5 * KT_PER_MS


def from_deg(u: float, v: float) -> float:
    """Meteorological direction the wind blows FROM, degrees true (0 = N, 90 = E)."""
    return (math.degrees(math.atan2(-u, -v)) + 360.0) % 360.0


def compass(deg: float) -> str:
    return _DIRS[int(round(deg / 22.5)) % 16]


def sample(g: dict, lat: float, lon: float):
    """Bilinear U/V (m/s) at lat/lon from a latest_grid() payload; None outside the grid.
    Mirrors uvAt() in wind-lab.js, so tests can hold the two to the same raw nodes."""
    north = (g["scan"] & 0x40) == 0
    nx, ny = g["nx"], g["ny"]
    fx = (lon - g["lo1"]) / g["dx"]
    fy = (g["la1"] - lat) / g["dy"] if north else (lat - g["la1"]) / g["dy"]
    if not (0 <= fx <= nx - 1 and 0 <= fy <= ny - 1):
        return None
    x0, y0 = int(fx), int(fy)
    x1, y1 = min(x0 + 1, nx - 1), min(y0 + 1, ny - 1)
    tx, ty = fx - x0, fy - y0
    out = []
    for arr in (g["u"], g["v"]):
        out.append(arr[y0 * nx + x0] * (1 - tx) * (1 - ty) + arr[y0 * nx + x1] * tx * (1 - ty)
                   + arr[y1 * nx + x0] * (1 - tx) * ty + arr[y1 * nx + x1] * tx * ty)
    return out[0], out[1]


def latest_grid(now: float | None = None, ahead: int = 0) -> dict:
    """Newest GFS run with the forecast hour nearest to now (+ ahead hours). Cached 30 minutes
    per step. ahead must be one of AHEAD_HOURS; anything else is treated as 0."""
    now = now or time.time()
    ahead = ahead if ahead in AHEAD_HOURS else 0
    key = "v" if ahead == 0 else "v+%d" % ahead
    with _lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < 1800:
            return hit[1]
    utc = dt.datetime.fromtimestamp(now, dt.timezone.utc)
    target = utc + dt.timedelta(hours=ahead)
    cycle = utc.replace(minute=0, second=0, microsecond=0, hour=(utc.hour // 6) * 6)
    last_err = "no run found"
    for back in range(0, 4):                  # current cycle, then up to 18 h older
        run = cycle - dt.timedelta(hours=6 * back)
        fh = max(0, min(120, round((target - run).total_seconds() / 3600)))
        q = {"dir": "/gfs.%s/%02d/atmos" % (run.strftime("%Y%m%d"), run.hour),
             "file": "gfs.t%02dz.pgrb2.0p25.f%03d" % (run.hour, fh),
             "var_UGRD": "on", "var_VGRD": "on", "lev_10_m_above_ground": "on", "subregion": ""}
        q.update({k: str(v) for k, v in BBOX.items()})
        try:
            msgs = decode(_fetch(FILTER + "?" + urlencode(q)))
        except (HTTPError, URLError, ValueError, OSError) as e:
            last_err = str(e)[:120]
            continue
        u = next((m for m in msgs if m.get("cat") == 2 and m.get("num") == 2), None)
        v = next((m for m in msgs if m.get("cat") == 2 and m.get("num") == 3), None)
        if not (u and v and u.get("grid")):
            last_err = "U/V missing"
            continue
        g = u["grid"]
        lo1 = g["lo1"] - 360 if g["lo1"] > 180 else g["lo1"]
        valid = u["ref"] + dt.timedelta(hours=u["fhour"] or 0)
        out = {
            "ok": True, "kind": "model forecast",
            "source": "NOAA NCEP GFS 0.25°, 10 m wind, via NOMADS",
            "run": u["ref"].strftime("%Y-%m-%dT%H:%MZ"), "valid": valid.strftime("%Y-%m-%dT%H:%MZ"),
            "forecastHour": u["fhour"], "units": "m/s",
            "nx": g["nx"], "ny": g["ny"], "la1": g["la1"], "lo1": lo1, "dx": g["dx"], "dy": g["dy"],
            "scan": g["scan"], "ahead": ahead,
            "u": [round(x, 2) for x in u["values"]], "v": [round(x, 2) for x in v["values"]],
        }
        with _lock:
            _cache[key] = (now, out)
        return out
    return {"ok": False, "error": "Model wind is unavailable right now.", "detail": last_err}
