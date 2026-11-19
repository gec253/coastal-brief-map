/* /wind private viewer UI. The particle engine and wind math live in wind-lab.js (CBWind, CBWindMath).
   NOAA GFS MODEL FORECAST only: never labelled as a station reading. Times in America/New_York (ET). */
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
  // Phone = touch screen whose short side is under 600 CSS px. Phones draw at 30 fps for battery; iPad/desktop at the display rate (60).
  const phone = coarse && Math.min(screen.width, screen.height) < 600;
  const fps = /[?&]fps=60\b/.test(q) ? 60 : /[?&]fps=30\b/.test(q) ? 30 : phone ? 30 : 60;
  let pref = null; try { pref = localStorage.getItem("coastalBrief.windMotion"); } catch (e) {}
  let motion = pref === "on" ? true : pref === "off" ? false : !osReduce;
  const AHEAD = [0, 3, 6, 9, 12];
  let ai = 0, grid = null, req = 0;
  const HOME = L.latLngBounds([33.75, -78.3], [36.55, -75.25]);
  const yieldTask = () => new Promise((r) => (window.scheduler && scheduler.yield ? scheduler.yield().then(r) : setTimeout(r, 0)));

  // ET clock (now). Clearly separate from the model's valid time.
  const clockF = new Intl.DateTimeFormat("en-US", { timeZone: "America/New_York", hour: "numeric", minute: "2-digit" });
  function tick() { $("w-clock").textContent = clockF.format(new Date()) + " ET"; }
  tick(); setInterval(tick, 15000);

  function ramp() { const c = $("w-ramp"), x = c.getContext("2d"); for (let i = 0; i < c.width; i++) { x.fillStyle = "rgb(" + M.rgb(i / c.width * 36, dark).join(",") + ")"; x.fillRect(i, 0, 1, c.height); } }
  ramp();

  /* Theme: the same site preference as the Morning Brief and dashboard toggles (localStorage
     "coastalBrief.theme" = "light" | "dark"; nothing stored = follow the phone's appearance).
     wind.html applies it before first paint; this keeps it live without a reload: the sun/moon
     toggle, other tabs (storage event), the phone switching appearance, and back/forward cache. */
  const THEME_STORE = "coastalBrief.theme";
  const sysDark = window.matchMedia ? matchMedia("(prefers-color-scheme: dark)") : null;
  const qTheme = (/[?&]theme=(light|dark)\b/.exec(q) || [])[1] || null;
  let onTheme = null;            // set by boot(): repaint coastline + particles
  function stored() { try { const t = localStorage.getItem(THEME_STORE); return t === "light" || t === "dark" ? t : null; } catch (e) { return null; } }
  function resolved() { return stored() || (sysDark && sysDark.matches ? "dark" : "light"); }
  const tbtn = $("w-theme");
  function syncToggle() {
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
  tbtn.addEventListener("click", function () { applyTheme(dark ? "light" : "dark", true); });
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
    // maxZoom 9.5 (about 1:630,000 at 35°N): the Census file asks not to be shown larger than 1:500,000.
    const map = L.map("wmap", { zoomControl: true, attributionControl: false, zoomSnap: 0.5, minZoom: 5, maxZoom: 9.5, maxBounds: [[30, -84], [40, -69]], tap: true, fadeAnimation: false });
    map.zoomControl.setPosition("topright");
    map.fitBounds(HOME);
    // Attribution is static HTML (.w-attrib) so it paints with the chrome, before Leaflet runs.
    await yieldTask();
    // Coastline: our own Census land polygons in the page palette (CSS --coast-*), drawn into <canvas>
    // tiles one per frame. No third-party tiles; a canvas tile can never be the LCP element.
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
    window.__windView = { map: map, wind: wind, fps: fps, phone: phone, motion: () => motion, grid: () => grid, dark: () => dark };

    if (dark !== bootDark) onTheme();     // theme switched while the map was starting
    play.addEventListener("click", function () {
      motion = !motion; setPlay(); try { localStorage.setItem("coastalBrief.windMotion", motion ? "on" : "off"); } catch (e) {}
      wind.setMotion(motion);
    });
    $("w-center").addEventListener("click", function () { map.flyToBounds(HOME, { duration: osReduce ? 0 : 0.6 }); });

    let dot = null;
    function readAt(latlng, label) {
      const s = wind.sample(latlng.lat, latlng.lng);
      if (!dot) dot = L.circleMarker(latlng, { radius: 7, className: "w-dot", interactive: false }).addTo(map); else dot.setLatLng(latlng);
      if (!s) { read.innerHTML = "<strong>Outside the model area</strong><span class=\"w-sub\">This viewer loads GFS wind for 32.5–37.5°N, 73–80°W.</span>"; read.hidden = false; return; }
      read.innerHTML = "<strong>" + Math.round(s.kt) + " kt</strong> from " + M.compass(s.from) + " (" + Math.round(s.from) + "°) · model forecast" +
        "<span class=\"w-sub\">" + (label ? label + " · " : "") + latlng.lat.toFixed(2) + "°N " + Math.abs(latlng.lng).toFixed(2) + "°W · GFS 10 m, interpolated · valid " + M.etShort(grid.valid) + "</span>";
      read.hidden = false;
    }
    map.on("click", function (e) { if (grid) readAt(e.latlng); });
    $("w-locate").addEventListener("click", function () {
      // Only asks for location after this tap.
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
      const a = AHEAD[ai];
      $("w-prev").disabled = ai === 0; $("w-next").disabled = ai === AHEAD.length - 1;
      $("w-hour").querySelector(".w-hour-a").textContent = a === 0 ? "Nearest hour" : "Later";
      $("w-hour").querySelector(".w-hour-b").textContent = "+" + a + " h";
    }
    function show(g) {
      grid = g;
      $("w-run").textContent = M.etShort(g.run);
      $("w-valid").textContent = M.etShort(g.valid);
      $("w-fh").textContent = "F" + String(g.forecastHour).padStart(3, "0");
      $("w-valid").parentNode.setAttribute("title", M.etLong(g.valid));
      $("w-run").parentNode.setAttribute("title", M.etLong(g.run) + " · " + g.source);
      wind.setGrid(g);
      if (read && !read.hidden && dot) readAt(dot.getLatLng());
    }
    const memo = {};
    async function load(i) {
      const my = ++req, a = AHEAD[i];
      status.textContent = a ? "Loading model wind +" + a + " h…" : "Loading NOAA GFS model wind…"; status.hidden = false;
      try {
        const g = memo[a] || await fetch("/api/wind-grid" + (a ? "?ahead=" + a : "")).then((r) => r.json());
        if (my !== req) return;
        if (!g.ok) { status.textContent = g.error || "Model wind is unavailable right now."; return; }
        memo[a] = g; ai = i; setHour();
        await yieldTask();
        show(g); status.hidden = true;
      } catch (e) { if (my === req) status.textContent = "Model wind is unavailable right now."; }
    }
    $("w-prev").addEventListener("click", function () { if (ai > 0) load(ai - 1); });
    $("w-next").addEventListener("click", function () { if (ai < AHEAD.length - 1) load(ai + 1); });
    setHour();
    load(0);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot); else boot();
})();
