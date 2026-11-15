"""Preview-only copy: honest labels, deterministic summaries, professional strings.

Wraps or rewrites brief.build_salt and freshwater preview items. Does not
edit brief.py.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import brief
import brief_strings
import conditions
import preview_alerts

ET = ZoneInfo("America/New_York")


def _item_alert(text: str) -> str:
    return text[len("Alerts: "):] if text.startswith("Alerts: ") else text

# Informal fragments that must not appear in rendered preview HTML.
INFORMAL = (
    "n/a",
    "unavailable",
    "Could not check",
    "right now",
    "Inshore unavailable",
    "not available from USGS right now",
)

_STALE_MISS = re.compile(
    r"^(?P<label>.+?) \(stale: last report (?P<time>.+), not used\)$"
)
_STALE_FC = re.compile(
    r"^(?P<label>.+) \(stale: NWS issued (?P<time>.+), not used\)$"
)


def place_word(meta: dict | None, role: str = "", kind: str = "") -> str | None:
    """offshore / nearshore / sound-side from the official setting or role, never guessed from distance alone."""
    blob = " ".join(
        str(x or "") for x in (
            (meta or {}).get("setting"),
            (meta or {}).get("name"),
            (meta or {}).get("network"),
            role,
            kind,
        )
    ).lower()
    if "sound" in blob or "marina" in blob:
        return "sound-side"
    if "nearshore" in blob:
        return "nearshore"
    if "offshore" in blob:
        return "offshore"
    if "waverider" in blob or "buoy" in blob:
        # Wave buoys that are not called nearshore or offshore in the record
        # still need a setting word only if the official setting uses one.
        return None
    return None


def where(sid: str, meta: dict | None, anchor: dict | None, role: str = "", kind: str = "") -> str:
    """'Name (id), N mi BEARING of Anchor (offshore)' or 'Name (id)' when local."""
    meta = meta or {}
    info = conditions.station_info(sid, meta, anchor)
    name = info.get("name") or sid
    loc = "%s (%s)" % (name, sid)
    d = info.get("distanceMi")
    b = info.get("bearingFromAnchor")
    anchor_label = (anchor or {}).get("label") or (info.get("anchor") or "the region anchor")
    if d is not None and float(d) >= 0.5 and b:
        # distances already rounded by station_info
        dtxt = str(int(d)) if float(d) == int(d) else str(d)
        loc += ", %s mi %s of %s" % (dtxt, b, anchor_label)
    word = place_word(meta, role, kind)
    if word:
        loc += " (%s)" % word
    return loc


def _ok(block: dict | None) -> bool:
    return bool(block) and block.get("status") == "ok" and not block.get("stale")


def _tides_text(t: dict, cfg: dict, stations: dict, anchor: dict) -> str | None:
    if t.get("status") != "ok":
        return None
    st = t.get("station") or {}
    sid = st.get("id") or (cfg.get("tide") or {}).get("station")
    meta = stations.get(sid) or {}
    pred_where = where(sid, {**meta, **{k: st.get(k) or meta.get(k) for k in ("name", "lat", "lon", "setting", "agency")}},
                       anchor, role="tide predictions")
    evs = t.get("events") or []
    # keep today's events already selected by build_salt; if the item listed them, we rebuild from t
    now = datetime.now(timezone.utc)
    day = now.astimezone(ET).date()
    today = []
    for e in evs:
        try:
            d = datetime.fromtimestamp(e["t"] / 1000, timezone.utc).astimezone(ET)
        except (KeyError, TypeError, ValueError, OSError):
            continue
        if d.date() == day:
            today.append((e, d))
    if not today:
        return None
    parts = []
    for e, d in today:
        kind = "high" if e.get("type") == "H" else "low"
        parts.append("%s %s (%.1f ft)" % (kind, brief._t(d), e.get("v")))
    text = "Predicted tides %s at %s, MLLW." % (", ".join(parts), pred_where)
    tide_cfg = cfg.get("tide") or {}
    if tide_cfg.get("observed") is False:
        text += " " + brief_strings.observed_water_level_not_measured(st.get("name") or sid)
    else:
        ob = t.get("observed") or {}
        if ob.get("status") == "ok" and ob.get("latest"):
            obs_sid = (ob.get("station") or {}).get("id") or tide_cfg.get("observedStation") or sid
            obs_meta = stations.get(obs_sid) or (ob.get("station") or {})
            obs_where = where(obs_sid, obs_meta, anchor, role="observed water level")
            latest = ob["latest"]
            try:
                ot = brief._t(datetime.fromtimestamp(latest["t"] / 1000, timezone.utc))
            except (KeyError, TypeError, ValueError, OSError):
                ot = None
            lvl = latest.get("v")
            bit = "Observed water level is %.2f ft MLLW at %s" % (lvl, obs_where) if lvl is not None else (
                "Observed water level is from %s" % obs_where)
            if ot:
                bit += ", observed at %s" % ot
            bit += "."
            if obs_sid != sid:
                bit += " It is not a local reading at %s." % (st.get("name") or sid)
            text += " " + bit
    return text


def _water_temp_text(R: dict, cfg: dict, stations: dict, anchor: dict) -> tuple[str, list]:
    """Return (item text, unavailable pairs)."""
    specs = cfg.get("readings") or {}
    unavail = []
    inshore = R.get("waterTemp") or {}
    offshore = R.get("waterTempOffshore") or {}
    inshore_spec = specs.get("waterTemp") or {}
    off_spec = specs.get("waterTempOffshore") or {}
    bits = []
    if _ok(inshore) and (inshore.get("values") or {}).get("f") is not None:
        st = inshore.get("station") or {}
        sid = st.get("id")
        bits.append("%.0f°F inshore at %s, observed." % (
            inshore["values"]["f"],
            where(sid, stations.get(sid) or st, anchor, role=inshore_spec.get("role") or "inshore", kind="waterTemp"),
        ))
    elif not (inshore_spec.get("sources")):
        bits.append(brief_strings.not_measured("Inshore water temperature"))
        unavail.append(("Inshore water temp", brief_strings.not_measured("Inshore water temperature")))
    elif inshore.get("status") == "stale" and inshore.get("time"):
        sid = (inshore.get("station") or {}).get("id") or (inshore_spec.get("sources") or ["the station"])[0]
        bits.append(brief_strings.not_used(
            "Inshore water temperature", brief._t(inshore["time"]),
            max(1, int(round((inshore.get("staleAfterMin") or 90) / 60))) or 2))
    # offshore / nearshore surface
    if _ok(offshore) and (offshore.get("values") or {}).get("f") is not None:
        st = offshore.get("station") or {}
        sid = st.get("id")
        meta = stations.get(sid) or st
        word = place_word(meta, off_spec.get("role") or "", "waterTempOffshore") or "surface"
        # Never call a nearshore buoy "offshore"
        label = "Nearshore water temperature" if word == "nearshore" else "Offshore water temperature"
        bits.append("%s: %.0f°F, observed at %s." % (
            label,
            offshore["values"]["f"],
            where(sid, meta, anchor, role=off_spec.get("role") or "", kind="waterTempOffshore"),
        ))
    return " ".join(bits), unavail


def relabel_salt(rid: str, body: dict, payload: dict, cfg: dict) -> dict:
    """Rebuild salt item wording with honest attribution; rewrite informal missing strings."""
    stations = (conditions.load_regions() or {}).get("stations") or {}
    anchor = (payload.get("region") or {}).get("anchor") or cfg.get("anchor") or {}
    R = (payload.get("readings") or {}) if payload else {}
    items = []
    specs = cfg.get("readings") or {}
    by_old = dict(body.get("items") or [])
    unavail = []

    # Alerts (was Advisories)
    al = payload.get("alerts") if payload else None
    if al is None:
        # keep build_salt advisories, but rewrite informal
        adv = by_old.get("Advisories") or ""
        if "Could not check" in adv:
            items.append(("Alerts", _item_alert(brief_strings.ALERTS_CHECK_FAILED)))
        elif adv.startswith("No NWS"):
            # coastal: use marine + land zone names if present
            zones = cfg.get("alertZones") or []
            areas = ", ".join(zones) if zones else "this area"
            items.append(("Alerts", _item_alert(brief_strings.alerts_none(areas))))
        else:
            items.append(("Alerts", "Alerts: " + adv if adv and not adv.lower().startswith("alert") else adv or brief_strings.ALERTS_CHECK_FAILED))
    elif al.get("items"):
        items.append(("Alerts", preview_alerts.alert_item_text(al, rid)))
    elif al.get("status") == "ok":
        zones = cfg.get("alertZones") or []
        areas = ", ".join(zones) if zones else "this area"
        # Prefer official zone names from marine + land if short
        names = []
        if (payload.get("marine") or {}).get("zone"):
            names.append((payload["marine"].get("zoneName") or payload["marine"]["zone"]))
        items.append(("Alerts", _item_alert(brief_strings.alerts_none(areas))))
    else:
        items.append(("Alerts", _item_alert(brief_strings.ALERTS_CHECK_FAILED)))

    def add_obs_kind(label, kind, verb, extra=""):
        r = R.get(kind) or {}
        if not _ok(r) or not r.get("values"):
            return False
        st = r.get("station") or {}
        sid = st.get("id")
        loc = where(sid, stations.get(sid) or st, anchor, role=(specs.get(kind) or {}).get("role") or "", kind=kind)
        items.append((label, verb + " at " + loc + (", observed." if not extra else extra)))
        return True

    # Wind
    if _ok(R.get("wind")) and (R["wind"].get("values") or {}).get("speedKt") is not None:
        v = R["wind"]["values"]
        st = R["wind"].get("station") or {}
        sid = st.get("id")
        loc = where(sid, stations.get(sid) or st, anchor, role=(specs.get("wind") or {}).get("role") or "", kind="wind")
        gust = v.get("gustKt") or v.get("speedKt")
        lead = card_lead(sid, stations.get(sid) or st, anchor, (specs.get("wind") or {}).get("role") or "", "wind")
        line = "%s: %d kt from the %s, gusting %d, observed at %s." % (
            lead or "Wind", round(v["speedKt"]), v.get("dirCompass") or "", round(gust or 0), loc)
        if not lead:
            line = "%d kt from the %s, gusting %d, observed at %s." % (
                round(v["speedKt"]), v.get("dirCompass") or "", round(gust or 0), loc)
        # keep the observed trend clause from build_salt if present
        old = by_old.get("Wind") or ""
        m = re.search(r"; ([^.;]*(?:earlier|steady)[^.]*)\.", old)
        if m:
            line = line[:-1] + "; " + m.group(1) + "."
        items.append(("Wind", line))
    # Seas — combined seas, never called swell
    if _ok(R.get("seas")) and (R["seas"].get("values") or {}).get("heightFt") is not None:
        v = R["seas"]["values"]
        st = R["seas"].get("station") or {}
        sid = st.get("id")
        loc = where(sid, stations.get(sid) or st, anchor, role=(specs.get("seas") or {}).get("role") or "", kind="seas")
        period = v.get("dominantPeriodS")
        dirc = v.get("meanDirCompass") or ""
        pbit = " every %d s" % round(period) if period else ""
        dbit = (" from the %s" % dirc) if dirc else ""
        lead = card_lead(sid, stations.get(sid) or st, anchor, (specs.get("seas") or {}).get("role") or "", "seas")
        prefix = (lead + ": ") if lead else ""
        line = "%sCombined seas %.1f ft%s%s at %s, observed." % (prefix, v["heightFt"], pbit, dbit, loc)
        old = by_old.get("Seas") or ""
        m = re.search(r"; ([^.;]*(?:building|easing|little changed)[^.]*)\.", old)
        if m:
            line = line[:-1] + "; " + m.group(1) + "."
        items.append(("Seas", line))
    # Swell — distinct from combined seas
    if _ok(R.get("swell")) and (R["swell"].get("values") or {}).get("heightFt") is not None:
        v = R["swell"]["values"]
        st = (R.get("swell") or {}).get("station") or (R.get("seas") or {}).get("station") or {}
        sid = st.get("id") or ((specs.get("swell") or {}).get("sources") or [None])[0]
        loc = where(sid, stations.get(sid) or st, anchor, role=(specs.get("swell") or {}).get("role") or "", kind="swell") if sid else "the wave buoy"
        lead = card_lead(sid, stations.get(sid) or st, anchor, (specs.get("swell") or {}).get("role") or "", "swell") if sid else ""
        prefix = (lead + ": ") if lead else ""
        items.append((
            "Swell",
            "%sSwell %.1f ft at %.0f s from the %s at %s, observed (swell from the wave spectrum, not combined seas)." % (
                prefix, v["heightFt"], v.get("periodS") or 0, v.get("dirCompass") or "", loc),
        ))
    # Pressure
    if _ok(R.get("pressure")) and (R["pressure"].get("values") or {}).get("inHg") is not None:
        p = R["pressure"]
        v = p["values"]
        st = p.get("station") or {}
        sid = st.get("id")
        loc = where(sid, stations.get(sid) or st, anchor, role=(specs.get("pressure") or {}).get("role") or "", kind="pressure")
        trend = v.get("trend") or "3-hour trend not reported"
        line = "%.2f inHg, %s, observed at %s." % (v["inHg"], trend, loc)
        old = by_old.get("Pressure") or ""
        m = re.search(r", ([^.]*(?:up|down|steady) hPa over \d+ h at [^.]+)\.", old)
        if m:
            line = line[:-1] + "; " + m.group(1) + "."
        items.append(("Pressure", line))
    # Marine forecast — keep as forecast
    if "Marine forecast" in by_old:
        txt = by_old["Marine forecast"]
        if not txt.lower().startswith("nws") and "NWS" in txt:
            items.append(("Marine forecast", "NWS forecasts %s" % txt[0].lower() + txt[1:] if txt else txt))
        else:
            items.append(("Marine forecast", txt if "NWS" in txt else "NWS forecasts: " + txt))
    # Rain / point forecast
    if "Rain" in by_old:
        items.append(("Rain", nws_chance_of_rain(by_old["Rain"])))
    # Tides
    t = (payload or {}).get("tides") or {}
    rebuilt = _tides_text(t, cfg, stations, anchor)
    if rebuilt:
        items.append(("Tides", rebuilt))
    elif "Tides" in by_old:
        items.append(("Tides", by_old["Tides"]))
    # Water temp
    wt, wt_un = _water_temp_text(R, cfg, stations, anchor)
    unavail.extend(wt_un)
    if wt:
        items.append(("Water temp", wt))
    elif (specs.get("waterTemp") or {}).get("sources") == []:
        unavail.append(("Inshore water temp", brief_strings.not_measured("Inshore water temperature")))

    # Keep build_salt items the payload did not cover (tests and partial assemblies).
    have = {k for k, _ in items}
    for k, v in body.get("items") or []:
        if k in ("Advisories", "Alerts") or k in have:
            continue
        items.append((k, v))

    # Predictions-only tide: string 6
    tide_cfg = cfg.get("tide") or {}
    if tide_cfg.get("observed") is False:
        name = tide_cfg.get("name") or tide_cfg.get("station")
        unavail.append(("Observed water level", brief_strings.observed_water_level_not_measured(name)))

    # Other empty-source readings (e.g. Topsail air temp)
    for kind, spec in specs.items():
        if kind in ("waterTemp",) or spec.get("sources"):
            continue
        if not spec.get("note"):
            continue
        label = {"airTemp": "Air temperature"}.get(kind, kind)
        unavail.append((label, brief_strings.not_measured(label)))

    missing = _rewrite_missing(body.get("missing") or [], cfg)
    # Drop inshore water temp / tides-as-missing when they are "not measured" instead
    freshness = list(body.get("freshness") or [])
    # Fix observed water-level station when it differs from the prediction station
    t = (payload or {}).get("tides") or {}
    obs = (t.get("observed") or {}) if t else {}
    obs_sid = (obs.get("station") or {}).get("id")
    if obs_sid:
        for f in freshness:
            if f.get("label") == "Water level":
                f["station"] = obs_sid

    # Preserve take
    out = dict(body)
    out["items"] = items
    out["missing"] = missing
    out["unavailable"] = unavail
    out["freshness"] = freshness
    return out


def _rewrite_missing(missing: list, cfg: dict | None = None) -> list:
    out = []
    stale_h = {"wind": 2, "seas": 2, "swell": 2, "pressure": 2, "water temp": 2, "waterTemp": 2}
    for raw in missing:
        s = str(raw)
        m = _STALE_MISS.match(s)
        if m:
            label = m.group("label").strip().capitalize() if m.group("label") else "Reading"
            label = label[0].upper() + label[1:]
            hours = stale_h.get(m.group("label").strip().lower(), 2)
            out.append(brief_strings.not_used(label, m.group("time"), hours))
            continue
        m = _STALE_FC.match(s)
        if m:
            label = m.group("label").strip()
            pretty = "Marine forecast" if "marine" in label.lower() else (
                "Rain forecast" if "rain" in label.lower() else label)
            out.append(brief_strings.nws_forecast_unavailable(pretty[0].upper() + pretty[1:]))
            continue
        key = s.strip().lower()
        if key in ("tides", "tide predictions"):
            out.append(brief_strings.TIDE_PREDICTIONS_UNAVAILABLE)
        elif "forecast" in key or key in ("marine forecast", "rain forecast", "weather forecast"):
            label = "Marine forecast" if "marine" in key else (
                "Rain forecast" if "rain" in key else "Weather forecast")
            out.append(brief_strings.nws_forecast_unavailable(label))
        elif key in ("advisories", "alerts"):
            out.append(brief_strings.ALERTS_CHECK_FAILED)
        else:
            out.append(brief_strings.not_available(s.strip().capitalize() if s else "Reading"))
    return out


def polish_fresh_items(rid: str, items: list, missing: list, unavailable: list, payload: dict) -> tuple[list, list, list]:
    al = payload.get("alerts") or {}
    new_items = []
    for k, v in items:
        if k in ("Alerts", "Advisories"):
            new_items.append(("Alerts", preview_alerts.alert_item_text(al, rid)))
            continue
        if k.startswith("Neuse River") or k.endswith("stage") or "stage" in v.lower():
            v = v.replace("not available from USGS right now", brief_strings.not_available("Stage and flow").split(": ", 1)[1])
            if "USGS does not publish discharge at this gauge (stage only)." in v:
                v = v.replace(
                    " USGS does not publish discharge at this gauge (stage only).",
                    " " + brief_strings.stage_only(k),
                )
        if k == "Lake level":
            v = v.replace("n/a vs the", "not available versus the")
            # keep numeric; replace remaining n/a
            v = re.sub(r"\bn/a\b", brief_strings.PLACEHOLDER, v)
            # If we used a placeholder mid-sentence, tidy "Not available ft in 24 h"
            v = v.replace("; %s ft in 24 h." % brief_strings.PLACEHOLDER, "; 24-hour change is not available at issue time.")
        if k == "Rain":
            v = v.replace("NWS 24-hour forecast unavailable", "NWS forecast not available at issue time")
            v = re.sub(r"\bunavailable\b", "not available at issue time", v)
        new_items.append((k, v))
    new_missing = []
    for m in missing:
        low = str(m).lower()
        if "forecast" in low or low == "weather forecast":
            new_missing.append(brief_strings.nws_forecast_unavailable("Weather forecast"))
        elif low in ("lake level", "release plus runoff", "rain", "river gauges"):
            new_missing.append(brief_strings.not_available(m[0].upper() + m[1:] if m else "Reading"))
        else:
            new_missing.append(brief_strings.not_available(str(m).capitalize()))
    new_unavail = []
    for label, _why in unavailable:
        new_unavail.append((label, brief_strings.not_measured(label)))
    return new_items, new_missing, new_unavail


def _fresh_ok(reading: dict | None) -> bool:
    return bool(reading) and reading.get("value") is not None and not reading.get("stale")


def summary_salt(rid: str, body: dict, payload: dict, cfg: dict) -> str:
    R = (payload or {}).get("readings") or {}
    al = (payload or {}).get("alerts") or {}
    d = dict(body.get("items") or [])
    sents = []

    if _ok(R.get("wind")) and d.get("Wind"):
        sents.append(d["Wind"].rstrip("."))
    elif (R.get("wind") or {}).get("status") == "stale" and R["wind"].get("time"):
        sents.append(brief_strings.not_used("Wind", brief._t(R["wind"]["time"]), 2).rstrip("."))
    elif (cfg.get("readings") or {}).get("wind", {}).get("sources"):
        sents.append(brief_strings.not_available("Wind").rstrip("."))

    mid = []
    if d.get("Seas"):
        mid.append(d["Seas"].rstrip("."))
    elif (R.get("seas") or {}).get("status") == "stale" and R["seas"].get("time"):
        mid.append(brief_strings.not_used("Combined seas", brief._t(R["seas"]["time"]), 2).rstrip("."))
    elif (cfg.get("readings") or {}).get("seas", {}).get("sources"):
        mid.append(brief_strings.not_available("Combined seas").rstrip("."))
    if d.get("Swell"):
        mid.append(d["Swell"][0].lower() + d["Swell"][1:].rstrip("."))
    if d.get("Water temp"):
        # Keep one clause; collapse the two-sentence "Not measured." string.
        wt = d["Water temp"].replace("Not measured. ", "not measured — ").rstrip(".")
        mid.append(wt[0].lower() + wt[1:] if mid else wt)
    if mid:
        sents.append("; ".join(mid))

    tail = []
    if d.get("Tides"):
        td = d["Tides"].replace("Not measured here. ", "not measured here — ").rstrip(".")
        tail.append(td)
    if al.get("status") and al.get("status") != "ok":
        tail.append(brief_strings.ALERTS_CHECK_FAILED.rstrip("."))
    elif al.get("items"):
        ev = al["items"][0].get("event") or "An NWS alert"
        tail.append("A %s is in effect" % ev)
    else:
        zones = cfg.get("alertZones") or []
        tail.append(brief_strings.alerts_none(", ".join(zones) if zones else "this area").rstrip("."))
    if tail:
        sents.append(". ".join(tail))

    out = []
    for s in sents:
        s = " ".join(s.split())
        if not s:
            continue
        if not s.endswith("."):
            s += "."
        out.append(s[0].upper() + s[1:] if s else s)
    return " ".join(out[:3])



def summary_jordan(payload: dict, items: list, missing: list) -> str:
    d = dict(items)
    bits = []
    L = payload.get("lake") or {}
    e = L.get("elevation") or {}
    if _fresh_ok(e):
        vs = L.get("vsGuideFt")
        vs_txt = ""
        if vs is not None:
            vs_txt = ", %.2f ft %s the %.1f ft guide curve" % (
                abs(vs), "below" if vs < 0 else "above", L.get("guideCurveFt") or 216.0)
        bits.append("Jordan Lake is at %.2f ft NGVD29%s, observed at the dam (USGS %s)." % (
            e["value"], vs_txt, L.get("usgs") or "02098197"))
    elif e.get("stale") and e.get("time"):
        bits.append(brief_strings.not_used("Lake level", brief._t(e["time"]), 3))
    else:
        bits.append(brief_strings.not_available("Lake level"))
    rel = payload.get("release") or {}
    flow = rel.get("flowCfs") or {}
    if _fresh_ok(flow):
        stage = rel.get("stageFt") or {}
        stage_bit = (", %.2f ft stage" % stage["value"]) if _fresh_ok(stage) else ""
        bits.append(
            "Release plus local runoff is %s at Haw River near Moncure (USGS %s)%s, not the official gate outflow." % (
                ("%g cfs" % flow["value"]) if flow.get("value") is not None else "",
                rel.get("usgs") or "02098206",
                stage_bit,
            )
        )
    elif flow.get("stale") and flow.get("time"):
        bits.append(brief_strings.not_used("Release plus runoff", brief._t(flow["time"]), 3))
    else:
        bits.append(brief_strings.not_available("Release plus runoff"))
    al = payload.get("alerts") or {}
    bits.append(preview_alerts.alert_line(al, "jordan-lake"))
    return " ".join(b if b.endswith(".") else b + "." for b in bits[:3])


def summary_neuse(payload: dict, items: list, missing: list) -> str:
    river = payload.get("river") or []
    # Prefer Clayton as the main gauge; mention others if useful
    by_usgs = {b.get("usgs"): b for b in river}
    clay = by_usgs.get("02087500") or (river[1] if len(river) > 1 else (river[0] if river else {}))
    bits = []
    if clay:
        stage, flow = clay.get("stageFt") or {}, clay.get("flowCfs") or {}
        label = clay.get("label") or "Neuse River near Clayton"
        if _fresh_ok(stage) or _fresh_ok(flow):
            parts = []
            if _fresh_ok(stage):
                parts.append("%.2f ft stage" % stage["value"])
            if _fresh_ok(flow):
                parts.append("%g cfs" % flow["value"])
            band = ((clay.get("band") or {}).get("label") or "").lower()
            band_bit = (", %s for the date" % band) if band else ""
            reg = ", regulated" if clay.get("regulated") else ""
            bits.append("At %s, the river is at %s%s%s, observed (USGS %s)." % (
                label.replace("Neuse River near ", "").replace("Neuse River ", ""),
                " and ".join(parts), band_bit, reg, clay.get("usgs") or ""))
        elif (stage.get("stale") or flow.get("stale")):
            t = stage.get("time") or flow.get("time")
            bits.append(brief_strings.not_used("Clayton stage and flow", brief._t(t) if t else "the last report", 3))
        else:
            bits.append(brief_strings.not_available("Clayton stage and flow"))
        fc = (clay.get("nwps") or {}).get("forecast") if (clay.get("nwps") or {}).get("status") == "ok" else None
        if fc and fc.get("crestStage") is not None:
            when = (" at " + brief._t(fc["crestTime"])) if fc.get("crestTime") else ""
            bits.append("NWS forecasts a crest of %.1f ft%s (NWPS %s)." % (
                fc["crestStage"], when, (clay.get("nwps") or {}).get("lid") or "CLYN7"))
        else:
            # try any routine-forecast gauge
            found = False
            for b in river:
                nw = b.get("nwps") or {}
                f = nw.get("forecast") if nw.get("status") == "ok" else None
                if f and f.get("crestStage") is not None:
                    bits.append("NWS forecasts a crest of %.1f ft at %s (NWPS %s)." % (
                        f["crestStage"], b.get("label") or "", nw.get("lid") or ""))
                    found = True
                    break
            if not found:
                bits.append(brief_strings.nws_forecast_unavailable("River forecast"))
    else:
        bits.append(brief_strings.not_available("River gauges"))
    al = payload.get("alerts") or {}
    bits.append(preview_alerts.alert_line(al, "neuse-river"))
    return " ".join(b if b.endswith(".") else b + "." for b in bits[:3])



MONCURE_LABEL = "Haw River flow at Moncure (USGS 02098206)"
MONCURE_SUB = (
    "About 1.6 miles below Jordan Lake Dam. Includes dam release plus local runoff. "
    "Not the official dam discharge."
)
# Official USACE Wilmington District note, checked 15 Nov 2026 in dsslake.txt:
# "Guide Curve for Jordan is 216.0 ... each day of the year." The file's last daily
# row is 22 Oct 2026; the 216.0 figure is the standing year-round target, not a
# seasonal schedule. The district lake page (jord.htm) does not itself state 216.0.
JORDAN_GUIDE_SOURCE = "https://epec.saw.usace.army.mil/dsslake.txt"
JORDAN_LAKE_PAGE = "https://epec.saw.usace.army.mil/jord.htm"
JORDAN_GUIDE_NOTE = (
    "The reading is the lake's pool elevation in feet NGVD29, observed at USGS 02098197 at the dam. "
    "The 216.0 ft guide curve is the USACE Wilmington District's conservation-pool target; "
    "it is the same each day of the year, not a seasonal schedule "
    "(%s, official note checked 15 Nov 2026)." % JORDAN_GUIDE_SOURCE
)



def nws_chance_of_rain(txt: str) -> str:
    """Preview-only: 'NWS forecasts a 0% chance through tonight' -> '...chance of rain...'."""
    if not txt:
        return txt
    if re.search(r"% chance(?! of rain)", txt, re.I):
        txt = re.sub(r"% chance(?! of rain)", "% chance of rain", txt, count=1, flags=re.I)
    if not txt.lower().startswith("nws"):
        if "% chance" in txt:
            txt = "NWS forecasts a " + txt[0].lower() + txt[1:]
        else:
            txt = "NWS forecasts: " + txt
    return txt


def take_place(sid: str, meta: dict | None, anchor: dict | None, role: str = "", kind: str = "") -> tuple[str, str]:
    """Natural Take location: ('offshore buoy 41064, 32 mi SSE', '') or
    ('Duck Pier (8651370), 21 mi NNW', 'a representative observation').
    Card labels stay on card_lead and are not changed here.
    """
    meta = meta or {}
    if not sid:
        return "", ""
    info = conditions.station_info(sid, meta, anchor)
    word = place_word(meta, role, kind)
    d = info.get("distanceMi")
    b = info.get("bearingFromAnchor")
    name = info.get("name") or sid
    loc = None
    if d is not None and float(d) >= 0.5 and b:
        dtxt = str(int(d)) if float(d) == int(d) else str(d)
        loc = "%s mi %s" % (dtxt, b)
    if word == "offshore" and loc:
        return "offshore buoy %s, %s" % (sid, loc), ""
    if word == "nearshore" and loc:
        return "nearshore buoy %s, %s" % (sid, loc), ""
    if loc and float(d) >= 8:
        return "%s (%s), %s" % (name, sid, loc), "a representative observation"
    return "%s (%s)" % (name, sid), ""


def _at_place(place: str, qual: str = "") -> str:
    if not place:
        return (", " + qual) if qual else ""
    bit = " at " + place
    if qual:
        bit += ", " + qual
    return bit


def _take_wind(kt, compass: str, gust=None) -> str:
    if kt is None:
        return ""
    k = int(round(kt))
    dirc = (compass or "").strip()
    if k < 10:
        w = "Light %s wind" % dirc if dirc else "Light wind"
    else:
        w = "%s wind %d kt" % (dirc, k) if dirc else "%d kt wind" % k
    if gust is not None and kt is not None and gust - kt >= 3:
        w += ", gusting %d kt" % round(gust)
    return w


def _next_tide(events: list, now: datetime | None):
    now = now or datetime.now(timezone.utc)
    now_et = now.astimezone(ET) if now.tzinfo else now.replace(tzinfo=timezone.utc).astimezone(ET)
    best = None
    for e in events or []:
        try:
            d = datetime.fromtimestamp(e["t"] / 1000, timezone.utc).astimezone(ET)
        except (KeyError, TypeError, ValueError, OSError):
            continue
        if d <= now_et:
            continue
        if best is None or d < best[1]:
            best = (e, d)
    return best


def _join_take_parts(parts: list) -> str:
    bits = []
    for i, p in enumerate(parts):
        tx = (p.get("text") or "").strip()
        if not tx:
            continue
        if i == 0:
            bits.append(tx[0].upper() + tx[1:] if tx and not tx[0].isupper() else tx)
            continue
        prev = bits[-1]
        if prev.endswith(".") or tx.startswith("Alerts:") or tx.startswith("A "):
            if not prev.endswith("."):
                bits[-1] = prev + "."
            bits.append(" " + (tx[0].upper() + tx[1:] if tx and tx[0].islower() else tx))
        else:
            # keep locked-string labels capitalized after a semicolon
            bits.append("; " + tx)
    text = "".join(bits).strip()
    if text and not text.endswith("."):
        text += "."
    return text


def _sentence(parts: list) -> dict | None:
    parts = [p for p in parts if (p.get("text") or "").strip()]
    if not parts:
        return None
    kinds = []
    srcs = []
    for p in parts:
        k = p.get("kind") or "observed"
        if k not in kinds:
            kinds.append(k)
        for s in p.get("sources") or []:
            if s and s not in srcs:
                srcs.append(s)
    return {
        "text": _join_take_parts(parts),
        "kind": " ".join(kinds),
        "kinds": kinds,
        "sources": srcs,
        "parts": parts,
    }


def card_lead(sid: str, meta: dict | None, anchor: dict | None, role: str = "", kind: str = "") -> str:
    """Short, prominent station lead for a card, e.g. 'Offshore buoy 44086, 11 mi ENE'."""
    meta = meta or {}
    info = conditions.station_info(sid, meta, anchor)
    word = place_word(meta, role, kind)
    d = info.get("distanceMi")
    b = info.get("bearingFromAnchor")
    name = info.get("name") or sid
    dtxt = None
    if d is not None and float(d) >= 0.5 and b:
        dtxt = str(int(d)) if float(d) == int(d) else str(d)
        loc = "%s mi %s" % (dtxt, b)
    else:
        loc = None
    if word == "offshore" and loc:
        return "Offshore buoy %s, %s" % (sid, loc)
    if word == "nearshore" and loc:
        return "Nearshore buoy %s, %s" % (sid, loc)
    if loc and float(d) >= 8:
        return "Representative observation, %s (%s), %s of %s" % (
            name, sid, loc, (anchor or {}).get("label") or "the region anchor")
    return ""


def _wind_plain(kt, compass: str) -> str:
    if kt is None:
        return ""
    k = int(round(kt))
    dirc = (compass or "").strip()
    if k < 10:
        return "Light %s wind" % dirc if dirc else "Light wind"
    return "%d kt %s wind" % (k, dirc) if dirc else "%d kt wind" % k


def captains_take(rid: str, body: dict, payload: dict, cfg: dict, issued_et: str = "", now=None) -> dict:
    """Deterministic Captain's Take model from fresh, verified readings only."""
    payload = payload or {}
    cfg = cfg or {}
    sentences = []
    if rid == "jordan-lake":
        sentences = _take_jordan(payload)
    elif rid == "neuse-river":
        sentences = _take_neuse(payload)
    else:
        sentences = _take_salt(rid, body, payload, cfg, now=now)
    return {
        "heading": "Captain's Take",
        "issuedEt": issued_et or (body.get("issuedEt") or ""),
        "sentences": sentences,
    }


