"""Cookie-gated homepage concept previews: /preview/home-heritage, -editorial, -hybrid.

Private sprint concepts only. One shared data path for all three:
conditions.assemble() (the same call /api/conditions and the public
homepage's first paint use) for saltwater, and freshwater.assemble() (the
same call /api/freshwater and /lake use) for the lakes and the Neuse.
Instruments show only the "safe" fields from Data's glance contract
(docs/glance-data-contract.md section 6, data/glance-contract 3d4abf5).
Missing values use the contract's existing fallback copy. Nothing here
writes data, and the three concepts differ only in presentation.

Photos come only from the approved Catch Wall / Coastal Life set, credited
with exactly what is stored. Empty slots say they are awaiting real material.
"""
from __future__ import annotations

import html
import math
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import conditions
import homepage_boot
import photo_rotation
import wave_intro

ROOT = Path(__file__).resolve().parent
DIR = ROOT / "preview" / "sprint-home"
CONCEPTS = ("heritage", "editorial", "hybrid")
ROUTES = {"/preview/home-%s" % c: c for c in CONCEPTS}

# Approved photographs (Catch Wall / Coastal Life), used only while approved.
LEAD_PHOTO_ID = "3e41ed83-23a3-4032-8a5f-c7957b788e3f"   # Red Drum, New Bern · Neuse River
WIDE_PHOTO_ID = "bcd8fba5-28d9-4db8-a41a-65a5fd2ef26b"   # Striped Bass, Roanoke River
FRESH_PHOTO_ID = "a225cada-6666-40ed-9640-4eba26905970"  # Weldon
LIFE_PHOTO_ID = "caec2542-d57c-40bd-ab1f-b57bb19a55a1"   # Rx Chicken& Oysters
LIFE2_PHOTO_ID = "89eef7f7-9d80-41ad-b1e5-96985bcaa73d"  # Rx Chicken & Oysters (diner)

# Bodie Island Lighthouse at sunrise: NPGallery asset, PhotoCredit "Cape Hatteras
# National Seashore", constraints "Public domain: Full Granting Rights".
# Verified 15 Nov 2026; see preview/sprint-home/CREDITS.md. Served locally.
PHOTO_DIR = DIR / "photos"
PHOTO_ROUTE = "/preview/sprint-home/photos/"
# Public homepage (/) serves the same approved files from this path. No listing; strict names only.
PUBLIC_PHOTO_ROUTE = "/home-photos/"
BODIE = {
    "id": "bodie-sunrise", "local": True, "w": 1600, "h": 1200,
    "base": PHOTO_ROUTE + "bodie-sunrise", "widths": (800, 1280),
    "alt": "Bodie Island Lighthouse and keepers' quarters at sunrise, Cape Hatteras National Seashore",
    "title": "Bodie Island Lighthouse at sunrise",
    "location": "Bodie Island, Cape Hatteras National Seashore", "region": "October 13, 2023",
    "credit_line": "Photo: National Park Service, Cape Hatteras National Seashore (public domain)",
    "source_url": "https://npgallery.nps.gov/AssetDetail/3011f0d3-bb6a-4b82-8fef-ca0b654e8040",
}

FALLS_SRC = "https://www.flickr.com/photos/sergesegal/52741376400/"
CC_BY_SA_2 = "https://creativecommons.org/licenses/by-sa/2.0/"
FALLS = {
    "id": "falls-lake-pier", "local": True, "w": 1280, "h": 960,
    "base": PHOTO_ROUTE + "falls-lake-pier", "widths": (800, 1280),
    "alt": "People on a wooden fishing pier at Falls Lake, with still water and woods beyond",
    "title": "Fishing pier, Falls Lake, North Carolina",
    "region": "March 5, 2023",
    "hz_class": "hz-lake",
    "credit_line": "Photo: Sergiy Galyonkin, CC BY-SA 2.0 (cropped and adjusted)",
    "credit_html": (
        'Photo: <a class="cr-a" href="%s" rel="noopener">Sergiy Galyonkin</a>, '
        '<a class="cr-a" href="%s" rel="noopener license">CC BY-SA 2.0</a> (cropped and adjusted)'
    ) % (FALLS_SRC, CC_BY_SA_2),
    "source_url": FALLS_SRC,
}

# Copy reused verbatim from the glance contract (section 2.3 / 3.4).
NOT_REPORTING = "Not reporting"
GUST_MISSING = "gust not reported"
SWELL_OFF = "Swell data unavailable for this area right now"
TIDE_OFF = "Tide predictions are unavailable right now."
MARINE_OFF = "The NWS marine forecast is unavailable right now."
POINT_OFF = "The NWS forecast is unavailable right now. See weather.gov/mhx."
FRESH_POINT_OFF = "NWS forecast unavailable."
ALERTS_OFF = ("Alerts unavailable", "Could not check NWS alerts. See weather.gov before heading out.")
PAYLOAD_OFF = "Readings unavailable"
LAKE_OFF = "USGS lake elevation is not available right now."
RELEASE_OFF = "USGS flow below the dam is not available right now."
RAIN_OFF = "USGS rain gauge at the dam is not reporting."
STAGE_OFF = "Stage is not available from USGS right now."
FRESH_WT_OFF = "No current USGS water temperature at this location."

AWAITING = "Awaiting real material"


def _esc(s, quote: bool = False) -> str:
    return html.escape("" if s is None else str(s), quote=quote)


_num = homepage_boot._is_num
_r0 = homepage_boot._round0
_fmt = homepage_boot._fmt
et_time = homepage_boot.et_time


def _vals(r):
    return (r or {}).get("values") or {}


def _state(r) -> str:
    st = (r or {}).get("status")
    if st == "ok":
        return "ok"
    if st == "stale":
        return "stale"
    return "off"


def _station(r) -> str:
    s = (r or {}).get("station") or {}
    name = s.get("name") or ""
    sid = s.get("id") or ""
    out = name + ((" · " + sid) if sid else "")  # id kept; CSS may truncate
    if _num(s.get("distanceMi")) and s.get("distanceMi") >= 15 and " mi " not in name:
        out += " · %s mi %s" % (_r0(s["distanceMi"]), s.get("bearingFromAnchor") or "")
    return out.strip()


def _tile(**kw) -> dict:
    base = {
        "id": "", "name": "", "kind": "Observed", "state": "ok", "dir": "", "num": "", "unit": "",
        "sub": "", "src": "", "when": "", "dial": None, "off": NOT_REPORTING, "note": "",
    }
    base.update(kw)
    return base


# ---------------------------------------------------------------- saltwater

def _wind_tile(r, name="Wind", tid="wind") -> dict:
    st = _state(r)
    v = _vals(r) if st != "off" else {}
    spd, gust = v.get("speedKt"), v.get("gustKt")
    if st != "off" and not _num(spd) and _num(gust):
        # Gust-only: the brief's measured-wind phrasing; no sustained number is invented.
        return _tile(id=tid, name=name, state=st, num="", unit="",
                     sub="gusting %s kt (sustained speed not reported)" % _r0(gust),
                     src=_station(r), when=et_time(r.get("time")), off="")
    if st == "off" or not _num(spd):
        return _tile(id=tid, name=name, state="off", src=_station(r))
    t = _tile(
        id=tid, name=name, state=st, dir=v.get("dirCompass") or "", num=str(_r0(spd)), unit="kt",
        sub="" if _num(gust) else GUST_MISSING,
        src=_station(r), when=et_time(r.get("time")),
        dial=v.get("dirDeg") if _num(v.get("dirDeg")) else None,
    )
    if _num(gust):
        t["gust"] = str(_r0(gust))
    return t


def _seas_tile(r) -> dict:
    st = _state(r)
    v = _vals(r)
    if st == "off" or not _num(v.get("heightFt")):
        return _tile(id="seas", name="Seas", state="off", src=_station(r), note="Combined wave height")
    bits = []
    if _num(v.get("dominantPeriodS")):
        bits.append("%s s dominant" % _r0(v["dominantPeriodS"]))
    if v.get("meanDirCompass"):
        bits.append("from " + v["meanDirCompass"])
    return _tile(id="seas", name="Seas", state=st, num=_fmt(v["heightFt"], 1), unit="ft",
                 sub=" · ".join(bits), src=_station(r), when=et_time(r.get("time")),
                 note="Combined wave height")


def _swell_tile(r) -> dict:
    st = _state(r)
    v = _vals(r)
    if st == "off" or not _num(v.get("heightFt")):
        return _tile(id="swell", name="Swell", state="off", off=SWELL_OFF, src=_station(r))
    bits = []
    if _num(v.get("periodS")):
        bits.append("%s s" % _r0(v["periodS"]))
    if v.get("dirCompass"):
        bits.append("from " + v["dirCompass"])
    return _tile(id="swell", name="Swell", state=st, num=_fmt(v["heightFt"], 1), unit="ft",
                 sub=" · ".join(bits), src=_station(r), when=et_time(r.get("time")),
                 note="Split from the wave spectrum")


def _temp_tile(r, name, tid, note="") -> dict:
    st = _state(r)
    v = _vals(r)
    if st == "off" or not _num(v.get("f")):
        return _tile(id=tid, name=name, state="off", src=_station(r), note=note)
    return _tile(id=tid, name=name, state=st, num=str(_r0(v["f"])), unit="°F",
                 src=_station(r), when=et_time(r.get("time")), note=note)


_PHOTO_NAME = re.compile(r"^[a-z0-9-]+-(800|1280)\.(avif|webp)$")


def photo_path(url_path: str, route: str = PHOTO_ROUTE):
    """Local photo for a request path under route, or None. Strict names only."""
    if not url_path.startswith(route):
        return None
    name = url_path[len(route):]
    if not _PHOTO_NAME.match(name):
        return None
    path = PHOTO_DIR / name
    return path if path.is_file() else None


def offshore_where(r) -> str:
    """'Buoy 41159 · 37 mi SSW of Beaufort Inlet' from station metadata only."""
    s = (r or {}).get("station") or {}
    sid = s.get("id") or ""
    head = ("Buoy %s" % sid) if sid else "Offshore buoy"
    if _num(s.get("distanceMi")):
        where = "%s mi %s" % (_r0(s["distanceMi"]), s.get("bearingFromAnchor") or "")
        if s.get("anchor"):
            where = where.rstrip() + " of " + s["anchor"]
        return head + " · " + where.strip()
    return head + " · distance offshore not recorded"


def inshore_label(r) -> str:
    """Design label: 'Inshore water · Beaufort, Duke Marine Lab'. Station metadata only."""
    name = ((r or {}).get("station") or {}).get("name") or ""
    return "Inshore water" + ((" · " + name) if name else "")


def offshore_label(r) -> str:
    """Design label: 'Offshore water · buoy 41159, 37 mi SSW of Beaufort Inlet'.

    The distance is conditions.station_info's great-circle distance from the
    region anchor to the official NDBC position, rounded to whole miles."""
    s = (r or {}).get("station") or {}
    out = "Offshore water · " + (("buoy %s" % s["id"]) if s.get("id") else "offshore buoy")
    if _num(s.get("distanceMi")):
        out += ", %s mi %s" % (_r0(s["distanceMi"]), s.get("bearingFromAnchor") or "")
        out = out.rstrip()
        if s.get("anchor"):
            out += " of " + s["anchor"]
    return out


