/* /wind private viewer UI. The particle engine and wind math live in wind-lab.js (CBWind, CBWindMath).
   NOAA GFS MODEL FORECAST only: never labelled as a station reading. Times in America/New_York (ET). */
(function () {
  "use strict";
  const W = window.CBWind, M = window.CBWindMath;
  if (!W || !M || !window.L) return;
  const $ = (id) => document.getElementById(id);
  const q = location.search;
  const dark = document.documentElement.getAttribute("data-theme") === "dark";
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

  (function ramp() { const c = $("w-ramp"), x = c.getContext("2d"); for (let i = 0; i < c.width; i++) { x.fillStyle = "rgb(" + M.rgb(i / c.width * 36, dark).join(",") + ")"; x.fillRect(i, 0, 1, c.height); } })();

  const play = $("w-play"), status = $("w-status"), read = $("w-read");
  function setPlay() {
    play.setAttribute("aria-pressed", String(motion));
    $("w-play-lbl").textContent = motion ? "Pause" : "Flow";
    play.setAttribute("aria-label", motion ? "Pause flow animation (show static arrows)" : "Play flow animation");
  }
  setPlay();

  async function boot() {
    const map = L.map("wmap", { zoomControl: true, attributionControl: false, zoomSnap: 0.5, minZoom: 5, maxZoom: 11, maxBounds: [[30, -84], [40, -69]], tap: true });
    map.zoomControl.setPosition("topright");
    map.fitBounds(HOME);
    // Attribution is static HTML (.w-attrib) so it paints with the chrome, before Leaflet runs.
    await yieldTask();
    // Basemap tiles drawn into <canvas> (not <img>), tinted to the palette. They load after the chrome and
    // can never become the Largest Contentful Paint element the page waits on.
    const base = dark ? "Dark_Gray_Base" : "Light_Gray_Base";
    const TintTiles = L.GridLayer.extend({
      createTile: function (c, done) {
        const t = document.createElement("canvas"); t.width = t.height = 256;
        const img = new Image(); img.decoding = "async";
        img.onload = function () {
          const x = t.getContext("2d"); x.drawImage(img, 0, 0, 256, 256);
          x.globalCompositeOperation = dark ? "color" : "multiply";
          x.globalAlpha = dark ? 0.9 : 1; x.fillStyle = dark ? "#2C6A9C" : "#F4EFE6"; x.fillRect(0, 0, 256, 256);
          done(null, t);
        };
        img.onerror = function () { done(new Error("tile"), t); };
        img.src = "https://services.arcgisonline.com/ArcGIS/rest/services/Canvas/World_" + base + "/MapServer/tile/" + c.z + "/" + c.y + "/" + c.x;
        return t;
      },
    });
    new TintTiles({ maxNativeZoom: 12, maxZoom: 12, updateWhenIdle: true, keepBuffer: 1 }).addTo(map);
    await yieldTask();
    const wind = W.layer(map, {
      dark: dark, motion: motion, frameMs: fps === 30 ? 33.3 : 0,
      dprCap: phone ? 1.5 : 2, maxParticles: phone ? 1100 : 2200, density: phone ? 260 : 380,
      observe: $("w-stage"), perf: /[?&]perf=1\b/.test(q) ? $("w-stage") : null,
    });
    window.__windStats = wind.stats;
    window.__windView = { map: map, wind: wind, fps: fps, phone: phone, motion: () => motion, grid: () => grid };

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
