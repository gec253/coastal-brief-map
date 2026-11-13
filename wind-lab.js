/* Wind particle prototype. Small custom canvas layer; no third-party code beyond Leaflet.
   Performance notes: lat/lon per pixel column/row are precomputed (Web Mercator: lon depends only on x,
   lat only on y), particles live in typed arrays, strokes are batched into a few colour buckets, the
   loop pauses when the tab is hidden, the map is off-screen, or the map is moving, and the particle
   count backs off if frames run long. */
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const meta = $("wl-meta"), btn = $("wl-motion"), readout = $("wl-read");
  const osReduce = !!(window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches);
  let pref = null; try { pref = localStorage.getItem("coastalBrief.windMotion"); } catch (e) {}
  let motion = pref === "on" ? true : pref === "off" ? false : !osReduce;
  const dark = document.documentElement.getAttribute("data-theme") === "dark";
  const perf = /[?&]perf=1/.test(location.search);

  const map = L.map("wmap", { zoomControl: true, attributionControl: true }).setView([34.9, -76.4], 7);
  const base = dark ? "Dark_Gray_Base" : "Light_Gray_Base";
  L.tileLayer("https://services.arcgisonline.com/ArcGIS/rest/services/Canvas/World_" + base + "/MapServer/tile/{z}/{y}/{x}", {
    attribution: 'Tiles © <a href="https://www.esri.com/">Esri</a> · Wind: NOAA NCEP GFS (model forecast)', maxZoom: 12,
  }).addTo(map);
  const fmt = new Intl.DateTimeFormat("en-US", { timeZone: "America/New_York", weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
  const et = (iso) => fmt.format(new Date(iso.replace("Z", ":00Z"))) + " ET";

  // Speed ramp in knots. Light map: deeper inks; dark map: luminous tints.
  const STOPS = dark
    ? [[0, [120, 160, 190]], [8, [110, 200, 215]], [15, [140, 220, 170]], [22, [235, 215, 120]], [30, [245, 150, 90]], [38, [240, 95, 95]]]
    : [[0, [70, 110, 140]], [8, [25, 120, 150]], [15, [30, 125, 95]], [22, [170, 130, 30]], [30, [190, 85, 40]], [38, [150, 35, 35]]];
  function rgb(kt) {
    for (let i = 1; i < STOPS.length; i++) if (kt <= STOPS[i][0]) {
      const a = STOPS[i - 1], b = STOPS[i], t = (kt - a[0]) / (b[0] - a[0]);
      return a[1].map((c, k) => Math.round(c + (b[1][k] - c) * t));
    }
    return STOPS[STOPS.length - 1][1];
  }
  const BUCKETS = 12, BMAX = 36;
  const bucketColor = [], bucketWidth = [];
  for (let i = 0; i < BUCKETS; i++) { const kt = (i + 0.5) * BMAX / BUCKETS, c = rgb(kt); bucketColor.push("rgba(" + c.join(",") + "," + (0.55 + 0.45 * i / (BUCKETS - 1)).toFixed(2) + ")"); bucketWidth.push(0.9 + 1.5 * i / (BUCKETS - 1)); }
  (function ramp() { const c = $("wl-ramp"), x = c.getContext("2d"); for (let i = 0; i < 150; i++) { x.fillStyle = "rgb(" + rgb(i / 150 * 36).join(",") + ")"; x.fillRect(i, 0, 1, 8); } })();

  function setBtn() { btn.setAttribute("aria-pressed", String(motion)); btn.textContent = motion ? "Motion: on" : "Motion: off (arrows)"; }
  setBtn();

  fetch("/api/wind-grid").then((r) => r.json()).then(function (g) {
    if (!g.ok) { meta.textContent = g.error || "Model wind is unavailable."; return; }
    meta.innerHTML = "<strong>Model forecast</strong> · " + g.source + " · run " + et(g.run) + " · valid " + et(g.valid) + " (forecast hour " + g.forecastHour + ")";
    start(g);
  }).catch(function () { meta.textContent = "Model wind is unavailable right now."; });

  function start(g) {
    const north = (g.scan & 0x40) === 0; // row 0 is the northern edge
    const U = Float32Array.from(g.u), V = Float32Array.from(g.v), nx = g.nx, ny = g.ny;
    function uvAt(lat, lon, out) {
      const fx = (lon - g.lo1) / g.dx, fy = north ? (g.la1 - lat) / g.dy : (lat - g.la1) / g.dy;
      if (!(fx >= 0 && fy >= 0 && fx <= nx - 1 && fy <= ny - 1)) return false;
      const x0 = fx | 0, y0 = fy | 0, x1 = x0 + 1 < nx ? x0 + 1 : x0, y1 = y0 + 1 < ny ? y0 + 1 : y0, tx = fx - x0, ty = fy - y0;
      const i00 = y0 * nx + x0, i10 = y0 * nx + x1, i01 = y1 * nx + x0, i11 = y1 * nx + x1;
      const w00 = (1 - tx) * (1 - ty), w10 = tx * (1 - ty), w01 = (1 - tx) * ty, w11 = tx * ty;
      out[0] = U[i00] * w00 + U[i10] * w10 + U[i01] * w01 + U[i11] * w11;
      out[1] = V[i00] * w00 + V[i10] * w10 + V[i01] * w01 + V[i11] * w11;
      return true;
    }
    window.__windSample = function (lat, lon) { const o = [0, 0]; return uvAt(lat, lon, o) ? o : null; };

    const canvas = L.DomUtil.create("canvas", "wind-particles");
    map.getPanes().overlayPane.appendChild(canvas);
    const ctx = canvas.getContext("2d");
    const coarse = matchMedia("(pointer: coarse)").matches;
    const dpr = Math.min(window.devicePixelRatio || 1, coarse ? 1.5 : 2);
    let w = 0, h = 0, lonX = null, latY = null, n = 0, maxN = 0;
    let PX, PY, AGE, running = false, raf = 0, moving = false, visible = true, last = 0, slow = 0;
    const tmp = [0, 0];
    const FRAME_MS = coarse && !/[?&]fps=60/.test(location.search) ? 33.3 : 0, MAXAGE = FRAME_MS ? 60 : 110;
    let lastDraw = 0;
    const bx = Array.from({ length: BUCKETS }, () => []);
    const stats = window.__windStats = { frames: 0, times: [], particles: 0, dpr: dpr, frameMs: 0 };

    function layout() {
      const s = map.getSize(); w = s.x; h = s.y;
      canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr); canvas.style.width = w + "px"; canvas.style.height = h + "px";
      L.DomUtil.setPosition(canvas, map.containerPointToLayerPoint([0, 0]));
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      lonX = new Float32Array(w); latY = new Float32Array(h);
      for (let x = 0; x < w; x++) lonX[x] = map.containerPointToLatLng([x, 0]).lng;
      for (let y = 0; y < h; y++) latY[y] = map.containerPointToLatLng([0, y]).lat;
      maxN = Math.round(Math.min(coarse ? 1100 : 2200, (w * h) / (coarse ? 260 : 380)));
      n = Math.min(n || maxN, maxN);
      PX = new Float32Array(maxN); PY = new Float32Array(maxN); AGE = new Uint8Array(maxN);
      for (let i = 0; i < maxN; i++) spawn(i, true);
      ctx.clearRect(0, 0, w, h);
      if (!motion) drawArrows();
    }
    function spawn(i, randomAge) { PX[i] = Math.random() * w; PY[i] = Math.random() * h; AGE[i] = randomAge ? (Math.random() * 100) | 0 : 0; }
    function frame(ts) {
      raf = 0;
      if (!running) return;
      // Phones draw at 30 fps (particles move twice as far per step), halving fill and raster cost.
      if (FRAME_MS && ts - lastDraw < FRAME_MS - 4) { raf = requestAnimationFrame(frame); return; }
      const stepMul = FRAME_MS && lastDraw ? Math.min(2.5, (ts - lastDraw) / 16.7) : 1;
      lastDraw = ts;
      const t0 = performance.now();
      ctx.globalCompositeOperation = "destination-in";
      ctx.fillStyle = FRAME_MS ? "rgba(0,0,0,0.87)" : "rgba(0,0,0,0.93)"; ctx.fillRect(0, 0, w, h);
      ctx.globalCompositeOperation = "source-over";
      const k = Math.pow(2, map.getZoom() - 7) * 0.16 * stepMul;
      for (let b = 0; b < BUCKETS; b++) bx[b].length = 0;
      for (let i = 0; i < n; i++) {
        const x = PX[i], y = PY[i], xi = x | 0, yi = y | 0;
        if (xi < 0 || yi < 0 || xi >= w || yi >= h || ++AGE[i] > MAXAGE || !uvAt(latY[yi], lonX[xi], tmp)) { spawn(i, false); continue; }
        const kt = Math.sqrt(tmp[0] * tmp[0] + tmp[1] * tmp[1]) * 1.94384;
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
      stats.frames++; if (stats.times.length < 2000) stats.times.push(dt); stats.particles = n; stats.frameMs = FRAME_MS;
      // Back off if the main-thread draw cost stays high (keeps older phones smooth and cooler).
      if (dt > 9) { if (++slow > 20 && n > 300) { n = Math.round(n * 0.8); slow = 0; } } else slow = 0;
      if (perf && ts - last > 500) { last = ts; hud(dt); }
      raf = requestAnimationFrame(frame);
    }
    let hudEl = null, fpsT = performance.now(), fpsN = 0;
    function hud(dt) {
      if (!hudEl) { hudEl = document.createElement("div"); hudEl.className = "wl-hud"; document.querySelector(".wl-stage").appendChild(hudEl); }
      const now = performance.now(); const fps = (stats.frames - fpsN) * 1000 / (now - fpsT); fpsN = stats.frames; fpsT = now;
      const mem = performance.memory ? " · heap " + (performance.memory.usedJSHeapSize / 1048576).toFixed(1) + " MB" : "";
      hudEl.textContent = fps.toFixed(0) + " fps · draw " + dt.toFixed(1) + " ms · " + n + " particles" + mem;
    }
    function drawArrows() {
      ctx.clearRect(0, 0, w, h);
      const step = 46;
      for (let y = step / 2; y < h; y += step) for (let x = step / 2; x < w; x += step) {
        if (!uvAt(latY[y | 0], lonX[x | 0], tmp)) continue;
        const kt = Math.hypot(tmp[0], tmp[1]) * 1.94384, a = Math.atan2(-tmp[1], tmp[0]), len = 10 + Math.min(kt, 40) * 0.45;
        const c = "rgb(" + rgb(kt).join(",") + ")";
        ctx.save(); ctx.translate(x, y); ctx.rotate(a); ctx.strokeStyle = c; ctx.fillStyle = c; ctx.lineWidth = 1.8; ctx.lineCap = "round";
        ctx.beginPath(); ctx.moveTo(-len / 2, 0); ctx.lineTo(len / 2 - 3, 0); ctx.stroke();
        ctx.beginPath(); ctx.moveTo(len / 2, 0); ctx.lineTo(len / 2 - 6, -4); ctx.lineTo(len / 2 - 6, 4); ctx.closePath(); ctx.fill(); ctx.restore();
      }
    }
    function want() { return motion && visible && !moving && !document.hidden; }
    function sync() {
      const go = want();
      if (go && !running) { running = true; if (!raf) raf = requestAnimationFrame(frame); }
      else if (!go && running) { running = false; if (raf) cancelAnimationFrame(raf); raf = 0; }
    }
    map.on("movestart zoomstart", function () { moving = true; sync(); ctx.clearRect(0, 0, w, h); });
    map.on("moveend zoomend resize", function () { moving = false; layout(); sync(); });
    document.addEventListener("visibilitychange", sync);
    if ("IntersectionObserver" in window) new IntersectionObserver(function (es) { visible = es[0].isIntersecting; sync(); }, { threshold: 0.05 }).observe($("wmap"));
    btn.addEventListener("click", function () {
      motion = !motion; setBtn(); try { localStorage.setItem("coastalBrief.windMotion", motion ? "on" : "off"); } catch (e) {}
      ctx.clearRect(0, 0, w, h); if (!motion) drawArrows(); sync();
    });
    const DIRS = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"];
    map.on("click", function (e) {
      const o = [0, 0];
      if (!uvAt(e.latlng.lat, e.latlng.lng, o)) { readout.textContent = "Outside the model area loaded for this prototype."; readout.hidden = false; return; }
      const kt = Math.hypot(o[0], o[1]) * 1.94384, from = (Math.atan2(-o[0], -o[1]) * 180 / Math.PI + 360) % 360;
      readout.innerHTML = "<strong>Model forecast</strong> " + Math.round(kt) + " kt from " + DIRS[Math.round(from / 22.5) % 16] + " (" + Math.round(from) + "°)<br>" +
        e.latlng.lat.toFixed(2) + "°N " + Math.abs(e.latlng.lng).toFixed(2) + "°W · GFS 10 m, interpolated";
      readout.hidden = false;
    });
    layout(); sync();
  }
})();