def _water_tile(R) -> dict:
    inshore = R.get("waterTemp")
    off = R.get("waterTempOffshore")
    if _state(inshore) != "off":
        t = _temp_tile(inshore, "Water", "water", note="Inshore station")
        t["label"] = inshore_label(inshore)
        ov = _vals(off)
        if _state(off) != "off" and _num(ov.get("f")):
            os_ = (off or {}).get("station") or {}
            dist = (" (%s mi %s)" % (_r0(os_["distanceMi"]), os_.get("bearingFromAnchor") or "")) if _num(os_.get("distanceMi")) else ""
            t["sub"] = "Offshore buoy %s%s: %s°F" % (os_.get("id") or "", dist.replace(" )", ")"), _r0(ov["f"]))
            if _state(off) == "stale":
                # An old buoy reading must not ride along looking current next to a fresh inshore one.
                t["sub"] += " (stale, last report %s)" % et_time(off.get("time"))
            t["offshore_label"] = offshore_label(off)
            t["off_read"] = {
                "num": str(_r0(ov["f"])),
                "unit": "°F",
                "src": offshore_where(off),
                "when": et_time(off.get("time")),
            }
        return t
    if _state(off) != "off":
        # No inshore sensor here (Nags Head, Emerald Isle, Topsail): the offshore
        # buoy is shown, labelled, with its ID and distance, and a distinct tile.
        t = _temp_tile(off, "Water", "water", note="Offshore buoy, no inshore sensor here")
        t["offshore"] = True
        t["label"] = offshore_label(off)
        t["src"] = offshore_where(off)
        return t
    return _tile(id="water", name="Water", state="off", note="Inshore station")


def _pressure_tile(r) -> dict:
    st = _state(r)
    v = _vals(r)
    if st == "off" or not _num(v.get("inHg")):
        return _tile(id="pressure", name="Barometer", state="off", src=_station(r))
    sub = ""
    if v.get("trend") and _num(v.get("change3hInHg")):
        sub = "%s · %+.2f in 3 h" % (v["trend"].capitalize(), v["change3hInHg"])
    elif v.get("trend"):
        sub = v["trend"].capitalize()
    return _tile(id="pressure", name="Barometer", state=st, num="%.2f" % v["inHg"], unit="inHg",
                 sub=sub, src=_station(r), when=et_time(r.get("time")))


def _now_ms() -> float:
    return datetime.now(timezone.utc).timestamp() * 1000.0


def _tide_tile(tides: dict) -> dict:
    tides = tides or {}
    now = _now_ms()
    evs = [e for e in (tides.get("events") or []) if _num(e.get("t")) and e["t"] > now]
    st = tides.get("station") or {}
    src = "Predictions: " + (st.get("name") or "") + ((" · " + st["id"]) if st.get("id") else "")
    if tides.get("status") != "ok" or not evs:
        return _tile(id="tide", name="Tide", kind="Predicted", state="off", off=TIDE_OFF, src=src)
    ev = evs[0]
    clock = homepage_boot._clock(ev["t"])
    hm, ampm = clock.split(" ") if " " in clock else (clock, "")
    nxt = evs[1] if len(evs) > 1 else None
    sub = "%s ft %s" % (_fmt(ev.get("v"), 1), tides.get("datum") or "") if _num(ev.get("v")) else ""
    then = ""
    if nxt:
        then = "Then %s %s ET%s" % ("high" if nxt.get("type") == "H" else "low", homepage_boot._clock(nxt["t"]),
                                    (" · %s ft" % _fmt(nxt.get("v"), 1)) if _num(nxt.get("v")) else "")
    t = _tile(id="tide", name="Next high" if ev.get("type") == "H" else "Next low", kind="Predicted",
              num=hm, unit=ampm + " ET", sub=sub.strip(), src=src, when="")
    t["then"] = then
    cs = tides.get("curveStation") or {}
    if cs.get("name"):
        # Jennette's Pier publishes highs and lows only; the 6-minute curve is Duck Pier's.
        t["curve_from"] = cs["name"]
        t["src"] += " · curve from %s%s" % (cs["name"], (" · " + cs["id"]) if cs.get("id") else "")
    obs = tides.get("observed")
    if isinstance(obs, dict) and obs.get("status") in ("ok", "stale"):
        lt = obs.get("latest") or {}
        if _num(lt.get("v")):
            os_ = obs.get("station") or {}
            if os_.get("id") and os_.get("id") != st.get("id"):
                # Observed level from a different gauge (Nags Head: Duck Pier). Say where, and how far.
                where = os_.get("name") or os_["id"]
                if _num(os_.get("distanceMi")):
                    where += " (%s mi %s)" % (_r0(os_["distanceMi"]), os_.get("bearingFromAnchor") or "")
                    where = where.replace(" )", ")")
                line = "Observed at %s: %s ft" % (where, _fmt(lt["v"], 1))
                if _num(lt.get("diff")):
                    line += ", %+.1f vs predicted there" % lt["diff"]
            else:
                line = "Observed %s ft" % _fmt(lt["v"], 1)
                if _num(lt.get("diff")):
                    line += ", %+.1f vs predicted" % lt["diff"]
            t["obs"] = line
            t["when"] = "· observed level preliminary, " + et_time(obs.get("time"))
            ot = homepage_boot._to_dt(obs.get("time"))
            if ot:
                t["obs_pt"] = (ot.timestamp() * 1000, float(lt["v"]))
    t["curve"] = tides.get("curve") or []
    t["events"] = tides.get("events") or []
    return t


def _alerts(a) -> dict:
    a = a or {}
    items = a.get("items") or []
    if items:
        out = []
        for it in items:
            meta = ("until " + et_time(it["ends"])) if it.get("ends") else ""
            out.append({"event": it.get("event") or "", "meta": meta})
        return {"state": "active", "items": out}
    if a.get("status") == "ok":
        return {"state": "clear", "items": [{"event": "No NWS alerts right now", "meta": ""}]}
    return {"state": "unknown", "items": [{"event": ALERTS_OFF[0], "meta": ALERTS_OFF[1]}]}


def _marine(m) -> dict | None:
    m = m or {}
    per = (m.get("periods") or [])
    if m.get("status") != "ok" or not per:
        return {"off": MARINE_OFF}
    p = per[0]
    return {
        "name": p.get("name") or "",
        "text": p.get("text") or "",
        "src": "%s · %s" % (m.get("office") or "NWS", m.get("zone") or ""),
        "when": et_time(m.get("updated")),
        "url": m.get("sourceUrl") or "",
    }


def salt_model(payload: dict) -> dict:
    R = payload.get("readings") or {}
    tiles = [_wind_tile(R.get("wind")), _seas_tile(R.get("seas")), _water_tile(R), _tide_tile(payload.get("tides"))]
    more = [_swell_tile(R.get("swell"))]
    air = R.get("airTemp")
    if _state(air) != "off":
        more.append(_temp_tile(air, "Air", "air"))
    more.append(_pressure_tile(R.get("pressure")))
    hw = R.get("harborWind")
    w = R.get("wind") or {}
    if hw and _state(hw) != "off" and ((hw.get("station") or {}).get("id") != (w.get("station") or {}).get("id")):
        more.append(_wind_tile(hw, name="Harbor wind", tid="harbor"))
    reg = payload.get("region") or {}
    return {
        "water": "salt", "region": reg, "tiles": tiles, "more": more,
        "alerts": _alerts(payload.get("alerts")), "alerts_raw": payload.get("alerts"), "forecast": _marine(payload.get("marine")),
        "updated": et_time(payload.get("generatedAt")), "ok": True,
    }


# ---------------------------------------------------------------- freshwater

def _usgs_when(v: dict) -> str:
    return et_time((v or {}).get("time"))


def _flow_tile(spec: dict, tid: str, name: str, off: str) -> dict:
    spec = spec or {}
    f = spec.get("flowCfs") or {}
    s = spec.get("stageFt") or {}
    src = "%s · USGS %s" % (spec.get("label") or "", spec.get("usgs") or "")
    if _num(f.get("value")):
        stale = bool(f.get("stale"))
        sub = []
        if (spec.get("band") or {}).get("label") and not stale:
            sub.append(spec["band"]["label"])
        if _num(s.get("value")):
            sub.append("Gage height %s ft" % _fmt(s["value"], 2))
        return _tile(id=tid, name=name, state="stale" if stale else "ok", num="{:,}".format(_r0(f["value"])),
                     unit="cfs", sub=" · ".join(sub), src=src, when=_usgs_when(f),
                     note="Regulated by the dam" if spec.get("regulated") else "")
    if _num(s.get("value")):
        return _tile(id=tid, name=name, state="stale" if s.get("stale") else "ok", num=_fmt(s["value"], 2),
                     unit="ft", sub="Gage height, not depth", src=src, when=_usgs_when(s),
                     note=spec.get("flowNote") or "")
    return _tile(id=tid, name=name, state="off", off=off, src=src)


def fresh_model(payload: dict) -> dict:
    reg = payload.get("region") or {}
    tiles, more = [], []
    lake = payload.get("lake")
    if lake:
        el = lake.get("elevation") or {}
        src = "USGS %s" % (lake.get("usgs") or "")
        if _num(el.get("value")):
            sub = ""
            if _num(lake.get("vsGuideFt")):
                g = lake["vsGuideFt"]
                sub = "%s ft %s guide curve (%s)" % (_fmt(abs(g), 2), "above" if g >= 0 else "below", _fmt(lake.get("guideCurveFt"), 1))
            t = _tile(id="lake", name="Lake level", state="stale" if el.get("stale") else "ok",
                      num=_fmt(el["value"], 2), unit="ft", sub=sub, src=src, when=_usgs_when(el),
                      note="Surface elevation, %s. Not depth." % (lake.get("datum") or "NGVD29"))
            if _num(lake.get("change24hFt")):
                t["obs"] = "%+.2f ft in 24 h" % lake["change24hFt"] + (
                    (" · %+.2f ft in 7 days" % lake["change7dFt"]) if _num(lake.get("change7dFt")) else "")
            tiles.append(t)
        else:
            tiles.append(_tile(id="lake", name="Lake level", state="off", off=LAKE_OFF, src=src))
        tiles.append(_flow_tile(payload.get("release"), "release",
                                (payload.get("release") or {}).get("tileTitle") or "Release", RELEASE_OFF))
        for i, inf in enumerate((payload.get("inflows") or [])[:1]):
            tiles.append(_flow_tile(inf, "inflow", "Inflow", "Not available from USGS right now."))
    else:
        for i, rv in enumerate((payload.get("river") or [])[:4]):
            tiles.append(_flow_tile(rv, "river-%d" % i, rv.get("label") or "River gauge", STAGE_OFF))
    wt = payload.get("waterTemp") or {}
    if wt.get("status") == "ok" and _num(wt.get("f")):
        tiles.append(_tile(id="water", name="Water", state="stale" if wt.get("stale") else "ok",
                           num=str(_r0(wt["f"])), unit="°F", src="USGS sensor at the dam", when=et_time(wt.get("time"))))
    else:
        tiles.append(_tile(id="water", name="Water", state="off", off=NOT_REPORTING,
                           sub=wt.get("note") or FRESH_WT_OFF))
    rain = payload.get("rain")
    if rain:
        if rain.get("status") == "ok" and _num(rain.get("last24In")):
            t = _tile(id="rain", name="Rain, 24 h", num="%.2f" % rain["last24In"], unit="in",
                      state="stale" if rain.get("stale") else "ok", src="USGS gauge at the dam",
                      when=et_time(rain.get("time")))
        else:
            t = _tile(id="rain", name="Rain, 24 h", state="off", off="—", sub=RAIN_OFF)
        q = rain.get("qpf") or {}
        if q.get("status") == "ok" and _num(q.get("next24In")):
            t["fc"] = "Forecast next 24 h: %.2f in (NWS)" % q["next24In"]
        more.append(t)
    fc = payload.get("forecast") or {}
    per = fc.get("periods") or []
    forecast = ({"name": per[0].get("name") or "", "text": per[0].get("detail") or per[0].get("short") or "",
                 "src": fc.get("office") or "NWS", "when": et_time(fc.get("updated")), "url": ""}
                if fc.get("status") == "ok" and per else {"off": FRESH_POINT_OFF})
    return {
        "water": "fresh", "region": reg, "tiles": tiles, "more": more,
        "alerts": _alerts(payload.get("alerts")), "alerts_raw": payload.get("alerts"), "forecast": forecast,
        "updated": et_time(payload.get("generatedAt")), "ok": True,
    }


