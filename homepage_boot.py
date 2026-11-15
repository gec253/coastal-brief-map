"""First-paint homepage conditions: render glance and alerts into the HTML.

Uses conditions.assemble() so the values are the same as /api/conditions.
Does not change data sources, regions, or assembly rules.
"""
from __future__ import annotations

import decimal
import html
import json
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import conditions

ET = ZoneInfo("America/New_York")
_WD = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
NWS_DETAILS = "https://www.weather.gov/mhx/"

_GLANCE_RE = re.compile(
    br'(<nav class="glance-strip" id="glance-strip"[^>]*>)(.*?)(</nav>)',
    re.S,
)
_ALERT_OPEN_RE = re.compile(
    br'<div class="dash-alert[^"]*"[^>]*id="dash-alert"[^>]*>',
    re.S,
)
_BADGE_RE = re.compile(
    br'(<span class="badge" id="freshness-badge"[^>]*>)(.*?)(</span>)',
    re.S,
)
_BOOT_MARK = b"<!--boot-json-->"


def _esc(s) -> str:
    return html.escape("" if s is None else str(s), quote=False)


def _to_dt(t):
    if t is None:
        return None
    if isinstance(t, datetime):
        return t if t.tzinfo else t.replace(tzinfo=timezone.utc)
    if isinstance(t, (int, float)):
        sec = t / 1000.0 if t > 1e12 else float(t)
        return datetime.fromtimestamp(sec, tz=timezone.utc)
    if isinstance(t, str):
        s = t.replace("Z", "+00:00")
        try:
            d = datetime.fromisoformat(s)
        except ValueError:
            return None
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    return None


def _clock(t) -> str:
    d = _to_dt(t)
    if d is None:
        return "—"
    d = d.astimezone(ET)
    h = d.hour % 12 or 12
    ampm = "AM" if d.hour < 12 else "PM"
    return "%d:%02d %s" % (h, d.minute, ampm)


def et_time(t, with_zone=True) -> str:
    d = _to_dt(t)
    if d is None:
        return "—"
    d = d.astimezone(ET)
    now = datetime.now(ET)
    same = d.date() == now.date()
    prefix = "" if same else (_WD[d.weekday()] + " ")
    suffix = " ET" if with_zone is not False else ""
    return prefix + _clock(d) + suffix


def _is_num(v) -> bool:
    return isinstance(v, (int, float)) and v == v and v not in (float("inf"), float("-inf"))


def _round0(n):
    """Nearest int, ties away from zero (decimal ROUND_HALF_UP).

    For the non-negative glance readings (knots, seconds, °F) this matches
    JS Math.round and Number#toFixed(0): 4.5 → 5, 58.5 → 59, 58.4 → 58.
    JS Math.round(-2.5) is -2 (ties toward +Infinity); this helper returns
    -3. Glance values are not negative. None and non-numeric inputs return None.
    """
    if n is None or not _is_num(n):
        return None
    return int(decimal.Decimal(str(n)).to_integral_value(rounding=decimal.ROUND_HALF_UP))


def _fmt(v, d=0) -> str:
    if not _is_num(v):
        return "—"
    return ("%." + str(0 if d is None else d) + "f") % v


def _val(r):
    if r and r.get("status") != "unavailable":
        return r.get("values") or {}
    return {}


