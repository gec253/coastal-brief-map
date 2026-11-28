/* Ramp Finder Phase 2 statewide map (steps 1-2 of the approved plan, Ed t556u).
   Vendored Leaflet + the Wind map's Census coastline; marker artwork from Summer's approved proposal.
   Reads only our own data file. No visitor location is requested, stored or sent on this page. */
(function () {
"use strict";
var $ = function (s) { return document.querySelector(s); };
var BODY = document.body, BASE = BODY.dataset.base, DIRECTORY = BODY.dataset.directory;
var NEEDS_REVIEW_NOTE = "Needs review: the official sources we checked do not confirm what kind of launch this is.";
function esc(s) { return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
function isUnc(st) { return st === "conflicting" || st === "not_stated"; }

/* ---- marker artwork (Summer's approved proposal): shape = access type, badge = status, never colour alone ---- */
/* ---- marker artwork: shape = type, badge = status (never colour alone) ---- */
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

/* ---- map: vendored Leaflet, Census coastline drawn in the page palette, no tiles ---- */
var reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
var map = L.map("map", { zoomControl: false, zoomSnap: 0.25, zoomDelta: 0.5, minZoom: 5.5, maxZoom: 16, worldCopyJump: false,
  zoomAnimation: !reduce, fadeAnimation: !reduce, markerZoomAnimation: !reduce });
L.control.zoom({ position: "topright" }).addTo(map);
var NC = [[33.8, -84.4], [36.65, -75.3]];
var WIDE = matchMedia("(min-width:900px)").matches;
function home() { if (WIDE) map.fitBounds(NC, { animate: false, padding: [4, 4] }); else map.setView([35.25, -79.3], 6.5, { animate: false }); }
home();
map.attributionControl.setPrefix("Leaflet");
map.attributionControl.addAttribution("Basemap: U.S. Census Bureau coastline (illustration, not for navigation)");
function css(v) { return getComputedStyle(document.documentElement).getPropertyValue(v).trim(); }
var coast = CBCoast.layer({ base: "/wind/coast-", land: css("--coast-land"), line: css("--coast-line"), lineWidth: 1 }).addTo(map);
var LABELS = [["Raleigh", 35.78, -78.64, 6, 1], ["Charlotte", 35.23, -80.84, 6, 1], ["Asheville", 35.6, -82.55, 6, 1], ["Wilmington", 34.2, -77.9, 6, 1], ["Greensboro", 36.07, -79.79, 7, 0], ["Greenville", 35.61, -77.37, 8, 0], ["New Bern", 35.11, -77.04, 8.5, 0], ["Morehead City", 34.735, -76.78, 9, 0], ["Nags Head", 35.96, -75.62, 8.5, 0], ["Fayetteville", 35.05, -78.88, 7.5, 0], ["Durham", 35.99, -78.9, 8.5, 0], ["Elizabeth City", 36.3, -76.25, 8, 0], ["Cape Hatteras", 35.25, -75.53, 8, 0], ["Atlantic Ocean", 33.95, -75.7, 6, 2], ["Pamlico Sound", 35.35, -75.95, 8, 2]];
var labelMk = LABELS.map(function (l) { return { z: l[3], m: L.marker([l[1], l[2]], { interactive: false, keyboard: false, icon: L.divIcon({ className: "", html: '<span class="lb' + (l[4] === 2 ? " sm" : l[4] ? " big" : "") + '">' + l[0] + "</span>", iconSize: [0, 0] }) }) }; });
function syncLabels() { var z = map.getZoom(); labelMk.forEach(function (o) { var show = z >= o.z; if (show && !map.hasLayer(o.m)) o.m.addTo(map); if (!show && map.hasLayer(o.m)) map.removeLayer(o.m); }); }
var mlayer = L.layerGroup().addTo(map);

var D = [], byId = {}, META = null, sel = null;

/* ---- greedy pixel-radius clustering (no library). Markers sit on their seed point, and every seed is
   at least R px from every other seed, so no two 44 px targets overlap. At the maximum zoom every ramp is its own pin. ---- */
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
  var z = map.getZoom(), b = map.getBounds().pad(0.25);
  var pts = D.filter(function (r) { return r.pr !== "none" && b.contains([r.la, r.lo]); });
  if (z >= map.getMaxZoom()) { pts.forEach(function (r) { addSingle(r); }); return; }
  clusters(pts, z).forEach(function (c) {
    if (c.m.length === 1) return addSingle(c.r);
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
function addSingle(r) {
  var isSel = sel === r.id;
  var title = r.n + ". " + r.tyl + ". " + r.stl + "." + (r.pr === "approx" ? " Approximate location." : "");
  var m = L.marker([r.la, r.lo], { keyboard: true, title: title, alt: title, zIndexOffset: isSel ? 900 : (r.st !== "listed_open" ? 300 : 0),
    icon: L.divIcon({ className: "", iconSize: [44, 44], iconAnchor: [22, 22], html: '<div class="mkw">' + pinSvg(r, isSel).replace("<svg ", '<svg width="32" height="32" ') + "</div>" }) });
  m.on("click", function () { select(r.id); }); m.addTo(mlayer);
}
map.on("moveend zoomend", function () { syncLabels(); schedule(); });

/* ---- info card: full official wording, never shortened ---- */
var FEE = { free_stated: "Free (stated by the owner)", fee_applies: "Fee applies", camping_only: "Camping fees apply; not a general day-use launch", not_stated: "Fee not stated" };
function where(r) { return [r.ci, r.co ? r.co + " Co." : "", r.w].filter(Boolean).join(" · "); }
function select(id) {
  var r = byId[id]; if (!r) return; sel = id; var pn = $("#panel"), h = [];
  h.push('<button type="button" class="x" id="px" aria-label="Close ramp card">×</button><h2>' + esc(r.n) + '</h2><p class="where">' + esc(where(r)) + "</p>");
  h.push('<div class="badges"><span class="badge t-' + r.ty + '">' + badgeInline("ty", r.ty) + esc(r.tyl) + '</span><span class="badge s-' + r.st + '">' + badgeInline("st", r.st) + esc(r.stl) + "</span></div>");
  if (r.pr === "approx") h.push('<p class="note apx-note"><b>≈ Approximate location.</b> This pin is the owner’s published access-area point (' + esc(r.cs) + "), not the ramp itself.</p>");
  if (r.ty === "limited") h.push('<p class="note"><b>Limited access.</b> ' + esc(r.rx) + "</p>");
  else if (r.ty === "needs_review") h.push('<p class="note"><b>' + esc(NEEDS_REVIEW_NOTE) + "</b> " + esc(r.rx) + "</p>");
  else if (r.rx) h.push('<p class="note"><b>Restriction.</b> ' + esc(r.rx) + "</p>");
  var sd = r.st === "listed_open" ? "Listed as open in the recorded official data. This is not a live check." : r.sd;
  h.push('<p class="sd"><b>' + esc(r.stf || r.stl) + ".</b> " + esc(sd) + "<small>Recorded status" + (r.sa ? ", as of " + esc(r.sa) : "") + (r.ss ? ". Source: " + esc(r.ss) : "") + ". Check with the owner before you tow.</small></p>");
  var f = [];
  if (typeof r.ln === "number") f.push(r.ln + (r.ln === 1 ? " lane" : " lanes"));
  if (typeof r.tp === "number" && r.tp > 0) f.push(r.tp + " trailer spaces");
  if (r.ada.length) f.push("ADA features listed: " + r.ada.join(", "));
  if (r.rr) f.push("Restrooms listed"); if (r.lt) f.push("Lighting listed"); if (r.dk) f.push("Boarding docks listed");
  f.push(FEE[r.fee]);
  h.push('<p class="facts">' + f.map(function (x) { return "<span>" + esc(x) + "</span>"; }).join("") + "</p>");
  pn.innerHTML = h.join(""); pn.hidden = false; $(".dock").classList.add("hasp"); BODY.classList.add("card-open");
  $("#px").addEventListener("click", closeCard); $("#px").focus({ preventScroll: true });
  if (!matchMedia("(min-width:900px)").matches) map.panBy([0, Math.round(pn.offsetHeight / 2 - 30)], { animate: false });
  renderMarkers();
}
function closeCard() { sel = null; $("#panel").hidden = true; $(".dock").classList.remove("hasp"); BODY.classList.remove("card-open"); renderMarkers(); }
document.addEventListener("keydown", function (e) { if (e.key === "Escape" && sel) closeCard(); });

/* ---- theme: same preference key as the rest of the site ---- */
function theme(t, save) {
  document.documentElement.classList.toggle("dark", t === "dark");
  document.querySelectorAll(".theme button").forEach(function (b) { b.setAttribute("aria-pressed", String(b.dataset.t === t)); });
  if (save) { try { localStorage.setItem("coastalBrief.theme", t); } catch (e) {} }
  coast.restyle({ land: css("--coast-land"), line: css("--coast-line") }); renderMarkers();
}
document.querySelector(".theme").addEventListener("click", function (e) { var b = e.target.closest("button"); if (b) theme(b.dataset.t, true); });
theme(document.documentElement.classList.contains("dark") ? "dark" : "light", false);
syncLabels();

/* ---- data: our own file, fetched after first paint ---- */
function load() {
  fetch(BASE + ".json", { credentials: "same-origin" }).then(function (res) { if (!res.ok) throw new Error(res.status); return res.json(); }).then(function (doc) {
    META = doc.meta; D = doc.records; D.forEach(function (r) { byId[r.id] = r; });
    $("#cnt").innerHTML = META.pins + " of " + META.total + " sites on the map (" + META.approx + " approximate). " + META.address_only +
      ' have no verified map location; see the <a href="' + esc(DIRECTORY) + '">full directory</a>. Recorded data, checked ' + esc(META.checked) + ".";
    renderMarkers(); BODY.dataset.ready = "1";
  }).catch(function () { $("#cnt").textContent = "The ramp data could not be loaded. The full directory still lists every site."; });
}
if (document.readyState === "complete") setTimeout(load, 0); else addEventListener("load", function () { setTimeout(load, 0); });
window.__rf = { map: map, home: home, data: function () { return D; }, clusters: clusters, select: select, theme: theme };
})();
