/* The Coastal Brief: private Falls Lake preview (FRESHWATER_ENABLED only).
   Renders /api/freshwater. Every number shows its source and time; missing or
   stale readings are said out loud, never filled in. */
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const isNum = (v) => typeof v === "number" && isFinite(v);
  const tfmt = new Intl.DateTimeFormat("en-US", { timeZone: "America/New_York", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
  const when = (t) => (t ? tfmt.format(new Date(t)) + " ET" : "");
  const signed = (v, d) => (v > 0 ? "+" : v < 0 ? "−" : "±") + Math.abs(v).toFixed(d);
  const cfs = (v) => (v >= 100 ? Math.round(v).toLocaleString("en-US") : v.toFixed(1));

  // theme toggle, same storage key as the main site
  function setTheme(t, save) {
    document.documentElement.setAttribute("data-theme", t);
    const b = $("theme-toggle");
    if (b) { b.textContent = t === "dark" ? "Light mode" : "Dark mode"; b.setAttribute("aria-pressed", String(t === "dark")); b.setAttribute("aria-label", t === "dark" ? "Switch to light mode" : "Switch to dark mode"); }
    if (save) try { localStorage.setItem("coastalBrief.theme", t); } catch (e) {}
  }
  setTheme(document.documentElement.getAttribute("data-theme") || "light", false);
  $("theme-toggle").addEventListener("click", () => setTheme(document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark", true));

  const tag = (k) => '<span class="tag tag-' + k + '">' + (k === "observed" ? "Observed" : "Forecast") + "</span>";
  const head = (title, kind) => '<header class="inst-h"><h3 class="inst-k">' + esc(title) + "</h3>" + (kind ? tag(kind) : "") + "</header>";
  const foot = (id, name, time, url, extra) =>
    '<div class="inst-foot"><details class="src"><summary><span class="src-id">' + esc(id) + '</span><span class="src-name">' + esc(name) + '</span><span class="src-time">' + esc(time) + "</span></summary>" +
    '<div class="src-body">' + (extra || "") + (url ? '<p class="src-links"><a href="' + esc(url) + '" target="_blank" rel="noopener">Open the official page</a></p>' : "") + "</div></details></div>";
  function fill(id, html) { const el = $(id); el.classList.remove("is-loading"); el.innerHTML = html; }
  const unavailable = (msg) => '<p class="fw-unavail">' + esc(msg) + "</p>";
  const staleNote = (r) => (r && r.stale ? '<p class="fw-note"><strong>Stale:</strong> last report ' + esc(when(r.time)) + ".</p>" : "");

  function poolSvg(level, guide) {
    // vertical scale with the guide curve (USACE target) and the current level
    const lo = Math.floor(Math.min(level, guide) - 2), hi = Math.ceil(Math.max(level, guide) + 1);
    const step = hi - lo > 8 ? 2 : 1;
    const y = (v) => 8 + (hi - v) / (hi - lo) * 164;
    let ticks = "";
    for (let v = lo + ((lo % step) + step) % step; v <= hi; v += step) ticks += '<line x1="34" x2="40" y1="' + y(v) + '" y2="' + y(v) + '" stroke="currentColor" stroke-opacity=".35"/><text x="30" y="' + (y(v) + 4) + '" text-anchor="end">' + v + "</text>";
    return '<svg class="fw-pool" viewBox="0 0 120 180" role="img" aria-label="Lake level ' + level.toFixed(2) + " feet against a guide curve of " + guide + ' feet">' +
      '<rect x="42" y="8" width="34" height="164" rx="4" fill="none" stroke="currentColor" stroke-opacity=".3"/>' +
      '<rect x="42" y="' + y(level).toFixed(1) + '" width="34" height="' + (172 - y(level)).toFixed(1) + '" rx="4" fill="var(--teal)" fill-opacity=".6"/>' + ticks +
      '<line x1="38" x2="82" y1="' + y(guide) + '" y2="' + y(guide) + '" stroke="var(--copper)" stroke-width="2.5" stroke-dasharray="5 3"/>' +
      '<text class="lbl" x="84" y="' + (y(guide) - 2) + '" style="fill:var(--copper)">Guide</text><text class="lbl" x="84" y="' + (y(guide) + 11) + '" style="fill:var(--copper)">' + guide + '</text>' +
      '<text class="lbl" x="84" y="' + (y(level) + 4) + '">Now</text></svg>';
  }
  function sparkSvg(series) {
    if (!series || series.length < 4) return "";
    const ts = series.map((p) => new Date(p[0]).getTime()), vs = series.map((p) => p[1]);
    const t0 = ts[0], t1 = ts[ts.length - 1];
    let lo = Math.min.apply(null, vs), hi = Math.max.apply(null, vs);
    if (hi - lo < 0.2) { const m = (hi + lo) / 2; lo = m - 0.1; hi = m + 0.1; }
    const W = 340, H = 104, x = (t) => 46 + (t - t0) / (t1 - t0) * (W - 52), yy = (v) => 10 + (hi - v) / (hi - lo) * (H - 32);
    const d = series.map((p, i) => (i ? "L" : "M") + x(ts[i]).toFixed(1) + " " + yy(vs[i]).toFixed(1)).join(" ");
    return '<p class="fw-k" style="margin-top:10px">Past 7 days</p><svg class="fw-spark" viewBox="0 0 ' + W + " " + H + '" role="img" aria-label="Lake elevation over the past seven days, from ' + vs[0].toFixed(2) + " to " + vs[vs.length - 1].toFixed(2) + ' feet">' +
      '<line x1="46" x2="' + (W - 6) + '" y1="' + yy(hi) + '" y2="' + yy(hi) + '" stroke="currentColor" stroke-opacity=".12"/><line x1="46" x2="' + (W - 6) + '" y1="' + yy(lo) + '" y2="' + yy(lo) + '" stroke="currentColor" stroke-opacity=".12"/>' +
      '<text x="40" y="' + (yy(hi) + 4) + '" text-anchor="end">' + hi.toFixed(2) + '</text><text x="40" y="' + (yy(lo) + 4) + '" text-anchor="end">' + lo.toFixed(2) + "</text>" +
      '<path d="' + d + '" fill="none" stroke="var(--teal)" stroke-width="2.2" stroke-linejoin="round"/>' +
      '<text x="46" y="' + (H - 4) + '">' + esc(new Intl.DateTimeFormat("en-US", { timeZone: "America/New_York", month: "short", day: "numeric" }).format(new Date(t0))) + '</text><text x="' + (W - 6) + '" y="' + (H - 4) + '" text-anchor="end">Now</text></svg>';
  }

  function renderLake(L) {
    const e = L.elevation;
    if (!e) { fill("fw-lake", head("Lake level", "observed") + unavailable("USGS lake elevation is not available right now.") + foot("USGS " + L.usgs, "Falls Lake above dam", "", L.url)); return; }
    const vs = L.vsGuideFt;
    const vsTxt = isNum(vs) ? (Math.abs(vs) < 0.05 ? "At the guide curve" : Math.abs(vs).toFixed(2) + " ft " + (vs < 0 ? "below" : "above") + " guide curve") : "";
    const fl = L.nwps && L.nwps.floodStages || {};
    let h = head("Lake level", "observed") +
      '<div class="fw-big">' + e.value.toFixed(2) + "<small>ft</small></div>" +
      '<p class="fw-vs' + (vs < -1 ? " low" : "") + '">' + esc(vsTxt) + "</p>" +
      '<p class="fw-note">Elevation above NGVD 1929, the datum USACE uses for the ' + esc(L.guideCurveFt) + " ft guide curve" + (isNum(L.datumOffsetFt) && L.navd88 ? ". Same reading on NAVD 1988: " + L.navd88.value.toFixed(2) + " ft (" + L.datumOffsetFt.toFixed(2) + " ft lower)." : ".") + "</p>" +
      staleNote(e) +
      '<div class="fw-row">' + poolSvg(e.value, L.guideCurveFt) +
      '<dl class="fw-dl"><div><dt>24 h change</dt><dd>' + (isNum(L.change24hFt) ? signed(L.change24hFt, 2) + " ft" : "—") + "</dd></div>" +
      "<div><dt>7 day change</dt><dd>" + (isNum(L.change7dFt) ? signed(L.change7dFt, 2) + " ft" : "—") + "</dd></div>" +
      "<div><dt>Guide curve</dt><dd>" + esc(L.guideCurveFt) + " ft</dd></div>" +
      "<div><dt>NWS flood action</dt><dd>" + (isNum(fl.action) ? fl.action + " ft" : "—") + "</dd></div></dl></div>" +
      sparkSvg(L.series7d) +
      foot("USGS " + L.usgs, L.siteName || "Falls Lake above dam", "Reported " + when(e.time), L.url,
        "<p>USGS parameter 62614 (lake elevation above NGVD 1929), provisional. Guide curve " + esc(L.guideCurveFt) + " ft from USACE Wilmington District (" + esc(L.guideCurveNote || "") + ") checked " + esc(L.guideCurveChecked) + '. <a href="' + esc(L.guideCurveSource) + '" target="_blank" rel="noopener">USACE data</a>.</p>' +
        (L.nwps && L.nwps.status === "ok" ? '<p>NWS flood categories for the lake (NWPS ' + esc(L.nwps.lid) + "): action " + fl.action + ", minor " + fl.minor + ", moderate " + fl.moderate + ", major " + fl.major + " ft. NWPS publishes no forecast for the lake itself.</p>" : ""));
    fill("fw-lake", h);
  }
  function renderTemp(w) {
    if (!w || w.status !== "ok") { fill("fw-temp", head("Water temp", "observed") + unavailable("No current USGS water temperature at the dam.") + foot("USGS 02087182", "Falls Lake above dam", "", "")); return; }
    fill("fw-temp", head("Water temp", "observed") + '<div class="fw-mid">' + w.f.toFixed(0) + "<small>°F</small></div>" +
      '<p class="fw-note">' + w.c.toFixed(1) + " °C · " + esc(w.note) + "</p>" + staleNote(w) +
      foot("USGS " + w.usgs, "Falls Lake above dam", "Reported " + when(w.time), "https://waterdata.usgs.gov/monitoring-location/" + w.usgs + "/", "<p>USGS parameter 00010, provisional.</p>"));
  }
  function bandHtml(s) {
    if (!s.band) return "";
    const st = s.stats || {};
    return '<span class="fw-band ' + esc(s.band.key) + '">' + esc(s.band.label) + "</span>" +
      '<p class="fw-meta">Compared with USGS daily-mean flows for this date (' + esc(st.years || "") + "): 10th pct " + (isNum(st.p10) ? cfs(st.p10) : "—") + ", median " + (isNum(st.p50) ? cfs(st.p50) : "—") + " cfs." + (s.regulated ? " Flow here is set by dam releases." : "") + "</p>";
  }
  function renderRelease(s) {
    if (!s || !s.flowCfs) { fill("fw-release", head("Release below dam", "observed") + unavailable("USGS flow below the dam is not available right now.")); return; }
    fill("fw-release", head("Release below dam", "observed") + '<div class="fw-mid">' + cfs(s.flowCfs.value) + "<small>cfs</small></div>" + bandHtml(s) + staleNote(s.flowCfs) +
      foot("USGS " + s.usgs, s.label, "Reported " + when(s.flowCfs.time), s.url, "<p>USGS discharge (00060) just below Falls Dam, provisional. USACE sets releases; this gauge shows the result.</p>"));
  }
  function renderRain(r) {
    const q = r.qpf || {};
    let h = head("Rain", null) + '<div class="fw-two">';
    h += "<div>" + tag("observed") + '<p class="fw-k" style="margin-top:6px">Past 24 h</p><p class="fw-v">' + (isNum(r.last24In) ? r.last24In.toFixed(2) + " in" : "—") + '</p><p class="fw-k">Past 7 days</p><p class="fw-v">' + (isNum(r.last7dIn) ? r.last7dIn.toFixed(2) + " in" : "—") + "</p></div>";
    h += "<div>" + tag("forecast") + '<p class="fw-k" style="margin-top:6px">Next 24 h</p><p class="fw-v">' + (q.status === "ok" ? q.next24In.toFixed(2) + " in" : "—") + '</p><p class="fw-k">Next 72 h</p><p class="fw-v">' + (q.status === "ok" ? q.next72In.toFixed(2) + " in" : "—") + "</p></div></div>";
    if (r.status !== "ok") h += unavailable("USGS rain gauge at the dam is not reporting.");
    h += foot("USGS " + r.usgs + " · NWS RAH", "Dam rain gauge · NWS gridded QPF", r.time ? "Reported " + when(r.time) : "", q.sourceUrl,
      "<p>" + esc(r.note || "") + "</p><p>Forecast amounts are NWS quantitative precipitation forecasts (QPF) for the grid cell at the dam" + (q.updated ? ", updated " + esc(when(q.updated)) : "") + ". " + esc(q.note || "") + "</p>");
    fill("fw-rain", h);
  }
  function gaugeCard(s) {
    let h = '<div class="inst fw-g"><h3>' + esc(s.label) + "</h3>";
    if (s.flowCfs) h += '<div class="fw-mid">' + cfs(s.flowCfs.value) + "<small>cfs</small></div>";
    else h += '<p class="fw-unavail">' + esc(s.flowNote || "Flow not available right now.") + "</p>";
    h += bandHtml(s);
    const n = s.nwps && s.nwps.status === "ok" ? s.nwps : null;
    h += '<p class="fw-meta">Stage ' + (s.stageFt ? s.stageFt.value.toFixed(2) + " ft" : "—") + (n && isNum(n.floodStages.minor) ? " · flood stage " + n.floodStages.minor + " ft" : "") + (s.stageFt ? " · " + esc(when(s.stageFt.time)) : "") + "</p>";
    if (n && n.forecast) h += '<p class="fw-meta">' + tag("forecast") + " NWS crest " + n.forecast.crestStage.toFixed(1) + " ft " + esc(when(n.forecast.crestTime)) + (n.forecast.category && n.forecast.category !== "no_flooding" ? " · " + esc(n.forecast.category.replace("_", " ")) : " · no flooding forecast") + "</p>";
    if ((s.flowCfs && s.flowCfs.stale) || (s.stageFt && s.stageFt.stale)) h += '<p class="fw-meta"><strong>Stale reading.</strong></p>';
    h += '<p class="fw-meta"><a href="' + esc(s.url) + '" target="_blank" rel="noopener">USGS ' + esc(s.usgs) + "</a>" + (n ? ' · <a href="' + esc(n.url) + '" target="_blank" rel="noopener">NWPS ' + esc(n.lid) + "</a>" : "") + "</p></div>";
    return h;
  }
  function renderForecast(f) {
    const box = $("fw-fc");
    if (!f || f.status !== "ok") { box.innerHTML = '<div class="fw-unavail">NWS forecast unavailable.</div>'; return; }
    box.innerHTML = f.periods.slice(0, 4).map((p) => "<div><b>" + esc(p.name) + '</b><span class="t">' + (isNum(p.tempF) ? p.tempF + "°" : "") + "</span><span>" + esc(p.short) + "</span><span>" + esc((p.windDir || "") + " " + (p.windMph || "")) + "</span></div>").join("");
    $("fw-fc-meta").innerHTML = "NWS Raleigh point forecast for the dam" + (f.updated ? ", updated " + esc(when(f.updated)) : "") + '. <a href="' + esc(f.sourceUrl) + '" target="_blank" rel="noopener">Full forecast</a>';
  }
  function renderAlerts(a) {
    const box = $("fw-alert");
    const link = '<a class="al-link" href="https://alerts.weather.gov/" target="_blank" rel="noopener">NWS alerts</a>';
    if (!a || a.status !== "ok") { box.className = "dash-alert is-clear"; box.innerHTML = '<div class="al-item"><span class="al-dot"></span><span class="al-ev">Alerts unavailable</span><span class="al-meta">Could not check NWS alerts. See weather.gov.</span></div>' + link; return; }
    if (!a.items.length) { box.className = "dash-alert is-clear"; box.innerHTML = '<div class="al-item"><span class="al-dot"></span><span class="al-ev">No NWS alerts right now</span><span class="al-meta">No watches, warnings, or advisories at the dam.</span></div>' + link; return; }
    box.className = "dash-alert is-active";
    box.innerHTML = a.items.map((it) => '<div class="al-item"><span class="al-dot"></span><span class="al-ev">' + esc(it.event) + '</span><span class="al-meta">' + (it.ends ? "until " + esc(when(it.ends)) : "") + "</span></div>").join("") + link;
  }
  function renderSources(d) {
    const L = d.lake, rows = [
      ["Lake elevation", "USGS 02087182 (62614, NGVD29; 62615, NAVD88)", "Every 15 min, about 1 h delay", L.elevation ? when(L.elevation.time) : "unavailable", L.url],
      ["Guide curve", "USACE Wilmington District, 251.5 ft every day", "Fixed in the water control plan", d.guideCheck && d.guideCheck.status === "ok" ? (d.guideCheck.matches ? "Matches the USACE page today" : "Does not match the USACE page: check") : "USACE page not reachable", L.guideCurveSource],
      ["Water temperature", "USGS 02087182 (00010)", "Every 15 min", d.waterTemp.time ? when(d.waterTemp.time) : "unavailable", L.url],
      ["Rain, observed", "USGS 02087182 (00045)", "15-min totals", d.rain.time ? when(d.rain.time) : "unavailable", L.url],
      ["Rain, forecast", "NWS gridded QPF, RAH 76,65", "About hourly", d.rain.qpf && d.rain.qpf.updated ? when(d.rain.qpf.updated) : "unavailable", d.rain.qpf && d.rain.qpf.sourceUrl],
      ["Flows and stages", "USGS 02087183, 02087500, 02087570, 02089000, 02085070, 02085500", "Every 15 min", "see each card", "https://waterdata.usgs.gov/"],
      ["Flow percentiles", "USGS daily statistics", "Daily means for each calendar day", "", "https://waterservices.usgs.gov/docs/statistics/"],
      ["River forecasts", "NWS NWPS (CLYN7, SMFN7, GLDN7; lake NUDN7 has no forecast)", "Issued by SERFC", "", "https://water.noaa.gov/"],
      ["Forecast and alerts", "NWS Raleigh point forecast; alerts for the dam point", "Hourly", d.forecast && d.forecast.updated ? when(d.forecast.updated) : "", "https://www.weather.gov/rah/"],
    ];
    $("fw-sources").innerHTML = '<table class="fw-src"><thead><tr><th>Reading</th><th>Source</th><th>Updates</th><th>Latest</th></tr></thead><tbody>' +
      rows.map((r) => "<tr><td><strong>" + esc(r[0]) + "</strong></td><td>" + (r[4] ? '<a href="' + esc(r[4]) + '" target="_blank" rel="noopener">' + esc(r[1]) + "</a>" : esc(r[1])) + "</td><td>" + esc(r[2]) + "</td><td>" + esc(r[3]) + "</td></tr>").join("") + "</tbody></table>" +
      '<p class="fine">USGS data are provisional. Duke Energy lake levels are not shown (their terms do not allow republishing). Generated ' + esc(when(d.generatedAt)) + ".</p>";
  }

  const rid = new URLSearchParams(location.search).get("region") || "falls-lake";
  fetch("/api/freshwater?region=" + encodeURIComponent(rid)).then((r) => r.json()).then(function (d) {
    if (!d.ok) throw new Error(d.error || "unavailable");
    $("fw-h").textContent = d.region.name; $("fw-sub").textContent = d.region.area || "";
    $("fw-badge").textContent = "Updated " + tfmt.format(new Date(d.generatedAt)).replace(/^\w+ \d+, /, "") + " ET";
    renderAlerts(d.alerts); renderLake(d.lake); renderTemp(d.waterTemp); renderRelease(d.release); renderRain(d.rain);
    $("fw-river").innerHTML = (d.river || []).map(gaugeCard).join("") || unavailable("No river gauges configured.");
    $("fw-inflows").innerHTML = (d.inflows || []).map(gaugeCard).join("");
    renderForecast(d.forecast);
    $("fw-links").innerHTML = (d.links || []).map((l) => '<li><a href="' + esc(l.url) + '" target="_blank" rel="noopener">' + esc(l.label) + "</a></li>").join("");
    renderSources(d);
  }).catch(function (e) {
    $("fw-badge").textContent = "Readings unavailable"; $("fw-badge").classList.add("amber");
    ["fw-lake", "fw-temp", "fw-release", "fw-rain"].forEach((id) => fill(id, head($(id).dataset.title, null) + unavailable("Could not load readings: " + e.message)));
  });
})();
