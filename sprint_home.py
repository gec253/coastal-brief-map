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
from datetime import datetime, timezone
from pathlib import Path

import conditions
import homepage_boot
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
    return _tile(
        id=tid, name=name, state=st, dir=v.get("dirCompass") or "", num=str(_r0(spd)), unit="kt",
        sub=("Gust %s kt" % _r0(gust)) if _num(gust) else GUST_MISSING,
        src=_station(r), when=et_time(r.get("time")),
        dial=v.get("dirDeg") if _num(v.get("dirDeg")) else None,
    )


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


def _water_tile(R) -> dict:
    inshore = R.get("waterTemp")
    off = R.get("waterTempOffshore")
    if _state(inshore) != "off":
        t = _temp_tile(inshore, "Water", "water", note="Inshore station")
        ov = _vals(off)
        if _state(off) != "off" and _num(ov.get("f")):
            t["sub"] = "Offshore buoy %s°F" % _r0(ov["f"])
        return t
    if _state(off) != "off":
        # No inshore sensor here (Nags Head, Emerald Isle, Topsail): label it offshore.
        return _temp_tile(off, "Water", "water", note="Offshore buoy")
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
    src = (st.get("name") or "") + ((" · " + st["id"]) if st.get("id") else "")
    if tides.get("status") != "ok" or not evs:
        return _tile(id="tide", name="Tide", kind="Predicted", state="off", off=TIDE_OFF, src=src)
    ev = evs[0]
    clock = homepage_boot._clock(ev["t"])
    hm, ampm = clock.split(" ") if " " in clock else (clock, "")
    nxt = evs[1] if len(evs) > 1 else None
    sub = "%s ft %s" % (_fmt(ev.get("v"), 1), tides.get("datum") or "") if _num(ev.get("v")) else ""
    if nxt:
        sub += (" · then %s %s" % ("high" if nxt.get("type") == "H" else "low", homepage_boot._clock(nxt["t"])))
    t = _tile(id="tide", name="Next high" if ev.get("type") == "H" else "Next low", kind="Predicted",
              num=hm, unit=ampm + " ET", sub=sub.strip(), src=src, when="")
    obs = tides.get("observed")
    if isinstance(obs, dict) and obs.get("status") in ("ok", "stale"):
        lt = obs.get("latest") or {}
        if _num(lt.get("v")):
            line = "Observed %s ft" % _fmt(lt["v"], 1)
            if _num(lt.get("diff")):
                line += ", %+.1f vs predicted" % lt["diff"]
            t["obs"] = line + " (preliminary, " + et_time(obs.get("time")) + ")"
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
        "alerts": _alerts(payload.get("alerts")), "forecast": _marine(payload.get("marine")),
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
        "alerts": _alerts(payload.get("alerts")), "forecast": forecast,
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
                return fresh_model(payload)
        else:
            status, payload = conditions.assemble(rid)
            if status == 200 and (payload or {}).get("ok"):
                return salt_model(payload)
    except Exception:
        pass
    return {"ok": False, "water": "salt", "region": {"id": rid or "", "name": ""}, "tiles": [], "more": [],
            "alerts": {"state": "unknown", "items": [{"event": ALERTS_OFF[0], "meta": ALERTS_OFF[1]}]},
            "forecast": None, "updated": ""}


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
    who = ("Photo: %s" % p["name"]) if p.get("name") else "Photographer not recorded"
    return "%s community photo · %s" % (collection(p), who)


def caption(p: dict) -> str:
    bits = [b for b in (p.get("species"), p.get("location"), p.get("region")) if b]
    return " · ".join(bits)


def alt(p: dict) -> str:
    try:
        import catch_wall_public
        return catch_wall_public._alt(p)
    except Exception:
        return caption(p) or "Community photograph"