def _freshwater_ids() -> set:
    try:
        import freshwater
        return set(freshwater.regions().keys())
    except Exception:
        return set()


def model(region_id: str | None = None) -> dict:
    """Live conditions through the existing assemble() calls. Never raises."""
    rid = (region_id or "").strip() or None
    try:
        if rid and rid in _freshwater_ids():
            import freshwater
            status, payload = freshwater.assemble(rid)
            if status == 200 and (payload or {}).get("ok"):
                return dict(fresh_model(payload), test=bool(payload.get("testData")))
        else:
            status, payload = conditions.assemble(rid)
            if status == 200 and (payload or {}).get("ok"):
                return dict(salt_model(payload), test=bool(payload.get("testData")))
    except Exception:
        pass
    return {"ok": False, "water": "salt", "region": {"id": rid or "", "name": ""}, "tiles": [], "more": [],
            "alerts": {"state": "unknown", "items": [{"event": ALERTS_OFF[0], "meta": ALERTS_OFF[1]}]},
            "forecast": None, "updated": ""}


def region_groups(current: str) -> list[tuple[str, list[tuple[str, str, bool]]]]:
    salt, fresh = [], []
    fids = _freshwater_ids()
    for rid, name, cur in region_links(current):
        (fresh if rid in fids else salt).append((rid, name, cur))
    return [("Saltwater", salt), ("Freshwater", fresh)]


def public_fresh_ids() -> set:
    """Freshwater regions that are public today (enabled, built, not preview/draft), only while FRESHWATER_ENABLED is on."""
    try:
        import freshwater
        if not freshwater.flag_on():
            return set()
        return {rid for rid, r in freshwater.regions().items()
                if r.get("enabled") and r.get("previewReady") and not r.get("draft") and not freshwater.is_preview_region(rid)}
    except Exception:
        return set()


def public_salt_ids() -> set:
    """Saltwater regions the public picker lists today (same list as /api/regions without the cookie)."""
    try:
        return {r["id"] for r in conditions.listed_regions(preview=False).get("regions") or []
                if (r.get("waterType") or "saltwater") == "saltwater"}
    except Exception:
        return set()


def public_region_groups(current: str) -> list[tuple[str, list[tuple[str, str, bool, str]]]]:
    """Public rail: only regions public today. Never preview, draft or disabled regions."""
    salt, fresh = [], []
    try:
        for r in conditions.listed_regions(preview=False).get("regions") or []:
            if (r.get("waterType") or "saltwater") == "saltwater":
                salt.append((r["id"], r.get("name") or r["id"], r["id"] == current, "/?region=%s" % r["id"]))
    except Exception:
        pass
    try:
        import freshwater
        if freshwater.flag_on():
            for rid, r in freshwater.regions().items():
                if r.get("enabled") and r.get("previewReady") and not r.get("draft") and not freshwater.is_preview_region(rid):
                    fresh.append((rid, r.get("name") or rid, rid == current, "/?region=%s" % rid))
    except Exception:
        pass
    return [("Saltwater", salt), ("Freshwater", fresh)]


def region_rail(current: str, public: bool = False) -> str:
    groups = []
    if public:
        for label, items in public_region_groups(current):
            if not items:
                continue
            links = "".join('<a href="%s"%s>%s</a>' % (_esc(h, True), ' aria-current="page"' if c else "", _esc(n))
                            for r, n, c, h in items)
            groups.append('<div class="rr-g rr-%s"><p class="rr-k">%s</p><div class="rr-l">%s</div></div>' % (label.lower(), label, links))
        return '<nav class="rr" aria-label="Choose your water">%s</nav>' % "".join(groups)
    for label, items in region_groups(current):
        if not items:
            continue
        links = "".join('<a href="?region=%s"%s>%s</a>' % (_esc(r, True), ' aria-current="page"' if c else "", _esc(n))
                        for r, n, c in items)
        groups.append('<div class="rr-g rr-%s"><p class="rr-k">%s</p><div class="rr-l">%s</div></div>' % (label.lower(), label, links))
    return '<nav class="rr" aria-label="Choose your water">%s</nav>' % "".join(groups)


def region_links(current: str) -> list[tuple[str, str, bool]]:
    out = []
    try:
        for r in conditions.listed_regions().get("regions") or []:
            out.append((r["id"], r.get("name") or r["id"], r["id"] == current))
    except Exception:
        pass
    try:
        import freshwater
        for rid, r in freshwater.regions().items():
            if r.get("previewReady"):
                out.append((rid, r.get("name") or rid, rid == current))
    except Exception:
        pass
    return out


# ---------------------------------------------------------------- photos

def approved_photos() -> list[dict]:
    try:
        import catch_wall_public
        return list(catch_wall_public.load_approved() or [])
    except Exception:
        return []


def photo_by_id(photos: list[dict], pid: str) -> dict | None:
    for p in photos:
        if str(p.get("id") or "").lower() == pid.lower():
            try:
                import catch_wall_public
                return catch_wall_public.localize_featured(p)
            except Exception:
                return p
    return None


def collection(p: dict) -> str:
    return "Coastal Life" if p.get("category") == "life" else "Catch Wall"


def credit(p: dict) -> str:
    """Credit built only from stored fields. No invented names."""
    if p.get("credit_line"):
        return str(p["credit_line"])
    if p.get("name"):
        return "Photo: %s · %s" % (p["name"], collection(p))
    return "Community photo · %s" % collection(p)


def caption(p: dict) -> str:
    """Stored fields only, shown as submitted. No overrides."""
    bits = [b for b in (p.get("title"), p.get("species"), p.get("location"), p.get("region")) if b]
    return " · ".join(bits)


def alt(p: dict) -> str:
    if p.get("alt"):
        return str(p["alt"])
    try:
        import catch_wall_public
        return catch_wall_public._alt(p)
    except Exception:
        return caption(p) or "Community photograph"


def img_html(p: dict, sizes: str, eager: bool = False) -> str:
    """<img>/<picture> with explicit dimensions. Never the LCP unless eager."""
    load = 'fetchpriority="low" loading="lazy"' if not eager else 'loading="eager"'
    if p.get("local"):
        srcs = lambda ext: ", ".join("%s-%d.%s %dw" % (p["base"], w, ext, w) for w in p["widths"])
        return (
            '<picture><source type="image/avif" srcset="%s" sizes="%s"><img src="%s-800.webp" srcset="%s" sizes="%s" '
            'alt="%s" width="%d" height="%d" %s decoding="async"></picture>'
        ) % (srcs("avif"), sizes, p["base"], srcs("webp"), sizes, _esc(alt(p), True), p["w"], p["h"], load)
    src = p.get("src") or {}
    parts = ["%s %sw" % (_esc(src[k], True), k) for k in ("400", "800", "1600") if src.get(k)]
    fallback = src.get("800") or src.get("400") or ""
    return '<img src="%s" srcset="%s" sizes="%s" alt="%s" width="%d" height="%d" %s decoding="async">' % (
        _esc(fallback, True), ", ".join(parts), sizes, _esc(alt(p), True),
        int(p.get("w") or 1600), int(p.get("h") or 1200), load)


def figure(p: dict | None, cls: str, sizes: str, slot_title: str = "", ratio: str = "4 / 5") -> str:
    """A credited photo, or an honest empty slot."""
    if not p:
        return (
            '<figure class="ph ph-empty %s" style="aspect-ratio:%s"><div class="ph-slot">'
            '<p class="ph-slot-k">%s</p><p class="ph-slot-t">%s</p></div></figure>'
        ) % (cls, ratio, AWAITING, _esc(slot_title))
    return (
        '<figure class="ph %s"><div class="ph-frame" style="aspect-ratio:%s">%s</div>'
        '<figcaption><span class="ph-cap">%s</span> <span class="ph-credit">%s</span></figcaption></figure>'
    ) % (cls, ratio, img_html(p, sizes), _esc(caption(p)), _esc(credit(p)))


# ---------------------------------------------------------------- instruments markup

def _dial(deg) -> str:
    """Compass with an arrow at the bearing the wind comes from (true north up)."""
    if deg is None:
        return ""
    a = math.radians(float(deg))
    # tip on the rim (from-direction); shaft points toward the centre
    tx, ty = 20 + 14 * math.sin(a), 20 - 14 * math.cos(a)
    bx, by = 20 + 3 * math.sin(a), 20 - 3 * math.cos(a)
    px, py = math.cos(a), math.sin(a)  # perpendicular
    l1x, l1y = tx - 5.2 * math.sin(a) + 4.2 * px, ty + 5.2 * math.cos(a) + 4.2 * py
    l2x, l2y = tx - 5.2 * math.sin(a) - 4.2 * px, ty + 5.2 * math.cos(a) - 4.2 * py
    return (
        '<svg class="t-dial" viewBox="0 0 40 40" aria-hidden="true" focusable="false">'
        '<circle cx="20" cy="20" r="15.5" class="d-rim"/>'
        '<path d="M20 3v3.5M20 33.5v3.5M3 20h3.5M33.5 20h3.5" class="d-tick"/>'
        '<text x="20" y="11.5" class="d-n" text-anchor="middle">N</text>'
        '<line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f" class="d-shaft"/>'
        '<path d="M%.2f %.2f L%.2f %.2f L%.2f %.2f Z" class="d-mark"/></svg>'
    ) % (bx, by, tx, ty, tx, ty, l1x, l1y, l2x, l2y)