def take_text(model: dict) -> str:
    bits = []
    for s in (model or {}).get("sentences") or []:
        tx = (s.get("text") or "").strip()
        if not tx:
            continue
        bits.append(tx if tx.endswith(".") else tx + ".")
    return " ".join(bits)


def _take_salt(rid: str, body: dict, payload: dict, cfg: dict, now=None) -> list:
    """At most three sentences: wind/seas, water temp + next tide, NWS forecast + alerts."""
    R = payload.get("readings") or {}
    al = payload.get("alerts") or {}
    stations = (conditions.load_regions() or {}).get("stations") or {}
    anchor = (payload.get("region") or {}).get("anchor") or cfg.get("anchor") or {}
    specs = cfg.get("readings") or {}
    now = now or datetime.now(timezone.utc)
    out = []

    def place_for(kind, sid_fallback=None):
        r = R.get(kind) or {}
        st = r.get("station") or {}
        sid = st.get("id") or sid_fallback
        if not sid:
            return "", ""
        return take_place(sid, stations.get(sid) or st, anchor, (specs.get(kind) or {}).get("role") or "", kind)

    # 1. Wind and seas/swell
    parts = []
    if _ok(R.get("wind")) and (R["wind"].get("values") or {}).get("speedKt") is not None:
        v = R["wind"]["values"]
        wtxt = _take_wind(v["speedKt"], v.get("dirCompass"), v.get("gustKt"))
        wplace, wqual = place_for("wind")
        if not wplace:
            sid = ((R["wind"].get("station") or {}).get("id"))
            wplace, wqual = take_place(sid, stations.get(sid) or R["wind"].get("station"), anchor,
                                       (specs.get("wind") or {}).get("role") or "", "wind") if sid else ("", "")
        text = wtxt + _at_place(wplace, wqual)
        sid = ((R["wind"].get("station") or {}).get("id"))
        parts.append({"text": text, "kind": "observed", "sources": [sid] if sid else []})
    elif (R.get("wind") or {}).get("status") == "stale" and R["wind"].get("time"):
        parts.append({"text": brief_strings.not_used("Wind", brief._t(R["wind"]["time"]), 2),
                      "kind": "missing",
                      "sources": [((R["wind"].get("station") or {}).get("id") or "")]})
    elif (specs.get("wind") or {}).get("sources"):
        parts.append({"text": brief_strings.not_available("Wind"),
                      "kind": "missing", "sources": (specs["wind"].get("sources") or [])[:1]})

    if _ok(R.get("seas")) and (R["seas"].get("values") or {}).get("heightFt") is not None:
        sv = R["seas"]["values"]
        splace, squal = place_for("seas")
        seas_txt = "%.1f ft combined seas" % sv["heightFt"] + _at_place(splace, squal)
        # If wind and seas share the exact same place phrase, fold into the wind part.
        if parts and parts[0].get("kind") == "observed" and splace and _at_place(splace, squal) and parts[0]["text"].endswith(_at_place(splace, squal)):
            parts[0]["text"] = parts[0]["text"][: -len(_at_place(splace, squal))] + " and " + seas_txt
            sid = ((R["seas"].get("station") or {}).get("id"))
            if sid and sid not in (parts[0].get("sources") or []):
                parts[0]["sources"] = list(parts[0].get("sources") or []) + [sid]
        else:
            sid = ((R["seas"].get("station") or {}).get("id"))
            parts.append({"text": seas_txt, "kind": "observed", "sources": [sid] if sid else []})
        if _ok(R.get("swell")) and (R["swell"].get("values") or {}).get("heightFt") is not None:
            parts.append({
                "text": "swell is %.1f ft" % R["swell"]["values"]["heightFt"],
                "kind": "observed",
                "sources": [((R.get("swell") or {}).get("station") or {}).get("id") or ((R.get("seas") or {}).get("station") or {}).get("id") or ""],
            })
    elif (R.get("seas") or {}).get("status") == "stale" and R["seas"].get("time"):
        parts.append({"text": brief_strings.not_used("Combined seas", brief._t(R["seas"]["time"]), 2),
                      "kind": "missing",
                      "sources": [((R["seas"].get("station") or {}).get("id") or "")]})
    elif (specs.get("seas") or {}).get("sources") and not _ok(R.get("seas")):
        parts.append({"text": brief_strings.not_available("Combined seas"),
                      "kind": "missing", "sources": (specs["seas"].get("sources") or [])[:1]})
    sent = _sentence(parts)
    if sent:
        out.append(sent)

    # 2. Water temp + next predicted high/low; observed WL only when local
    parts = []
    inshore = R.get("waterTemp") or {}
    offshore = R.get("waterTempOffshore") or {}
    in_spec = specs.get("waterTemp") or {}
    off_spec = specs.get("waterTempOffshore") or {}
    if _ok(inshore) and (inshore.get("values") or {}).get("f") is not None:
        st = inshore.get("station") or {}
        sid = st.get("id")
        place, qual = take_place(sid, stations.get(sid) or st, anchor, in_spec.get("role") or "inshore", "waterTemp")
        parts.append({"text": "%.0f°F inshore%s" % (inshore["values"]["f"], _at_place(place, qual)),
                      "kind": "observed", "sources": [sid] if sid else []})
    elif not in_spec.get("sources"):
        parts.append({"text": brief_strings.not_measured("Inshore water temperature"),
                      "kind": "missing", "sources": []})
    elif inshore.get("status") == "stale" and inshore.get("time"):
        parts.append({"text": brief_strings.not_used(
            "Inshore water temperature", brief._t(inshore["time"]),
            max(1, int(round((inshore.get("staleAfterMin") or 90) / 60))) or 2),
                      "kind": "missing",
                      "sources": [((inshore.get("station") or {}).get("id") or "")]})
    if _ok(offshore) and (offshore.get("values") or {}).get("f") is not None:
        st = offshore.get("station") or {}
        sid = st.get("id")
        place, qual = take_place(sid, stations.get(sid) or st, anchor, off_spec.get("role") or "", "waterTempOffshore")
        parts.append({"text": "%.0f°F observed%s" % (offshore["values"]["f"], _at_place(place, qual)),
                      "kind": "observed", "sources": [sid] if sid else []})

    tides = payload.get("tides") or {}
    tide_cfg = cfg.get("tide") or {}
    pred_st = tides.get("station") or {}
    pred_sid = pred_st.get("id") or tide_cfg.get("station")
    nxt = _next_tide(tides.get("events") or [], now) if tides.get("status") == "ok" else None
    if nxt:
        e, d = nxt
        kind_word = "high" if e.get("type") == "H" else "low"
        name = (pred_st.get("name") or (stations.get(pred_sid) or {}).get("name") or pred_sid or "the tide station")
        at = "%s (%s)" % (name, pred_sid) if pred_sid else name
        parts.append({"text": "next %s is %s (%.1f ft) at %s" % (kind_word, brief._t(d), e.get("v") or 0, at),
                      "kind": "predicted", "sources": [pred_sid] if pred_sid else []})
        # Observed water level only when it is a local reading at the prediction station.
        ob = tides.get("observed") or {}
        # When observed and predictions share a station, assemble omits observed.station.
        want_obs = tide_cfg.get("observed", True) is not False
        obs_sid = (
            ((ob.get("station") or {}).get("id"))
            or tide_cfg.get("observedStation")
            or (pred_sid if want_obs and ob else None)
        )
        local = bool(want_obs and obs_sid and pred_sid and obs_sid == pred_sid)
        if local and ob.get("status") == "ok" and ob.get("latest") and ob["latest"].get("v") is not None:
            parts.append({"text": "observed water level is %.2f ft MLLW" % ob["latest"]["v"],
                          "kind": "observed", "sources": [obs_sid]})
    sent = _sentence(parts)
    if sent:
        out.append(sent)

    # 3. NWS forecast and alerts
    parts = []
    rain = dict(body.get("items") or []).get("Rain")
    marine = dict(body.get("items") or []).get("Marine forecast")
    fc_bits = []
    fc_srcs = []
    if rain and ("NWS" in rain or "% chance" in rain):
        fc_bits.append(nws_chance_of_rain(rain))
        fc_srcs.append("NWS")
    elif any("Rain forecast" in m or "rain forecast" in m.lower() for m in (body.get("missing") or [])):
        parts.append({"text": brief_strings.nws_forecast_unavailable("Rain forecast"),
                      "kind": "missing", "sources": ["NWS"]})
    if marine and "NWS" in marine:
        mt = marine.strip()
        mt = re.sub(r"^NWS forecasts\s+", "", mt)
        mt = re.sub(r"\.\s*\(NWS\s+([A-Z0-9]+)\)\.?\s*$", r" (\1)", mt)
        mt = re.sub(r"\s*\(NWS\s+([A-Z0-9]+)\)\.?\s*$", r" (\1)", mt)
        mt = mt.rstrip(".")
        fc_bits.append(mt)
        fc_srcs.append((payload.get("marine") or {}).get("zone") or "NWS")
    if fc_bits:
        parts.append({"text": "; ".join(b.rstrip(".") for b in fc_bits), "kind": "forecast", "sources": fc_srcs})
    if al.get("status") and al.get("status") != "ok":
        parts.append({"text": brief_strings.ALERTS_CHECK_FAILED,
                      "kind": "missing", "sources": ["NWS"]})
    elif al.get("items"):
        ev = al["items"][0].get("event") or "An NWS alert"
        parts.append({"text": "A %s is in effect" % ev, "kind": "alert",
                      "sources": [z for z in (cfg.get("alertZones") or [])][:3]})
    else:
        zones = cfg.get("alertZones") or []
        parts.append({"text": brief_strings.alerts_none(", ".join(zones) if zones else "this area"),
                      "kind": "alert", "sources": list(zones)})
    sent = _sentence(parts)
    if sent:
        out.append(sent)
    return out[:3]


