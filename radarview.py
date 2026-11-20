"""Private /radar viewer: data payload and the test-only fixture.

Real data reuses server.py's WeatherAPI integration unchanged (handle_radar_meta: radar.json cached 3 min,
signed tile template kept in memory; tiles via /api/radar/tile/{z}/{x}/{y}.png?t=, cached 2 h by z/x/y/time).
Without a radar entitlement (WeatherAPI error 2009) the viewer gets an honest "unavailable on current data
plan" state, never fixture frames.

FIXTURE (synthetic "TEST DATA") is served only when RADAR_FIXTURE=1 AND the process is not on Render
(Render sets RENDER / RENDER_SERVICE_ID in every service), so production cannot enable it.
"""
from __future__ import annotations

import json
import os
import html as _html
import re
from pathlib import Path

FIXTURE_DIR = Path(__file__).resolve().parent / "tests" / "fixtures" / "radar"
FIXTURE_LABEL = "TEST DATA — not current radar"
PLAN_MESSAGE = "Radar unavailable on current data plan"


def fixture_mode() -> bool:
    if os.environ.get("RENDER") or os.environ.get("RENDER_SERVICE_ID"):
        return False
    return os.environ.get("RADAR_FIXTURE", "").strip() == "1"


def fixture_payload() -> dict:
    meta = json.loads((FIXTURE_DIR / "fixture.json").read_text(encoding="utf-8"))
    return {
        "ok": True, "available": True, "covered": True, "fixture": True, "fixture_label": FIXTURE_LABEL,
        "fixture_source": meta["source"],
        "tile_url": "/radar/fixture-tile/{z}/{x}/{y}.png?t={time}",
        "min_zoom": meta["zoom"], "max_zoom": 10, "max_native_zoom": meta["zoom"], "tile_size": 256,
        "frames": meta["frames"], "legend": meta["legend"],
        "attribution": "TEST DATA: synthetic pattern, not radar.",
        "disclaimer": FIXTURE_LABEL,
    }


def view_payload(handle_radar_meta) -> tuple[int, dict]:
    """(status, payload) for /api/radar-view."""
    if fixture_mode():
        return 200, fixture_payload()
    status, p = handle_radar_meta()
    p = dict(p)
    p["fixture"] = False
    if not p.get("ok"):
        if p.get("reason") == "coming_soon":
            p.update({"reason": "plan", "message": PLAN_MESSAGE})
            return 200, p
        return status, p
    # MRMS is a ~1 km grid; z7 tiles are ~1 km/px at 35°N, so higher zooms add tiles, not detail.
    # Capping the native zoom keeps a 25-frame loop to ~9 tiles a frame on a phone (z8 needs ~15).
    p["max_native_zoom"] = min(int(p.get("max_zoom", 11) or 11), REAL_MAX_NATIVE_ZOOM)
    return 200, p


REAL_MAX_NATIVE_ZOOM = 7
def fixture_tile(z: str, x: str, y: str, t: str) -> bytes | None:
    """PNG bytes for a fixture tile, or None (outside the fixture, bad input, or not in fixture mode)."""
    if not fixture_mode():
        return None
    if not (re.fullmatch(r"\d{1,2}", z) and re.fullmatch(r"\d{1,4}", x) and re.fullmatch(r"\d{1,4}", y) and re.fullmatch(r"\d{12}", t or "")):
        return None
    p = FIXTURE_DIR / ("%s_%s_%s_%s.png" % (t, z, x, y))
    return p.read_bytes() if p.is_file() else None


def page_html(html: str, payload: dict) -> str:
    """Server-render the honest unavailable state into radar.html, so it paints with the chrome (LCP/CLS)."""
    if payload.get("ok") and payload.get("frames"):
        # WeatherAPI's radar.json `attribution` is "Credit to show on your map (required by the radar data
        # providers)": render it verbatim, server-side, so the footer never changes size after load.
        credit = (payload.get("attribution") or "").strip().rstrip(".")
        if credit and not payload.get("fixture"):
            html = html.replace('<span id="r-credit">Radar: NOAA/NSSL MRMS via WeatherAPI.com</span>',
                                '<span id="r-credit">%s</span>' % _html.escape(credit))
        return html
    plan = payload.get("reason") in ("plan", "coming_soon")
    out = html.replace('<div class="r-unavail" id="r-unavail" role="status" hidden>', '<div class="r-unavail" id="r-unavail" role="status">')
    out = out.replace('<p class="w-status" id="r-status" role="status">', '<p class="w-status" id="r-status" role="status" hidden>')
    out = out.replace('id="r-legend" role="img"', 'id="r-legend" hidden role="img"').replace('<label class="r-fc">', '<label class="r-fc" hidden>')
    out = out.replace('<span class="w-badge" id="r-badge">Observed</span>', '<span class="w-badge" id="r-badge">Radar off</span>')
    if not plan:
        out = out.replace(PLAN_MESSAGE + "</strong>", "Radar is unavailable right now</strong>")
    return out
