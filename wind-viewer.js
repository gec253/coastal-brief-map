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
  // Phone (coarse, short side < 600): 30 fps.
  const phone = coarse && Math.min(screen.width, screen.height) < 600;
  const fps = /[?&]fps=60\b/.test(q) ? 60 : /[?&]fps=30\b/.test(q) ? 30 : phone ? 30 : 60;
  let pref = null; try { pref = localStorage.getItem("coastalBrief.windMotion"); } catch (e) {}
  let motion = pref === "on" ? true : pref === "off" ? false : !osReduce;
  const AHEAD = [0, 3, 6, 9, 12];
  // Private ?model=hrrr only. GFS default. Never blended.
  const wantHrrr = /[?&]model=hrrr\b/.test(q);
  let modelName = wantHrrr ? "HRRR" : "GFS";
  let ai = 0, grid = null, req = 0;
  // ?at=lat,lon centres the opening view if inside the data area.
  const AT = (/[?&]at=(-?\d{1,2}(?:\.\d{1,5})?),(-?\d{1,3}(?:\.\d{1,5})?)(?:&|$)/.exec(q) || []).slice(1).map(Number);
  const COAST = L.latLngBounds([33.75, -78.3], [36.55, -75.25]);
  const HOME = AT.length === 2 && AT[0] >= 32.5 && AT[0] <= 37.5 && AT[1] >= -80 && AT[1] <= -73
    ? L.latLngBounds([AT[0] - 0.9, AT[1] - 1.2], [AT[0] + 0.9, AT[1] + 1.2])
    : COAST;
  const yieldTask = () => new Promise((r) => (window.scheduler && scheduler.yield ? scheduler.yield().then(r) : setTimeout(r, 0)));

  // ET clock (now), not the model's valid time.
  const clockF = new Intl.DateTimeFormat("en-US", { timeZone: "America/New_York", hour: "numeric", minute: "2-digit" });
  let onTick = null;
  function nowMs() { return (typeof window.__windNow === "function") ? window.__windNow() : Date.now(); }
  function tick() { $("w-clock").textContent = clockF.format(new Date(nowMs())) + " ET"; if (onTick) onTick(); }
  tick(); setInterval(tick, 15000);

  function ramp() { const c = $("w-ramp"), x = c.getContext("2d"); for (let i = 0; i < c.width; i++) { x.fillStyle = "rgb(" + M.rgb(i / c.width * 36, dark).join(",") + ")"; x.fillRect(i, 0, 1, c.height); } }
  ramp();

  /* Theme: coastalBrief.theme light|dark; unset = follow the phone. */
  const THEME_STORE = "coastalBrief.theme";
  const sysDark = window.matchMedia ? matchMedia("(prefers-color-scheme: dark)") : null;
  const qTheme = (/[?&]theme=(light|dark)\b/.exec(q) || [])[1] || null;
  let onTheme = null;            // set by boot(): repaint coastline + particles
  function stored() { try { const t = localStorage.getItem(THEME_STORE); return t === "light" || t === "dark" ? t : null; } catch (e) { return null; } }
  function resolved() { return stored() || (sysDark && sysDark.matches ? "dark" : "light"); }
  const tbtn = $("w-theme");
  function syncToggle() {
    if (!tbtn) return;  // replaced by the shared Light / Dark / Auto control (theme_toggle.py)
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
    // maxZoom 9.5: Census file asks not to be shown larger than 1:500,000.
    const map = L.map("wmap", { zoomControl: true, attributionControl: false, zoomSnap: 0.5, minZoom: 5, maxZoom: 9.5, maxBounds: [[30, -84], [40, -69]], tap: true, fadeAnimation: false });
    map.zoomControl.setPosition("topright");
    map.fitBounds(HOME);
    // Attribution is static HTML (.w-attrib), painted with the chrome.
    await yieldTask();
    // Census land in CSS --coast-*, canvas tiles (never the LCP element).
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

    if (dark !== bootDark) onTheme();     // theme switched while the map was starting
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
    let staOn = false, staSel = null, staPack = null, staErr = null, staReq = 0, staAt = 0, staTimer = 0, staMarks = [];
    const STA_TTL = 90e3;
    const PRI_HI = "41025 41013 41064 41038 CLKN7 8651370 8652587 8654467 8656483 8658163 KHSE KILM KSUT";
    function esc(x) { return String(x == null ? "" : x).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").split(String.fromCharCode(34)).join("&quot;"); }
    function staKind(s) { return s.type === "nws" ? "air" : (s.type === "coops" || /[A-Z]/.test(s.id)) ? "pier" : "buoy"; }
    function staPri(s) { if (staSel && s.id === staSel) return 1000; if (PRI_HI.indexOf(s.id) >= 0) return /410/.test(s.id) ? 80 : 70; return s.optional ? 10 : 40; }
    function ageTxt(m) { if (m == null || !isFinite(m)) return ""; return m >= 120 ? Math.round(m / 60) + " h ago" : Math.round(m) + " min ago"; }
    // Recompute status and age from observedAt vs now so a cached payload cannot stay "Fresh".
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
      let num = (w.speedKt != null ? Math.round(w.speedKt) + " kt" : "");
      if (w.gustKt != null) num += (num ? ", gust " : "gust ") + Math.round(w.gustKt);
      if (w.dirDeg != null) num += " from " + (w.dirCompass || M.compass(w.dirDeg)) + " (" + Math.round(w.dirDeg) + "°)";
      const line = c.status === "stale" ? ("Stale — last report " + t) : (t + (c.ageMin != null ? " · " + ageTxt(c.ageMin) : "") + " · Fresh");
      return head + "<strong>" + num + "</strong><span class=\"w-sub\">" + line + "</span>" + src;
    }
    function staRow(id) { return staPack && (staPack.stations || []).filter(function (s) { return s.id === id; })[0]; }
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
          let badge = el.querySelector(".w-n");
          if (!hide && hit && hit.cluster && hit.m === it.m) {
            /* shown later */
          }
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
        } else if (badge) { badge.remove(); }
      });
      /* restore spiderfied markers' true coords when leaving max zoom is handled on redraw */
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
      // Home positions (in case a previous spiderfy moved them)
      staMarks.forEach(function (m) { if (m._home) m.setLatLng(m._home); });
      setTimeout(declutter, 0);
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
      if (staBtn) {
        staBtn.setAttribute("aria-pressed", String(staOn));
        staBtn.title = staOn ? "Hide observed NOAA stations" : "Show observed NOAA stations";
        staBtn.setAttribute("aria-label", staOn ? "Hide observed NOAA stations" : "Show observed NOAA stations");
      }
      if (staOn) loadStations();
      else {
        staReq++;
        stopStaTimer();
        clearMarks();
        setStaErr("");
        if (staSel) { staSel = null; if (dot) readAt(dot.getLatLng(), null, null); }
      }
    }
    if (staBtn) staBtn.addEventListener("click", function () { setStaOn(!staOn); });
    if (/[?&]stations=1\b/.test(q)) setStaOn(true);
    map.on("zoomend moveend", function () {
      if (!staOn || !staMarks.length) return;
      staMarks.forEach(function (m) { if (m._home) m.setLatLng(m._home); });
      declutter();
    });
    window.__windView.stations = {
      on: function () { return staOn; }, set: setStaOn, pack: function () { return staPack; },
      selected: function () { return staSel; }, marks: function () { return staMarks; },
      err: function () { return staErr; }, load: loadStations, classify: classifySta
    };

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
      if (!wantHrrr) return;                          // GFS default: attribution text stays as served
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
      } catch (e) { if (my === req) loadFail("Model wind is unavailable right now."); }
    }
    $("w-prev").addEventListener("click", function () { if (ai > 0) load(ai - 1); });
    $("w-next").addEventListener("click", function () { if (ai < AHEAD.length - 1) load(ai + 1); });
    setHour();
    load(0);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot); else boot();
})();
