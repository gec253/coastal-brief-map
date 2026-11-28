"""Ramp Finder Phase 2: the statewide interactive map (steps 1 and 2 of the approved plan).

Private at /preview/ramps-statewide/map (+ .css, .js, .json), cookie-gated like every preview.
Public /ramps/map, /ramps/map.css, /ramps/map.js and /ramps/map.json are served only when
PUBLIC_RAMP_MAP is on; with the flag off the server returns 404 before reaching this module.
Reuses vendor/leaflet and the Wind map's Census coastline (/wind/coast.js, /wind/coast-lo|hi.json).
No tiles and no third-party requests. Near Me asks for location only on tap and keeps it in memory.
Inland water and geography: self-hosted Census TIGER (public domain), see docs/RAMP_MAP_GEO_SOURCES.md.
"""
from __future__ import annotations

import html
from pathlib import Path

import ramp_map_data
import ramp_search

ROOT = Path(__file__).resolve().parent
ASSET_DIR = ROOT / "preview" / "ramp-finder" / "map"
JS_PATH = ASSET_DIR / "map.js"
CSS_PATH = ASSET_DIR / "map.css"
PRIVATE_BASE = "/preview/ramps-statewide/map"
PUBLIC_BASE = "/ramps/map"
SUFFIXES = ("", ".css", ".js", ".json", "/geo-lo.json", "/geo-hi.json")


def render_html(*, public: bool = False) -> str:
    base = PUBLIC_BASE if public else PRIVATE_BASE
    directory = "/ramps" if public else "/preview/ramps-statewide"
    robots = '<meta name="robots" content="index, follow">\n' if public else '<meta name="robots" content="noindex, nofollow">\n'
    tag = "" if public else '<span class="tag">Private preview</span>'
    b = html.escape(base, quote=True)
    d = html.escape(directory, quote=True)
    search_js = ramp_search.JS.replace("</", "<\\/")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
{robots}<link rel="icon" href="/branding/favicon.svg">
<title>Ramp Finder map · The Coastal Brief</title>
<link rel="preload" href="/fonts/source-sans-3-var.woff2" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="/fonts/fraunces-var.woff2" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="/fonts/barlow-condensed-600.woff2" as="font" type="font/woff2" crossorigin>
<link rel="stylesheet" href="/vendor/leaflet/leaflet.css"><link rel="stylesheet" href="{b}.css">
<script>try{{var q=/[?&]theme=(light|dark)\\b/.exec(location.search),t=q?q[1]:localStorage.getItem("coastalBrief.theme");if(t==="dark"||((!t||t==="auto")&&matchMedia("(prefers-color-scheme:dark)").matches))document.documentElement.classList.add("dark")}}catch(e){{}}</script>
</head><body data-base="{b}" data-directory="{d}">
<a class="skip" href="#list">Skip to the ramp list</a>
<header class="bar">
  <img class="mono" src="/branding/favicon.svg" alt="" width="30" height="30">
  <div class="wm"><b>The Coastal Brief</b><small>Ramp Finder</small></div>
  {tag}
  <a class="dirlink" id="dirlink" href="{d}">List</a>
  <div class="theme" role="group" aria-label="Theme"><button type="button" data-t="auto" aria-pressed="false">Auto</button><button type="button" data-t="light" aria-pressed="false">Light</button><button type="button" data-t="dark" aria-pressed="false">Dark</button></div>
