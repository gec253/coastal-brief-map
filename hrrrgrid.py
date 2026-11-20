"""NOAA HRRR 3 km 10 m wind for the private /wind viewer (?model=hrrr), standard library only.

The NOMADS grib filter returns a sub-region that keeps HRRR's native Lambert conformal grid (GRIB2 grid
template 3.30) with simple packing (5.0). We decode it (chunked unpack, ~50x faster than one big int),
regrid bilinearly to a regular 0.025° lat/lon grid over the viewer box, and rotate the grid-relative U/V
to true north (alpha = n * (lon - LoV), n = sin(Latin1)). The payload has the same shape as
windgrid.latest_grid(), so the browser engine is unchanged. One model per payload, never blended: if HRRR
is stale, missing or fails sanity checks, the GFS payload is returned and labelled as a fallback.
"""
from __future__ import annotations

import datetime as dt
import math
import struct
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode

import windgrid

FILTER = "https://nomads.ncep.noaa.gov/cgi-bin/filter_hrrr_2d.pl"
# Fetch a little wider than the viewer box: HRRR rows/columns are curved in lat/lon, so the exact box
# leaves the corners uncovered. The output grid is exactly the GFS box at 0.025° (281 x 201).
FETCH_BOX = {"toplat": 38.0, "bottomlat": 32.0, "leftlon": -80.5, "rightlon": -72.5}
OUT_BOX = (37.5, 32.5, -80.0, -73.0)          # north, south, west, east
RES = 0.025
MAX_RUN_AGE_H = 3                               # older than this -> GFS fallback
POSTED_AFTER_MIN = 50                           # NOMADS posts f00-f01 ~49-56 min after the cycle hour (measured)
LABEL = "HRRR 3 km"
SOURCE = "NOAA NCEP HRRR 3 km, 10 m wind, via NOMADS (regridded 0.025°, rotated to true north)"
_cache: dict = {}
_lock = threading.Lock()
_fetch = windgrid._fetch                        # same User-Agent and timeout as GFS


def _sm(b: bytes) -> int:
    v = int.from_bytes(b, "big")
    top = 1 << (len(b) * 8 - 1)
    return -(v - top) if v & top else v


