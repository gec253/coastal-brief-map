/* Wind particle prototype. Small custom canvas layer; no third-party code beyond Leaflet. */
(function () {
  "use strict";
  const meta = document.getElementById("wl-meta");
  const reduce = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;
  const map = L.map("wmap", { zoomControl: true, attributionControl: true }).setView([34.6, -76.6], 7);
  L.tileLayer("https://services.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}", {
    attribution: 'Tiles © <a href="https://www.esri.com/">Esri</a> · Wind: NOAA NCEP GFS (model forecast)', maxZoom: 12,
  }).addTo(map);
  const fmt = new Intl.DateTimeFormat("en-US", { timeZone: "America/New_York", weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
  const et = (iso) => fmt.format(new Date(iso.replace("Z", ":00Z"))) + " ET";

  fetch("/api/wind-grid").then((r) => r.json()).then(function (g) {
    if (!g.ok) { meta.textContent = g.error || "Model wind is unavailable."; return; }
    meta.innerHTML = "<strong>Model forecast</strong> · " + g.source + " · run " + et(g.run) + " · valid " + et(g.valid) + " (forecast hour " + g.forecastHour + ")";
    start(g);
  }).catch(function () { meta.textContent = "Model wind is unavailable right now."; });

  function start(g) {
    const north = (g.scan & 0x40) === 0; // row 0 is the northern edge
    function uv(lat, lon) {
      const fx = (lon - g.lo1) / g.dx;
      const fy = north ? (g.la1 - lat) / g.dy : (lat - g.la1) / g.dy;
      if (fx < 0 || fy < 0 || fx > g.nx - 1 || fy > g.ny - 1) return null;
      const x0 = Math.floor(fx), y0 = Math.floor(fy), x1 = Math.min(x0 + 1, g.nx - 1), y1 = Math.min(y0 + 1, g.ny - 1);
      const tx = fx - x0, ty = fy - y0;
      const at = (a, x, y) => a[y * g.nx + x];
      const bl = (a) => (at(a, x0, y0) * (1 - tx) + at(a, x1, y0) * tx) * (1 - ty) + (at(a, x0, y1) * (1 - tx) + at(a, x1, y1) * tx) * ty;
      return [bl(g.u), bl(g.v)];
    }
    const canvas = L.DomUtil.create("canvas", "wind-particles");
    const pane = map.getPanes().overlayPane;
    pane.appendChild(canvas);
    const ctx = canvas.getContext("2d");
    let parts = [], w = 0, h = 0, dpr = Math.min(window.devicePixelRatio || 1, 2), running = true, raf = 0;
    const N = () => Math.round(Math.min(1400, (w * h) / 900));
    function resize() {
      const s = map.getSize(); w = s.x; h = s.y;
      canvas.width = w * dpr; canvas.height = h * dpr; canvas.style.width = w + "px"; canvas.style.height = h + "px";
      L.DomUtil.setPosition(canvas, map.containerPointToLayerPoint([0, 0]));
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      parts = []; for (let i = 0; i < N(); i++) parts.push(spawn());
      ctx.clearRect(0, 0, w, h);
      if (reduce) drawArrows();
    }
    function spawn() { return { x: Math.random() * w, y: Math.random() * h, age: Math.floor(Math.random() * 80) }; }
    function color(kt) { return kt < 10 ? "rgba(43,111,143,0.8)" : kt < 20 ? "rgba(31,110,102,0.9)" : kt < 30 ? "rgba(169,99,58,0.95)" : "rgba(140,47,35,1)"; }
    function step() {
      if (!running) return;
      ctx.globalCompositeOperation = "destination-in";
      ctx.fillStyle = "rgba(0,0,0,0.92)"; ctx.fillRect(0, 0, w, h);
      ctx.globalCompositeOperation = "source-over";
      ctx.lineWidth = 1.3;
      const zoomScale = Math.pow(2, map.getZoom() - 7) * 0.18;
      for (const p of parts) {
        const ll = map.containerPointToLatLng([p.x, p.y]);
        const v = uv(ll.lat, ll.lng);
        if (!v || p.age++ > 90) { Object.assign(p, spawn(), { age: 0 }); continue; }
        const kt = Math.hypot(v[0], v[1]) * 1.94384;
        const nx = p.x + v[0] * zoomScale, ny = p.y - v[1] * zoomScale;
        ctx.strokeStyle = color(kt);
        ctx.beginPath(); ctx.moveTo(p.x, p.y); ctx.lineTo(nx, ny); ctx.stroke();
        p.x = nx; p.y = ny;
        if (p.x < 0 || p.y < 0 || p.x > w || p.y > h) Object.assign(p, spawn(), { age: 0 });
      }
      raf = requestAnimationFrame(step);
    }
    function drawArrows() {
      ctx.clearRect(0, 0, w, h);
      for (let y = 20; y < h; y += 44) for (let x = 20; x < w; x += 44) {
        const ll = map.containerPointToLatLng([x, y]); const v = uv(ll.lat, ll.lng); if (!v) continue;
        const kt = Math.hypot(v[0], v[1]) * 1.94384, a = Math.atan2(-v[1], v[0]), len = 8 + Math.min(kt, 40) * 0.4;
        ctx.save(); ctx.translate(x, y); ctx.rotate(a); ctx.strokeStyle = color(kt); ctx.fillStyle = color(kt); ctx.lineWidth = 1.6;
        ctx.beginPath(); ctx.moveTo(-len / 2, 0); ctx.lineTo(len / 2, 0); ctx.stroke();
        ctx.beginPath(); ctx.moveTo(len / 2, 0); ctx.lineTo(len / 2 - 5, -3.5); ctx.lineTo(len / 2 - 5, 3.5); ctx.fill(); ctx.restore();
      }
    }
    map.on("movestart zoomstart", function () { running = false; cancelAnimationFrame(raf); ctx.clearRect(0, 0, w, h); });
    map.on("moveend zoomend resize", function () { resize(); if (!reduce) { running = true; step(); } });
    document.addEventListener("visibilitychange", function () {
      if (document.hidden) { running = false; cancelAnimationFrame(raf); }
      else if (!reduce) { running = true; step(); }
    });
    resize();
    if (!reduce) step();
  }
})();