</header>
<div class="shell" id="shell" data-view="map">
  <section class="tools" aria-label="Search and filters">
    <div class="srow">
      <label class="search"><span class="vh">Search ramps by name, town, county or waterbody</span>
        <svg viewBox="0 0 20 20" aria-hidden="true"><circle cx="8.5" cy="8.5" r="5.5"/><path d="M13 13l4.5 4.5"/></svg>
        <input id="q" type="search" placeholder="Ramp, town, county, water" autocomplete="off" enterkeyhint="search" role="combobox" aria-autocomplete="list" aria-expanded="false" aria-controls="sugg"></label>
      <button type="button" class="fbtn" id="fbtn" aria-expanded="false" aria-controls="fpanel"><svg viewBox="0 0 20 20" aria-hidden="true"><path d="M3 5h14M6 10h8M8.5 15h3"/></svg><span>Filters</span><b id="fcount" hidden>0</b></button>
    </div>
    <div class="crow">
      <div class="chips" id="chips" role="group" aria-label="Quick filters"></div>
      <div class="seg" role="group" aria-label="Map or list"><button type="button" id="vmap" aria-pressed="true">Map</button><button type="button" id="vlist" aria-pressed="false">List</button></div>
    </div>
    <div class="actf" id="actf" role="group" aria-label="Active filters" hidden></div>
    <div class="sugg" id="sugg" role="listbox" aria-label="Search suggestions" hidden></div>
    <p class="vh" id="live" aria-live="polite"></p>
  </section>
  <aside class="side" id="side" aria-label="Ramp list">
    <div class="sumline"><button type="button" id="nearoff" hidden>Exit Near me</button><p id="sum"></p><p class="sl" id="sl" hidden>Distances are straight-line, not driving distance.</p></div>
    <ol id="list" class="list" tabindex="-1"></ol>
  </aside>
  <main class="mapwrap">
    <div id="map" role="application" aria-label="Map of North Carolina public boat ramps"></div>
    <p class="attrib" id="attrib">Leaflet | Basemap: U.S. Census Bureau coastline and TIGER/Line® water and places (public domain). Illustration, not for navigation</p>
    <div class="key" id="key">
      <button type="button" class="ktog" id="ktog" aria-expanded="false" aria-controls="kbody"><svg class="kg" viewBox="0 0 28 28" data-k="trailer"></svg>Map key<svg class="chev" viewBox="0 0 12 12" aria-hidden="true"><path d="M2 4l4 4 4-4"/></svg></button>
      <div class="kbody" id="kbody" hidden>
        <p><b>Ramp type</b><span><svg class="kg" viewBox="0 0 28 28" data-k="trailer"></svg>Trailer</span><span><svg class="kg" viewBox="0 0 28 28" data-k="paddle"></svg>Paddle</span><span><svg class="kg" viewBox="0 0 28 28" data-k="limited"></svg>Limited access</span><span><svg class="kg" viewBox="0 0 28 28" data-k="needs_review"></svg>Needs review</span></p>
        <p><b>Status</b><span><svg class="kg" viewBox="0 0 28 28" data-s="temporarily_closed"></svg>Closed</span><span><svg class="kg" viewBox="0 0 28 28" data-s="partially_open"></svg>Partly open</span><span><svg class="kg" viewBox="0 0 28 28" data-s="unc"></svg>Unclear / not stated</span><span class="nb">No badge: listed open</span></p>
        <p><span><svg class="kg" viewBox="0 0 28 28" data-a="1"></svg>Dashed ring: approximate location</span><span class="nb">Not for navigation</span></p>
        <p class="cnt" id="cnt">Loading the official ramp data…</p>
      </div>
    </div>
    <div class="dock">
      <button type="button" class="near" id="near"><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="4.2"/><path d="M12 2.5v4M12 17.5v4M2.5 12h4M17.5 12h4"/></svg><span><b>Near me</b><small>Nearest ramps first</small></span></button>
      <section class="panel" id="panel" aria-label="Ramp details" hidden></section>
    </div>
    <section class="sheet" id="pre" role="dialog" aria-modal="false" aria-labelledby="pre-h" hidden>
      <h2 id="pre-h">Find ramps near you</h2>
      <p id="pre-p">Your browser will ask for permission when you tap <b>Use my location</b>. We use it once, on this device, to sort ramps by distance. <b>It is never stored or sent</b> to The Coastal Brief or anyone else, and this page’s address does not change.</p>
      <p class="fine">Distances are <b>straight-line</b>, not driving distance. Prefer not to share? Search a town, county or waterbody instead.</p>
      <div class="acts"><button type="button" class="btn pri" id="pre-go">Use my location</button><button type="button" class="btn" id="pre-no">Not now</button></div>
    </section>
  </main>
  <section class="fpanel" id="fpanel" aria-label="Filters" hidden></section>
</div>
<script src="/vendor/leaflet/leaflet.js"></script><script src="/wind/coast.js"></script><script>{search_js}</script><script src="{b}.js" defer></script>
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
    if suffix in ("/geo-lo.json", "/geo-hi.json"):
        return 200, "application/json; charset=utf-8", (ASSET_DIR / suffix[1:]).read_bytes()
    if suffix == ".json":
        return 200, "application/json; charset=utf-8", ramp_map_data.OUT.read_bytes()
    return 404, "text/plain", "not found"