def render_glance_html(d: dict) -> str:
    R = d.get("readings") or {}

    def cell(id_, k, v, s, r):
        stale = r and r.get("status") == "stale"
        off = (not r) or r.get("status") == "unavailable" or v == "—"
        return (
            '<a class="gs-cell'
            + (" is-stale" if stale else "")
            + (" is-off" if off else "")
            + '" href="#'
            + _esc(id_)
            + '">'
            + '<span class="gs-k">'
            + _esc(k)
            + (' <span class="gs-stale">stale</span>' if stale else "")
            + "</span>"
            + '<span class="gs-v">'
            + _esc("—" if off else v)
            + "</span>"
            + '<span class="gs-s">'
            + _esc("not reporting" if off else s)
            + "</span></a>"
        )

    w, se, wt = _val(R.get("wind")), _val(R.get("seas")), _val(R.get("waterTemp"))
    evs = [e for e in ((d.get("tides") or {}).get("events") or []) if e.get("t") and e["t"] > _now_ms()]
    ev = evs[0] if evs else None
    tides = d.get("tides") or {}
    tide_r = {"status": "ok"} if tides.get("status") == "ok" else None
    wind_v = (
        (("%s " % w["dirCompass"] if w.get("dirCompass") else "") + str(_round0(w["speedKt"])) + " kt")
        if _is_num(w.get("speedKt"))
        else "—"
    )
    wind_s = ("gust " + str(_round0(w["gustKt"])) + " kt") if _is_num(w.get("gustKt")) else "observed"
    seas_v = (_fmt(se["heightFt"], 1) + " ft") if _is_num(se.get("heightFt")) else "—"
    seas_s = (
        (str(_round0(se["dominantPeriodS"])) + " s" + ((" · " + se["meanDirCompass"]) if se.get("meanDirCompass") else ""))
        if _is_num(se.get("dominantPeriodS"))
        else "observed"
    )
    water_v = (str(_round0(wt["f"])) + "°F") if _is_num(wt.get("f")) else "—"
    tide_k = "Next high" if ev and ev.get("type") == "H" else ("Next low" if ev else "Tide")
    tide_v = _clock(ev["t"]) if ev else "—"
    tide_s = (_fmt(ev["v"], 1) + " ft predicted") if ev and _is_num(ev.get("v")) else "predicted"
    return (
        cell("i-wind", "Wind", wind_v, wind_s, R.get("wind"))
        + cell("i-seas", "Seas", seas_v, seas_s, R.get("seas"))
        + cell("i-water", "Water", water_v, "inshore station", R.get("waterTemp"))
        + cell("i-tide", tide_k, tide_v, tide_s, ev and tide_r)
    )


def _now_ms() -> float:
    return datetime.now(timezone.utc).timestamp() * 1000.0


def render_alerts_html(a: dict | None) -> tuple[str, str]:
    """Return (inner HTML, class list without dash-alert)."""
    items = (a or {}).get("items") or []
    if not items:
        if (a or {}).get("status") == "ok":
            zones = ", ".join((a or {}).get("zones") or [])
            inner = (
                '<div class="al-item"><span class="al-dot"></span>'
                '<span class="al-ev">No NWS alerts right now</span>'
                '<span class="al-meta">No watches, warnings, or advisories for '
                + _esc(zones)
                + ".</span></div>"
            )
        else:
            inner = (
                '<div class="al-item"><span class="al-dot"></span>'
                '<span class="al-ev">Alerts unavailable</span>'
                '<span class="al-meta">Could not check NWS alerts. See weather.gov before heading out.</span></div>'
            )
        cls = "is-clear"
    else:
        parts = []
        for it in items:
            meta = ""
            if it.get("ends"):
                meta += "until " + _esc(et_time(it["ends"]))
            if it.get("areas"):
                meta += (" · " if meta else "") + _esc(it["areas"])
            parts.append(
                '<div class="al-item"><span class="al-dot"></span>'
                '<span class="al-ev">'
                + _esc(it.get("event"))
                + "</span>"
                '<span class="al-meta">'
                + meta
                + "</span></div>"
            )
        inner = "".join(parts)
        cls = "is-active"
    inner += '<a class="al-link" href="' + NWS_DETAILS + '" target="_blank" rel="noopener">NWS details</a>'
    return inner, cls