def _tide_spark(t: dict) -> str:
    now = _now_ms()
    t0, t1 = now - 3 * 3600e3, now + 12 * 3600e3
    curve = [c for c in (t.get("curve") or []) if isinstance(c, (list, tuple)) and len(c) == 2 and _num(c[1])]
    pts = [c for c in curve if t0 <= c[0] <= t1]
    method = "6-minute NOAA predictions" + ((" from " + t["curve_from"]) if t.get("curve_from") else "")
    # Owner decision (Nov 15): stations with only official highs and lows (Emerald Isle, Topsail)
    # get text only; a curve is drawn only from genuine NOAA 6-minute predictions.
    if len(pts) < 10 or not (pts[0][0] <= now <= pts[-1][0]):
        return ""
    evs = [e for e in (t.get("events") or []) if _num(e.get("t")) and _num(e.get("v")) and t0 <= e["t"] <= t1]
    ob = t.get("obs_pt") if t.get("obs_pt") and t0 <= t["obs_pt"][0] <= t1 else None
    vals = [p[1] for p in pts] + [e["v"] for e in evs] + ([ob[1]] if ob else [])
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1
    W, H = 200.0, 56.0
    X = lambda x: (x - t0) / (t1 - t0) * W
    Y = lambda v: H - 8 - (v - lo) / span * (H - 18)
    path = " ".join(("M" if i == 0 else "L") + "%.1f %.1f" % (X(p[0]), Y(p[1])) for i, p in enumerate(pts))
    # predicted level at now, for the now dot (linear between the two bracketing points)
    yn = None
    for a, b in zip(pts, pts[1:]):
        if a[0] <= now <= b[0]:
            yn = a[1] + (b[1] - a[1]) * ((now - a[0]) / ((b[0] - a[0]) or 1))
            break
    marks = []
    for e in evs:
        if e["t"] > now:
            marks.append('<circle cx="%.1f" cy="%.1f" r="2.6" class="s-ev"/>' % (X(e["t"]), Y(e["v"])))
            marks.append('<text x="%.1f" y="%.1f" class="s-lab" text-anchor="middle">%s</text>' % (
                min(max(X(e["t"]), 8), W - 8), Y(e["v"]) - 5 if e.get("type") == "H" else Y(e["v"]) + 11, "H" if e.get("type") == "H" else "L"))
    nowm = '<path d="M%.1f 2V%.1f" class="s-now"/>' % (X(now), H - 2)
    if yn is not None:
        nowm += '<circle cx="%.1f" cy="%.1f" r="5" class="s-nowring"/>' % (X(now), Y(yn))
        nowm += '<circle cx="%.1f" cy="%.1f" r="2.6" class="s-nowdot"/>' % (X(now), Y(yn))
    obs = ('<circle cx="%.1f" cy="%.1f" r="3.4" class="s-obs"/>' % (X(ob[0]), Y(ob[1]))) if ob else ""
    label = "Tide curve, %s, from 3 hours ago to 12 hours ahead%s." % (method, "; dot marks the latest observed level" if ob else "")
    legend = '<span class="s-k s-k-pred">%s</span>' % _esc("Predicted" + ((" · " + t["curve_from"]) if t.get("curve_from") else ""))
    if ob:
        legend += '<span class="s-k s-k-obs">Observed</span>'
    legend += '<span class="s-k s-k-now">Now</span>'
    return (
        '<figure class="t-tide"><svg class="t-spark" viewBox="0 0 200 56" role="img" aria-label="%s" focusable="false">'
        '<path d="M0 %.1fH200" class="s-base"/><path d="%s" class="s-line"/>%s%s%s</svg>'
        '<figcaption class="s-legend">%s</figcaption></figure>'
    ) % (_esc(label, True), H - 1, path, "".join(marks), nowm, obs, legend)


OFFSHORE_ICON = (
    '<svg class="t-buoy" viewBox="0 0 24 16" aria-hidden="true" focusable="false">'
    '<path d="M12 2 L15 9 H9 Z" fill="currentColor"/><path d="M12 0V2" stroke="currentColor" stroke-width="1.4"/>'
    '<path d="M1 12 Q4 10 7 12 T13 12 T19 12 T23 12" fill="none" stroke="currentColor" stroke-width="1.4"/></svg>'
)


def tile_html(t: dict, big: bool = False) -> str:
    st = t["state"]
    cls = "t t-%s%s%s%s" % (t["id"], " is-stale" if st == "stale" else "", " is-off" if st == "off" else "",
                           " is-offshore" if t.get("offshore") else "")
    kind_cls = {"Observed": "k-obs", "Predicted": "k-pred", "Forecast": "k-fc"}.get(t["kind"], "k-obs")
    hid = "t-%s-n" % t["id"]
    if st == "stale":
        chip = '<span class="t-chip c-stale" title="Older than this station\'s normal reporting gap">Stale · %s</span>' % _esc(t["when"])
    else:
        chip = '<span class="t-kind %s">%s</span>' % (kind_cls, _esc(t["kind"]))
    out = ['<div class="%s" role="group" aria-labelledby="%s">' % (cls, hid)]
    out.append('<div class="t-head"><h3 class="t-name" id="%s">%s</h3>%s</div>' % (hid, _esc(t["name"]), chip))
    if t.get("offshore") and st != "off":
        out.append('<p class="t-offtag">%s<span>Offshore buoy</span></p>' % OFFSHORE_ICON)
    if st == "off":
        out.append('<p class="t-read"><span class="t-num num-off">—</span></p>')
        out.append('<p class="t-sub t-offline">%s</p>' % _esc(t["off"] or NOT_REPORTING))
        if t.get("sub"):
            out.append('<p class="t-note">%s</p>' % _esc(t["sub"]))
    else:
        read = []
        if t["dir"]:
            read.append('<span class="t-dir">%s</span>' % _esc(t["dir"]))
        if t["num"]:
            read.append('<span class="t-num">%s</span>' % _esc(t["num"]))
            if t["unit"]:
                read.append('<span class="t-unit">%s</span>' % _esc(t["unit"]))
        else:
            read.append('<span class="t-num num-off">—</span>')
        dial = _dial(t.get("dial"))
        if t["id"] == "wind" and dial:
            out.append('<p class="t-read t-read-wind">%s<span class="t-wind-vals">%s</span></p>' % (dial, "".join(read)))
        else:
            out.append('<p class="t-read">%s%s</p>' % ("".join(read), dial))
        if t.get("gust"):
            out.append('<p class="t-gust"><span class="t-gust-k">Gust</span> <span class="t-gust-n">%s</span> <span class="t-gust-u">kt</span></p>' % _esc(t["gust"]))
        # Data (audit-nov16): prefer label / offshore_label when present; otherwise
        # keep the current Inshore station / Offshore buoy wording. Never reword the fields.
        if t.get("label"):
            out.append('<p class="t-label">%s</p>' % _esc(t["label"]))
        elif t.get("note"):
            out.append('<p class="t-note">%s</p>' % _esc(t["note"]))
        o = t.get("off_read") or {}
        off_lab = t.get("offshore_label") or ""
        sub = t["sub"] or ""
        stale_m = re.search(r"\(stale, last report [^)]+\)", sub)
        stale_txt = ""
        if isinstance(o.get("stale"), str) and o["stale"]:
            stale_txt = o["stale"]
        elif stale_m:
            stale_txt = stale_m.group(0)
        if off_lab or o:
            bits = ['<div class="t-offread%s">' % (" is-stale" if stale_txt else "")]
            if not off_lab:
                bits.append('<p class="t-offread-k">Offshore buoy</p>')
            if o.get("num"):
                bits.append(
                    '<p class="t-read t-read-off"><span class="t-off-num">%s</span><span class="t-unit">%s</span></p>'
                    % (_esc(o.get("num") or ""), _esc(o.get("unit") or ""))
                )
            src = off_lab or o.get("src") or ""
            when = (' <time>%s</time>' % _esc(o["when"])) if o.get("when") and not off_lab else ""
            if src or when:
                bits.append('<p class="t-offread-src">%s%s</p>' % (_esc(src), when))
            if stale_txt:
                bits.append('<p class="t-stale">%s</p>' % _esc(stale_txt))
            bits.append("</div>")
            out.append("".join(bits))
        elif sub:
            if stale_m:
                head = sub[:stale_m.start()].rstrip()
                if head:
                    out.append('<p class="t-sub">%s</p>' % _esc(head))
                out.append('<p class="t-stale">%s</p>' % _esc(stale_m.group(0)))
            else:
                out.append('<p class="t-sub">%s</p>' % _esc(sub))
        if t.get("obs"):
            out.append('<p class="t-sub t-obs">%s</p>' % _esc(t["obs"]))
        if t.get("fc"):
            out.append('<p class="t-sub t-fcline"><span class="t-chip k-fc">Forecast</span> %s</p>' % _esc(t["fc"].replace("Forecast ", "")))
        if t.get("then"):
            out.append('<p class="t-sub t-then">%s</p>' % _esc(t["then"]))
        if t["id"] == "tide":
            out.append(_tide_spark(t))
    if st == "off" and t.get("note"):
        out.append('<p class="t-note">%s</p>' % _esc(t["note"]))
    src = t["src"]
    if src or t["when"]:
        out.append('<p class="t-src">%s%s</p>' % (
            '<span class="t-st">%s</span>' % _esc(src) if src else "",
            ' <time>%s</time>' % _esc(t["when"]) if t["when"] and st != "stale" else ""))
    out.append("</div>")
    return "".join(out)


# NWS Coastal Warning Display signals (weather.gov/marine/cwd), keyed by the
# exact `event` string NWS returns from api.weather.gov/alerts/active.
FLAG_EVENTS = {
    "Small Craft Advisory": "pennant",
    "Gale Warning": "pennant2",
    "Storm Warning": "square",
    "Hurricane Warning": "square2",
}
FLAG_LABELS = {
    "pennant": "one red pennant",
    "pennant2": "two red pennants",
    "square": "a square red flag with a black center",
    "square2": "two square red flags with black centers",
}


def _ended(it: dict) -> bool:
    d = homepage_boot._to_dt(it.get("ends"))
    return bool(d and d < datetime.now(timezone.utc))


def flag_for(alerts: dict | None) -> str | None:
    """Highest flag for active, verified alerts, or None. Exact event names only."""
    a = alerts or {}
    if a.get("status") != "ok":
        return None
    order = ("pennant", "pennant2", "square", "square2")
    best = None
    for it in a.get("items") or []:
        kind = FLAG_EVENTS.get(it.get("event") or "")
        if kind and not _ended(it) and (best is None or order.index(kind) > order.index(best)):
            best = kind
    return best


def flag_svg(kind: str | None) -> str:
    if not kind:
        return ""
    pen = '<path d="M3 3 L27 10 L3 17 Z" fill="#B3261E"/>'
    sq = '<rect x="3" y="3" width="18" height="18" fill="#B3261E"/><rect x="9" y="9" width="6" height="6" fill="#141414"/>'
    mast = '<path d="M2 1V44" stroke="currentColor" stroke-width="1.6"/>'
    body = {
        "pennant": pen,
        "pennant2": pen + '<g transform="translate(0 18)">' + pen + "</g>",
        "square": sq,
        "square2": sq + '<g transform="translate(0 21)">' + sq + "</g>",
    }[kind]
    return (
        '<span class="al-flag" role="img" aria-label="Coastal warning display: %s">'
        '<svg viewBox="0 0 30 46" width="11" height="17" aria-hidden="true" focusable="false">%s%s</svg></span>'
    ) % (FLAG_LABELS[kind], mast, body)


def severity(event: str) -> str:
    """Banner tone from the NWS product type in the event name. Colour only where it means something."""
    e = event or ""
    if e.endswith("Warning"):
        return "warn"
    if e.endswith("Advisory"):
        return "adv"
    if e.endswith("Watch"):
        return "watch"
    return "stmt"


SEV_LABEL = {"warn": "Warning", "adv": "Advisory", "watch": "Watch", "stmt": "Statement"}