def _take_jordan(payload: dict) -> list:
    out = []
    L = payload.get("lake") or {}
    e = L.get("elevation") or {}
    if _fresh_ok(e):
        vs = L.get("vsGuideFt")
        vs_txt = ""
        if vs is not None:
            vs_txt = ", %.2f ft %s the 216.0 ft guide curve" % (abs(vs), "below" if vs < 0 else "above")
        out.append({
            "text": "Jordan Lake is at %.2f ft NGVD29%s, observed at the dam (USGS 02098197)." % (
                e["value"], vs_txt),
            "kind": "observed", "sources": [L.get("usgs") or "02098197"],
        })
    elif e.get("stale") and e.get("time"):
        out.append({"text": brief_strings.not_used("Lake level", brief._t(e["time"]), 3),
                    "kind": "missing", "sources": [L.get("usgs") or "02098197"]})
    else:
        out.append({"text": brief_strings.not_available("Lake level"), "kind": "missing", "sources": ["02098197"]})
    rel = payload.get("release") or {}
    flow = rel.get("flowCfs") or {}
    if _fresh_ok(flow):
        out.append({
            "text": "Haw River flow at Moncure is %s, observed at USGS 02098206, about 1.6 miles below the dam; it includes dam release plus local runoff and is not the official dam discharge." % (
                ("%g cfs" % flow["value"]) if flow.get("value") is not None else "reported"),
            "kind": "observed", "sources": [rel.get("usgs") or "02098206"],
        })
    elif flow.get("stale") and flow.get("time"):
        out.append({"text": brief_strings.not_used("Haw River flow at Moncure", brief._t(flow["time"]), 3),
                    "kind": "missing", "sources": ["02098206"]})
    else:
        out.append({"text": brief_strings.not_available("Haw River flow at Moncure"),
                    "kind": "missing", "sources": ["02098206"]})
    al = payload.get("alerts") or {}
    out.append({"text": preview_alerts.alert_line(al, "jordan-lake"),
                "kind": "alert" if al.get("status") == "ok" else "missing",
                "sources": preview_alerts.zone_ids(rid="jordan-lake")})
    return out