def _close_div(html_bytes: bytes, open_match_end: int) -> int | None:
    """Index just after the matching </div> for a div that opened before open_match_end."""
    i = open_match_end
    depth = 1
    open_tag = re.compile(br"<div\b")
    close_tag = re.compile(br"</div>")
    while i < len(html_bytes) and depth:
        o = open_tag.search(html_bytes, i)
        c = close_tag.search(html_bytes, i)
        if not c:
            return None
        if o and o.start() < c.start():
            depth += 1
            i = o.end()
        else:
            depth -= 1
            i = c.end()
    return i


def _json_script(obj, el_id: str) -> bytes:
    raw = json.dumps(obj, separators=(",", ":"), ensure_ascii=False)
    raw = raw.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    return (
        b'<script type="application/json" id="%s">%s</script>\n'
        % (el_id.encode("ascii"), raw.encode("utf-8"))
    )


def _replace_text_by_id(data: bytes, el_id: bytes, text: str) -> bytes:
    pat = re.compile(br"(<[^>]*id=\"" + el_id + br"\"[^>]*>)(.*?)(</p>|</span>)", re.S)
    return pat.sub(lambda m: m.group(1) + _esc(text).encode("utf-8") + m.group(3), data, count=1)


def _paint_region_select(data: bytes, region_id, name) -> bytes:
    """Replace the template's single #region-select option with the current region."""
    if not region_id or not name:
        return data
    rid = html.escape(str(region_id), quote=True).encode("utf-8")
    label = html.escape(str(name), quote=False).encode("utf-8")
    pat = re.compile(
        br'(<select id="region-select"[^>]*>)\s*<option value="[^"]*">[^<]*</option>\s*(</select>)',
        re.S,
    )
    return pat.sub(br'\1<option value="' + rid + br'" selected>' + label + br'</option>\2', data, count=1)


def inject(data: bytes, region_id: str | None = None, preview: bool = False) -> bytes:
    """Fill glance, alerts, badge, and boot JSON. Leave the template alone on failure."""
    try:
        listed = conditions.listed_regions(preview=preview)
        status, payload = conditions.assemble(region_id, preview=preview)
    except Exception:
        return data
    if not listed.get("ok") or status != 200 or not (payload or {}).get("ok"):
        return data

    glance = render_glance_html(payload).encode("utf-8")
    alert_inner, alert_cls = render_alerts_html(payload.get("alerts"))
    badge = "Updated " + et_time(payload.get("generatedAt"))
    region = payload.get("region") or {}
    loc = "%s · %s. Location is not requested from your browser." % (
        region.get("name") or "",
        region.get("area") or "",
    )
    sub = region.get("area") or ""

    m = _GLANCE_RE.search(data)
    if m:
        data = data[: m.start()] + m.group(1) + glance + m.group(3) + data[m.end() :]

    am = _ALERT_OPEN_RE.search(data)
    if am:
        end = _close_div(data, am.end())
        if end:
            new_open = (
                b'<div class="dash-alert '
                + alert_cls.encode("ascii")
                + b'" id="dash-alert" role="status">'
            )
            data = data[: am.start()] + new_open + alert_inner.encode("utf-8") + b"</div>" + data[end:]

    bm = _BADGE_RE.search(data)
    if bm:
        data = data[: bm.start()] + bm.group(1) + _esc(badge).encode("utf-8") + bm.group(3) + data[bm.end() :]

    data = data.replace(b' class="panel glance dash is-booting"', b' class="panel glance dash"', 1)
    data = _replace_text_by_id(data, b"loc-line", loc)
    data = _replace_text_by_id(data, b"dash-sub", sub)
    # Keep the glance region control's first-paint label in sync with the
    # current region so a wrapping name (e.g. Wilmington) does not change
    # height when dashboard.js later fills the full option list.
    data = _paint_region_select(data, region.get("id") or region_id, region.get("name"))

    boot = _json_script(payload, "cb-boot-conditions") + _json_script(listed, "cb-boot-regions")
    if _BOOT_MARK in data:
        data = data.replace(_BOOT_MARK, boot, 1)
    else:
        data = data.replace(b'<script src="region-nav.js"', boot + b'<script src="region-nav.js"', 1)
    return data