def figure(p: dict | None, cls: str, sizes: str, slot_title: str = "", ratio: str = "4 / 5") -> str:
    """A credited photo, or an honest empty slot."""
    if not p:
        return (
            '<figure class="ph ph-empty %s" style="aspect-ratio:%s"><div class="ph-slot">'
            '<p class="ph-slot-k">%s</p><p class="ph-slot-t">%s</p></div></figure>'
        ) % (cls, ratio, AWAITING, _esc(slot_title))
    src = p.get("src") or {}
    parts = []
    for key in ("400", "800", "1600"):
        if src.get(key):
            parts.append("%s %sw" % (_esc(src[key], True), key))
    fallback = src.get("800") or src.get("400") or ""
    return (
        '<figure class="ph %s"><div class="ph-frame" style="aspect-ratio:%s">'
        '<img src="%s" srcset="%s" sizes="%s" alt="%s" width="%d" height="%d" loading="lazy" decoding="async"></div>'
        '<figcaption><span class="ph-cap">%s</span> <span class="ph-credit">%s</span></figcaption></figure>'
    ) % (cls, ratio, _esc(fallback, True), ", ".join(parts), sizes, _esc(alt(p), True),
         int(p.get("w") or 1600), int(p.get("h") or 1200), _esc(caption(p)), _esc(credit(p)))


# ---------------------------------------------------------------- instruments markup

def _dial(deg) -> str:
    """Rim marker at the bearing the wind comes from (true north up)."""
    if deg is None:
        return ""
    a = math.radians(float(deg))
    x, y = 20 + 15 * math.sin(a), 20 - 15 * math.cos(a)
    return (
        '<svg class="t-dial" viewBox="0 0 40 40" aria-hidden="true" focusable="false">'
        '<circle cx="20" cy="20" r="15" class="d-rim"/>'
        '<path d="M20 3v4M20 33v4M3 20h4M33 20h4" class="d-tick"/>'
        '<circle cx="%.2f" cy="%.2f" r="3.6" class="d-mark"/></svg>'
    ) % (x, y)


def _tide_spark(t: dict) -> str:
    curve = [c for c in (t.get("curve") or []) if isinstance(c, (list, tuple)) and len(c) == 2 and _num(c[1])]
    if len(curve) < 10:
        return ""
    now = _now_ms()
    t0, t1 = now - 3 * 3600e3, now + 12 * 3600e3
    pts = [c for c in curve if t0 <= c[0] <= t1]
    if len(pts) < 10:
        return ""
    lo = min(p[1] for p in pts)
    hi = max(p[1] for p in pts)
    span = (hi - lo) or 1
    W, H = 160.0, 34.0
    path = " ".join(
        ("M" if i == 0 else "L") + "%.1f %.1f" % ((p[0] - t0) / (t1 - t0) * W, H - 3 - (p[1] - lo) / span * (H - 6))
        for i, p in enumerate(pts)
    )
    nx = (now - t0) / (t1 - t0) * W
    return (
        '<svg class="t-spark" viewBox="0 0 160 34" preserveAspectRatio="none" aria-hidden="true" focusable="false">'
        '<path d="%s" class="s-line"/><path d="M%.1f 0V34" class="s-now"/></svg>'
    ) % (path, nx)


def tile_html(t: dict, big: bool = False) -> str:
    st = t["state"]
    cls = "t t-%s%s%s" % (t["id"], " is-stale" if st == "stale" else "", " is-off" if st == "off" else "")
    kind_cls = {"Observed": "k-obs", "Predicted": "k-pred", "Forecast": "k-fc"}.get(t["kind"], "k-obs")
    hid = "t-%s-n" % t["id"]
    if st == "stale":
        chip = '<span class="t-chip c-stale" title="Older than this station\'s normal reporting gap">Stale · %s</span>' % _esc(t["when"])
    else:
        chip = '<span class="t-kind %s">%s</span>' % (kind_cls, _esc(t["kind"]))
    out = ['<div class="%s" role="group" aria-labelledby="%s">' % (cls, hid)]
    out.append('<div class="t-head"><h3 class="t-name" id="%s">%s</h3>%s</div>' % (hid, _esc(t["name"]), chip))
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
        out.append('<p class="t-read">%s%s</p>' % ("".join(read), _dial(t.get("dial"))))
        if t.get("note"):
            out.append('<p class="t-note">%s</p>' % _esc(t["note"]))
        if t["sub"]:
            out.append('<p class="t-sub">%s</p>' % _esc(t["sub"]))
        if t.get("obs"):
            out.append('<p class="t-sub t-obs">%s</p>' % _esc(t["obs"]))
        if t.get("fc"):
            out.append('<p class="t-sub t-fcline"><span class="t-chip k-fc">Forecast</span> %s</p>' % _esc(t["fc"].replace("Forecast ", "")))
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


