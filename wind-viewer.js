/* /wind viewer UI (CBWind / CBWindMath). NOAA MODEL FORECAST only. Times in ET. */
(function () {
  "use strict";
  const W = window.CBWind, M = window.CBWindMath;
  if (!W || !M || !window.L || !window.CBCoast) return;
  const $ = (id) => document.getElementById(id);
  const q = location.search;
  const root = document.documentElement;
  let dark = root.getAttribute("data-theme") === "dark";
  const mm = (s) => !!(window.matchMedia && matchMedia(s).matches);
  const osReduce = mm("(prefers-reduced-motion: reduce)");
  const coarse = mm("(pointer: coarse)");
  const phone = coarse && Math.min(screen.width, screen.height) < 600;
  const fps = /[?&]fps=60\b/.test(q) ? 60 : /[?&]fps=30\b/.test(q) ? 30 : phone ? 30 : 60;
  let pref = null; try { pref = localStorage.getItem("coastalBrief.windMotion"); } catch (e) {}
  let motion = pref === "on" ? true : pref === "off" ? false : !osReduce;
  const AHEAD = [0, 3, 6, 9, 12];
  const wantHrrr = /[?&]model=hrrr\b/.test(q);
  let modelName = wantHrrr ? "HRRR" : "GFS";
  let ai = 0, grid = null, req = 0;
  const AT = (/[?&]at=(-?\d{1,2}(?:\.\d{1,5})?),(-?\d{1,3}(?:\.\d{1,5})?)(?:&|$)/.exec(q) || []).slice(1).map(Number);
  const COAST = L.latLngBounds([33.75, -78.3], [36.55, -75.25]);
  const HOME = AT.length === 2 && AT[0] >= 32.5 && AT[0] <= 37.5 && AT[1] >= -80 && AT[1] <= -73
    ? L.latLngBounds([AT[0] - 0.9, AT[1] - 1.2], [AT[0] + 0.9, AT[1] + 1.2])
    : COAST;
  const yieldTask = () => new Promise((r) => (window.scheduler && scheduler.yield ? scheduler.yield().then(r) : setTimeout(r, 0)));

  const clockF = new Intl.DateTimeFormat("en-US", { timeZone: "America/New_York", hour: "numeric", minute: "2-digit" });
  let onTick = null;
  function nowMs() { return (typeof window.__windNow === "function") ? window.__windNow() : Date.now(); }
  function tick() { $("w-clock").textContent = clockF.format(new Date(nowMs())) + " ET"; if (onTick) onTick(); }
  tick(); setInterval(tick, 15000);

  function ramp() { const c = $("w-ramp"), x = c.getContext("2d"); for (let i = 0; i < c.width; i++) { x.fillStyle = "rgb(" + M.rgb(i / c.width * 36, dark).join(",") + ")"; x.fillRect(i, 0, 1, c.height); } }
  ramp();

  const THEME_STORE = "coastalBrief.theme";
  const sysDark = window.matchMedia ? matchMedia("(prefers-color-scheme: dark)") : null;
  const qTheme = (/[?&]theme=(light|dark)\b/.exec(q) || [])[1] || null;
  let onTheme = null;
  function stored() { try { const t = localStorage.getItem(THEME_STORE); return t === "light" || t === "dark" ? t : null; } catch (e) { return null; } }
  function resolved() { return stored() || (sysDark && sysDark.matches ? "dark" : "light"); }
  const tbtn = $("w-theme");
  function syncToggle() {
    if (!tbtn) return;
    tbtn.setAttribute("aria-pressed", String(dark));
    tbtn.title = dark ? "Switch to day mode" : "Switch to night mode";
  }
  function applyTheme(t, persist) {
    t = t === "dark" ? "dark" : "light";
    if (persist) { try { localStorage.setItem(THEME_STORE, t); } catch (e) {} }
    const d = t === "dark";
    if (d === dark && root.getAttribute("data-theme") === t) { syncToggle(); return; }
    dark = d;
    root.setAttribute("data-theme", t);
    if (d) root.setAttribute("data-night", "b"); else root.removeAttribute("data-night");
    syncToggle(); ramp();
    if (onTheme) onTheme();
  }
  syncToggle();
  if (tbtn) tbtn.addEventListener("click", function () { applyTheme(dark ? "light" : "dark", true); });
  window.addEventListener("cb:theme", function (e) { if (e && e.detail) applyTheme(e.detail.theme, false); });
  window.addEventListener("storage", function (e) { if (e.key === THEME_STORE || e.key === null) applyTheme(resolved(), false); });
  if (sysDark) {
    const onSys = function () { if (!stored() && !qTheme) applyTheme(resolved(), false); };
    if (sysDark.addEventListener) sysDark.addEventListener("change", onSys); else if (sysDark.addListener) sysDark.addListener(onSys);
  }
  window.addEventListener("pageshow", function (e) { if (e.persisted) applyTheme(qTheme && !stored() ? qTheme : resolved(), false); });

  const play = $("w-play"), status = $("w-status"), read = $("w-read");
  function setPlay() {
    play.setAttribute("aria-pressed", String(motion));
    $("w-play-lbl").textContent = motion ? "Pause" : "Flow";
    play.setAttribute("aria-label", motion ? "Pause flow animation (show static arrows)" : "Play flow animation");
  }
  setPlay();

  async function boot() {
    // maxZoom 9.5: Census 1:500,000 cap.
    const map = L.map("wmap", { zoomControl: true, attributionControl: false, zoomSnap: 0.5, minZoom: 5, maxZoom: 9.5, maxBounds: [[30, -84], [40, -69]], tap: true, fadeAnimation: false });
    map.zoomControl.setPosition("topright");
    map.fitBounds(HOME);
    await yieldTask();
    const cs = getComputedStyle(root), bootDark = dark;
    const coast = window.CBCoast.layer({
      base: "/wind/coast-", land: cs.getPropertyValue("--coast-land").trim(),
      line: cs.getPropertyValue("--coast-line").trim(), lineWidth: dark ? 1 : 0.9,
    }).addTo(map);
    window.__coast = coast;
    function coastStyle() {
      const c = getComputedStyle(root);
      return { land: c.getPropertyValue("--coast-land").trim(), line: c.getPropertyValue("--coast-line").trim(), lineWidth: dark ? 1 : 0.9 };
    }
    await yieldTask();
    const wind = W.layer(map, {
      dark: dark, motion: motion, frameMs: fps === 30 ? 33.3 : 0,
      dprCap: phone ? 1.5 : 2, maxParticles: phone ? 1100 : 2200, density: phone ? 260 : 380,
      observe: $("w-stage"), perf: /[?&]perf=1\b/.test(q) ? $("w-stage") : null,
    });
    window.__windStats = wind.stats;
    onTheme = function () { coast.restyle(coastStyle()); wind.setDark(dark); };
    window.__windView = { map: map, wind: wind, fps: fps, phone: phone, motion: () => motion, grid: () => grid, dark: () => dark, tick: tick };

    if (dark !== bootDark) onTheme();
    play.addEventListener("click", function () {
      motion = !motion; setPlay(); try { localStorage.setItem("coastalBrief.windMotion", motion ? "on" : "off"); } catch (e) {}
      wind.setMotion(motion);
    });
    $("w-center").addEventListener("click", function () { map.flyToBounds(COAST, { duration: osReduce ? 0 : 0.6 }); });

    let dot = null, loading = false;
    const live = $("w-read-body");
    function validMs(iso) { return Date.parse(String(iso || "").replace("Z", "+00:00")); }
    function relValid(iso) {
      const h = (validMs(iso) - Date.now()) / 36e5;
      if (!isFinite(h)) return "";
      const n = Math.abs(Math.round(h));
      if (h < -0.75) return n + " h ago";
      if (h > 0.75) return "in " + n + " h";
      return "";
    }
    function fcstTag(g) { return g && g.forecastHour != null ? "F" + String(g.forecastHour).padStart(3, "0") : ""; }
    const staBtn = $("w-sta"), retryBtn = $("w-retry"), staErrEl = $("w-sta-err");
    const STA_STORE = "coastalBrief.windStations";
    const CMP_STORE = "coastalBrief.windCompass";
    let staOn = false;
    try { if (localStorage.getItem(STA_STORE) === "on") staOn = true; } catch (e) {}
    if (/[?&]stations=1\b/.test(q)) staOn = true;
    let cmpOn = true;
    try { if (localStorage.getItem(CMP_STORE) === "off") cmpOn = false; } catch (e) {}
    let staSel = null, staPack = null, staErr = null, staReq = 0, staAt = 0, staTimer = 0, staMarks = [];
    const STA_TTL = 90e3;
    const PRI_HI = "41025 41013 41064 41038 CLKN7 8651370 8652587 8654467 8656483 8658163 KHSE KILM KSUT";
    function esc(x) { return String(x == null ? "" : x).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").split(String.fromCharCode(34)).join("&quot;"); }
    // Types from NDBC pages 26 Nov 2026: numeric buoys; CLKN7/MBNN7/MBIN7 C-MAN.
    const STA_KIND = {41013:"buoy",41025:"buoy",41038:"buoy",41064:"buoy",CLKN7:"pier",MBNN7:"pier",MBIN7:"pier"};
    function staKind(s) { return STA_KIND[s.id] || (s.type === "nws" ? "air" : s.type === "coops" ? "pier" : "buoy"); }
    function staPri(s) { if (staSel && s.id === staSel) return 1000; if (PRI_HI.indexOf(s.id) >= 0) return /410/.test(s.id) ? 80 : 70; return s.optional ? 10 : 40; }
    function ageTxt(m) { if (m == null || !isFinite(m)) return ""; return m >= 120 ? Math.round(m / 60) + " h ago" : Math.round(m) + " min ago"; }
    function classifySta(s, now) {
      now = now || nowMs();
      const t = Date.parse(String(s.observedAt || "").replace("Z", "+00:00"));
      const age = isFinite(t) ? (now - t) / 6e4 : null;
      const w = s.wind || {};
      const staleAfter = s.staleAfterMin != null ? s.staleAfterMin : 75;
      const empty = { speedKt: null, gustKt: null, dirDeg: null, dirCompass: null };
      if (age == null || age > 720) return { status: "unavailable", ageMin: age, wind: empty };
      if (w.speedKt == null && w.gustKt != null) return { status: "gust_only", ageMin: age, wind: w };
      if (w.speedKt == null) return { status: "unavailable", ageMin: age, wind: empty };
      return { status: age <= staleAfter ? "fresh" : "stale", ageMin: age, wind: w };
    }
    function setStaErr(msg) { if (!staErrEl) return; staErrEl.textContent = msg || ""; staErrEl.hidden = !msg; }
    function syncRetry() { if (retryBtn) retryBtn.hidden = !(!grid && !loading); }

    function dismissRead() {
      if (dot) { map.removeLayer(dot); dot = null; }
      staSel = null;
      markSel();
      if (live) live.innerHTML = "";
      read.hidden = true;
      syncRetry();
      syncCmp();
      paintLabels();
      const el = $("wmap"); if (el) el.focus();
    }
    function fcstBody(latlng, label) {
      const kind = modelName + " FORECAST";
      const s = grid ? wind.sample(latlng.lat, latlng.lng) : null;
      if (!grid) {
        const msg = loading ? "Loading model wind…" : "Model data didn't load — try again";
        return "<span class=\"w-k\">" + kind + "</span><strong>" + msg + "</strong>";
      } else if (!s || !isFinite(s.kt) || !isFinite(s.from)) {
        return "<span class=\"w-k\">" + kind + "</span><strong>Outside model coverage — no GFS data for this spot</strong><span class=\"w-sub\">This viewer loads GFS wind for 32.5–37.5°N, 73–80°W.</span>";
      } else {
        const rel = relValid(grid.valid), behind = rel.indexOf("ago") >= 0;
        const tline = "Valid " + M.etShort(grid.valid) + (rel ? (behind ? " — " + rel + " · Behind current time" : " · " + rel) : " · " + (fcstTag(grid) || "interpolated"));
        return "<span class=\"w-k\">" + kind + "</span><strong>" + Math.round(s.kt) + " kt</strong> from " + M.compass(s.from) + " (" + Math.round(s.from) + "°)" +
          "<span class=\"w-sub\">" + tline + "</span>" +
          "<span class=\"w-sub w-grid\">" + (label ? label + " · " : "") + latlng.lat.toFixed(2) + "°N " + Math.abs(latlng.lng).toFixed(2) + "°W · interpolated, 0.25° grid (~25 km)</span>";
      }
    }
    function obsBody(s) {
      const c = classifySta(s), w = c.wind, t = s.observedAt ? M.etShort(s.observedAt) : "";
      const head = "<span class=\"w-k\">OBSERVED · " + esc(s.name) + "  " + esc(s.id) + "</span>";
      const src = "<span class=\"w-sub\">" + esc(s.source || "") + "</span>";
      if (c.status === "gust_only") {
        return head + "<strong>Wind speed unavailable</strong>" +
          (w.gustKt != null ? "<span class=\"w-sub\">Gust " + Math.round(w.gustKt) + " kt" + (t ? " · " + t : "") + "</span>" : (t ? "<span class=\"w-sub\">" + t + "</span>" : "")) + src;
      }
      if (c.status === "unavailable") {
        return head + "<strong>Unavailable" + (t ? " — last report " + t : "") + "</strong>" + src;
      }
      let num = (w.speedKt != null ? "<strong>" + Math.round(w.speedKt) + " kt</strong>" : "");
      if (w.gustKt != null) num += (num ? " <span class=\"w-gust\">gust " + Math.round(w.gustKt) + "</span>" : "<span class=\"w-gust\">gust " + Math.round(w.gustKt) + "</span>");
      if (w.dirDeg != null) num += " from " + (w.dirCompass || M.compass(w.dirDeg)) + " (" + Math.round(w.dirDeg) + "°)";
      const line = c.status === "stale" ? ("Stale — last report " + t) : (t + (c.ageMin != null ? " · " + ageTxt(c.ageMin) : "") + " · Fresh");
      return head + num + "<span class=\"w-sub\">" + line + "</span>" + src;
    }
    function staRow(id) { return staPack && (staPack.stations || []).filter(function (s) { return s.id === id; })[0]; }

    let labData = null, labVis = [];
    const labRoot = $("w-labels");
    function hits(a, b) { return a.l < b.r && a.r > b.l && a.t < b.b && a.b > b.t; }
    function addBox(list, el, pad) {
      if (!el || el.hidden || (el.hasAttribute && el.hasAttribute("hidden"))) return;
      const r = el.getBoundingClientRect();
      if (r.width < 2 || r.height < 2) return;
      const st = $("w-stage").getBoundingClientRect();
      list.push({ l: r.left - st.left - pad, t: r.top - st.top - pad, r: r.right - st.left + pad, b: r.bottom - st.top + pad });
    }
    function reserved() {
      const box = [];
      addBox(box, document.querySelector(".w-legend"), 6);
      addBox(box, $("w-sta-leg"), 6);
      addBox(box, document.querySelector(".w-about summary"), 6);
      const about = document.querySelector(".w-about");
      if (about && about.open) addBox(box, about.querySelector(".w-about-body"), 8);
      if (read && !read.hidden) addBox(box, read, 8);
      addBox(box, document.querySelector(".w-attrib"), 4);
      if (status && !status.hidden) addBox(box, status, 4);
      addBox(box, $("w-sta-err"), 4);
      addBox(box, $("w-retry"), 4);
      document.querySelectorAll(".w-mk.on").forEach(function (el) { addBox(box, el, 20); });
      document.querySelectorAll(".leaflet-control-zoom").forEach(function (el) {
        if (getComputedStyle(el).display === "none") return;
        addBox(box, el, 4);
      });
      return box;
    }
    function paintLabels() {
      if (!labRoot) return;
      labVis = [];
      labRoot.textContent = "";
      if (!labData || !labData.places) return;
      const z = map.getZoom(), box = reserved(), kept = [];
      const st = $("w-stage").getBoundingClientRect();
      const m = document.createElement("span");
      m.style.cssText = "position:absolute;visibility:hidden;white-space:nowrap";
      labRoot.appendChild(m);
      labData.places.slice().sort(function (a, b) { return (b.p || 0) - (a.p || 0); }).forEach(function (p) {
        if (z < p.z0 || z > p.z1) return;
        const pt = map.latLngToContainerPoint([p.la, p.lo]);
        m.className = "w-lab w-lab-" + p.k;
        m.textContent = p.n;
        const w = m.offsetWidth, h = m.offsetHeight || 12;
        const rec = { l: pt.x - w / 2, t: pt.y - h / 2, r: pt.x + w / 2, b: pt.y + h / 2 };
        if (rec.l < 2 || rec.t < 2 || rec.r > st.width - 2 || rec.b > st.height - 2) return;
        if (box.some(function (b) { return hits(rec, b); }) || kept.some(function (b) { return hits(rec, b); })) return;
        kept.push(rec);
        const el = document.createElement("span");
        el.className = m.className;
        el.textContent = p.n;
        el.style.left = pt.x + "px";
        el.style.top = pt.y + "px";
        labRoot.appendChild(el);
        labVis.push(p);
      });
      m.remove();
    }
    fetch("/wind/labels.json").then(function (r) { return r.json(); }).then(function (d) { labData = d; paintLabels(); }).catch(function () {});

    function cmpState() {
      const row = staSel ? staRow(staSel) : null;
      if (row) {
        const w = classifySta(row).wind || {};
        if (w.dirDeg != null && isFinite(w.dirDeg)) return { mode: "observed", dirDeg: w.dirDeg, compass: w.dirCompass || M.compass(w.dirDeg) };
      }
      const ll = dot ? dot.getLatLng() : null;
      const s = (grid && ll) ? wind.sample(ll.lat, ll.lng) : null;
      if (s && isFinite(s.from)) return { mode: "forecast", dirDeg: s.from, compass: M.compass(s.from) };
      return { mode: null, dirDeg: null, compass: "" };
    }
    function syncCmp() {
      const wrap = $("w-cmp");
      if (!wrap) return;
      wrap.hidden = !!(read && read.hidden);
      wrap.classList.toggle("is-off", !cmpOn);
      const tog = $("w-cmp-tog");
      if (tog) {
        tog.setAttribute("aria-pressed", String(cmpOn));
        tog.setAttribute("aria-label", cmpOn ? "Hide wind compass" : "Show wind compass");
      }
      const st = cmpState();
      const needle = $("w-cmp-needle"), k = $("w-cmp-k"), d = $("w-cmp-d");
      if (!cmpOn || !st.mode) {
        if (k) k.textContent = "";
        if (d) d.textContent = "";
        if (needle) needle.setAttribute("transform", "rotate(0 32 32)");
        if (cmpOn && !st.mode) wrap.classList.add("is-off");
        return;
      }
      if (k) k.textContent = st.mode === "observed" ? "OBSERVED" : "FORECAST";
      if (d) d.textContent = "FROM " + Math.round(st.dirDeg) + "°T";
      if (needle) {
        needle.setAttribute("transform", "rotate(" + st.dirDeg + " 32 32)");
        needle.setAttribute("data-dir", String(st.dirDeg));
      }
    }
    function setCmpOn(on) {
      cmpOn = !!on;
      try { localStorage.setItem(CMP_STORE, cmpOn ? "on" : "off"); } catch (e) {}
      syncCmp();
    }
    const cmpTog = $("w-cmp-tog");
    if (cmpTog) cmpTog.addEventListener("click", function () { setCmpOn(!cmpOn); });

    function readAt(latlng, label, station) {
      if (arguments.length >= 3) staSel = station ? station.id : null;
      const row = staSel ? staRow(staSel) : null;
      if (row) latlng = L.latLng(row.lat, row.lon);
      if (!dot) dot = L.circleMarker(latlng, { radius: 7, className: "w-dot", interactive: false }).addTo(map); else dot.setLatLng(latlng);
      let body = "<div class=\"w-fcst\">" + fcstBody(latlng, label) + "</div>";
      if (row) body += "<div class=\"w-obs is-" + esc(classifySta(row).status) + "\">" + obsBody(row) + "</div>";
      if (live.innerHTML !== body) live.innerHTML = body;
      read.hidden = false;
      syncRetry();
      markSel();
      syncCmp();
      paintLabels();
    }
    $("w-read-x").addEventListener("click", dismissRead);
    if (retryBtn) retryBtn.addEventListener("click", function () { load(ai); });
    document.addEventListener("keydown", function (e) {
      if (e.key !== "Escape") return;
      const about = document.querySelector(".w-about");
      if (about && about.open) { about.open = false; e.preventDefault(); return; }
      if (read && !read.hidden) { e.preventDefault(); dismissRead(); }
    });
    map.on("click", function (e) { readAt(e.latlng, null, null); });
    window.__windView.readAt = readAt;
    window.__windView.dismiss = dismissRead;
    function clearMarks() {
      staMarks.forEach(function (m) { staLayer.removeLayer(m); });
      staMarks = [];
    }
    function markSel() {
      staMarks.forEach(function (m) {
        const on = !!(staSel && m._sta && m._sta.id === staSel);
        const el = m.getElement();
        if (el) el.classList.toggle("on", on);
      });
    }
    function restyleMarks() {
      staMarks.forEach(function (m) {
        if (!m._sta) return;
        const el = m.getElement(); if (!el) return;
        const st = classifySta(m._sta).status;
        el.className = el.className.replace(/\bis-(?:fresh|stale|unavailable|gust_only)\b/g, "").trim() + " is-" + st;
      });
    }
    function clampBadge(badge) {
      if (!badge) return;
      badge.classList.remove("w-n-left", "w-n-down");
      const stage = $("w-stage").getBoundingClientRect();
      let br = badge.getBoundingClientRect();
      if (br.right > stage.right - 2) badge.classList.add("w-n-left");
      br = badge.getBoundingClientRect();
      if (br.top < stage.top + 2) badge.classList.add("w-n-down");
    }
    function declutter() {
      if (!staMarks.length) return;
      const z = map.getZoom(), maxZ = map.getMaxZoom(), hidden = {};
      const items = staMarks.map(function (m) { return { m: m, s: m._sta, p: map.latLngToLayerPoint(m.getLatLng()), pri: staPri(m._sta) }; });
      items.sort(function (a, b) { return b.pri - a.pri; });
      const kept = [];
      items.forEach(function (it) {
        const hit = kept.filter(function (k) { const dx = k.p.x - it.p.x, dy = k.p.y - it.p.y; return dx * dx + dy * dy < 32 * 32; })[0];
        const el = it.m.getElement();
        const btn = el && el.querySelector(".w-mk-h");
        let hide = false;
        if (hit && !(staSel && it.s.id === staSel)) {
          if (z >= maxZ - 0.01) {
            const n = (hit.cluster = (hit.cluster || [hit])).length;
            const ang = (n * 2.2);
            const pt = L.point(hit.p.x + Math.cos(ang) * 18, hit.p.y + Math.sin(ang) * 18);
            it.m.setLatLng(map.layerPointToLatLng(pt));
            hit.cluster.push(it);
          } else {
            hide = true;
            (hit.cluster = hit.cluster || [hit]).push(it);
          }
        }
        if (el) {
          el.classList.toggle("is-hide", hide);
        }
        if (btn) btn.tabIndex = hide ? -1 : 0;
        if (!hide) kept.push(it);
        else hidden[it.s.id] = 1;
      });
      kept.forEach(function (k) {
        const el = k.m.getElement(); if (!el) return;
        let badge = el.querySelector(".w-n");
        const n = k.cluster ? k.cluster.length : 0;
        if (n > 1 && map.getZoom() < map.getMaxZoom() - 0.01) {
          if (!badge) { badge = document.createElement("span"); badge.className = "w-n"; badge.tabIndex = 0; el.appendChild(badge); }
          badge.textContent = "+" + (n - 1);
          badge.onclick = function (e) { L.DomEvent.stop(e); const b = L.latLngBounds(k.cluster.map(function (c) { return c.m.getLatLng(); })); map.fitBounds(b.pad(0.4), { maxZoom: Math.min(map.getMaxZoom(), map.getZoom() + 2), animate: !osReduce }); };
          clampBadge(badge);
        } else if (badge) { badge.remove(); }
      });
    }
    const staLayer = L.layerGroup().addTo(map);
    function drawSta() {
      clearMarks();
      if (!staOn || !staPack || !staPack.stations) return;
      staPack.stations.forEach(function (s) {
        if (s.lat == null || s.lon == null) return;
        const kind = staKind(s), st = classifySta(s).status || "unavailable";
        const ic = L.divIcon({ className: "w-mk w-mk-" + kind + " is-" + st, iconSize: [44, 44], iconAnchor: [22, 22],
          html: "<button type=\"button\" class=\"w-mk-h\" aria-label=\"" + esc(s.name) + ", observed\"><i></i></button>" });
        const m = L.marker([s.lat, s.lon], { icon: ic, keyboard: false, riseOnHover: true });
        m._sta = s;
        m._home = L.latLng(s.lat, s.lon);
        m.on("click", function (e) { L.DomEvent.stop(e); readAt(m.getLatLng(), null, s); });
        staLayer.addLayer(m);
        staMarks.push(m);
      });
      markSel();
      staMarks.forEach(function (m) { if (m._home) m.setLatLng(m._home); });
      setTimeout(function () { declutter(); paintLabels(); }, 0);
    }
    function stopStaTimer() { if (staTimer) { clearInterval(staTimer); staTimer = 0; } }
    async function loadStations(force) {
      if (!staOn) return;
      const my = ++staReq;
      if (!force && staPack && (Date.now() - staAt) < STA_TTL) { drawSta(); return; }
      try {
        const res = await fetch("/api/wind-stations");
        let data = {};
        try { data = await res.json(); } catch (err) { data = {}; }
        if (my !== staReq || !staOn) return;
        if (!res.ok || !data.ok) {
          staErr = (data && data.error) || "Observed stations unavailable right now.";
          setStaErr(staErr);
          if (!staPack) clearMarks();
          if (read && !read.hidden) readAt(dot ? dot.getLatLng() : map.getCenter());
          return;
        }
        staErr = null; setStaErr(""); staPack = data; staAt = Date.now();
        drawSta();
        if (read && !read.hidden && (staSel || dot)) readAt(dot ? dot.getLatLng() : map.getCenter());
        stopStaTimer();
        staTimer = setInterval(function () { if (staOn && !document.hidden) loadStations(); }, STA_TTL);
      } catch (e) {
        if (my !== staReq || !staOn) return;
        staErr = "Observed stations unavailable right now.";
        setStaErr(staErr);
        if (!staPack) clearMarks();
      }
    }
    function setStaOn(on) {
      staOn = !!on;
      try { localStorage.setItem(STA_STORE, staOn ? "on" : "off"); } catch (e) {}
      if (staBtn) {
        staBtn.setAttribute("aria-pressed", String(staOn));
        staBtn.title = staOn ? "Hide observed NOAA stations" : "Show observed NOAA stations";
        staBtn.setAttribute("aria-label", staOn ? "Hide observed NOAA stations" : "Show observed NOAA stations");
      }
      const leg = $("w-sta-leg");
      if (leg) leg.hidden = !staOn;
      if (staOn) loadStations();
      else {
        staReq++;
        stopStaTimer();
        clearMarks();
        setStaErr("");
        if (staSel) { staSel = null; if (dot) readAt(dot.getLatLng(), null, null); }
      }
      paintLabels();
    }
    if (staBtn) staBtn.addEventListener("click", function () { setStaOn(!staOn); });
    setStaOn(staOn);
    map.on("zoomend moveend", function () {
      if (staOn && staMarks.length) {
        staMarks.forEach(function (m) { if (m._home) m.setLatLng(m._home); });
        declutter();
      }
      paintLabels();
    });
    window.addEventListener("resize", function () { paintLabels(); if (staOn) declutter(); });
    const aboutEl = document.querySelector(".w-about");
    if (aboutEl) aboutEl.addEventListener("toggle", function () { paintLabels(); });
    window.__windView.stations = {
      on: function () { return staOn; }, set: setStaOn, pack: function () { return staPack; },
      selected: function () { return staSel; }, marks: function () { return staMarks; },
      err: function () { return staErr; }, load: loadStations, classify: classifySta, kind: staKind, kinds: STA_KIND
    };
    window.__windView.compass = function () { const s = cmpState(); return { on: cmpOn, mode: s.mode, dirDeg: s.dirDeg, set: setCmpOn }; };
    window.__windView.labels = function () { return { data: labData, visible: labVis, paint: paintLabels, reserved: reserved }; };

    $("w-locate").addEventListener("click", function () {
      if (!navigator.geolocation) { status.textContent = "Location isn't available in this browser."; status.hidden = false; return; }
      status.textContent = "Finding your location…"; status.hidden = false;
      navigator.geolocation.getCurrentPosition(function (p) {
        status.hidden = true;
        const ll = L.latLng(p.coords.latitude, p.coords.longitude);
        if (wind.sample(ll.lat, ll.lng)) map.setView(ll, Math.max(map.getZoom(), 8.5), { animate: !osReduce });
        if (grid) readAt(ll, "Your location");
      }, function () { status.textContent = "Location wasn't shared. Tap the map to read the model wind anywhere."; status.hidden = false; },
      { enableHighAccuracy: false, timeout: 10000, maximumAge: 300000 });
    });

    function setHour() {
      $("w-prev").disabled = ai === 0; $("w-next").disabled = ai === AHEAD.length - 1;
      const aEl = $("w-hour").querySelector(".w-hour-a"), bEl = $("w-hour").querySelector(".w-hour-b");
      const tag = fcstTag(grid) || "Fcst hour";
      const rel = grid ? relValid(grid.valid) : "";
      const near = grid && !rel && isFinite(validMs(grid.valid)) ? clockF.format(new Date(validMs(grid.valid))) : "";
      const lo = rel || near || "—";
      if (aEl.textContent !== tag) aEl.textContent = tag;
      if (bEl.textContent !== lo) bEl.textContent = lo;
    }
    onTick = function () {
      if (staOn) restyleMarks();
      if (!grid) return;
      setHour();
      if (read && !read.hidden && dot) readAt(dot.getLatLng());
    };
    function labelModel(g) {
      const hrrr = g.model === "hrrr";
      modelName = hrrr ? "HRRR" : "GFS";
      $("w-run-k").textContent = hrrr ? "HRRR run" : "GFS run";
      if (!wantHrrr) return;
      const src = $("w-src");
      src.textContent = hrrr ? "NOAA NCEP HRRR" : "NOAA NCEP GFS";
      src.href = hrrr ? "https://rapidrefresh.noaa.gov/hrrr/" : "https://www.nco.ncep.noaa.gov/pmb/products/gfs/";
      $("w-src-res").textContent = hrrr ? "3 km model forecast" : "0.25° (HRRR unavailable)";
    }
    function show(g) {
      grid = g;
      labelModel(g);
      $("w-run").textContent = M.etShort(g.run);
      $("w-valid").textContent = M.etShort(g.valid);
      $("w-fh").textContent = "F" + String(g.forecastHour).padStart(3, "0");
      const lag = relValid(g.valid);
      $("w-valid").parentNode.setAttribute("title", M.etLong(g.valid) + (lag && lag.indexOf("ago") >= 0 ? " · Behind current time" : ""));
      $("w-run").parentNode.setAttribute("title", M.etLong(g.run) + " · " + g.source);
      wind.setGrid(g);
      setHour();
      if (read && !read.hidden && dot) readAt(dot.getLatLng());
    }
    const memo = {};
    function loadFail(msg) {
      loading = false; status.textContent = msg; status.hidden = false;
      syncRetry();
      if (dot && !grid) readAt(dot.getLatLng());
    }
    async function load(i) {
      const my = ++req, a = AHEAD[i];
      loading = true; syncRetry();
      status.textContent = a ? "Loading model wind +" + a + " h…" : "Loading NOAA " + modelName + " model wind…"; status.hidden = false;
      try {
        const qs = [a ? "ahead=" + a : "", wantHrrr ? "model=hrrr" : ""].filter(Boolean).join("&");
        let g = memo[a];
        if (g && Math.abs(validMs(g.valid) - Date.now() - a * 36e5) > 54e5) g = null;
        if (!g) {
          const res = await fetch("/api/wind-grid" + (qs ? "?" + qs : ""));
          try { g = await res.json(); } catch (err) { g = {}; }
          if (res.status === 429) { loadFail((g && g.error) || "Too many requests. Please try again in a moment."); return; }
        }
        if (my !== req) return;
        if (!g.ok) { loadFail(g.error || "Model wind is unavailable right now."); return; }
        loading = false;
        memo[a] = g; ai = i;
        await yieldTask();
        show(g); status.hidden = true; syncRetry();
        paintLabels();
      } catch (e) { if (my === req) loadFail("Model wind is unavailable right now."); }
    }
    $("w-prev").addEventListener("click", function () { if (ai > 0) load(ai - 1); });
    $("w-next").addEventListener("click", function () { if (ai < AHEAD.length - 1) load(ai + 1); });
    setHour();
    load(0);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot); else boot();
})();