def _take_neuse(payload: dict) -> list:
    out = []
    river = payload.get("river") or []
    by_usgs = {b.get("usgs"): b for b in river}
    clay = by_usgs.get("02087500") or (river[1] if len(river) > 1 else (river[0] if river else {}))
    if clay:
        stage, flow = clay.get("stageFt") or {}, clay.get("flowCfs") or {}
        srcs = [clay.get("usgs") or "02087500"]
        if _fresh_ok(stage) or _fresh_ok(flow):
            parts = []
            if _fresh_ok(stage):
                parts.append("%.2f ft stage" % stage["value"])
            if _fresh_ok(flow):
                parts.append("%g cfs" % flow["value"])
            band = ((clay.get("band") or {}).get("label") or "").lower()
            band_bit = (", %s for the date" % band) if band else ""
            out.append({
                "text": "At Clayton, the river is at %s%s, observed (USGS 02087500)." % (
                    " and ".join(parts), band_bit),
                "kind": "observed", "sources": srcs,
            })
        elif stage.get("stale") or flow.get("stale"):
            t = stage.get("time") or flow.get("time")
            out.append({"text": brief_strings.not_used("Clayton stage and flow", brief._t(t) if t else "the last report", 3),
                        "kind": "missing", "sources": srcs})
        else:
            out.append({"text": brief_strings.not_available("Clayton stage and flow"),
                        "kind": "missing", "sources": srcs})
        fc = (clay.get("nwps") or {}).get("forecast") if (clay.get("nwps") or {}).get("status") == "ok" else None
        if not (fc and fc.get("crestStage") is not None):
            for b in river:
                nw = b.get("nwps") or {}
                f = nw.get("forecast") if nw.get("status") == "ok" else None
                if f and f.get("crestStage") is not None:
                    fc, clay_fc_lid, clay_fc_label = f, nw.get("lid"), b.get("label")
                    break
            else:
                fc = None
                clay_fc_lid = clay_fc_label = None
        else:
            clay_fc_lid = (clay.get("nwps") or {}).get("lid") or "CLYN7"
            clay_fc_label = None
        if fc and fc.get("crestStage") is not None:
            when = (" at " + brief._t(fc["crestTime"])) if fc.get("crestTime") else ""
            place = clay_fc_label or "Clayton"
            out.append({
                "text": "NWS forecasts a crest of %.1f ft%s (NWPS %s)." % (
                    fc["crestStage"], when, clay_fc_lid or "CLYN7"),
                "kind": "forecast", "sources": [clay_fc_lid or "CLYN7"],
            })
        else:
            out.append({"text": brief_strings.nws_forecast_unavailable("River forecast"),
                        "kind": "missing", "sources": ["NWPS"]})
    else:
        out.append({"text": brief_strings.not_available("River gauges"), "kind": "missing", "sources": []})
    al = payload.get("alerts") or {}
    out.append({"text": preview_alerts.alert_line(al, "neuse-river"),
                "kind": "alert" if al.get("status") == "ok" else "missing",
                "sources": preview_alerts.zone_ids(rid="neuse-river")})
    return out