def alerts_html(a: dict, pennants: bool = False) -> str:
    st = a["state"]
    rows = []
    for it in a["items"]:
        flag = ""
        if pennants and st == "active":
            flag = _pennant(it["event"])
        rows.append('<p class="al-row">%s<b>%s</b>%s</p>' % (
            flag, _esc(it["event"]), (' <span>%s</span>' % _esc(it["meta"])) if it["meta"] else ""))
    return '<div class="al al-%s" role="status">%s<a class="al-link" href="%s" rel="noopener">NWS details</a></div>' % (
        st, "".join(rows), homepage_boot.NWS_DETAILS)


def _pennant(event: str) -> str:
    """Historic NWS coastal warning display flags, only for a live matching alert."""
    e = event.lower()
    pen = '<path d="M2 2 L22 8 L2 14 Z" fill="#B3261E"/>'
    sq = '<rect x="2" y="2" width="16" height="16" fill="#B3261E"/><rect x="7" y="7" width="6" height="6" fill="#111"/>'
    if "hurricane" in e:
        body, w = sq + '<g transform="translate(20 0)">' + sq + "</g>", 40
    elif "storm" in e:
        body, w = sq, 20
    elif "gale" in e:
        body, w = pen + '<g transform="translate(0 6)">' + pen + "</g>", 24
    elif "small craft" in e:
        body, w = pen, 24
    else:
        return ""
    return '<svg class="al-flag" viewBox="0 0 %d 22" width="%d" height="22" aria-hidden="true">%s</svg>' % (w, w, body)


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
    if variant == "editorial" and (more or fc):
        # Editorial keeps the four headline readings on the first screen and
        # folds the rest under one labelled control so the photograph leads.
        label = "Swell, barometer and the marine forecast" if m.get("water") == "salt" else "Rain and the NWS forecast"
        return ('<details class="cg-fold"><summary>%s</summary>%s%s</details>' % (label, more, fc), "")
    return (more, fc)


def conditions_html(m: dict, *, variant: str) -> str:
    reg = m.get("region") or {}
    rid = reg.get("id") or ""
    if not m.get("ok"):
        body = '<p class="cg-off">%s</p>' % PAYLOAD_OFF
        tiles = ""
        more = ""
    else:
        body = alerts_html(m["alerts"], pennants=variant in ("heritage", "hybrid"))
        tiles = '<div class="cg-grid">%s</div>' % "".join(tile_html(t) for t in m["tiles"])
        more = ('<div class="cg-more" role="group" aria-label="Also observed"><p class="cg-more-k">Also observed</p>%s</div>' % "".join(tile_html(t) for t in m["more"])) if m["more"] else ""
    links = []
    for r_id, name, cur in region_links(rid):
        links.append('<a href="?region=%s"%s>%s</a>' % (_esc(r_id, True), ' aria-current="true"' if cur else "", _esc(name)))
    dash = "/lake?region=%s" % rid if m.get("water") == "fresh" else ("/?region=%s" % rid if rid else "/")
    return (
        '<section class="cg cg-%s" id="conditions" aria-labelledby="cg-h" data-conditions>'
        '<header class="cg-head"><h2 id="cg-h">Conditions at a Glance</h2>'
        '<p class="cg-where">%s</p>'
        '<p class="cg-upd">%s</p></header>'
        "%s%s%s%s"
        '<div class="cg-foot"><details class="cg-region"><summary>Change water</summary><nav aria-label="Regions">%s</nav></details>'
        '<a class="cg-link" href="%s">Full dashboard</a><a class="cg-link" href="/brief?region=%s">Morning Brief</a></div>'
        "</section>"
    ) % (
        variant, _esc(reg.get("name") or ""),
        ("Updated %s" % _esc(m["updated"])) if m.get("updated") else "",
        body, tiles, *_extras(m, more, variant),
        "".join(links), _esc(dash, True), _esc(rid, True),
    )


# ---------------------------------------------------------------- page chrome

def _today() -> str:
    d = datetime.now(homepage_boot.ET)
    return "%s, %s %d, %d" % (d.strftime("%A"), d.strftime("%B"), d.day, d.year)


