/* Wind particle engine, shared by /lab/wind (prototype page) and /wind (private viewer).
   Small custom canvas layer; no third-party code beyond Leaflet.
   Performance notes: lat/lon per pixel column/row are precomputed (Web Mercator: lon depends only on x,
   lat only on y), particles live in typed arrays, strokes are batched into a few colour buckets, the
   loop pauses when the tab is hidden, the map is off-screen, or the map is moving, and the particle
   count backs off if frames run long. Values are a MODEL FORECAST (NOAA GFS), never observations.
   The pure math at the top (WindMath) also loads in Node for tests/test_wind_viewer.py. */
(function (root) {
  "use strict";
  const KT = 1.943844;
  const DIRS = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"];
  // Speed ramp (knots): navy -> Carolina blue -> cyan. Dark: luminous, white-cyan tip.
  const STOPS_DARK = [[0, [116, 154, 184]], [8, [75, 156, 211]], [15, [88, 198, 222]], [22, [130, 226, 236]], [30, [188, 242, 250]], [38, [236, 252, 255]]];
  const STOPS_LIGHT = [[0, [20, 46, 70]], [8, [30, 82, 118]], [15, [34, 114, 164]], [22, [24, 122, 162]], [30, [12, 106, 134]], [38, [4, 86, 108]]];
  function rgb(kt, dark) {
    const S = dark ? STOPS_DARK : STOPS_LIGHT;
    for (let i = 1; i < S.length; i++) if (kt <= S[i][0]) {
      const a = S[i - 1], b = S[i], t = (kt - a[0]) / (b[0] - a[0]);
      return a[1].map((c, k) => Math.round(c + (b[1][k] - c) * t));
    }
    return S[S.length - 1][1];
  }
  // Bilinear U/V (m/s) from the /api/wind-grid payload. Returns false outside the grid.
  function makeSampler(g) {
    const north = (g.scan & 0x40) === 0; // row 0 is the northern edge
    const U = Float32Array.from(g.u), V = Float32Array.from(g.v), nx = g.nx, ny = g.ny;
    return function uvAt(lat, lon, out) {
      const fx = (lon - g.lo1) / g.dx, fy = north ? (g.la1 - lat) / g.dy : (lat - g.la1) / g.dy;
      if (!(fx >= 0 && fy >= 0 && fx <= nx - 1 && fy <= ny - 1)) return false;
      const x0 = fx | 0, y0 = fy | 0, x1 = x0 + 1 < nx ? x0 + 1 : x0, y1 = y0 + 1 < ny ? y0 + 1 : y0, tx = fx - x0, ty = fy - y0;
      const i00 = y0 * nx + x0, i10 = y0 * nx + x1, i01 = y1 * nx + x0, i11 = y1 * nx + x1;
      const w00 = (1 - tx) * (1 - ty), w10 = tx * (1 - ty), w01 = (1 - tx) * ty, w11 = tx * ty;
      out[0] = U[i00] * w00 + U[i10] * w10 + U[i01] * w01 + U[i11] * w11;
      out[1] = V[i00] * w00 + V[i10] * w10 + V[i01] * w01 + V[i11] * w11;
      return true;
    };
  }
  const speedKt = (u, v) => Math.hypot(u, v) * KT;
  const fromDeg = (u, v) => (Math.atan2(-u, -v) * 180 / Math.PI + 360) % 360; // direction wind blows FROM
  const compass = (deg) => DIRS[Math.round(deg / 22.5) % 16];
  // "2026-11-19T21:00Z" -> "Thu 4:00 PM ET" (America/New_York, with the ET label).
  const ETF = new Intl.DateTimeFormat("en-US", { timeZone: "America/New_York", weekday: "short", hour: "numeric", minute: "2-digit" });
  const ETFD = new Intl.DateTimeFormat("en-US", { timeZone: "America/New_York", weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
  const parseIso = (iso) => new Date(/T\d\d:\d\dZ$/.test(iso) ? iso.replace("Z", ":00Z") : iso);
  const etShort = (iso) => ETF.format(parseIso(iso)) + " ET";
  const etLong = (iso) => ETFD.format(parseIso(iso)) + " ET";
  const WindMath = { KT, DIRS, rgb, makeSampler, speedKt, fromDeg, compass, etShort, etLong };
  if (typeof module === "object" && module.exports) { module.exports = WindMath; return; }
  root.CBWindMath = WindMath;
  if (typeof document === "undefined" || !root.L) return;

  /* Particle layer on a Leaflet map. opts: dark, motion, frameMs (0 = every rAF, 33.3 = 30 fps),
     dprCap, maxParticles, density (px² per particle), observe (element for IntersectionObserver),
     perf (HUD element parent or null). Returns { setGrid, setMotion, setDark, sample, stats }. */
  function layer(map, opts) {
    let dark = !!opts.dark;
    const BUCKETS = 12, BMAX = 36;
    const bucketColor = [], bucketWidth = [];
    function palette() { for (let i = 0; i < BUCKETS; i++) { const kt = (i + 0.5) * BMAX / BUCKETS, c = rgb(kt, dark); bucketColor[i] = "rgba(" + c.join(",") + "," + (0.52 + 0.48 * i / (BUCKETS - 1)).toFixed(2) + ")"; bucketWidth[i] = 0.85 + 1.45 * i / (BUCKETS - 1); } }
    palette();
    let uvAt = null, motion = !!opts.motion;
    const canvas = L.DomUtil.create("canvas", "wind-particles");
    canvas.setAttribute("aria-hidden", "true");
    map.getPanes().overlayPane.appendChild(canvas);
    const ctx = canvas.getContext("2d");
    const dpr = Math.min(window.devicePixelRatio || 1, opts.dprCap || 2);
    let w = 0, h = 0, lonX = null, latY = null, n = 0, maxN = 0;
    let PX, PY, AGE, running = false, raf = 0, moving = false, visible = true, last = 0, slow = 0;
    const tmp = [0, 0];
    const FRAME_MS = opts.frameMs || 0, MAXAGE = FRAME_MS ? 78 : 130;
    let lastDraw = 0;
    const bx = Array.from({ length: BUCKETS }, () => []);
    const stats = { frames: 0, times: [], particles: 0, dpr: dpr, frameMs: FRAME_MS, intervals: [] };

    function layout() {
      const s = map.getSize(); w = s.x; h = s.y;
      canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr); canvas.style.width = w + "px"; canvas.style.height = h + "px";
      L.DomUtil.setPosition(canvas, map.containerPointToLayerPoint([0, 0]));
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.lineCap = "round"; ctx.lineJoin = "round";
      // Web Mercator: lon depends only on x, lat only on y. Two cheap linear passes, no per-pixel unproject.
      lonX = new Float32Array(w); latY = new Float32Array(h);
      const lon0 = map.containerPointToLatLng([0, 0]).lng, lon1 = map.containerPointToLatLng([w, 0]).lng;
      for (let x = 0; x < w; x++) lonX[x] = lon0 + (lon1 - lon0) * x / w;
      for (let y = 0; y < h; y++) latY[y] = map.containerPointToLatLng([0, y]).lat;
      maxN = Math.round(Math.min(opts.maxParticles || 2200, (w * h) / (opts.density || 380)));
      n = Math.min(n || maxN, maxN);
      PX = new Float32Array(maxN); PY = new Float32Array(maxN); AGE = new Uint8Array(maxN);
      for (let i = 0; i < maxN; i++) spawn(i, true);
      ctx.clearRect(0, 0, w, h);
      if (!motion) drawArrows();
    }
    function spawn(i, randomAge) {
      if (randomAge || !w || !h) { PX[i] = Math.random() * w; PY[i] = Math.random() * h; }
      else { const e = (Math.random() * 4) | 0; PX[i] = e === 0 ? 0 : e === 1 ? w - 1 : Math.random() * w; PY[i] = e === 2 ? 0 : e === 3 ? h - 1 : Math.random() * h; }
      AGE[i] = randomAge ? (Math.random() * 80) | 0 : 0;
    }
    function frame(ts) {
      raf = 0;
      if (!running) return;
      // Phones draw at 30 fps (particles move twice as far per step), halving fill and raster cost.
      if (FRAME_MS && ts - lastDraw < FRAME_MS - 4) { raf = requestAnimationFrame(frame); return; }
      const gap = lastDraw ? ts - lastDraw : 16.7;
      const stepMul = Math.min(2.5, gap / 16.7);
      if (lastDraw && stats.intervals.length < 2000) stats.intervals.push(gap);
      lastDraw = ts;
      const t0 = performance.now();
      ctx.globalCompositeOperation = "destination-in";
      ctx.fillStyle = FRAME_MS ? "rgba(0,0,0,0.90)" : "rgba(0,0,0,0.945)"; ctx.fillRect(0, 0, w, h);
      ctx.globalCompositeOperation = "source-over";
      const k = Math.pow(2, map.getZoom() - 7) * 0.16 * stepMul;
      for (let b = 0; b < BUCKETS; b++) bx[b].length = 0;
      for (let i = 0; i < n; i++) {
        const x = PX[i], y = PY[i], xi = x | 0, yi = y | 0;
        if (xi < 0 || yi < 0 || xi >= w || yi >= h || ++AGE[i] > MAXAGE || !uvAt(latY[yi], lonX[xi], tmp)) { spawn(i, false); continue; }
        const kt = Math.sqrt(tmp[0] * tmp[0] + tmp[1] * tmp[1]) * KT;
        const nx2 = x + tmp[0] * k, ny2 = y - tmp[1] * k;
        let b = (kt / BMAX * BUCKETS) | 0; if (b >= BUCKETS) b = BUCKETS - 1;
        bx[b].push(x, y, nx2, ny2);
        PX[i] = nx2; PY[i] = ny2;
      }
      for (let b = 0; b < BUCKETS; b++) {
        const a = bx[b]; if (!a.length) continue;
        ctx.strokeStyle = bucketColor[b]; ctx.lineWidth = bucketWidth[b]; ctx.beginPath();
        for (let j = 0; j < a.length; j += 4) { ctx.moveTo(a[j], a[j + 1]); ctx.lineTo(a[j + 2], a[j + 3]); }
        ctx.stroke();
      }
      const dt = performance.now() - t0;
      stats.frames++; if (stats.times.length < 2000) stats.times.push(dt); stats.particles = n;
      // Back off if the main-thread draw cost stays high (keeps older phones smooth and cooler).
      if (dt > 9) { if (++slow > 20 && n > 300) { n = Math.round(n * 0.8); slow = 0; } } else slow = 0;
      if (opts.perf && ts - last > 500) { last = ts; hud(dt); }
      raf = requestAnimationFrame(frame);
    }
    let hudEl = null, fpsT = performance.now(), fpsN = 0;
    function hud(dt) {
      if (!hudEl) { hudEl = document.createElement("div"); hudEl.className = "wl-hud"; opts.perf.appendChild(hudEl); }
      const now = performance.now(); const fps = (stats.frames - fpsN) * 1000 / (now - fpsT); fpsN = stats.frames; fpsT = now;
      const mem = performance.memory ? " · heap " + (performance.memory.usedJSHeapSize / 1048576).toFixed(1) + " MB" : "";
      hudEl.textContent = fps.toFixed(0) + " fps · draw " + dt.toFixed(1) + " ms · " + n + " particles" + mem;
    }
    function drawArrows() {
      ctx.clearRect(0, 0, w, h);
      if (!uvAt) return;
      const step = 46;
      for (let y = step / 2; y < h; y += step) for (let x = step / 2; x < w; x += step) {
        if (!uvAt(latY[y | 0], lonX[x | 0], tmp)) continue;
        const kt = Math.hypot(tmp[0], tmp[1]) * KT, a = Math.atan2(-tmp[1], tmp[0]), len = 10 + Math.min(kt, 40) * 0.45;
        const c = "rgb(" + rgb(kt, dark).join(",") + ")";
        ctx.save(); ctx.translate(x, y); ctx.rotate(a); ctx.strokeStyle = c; ctx.fillStyle = c; ctx.lineWidth = 1.8; ctx.lineCap = "round";
        ctx.beginPath(); ctx.moveTo(-len / 2, 0); ctx.lineTo(len / 2 - 3, 0); ctx.stroke();
        ctx.beginPath(); ctx.moveTo(len / 2, 0); ctx.lineTo(len / 2 - 6, -4); ctx.lineTo(len / 2 - 6, 4); ctx.closePath(); ctx.fill(); ctx.restore();
      }
    }
    function want() { return !!uvAt && motion && visible && !moving && !document.hidden; }
    function sync() {
      const go = want();
      if (go && !running) { running = true; lastDraw = 0; if (!raf) raf = requestAnimationFrame(frame); }
      else if (!go && running) { running = false; if (raf) cancelAnimationFrame(raf); raf = 0; }
    }
    map.on("movestart zoomstart", function () { moving = true; sync(); ctx.clearRect(0, 0, w, h); });
    map.on("moveend zoomend resize", function () { moving = false; layout(); sync(); });
    document.addEventListener("visibilitychange", sync);
    if ("IntersectionObserver" in window && opts.observe) new IntersectionObserver(function (es) { visible = es[0].isIntersecting; sync(); }, { threshold: 0.05 }).observe(opts.observe);
    let laidOut = false;
    return {
      stats: stats,
      setGrid: function (g) {
        uvAt = makeSampler(g);
        if (!laidOut) { laidOut = true; layout(); } else { ctx.clearRect(0, 0, w, h); for (let i = 0; i < maxN; i++) spawn(i, true); if (!motion) drawArrows(); }
        sync();
      },
      setMotion: function (on) { motion = !!on; ctx.clearRect(0, 0, w, h); if (!motion) drawArrows(); sync(); },
      // Day/night palette swap in place: particles, positions, grid and loop are untouched.
      setDark: function (on) { on = !!on; if (on === dark) return; dark = on; palette(); if (!motion && laidOut) drawArrows(); },
      sample: function (lat, lon) {
        const o = [0, 0];
        if (!uvAt || !uvAt(lat, lon, o)) return null;
        return { u: o[0], v: o[1], kt: speedKt(o[0], o[1]), from: fromDeg(o[0], o[1]) };
      },
    };
  }
  root.CBWind = { layer: layer };

  // ---------------------------------------------------------------- /lab/wind prototype page
  const meta = document.getElementById("wl-meta");
  if (!meta) return;
  const $ = (id) => document.getElementById(id);
  const btn = $("wl-motion"), readout = $("wl-read");
  const osReduce = !!(window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches);
  let pref = null; try { pref = localStorage.getItem("coastalBrief.windMotion"); } catch (e) {}
  let motion = pref === "on" ? true : pref === "off" ? false : !osReduce;
  const dark = document.documentElement.getAttribute("data-theme") === "dark";
  const map = L.map("wmap", { zoomControl: true, attributionControl: true }).setView([34.9, -76.4], 7);
  const base = dark ? "Dark_Gray_Base" : "Light_Gray_Base";
  L.tileLayer("https://services.arcgisonline.com/ArcGIS/rest/services/Canvas/World_" + base + "/MapServer/tile/{z}/{y}/{x}", {
    attribution: 'Tiles © <a href="https://www.esri.com/">Esri</a> · Wind: NOAA NCEP GFS (model forecast)', maxZoom: 12,
  }).addTo(map);
  (function ramp() { const c = $("wl-ramp"), x = c.getContext("2d"); for (let i = 0; i < 150; i++) { x.fillStyle = "rgb(" + rgb(i / 150 * 36, dark).join(",") + ")"; x.fillRect(i, 0, 1, 8); } })();
  function setBtn() { btn.setAttribute("aria-pressed", String(motion)); btn.textContent = motion ? "Motion: on" : "Motion: off (arrows)"; }
  setBtn();
  const coarse = matchMedia("(pointer: coarse)").matches;
  const wind = layer(map, {
    dark: dark, motion: motion, frameMs: coarse && !/[?&]fps=60/.test(location.search) ? 33.3 : 0,
    dprCap: coarse ? 1.5 : 2, maxParticles: coarse ? 1100 : 2200, density: coarse ? 260 : 380,
    observe: $("wmap"), perf: /[?&]perf=1/.test(location.search) ? document.querySelector(".wl-stage") : null,
  });
  window.__windStats = wind.stats;
  window.__windSample = function (lat, lon) { const s = wind.sample(lat, lon); return s ? [s.u, s.v] : null; };
  fetch("/api/wind-grid").then((r) => r.json()).then(function (g) {
    if (!g.ok) { meta.textContent = g.error || "Model wind is unavailable."; return; }
    meta.innerHTML = "<strong>Model forecast</strong> · " + g.source + " · run " + etLong(g.run) + " · valid " + etLong(g.valid) + " (forecast hour " + g.forecastHour + ")";
    wind.setGrid(g);
  }).catch(function () { meta.textContent = "Model wind is unavailable right now."; });
  btn.addEventListener("click", function () {
    motion = !motion; setBtn(); try { localStorage.setItem("coastalBrief.windMotion", motion ? "on" : "off"); } catch (e) {}
    wind.setMotion(motion);
  });
  map.on("click", function (e) {
    const s = wind.sample(e.latlng.lat, e.latlng.lng);
    if (!s) { readout.textContent = "Outside the model area loaded for this prototype."; readout.hidden = false; return; }
    readout.innerHTML = "<strong>Model forecast</strong> " + Math.round(s.kt) + " kt from " + compass(s.from) + " (" + Math.round(s.from) + "°)<br>" +
      e.latlng.lat.toFixed(2) + "°N " + Math.abs(e.latlng.lng).toFixed(2) + "°W · GFS 10 m, interpolated";
    readout.hidden = false;
  });
})(typeof window !== "undefined" ? window : this);