def reading_sources(rid: str, payload: dict, body: dict, cfg: dict, now=None) -> list:
    """Structured source rows for every reading, for Design's expandable panel."""
    from datetime import datetime, timezone
    now = now or datetime.now(timezone.utc)
    rows = []
    payload = payload or {}
    stations = (conditions.load_regions() or {}).get("stations") or {}

    def age_min(iso):
        if not iso:
            return None
        try:
            t = iso if hasattr(iso, "timestamp") else datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
            if not getattr(t, "tzinfo", None):
                t = t.replace(tzinfo=timezone.utc)
            return int(round((now - t).total_seconds() / 60))
        except (TypeError, ValueError, OSError):
            return None

    def add(label, station, name, agency, endpoint, kind, time_iso, extra=None):
        t_et = None
        if time_iso:
            try:
                t_et = brief._t(time_iso)
            except Exception:
                t_et = None
        rec = {
            "label": label,
            "station": station,
            "stationName": name,
            "agency": agency,
            "endpoint": endpoint,
            "kind": kind,  # observed | forecast | predicted
            "timeEt": t_et,
            "ageMin": age_min(time_iso),
        }
        if extra:
            rec.update(extra)
        rows.append(rec)

    R = payload.get("readings") or {}
    for kind, r in R.items():
        st = (r or {}).get("station") or {}
        sid = st.get("id")
        meta = stations.get(sid) or st
        add(kind, sid, meta.get("name") or st.get("name"), meta.get("agency"),
            r.get("sourceUrl") or r.get("url") or meta.get("url"),
            "observed", r.get("time"),
            {"status": r.get("status"), "stale": r.get("stale")})
    t = payload.get("tides") or {}
    if t:
        st = t.get("station") or {}
        add("tide predictions", st.get("id"), st.get("name"), "NOAA CO-OPS",
            t.get("sourceUrl") or "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter",
            "predicted", None)
        ob = t.get("observed") or {}
        if ob:
            ost = ob.get("station") or st
            latest = ob.get("latest") or {}
            tiso = None
            if latest.get("t"):
                try:
                    tiso = datetime.fromtimestamp(latest["t"] / 1000, timezone.utc).isoformat()
                except (TypeError, ValueError, OSError, OverflowError):
                    tiso = None
            add("observed water level", ost.get("id"), ost.get("name"), "NOAA CO-OPS",
                ob.get("sourceUrl") or "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter",
                "observed", tiso, {"status": ob.get("status")})
    for key, kind in (("forecast", "forecast"), ("marine", "forecast")):
        block = payload.get(key) or {}
        if block:
            add(key, (block.get("zone") if key == "marine" else (block.get("grid") or {}).get("office") or "NWS"),
                block.get("zoneName") or block.get("label") or key,
                "National Weather Service",
                block.get("sourceUrl") or "https://api.weather.gov",
                "forecast", block.get("updated"), {"status": block.get("status")})
    # freshwater
    lake = payload.get("lake") or {}
    if lake.get("elevation"):
        add("lake elevation", lake.get("usgs"), "Jordan Lake at dam" if rid == "jordan-lake" else "Lake elevation",
            "USGS", "https://waterservices.usgs.gov/nwis/iv/?sites=%s" % (lake.get("usgs") or ""),
            "observed", lake["elevation"].get("time"), {"datum": lake.get("datum") or "NGVD29"})
    rel = payload.get("release") or {}
    if rel.get("flowCfs") or rel.get("stageFt"):
        add("Haw River flow at Moncure" if rid == "jordan-lake" else "release",
            rel.get("usgs"), rel.get("label"), "USGS",
            "https://waterservices.usgs.gov/nwis/iv/?sites=%s" % (rel.get("usgs") or ""),
            "observed", (rel.get("flowCfs") or rel.get("stageFt") or {}).get("time"))
    for block in payload.get("river") or []:
        add(block.get("label") or "gauge", block.get("usgs"), block.get("label"), "USGS",
            "https://waterservices.usgs.gov/nwis/iv/?sites=%s" % (block.get("usgs") or ""),
            "observed", ((block.get("stageFt") or block.get("flowCfs") or {}).get("time")))
        nw = block.get("nwps") or {}
        fc = nw.get("forecast") if nw.get("status") == "ok" else None
        if fc:
            add("NWPS forecast (%s)" % (nw.get("lid") or ""), nw.get("lid"), block.get("label"),
                "NWS / National Water Prediction Service",
                "https://api.water.noaa.gov/nwps/v1/gauges/%s" % (nw.get("lid") or ""),
                "forecast", fc.get("issued"))
    rn = payload.get("rain") or {}
    if rn:
        add("rain", rn.get("usgs"), "Rain at the dam", "USGS",
            "https://waterservices.usgs.gov/nwis/iv/?sites=%s" % (rn.get("usgs") or ""),
            "observed", rn.get("time"), {"status": rn.get("status")})
    al = payload.get("alerts") or {}
    if al:
        add("alerts", ",".join(preview_alerts.zone_ids(rid=rid) or (cfg.get("alertZones") or [])),
            al.get("areasChecked") or "NWS alerts", "National Weather Service",
            al.get("sourceUrl") or "https://api.weather.gov/alerts/active",
            "observed", None, {"status": al.get("status")})
    return rows