def unpack(raw: bytes, n: int, bits: int) -> list[int]:
    """n unsigned `bits`-bit integers, MSB first. Eight values fill exactly `bits` bytes, so each chunk is
    one small int (fast) instead of shifting one huge int per value."""
    if bits == 0:
        return [0] * n
    out: list[int] = []
    mask = (1 << bits) - 1
    shifts = [bits * (7 - k) for k in range(8)]
    fb = int.from_bytes
    full = (n // 8) * bits
    for off in range(0, full, bits):
        w = fb(raw[off:off + bits], "big")
        out.extend([(w >> s) & mask for s in shifts])
    rem = n - len(out)
    if rem:
        tail = raw[full:full + (rem * bits + 7) // 8]
        w, tb = fb(tail, "big"), len(tail) * 8
        out.extend([(w >> (tb - bits * (k + 1))) & mask for k in range(rem)])
    return out


def decode(data: bytes) -> list[dict]:
    """GRIB2 messages with grid template 3.30 (Lambert conformal) and data template 5.0 only."""
    out, pos = [], 0
    while True:
        start = data.find(b"GRIB", pos)
        if start < 0:
            break
        if data[start + 7] != 2:
            raise ValueError("not GRIB2")
        total = int.from_bytes(data[start + 8:start + 16], "big")
        msg = data[start:start + total]
        if len(msg) < total or msg[-4:] != b"7777":
            raise ValueError("truncated GRIB2 message")
        i, rec, pack = 16, {}, None
        while i < len(msg) - 4:
            ln = int.from_bytes(msg[i:i + 4], "big")
            sec, s = msg[i + 4], msg[i:i + ln]
            if sec == 1:
                rec["ref"] = dt.datetime(int.from_bytes(s[12:14], "big"), s[14], s[15], s[16], s[17], s[18], tzinfo=dt.timezone.utc)
            elif sec == 3:
                if int.from_bytes(s[12:14], "big") != 30:
                    raise ValueError("unsupported grid template")
                rec["grid"] = {
                    "shape": s[14], "nx": int.from_bytes(s[30:34], "big"), "ny": int.from_bytes(s[34:38], "big"),
                    "la1": _sm(s[38:42]) / 1e6, "lo1": int.from_bytes(s[42:46], "big") / 1e6, "flags": s[46],
                    "lad": _sm(s[47:51]) / 1e6, "lov": int.from_bytes(s[51:55], "big") / 1e6,
                    "dx": int.from_bytes(s[55:59], "big") / 1e3, "dy": int.from_bytes(s[59:63], "big") / 1e3,
                    "scan": s[64], "latin1": _sm(s[65:69]) / 1e6, "latin2": _sm(s[69:73]) / 1e6,
                }
            elif sec == 4:
                rec["cat"], rec["num"] = s[9], s[10]
                unit, ft = s[17], int.from_bytes(s[18:22], "big")
                rec["fhour"] = ft if unit == 1 else ft / 60 if unit == 0 else None
            elif sec == 5:
                if int.from_bytes(s[9:11], "big") != 0:
                    raise ValueError("unsupported packing")
                pack = (int.from_bytes(s[5:9], "big"), struct.unpack(">f", s[11:15])[0], _sm(s[15:17]), _sm(s[17:19]), s[19])
            elif sec == 6:
                if s[5] != 255:
                    raise ValueError("bitmaps not supported")
            elif sec == 7:
                n, R, E, D, bits = pack
                s2, s10 = 2.0 ** E, 10.0 ** D
                rec["values"] = [(R + x * s2) / s10 for x in unpack(s[5:], n, bits)]
            i += ln
        out.append(rec)
        pos = start + total
    return out


class Lambert:
    """Spherical Lambert conformal (tangent or secant) matching the GRIB2 3.30 grid of one message."""

    def __init__(self, g: dict):
        if g["shape"] != 6:
            raise ValueError("unexpected earth shape")
        self.R = 6371229.0
        D = math.pi / 180
        p1, p2 = g["latin1"] * D, g["latin2"] * D
        if abs(p1 - p2) < 1e-9:
            n = math.sin(p1)
        else:
            n = math.log(math.cos(p1) / math.cos(p2)) / math.log(math.tan(math.pi / 4 + p2 / 2) / math.tan(math.pi / 4 + p1 / 2))
        self.n = n
        self.F = math.cos(p1) * math.tan(math.pi / 4 + p1 / 2) ** n / n
        self.lov = g["lov"] - 360 if g["lov"] > 180 else g["lov"]
        self.g = g
        lo1 = g["lo1"] - 360 if g["lo1"] > 180 else g["lo1"]
        self.x0, self.y0 = self.xy(g["la1"], lo1)
        self.south_first = bool(g["scan"] & 0x40)

    def xy(self, lat: float, lon: float):
        D = math.pi / 180
        rho = self.R * self.F / math.tan(math.pi / 4 + lat * D / 2) ** self.n
        th = self.n * (lon - self.lov) * D
        return rho * math.sin(th), -rho * math.cos(th)

    def ij(self, lat: float, lon: float):
        x, y = self.xy(lat, lon)
        fi = (x - self.x0) / self.g["dx"]
        fj = (y - self.y0) / self.g["dy"]
        return fi, (fj if self.south_first else -fj)

    def alpha(self, lon: float) -> float:
        """Angle (radians) from true north to grid north at this longitude."""
        return self.n * (lon - self.lov) * math.pi / 180


def to_earth(ug: float, vg: float, alpha: float):
    c, s = math.cos(alpha), math.sin(alpha)
    return c * ug + s * vg, -s * ug + c * vg


def regrid(u: dict, v: dict, res: float = RES, box=OUT_BOX):
    """Bilinear regrid of grid-relative U/V to a regular north-first lat/lon grid, rotated to true north.
    Returns (meta, u, v, missing); missing points are None."""
    g = u["grid"]
    if v["grid"] != g:
        raise ValueError("U/V grids differ")
    if not (g["flags"] & 0x08):
        raise ValueError("expected grid-relative winds")
    lam = Lambert(g)
    nx, ny = g["nx"], g["ny"]
    U, V = u["values"], v["values"]
    north, south, west, east = box
    tnx, tny = int(round((east - west) / res)) + 1, int(round((north - south) / res)) + 1
    ou, ov, miss = [], [], 0
    alphas = [lam.alpha(west + i * res) for i in range(tnx)]
    for jj in range(tny):
        lat = north - jj * res
        for ii in range(tnx):
            lon = west + ii * res
            fi, fj = lam.ij(lat, lon)
            i0, j0 = int(math.floor(fi)), int(math.floor(fj))
            if not (0 <= i0 < nx - 1 and 0 <= j0 < ny - 1):
                ou.append(None); ov.append(None); miss += 1
                continue
            ti, tj, k = fi - i0, fj - j0, j0 * nx + i0
            w00, w10, w01, w11 = (1 - ti) * (1 - tj), ti * (1 - tj), (1 - ti) * tj, ti * tj
            ug = U[k] * w00 + U[k + 1] * w10 + U[k + nx] * w01 + U[k + nx + 1] * w11
            vg = V[k] * w00 + V[k + 1] * w10 + V[k + nx] * w01 + V[k + nx + 1] * w11
            ue, ve = to_earth(ug, vg, alphas[ii])
            ou.append(round(ue, 1)); ov.append(round(ve, 1))
    meta = {"nx": tnx, "ny": tny, "la1": north, "lo1": west, "dx": res, "dy": res, "scan": 0}
    return meta, ou, ov, miss


def sane(u: list, v: list, miss: int) -> str | None:
    """None if usable, else the reason."""
    if miss > 0.001 * len(u):
        return "grid does not cover the box"
    for arr in (u, v):
        for x in arr:
            if x is not None and not (-80.0 < x < 80.0):
                return "wind out of range"
    return None


def build(data: bytes, now: float | None = None) -> dict:
    msgs = decode(data)
    u = next((m for m in msgs if m.get("cat") == 2 and m.get("num") == 2), None)
    v = next((m for m in msgs if m.get("cat") == 2 and m.get("num") == 3), None)
    if not (u and v and u.get("grid") and u.get("values") and v.get("values")):
        raise ValueError("U/V missing")
    meta, ou, ov, miss = regrid(u, v)
    why = sane(ou, ov, miss)
    if why:
        raise ValueError(why)
    valid = u["ref"] + dt.timedelta(hours=u["fhour"] or 0)
    out = {"ok": True, "kind": "model forecast", "model": "hrrr", "modelLabel": LABEL, "source": SOURCE,
           "run": u["ref"].strftime("%Y-%m-%dT%H:%MZ"), "valid": valid.strftime("%Y-%m-%dT%H:%MZ"),
           "forecastHour": u["fhour"], "units": "m/s"}
    out.update(meta)
    out["u"], out["v"] = ou, ov
    return out


def _max_fh(run: dt.datetime) -> int:
    return 48 if run.hour % 6 == 0 else 18


def candidates(now: float, ahead: int):
    """(run, fh) pairs to try, newest run first, within MAX_RUN_AGE_H and the run's forecast length.
    The target valid time is the nearest whole hour to now + ahead."""
    utc = dt.datetime.fromtimestamp(now, dt.timezone.utc)
    target = (utc + dt.timedelta(hours=ahead, minutes=30)).replace(minute=0, second=0, microsecond=0)
    cycle = utc.replace(minute=0, second=0, microsecond=0)
    if (utc - cycle).total_seconds() < POSTED_AFTER_MIN * 60:
        cycle -= dt.timedelta(hours=1)          # this hour's run isn't posted yet: skip a doomed request
    out = []
    for back in range(0, MAX_RUN_AGE_H):
        run = cycle - dt.timedelta(hours=back)
        fh = int(round((target - run).total_seconds() / 3600))
        if 0 <= fh <= _max_fh(run):
            out.append((run, fh))
    return out


def _url(run: dt.datetime, fh: int) -> str:
    q = {"dir": "/hrrr.%s/conus" % run.strftime("%Y%m%d"), "file": "hrrr.t%02dz.wrfsfcf%02d.grib2" % (run.hour, fh),
         "var_UGRD": "on", "var_VGRD": "on", "lev_10_m_above_ground": "on", "subregion": ""}
    q.update({k: str(v) for k, v in FETCH_BOX.items()})
    return FILTER + "?" + urlencode(q)


def fallback(ahead: int, reason: str) -> dict:
    """The GFS payload, explicitly labelled as standing in for HRRR (never blended)."""
    g = dict(windgrid.latest_grid(ahead=ahead))
    g.update({"model": "gfs", "modelLabel": "GFS 0.25°", "requested": "hrrr", "fallback": "HRRR unavailable", "fallbackReason": reason[:120]})
    return g


def latest_grid(now: float | None = None, ahead: int = 0) -> dict:
    """Newest usable HRRR run for the valid hour nearest now + ahead, or a labelled GFS fallback.
    Cache: per step for 10 minutes (HRRR runs hourly; a new run appears ~50 min after the hour), and the
    decoded grid per (run, forecast hour) so a refresh that lands on the same file doesn't re-download.
    Failures are cached for 5 minutes so NOMADS isn't hammered (it allows 120 requests/min per IP)."""
    now = now or time.time()
    ahead = ahead if ahead in windgrid.AHEAD_HOURS else 0
    key = ("step", ahead)
    with _lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < hit[1]:
            return hit[2]
    last = "no HRRR run in the last %d h" % MAX_RUN_AGE_H
    for run, fh in candidates(now, ahead):
        fkey = ("file", run.strftime("%Y%m%d%H"), fh)
        with _lock:
            done = _cache.get(fkey)
        if done:
            out = dict(done, ahead=ahead)
        else:
            try:
                out = build(_fetch(_url(run, fh)))
            except (HTTPError, URLError, ValueError, OSError, KeyError, IndexError) as e:
                last = str(e)[:120] or e.__class__.__name__
                continue
            with _lock:
                for k in [k for k in _cache if k[0] == "file" and k[1] < (run - dt.timedelta(hours=MAX_RUN_AGE_H)).strftime("%Y%m%d%H")]:
                    del _cache[k]
                _cache[fkey] = out
            out = dict(out, ahead=ahead)
        with _lock:
            _cache[key] = (now, 600, out)
        return out
    out = fallback(ahead, last)
    with _lock:
        _cache[key] = (now, 300, out)
    return out