def alerts_html(a: dict, pennants: bool = False, raw: dict | None = None) -> str:
    """Slim alert strip (Ed, Nov 16): one line per alert with the exact NWS product name and its
    until-time, then a compact "NWS details" link. Colour carries the severity (ivory + amber edge
    for advisories and watches, solid red for warnings). Official flags only, tiny and inline.
    Server-rendered, so its space is reserved before first paint (no CLS)."""
    st = a["state"]
    rows, sevs = [], []
    flag = flag_svg(flag_for(raw)) if pennants else ""
    for i, it in enumerate(a["items"]):
        sv = severity(it["event"]) if st == "active" else ""
        sevs.append(sv)
        rows.append('<p class="al-row%s">%s<b class="al-ev">%s</b>%s</p>' % (
            (" sev-" + sv) if sv else "", flag if i == 0 else "",
            _esc(it["event"]), (' <span class="al-meta">%s</span>' % _esc(it["meta"])) if it["meta"] else ""))
    top = next((x for x in ("warn", "adv", "watch", "stmt") if x in sevs), "")
    return '<div class="al al-%s%s%s" role="status"><div class="al-rows">%s</div><a class="al-link" href="%s" rel="noopener">NWS details</a></div>' % (
        st, (" al-" + top) if top else "", " has-flag" if flag else "", "".join(rows), homepage_boot.NWS_DETAILS)


def forecast_html(f: dict | None, water: str) -> str:
    if not f:
        return ""
    if f.get("off"):
        return '<div class="fc"><span class="t-kind k-fc">Forecast</span><p class="fc-t">%s</p></div>' % _esc(f["off"])
    label = "Marine forecast" if water == "salt" else "NWS forecast"
    src = _esc(f["src"]) + (' · issued %s' % _esc(f["when"]) if f.get("when") else "")
    return (
        '<div class="fc"><p class="fc-h"><span class="t-kind k-fc">Forecast</span> <b>%s</b> · %s</p>'
        '<p class="fc-t">%s</p><p class="t-src">%s</p></div>'
    ) % (label, _esc(f["name"]), _esc(f["text"]), src)


def _extras(m: dict, more: str, variant: str) -> tuple[str, str]:
    fc = forecast_html(m.get("forecast"), m.get("water")) if m.get("ok") else ""
    if False:  # Ed: no toggles that hide instruments
        # Editorial keeps the four headline readings on the first screen and
        # folds the rest under one labelled control so the photograph leads.
        label = "Swell, barometer and the marine forecast" if m.get("water") == "salt" else "Rain and the NWS forecast"
        return ('<details class="cg-fold"><summary>%s</summary>%s%s</details>' % (label, more, fc), "")
    if variant == "hybrid":
        return (fc, more)  # forecast right under the headline instruments
    return (more, fc)


TEST_BANNER = ('<p class="test-banner" role="note"><b>TEST DATA</b> Simulated readings, tide and alerts for design review. '
               'Not live, not a forecast.</p>')


def strip_item(t: dict) -> str:
    """One cell of the secondary strip: label, reading, kind, station and time. Same fields as a tile, less chrome."""
    st = t["state"]
    if st == "off":
        val = '<span class="sx-v num-off">—</span>'
        sub = _esc(t["off"] or NOT_REPORTING)
    else:
        val = '<span class="sx-v">%s%s%s</span>' % (
            ('<span class="sx-dir">%s</span> ' % _esc(t["dir"])) if t["dir"] else "",
            _esc(t["num"]) if t["num"] else "—",
            (' <span class="sx-u">%s</span>' % _esc(t["unit"])) if t["unit"] else "")
        sub = " · ".join(_esc(x) for x in (t.get("note"), t["sub"]) if x)
    chip = ('<span class="t-chip c-stale" title="Older than this station\'s normal reporting gap">Stale · %s</span>' % _esc(t["when"])
            if st == "stale" else '<span class="sx-kind">%s</span>' % _esc(t["kind"]))
    fc = ('<span class="sx-fc"><span class="t-chip k-fc">Forecast</span> %s</span>' % _esc(t["fc"].replace("Forecast ", ""))) if t.get("fc") else ""
    src = " ".join(x for x in (_esc(t["src"]) if t["src"] else "", _esc(t["when"]) if t["when"] and st != "stale" else "") if x)
    return ('<div class="sx sx-%s%s" role="group" aria-label="%s"><p class="sx-h"><span class="sx-k">%s</span>%s</p>%s'
            '<p class="sx-sub">%s</p>%s<p class="sx-src">%s</p></div>') % (
        _esc(t["id"], True), " is-off" if st == "off" else "", _esc(t["name"], True), _esc(t["name"]), chip, val, sub, fc, src)


def conditions_html(m: dict, *, variant: str, public: bool = False) -> str:
    reg = m.get("region") or {}
    rid = reg.get("id") or ""
    if not m.get("ok"):
        body = '<p class="cg-off">%s</p>' % PAYLOAD_OFF
        tiles = ""
        more = ""
    else:
        body = alerts_html(m["alerts"], pennants=variant in ("heritage", "hybrid"), raw=m.get("alerts_raw"))
        tiles = '<div class="cg-grid">%s</div>' % "".join(tile_html(t) for t in m["tiles"])
        if variant == "hybrid":
            more = ('<div class="cg-strip" role="group" aria-label="Also observed"><p class="cg-more-k">Also observed</p>%s</div>' % "".join(strip_item(t) for t in m["more"])) if m["more"] else ""
        else:
            more = ('<div class="cg-more" role="group" aria-label="Also observed"><p class="cg-more-k">Also observed</p>%s</div>' % "".join(tile_html(t) for t in m["more"])) if m["more"] else ""
    if m.get("test"):
        body = TEST_BANNER + body
    links = []
    for r_id, name, cur in region_links(rid):
        links.append('<a href="?region=%s"%s>%s</a>' % (_esc(r_id, True), ' aria-current="true"' if cur else "", _esc(name)))
    brief_link = '<a class="cg-link" href="/brief?region=%s">Today\'s brief for this water</a>' % _esc(rid, True)
    if public:   # only public briefs; same rule as brief-link.js; no link when the brief is switched off
        brief_link = ""
        if _brief_on():
            import site_chrome
            tgt, own = site_chrome.brief_target(rid)
            # Ed (Nov 19, t336u): always this region's own /brief page. Without a published brief
            # that is the "No Morning Brief for this area" page (with a way back), never another region.
            label = "Today\'s Morning Brief" if own else "Morning Brief: not yet available here"
            brief_link = '<a class="cg-link" href="/brief?region=%s">%s</a>' % (_esc(tgt, True), label)
    if m.get("water") == "fresh":
        dash = "/lake?region=%s" % rid
    else:   # "/" is the Hybrid page itself; the map, chart, radar and tide tables live on /dashboard
        dash = "/dashboard?region=%s" % rid if rid else "/dashboard"
    if variant == "hybrid":
        return (
            '<section class="cg cg-%s" id="conditions" aria-labelledby="cg-h" data-conditions>'
            '<header class="cg-head"><h2 id="cg-h">Conditions at a Glance</h2>'
            '<p class="cg-where">%s</p>'
            '<p class="cg-upd">%s</p></header>'
            "%s%s%s%s"
            '<div class="cg-foot">%s%s</div>'
            "</section>"
        ) % (
            variant, _esc(reg.get("name") or ""),
            ("Updated %s" % _esc(m["updated"])) if m.get("updated") else "",
            body, tiles, *_extras(m, more, variant),
            region_rail(rid, public=public), tools_html(dash, m.get("water") == "fresh", brief_link),
        )
    return (
        '<section class="cg cg-%s" id="conditions" aria-labelledby="cg-h" data-conditions>'
        '<header class="cg-head"><h2 id="cg-h">Conditions at a Glance</h2>'
        '<p class="cg-where">%s</p>'
        '<p class="cg-upd">%s</p></header>'
        "%s%s%s%s"
        '<div class="cg-foot">%s'
        '<a class="cg-link" href="%s">Full dashboard</a>%s</div>'
        "</section>"
    ) % (
        variant, _esc(reg.get("name") or ""),
        ("Updated %s" % _esc(m["updated"])) if m.get("updated") else "",
        body, tiles, *_extras(m, more, variant),
        '<details class="cg-region"><summary>Change water</summary><nav aria-label="Regions">%s</nav></details>' % "".join(links),
        _esc(dash, True), brief_link,
    )


# Map/chart/radar/tide tables on the dashboard. Anchors exist in index.html (#map-section, #tide-search);
# #map-chart / #map-radar are read by app.js, which scrolls to the map and switches that layer on.
TOOLS_SALT = (("Nautical chart", "#map-chart"), ("Radar", "#map-radar"), ("Tide tables", "#tide-search"))


def tools_html(dash: str, fresh: bool, brief_link: str = "") -> str:
    """Clear, 44px chart and radar navigation under the instruments. Presentation only."""
    if fresh:
        items = '<a class="cg-tool cg-tool-main" href="%s">Full dashboard</a>' % _esc(dash, True)
    else:
        items = "".join('<a class="cg-tool" href="%s%s">%s</a>' % (_esc(dash, True), a, n) for n, a in TOOLS_SALT)
        items += '<a class="cg-tool cg-tool-main" href="%s">Full dashboard</a>' % _esc(dash, True)
    brief = brief_link.replace('class="cg-link"', 'class="cg-tool cg-tool-brief"') if brief_link else ""
    return ('<nav class="cg-tools" aria-label="Maps, charts and the Morning Brief">'
            '<p class="cg-tools-k">%s</p><div class="cg-tools-l">%s%s</div></nav>') % (
        "More readings" if fresh else "Map, chart &amp; radar", items, brief)


# ---------------------------------------------------------------- page chrome

def _today() -> str:
    d = datetime.now(homepage_boot.ET)
    return "%s, %s %d, %d" % (d.strftime("%A"), d.strftime("%B"), d.day, d.year)


def _brief_on() -> bool:
    """Morning Brief public flag (MORNING_BRIEF_ENABLED kill switch). Links are dropped when it is off."""
    try:
        import brief
        return bool(brief.flag_on())
    except Exception:
        return False


PUBLIC_BRIEF_SALT = ("crystal-coast", "hatteras")   # the coastal briefs that are public today


def _hybrid_masthead(public: bool, water: str) -> str:
    """Newspaper-style nameplate: navy dateline ear, nameplate, brass-and-navy double rule, section nav.
    The rule keeps the .wave-settle line the wave intro lands on."""
    if public:
        fresh_href = "/?region=falls-lake" if public_fresh_ids() else "/lake"
        brief = '<a href="/brief?region=crystal-coast" id="nav-brief">Morning Brief</a>' if _brief_on() else ""
        flag = ""
    else:
        fresh_href = "/preview/home-hybrid?region=falls-lake"
        brief = '<a href="/brief?region=crystal-coast">Morning Brief</a>'
        flag = '<p class="pv-flag">Private concept · %s</p>' % _esc(TITLES["hybrid"])
    salt_href = "/" if public else "/preview/home-hybrid"
    return (
        '<header class="mh mh-hybrid">%s'
        '<div class="mh-ear"><div class="mh-ear-in"><p class="mh-date"><time>%s</time></p></div></div>'
        '<div class="mh-plate"><h1 class="mh-name"><a href="/">The Coastal Brief</a></h1>'
        '<div class="mh-rules" aria-hidden="true"><span class="mh-rule-heavy"></span>'
        '<svg class="mh-rule" viewBox="0 0 1200 4" preserveAspectRatio="none" aria-hidden="true" focusable="false">'
        '<line class="wave-settle" x1="0" y1="2" x2="1200" y2="2"/></svg></div>'
        '<p class="mh-motto">From the rivers to the sounds to the sea</p>'
        '<nav class="mh-sec" aria-label="Sections"><a href="%s"%s>Saltwater</a><a href="%s"%s>Freshwater</a>'
        '%s<a href="/catch-wall">Catch Wall</a><a class="mh-maps" href="/dashboard">Map<span class="mh-maps-x"> &amp; tides</span></a></nav></div>'
        "</header>"
    ) % (flag, _esc(_today()), salt_href, "" if water == "fresh" else ' aria-current="page"',
         fresh_href, ' aria-current="page"' if water == "fresh" else "", brief)