def has_stage(items: list) -> bool:
    for k, v in items or []:
        if k == "Lake level":
            continue
        if re.search(r"\bstage\b", (k or "") + " " + (v or ""), re.I):
            return True
    return False


def inject_page(html: str, b: dict) -> str:
    """Insert Captain's Take, stage note, sources block, and professional missing sections.

    No typography restyle: existing brief.css rules for .mb-take are left to Design.
    """
    import json
    esc = __import__("html").escape
    # Strip earlier preview typography overrides if a previous build added them — keep
    # only a minimal hook so mb-sources is identifiable, no palette or type changes.
    model = b.get("captainsTake") or captains_take(
        b.get("regionId") or (b.get("region") or {}).get("id") or "",
        b, b.get("payload") or {}, {}, b.get("issuedEt") or "")
    take_html = _render_captains_take(model)
    sources = b.get("readingSources") or []
    sources_html = _render_sources(sources, model)
    # Place the single Take at the top, after the region nav and before the issue
    # card, so it is visible in a 390px viewport. Remove the bottom take.
    html = re.sub(r'<section class="mb-take">.*?</section>', "", html, count=1, flags=re.S)
    if take_html:
        def _place_take(m):
            return m.group(0) + "\n  " + take_html
        if re.search(r'<nav class="mb-regions"', html):
            html, n = re.subn(
                r'<nav class="mb-regions"[^>]*>.*?</nav>',
                _place_take,
                html,
                count=1,
                flags=re.S,
            )
        else:
            n = 0
        if n == 0 and re.search(r'<section class="mb-issue"', html):
            html = re.sub(
                r'<section class="mb-issue"',
                lambda m: take_html + "\n  " + m.group(0),
                html,
                count=1,
            )
        elif n == 0:
            html = re.sub(r"(<h1>[^<]*</h1>)", lambda m: m.group(0) + "\n  " + take_html, html, count=1)
    if b.get("stageNote"):
        note = '<p class="mb-stage-note">%s</p>' % esc(brief_strings.STAGE_NOTE)
        def _insert_stage(m):
            return m.group(0) + "\n    " + note
        html, n = re.subn(
            r'<div class="mb-row[^"]*"><dt>(?!Lake level)[^<]*</dt><dd>[^<]*\bstage\b[^<]*</dd></div>',
            _insert_stage,
            html,
            count=1,
            flags=re.I,
        )
        if n == 0:
            html = re.sub(
                r'(<dd>[^<]*\bstage\b[^<]*</dd>)',
                r"\1\n    " + note,
                html,
                count=1,
                flags=re.I,
            )
    html = re.sub(r'<p class="mb-miss">Not available at issue time: [^<]*</p>', "", html, count=1)
    html = re.sub(r'<section class="mb-miss mb-unavail"[^>]*>.*?</section>', "", html, count=1, flags=re.S)
    extras = _missing_sections_html(b) + sources_html
    if extras:
        html = html.replace(
            '  <script>\n  (function(){\n    var d=document.getElementById("mb-details");',
            extras + '\n  <script>\n  (function(){\n    var d=document.getElementById("mb-details");',
            1,
        )
        # If that marker is gone, append before footer
        if 'class="mb-sources"' not in html and sources_html:
            html = html.replace('<footer class="mb-foot">', sources_html + '\n  <footer class="mb-foot">', 1)
    return html


