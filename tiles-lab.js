/* Tile design prototype. Reads the site's own APIs; nothing here is used by public pages. */
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const tf = new Intl.DateTimeFormat("en-US", { timeZone: "America/New_York", hour: "numeric", minute: "2-digit" });
  const df = new Intl.DateTimeFormat("en-US", { timeZone: "America/New_York", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
  const t12 = (t) => tf.format(new Date(t)) + " ET", dt = (t) => df.format(new Date(t)) + " ET";
  const DIRS = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"];
  const DEG = Object.fromEntries(DIRS.map((d, i) => [d, i * 22.5]));

  // theme toggle shared with the site
  const tb = $("theme");
  function label() { tb.textContent = document.documentElement.getAttribute("data-theme") === "dark" ? "Light mode" : "Dark mode"; }
  tb.addEventListener("click", function () { const n = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark"; document.documentElement.setAttribute("data-theme", n); try { localStorage.setItem("coastalBrief.theme", n); } catch (e) {} label(); });
  label();

  const chip = (k) => k === "both" ? '<span><span class="chip fc">Predicted</span> <span class="chip">Observed</span></span>' : k === "sample" ? '<span class="chip sample">Sample</span>' : k === "forecast" || k === "predicted" ? '<span class="chip fc">' + (k === "predicted" ? "Predicted" : "Forecast") + "</span>" : '<span class="chip">Observed</span>';
  const head = (name, kind) => '<div class="t-h"><span class="t-name">' + name + "</span>" + chip(kind) + "</div>";
  const foot = (src, when, url) => '<div class="t-f"><span>' + (url ? '<a href="' + esc(url) + '" target="_blank" rel="noopener">' + esc(src) + "</a>" : esc(src)) + "</span><span>" + esc(when) + "</span></div>";

  /* -------- instruments -------- */
  function compass(fromDeg) {
    let tk = "";
    for (let a = 0; a < 360; a += 10) {
      const m = a % 90 === 0, r1 = m ? 47 : 51, r = (a - 90) * Math.PI / 180;
      tk += '<line class="tk' + (m ? " m" : "") + '" x1="' + (64 + r1 * Math.cos(r)).toFixed(1) + '" y1="' + (64 + r1 * Math.sin(r)).toFixed(1) + '" x2="' + (64 + 56 * Math.cos(r)).toFixed(1) + '" y2="' + (64 + 56 * Math.sin(r)).toFixed(1) + '"/>';
    }
    const has = fromDeg != null;
    return '<svg class="compass" viewBox="0 0 128 128" role="img" aria-label="' + (has ? "Wind from " + Math.round(fromDeg) + " degrees" : "Wind direction unavailable") + '">' +
      '<circle class="ring" cx="64" cy="64" r="60"/><circle class="ring" cx="64" cy="64" r="40" stroke-dasharray="1 3"/>' + tk +
      '<text x="64" y="25">N</text><text x="103" y="64">E</text><text x="64" y="103">S</text><text x="25" y="64">W</text>' +
      (has ? '<g class="needle" style="transform:rotate(' + fromDeg + 'deg)"><path d="M64 4 l7 12 h-14z" fill="var(--tAcc)"/><line x1="64" y1="18" x2="64" y2="100" stroke="var(--tAcc)" stroke-width="2.2" stroke-linecap="round"/><path d="M64 112 l-6-12 h12z" fill="var(--tAcc)" opacity=".55"/></g><circle cx="64" cy="64" r="3.5" fill="var(--tInk)"/>' : "") +
      "</svg>";
  }
  function swellWave(hFt, periodS) {
    // Deep-water wavelength from period (L = gT²/2π ≈ 1.56 T² m); the drawing spans 400 m of sea surface.
    if (!(hFt > 0 && periodS > 0)) return '<svg class="wave" viewBox="0 0 300 58" aria-hidden="true"></svg>';
    const L = 1.56 * periodS * periodS, span = 400, amp = Math.max(1.5, Math.min(22, hFt / 10 * 22));
    let d = "M0 " + (29 - amp * Math.sin(0)).toFixed(1);
    for (let x = 2; x <= 300; x += 2) d += " L" + x + " " + (29 - amp * Math.sin(2 * Math.PI * (x / 300 * span) / L)).toFixed(1);
    return '<svg class="wave" viewBox="0 0 300 58" preserveAspectRatio="none" role="img" aria-label="Swell profile drawn from height and period"><path d="' + d + ' L300 58 L0 58Z" fill="var(--tAcc)" opacity=".10"/><path d="' + d + '" fill="none" stroke="var(--tAcc)" stroke-width="1.8" vector-effect="non-scaling-stroke"/><line x1="0" y1="29" x2="300" y2="29" stroke="currentColor" stroke-opacity=".18" stroke-dasharray="2 4" vector-effect="non-scaling-stroke"/></svg>';
  }
  function seaMeter(hFt) {
    const max = 12, y = (v) => 120 - v / max * 112;
    let s = '<svg class="meter" viewBox="0 0 30 128" role="img" aria-label="Sea height on a 0 to 12 foot scale">';
    s += '<rect x="9" y="8" width="12" height="112" rx="6" fill="currentColor" fill-opacity=".08" stroke="currentColor" stroke-opacity=".2"/>';
    if (hFt != null) s += '<rect x="9" y="' + y(Math.min(hFt, max)).toFixed(1) + '" width="12" height="' + (120 - y(Math.min(hFt, max))).toFixed(1) + '" rx="6" fill="var(--tAcc)" opacity=".85"/>';
    for (let v = 0; v <= max; v += 2) s += '<line x1="23" x2="' + (v % 4 ? 26 : 29) + '" y1="' + y(v) + '" y2="' + y(v) + '" stroke="currentColor" stroke-opacity=".45"/>';
    return s + "</svg>";
  }
  function chop(periodS) {
    const L = Math.max(10, (periodS || 5) * 5);
    let d = "M0 40";
    for (let x = 0; x < 300; x += L) d += " q" + (L / 2) + " -" + (12 + (x / L % 2) * 4) + " " + L + " 0";
    return '<svg class="wave" viewBox="0 0 300 58" preserveAspectRatio="none" aria-hidden="true"><path d="' + d + '" fill="none" stroke="var(--tAcc)" stroke-width="1.6" vector-effect="non-scaling-stroke"/><path d="' + d.replace("M0 40", "M" + (-L / 2) + " 50") + '" fill="none" stroke="var(--tAcc)" stroke-opacity=".4" stroke-width="1.2" vector-effect="non-scaling-stroke"/></svg>';
  }

  /* -------- skeletons reserve final layout before data -------- */
  function skel(id, cls, name) { $(id).innerHTML = head(name, "observed") + '<div class="t-body"><div><div class="big">—</div><div class="line2">&nbsp;</div><div class="desc">&nbsp;</div></div></div>' + foot("Loading…", ""); }
  skel("t-wind", "wind", "Wind"); skel("t-swell", "swell", "Swell"); skel("t-seas", "seas", "Seas"); skel("t-tide", "tide", "Tide"); skel("t-temp", "temp", "Water temp"); skel("t-fresh", "fresh", "Lake level");

  function renderWind(r) {
    const v = r.values || {};
    $("t-wind").innerHTML = head("Wind", r.kind) + '<div class="t-body"><div><div class="big">' + Math.round(v.speedKt) + "<small>kt</small></div>" +
      '<div class="line2">Gusts <b>' + Math.round(v.gustKt) + " kt</b></div>" +
      '<div class="line2">From <b>' + esc(v.dirCompass) + "</b> · " + Math.round(v.dirDeg) + "°</div>" +
      '<div class="desc">' + esc(r.station.name) + ", " + esc(r.station.network) + "</div></div>" + compass(v.dirDeg) + "</div>" +
      foot("NOAA NDBC " + r.station.id, t12(r.time), r.station.url);
  }
  function renderSwell(r) {
    const v = r.values || {};
    $("t-swell").innerHTML = head("Swell", r.kind) + '<div class="t-body" style="grid-template-columns:1fr"><div><div class="big">' + v.heightFt.toFixed(1) + "<small>ft</small></div>" +
      '<div class="stat3"><div>Period<b>' + v.periodS.toFixed(1) + "<small>s</small></b></div><div>From<b>" + esc(v.dirCompass) + "</b></div><div>Wavelength<b>≈" + Math.round(1.56 * v.periodS * v.periodS) + "<small>m</small></b></div></div>" +
      swellWave(v.heightFt, v.periodS) +
      '<div class="desc">Long-period energy split from the buoy\'s wave spectrum. Wavelength is a deep-water estimate from period.</div></div></div>' +
      foot("NDBC " + r.station.id + " spectrum", t12(r.time), r.dataUrl);
  }
  function renderSeas(r, sw) {
    const v = r.values || {}, st = sw && sw.values ? String(sw.values.steepness || "").replace(/_/g, " ").toLowerCase() : "";
    $("t-seas").innerHTML = head("Seas", r.kind) + '<div class="t-body"><div><div class="big">' + v.heightFt.toFixed(1) + "<small>ft</small></div>" +
      '<div class="line2">Every <b>' + v.dominantPeriodS.toFixed(0) + " s</b> · from <b>" + esc(v.meanDirCompass) + "</b></div>" +
      (st ? '<div class="line2">Steepness <b>' + esc(st) + "</b></div>" : "") +
      '<div class="desc">Significant height: wind waves and swell combined, ' + esc(r.station.name) + ".</div></div>" + seaMeter(v.heightFt) + "</div>" + chop(v.dominantPeriodS) +
      foot("NDBC " + r.station.id, t12(r.time), r.station.url);
  }
  function renderTide(t) {
    lastTide = t; rw = innerWidth;
    const now = Date.now();
    const day0 = new Date(new Date().toLocaleString("en-US", { timeZone: "America/New_York" })); day0.setHours(0, 0, 0, 0);
    const off = new Date().getTime() - new Date(new Date().toLocaleString("en-US", { timeZone: "America/New_York" })).getTime();
    const a = day0.getTime() + off, b = a + 86400000;
    const pts = (t.curve || []).filter((p) => p[0] >= a && p[0] <= b), obs = ((t.observed && t.observed.points) || []).filter((p) => p[0] >= a);
    const all = pts.concat(obs).map((p) => p[1]); const lo = Math.floor(Math.min.apply(null, all) - 0.3), hi = Math.ceil(Math.max.apply(null, all) + 0.3);
    const W = innerW("t-tide"), H = 150, X = (x) => 8 + (x - a) / (b - a) * (W - 16), Y = (v) => 18 + (hi - v) / (hi - lo) * (H - 40);
    const line = (arr) => arr.map((p, i) => (i ? "L" : "M") + X(p[0]).toFixed(1) + " " + Y(p[1]).toFixed(1)).join("");
    const ev = (t.events || []).filter((e) => e.t >= a && e.t <= b);
    let s = '<svg class="tidesvg" viewBox="0 0 ' + W + " " + H + '" role="img" aria-label="Predicted tide for today with observed water level">';
    s += '<defs><linearGradient id="tg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="var(--tAcc)" stop-opacity=".22"/><stop offset="1" stop-color="var(--tAcc)" stop-opacity="0"/></linearGradient></defs>';
    for (let h = 0; h <= 24; h += 6) s += '<line x1="' + X(a + h * 3600000) + '" x2="' + X(a + h * 3600000) + '" y1="12" y2="' + (H - 18) + '" stroke="currentColor" stroke-opacity=".1" vector-effect="non-scaling-stroke"/>';
    if (pts.length) s += '<path d="' + line(pts) + "L" + X(pts[pts.length - 1][0]) + " " + (H - 18) + "L" + X(pts[0][0]) + " " + (H - 18) + 'Z" fill="url(#tg)"/><path d="' + line(pts) + '" fill="none" stroke="var(--tAcc)" stroke-width="2" vector-effect="non-scaling-stroke"/>';
    if (obs.length) s += '<path d="' + line(obs) + '" fill="none" stroke="var(--tInk)" stroke-width="2.4" stroke-linecap="round" vector-effect="non-scaling-stroke"/>';
    if (now > a && now < b) s += '<line x1="' + X(now) + '" x2="' + X(now) + '" y1="10" y2="' + (H - 18) + '" stroke="var(--tInk)" stroke-opacity=".5" stroke-dasharray="3 3" vector-effect="non-scaling-stroke"/>';
    ["12a", "6a", "12p", "6p", ""].forEach((l, i) => { if (l) s += '<text x="' + (X(a + i * 6 * 3600000) + 3) + '" y="' + (H - 4) + '" opacity=".7">' + l + "</text>"; });
    s += "</svg>";
    const next = (t.events || []).find((e) => e.t > now), last = t.observed && t.observed.latest;
    const evRow = ev.map((e) => "<div>" + (e.type === "H" ? "High" : "Low") + "<b>" + tf.format(new Date(e.t)).replace(" ", "\u202f") + "</b>" + e.v.toFixed(1) + " ft</div>").join("");
    const rising = last && pts.length ? (function () { const p = pts.find((q) => q[0] > now); const q = pts.filter((r) => r[0] <= now).pop(); return p && q ? p[1] > q[1] : null; })() : null;
    $("t-tide").innerHTML = head("Tide · Beaufort", "both") + '<div class="t-body" style="grid-template-columns:1fr"><div>' +
      '<div class="big">' + (last ? last.v.toFixed(1) : "—") + "<small>ft MLLW</small></div>" +
      '<div class="line2">' + (rising == null ? "" : rising ? "<b>Rising</b>" : "<b>Falling</b>") + (next ? " · next " + (next.type === "H" ? "high" : "low") + " <b>" + t12(next.t) + "</b>, " + next.v.toFixed(1) + " ft" : "") + "</div>" +
      (last ? '<div class="desc">Observed ' + t12(last.t) + " (dark line, preliminary), " + (last.diff >= 0 ? last.diff.toFixed(1) + " ft above" : Math.abs(last.diff).toFixed(1) + " ft below") + " the prediction (shaded curve).</div>" : "") +
      s + '<div class="stat3" style="grid-template-columns:repeat(' + Math.max(1, ev.length) + ',1fr)">' + evRow + "</div></div></div>" +
      foot("NOAA CO-OPS " + t.station.id + " · predictions and observed", "Today, " + t.datum, t.sourceUrl);
  }
  function renderTemp(r, off) {
    const f = r.values.f, of = off && off.values ? off.values.f : null, pos = (v) => Math.max(0, Math.min(100, (v - 40) / 45 * 100));
    const el = $("t-temp"); el.style.setProperty("--wh", String(Math.round(205 - (Math.max(45, Math.min(80, f)) - 45) / 35 * 50)));
    el.innerHTML = head("Water temp", r.kind) + '<div class="t-body" style="grid-template-columns:1fr"><div><div class="big">' + f.toFixed(1) + "<small>°F</small></div>" +
      '<div class="line2">Inlet and harbor · <b>' + r.values.c.toFixed(1) + " °C</b></div>" +
      (of != null ? '<div class="line2">Offshore <b>' + of.toFixed(1) + " °F</b> · Onslow Bay buoy " + esc(off.station.id) + "</div>" : "") +
      '<div class="tbar" aria-hidden="true"><i style="left:' + pos(f) + '%"></i>' + (of != null ? '<i class="o" style="left:' + pos(of) + '%"></i>' : "") + '</div><div class="tscale"><span>40°</span><span>55°</span><span>70°</span><span>85°F</span></div>' +
      '<div class="desc">Bar: inlet reading; ring: offshore buoy (' + (of != null ? t12(off.time) : "n/a") + ").</div></div></div>" +
      foot("NOAA CO-OPS " + r.station.id, t12(r.time), r.station.url);
  }
  function renderFresh(d, sample) {
    lastFresh = [d, sample]; rw = innerWidth;
    const L = d.lake, e = L.elevation.value, g = L.guideCurveFt, lo = 240, hi = 256, W = innerW("t-fresh"), X = (v) => 10 + (v - lo) / (hi - lo) * (W - 20);
    let s = '<svg class="pool" viewBox="0 0 ' + W + ' 64" role="img" aria-label="Lake elevation ' + e.toFixed(2) + " feet against the " + g + ' foot guide curve">';
    s += '<rect x="10" y="20" width="' + (W - 20) + '" height="14" rx="7" fill="currentColor" fill-opacity=".08"/><rect x="10" y="20" width="' + (X(e) - 10).toFixed(1) + '" height="14" rx="7" fill="var(--tAcc)" opacity=".8"/>';
    s += '<line x1="' + X(g) + '" x2="' + X(g) + '" y1="12" y2="42" stroke="#9C7A58" stroke-width="2.5" stroke-dasharray="4 3" vector-effect="non-scaling-stroke"/>';
    for (let v = lo; v <= hi; v += 4) s += '<text x="' + X(v) + '" y="58" text-anchor="middle" opacity=".7">' + v + "</text>";
    s += '<text x="' + (X(g) + 6) + '" y="11">Guide ' + g + "</text></svg>";
    const rel = d.release && d.release.flowCfs, wt = d.waterTemp;
    const k = sample ? "sample" : "observed";
    $("t-fresh").innerHTML = head("Lake level · Falls Lake", k) + '<div class="t-body" style="grid-template-columns:1fr"><div>' +
      '<div class="big">' + e.toFixed(2) + '<small>ft</small></div><div class="line2"><b>' + Math.abs(L.vsGuideFt).toFixed(2) + " ft " + (L.vsGuideFt < 0 ? "below" : "above") + "</b> the " + g + " ft guide curve (target pool)</div>" + s +
      '<div class="stat3"><div>Dam release<b>' + (rel ? Math.round(rel.value) : "—") + "<small>cfs</small></b></div><div>Water temp<b>" + (wt && wt.f != null ? wt.f.toFixed(1) : "—") + "<small>°F</small></b></div><div>7-day change<b>" + (L.change7dFt != null ? (L.change7dFt > 0 ? "+" : "−") + Math.abs(L.change7dFt).toFixed(2) : "—") + "<small>ft</small></b></div></div>" +
      '<div class="wood" aria-hidden="true"></div><div class="desc">Elevation above NGVD 1929 at the dam, the datum USACE uses for the guide curve. Release is regulated by Falls Dam' + (d.release && d.release.band ? " · " + esc(d.release.band.label.toLowerCase()) : "") + ".</div></div></div>" +
      foot((sample ? "Sample of " : "") + "USGS 02087182 / 02087183, USACE guide curve", (sample ? "Recorded " : "") + dt(L.elevation.time), L.url);
  }

  function innerW(id) { const el = $(id); return Math.max(260, Math.round(el.clientWidth - 34)); }
  // the tide and pool drawings are sized to the tile in real pixels (no stretched text); redraw on width change
  let lastTide = null, lastFresh = null, rw = 0, rT = 0;
  addEventListener("resize", function () { clearTimeout(rT); rT = setTimeout(function () { if (innerWidth === rw) return; rw = innerWidth; if (lastTide) renderTide(lastTide); if (lastFresh) renderFresh(lastFresh[0], lastFresh[1]); }, 150); });

  /* -------- editorial lines, built only from the readings above -------- */
  function ed(id, text) { if (text) $(id).innerHTML = "<i>From the readings</i>" + esc(text); }

  function alerts(a) {
    const box = $("adv");
    if (!a || a.status !== "ok") { box.className = "adv clear"; box.innerHTML = '<span class="dot"></span><div><b>Advisories unavailable</b><small>Check weather.gov before heading out.</small></div>'; return; }
    if (!a.items.length) { box.className = "adv clear"; box.innerHTML = '<span class="dot"></span><div><b>No marine advisories</b><small>NWS zones ' + esc(a.zones.join(", ")) + "</small></div>"; return; }
    box.className = "adv"; box.innerHTML = '<span class="dot"></span><div>' + a.items.map((i) => "<b>" + esc(i.event) + "</b>" + (i.ends ? " until " + esc(t12(i.ends)) : "") + "<small>" + esc(i.areas) + "</small>").join("") + "</div>";
  }

  const SAMPLE_LAKE = { lake: { elevation: { value: 245.07, time: "2026-11-13T08:30:00-05:00" }, guideCurveFt: 251.5, vsGuideFt: -6.43, change7dFt: -0.23, url: "https://waterdata.usgs.gov/monitoring-location/02087182/" },
    release: { flowCfs: { value: 60 }, band: { label: "Below lowest daily mean for this date" } }, waterTemp: { f: 62.1 } };

  fetch("/api/conditions?region=crystal-coast").then((r) => r.json()).then(function (d) {
    const R = d.readings;
    $("note").textContent = "Live from the site's conditions API · loaded " + t12(Date.now()) + " · each tile shows its own station and time";
    alerts(d.alerts);
    if (R.wind.status === "ok") renderWind(R.wind);
    if (R.swell.status === "ok") renderSwell(R.swell);
    if (R.seas.status === "ok") renderSeas(R.seas, R.swell);
    if (d.tides.status === "ok") renderTide(d.tides);
    if (R.waterTemp.status === "ok") renderTemp(R.waterTemp, R.waterTempOffshore);
    const w = R.wind.values, s = R.seas.values;
    if (w && s) ed("ed-coast", Math.round(w.speedKt) + " kt from the " + w.dirCompass + " at Cape Lookout, with " + s.heightFt.toFixed(1) + " ft seas every " + s.dominantPeriodS.toFixed(0) + " s in Onslow Bay" + (s.dominantPeriodS < 7 ? ": short-period wind waves more than groundswell." : "."));
    const tl = d.tides.observed && d.tides.observed.latest, nx = (d.tides.events || []).find((e) => e.t > Date.now());
    if (nx) ed("ed-sound", "Next " + (nx.type === "H" ? "high" : "low") + " tide at Beaufort " + t12(nx.t) + (tl && Math.abs(tl.diff) >= 0.3 ? "; the water is running " + Math.abs(tl.diff).toFixed(1) + " ft " + (tl.diff > 0 ? "above" : "below") + " the prediction." : "."));
  }).catch(function () { $("note").textContent = "Live readings could not be loaded."; });

  fetch("/api/freshwater?region=falls-lake").then((r) => { if (!r.ok) throw 0; return r.json(); }).then(function (d) { renderFresh(d, false); lakeEd(d); })
    .catch(function () { renderFresh(SAMPLE_LAKE, true); lakeEd(SAMPLE_LAKE); });
  function lakeEd(d) { ed("ed-lake", "Falls Lake sits " + Math.abs(d.lake.vsGuideFt).toFixed(1) + " ft " + (d.lake.vsGuideFt < 0 ? "below" : "above") + " its guide curve, and the dam is releasing " + Math.round(d.release.flowCfs.value) + " cfs."); }

  // pause the wind drift when the tiles are off screen
  if ("IntersectionObserver" in window) new IntersectionObserver(function (es) { document.body.classList.toggle("paused", !es[0].isIntersecting); }).observe($("t-wind"));
})();