def masthead_html(variant: str, public: bool = False, water: str = "salt") -> str:
    if public or variant == "hybrid":
        return _hybrid_masthead(public, water)
    return (
        '<header class="mh mh-%s"><p class="pv-flag">Private concept · %s</p>'
        '<div class="mh-bar">'
        '<nav class="mh-nav" aria-label="Sections"><a href="/brief">Morning Brief</a><a href="/lake">Lakes &amp; rivers</a><a href="/catch-wall">Catch Wall</a></nav></div>'
        '<div class="mh-plate"><h1 class="mh-name"><a href="/">The Coastal Brief</a></h1>'
        '<svg class="mh-rule" viewBox="0 0 1200 4" preserveAspectRatio="none" aria-hidden="true" focusable="false">'
        '<line class="wave-settle" x1="0" y1="2" x2="1200" y2="2"/></svg>'
        '<p class="mh-date"><time>%s</time><span class="mh-motto">From the rivers to the sounds to the sea</span></p></div>'
        "</header>"
    ) % (variant, _esc(TITLES[variant]), _esc(_today()))


SYSTEM = {
    "heritage": (
        ("Morning Brief", "Same navy instrument panel and chart neatline frame, then the Captain's Take set in the serif like a logbook entry."),
        ("Freshwater dashboards", "Lake level vs guide curve takes the big-numeral slot; marsh green replaces Atlantic blue as the accent. Same Observed / Forecast chips."),
        ("Galleries", "Catch Wall and Coastal Life as captioned plates on ivory, credit line under every frame, empty plates say what is missing."),
        ("Editorial sections", "Daymark squares and triangles mark section heads; chart-line texture stays on the masthead only."),
    ),
    "editorial": (
        ("Morning Brief", "Readings as a typeset table, then the Take as a magazine standfirst. Generous measure, sentence-case heads."),
        ("Freshwater dashboards", "One big serif numeral per gauge with a hairline-ruled data column; Pamlico green section labels."),
        ("Galleries", "A photo-first grid where the photograph leads and the credit sits on the caption rule, never on the image."),
        ("Editorial sections", "Kicker, serif headline, standfirst, credited photo. Empty story slots are shown, not filled."),
    ),
    "hybrid": (
        ("Morning Brief", "The readings band opens the brief exactly as here, navy on the coast and river green inland, then the Take in editorial type."),
        ("Freshwater dashboards", "Same band, tiles and chips in river green and clay: lake level vs guide curve, release, inflow and gage height get the big numerals."),
        ("Galleries", "The asymmetric mosaic: varied crops, captions on a soft scrim, a concise community credit on every frame, honest empty cells."),
        ("Editorial sections", "Horizon photo below the instruments, then kicker, serif headline and standfirst. One daymark per page."),
    ),
}


FRESH_SW = (("River green", "#1F3A2E"), ("Moss", "#5D6B3A"), ("Clay", "#8A5A3C"), ("Tannin", "#6B4A2E"), ("Sandbar", "#D8C9A8"))
SALT_SW = (("Midnight navy", "#071C29"), ("Atlantic blue", "#0E3A57"), ("Pamlico green", "#2F5D57"), ("Dock wood", "#6B5440"), ("Coastal sand", "#D9C7A6"))


def system_html(variant: str) -> str:
    if variant == "hybrid":
        pal = lambda items: "".join('<li><span class="sw" style="background:%s"></span>%s <code>%s</code></li>' % (c, n, c) for n, c in items)
        rows = "".join("<li><b>%s.</b> %s</li>" % (_esc(a), _esc(b)) for a, b in SYSTEM[variant])
        return (
            '<section class="sys" aria-labelledby="sys-h"><h2 id="sys-h">Design system (concept notes)</h2>'
            '<div class="sys-twin"><div><h3>Saltwater palette</h3><ul class="sys-sw">%s</ul></div>'
            '<div><h3>Freshwater palette</h3><ul class="sys-sw">%s</ul></div></div>'
            '<p class="sys-type">Shared: ivory <code>#F6F1E7</code>, sunrise gold <code>#E0A43C</code>, brass rule <code>#C4A36A</code>. '
            '<span class="sys-serif">Fraunces</span> nameplate, headlines and instrument numerals · <span class="sys-sans">Source Sans 3</span> text · '
            '<span class="sys-num">Barlow Condensed</span> instrument labels. All OFL, self-hosted.</p>'
            '<ul class="sys-carry">%s</ul></section>'
        ) % (pal(SALT_SW), pal(FRESH_SW), rows)
    sw = (("Midnight navy", "#071C29"), ("Atlantic blue", "#0E3A57"), ("Pamlico green", "#2F5D57"),
          ("Marsh green", "#5D6B3A"), ("Dock wood", "#6B5440"), ("Coastal sand", "#D9C7A6"),
          ("Sunrise gold", "#E0A43C"), ("Ivory", "#F6F1E7"), ("Brass rule", "#C4A36A"))
    chips = "".join('<li><span class="sw" style="background:%s"></span>%s <code>%s</code></li>' % (c, n, c) for n, c in sw)
    rows = "".join("<li><b>%s.</b> %s</li>" % (_esc(a), _esc(b)) for a, b in SYSTEM[variant])
    return (
        '<section class="sys" aria-labelledby="sys-h"><h2 id="sys-h">Design system (concept notes)</h2>'
        '<ul class="sys-sw">%s</ul>'
        '<p class="sys-type"><span class="sys-serif">Fraunces</span> nameplate and headlines · '
        '<span class="sys-sans">Source Sans 3</span> text · <span class="sys-num">Barlow Condensed 0123456789</span> instrument numerals (tabular). All OFL, self-hosted.</p>'
        '<ul class="sys-carry">%s</ul></section>'
    ) % (chips, rows)


def _read(name: str) -> str:
    return (DIR / name).read_text(encoding="utf-8")


def style_tag(variant: str) -> str:
    css = _read("base.css") + "\n" + _read("%s.css" % variant)
    return '<style id="sprint-css">\n%s\n</style>\n' % css.replace("</", "<\\/")


TITLES = {
    "heritage": "A · Carolina Maritime Heritage",
    "editorial": "B · Premium Coastal Editorial",
    "hybrid": "C · Hybrid",
}


def _public_head() -> str:
    """Title, description, OG and Twitter tags copied verbatim from the public index.html."""
    src = (ROOT / "index.html").read_text(encoding="utf-8")
    keep = []
    for line in src.splitlines():
        t = line.strip()
        if t.startswith(("<title>", '<meta name="description"', '<meta property="og:', '<meta name="twitter:', '<meta name="theme-color"')):
            keep.append(t)
        if t.startswith("</head>"):
            break
    return "\n".join(keep) + '\n<link rel="canonical" href="https://thecoastalbrief.com/">'


PUBLIC_FOOTER = """<div class="ft-pub">
<ul class="ft-links" aria-label="Quick links">
<li><a href="https://license.gooutdoorsnorthcarolina.com/Licensing/CustomerLookup.aspx" rel="noopener" target="_blank">Buy an NC fishing or hunting license</a></li>
<li><a href="https://www.ncwildlife.gov/hunting/license-types-and-fees" rel="noopener" target="_blank">License types and fees</a></li>
<li><a href="https://www.ncwildlife.gov/" rel="noopener" target="_blank">NC Wildlife Resources Commission</a></li>
</ul>
<p>Readings are live from NOAA, NWS and USGS. Data credits: NOAA National Data Buoy Center; National Weather Service (api.weather.gov and the National Digital Forecast Database); NOAA CO-OPS tide predictions and observed water levels; USGS water data. The <a href="/dashboard">full dashboard</a> credits the map, chart, sea-surface temperature and radar sources.</p>
<p>Photographs: approved Catch Wall and Coastal Life submissions, credited as submitted. Bodie Island Lighthouse: Photo: National Park Service, Cape Hatteras National Seashore (public domain). Falls Lake: Photo: <a href="%(falls)s" rel="noopener">Sergiy Galyonkin</a>, <a href="%(lic)s" rel="noopener license">CC BY-SA 2.0</a> (cropped and adjusted).</p>
<p>Your location is never requested; the region picker sets what you see.</p>
<p>The Coastal Brief is not weather, surf, or fishing advice. Radar and other conditions data are for general information only and can be incomplete or late. Always check official NWS marine forecasts and advisories before going out. Do not rely on this site as the only source for safety decisions.</p>
<p>Licenses are sold by the NC Wildlife Resources Commission; The Coastal Brief is not affiliated with it.</p>
</div>""" % {"falls": FALLS_SRC, "lic": CC_BY_SA_2}


_CSS_COMMENT = re.compile(r"/\*.*?\*/", re.S)


def _feedback_embed() -> str:
    try:
        import feedback
        return feedback.embed_html()
    except Exception:
        return ""


# Night-strip prototype (design/night-strip-1119, private): opt-in preview switches only, so production
# daytime is unchanged. ?night=1 sets html[data-night="b"] (the Coastal blue dark token set; it only paints
# when the device is in dark mode), ?strip=1 shows the coastal photo strip under the masthead (saltwater
# only). ?night=1 also turns on the faint NOAA chart texture behind the nameplate, phones included
# (Ed reversed the Nov 14 no-texture-on-phones rule for this combination). With no query the page is unchanged.
_STRIP_DIR = "/static/night-strip/docks-"
# Exact-size art-directed crops, each cut into a left and a right half that sit edge to edge.
# Phone box 390 x 88 (4.43:1 crop): halves 195 / 390 / 585 px wide = 1x / 2x / 3x.
# Tablet box 768 x 112 (6.86:1 crop): halves 384 / 768 / 1152 px wide = 1x / 2x / 3x; cover-fit on wider screens.
# Why halves: one full-width strip was the page's largest element, so Lighthouse timed LCP on the photo
# (2.7 s simulated) instead of the forecast text (1.3-1.6 s). At the Lighthouse mobile viewport each half is smaller than that text block,
# so LCP stays on the text while the photo still paints in the first frame. Visually identical.
_STRIP_W = {"phone": (195, 390, 585), "wide": (384, 768, 1152)}


def _strip_srcset(kind: str, side: str, ext: str) -> str:
    return ", ".join("%s%s-%s-%d.%s %dw" % (_STRIP_DIR, kind, side, w, ext, w) for w in _STRIP_W[kind])


