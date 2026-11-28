/* Ramp Finder Phase 2 statewide map (Ed t556u, t558u). Private preview; PUBLIC_RAMP_MAP stays off.
   Vendored Leaflet + the Wind map's Census coastline + our own Census TIGER water layer (public domain).
   Marker artwork from Summer's approved proposal.
   Privacy: location is requested only when the visitor taps "Use my location". The position lives in one
   in-memory variable, is never stored, logged, sent or written to the address bar, and is cleared on exit.
   The only requests this script makes are for our own data and geography files. */
(function () {
"use strict";
var $ = function (s) { return document.querySelector(s); };
var BODY = document.body, BASE = BODY.dataset.base, DIRECTORY = BODY.dataset.directory;
var NEEDS_REVIEW_NOTE = "The official sources we checked do not confirm what kind of launch this is.";
var STL = { listed_open: "Listed open", temporarily_closed: "Temporarily closed", partially_open: "Partly open", conflicting: "Status unclear", not_stated: "Status not stated" };
var TYL = { trailer: "Trailer launch", paddle: "Paddle / carry-in", limited: "Limited access", needs_review: "Needs review" };
function esc(s) { return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
function isUnc(st) { return st === "conflicting" || st === "not_stated"; }
var RS = window.CBRampSearch; /* shared with the /ramps directory: ramp_search.py */
function norm(s) { return RS.norm(s); }

/* ---- marker artwork: shape = access type, badge = status, never colour alone ---- */
function shape(t, cls) {
  var c = cls ? ' class="' + cls + '"' : "";
  if (t === "trailer") return '<circle' + c + ' cx="14" cy="14" r="9.6"/>';
  if (t === "paddle") return '<rect' + c + ' x="7.2" y="7.2" width="13.6" height="13.6" rx="2.6" transform="rotate(45 14 14)"/>';
  if (t === "limited") return '<rect' + c + ' x="4.6" y="4.6" width="18.8" height="18.8" rx="4.4"/>';
  return '<polygon' + c + ' points="14,4 22.6,9 22.6,19 14,24 5.4,19 5.4,9" stroke-linejoin="round"/>';
}
function glyph(t) {
  if (t === "trailer") return '<path class="g-trailer" d="M8.6 17.6H19.6V10.2Z"/>';
  if (t === "paddle") return '<ellipse class="g-paddle" cx="14" cy="14" rx="2.2" ry="4.8" transform="rotate(45 14 14)"/>';
  if (t === "limited") return '<rect class="g-limited" x="8.4" y="12.3" width="11.2" height="3.4" rx="1.2"/>';
  return '<g class="g-needs_review"><circle cx="9.6" cy="14" r="1.5"/><circle cx="14" cy="14" r="1.5"/><circle cx="18.4" cy="14" r="1.5"/></g>';
}
function badgeSvg(st) {
  if (st === "listed_open") return "";
  var base = '<circle class="bd-ring" cx="22.4" cy="5.8" r="6.6"/>';
  if (st === "temporarily_closed") return base + '<circle class="bd-bad" cx="22.4" cy="5.8" r="6.6"/><path class="bd-g" d="M20 3.4l4.8 4.8M24.8 3.4L20 8.2"/>';
  if (st === "partially_open") return base + '<circle class="bd-part" cx="22.4" cy="5.8" r="6.6"/><path class="bd-pg" d="M22.4 -.8A6.6 6.6 0 0 0 22.4 12.4Z"/><circle class="bd-po" cx="22.4" cy="5.8" r="5.9"/>';
  return base + '<circle class="bd-unc" cx="22.4" cy="5.8" r="6.6"/><circle class="bd-d" cx="22.4" cy="5.8" r="5.2"/><text class="bd-q" x="22.4" y="9.2">?</text>';
}
function mkSvg(t, st, sel, cls) {
  var s = (st === "temporarily_closed") ? '<path class="slash-h" d="M7.6 20.4L20.4 7.6"/><path class="slash" style="stroke:var(--bad)" d="M7.6 20.4L20.4 7.6"/>' : "";
  return '<svg class="mk' + (cls ? " " + cls : "") + '" viewBox="0 0 28 28" aria-hidden="true">' + shape(t, "halo") + shape(t, "b-" + t) + glyph(t) + s + (sel ? shape(t, "sel").replace("<", '<g transform="translate(14 14) scale(1.32) translate(-14 -14)"><').replace("/>", "/></g>") : "") + badgeSvg(st) + '</svg>';
}
function badgeInline(kind, v) { // small inline icon for chips / filters
  if (kind === "ty") return '<svg viewBox="0 0 28 28" class="mk" aria-hidden="true">' + shape(v, "b-" + v) + glyph(v) + '</svg>';
  if (v === "listed_open") return '<svg viewBox="0 0 28 28" aria-hidden="true"><circle cx="14" cy="14" r="8.5" fill="none" stroke="currentColor" stroke-width="2.2"/><path d="M10 14.2l3 3 5-6" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/></svg>';
  return '<svg viewBox="0 0 28 28" class="mk" aria-hidden="true"><g transform="translate(-8.4 -.2) scale(1.45)">' + badgeSvg(v).replace('class="bd-ring"', 'class="bd-ring" style="stroke-width:1.2"') + '</g></svg>';
}
function apxRing() { return '<circle class="apx" cx="14" cy="14" r="13.4"/>'; }
function pinSvg(r, sel) {
  var s = mkSvg(r.ty, r.st, sel, "");
  return r.pr === "approx" ? s.replace('aria-hidden="true">', 'aria-hidden="true">' + apxRing()) : s;
}
document.querySelectorAll(".kg").forEach(function (e) {
  if (e.dataset.k) e.innerHTML = shape(e.dataset.k, "halo") + shape(e.dataset.k, "b-" + e.dataset.k) + glyph(e.dataset.k);
  else if (e.dataset.a) e.innerHTML = apxRing() + shape("trailer", "halo") + shape("trailer", "b-trailer") + glyph("trailer");
  else { var s = e.dataset.s; e.innerHTML = badgeSvg(s === "unc" ? "not_stated" : s).replace(/22\.4/g, "14").replace(/5\.8/g, "14").replace(/-\.8/g, "7.4").replace("12.4Z", "20.6Z"); }
  e.setAttribute("class", "kg mk"); e.setAttribute("aria-hidden", "true");
});

/* ---- map: vendored Leaflet, Census coastline, no tiles ---- */
var reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
function wide() { return matchMedia("(min-width:900px)").matches; }
var map = L.map("map", { zoomControl: false, zoomSnap: 0.25, zoomDelta: 0.5, minZoom: 5.5, maxZoom: 16, worldCopyJump: false,
  zoomAnimation: !reduce, fadeAnimation: !reduce, markerZoomAnimation: !reduce });
L.control.zoom({ position: "topright" }).addTo(map);
var NC = [[33.8, -84.4], [36.65, -75.3]];
function home() { if (wide()) map.fitBounds(NC, { animate: false, padding: [4, 4] }); else map.setView([35.25, -79.3], 6.5, { animate: false }); }
home();
map.attributionControl.setPrefix("Leaflet");
map.attributionControl.addAttribution("Basemap: U.S. Census Bureau coastline and TIGER/Line® water and places (public domain). Illustration, not for navigation");
function css(v) { return getComputedStyle(document.documentElement).getPropertyValue(v).trim(); }
var coast = CBCoast.layer({ base: "/wind/coast-", land: css("--coast-land"), line: css("--coast-line"), lineWidth: 1 }).addTo(map);

/* ---- inland water and geography (Census TIGER, public domain; self-hosted) ---- */
map.createPane("geo"); map.getPane("geo").style.zIndex = 350; map.getPane("geo").style.pointerEvents = "none";
map.createPane("labels"); map.getPane("labels").style.zIndex = 450; map.getPane("labels").style.pointerEvents = "none";
var geoR = L.canvas({ pane: "geo", padding: 0.3 });
var GEO = { lo: null, hi: null, hiLoading: false, on: null, layers: [], labels: [] };
function dec(a) { var out = [], x = 0, y = 0; for (var i = 0; i < a.length; i += 2) { x += a[i]; y += a[i + 1]; out.push([y / 1e4, x / 1e4]); } return out; }
function riverW() { var z = map.getZoom(); return z < 8 ? 0.7 : z < 10 ? 1.1 : z < 12 ? 1.6 : 2.2; }
function drawGeo(doc) {
  GEO.layers.forEach(function (l) { map.removeLayer(l); }); GEO.layers = []; GEO.on = doc;
  var sea = css("--sea"), wl = css("--water-line");
  GEO.layers.push(L.polyline([].concat.apply([], doc.states.map(function (f) { return f.map(dec); })), { renderer: geoR, interactive: false, color: css("--state"), weight: 1, dashArray: "5 4" }).addTo(map));
  GEO.layers.push(L.polyline([].concat.apply([], doc.rivers.map(function (f) { return f.map(dec); })), { renderer: geoR, interactive: false, color: css("--river"), weight: riverW(), opacity: 0.95, lineCap: "round", lineJoin: "round" }).addTo(map));
  GEO.layers.push(L.polygon(doc.water.map(function (f) { return f.map(dec); }), { renderer: geoR, interactive: false, color: wl, weight: 0.6, fillColor: sea, fillOpacity: 1 }).addTo(map));
}
function geoFor() {
  var z = map.getZoom();
  if (z >= 9 && !GEO.hi && !GEO.hiLoading) { GEO.hiLoading = true; fetch(BASE + "/geo-hi.json", { credentials: "same-origin" }).then(function (r) { return r.json(); }).then(function (d) { GEO.hi = d; geoFor(); }).catch(function () { GEO.hiLoading = false; }); }
  var want = z >= 9 && GEO.hi ? GEO.hi : GEO.lo;
  if (want && want !== GEO.on) drawGeo(want);
  else if (GEO.layers[1]) GEO.layers[1].setStyle({ weight: riverW() });
}
function restyleGeo() { if (GEO.on) drawGeo(GEO.on); }
function makeLabels(doc) {
  GEO.labels = doc.labels.map(function (l) {
    var cls = l.k === "lake" ? "lb lake" : l.k === "river" ? "lb river" : (l.z <= 6 ? "lb big" : "lb");
    return { z: l.z, m: L.marker([l.la, l.lo], { pane: "labels", interactive: false, keyboard: false, icon: L.divIcon({ className: "", html: '<span class="' + cls + '">' + esc(l.t) + "</span>", iconSize: [0, 0] }) }) };
  });
  syncLabels();
}
function syncLabels() { var z = map.getZoom(); GEO.labels.forEach(function (o) { var show = z >= o.z; if (show && !map.hasLayer(o.m)) o.m.addTo(map); if (!show && map.hasLayer(o.m)) map.removeLayer(o.m); }); }

var mlayer = L.layerGroup().addTo(map), youLayer = L.layerGroup().addTo(map);

/* ---- state: search, filters, view. NEAR (the visitor's position) is never part of S or the URL. ---- */
var D = [], byId = {}, META = null;
var S = { q: "", scope: null, f: { ty: {}, st: {}, fac: {}, fee: {} }, sel: null, view: "map", more: 60 };
var NEAR = null;
var FAC = { ada: ["ADA features listed", function (r) { return r.ada.length > 0; }], rr: ["Restrooms listed", function (r) { return r.rr; }],
  lt: ["Lighting listed", function (r) { return r.lt; }], dk: ["Boarding docks listed", function (r) { return r.dk > 0; }], tp: ["Trailer parking listed", function (r) { return r.tp > 0; }] };
var FEE = { free_stated: "Free (stated)", camping_only: "Camping fees apply", fee_applies: "Fee applies", not_stated: "Fee not stated" };
var FEE_CARD = { free_stated: "Free (stated by the owner)", fee_applies: "Fee applies", camping_only: "Camping fees apply; not a general day-use launch", not_stated: "Fee not stated" };
function on(g) { return Object.keys(S.f[g]); }
function rad(x) { return x * Math.PI / 180; }
function miles(a, b) { var dl = rad(b.lat - a.lat), dn = rad(b.lon - a.lon), x = Math.sin(dl / 2) * Math.sin(dl / 2) + Math.cos(rad(a.lat)) * Math.cos(rad(b.lat)) * Math.sin(dn / 2) * Math.sin(dn / 2); return 2 * 3958.8 * Math.asin(Math.sqrt(x)); }
function fmtD(r, d) { return (r.pr === "approx" ? "≈ " : "") + (d < 10 ? d.toFixed(1) : Math.round(d)) + " mi"; }
function where(r) { return [r.ci, r.co ? r.co + " Co." : "", r.w].filter(Boolean).join(" · "); }
function townKey(r) { return r.ci + "|" + r.co; }

function matchQ(r) {
  var sc = S.scope;
  if (sc) return sc.k === "ramp" ? r.id === sc.v : sc.k === "town" ? townKey(r) === sc.v : sc.k === "county" ? r.co === sc.v : r.w === sc.v;
  return RS.matches(r._hay, S.q);
}
function pass(r, skip) {
  var a;
  if (skip !== "ty" && (a = on("ty")).length && a.indexOf(r.ty) < 0) return false;
  if (skip !== "st" && (a = on("st")).length && a.indexOf(r.st) < 0) return false;
  if (skip !== "fee" && (a = on("fee")).length && a.indexOf(r.fee) < 0) return false;
  if (skip !== "fac") { a = on("fac"); for (var i = 0; i < a.length; i++) if (!FAC[a[i]][1](r)) return false; }
  return true;
}
function results() {
  var out = D.filter(function (r) { return pass(r) && matchQ(r); });
  if (NEAR) {
    out.forEach(function (r) { r.d = r.pr !== "none" ? miles(NEAR, { lat: r.la, lon: r.lo }) : null; });
    out.sort(function (a, b) { return a.d === null ? (b.d === null ? a.n.localeCompare(b.n) : 1) : b.d === null ? -1 : a.d - b.d; });
  } else {
    out.forEach(function (r) { r.d = null; });
    out.sort(function (a, b) { return ((a.pr === "none") - (b.pr === "none")) || a.n.localeCompare(b.n); });
  }
  return out;
}

/* ---- URL state: search and filters only. Never location, never written by Near Me. ---- */
var URLKEYS = ["q", "in", "type", "status", "fac", "fee"];
function urlFromState() {
  var u = new URLSearchParams(location.search);
  URLKEYS.forEach(function (k) { u.delete(k); });
  if (S.scope) u.set("in", S.scope.k + ":" + S.scope.v); else if (S.q.trim()) u.set("q", S.q.trim());
  [["type", "ty"], ["status", "st"], ["fac", "fac"], ["fee", "fee"]].forEach(function (p) { var a = on(p[1]); if (a.length) u.set(p[0], a.join(",")); });
  var s = u.toString(); return location.pathname + (s ? "?" + s : "");
}
function writeURL() { var want = urlFromState(); if (want !== location.pathname + location.search) history.replaceState(null, "", want); }
function readURL() {
  var u = new URLSearchParams(location.search), inn = u.get("in");
  if (inn && inn.indexOf(":") > 0) { var k = inn.slice(0, inn.indexOf(":")), v = inn.slice(inn.indexOf(":") + 1); if (["ramp", "town", "county", "water"].indexOf(k) > -1) S.scope = { k: k, v: v }; }
  if (u.get("q")) S.q = u.get("q").slice(0, 80);
  [["type", "ty", TYL], ["status", "st", STL], ["fac", "fac", FAC], ["fee", "fee", FEE]].forEach(function (p) { (u.get(p[0]) || "").split(",").forEach(function (k) { if (p[2][k]) S.f[p[1]][k] = 1; }); });
}
function scopeLabel(sc) { if (sc.k === "ramp") return byId[sc.v] ? byId[sc.v].n : ""; if (sc.k === "town") return sc.v.split("|")[0]; if (sc.k === "county") return sc.v + " County"; return sc.v; }

function refresh(fit) {
  S.more = 60; renderList(); renderMarkers(); writeURL();
  var res = results();
  if (fit) { var p = res.filter(function (r) { return r.pr !== "none"; }); if (p.length) map.fitBounds(L.latLngBounds(p.map(function (r) { return [r.la, r.lo]; })), { padding: [50, 50], maxZoom: 12, animate: !reduce }); }
  if (!$("#fpanel").hidden) { var g = $("#fgo"); if (g) g.textContent = "Show " + res.length + (res.length === 1 ? " ramp" : " ramps"); }
  $("#live").textContent = res.length + (res.length === 1 ? " ramp matches." : " ramps match.");
}

/* ---- markers: greedy pixel-radius clustering, no library ---- */
var R = 48;
function priority(r) { return r.st === "temporarily_closed" ? 0 : r.st === "partially_open" ? 1 : isUnc(r.st) ? 2 : 3; }
function clusters(pts, z) {
  var seeds = [];
  pts.slice().sort(function (a, b) { return priority(a) - priority(b) || (a.id < b.id ? -1 : 1); }).forEach(function (r) {
    var p = map.project([r.la, r.lo], z), best = null, bd = R * R;
    for (var i = 0; i < seeds.length; i++) { var dx = seeds[i].p.x - p.x, dy = seeds[i].p.y - p.y, d = dx * dx + dy * dy; if (d < bd) { bd = d; best = seeds[i]; } }
    if (best) best.m.push(r); else seeds.push({ p: p, r: r, m: [r] });
  });
  return seeds;
}
var raf = 0;
function schedule() { if (!raf) raf = requestAnimationFrame(function () { raf = 0; renderMarkers(); }); }
function renderMarkers() {
  mlayer.clearLayers(); if (!D.length) return;
  var z = map.getZoom(), b = map.getBounds().pad(0.25), all = results();
  var rank = {}; if (NEAR) all.filter(function (r) { return r.pr !== "none"; }).slice(0, 5).forEach(function (r, i) { rank[r.id] = i + 1; });
  var pts = all.filter(function (r) { return r.pr !== "none" && b.contains([r.la, r.lo]); });
  if (z >= map.getMaxZoom()) { pts.forEach(function (r) { addSingle(r, rank[r.id]); }); return; }
  clusters(pts, z).forEach(function (c) {
    if (c.m.length === 1) return addSingle(c.r, rank[c.r.id]);
    var closed = 0, unc = 0, part = 0, apx = 0;
    c.m.forEach(function (r) { if (r.st === "temporarily_closed") closed++; else if (isUnc(r.st)) unc++; else if (r.st === "partially_open") part++; if (r.pr === "approx") apx++; });
    var sz = Math.min(48, 34 + Math.sqrt(c.m.length) * 3), hint = closed ? "temporarily_closed" : part ? "partially_open" : unc ? "not_stated" : "";
    var title = c.m.length + " ramps. " + (closed ? closed + " temporarily closed. " : "") + (part ? part + " partly open. " : "") + (unc ? unc + " with unclear or unstated status. " : "") + (apx ? apx + " at approximate locations. " : "") + "Zoom in.";
    var m = L.marker([c.r.la, c.r.lo], { keyboard: true, title: title, alt: title, zIndexOffset: 500, icon: L.divIcon({ className: "", iconSize: [48, 48], iconAnchor: [24, 24],
      html: '<div class="clw"><div class="cl" style="width:' + sz + "px;height:" + sz + 'px">' + c.m.length + (hint ? '<small><svg viewBox="0 0 28 28" class="mk">' + badgeSvg(hint).replace(/22\.4/g, "14").replace(/5\.8/g, "14").replace(/-\.8/g, "7.4").replace("12.4Z", "20.6Z") + "</svg></small>" : "") + "</div></div>" }) });
    m.on("click", function () { map.fitBounds(L.latLngBounds(c.m.map(function (r) { return [r.la, r.lo]; })), { padding: [70, 70], maxZoom: map.getMaxZoom(), animate: !reduce }); });
    m.addTo(mlayer);
  });
}
function addSingle(r, rk) {
  var isSel = S.sel === r.id;
  var title = r.n + ". " + r.tyl + ". " + r.stl + "." + (r.pr === "approx" ? " Approximate location." : "");
  var m = L.marker([r.la, r.lo], { keyboard: true, title: title, alt: title, zIndexOffset: isSel ? 900 : (r.st !== "listed_open" ? 300 : 0),
    icon: L.divIcon({ className: "", iconSize: [44, 44], iconAnchor: [22, 22], html: '<div class="mkw">' + pinSvg(r, isSel).replace("<svg ", '<svg width="32" height="32" ') + (rk ? '<span class="rank">' + rk + "</span>" : "") + "</div>" }) });
  m.on("click", function () { select(r.id, false); }); m.addTo(mlayer);
}
map.on("moveend zoomend", function () { syncLabels(); geoFor(); schedule(); });

/* ---- list (same filtered set as the map) ---- */
function badges(r) { return '<span class="badge t-' + r.ty + '">' + badgeInline("ty", r.ty) + esc(r.tyl) + '</span><span class="badge s-' + r.st + '">' + badgeInline("st", r.st) + esc(r.stl) + "</span>"; }
function itemHtml(r, i) {
  var ds = r.d != null ? '<span class="ds">' + fmtD(r, r.d) + "<small>straight-line</small></span>" : "";
  var rk = NEAR && r.d != null && i < 5 ? '<span class="rk">#' + (i + 1) + " nearest · </span>" : "";
  var icon = r.pr === "none" ? "" : pinSvg(r, false).replace("<svg ", '<svg width="30" height="30" ');
  var extra = r.pr === "none" ? '<span class="na">Address only · no verified map location' + (NEAR ? " · distance unavailable" : "") + "</span>" : r.pr === "approx" ? '<span class="na">≈ Approximate location</span>' : "";
  return '<li><button type="button" class="it" data-id="' + r.id + '"' + (S.sel === r.id ? ' aria-current="true"' : "") + ">" + icon + '<span class="nm">' + esc(r.n) + "</span>" + ds + '<span class="wh">' + rk + esc(where(r)) + '</span><span class="bd">' + badges(r) + extra + "</span></button></li>";
}
function renderList() {
  var res = results(), pins = res.filter(function (r) { return r.pr !== "none"; }).length, addr = res.length - pins;
  var head = NEAR ? "<b>Nearest first</b> · " + res.length + " ramps" : "<b>" + res.length + "</b> of " + (META ? META.total : 0) + " ramps · " + pins + " on map" + (addr ? " · " + addr + " address only" : "");
  var act = activeFilters();
  $("#actf").innerHTML = act.length ? '<span class="lbl">Active:</span>' + act.map(function (a) { return '<button type="button" class="af" data-g="' + a[0] + '" data-k="' + esc(a[1]) + '" aria-label="Remove filter: ' + esc(a[2]) + '">' + esc(a[2]) + ' <span aria-hidden="true">×</span></button>'; }).join("") + (res.length ? "" : '<button type="button" class="af all" data-g="all">Search all North Carolina ramps</button>') : "";
  $("#actf").hidden = !act.length;
  $("#sum").innerHTML = head; $("#nearoff").hidden = !NEAR; $("#sl").hidden = !NEAR;
  var shown = res.slice(0, S.more);
  $("#list").innerHTML = shown.length ? shown.map(itemHtml).join("") + (res.length > shown.length ? '<li><button type="button" class="btn" id="more" style="margin:10px 14px;width:calc(100% - 28px);flex:none">Show more (' + (res.length - shown.length) + ")</button></li>" : "") : '<li class="empty">' + (act.length ? 'No ramps match with these filters.<button type="button" class="btn pri" id="allnc">Search all North Carolina ramps</button>' : "No ramps match that search. Try a town, county, ramp name or waterbody.") + "</li>";
  var n = 0; ["ty", "st", "fac", "fee"].forEach(function (g) { n += on(g).length; }); $("#fcount").textContent = n; $("#fcount").hidden = !n;
  syncChips();
}
/* Active filters are always visible and removable. Search itself is statewide and never needs a reset. */
function activeFilters() {
  var a = [];
  if (S.scope) a.push(["scope", "", "In: " + scopeLabel(S.scope)]);
  on("ty").forEach(function (k) { a.push(["ty", k, TYL[k]]); });
  on("st").forEach(function (k) { a.push(["st", k, STL[k]]); });
  on("fac").forEach(function (k) { a.push(["fac", k, FAC[k][0]]); });
  on("fee").forEach(function (k) { a.push(["fee", k, FEE[k]]); });
  return a;
}
function searchAllNC() {
  if (S.scope) { S.q = scopeLabel(S.scope); S.scope = null; $("#q").value = S.q; }
  ["ty", "st", "fac", "fee"].forEach(function (g) { S.f[g] = {}; });
  refresh(true); if (!$("#fpanel").hidden) renderFilters();
  $("#live").textContent = "Searching all North Carolina ramps. " + $("#live").textContent;
}
$("#actf").addEventListener("click", function (e) {
  var b = e.target.closest(".af"); if (!b) return;
  if (b.dataset.g === "all") { searchAllNC(); $("#q").focus(); return; }
  if (b.dataset.g === "scope") { S.q = ""; S.scope = null; $("#q").value = ""; } else delete S.f[b.dataset.g][b.dataset.k];
  refresh(false); if (!$("#fpanel").hidden) renderFilters(); var n = $("#actf .af"); (n || $("#q")).focus();
});
$("#list").addEventListener("click", function (e) {
  if (e.target.id === "allnc") { searchAllNC(); return; }
  if (e.target.id === "more") { S.more += 60; renderList(); return; }
  var b = e.target.closest(".it"); if (b) select(b.dataset.id, true);
});

/* ---- quick chips ---- */
var CHIPS = [["ty", "trailer", "Trailer"], ["ty", "paddle", "Paddle / carry-in"], ["st", "listed_open", "Listed open"], ["fac", "ada", "ADA features listed"]];
$("#chips").innerHTML = CHIPS.map(function (c, i) { return '<button type="button" class="chip" data-i="' + i + '" aria-pressed="false">' + esc(c[2]) + "</button>"; }).join("");
function syncChips() { document.querySelectorAll(".chip").forEach(function (b) { var c = CHIPS[b.dataset.i]; b.setAttribute("aria-pressed", S.f[c[0]][c[1]] ? "true" : "false"); }); }
function tog(g, k) { if (S.f[g][k]) delete S.f[g][k]; else S.f[g][k] = 1; }
$("#chips").addEventListener("click", function (e) { var b = e.target.closest(".chip"); if (!b) return; var c = CHIPS[b.dataset.i]; tog(c[0], c[1]); refresh(false); if (!$("#fpanel").hidden) renderFilters(); });

/* ---- search: name, town, county, waterbody; grouped suggestions; combobox keyboard ---- */
var ICON = { ramp: '<svg viewBox="0 0 20 20"><path d="M3 15h14M5 15l9-7v7"/></svg>', town: '<svg viewBox="0 0 20 20"><path d="M10 17s5-4.6 5-8.5a5 5 0 0 0-10 0C5 12.4 10 17 10 17z"/><circle cx="10" cy="8.5" r="1.8"/></svg>', county: '<svg viewBox="0 0 20 20"><path d="M3 5l4-1.5 6 2 4-1.5v10l-4 1.5-6-2-4 1.5z"/></svg>', water: '<svg viewBox="0 0 20 20"><path d="M2 8c2-2 3-2 5 0s3 2 5 0 3-2 6 0M2 13c2-2 3-2 5 0s3 2 5 0 3-2 6 0"/></svg>' };
function hl(t, q) { var i = t.toLowerCase().indexOf(q); return i < 0 || !q ? esc(t) : esc(t.slice(0, i)) + "<mark>" + esc(t.slice(i, i + q.length)) + "</mark>" + esc(t.slice(i + q.length)); }
var SUG = [], act = -1;
function suggest(raw) {
  var q = norm(raw), lq = raw.trim().toLowerCase(), box = $("#sugg"); SUG = []; act = -1;
  if (q.length < 2) return closeSugg();
  var rs = [], tw = {}, co = {}, wa = {};
  D.forEach(function (r) {
    if (r._n.indexOf(q) > -1) rs.push(r);
    if (r._ci.indexOf(q) > -1) tw[townKey(r)] = (tw[townKey(r)] || 0) + 1;
    if (r._co.indexOf(q) > -1 || (r._co + " county").indexOf(q) > -1) co[r.co] = (co[r.co] || 0) + 1;
    if (r._w.indexOf(q) > -1) wa[r.w] = (wa[r.w] || 0) + 1;
  });
  function starts(s) { return norm(s).indexOf(q) === 0 ? 0 : 1; }
  function top(o, n) { return Object.keys(o).sort(function (a, b) { return starts(a) - starts(b) || o[b] - o[a] || a.localeCompare(b); }).slice(0, n); }
  rs.sort(function (a, b) { return starts(a.n) - starts(b.n) || a.n.localeCompare(b.n); });
  rs.slice(0, 4).forEach(function (r) { SUG.push({ g: "Ramps", k: "ramp", v: r.id, h: hl(r.n, lq) + "<small>" + esc(r.ci + ", " + r.co + " Co.") + (r.pr === "none" ? " · address only" : r.pr === "approx" ? " · approximate location" : "") + "</small>", e: r.tyl }); });
  top(tw, 3).forEach(function (k) { var p = k.split("|"); SUG.push({ g: "Towns", k: "town", v: k, h: hl(p[0], lq) + "<small>" + esc(p[1] + " Co.") + "</small>", e: tw[k] + (tw[k] === 1 ? " ramp" : " ramps") }); });
  top(co, 2).forEach(function (k) { SUG.push({ g: "Counties", k: "county", v: k, h: hl(k + " County", lq), e: co[k] + (co[k] === 1 ? " ramp" : " ramps") }); });
  top(wa, 3).forEach(function (k) { SUG.push({ g: "Waterbodies", k: "water", v: k, h: hl(k, lq), e: wa[k] + (wa[k] === 1 ? " ramp" : " ramps") }); });
  var h = "", g = "";
  SUG.forEach(function (s, i) { if (s.g !== g) { g = s.g; h += '<div class="gh" role="presentation">' + g + "</div>"; } h += '<div class="sg" role="option" id="sg-' + i + '" data-i="' + i + '" aria-selected="false"><i>' + ICON[s.k] + "</i><span>" + s.h + "</span><em>" + esc(s.e) + "</em></div>"; });
  box.innerHTML = h || '<p class="empty" role="presentation">No ramp, town, county or waterbody matches “' + esc(raw.trim()) + '”.</p>';
  box.hidden = false; $("#q").setAttribute("aria-expanded", "true"); $("#q").removeAttribute("aria-activedescendant");
}
function closeSugg() { $("#sugg").hidden = true; $("#q").setAttribute("aria-expanded", "false"); $("#q").removeAttribute("aria-activedescendant"); act = -1; }
function setAct(i) {
  if (!SUG.length) return; act = (i + SUG.length) % SUG.length;
  document.querySelectorAll("#sugg .sg").forEach(function (el) { el.setAttribute("aria-selected", String(+el.dataset.i === act)); });
  var el = document.getElementById("sg-" + act); $("#q").setAttribute("aria-activedescendant", "sg-" + act); if (el) el.scrollIntoView({ block: "nearest" });
}
function choose(i) {
  var s = SUG[i]; if (!s) return; S.scope = { k: s.k, v: s.v }; S.q = scopeLabel(S.scope); $("#q").value = S.q; closeSugg(); refresh(true);
  if (s.k === "ramp") select(s.v, true);
}
$("#q").addEventListener("input", function (e) { S.q = e.target.value; S.scope = null; suggest(S.q); refresh(false); });
$("#q").addEventListener("keydown", function (e) {
  var open = !$("#sugg").hidden;
  if (e.key === "ArrowDown") { e.preventDefault(); if (!open) suggest(S.q); setAct(act + 1); }
  else if (e.key === "ArrowUp") { e.preventDefault(); if (open) setAct(act - 1); }
  else if (e.key === "Enter") { e.preventDefault(); if (open && act > -1) choose(act); else { closeSugg(); refresh(true); } }
  else if (e.key === "Escape") { if (open) { e.stopPropagation(); closeSugg(); } }
});
$("#sugg").addEventListener("mousedown", function (e) { e.preventDefault(); });
$("#sugg").addEventListener("click", function (e) { var b = e.target.closest(".sg"); if (b) choose(+b.dataset.i); });
$("#q").addEventListener("blur", function () { setTimeout(closeSugg, 120); });

/* ---- ramp card: status first, full official text, actions always reachable ---- */
function isApple() { var ua = navigator.userAgent || ""; return /iPhone|iPad|iPod/.test(ua) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1); }
function destination(r) { return r.pr === "exact" ? r.la + "," + r.lo : r.ad; }
function directionsURL(r) {
  var d = encodeURIComponent(destination(r));
  return isApple() ? "https://maps.apple.com/?daddr=" + d : "https://www.google.com/maps/dir/?api=1&destination=" + d;
}
function select(id, fromList) {
  var r = byId[id]; if (!r) return; S.sel = id; var pn = $("#panel"), h = [];
  h.push('<button type="button" class="x" id="px" aria-label="Close ramp card">×</button><h2 id="ph">' + esc(r.n) + '</h2><p class="where">' + esc(where(r)) + '</p><div class="badges">' + badges(r) + "</div>");
  h.push('<div class="pscroll">');
  var sd = r.st === "listed_open" ? "Listed as open in the recorded official data. This is not a live check." : r.sd;
  h.push('<div class="stat s-' + r.st + '"><h3>Recorded status</h3><b>' + esc(r.stf || r.stl) + ".</b> " + esc(sd) + "<small>" + (r.sa ? "As of " + esc(r.sa) + ". " : "") + (r.ss ? "Source: " + esc(r.ss) + ". " : "") + "Check with the owner before you tow.</small></div>");
  if (r.ty === "limited") h.push('<div class="note"><h3>Limited access</h3>' + esc(r.rx) + "</div>");
  else if (r.ty === "needs_review") h.push('<div class="note"><h3>Needs review</h3>' + esc(NEEDS_REVIEW_NOTE) + " " + esc(r.rx) + "</div>");
  else if (r.rx) h.push('<div class="note"><h3>Restriction</h3>' + esc(r.rx) + "</div>");
  if (r.pr === "approx") h.push('<div class="note apx-note"><h3>≈ Approximate location</h3>This pin is the owner’s published access-area point (' + esc(r.cs) + "), not the ramp itself. Directions use the street address.</div>");
  if (r.pr === "none") h.push('<div class="note apx-note"><h3>Address only</h3>No verified map location is published, so this site has no pin. Directions use the street address.</div>');
  if (NEAR && r.d != null) h.push('<p class="dist">' + fmtD(r, r.d) + " straight-line from you, not driving distance.</p>");
  var f = [];
  if (typeof r.ln === "number") f.push(r.ln + (r.ln === 1 ? " lane" : " lanes"));
  if (typeof r.tp === "number" && r.tp > 0) f.push(r.tp + " trailer spaces");
  if (r.ada.length) f.push("ADA features listed: " + r.ada.join(", "));
  if (r.rr) f.push("Restrooms listed"); if (r.lt) f.push("Lighting listed"); if (r.dk) f.push("Boarding docks listed");
  f.push(FEE_CARD[r.fee]);
  h.push('<p class="facts">' + f.map(function (x) { return "<span>" + esc(x) + "</span>"; }).join("") + "</p></div>");
  var dest = r.pr === "exact" ? "this ramp’s official coordinates" : "the street address";
  h.push('<div class="acts-wrap"><div class="acts"><a class="btn pri" id="pdir" href="' + esc(directionsURL(r)) + '" target="_blank" rel="noopener noreferrer"><svg viewBox="0 0 20 20" aria-hidden="true"><path d="M3 10l14-6-6 14-2-6z"/></svg>Directions</a><a class="btn" href="' + esc(DIRECTORY + "/" + r.id) + '"><svg viewBox="0 0 20 20" aria-hidden="true"><path d="M4 10h12M11 5l5 5-5 5"/></svg>Details</a></div>');
  h.push('<p class="hint">Opens ' + (isApple() ? "Apple Maps" : "Google Maps") + " with " + dest + " as the destination only. Your location is not sent by this page.</p></div>");
  pn.innerHTML = h.join(""); pn.hidden = false; $("#pre").hidden = true; $(".dock").classList.add("hasp"); BODY.classList.add("card-open");
  var acts = pn.querySelector(".acts-wrap"); acts.className = "acts-wrap"; pn.appendChild(acts);
  $("#px").addEventListener("click", closeCard);
  if (S.view === "list" && !wide()) setView("map");
  if (r.pr !== "none") {
    if (fromList || !map.getBounds().contains([r.la, r.lo])) map.setView([r.la, r.lo], Math.max(map.getZoom(), 11), { animate: false });
    if (!wide()) map.panBy([0, Math.round(pn.offsetHeight / 2 - 30)], { animate: false });
  }
  $("#px").focus({ preventScroll: true });
  renderMarkers(); renderList();
}
function closeCard() { S.sel = null; $("#panel").hidden = true; $(".dock").classList.remove("hasp"); BODY.classList.remove("card-open"); renderMarkers(); renderList(); }

/* ---- Near Me: asks only after an explicit tap; position kept in memory only ---- */
var PRE = { h: $("#pre-h").textContent, p: $("#pre-p").innerHTML };
function openPre() {
  $("#pre-h").textContent = PRE.h; $("#pre-p").innerHTML = PRE.p; $("#pre-p").classList.remove("err"); $("#pre-go").textContent = "Use my location"; $("#pre-no").textContent = "Not now";
  $("#panel").hidden = true; $(".dock").classList.remove("hasp"); BODY.classList.remove("card-open"); $("#pre").hidden = false; $("#pre-go").focus();
}
$("#near").addEventListener("click", openPre);
$("#pre-no").addEventListener("click", function () { var search = $("#pre-no").dataset.search === "1"; $("#pre").hidden = true; $("#pre-no").dataset.search = ""; if (search) $("#q").focus(); else $("#near").focus(); });
$("#pre-go").addEventListener("click", function () {
  if (!("geolocation" in navigator)) return failNear({ code: 2 });
  $("#pre-go").textContent = "Finding you…";
  navigator.geolocation.getCurrentPosition(function (p) { setNear({ lat: p.coords.latitude, lon: p.coords.longitude }); }, failNear, { enableHighAccuracy: false, timeout: 10000, maximumAge: 30000 });
});
function failNear(e) {
  var code = e && e.code, msg = code === 1 ? "Location permission was not given. That is fine."
    : code === 3 ? "Finding your location took too long." : "Your device could not provide a location right now.";
  $("#pre-h").textContent = "Couldn’t use your location";
  $("#pre-p").textContent = msg + " Nothing was stored or sent. You can search a town, county or waterbody instead."; $("#pre-p").classList.add("err");
  $("#pre-go").textContent = "Try again"; $("#pre-no").textContent = "Search instead"; $("#pre-no").dataset.search = "1";
}
function setNear(pos) {
  NEAR = pos; $("#pre").hidden = true; closeCard(); setView("near"); youLayer.clearLayers();
  L.marker([pos.lat, pos.lon], { interactive: false, keyboard: false, icon: L.divIcon({ className: "", iconSize: [22, 22], html: '<div class="me" role="img" aria-label="Your position"></div>' }) }).addTo(youLayer);
  refresh(false);
  var top = results().filter(function (r) { return r.pr !== "none"; }).slice(0, 5);
  setTimeout(function () { map.fitBounds(L.latLngBounds(top.map(function (r) { return [r.la, r.lo]; }).concat([[pos.lat, pos.lon]])), { paddingTopLeft: [40, 56], paddingBottomRight: [40, 34], maxZoom: 11, animate: !reduce }); }, 0);
  $("#live").textContent = "Sorted nearest first by straight-line distance.";
}
function exitNear() { NEAR = null; youLayer.clearLayers(); setView("map"); refresh(false); }
$("#nearoff").addEventListener("click", exitNear);
addEventListener("pagehide", function () { NEAR = null; });

/* ---- views ---- */
function setView(v) {
  S.view = v; $("#shell").dataset.view = v; $("#vmap").setAttribute("aria-pressed", String(v !== "list")); $("#vlist").setAttribute("aria-pressed", String(v === "list"));
  setTimeout(function () { map.invalidateSize(); renderMarkers(); }, 0); renderList();
}
$("#vmap").addEventListener("click", function () { setView(NEAR ? "near" : "map"); });
$("#vlist").addEventListener("click", function () { setView("list"); });
$(".skip").addEventListener("click", function () { if (!wide()) setView("list"); setTimeout(function () { $("#list").focus(); }, 0); });

/* ---- filters sheet ---- */
function opt(g, k, label, inner, sub) { return '<button type="button" class="opt" data-g="' + g + '" data-k="' + k + '" aria-pressed="' + (S.f[g][k] ? "true" : "false") + '">' + (inner || "") + '<span class="box" aria-hidden="true">✓</span>' + esc(label) + (sub != null ? " <small>" + sub + "</small>" : "") + "</button>"; }
function cnt(g, fn) { return D.filter(function (r) { return pass(r, g) && matchQ(r) && fn(r); }).length; }
function renderFilters() {
  var h = '<div class="fh2"><h2>Filters</h2><button type="button" id="freset">Reset</button></div><div class="fbody">';
  h += '<div class="fg"><h3>Access type</h3><div class="opts">' + Object.keys(TYL).map(function (k) { return opt("ty", k, TYL[k], badgeInline("ty", k), cnt("ty", function (r) { return r.ty === k; })); }).join("") + "</div></div>";
  h += '<div class="fg"><h3>Listed status <small>recorded, not a live check</small></h3><div class="opts">' + Object.keys(STL).map(function (k) { return opt("st", k, STL[k], '<span style="width:20px;height:20px;display:inline-grid;place-items:center;flex:none;overflow:hidden;border-radius:50%">' + badgeInline("st", k) + "</span>", cnt("st", function (r) { return r.st === k; })); }).join("") + "</div></div>";
  h += '<div class="fg"><h3>Facilities <small>sites must list every one selected; “not stated” is not “none”</small></h3><div class="opts">' + Object.keys(FAC).map(function (k) { return opt("fac", k, FAC[k][0], "", cnt("fac", FAC[k][1])); }).join("") + "</div></div>";
  h += '<div class="fg"><h3>Fees</h3><div class="opts">' + Object.keys(FEE).filter(function (k) { return D.some(function (r) { return r.fee === k; }); }).map(function (k) { return opt("fee", k, FEE[k], "", cnt("fee", function (r) { return r.fee === k; })); }).join("") + "</div></div></div>";
  var n = results().length;
  h += '<div class="ffoot"><button type="button" class="btn pri" id="fgo">Show ' + n + (n === 1 ? " ramp" : " ramps") + "</button></div>";
  $("#fpanel").innerHTML = h;
}
function openFilters(o) { var p = $("#fpanel"); if (o) renderFilters(); p.hidden = !o; $("#shell").classList.toggle("fo", o); $("#fbtn").setAttribute("aria-expanded", String(o)); if (o) p.querySelector(".opt").focus(); else $("#fbtn").focus(); }
$("#fbtn").addEventListener("click", function () { openFilters($("#fpanel").hidden); });
$("#fpanel").addEventListener("click", function (e) {
  if (e.target.closest("#fgo")) return openFilters(false);
  if (e.target.id === "freset") { S.f = { ty: {}, st: {}, fac: {}, fee: {} }; refresh(false); renderFilters(); $("#freset").focus(); return; }
  var b = e.target.closest(".opt[data-g]"); if (!b) return; tog(b.dataset.g, b.dataset.k); refresh(false); renderFilters();
  var n = $("#fpanel").querySelector('[data-g="' + b.dataset.g + '"][data-k="' + b.dataset.k + '"]'); if (n) n.focus();
});

/* ---- legend: compact by default, expands on tap ---- */
$("#ktog").addEventListener("click", function () { var o = $("#ktog").getAttribute("aria-expanded") !== "true"; $("#ktog").setAttribute("aria-expanded", String(o)); $("#kbody").hidden = !o; });

/* ---- Escape closes the top-most layer ---- */
document.addEventListener("keydown", function (e) {
  if (e.key !== "Escape") return;
  if (!$("#fpanel").hidden) return openFilters(false);
  if (!$("#pre").hidden) { $("#pre").hidden = true; return $("#near").focus(); }
  if (S.sel) closeCard();
});

/* ---- theme: Auto follows the device; same preference key as the rest of the site ---- */
var MQ = matchMedia("(prefers-color-scheme: dark)"), PREF = "auto";
try { var qt = /[?&]theme=(light|dark)\b/.exec(location.search); PREF = qt ? qt[1] : (localStorage.getItem("coastalBrief.theme") || "auto"); } catch (e) {}
function applyTheme() {
  var t = PREF === "auto" ? (MQ.matches ? "dark" : "light") : PREF;
  document.documentElement.classList.toggle("dark", t === "dark");
  document.querySelectorAll(".theme button").forEach(function (b) { b.setAttribute("aria-pressed", String(b.dataset.t === PREF)); });
  coast.restyle({ land: css("--coast-land"), line: css("--coast-line") }); restyleGeo(); renderMarkers();
}
document.querySelector(".theme").addEventListener("click", function (e) {
  var b = e.target.closest("button"); if (!b) return; PREF = b.dataset.t;
  try { if (PREF === "auto") localStorage.removeItem("coastalBrief.theme"); else localStorage.setItem("coastalBrief.theme", PREF); } catch (x) {}
  applyTheme();
});
(MQ.addEventListener ? MQ.addEventListener.bind(MQ, "change") : MQ.addListener.bind(MQ))(function () { if (PREF === "auto") applyTheme(); });
applyTheme();

/* ---- data and geography: our own files, fetched after first paint ---- */
function load() {
  fetch(BASE + ".json", { credentials: "same-origin" }).then(function (res) { if (!res.ok) throw new Error(res.status); return res.json(); }).then(function (doc) {
    META = doc.meta; D = doc.records;
    D.forEach(function (r) { byId[r.id] = r; r._n = norm(r.n); r._ci = norm(r.ci); r._co = norm(r.co); r._w = norm(r.w); r._hay = RS.haystack(RS.parts(r.n, r.al, r.ci, r.co, r.w, r.a)); });
    $("#cnt").innerHTML = META.pins + " of " + META.total + " sites on the map (" + META.approx + " approximate). " + META.address_only + " have no verified map location and are in the list only. Recorded data, checked " + esc(META.checked) + ".";
    readURL(); if (S.scope) $("#q").value = scopeLabel(S.scope); else if (S.q) $("#q").value = S.q;
    refresh(!!(S.scope || S.q)); BODY.dataset.ready = "1";
    return fetch(BASE + "/geo-lo.json", { credentials: "same-origin" }).then(function (r) { return r.json(); }).then(function (g) { GEO.lo = g; makeLabels(g); geoFor(); BODY.dataset.geo = "1"; });
  }).catch(function () { $("#cnt").textContent = "The ramp data could not be loaded. The full directory still lists every site."; $("#sum").textContent = "The ramp data could not be loaded."; });
}
if (document.readyState === "complete") setTimeout(load, 0); else addEventListener("load", function () { setTimeout(load, 0); });
window.__rf = { map: map, home: home, data: function () { return D; }, clusters: clusters, select: select, results: results, state: function () { return JSON.parse(JSON.stringify(S)); }, nearActive: function () { return NEAR !== null; }, geo: function () { return GEO; } };
})();