def masthead_html(variant: str) -> str:
    return (
        '<header class="mh mh-%s"><p class="pv-flag">Private concept · %s</p>'
        '<div class="mh-bar"><a class="mh-mark" href="/">The Coastal Brief</a>'
        '<nav class="mh-nav" aria-label="Sections"><a href="/brief">Morning Brief</a><a href="/catch-wall">Catch Wall</a></nav></div>'
        '<div class="mh-plate"><h1 class="mh-name"><a href="/">The Coastal Brief</a></h1>'
        '<svg class="mh-rule" viewBox="0 0 400 4" preserveAspectRatio="none" aria-hidden="true" focusable="false">'
        '<line class="wave-settle" x1="0" y1="2" x2="400" y2="2"/></svg>'
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
        ("Morning Brief", "Navy readings band from Heritage on top, editorial body type below. One brass rule ties them."),
        ("Freshwater dashboards", "Same band with marsh green accent; lake level, release and inflow keep the tile grid."),
        ("Galleries", "Editorial grid with Heritage plate captions."),
        ("Editorial sections", "Magazine layout with daymark section markers used once per page."),
    ),
}


def system_html(variant: str) -> str:
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


def _shell(variant: str, main: str, shot: bool) -> bytes:
    intro_css = wave_intro._css()
    page = """<!DOCTYPE html>
<html lang="en" data-sprint="%(v)s" data-wave-intro%(shot)s>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="robots" content="noindex, nofollow">
<meta name="color-scheme" content="light dark">
<title>The Coastal Brief · %(title)s (private concept)</title>
<meta name="description" content="Private homepage concept for The Coastal Brief. Not public.">
<link rel="preload" href="/fonts/fraunces-var.woff2" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="/fonts/barlow-condensed-600.woff2" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="/fonts/source-sans-3-var.woff2" as="font" type="font/woff2" crossorigin>
<link rel="icon" href="/branding/favicon.svg" type="image/svg+xml">
<link rel="preconnect" href="https://wgjoenkugzfrrfejmtvh.supabase.co" crossorigin>
%(css)s<style id="wave-intro-css">
%(icss)s
</style>
%(boot)s</head>
<body>
%(overlay)s
<a class="skip" href="#conditions">Skip to Conditions at a Glance</a>
%(mast)s
<main id="main">%(main)s</main>
<footer class="ft"><div class="ft-in">
<p>Private concept preview. Readings are live from NOAA, NWS and USGS through the same feed as the homepage. Photographs are approved Catch Wall and Coastal Life submissions, credited as stored.</p>
%(replay)s</div></footer>
<script>
%(ijs)s
</script>
</body>
</html>
""" % {
        "v": variant, "shot": " data-shot" if shot else "", "title": _esc(TITLES[variant]),
        "css": style_tag(variant), "icss": intro_css, "boot": wave_intro._BOOT, "overlay": wave_intro._OVERLAY,
        "mast": masthead_html(variant), "main": main, "replay": wave_intro._REPLAY, "ijs": wave_intro._js(),
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
    }


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


def page_hybrid(m: dict, P: dict) -> str:
    return (
        conditions_html(m, variant="hybrid")
        + '<section class="hy-feature" aria-labelledby="hy-f">'
        + figure(P["lead"], "hy-lead", "(min-width: 1000px) 640px, 100vw", ratio="3 / 2")
        + '<div class="hy-copy"><p class="kicker"><span class="dm dm-sq" aria-hidden="true"></span>Catch Wall</p>'
        + '<h2 id="hy-f" class="hy-hed">Red drum on the Neuse at New Bern</h2>'
        + '<p class="hy-dek">A community photograph, shown as it was submitted. No story has been reported for it yet.</p>'
        + '<p><a class="hy-cta" href="/catch-wall">Open the Catch Wall</a></p></div></section>'
        + '<section class="hy-row" aria-labelledby="hy-r"><h2 id="hy-r" class="sec">Coast and inland</h2><div class="hy-strip" tabindex="0" role="region" aria-label="Photographs, scroll sideways">'
        + figure(P["wide"], "", "(min-width: 1000px) 300px, 70vw", ratio="4 / 3")
        + figure(P["fresh"], "", "(min-width: 1000px) 300px, 70vw", ratio="4 / 3")
        + figure(P["life"], "", "(min-width: 1000px) 300px, 70vw", ratio="4 / 3")
        + figure(None, "", "", "Bodie Island Lighthouse, sunrise. Not in the approved collections yet.", "4 / 3")
        + "</div></section>"
        + system_html("hybrid")
    )


BUILDERS = {"heritage": page_heritage, "editorial": page_editorial, "hybrid": page_hybrid}


def page(variant: str, region_id: str | None = None, shot: bool = False) -> bytes:
    if variant not in BUILDERS:
        raise ValueError("unknown concept")
    m = model(region_id)
    return _shell(variant, BUILDERS[variant](m, _photos()), shot)