_STRIP_MEDIA = {"phone": "(max-width: 639px)", "wide": "(min-width: 640px)"}
# Both halves' AVIFs are preloaded from <head> (media-matched, high priority) so they download alongside
# the fonts and are ready for the first paint.
NIGHT_BOOT = (
    '<script>(function(){try{var q=new URLSearchParams(location.search||""),d=document.documentElement,'
    'n=q.get("night"),s=q.get("strip");if(n==="1"||n==="b")d.setAttribute("data-night","b");'
    'if(s==="1"||s==="natural"){d.setAttribute("data-strip","");'
    'document.currentScript.insertAdjacentHTML("beforebegin",%s);}'
    'if(d.hasAttribute("data-night"))d.setAttribute("data-mastchart","");'
    '}catch(e){}})();</script>\n'
) % json.dumps("".join(
    '<link rel="preload" as="image" type="image/avif" fetchpriority="high" media="%s" '
    'imagesrcset="%s" imagesizes="50vw">' % (_STRIP_MEDIA[k], _strip_srcset(k, side, "avif"))
    for k in ("phone", "wide") for side in ("l", "r")
)).replace("<", "\\u003c")
STRIP_ALT = "Two long wooden docks over sound-side water, with marsh grass and red glasswort in the foreground"


def _strip_half(side: str, alt: str) -> str:
    srcs = "".join(
        '<source media="%s" type="image/%s" srcset="%s" sizes="50vw">'
        % (_STRIP_MEDIA["wide"], t, _strip_srcset("wide", side, e)) for t, e in (("avif", "avif"), ("webp", "webp"), ("jpeg", "jpg"))
    ) + "".join(
        '<source type="image/%s" srcset="%s" sizes="50vw">' % (t, _strip_srcset("phone", side, e))
        for t, e in (("avif", "avif"), ("webp", "webp"))
    )
    return (
        '<picture class="nstrip-%s">%s<img src="%sphone-%s-390.jpg" srcset="%s" sizes="50vw" width="195" height="88" '
        'alt="%s" decoding="async" fetchpriority="high"></picture>'
    ) % (side, srcs, _STRIP_DIR, side, _strip_srcset("phone", side, "jpg"), alt)


def night_strip_html() -> str:
    """Slim panoramic strip of Ed's own photograph (owner-supplied, approved). Inserted only when
    ?strip=1 asks for it, so the default page makes no request and has no extra layout. AVIF, then WebP,
    then JPEG. The box has a fixed CSS height and each img carries width/height, so showing it never
    shifts later content. The right half is a continuation of the same photo, so it has empty alt text.
    No place name: the location is not confirmed."""
    fig = '<figure class="nstrip">%s%s</figure>' % (
        _strip_half("l", STRIP_ALT), _strip_half("r", ""))
    # Markup lives in a JS string (with "<" escaped) so the default page carries no extra element at all.
    js = json.dumps(fig).replace("<", "\\u003c")
    return (
        '<script>(function(){if(document.documentElement.hasAttribute("data-strip"))'
        'document.currentScript.insertAdjacentHTML("beforebegin",%s);})();</script>' % js
    )


def _with_strip(mast: str, water: str) -> str:
    """The strip sits inside the masthead's <header> (a landmark), directly under the section nav."""
    i = mast.rfind("</header>")
    if water != "salt" or i < 0:
        return mast
    return mast[:i] + night_strip_html() + mast[i:]


def _shell(variant: str, main: str, shot: bool, water: str = "salt", public: bool = False, preload: str = "") -> bytes:
    intro_css = wave_intro._css()
    page = """<!DOCTYPE html>
<html lang="en" data-sprint="%(v)s" data-water="%(water)s" data-wave-intro%(shot)s>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
%(meta)s
<meta name="color-scheme" content="light dark">
%(nboot)s<link rel="preload" href="/fonts/fraunces-var.woff2" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="/fonts/fraunces-italic-var.woff2" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="/fonts/barlow-condensed-600.woff2" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="/fonts/source-sans-3-var.woff2" as="font" type="font/woff2" crossorigin>
%(img_preload)s<link rel="icon" href="/branding/favicon.svg" type="image/svg+xml">
<link rel="preconnect" href="https://wgjoenkugzfrrfejmtvh.supabase.co" crossorigin>
%(css)s<style id="wave-intro-css">
%(icss)s
</style>
%(boot)s</head>
<body>
%(defs)s%(overlay)s
<a class="skip" href="#conditions">Skip to Conditions at a Glance</a>
%(mast)s
<main id="main">%(main)s</main>
<footer class="ft"><div class="ft-in">
%(foot)s%(fb)s%(replay)s</div></footer>
<script>
%(ijs)s
</script>
</body>
</html>
"""
    priv_foot = """<p>Private concept preview. Readings are live from NOAA, NWS and USGS through the same feed as the homepage. Photographs are approved Catch Wall and Coastal Life submissions, credited as stored, plus a public-domain National Park Service photograph and, on lake and river views, a CC BY-SA 2.0 Flickr photograph of Falls Lake (cropped and colour-adjusted).</p>
"""
    meta = _public_head() if public else (
        '<meta name="robots" content="noindex, nofollow">\n'
        '<title>The Coastal Brief · %s (private concept)</title>\n'
        '<meta name="description" content="Private homepage concept for The Coastal Brief. Not public.">' % _esc(TITLES[variant]))
    css, icss = style_tag(variant), intro_css
    if public:   # drop the private-concept CSS comments from public view-source; rules unchanged
        css, icss = _CSS_COMMENT.sub("", css), _CSS_COMMENT.sub("", icss)
    page = page % {
        "meta": meta, "img_preload": preload, "foot": PUBLIC_FOOTER if public else priv_foot,
        "water": water, "defs": getattr(wave_intro, "_DEFS", ""),
        "v": variant, "shot": " data-shot" if shot else "", "title": _esc(TITLES[variant]),
        "css": css, "icss": icss, "boot": wave_intro._BOOT, "overlay": wave_intro._OVERLAY,
        "mast": _with_strip(masthead_html(variant, public=public, water=water), water), "main": main, "replay": wave_intro._REPLAY, "ijs": wave_intro._js(),
        "fb": _feedback_embed(),
        "nboot": NIGHT_BOOT,
    }
    return page.encode("utf-8")


# ---------------------------------------------------------------- concepts

def _photos():
    ph = approved_photos()
    return {
        "lead": photo_by_id(ph, LEAD_PHOTO_ID),
        "wide": photo_by_id(ph, WIDE_PHOTO_ID),
        "fresh": photo_by_id(ph, FRESH_PHOTO_ID),
        "life": photo_by_id(ph, LIFE_PHOTO_ID),
        "life2": photo_by_id(ph, LIFE2_PHOTO_ID),
        "bodie": BODIE if (PHOTO_DIR / "bodie-sunrise-800.avif").is_file() else None,
        "falls": FALLS if (PHOTO_DIR / "falls-lake-pier-800.avif").is_file() else None,
    }


def _is_lake(rid: str) -> bool:
    """Lake regions carry a "lake" block in the freshwater registry; rivers carry "river"."""
    try:
        import freshwater
        r = freshwater.regions().get(rid) or {}
        if "lake" in r or "river" in r:
            return "lake" in r
    except Exception:
        pass
    return rid.endswith("-lake")


def credit_html(p: dict) -> str:
    """Credit markup. Only our own FALLS constant carries pre-built link markup; everything else is escaped text."""
    if p is FALLS or (p.get("id") == FALLS["id"] and p.get("credit_html") == FALLS["credit_html"]):
        return FALLS["credit_html"]
    return _esc(credit(p))


BODIE_SLOT = "Bodie Island Lighthouse at sunrise. Ed's pick, but it is not in the approved Catch Wall or Coastal Life collections yet."
STORY_SLOT = "A working-waterfront story with a named, consenting source."


def _card(kicker: str, title: str, body: str, fig: str, href: str = "", cls: str = "") -> str:
    head = ('<a href="%s">%s</a>' % (_esc(href, True), _esc(title))) if href else _esc(title)
    return '<article class="card %s">%s<p class="kicker">%s</p><h3>%s</h3><p>%s</p></article>' % (
        cls, fig, _esc(kicker), head, _esc(body))


def page_heritage(m: dict, P: dict) -> str:
    return (
        conditions_html(m, variant="heritage")
        + '<section class="hx-water" aria-labelledby="hx-w"><h2 id="hx-w" class="sec"><span class="dm dm-sq" aria-hidden="true"></span>From the working water</h2>'
        + '<div class="hx-plates">'
        + figure(P["lead"], "plate plate-lead", "(min-width: 1000px) 560px, 100vw", ratio="4 / 3")
        + figure(P["wide"], "plate", "(min-width: 1000px) 360px, 50vw", ratio="4 / 3")
        + figure(P["fresh"], "plate", "(min-width: 1000px) 360px, 50vw", ratio="4 / 3")
        + "</div></section>"
        + '<section class="hx-log" aria-labelledby="hx-l"><h2 id="hx-l" class="sec"><span class="dm dm-tri" aria-hidden="true"></span>Logbook</h2>'
        + '<div class="hx-cards">'
        + _card("Catch Wall", "Share a catch from North Carolina water", "Approved photos appear here with the name and place you give us.", "", "/catch-wall")
        + _card("Story slot", STORY_SLOT, "Nothing runs here until it is reported and the people in it agree.", figure(None, "plate", "", STORY_SLOT, "3 / 2"))
        + _card("Photo slot", "Bodie Island Lighthouse", BODIE_SLOT, figure(None, "plate", "", "Bodie Island Lighthouse, sunrise", "3 / 2"))
        + "</div></section>"
        + system_html("heritage")
    )


def page_editorial(m: dict, P: dict) -> str:
    lead = figure(P["lead"], "ed-lead", "(min-width: 1000px) 720px, 100vw", ratio="4 / 5")
    return (
        '<div class="ex-top">'
        + conditions_html(m, variant="editorial")
        + '<section class="ex-lead" aria-labelledby="ex-lh"><p class="kicker">Catch Wall</p>'
        + '<h2 id="ex-lh" class="ex-hed">Red drum on the Neuse at New Bern</h2>'
        + '<p class="ex-dek">A community photograph from the Catch Wall. The story behind it has not been reported yet.</p>'
        + lead + "</section></div>"
        + '<section class="ex-grid" aria-labelledby="ex-gh"><h2 id="ex-gh" class="sec">Along the water</h2>'
        + _card("Catch Wall", "Striped bass, Roanoke River", "Community photograph, as submitted.", figure(P["wide"], "", "(min-width: 1000px) 380px, 100vw", ratio="4 / 3"), "/catch-wall")
        + _card("Freshwater", "Weldon", "Community photograph, as submitted. Species was not recorded.", figure(P["fresh"], "", "(min-width: 1000px) 380px, 100vw", ratio="4 / 3"), "/catch-wall")
        + _card("Coastal Life", "Rx Chicken & Oysters, Wilmington", "Community photograph from Coastal Life.", figure(P["life"], "", "(min-width: 1000px) 380px, 100vw", ratio="4 / 3"))
        + _card("Photo slot", "Bodie Island Lighthouse at sunrise", BODIE_SLOT, figure(None, "", "", "Bodie Island Lighthouse, sunrise", "4 / 3"))
        + _card("Story slot", "Working waterfronts", STORY_SLOT, figure(None, "", "", "Story photograph", "4 / 3"))
        + "</section>"
        + system_html("editorial")
    )


def _mosaic_cell(p: dict | None, cls: str, sizes: str, slot: str = "", kicker: str = AWAITING, cap: str | None = None) -> str:
    if not p:
        return (
            '<figure class="mz %s mz-slot"><div class="mz-slot-in"><p class="mz-k">%s</p>'
            '<p class="mz-t">%s</p></div></figure>'
        ) % (cls, _esc(kicker), _esc(slot))
    return (
        '<figure class="mz %s"><div class="mz-img">%s</div>'
        '<figcaption><span class="mz-cap">%s</span><span class="mz-credit">%s</span></figcaption></figure>'
    ) % (cls, img_html(p, sizes), _esc(caption(p) if cap is None else cap), credit_html(p))