def _render_captains_take(model: dict) -> str:
    esc = __import__("html").escape
    if not model or not model.get("sentences"):
        return ""
    ps = []
    for s in model["sentences"]:
        tx = (s.get("text") or "").strip()
        if not tx:
            continue
        kinds = s.get("kinds") or [k for k in str(s.get("kind") or "observed").split() if k]
        kind = esc(" ".join(kinds))
        srcs = " ".join(esc(str(x)) for x in (s.get("sources") or []) if x)
        attr = ' data-kind="%s"' % kind
        if srcs:
            attr += ' data-sources="%s"' % srcs
        parts = [p for p in (s.get("parts") or []) if (p.get("text") or "").strip()]
        mixed = len(set(p.get("kind") for p in parts)) > 1
        if mixed:
            inner = []
            # Rebuild with the same separators as _join_take_parts, as tagged spans.
            acc = ""
            for i, p in enumerate(parts):
                piece = (p.get("text") or "").strip()
                if not piece:
                    continue
                if i == 0:
                    chunk = piece[0].upper() + piece[1:] if piece and not piece[0].isupper() else piece
                    prefix = ""
                elif acc.endswith(".") or piece.startswith("Alerts:") or piece.startswith("A "):
                    if not acc.endswith("."):
                        inner[-1] = inner[-1] + "."
                        acc = acc + "."
                    chunk = piece[0].upper() + piece[1:] if piece and piece[0].islower() else piece
                    prefix = " "
                else:
                    chunk = piece
                    prefix = "; "
                pattr = ' data-kind="%s"' % esc(p.get("kind") or "observed")
                psr = " ".join(esc(str(x)) for x in (p.get("sources") or []) if x)
                if psr:
                    pattr += ' data-sources="%s"' % psr
                inner.append("%s<span%s>%s</span>" % (prefix, pattr, esc(chunk)))
                acc = (acc + prefix + chunk).rstrip()
            body = "".join(inner)
            if acc and not acc.endswith("."):
                body += "."
            ps.append("<p%s>%s</p>" % (attr, body))
        else:
            ps.append("<p%s>%s</p>" % (attr, esc(tx if tx.endswith(".") else tx + ".")))
    issued = esc(model.get("issuedEt") or "")
    issued_p = ('<p class="mb-take-note">Issued %s. Generated by fixed rules from verified readings. Not an observation and not a fishing report.</p>' % issued) if issued else (
        '<p class="mb-take-note">Generated by fixed rules from verified readings. Not an observation and not a fishing report.</p>')
    # Reuse existing take typography (mb-take-k, mb-take-body, mb-take-note). Add mb-summary as requested.
    return (
        "<section class=\"mb-summary mb-take\" aria-label=\"Captain's Take\">"
        "<p class=\"mb-take-k\"><span>Captain's Take</span> <span class=\"mb-interp\">Interpretation</span></p>"
        '<div class="mb-take-body">%s</div>%s'
        '<script type="application/json" id="cb-captains-take">%s</script>'
        '</section>'
    ) % ("".join(ps), issued_p, __import__("json").dumps(model, ensure_ascii=False).replace("</", "<\\/"))


