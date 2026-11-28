"""Ramp Finder Phase 2: the statewide interactive map (steps 1 and 2 of the approved plan).

Private at /preview/ramps-statewide/map (+ .css, .js, .json), cookie-gated like every preview.
Public /ramps/map, /ramps/map.css, /ramps/map.js and /ramps/map.json are served only when
PUBLIC_RAMP_MAP is on; with the flag off the server returns 404 before reaching this module.
Reuses vendor/leaflet and the Wind map's Census coastline (/wind/coast.js, /wind/coast-lo|hi.json).
No tiles, no third-party requests, no visitor location (Near Me is a later step).
"""
from __future__ import annotations

import html
from pathlib import Path

import ramp_map_data

ROOT = Path(__file__).resolve().parent
ASSET_DIR = ROOT / "preview" / "ramp-finder" / "map"
JS_PATH = ASSET_DIR / "map.js"
CSS_PATH = ASSET_DIR / "map.css"
PRIVATE_BASE = "/preview/ramps-statewide/map"
PUBLIC_BASE = "/ramps/map"
SUFFIXES = ("", ".css", ".js", ".json")


def render_html(*, public: bool = False) -> str:
    base = PUBLIC_BASE if public else PRIVATE_BASE
    directory = "/ramps" if public else "/preview/ramps-statewide"
    robots = '<meta name="robots" content="index, follow">\n' if public else '<meta name="robots" content="noindex, nofollow">\n'
    tag = "" if public else '<span class="tag">Private preview</span>'
    b = html.escape(base, quote=True)
    d = html.escape(directory, quote=True)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
{robots}<link rel="icon" href="/branding/favicon.svg">
<title>Ramp Finder map · The Coastal Brief</title>
<link rel="preload" href="/fonts/source-sans-3-var.woff2" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="/fonts/fraunces-var.woff2" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="/fonts/barlow-condensed-600.woff2" as="font" type="font/woff2" crossorigin>
<link rel="stylesheet" href="/vendor/leaflet/leaflet.css"><link rel="stylesheet" href="{b}.css">
<script>try{{var q=/[?&]theme=(light|dark)\\b/.exec(location.search),t=q?q[1]:localStorage.getItem("coastalBrief.theme");if(t==="dark"||(!t&&matchMedia("(prefers-color-scheme:dark)").matches))document.documentElement.classList.add("dark")}}catch(e){{}}</script>
</head><body data-base="{b}" data-directory="{d}">
<header class="bar">
  <img class="mono" src="/branding/favicon.svg" alt="" width="30" height="30">
  <div class="wm"><b>The Coastal Brief</b><small>Ramp Finder</small></div>
  {tag}
  <div class="theme" role="group" aria-label="Theme"><button type="button" data-t="light" aria-pressed="false">Light</button><button type="button" data-t="dark" aria-pressed="false">Dark</button></div>
</header>
<main class="mapwrap">
  <div id="map" role="application" aria-label="Map of North Carolina public boat ramps"></div>
  <div class="key" id="key">
    <p><b>Ramp type</b><span><svg class="kg" viewBox="0 0 28 28" data-k="trailer"></svg>Trailer</span><span><svg class="kg" viewBox="0 0 28 28" data-k="paddle"></svg>Paddle</span><span><svg class="kg" viewBox="0 0 28 28" data-k="limited"></svg>Limited access</span><span><svg class="kg" viewBox="0 0 28 28" data-k="needs_review"></svg>Needs review</span></p>
    <p><b>Status</b><span><svg class="kg" viewBox="0 0 28 28" data-s="temporarily_closed"></svg>Closed</span><span><svg class="kg" viewBox="0 0 28 28" data-s="partially_open"></svg>Partly open</span><span><svg class="kg" viewBox="0 0 28 28" data-s="unc"></svg>Unclear / not stated</span><span class="nb">No badge: listed open</span></p>
    <p><span><svg class="kg" viewBox="0 0 28 28" data-a="1"></svg>Dashed ring: approximate location</span><span class="nb">Not for navigation</span></p>
    <p class="cnt" id="cnt">Loading the official ramp data…</p>
  </div>
  <div class="dock"><section class="panel" id="panel" aria-live="polite" hidden></section></div>
</main>
<script src="/vendor/leaflet/leaflet.js"></script><script src="/wind/coast.js"></script><script src="{b}.js" defer></script>
</body></html>
"""


def resolve(suffix: str, *, public: bool = False):
    """suffix is '', '.css', '.js' or '.json'. Returns (status, content type, body)."""
    if suffix == "":
        return 200, "text/html; charset=utf-8", render_html(public=public)
    if suffix == ".css":
        return 200, "text/css; charset=utf-8", CSS_PATH.read_bytes()
    if suffix == ".js":
        return 200, "text/javascript; charset=utf-8", JS_PATH.read_bytes()
    if suffix == ".json":
        return 200, "application/json; charset=utf-8", ramp_map_data.OUT.read_bytes()
    return 404, "text/plain", "not found"