MZ_SIZES = {"mz-a": "(min-width: 1000px) 400px, 50vw", "mz-b": "(min-width: 1000px) 400px, 50vw",
            "mz-c": "(min-width: 1000px) 400px, 50vw", "mz-d": "(min-width: 1000px) 820px, 100vw",
            "mz-e": "(min-width: 1000px) 400px, 50vw"}
MZ_CTA = ('<aside class="mz mz-cta"><p class="mz-cta-k">Catch Wall</p><p class="mz-cta-t">Caught something, or ate well on the water?</p>'
          '<a class="mz-cta-a" href="/catch-wall">Share yours on the Catch Wall</a></aside>')


# Daily photo: the placeholder colour shows first, then the decoded image fades in once (no flash, no CLS:
# the frame's aspect-ratio is fixed). Runs inline right after the frame so it is set before the image paints.
# Already-cached images are left alone. Reduced motion: no transition (CSS).
FP_FADE_JS = ("<script>(function(){var i=document.querySelector('.hz-rot .hz-img img');if(!i||i.complete)return;"
              "var w=i.parentNode.closest('.hz-img');w.classList.add('fp-wait');var d=0;function r(){if(d)return;d=1;w.classList.remove('fp-wait');}"
              "if(i.decode){i.decode().then(r,r);}i.addEventListener('load',r);i.addEventListener('error',r);setTimeout(r,4000);})();</script>")


CHARACTER_LINE = "More than the forecast. It's a way of life."


def _character_photo(m: dict, P: dict) -> dict | None:
    """A licensed rotation frame that is not today's horizon. Salt pages stay salt-eligible."""
    fresh = m.get("water") == "fresh"
    hero_id = ""
    if not fresh:
        hero_id = ((P.get("featured") or {}).get("id") or "")
    elif (m.get("region") or {}).get("id") == "falls-lake":
        hero_id = "falls-lake-pier"
    try:
        man = photo_rotation.active()
        if not man:
            return None
        photos = [e for e in man["photos"] if e.get("approved")]
        if fresh:
            pool = [e for e in photos if e.get("category") == "freshwater" or photo_rotation.is_inland(e)]
        else:
            pool = [e for e in photos if photo_rotation.salt_eligible(e)]
        pool = [e for e in pool if e.get("id") != hero_id]
        if not pool:
            return None
        from datetime import timedelta
        shot = photo_rotation.pick(pool, photo_rotation.et_date() + timedelta(days=1))
        return photo_rotation.resolve(shot, approved_photos()) if shot else None
    except Exception:
        return None


def _character_picture(photo: dict) -> str:
    """Lazy, compact <picture> from a rotation entry. Credits and alt stay as stored."""
    srcs = photo.get("sources") or {}
    fmts = [(f, m) for f, m in photo_rotation.FORMATS if srcs.get(f)]
    if not fmts:
        return ""
    parts = []
    for fmt, mime in fmts[:-1]:
        parts.append('<source type="%s" srcset="%s" sizes="(min-width:1000px) 140px, 96px">' % (
            mime, photo_rotation.srcset(srcs[fmt])))
    last = srcs[fmts[-1][0]]
    fb_w = 640 if 640 in last else (800 if 800 in last else min(last))
    alt = photo.get("alt") or photo.get("description") or photo.get("location") or ""
    w, h = int(photo.get("width") or 1600), int(photo.get("height") or 1000)
    return '<picture>%s<img src="%s" srcset="%s" sizes="(min-width:1000px) 140px, 96px" alt="%s" width="%d" height="%d" loading="lazy" decoding="async"></picture>' % (
        "".join(parts), _esc(photo_rotation.src_url(last[fb_w]), True),
        photo_rotation.srcset(last), _esc(alt, True), w, h)


def character_html(m: dict, P: dict) -> str:
    """Compact editorial band below conditions / forecast / advisories."""
    photo = _character_photo(m, P)
    fig = ""
    if photo:
        cap = photo.get("description") or photo.get("location") or ""
        loc = photo.get("location") or ""
        if cap and loc and photo_rotation._squash(loc) in photo_rotation._squash(cap):
            loc = ""
        credit = photo_rotation.credit_html(photo)
        meta = " · ".join(b for b in (cap, loc) if b)
        pic = _character_picture(photo)
        if pic:
            fig = (
                '<figure class="cb-life-fig" data-photo="%s" data-category="%s">%s'
                '<figcaption>%s%s</figcaption></figure>'
            ) % (_esc(photo["id"], True), _esc(photo.get("category") or "", True), pic,
                 ('<span class="cb-life-cap">%s</span> ' % _esc(meta)) if meta else "",
                 '<span class="cb-life-cr">%s</span>' % credit)
    return (
        '<aside class="cb-life" aria-labelledby="cb-life-h">'
        '<p id="cb-life-h" class="cb-life-t">%s</p>%s</aside>'
    ) % (_esc(CHARACTER_LINE), fig)


BRAND_LINE = ('<div class="bl"><p class="bl-p"><span class="bl-k">The Coastal Brief —</span> '
              '<span class="bl-t">Know the Water. Live the Coast.</span></p></div>')


def page_hybrid(m: dict, P: dict, public: bool = False) -> str:
    fresh = m.get("water") == "fresh"
    lake = fresh and _is_lake((m.get("region") or {}).get("id") or "")
    falls = P.get("falls")
    rid = (m.get("region") or {}).get("id") or ""
    if lake and rid == "falls-lake":   # Falls Lake leads only on its own page
        hero, wide = falls, P["fresh"]
    elif lake:    # other lakes: no lake hero (thin brass line); never a photo of a different lake as the lead
        hero, wide = None, P["fresh"]
    elif fresh:   # rivers: Weldon (Roanoke River) leads; the Falls Lake frame takes the wide cell
        hero, wide = (P["fresh"] or falls or P["bodie"]), falls or P["bodie"]
    else:   # saltwater: the daily featured photo (photo_rotation), else the Bodie Island default
        hero, wide = (P.get("featured") or P["bodie"] or P["lead"]), P["fresh"]
    hero_cw = (hero or {}).get("catch_wall_id") or ""
    # Each photo gets the shape that suits it: the portrait diner frame (89eef7f7) takes the tall cell.
    want = [("mz-a", P["lead"]), ("mz-b", P["wide"]), ("mz-c", P["life"]), ("mz-e", P.get("life2")),
            ("mz-d", wide)]
    placed = [(sh, x) for sh, x in want if x and x is not hero and str(x.get("id") or "").lower() != hero_cw.lower()]
    # No placeholders: empty cells are dropped. A full set uses the composed mosaic; fewer falls back to a loose grid.
    full = len(placed) == len(want)
    # Stored captions as submitted. When two photos share the same stored caption (the two diner frames),
    # the location is shown once: the later frame keeps its credit but drops the repeated caption.
    seen, cells = set(), []
    if hero is not None and hero is P.get("featured"):   # the featured photo's place is already captioned above
        seen.add(re.sub(r"\s+", "", hero.get("location") or "").casefold())
    for sh, x in placed:
        c = caption(x)
        key = re.sub(r"\s+", "", c).casefold()   # "Rx Chicken& Oysters" == "Rx Chicken & Oysters"
        cells.append(_mosaic_cell(x, sh, MZ_SIZES[sh], cap="" if key in seen else c))
        seen.add(key)
    cells.append(MZ_CTA)
    grid_cls = "mz-grid" + ("" if full else " mz-loose mz-n%d" % len(placed))
    if hero and hero is P.get("featured"):
        horizon = photo_rotation.horizon_html(hero) + FP_FADE_JS
    elif hero:
        horizon = (
            '<section class="hz%s" aria-labelledby="hz-h"><div class="hz-img">%s</div>'
            '<div class="hz-cap"><h2 id="hz-h" class="hz-t">%s</h2><p class="hz-m">%s</p><p class="hz-c">%s</p></div></section>'
        ) % ((" " + _esc(hero["hz_class"], True)) if hero.get("hz_class") else "", img_html(hero, "100vw"), _esc(hero.get("title") or hero.get("location") or caption(hero)),
             _esc(" · ".join(b for b in (hero.get("species"), hero.get("location") if hero.get("title") else None, hero.get("region")) if b)),
             credit_html(hero))
    else:
        horizon = '<div class="hz-none" aria-hidden="true"></div>'
    return (
        conditions_html(m, variant="hybrid", public=public)
        + character_html(m, P)
        + horizon
        + BRAND_LINE
        + '<section class="mzs" aria-labelledby="mz-h"><p class="kicker"><span class="dm dm-sq" aria-hidden="true"></span>Catch Wall · Coastal Life</p>'
        + '<h2 id="mz-h" class="mzs-h">From the docks, sounds and rivers</h2>'
        + '<p class="mzs-dek">Approved community photographs, shown as they were submitted.</p>'
        + '<div class="%s">%s</div></section>' % (grid_cls, "".join(cells))
        + ("" if public else system_html("hybrid"))
    )


BUILDERS = {"heritage": page_heritage, "editorial": page_editorial, "hybrid": page_hybrid}


def _featured(day=None, photo_id: str | None = None):
    try:
        # only ever called for saltwater views: salt=True keeps freshwater/inland photos out
        return photo_rotation.featured(day=day, photo_id=photo_id, approved=approved_photos(), salt=True)
    except Exception:
        return None   # the Bodie Island default stays


def page(variant: str, region_id: str | None = None, shot: bool = False, public: bool = False,
         photo_day: str | None = None, photo_id: str | None = None) -> bytes:
    """public=True is the public homepage (/): Hybrid only, public regions only, no concept chrome.
    photo_day (YYYY-MM-DD) and photo_id are preview-only overrides; the public page ignores them."""
    if variant not in BUILDERS:
        raise ValueError("unknown concept")
    if public:
        if variant != "hybrid":
            raise ValueError("only the Hybrid page is public")
        rid = (region_id or "").strip()
        if rid not in public_salt_ids() and rid not in public_fresh_ids():
            region_id = None   # unknown or not-public ids fall back to the default region, never render
        m = model(region_id)
        P = _photos()
        fresh = m.get("water") == "fresh"
        P["featured"] = None if fresh else _featured()
        data = _shell(variant, page_hybrid(m, P, public=True), shot, water=m.get("water") or "salt", public=True,
                      preload=photo_rotation.preload_html(P["featured"]))
        # Header "Morning Brief" follows the region on screen (its own brief, else the nearest).
        import site_chrome
        tgt = site_chrome.brief_target(((m.get("region") or {}).get("id")) or region_id)[0]
        data = data.replace(b'<a href="/brief?region=crystal-coast" id="nav-brief">',
                            b'<a href="/brief?region=' + tgt.encode("ascii", "ignore") + b'" id="nav-brief">', 1)
        return data.replace(PHOTO_ROUTE.encode(), PUBLIC_PHOTO_ROUTE.encode())
    m = model(region_id)
    P = _photos()
    pre = ""
    if variant == "hybrid" and m.get("water") != "fresh":
        P["featured"] = _featured(photo_rotation.parse_day(photo_day or ""), (photo_id or "")[:64] or None)
        pre = photo_rotation.preload_html(P["featured"])
    return _shell(variant, BUILDERS[variant](m, P), shot, water=m.get("water") or "salt", preload=pre)