def _render_sources(rows: list, model: dict | None = None) -> str:
    esc = __import__("html").escape
    import json
    if not rows:
        payload = json.dumps({"readings": [], "captainsTake": model or {}}, ensure_ascii=False)
        return '<script type="application/json" id="cb-reading-sources">%s</script>' % esc(payload)
    lis = []
    for r in rows:
        kind = r.get("kind") or ""
        time = r.get("timeEt") or ""
        age = r.get("ageMin")
        age_s = (", %d min old" % age) if age is not None else ""
        bits = [r.get("label") or "Reading"]
        if r.get("stationName") or r.get("station"):
            bits.append("%s (%s)" % (r.get("stationName") or "", r.get("station") or ""))
        if r.get("agency"):
            bits.append(r["agency"])
        if kind:
            bits.append(kind)
        if time:
            bits.append("%s%s" % (time, age_s))
        if r.get("endpoint"):
            bits.append(r["endpoint"])
        lis.append("<li>%s</li>" % esc(" · ".join(str(x) for x in bits if x)))
    payload = json.dumps({"readings": rows, "captainsTake": model or {}}, ensure_ascii=False, default=str)
    return (
        '<details class="mb-sources"><summary>Sources and times</summary><ul>%s</ul></details>'
        '<script type="application/json" id="cb-reading-sources">%s</script>'
    ) % ("".join(lis), payload.replace("</", "<\\/"))


def _missing_sections_html(b: dict) -> str:
    esc = __import__("html").escape
    measured, available = [], []
    for label, why in b.get("unavailable") or []:
        text = why if why.startswith(label) or why.startswith("Observed") or why.startswith("Inshore") else "%s: %s" % (label, why)
        if "Not measured" in why or "Not published" in why or "Not measured here" in why:
            measured.append(text)
        else:
            available.append(text)
    for raw in b.get("missing") or []:
        available.append(raw)
    parts = []
    if measured:
        lis = "".join("<li>%s</li>" % esc(t) for t in measured)
        parts.append(
            '<section class="mb-miss-sec mb-unavail" aria-label="%s"><h2>%s</h2><ul>%s</ul></section>'
            % (esc(brief_strings.HEADING_NOT_MEASURED), esc(brief_strings.HEADING_NOT_MEASURED), lis)
        )
    if available:
        lis = "".join("<li>%s</li>" % esc(t) for t in available)
        parts.append(
            '<section class="mb-miss-sec mb-miss" aria-label="%s"><h2>%s</h2><ul>%s</ul></section>'
            % (esc(brief_strings.HEADING_NOT_AVAILABLE), esc(brief_strings.HEADING_NOT_AVAILABLE), lis)
        )
    return "".join(parts)


def informal_hits(text: str) -> list[str]:
    """Return informal fragments still present in preview HTML or item text."""
    hits = []
    # Don't flag the professional "Not available" / "Could not be checked"
    lowered_skip = text
    lowered_skip = lowered_skip.replace("Could not be checked at issue time", "")
    lowered_skip = lowered_skip.replace("Not available at issue time", "")
    lowered_skip = lowered_skip.replace("Not available", "")
    for frag in INFORMAL:
        if frag in lowered_skip:
            hits.append(frag)
    return hits
