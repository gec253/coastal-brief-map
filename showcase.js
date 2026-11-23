/* PRIVATE design preview (showcase.py): static Wind & Radar instrument snapshots on the homepage.
   Loads nothing until the section is near the viewport. Wind: one static streak snapshot of the real
   NOAA GFS grid (/api/home-wind), no animation. Radar: only the LATEST OBSERVED frame, a few z7 tiles
   through the existing proxy (/api/radar/tile/...), never forecast frames, never the animation. */
(function () {
  "use strict";
  const sec = document.getElementById("showcase");
  if (!sec || sec.dataset.unsupported) return;
  const KT = 1.943844, D = Math.PI / 180;
  const DIRS = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"];
  // Focus comes from the server (the region's own NWS forecast point, data/regions.json). Crystal Coast
  // keeps its original framing; these defaults match it exactly.
  const num = (k, d) => { const n = parseFloat(sec.dataset[k]); return isFinite(n) ? n : d; };
  const HOME = { lat: num("lat", 34.72), lon: num("lon", -76.70), name: sec.dataset.label || "Morehead City" };
  const CENTER = { lat: num("clat", 34.62), lon: num("clon", -76.75) };
  const SPAN_DEG = 2.9; // longitude across the instrument face
  const STOPS_DARK = [[0, [120, 160, 190]], [8, [110, 200, 215]], [15, [140, 220, 170]], [22, [235, 215, 120]], [30, [245, 150, 90]], [38, [240, 95, 95]]];
  const STOPS_LIGHT = [[0, [70, 110, 140]], [8, [25, 120, 150]], [15, [30, 125, 95]], [22, [170, 130, 30]], [30, [190, 85, 40]], [38, [150, 35, 35]]];
  // Radar-only labels at true WGS84 positions. Water names (w=1) sit in the sound; never used as weather.
  // ax: 0 right of the point, 1 centered (water), 2 left, 3 above. Positions are true WGS84.
  const PLACES = [["Cape Lookout",34.605,-76.536,0,0],["Morehead City",34.722,-76.695,0,3],["Pamlico Sound",35.22,-76.32,1,1],["Ocracoke",35.115,-75.981,0,2],["Emerald Isle",34.668,-77.063,0,2],["Core Sound",34.80,-76.28,1,1],["Cape Hatteras",35.222,-75.530,0,2],["New Bern",35.108,-77.044,0,2],
    // Labels for the other regions' faces (t444u). Not drawn on the Crystal Coast face, which keeps its approved look.
    ["Wilmington",34.226,-77.945,0,2,1],["Jacksonville",34.754,-77.430,0,2,1],["Nags Head",35.957,-75.624,0,2,1],["Manteo",35.908,-75.676,0,2,1],
    ["Albemarle Sound",36.06,-76.25,1,1,1],["Raleigh",35.780,-78.638,0,0,1],["Durham",35.994,-78.899,0,2,1],["Chapel Hill",35.913,-79.056,0,2,1],
    ["Goldsboro",35.385,-77.993,0,0,1],["Fayetteville",35.053,-78.878,0,0,1]];
  const CC = !sec.dataset.region || sec.dataset.region === "crystal-coast";
  const SANS = "\"Barlow Condensed\",\"Arial Narrow\",sans-serif";
  const dark = () => matchMedia("(prefers-color-scheme: dark)").matches;
  const $ = (k) => sec.querySelector('[data-k="' + k + '"]');
  const et = (d, o) => new Intl.DateTimeFormat("en-US", Object.assign({ timeZone: "America/New_York" }, o)).format(d);
  const etTime = (d) => et(d, { hour: "numeric", minute: "2-digit" }) + " ET";
  function rgb(kt, dk) {
    const S = dk ? STOPS_DARK : STOPS_LIGHT;
    for (let i = 1; i < S.length; i++) if (kt <= S[i][0]) { const a = S[i - 1], b = S[i], t = (kt - a[0]) / (b[0] - a[0]); return a[1].map((c, k) => Math.round(c + (b[1][k] - c) * t)); }
    return S[S.length - 1][1];
  }
  function proj(lon, lat, z) { const s = 256 * Math.pow(2, z), sn = Math.sin(lat * D); return [s * (0.5 + lon / 360), s * (0.5 - Math.log((1 + sn) / (1 - sn)) / (4 * Math.PI))]; }
  function unproj(x, y, z) { const s = 256 * Math.pow(2, z); return [x / s * 360 - 180, Math.atan(Math.sinh(Math.PI * (1 - 2 * y / s))) / D]; }
  function decode(doc) {
    const q = doc.q;
    return doc.polys.map((p) => ({ b: p.b.map((v) => v / q), r: p.r.map((a) => { const o = new Float64Array(a.length); let x = 0, y = 0; for (let i = 0; i < a.length; i += 2) { x += a[i]; y += a[i + 1]; o[i] = x / q; o[i + 1] = y / q; } return o; }) }));
  }
  // A view: canvas sized to its face at the device pixel ratio; mercator zoom chosen so the face spans SPAN_DEG.
  function view(cv) {
    const r = cv.getBoundingClientRect(), dpr = Math.min(window.devicePixelRatio || 1, 2);
    const w = Math.max(1, Math.round(r.width)), h = Math.max(1, Math.round(r.height));
    cv.width = w * dpr; cv.height = h * dpr;
    const ctx = cv.getContext("2d"); ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const z = Math.log2(w * 360 / (256 * SPAN_DEG)), c = proj(CENTER.lon, CENTER.lat, z);
    return { ctx, w, h, z, ox: c[0] - w / 2, oy: c[1] - h / 2, px: (lon, lat) => { const p = proj(lon, lat, z); return [p[0] - c[0] + w / 2, p[1] - c[1] + h / 2]; } };
  }
  const css = (n) => getComputedStyle(sec).getPropertyValue(n).trim();
  function base(v, coast) {
    const x = v.ctx; x.fillStyle = css("--sc-water"); x.fillRect(0, 0, v.w, v.h);
    x.beginPath();
    for (const p of coast) for (const r of p.r) { for (let i = 0; i < r.length; i += 2) { const q = v.px(r[i], r[i + 1]); i ? x.lineTo(q[0], q[1]) : x.moveTo(q[0], q[1]); } x.closePath(); }
    x.fillStyle = css("--sc-land"); x.fill("evenodd");
  }
  function coastline(v, coast) {
    const x = v.ctx; x.beginPath();
    for (const p of coast) for (const r of p.r) { for (let i = 0; i < r.length; i += 2) { const q = v.px(r[i], r[i + 1]); i ? x.lineTo(q[0], q[1]) : x.moveTo(q[0], q[1]); } x.closePath(); }
    x.strokeStyle = css("--sc-coast"); x.lineWidth = 1; x.stroke();
  }
  // Chart neatline: hairline outer and inner frames with a 10′ graduated bar between them.
  function neatline(v) {
    const x = v.ctx, ink = css("--sc-neat"), face = css("--sc-face"), o = 1, b = 2, t = o + b;
    x.fillStyle = face; x.fillRect(0, 0, v.w, t); x.fillRect(0, v.h - t, v.w, t); x.fillRect(0, 0, t, v.h); x.fillRect(v.w - t, 0, t, v.h);
    x.fillStyle = ink; x.globalAlpha = 0.58;
    const tl = unproj(v.ox, v.oy, v.z), br = unproj(v.ox + v.w, v.oy + v.h, v.z), step = 1 / 6;
    for (let lon = Math.floor(tl[0] / step) * step; lon < br[0]; lon += step) {
      if (Math.round(lon / step) % 2) continue;
      const a = Math.max(0, v.px(lon, 0)[0]), c = Math.min(v.w, v.px(lon + step, 0)[0]);
      if (c > a) { x.fillRect(a, o, c - a, b); x.fillRect(a, v.h - t, c - a, b); }
    }
    for (let lat = Math.floor(br[1] / step) * step; lat < tl[1]; lat += step) {
      if (Math.round(lat / step) % 2) continue;
      const a = Math.max(0, v.px(0, lat + step)[1]), c = Math.min(v.h, v.px(0, lat)[1]);
      if (c > a) { x.fillRect(o, a, b, c - a); x.fillRect(v.w - t, a, b, c - a); }
    }
    x.globalAlpha = 1; x.strokeStyle = ink; x.lineWidth = 1;
    x.strokeRect(0.5, 0.5, v.w - 1, v.h - 1);
    x.strokeRect(t + 0.5, t + 0.5, v.w - 2 * t - 1, v.h - 2 * t - 1);
  }
  function haloText(x, s, tx, ty) {
    x.strokeStyle = css("--sc-face"); x.lineWidth = 3; x.lineJoin = "round"; x.miterLimit = 2;
    x.strokeText(s, tx, ty); x.fillStyle = css("--sc-neat"); x.fillText(s, tx, ty);
  }
  function graticule(v) {
    const x = v.ctx, tl = unproj(v.ox, v.oy, v.z), br = unproj(v.ox + v.w, v.oy + v.h, v.z), step = 0.5, pad = 4;
    x.save(); x.beginPath(); x.strokeStyle = css("--sc-neat"); x.globalAlpha = 0.2; x.lineWidth = 0.6;
    for (let lon = Math.ceil(tl[0] / step) * step; lon < br[0]; lon += step) {
      const p = v.px(lon, 0); x.moveTo(p[0], pad); x.lineTo(p[0], v.h - pad);
    }
    for (let lat = Math.ceil(br[1] / step) * step; lat < tl[1]; lat += step) {
      const p = v.px(0, lat); x.moveTo(pad, p[1]); x.lineTo(v.w - pad, p[1]);
    }
    x.stroke();
    x.globalAlpha = 0.78; x.font = "600 8.5px " + SANS;
    x.textAlign = "left"; x.textBaseline = "top";
    for (let lon = Math.ceil(tl[0]); lon < br[0]; lon++) {
      const p = v.px(lon, 0); if (p[0] < 28 || p[0] > v.w - 44) continue;
      haloText(x, Math.abs(lon) + "°W", p[0] + 3, 5);
    }
    x.textBaseline = "middle";
    for (let lat = Math.ceil(br[1]); lat < tl[1]; lat++) {
      const p = v.px(0, lat); if (p[1] < 20 || p[1] > v.h - 20) continue;
      haloText(x, lat + "°N", 5, p[1]);
    }
    x.restore();
  }
  function scaleBar(v) {
    const x = v.ctx, nm = 20, lat = CENTER.lat;
    const px = Math.abs(v.px(CENTER.lon + 1, lat)[0] - v.px(CENTER.lon, lat)[0]) * nm / (60 * Math.cos(lat * D));
    if (!(px > 24 && px < v.w * 0.4)) return;
    const x1 = v.w - 10, y = v.h - 11, x0 = x1 - px;
    x.save(); x.strokeStyle = css("--sc-neat"); x.lineWidth = 1; x.globalAlpha = 0.9;
    x.beginPath(); x.moveTo(x0, y - 3); x.lineTo(x0, y); x.lineTo(x1, y); x.lineTo(x1, y - 3);
    x.moveTo((x0 + x1) / 2, y); x.lineTo((x0 + x1) / 2, y - 2); x.stroke();
    x.font = "600 8.5px " + SANS; x.textAlign = "center"; x.textBaseline = "bottom";
    haloText(x, nm + " nm", (x0 + x1) / 2, y - 4);
    x.restore();
  }
  function placeLabels(v) {
    const x = v.ctx, fs = v.w < 260 ? 8 : 9.5;
    const taken = [[0, v.h - 52, Math.min(220, v.w * 0.62), v.h], [v.w - 42, 0, v.w, 40], [v.w - 90, v.h - 28, v.w, v.h]];
    x.save(); x.lineWidth = 3; x.lineJoin = "round"; x.textBaseline = "middle"; x.textAlign = "left";
    for (const [name, lat, lon, water, ax, regional] of PLACES) {
      if (regional && CC) continue;
      const q = v.px(lon, lat);
      if (q[0] < 0 || q[0] > v.w || q[1] < 0 || q[1] > v.h) continue; // never pull an off-face place into view
      x.font = (water ? "italic 500 " : "600 ") + fs + "px " + (water ? "Fraunces,Georgia,serif" : SANS);
      const tw = x.measureText(name).width;
      let tx, ty;
      if (ax === 3) { tx = q[0] - tw / 2; ty = q[1] - fs - 3; }
      else if (ax === 2) { tx = q[0] - tw - 5; ty = q[1]; }
      else if (ax === 1) { tx = q[0] - tw / 2; ty = q[1]; }
      else { tx = q[0] + 5; ty = q[1]; }
      if (tx < 6) tx = 6;
      if (tx + tw > v.w - 6) tx = v.w - 6 - tw;
      if (ty < 16 || ty > v.h - 16) continue;
      const box = [tx - 2, ty - fs, tx + tw + 2, ty + fs];
      if (taken.some((r) => box[0] < r[2] && box[2] > r[0] && box[1] < r[3] && box[3] > r[1])) continue;
      taken.push(box);
      haloText(x, name, tx, ty);
    }
    x.restore();
  }
  function homeDot(v) {
    const x = v.ctx, q = v.px(HOME.lon, HOME.lat);
    x.beginPath(); x.arc(q[0], q[1], 2.8, 0, 7); x.fillStyle = css("--sc-neat"); x.fill();
    x.lineWidth = 1.4; x.strokeStyle = css("--sc-face"); x.stroke();
  }
  function sampler(g) {
    const north = (g.scan & 0x40) === 0, U = g.u, V = g.v, nx = g.nx, ny = g.ny;
    return function (lat, lon) {
      const fx = (lon - g.lo1) / g.dx, fy = north ? (g.la1 - lat) / g.dy : (lat - g.la1) / g.dy;
      if (!(fx >= 0 && fy >= 0 && fx <= nx - 1 && fy <= ny - 1)) return null;
      const x0 = fx | 0, y0 = fy | 0, x1 = Math.min(x0 + 1, nx - 1), y1 = Math.min(y0 + 1, ny - 1), tx = fx - x0, ty = fy - y0;
      const f = (A) => A[y0 * nx + x0] * (1 - tx) * (1 - ty) + A[y0 * nx + x1] * tx * (1 - ty) + A[y1 * nx + x0] * (1 - tx) * ty + A[y1 * nx + x1] * tx * ty;
      return [f(U), f(V)];
    };
  }
  // Static streak snapshot: deterministic jittered seeds, each traced a short way along the field and drawn
  // with a fading tail. One frame, no animation loop.
  function drawWind(cv, g, coast) {
    const v = view(cv), x = v.ctx, uv = sampler(g), dk = dark();
    base(v, coast);
    let seed = 7; const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
    const sp = v.w < 220 ? 11 : 13, steps = 16;
    x.lineCap = "round";
    for (let yy = sp / 2; yy < v.h; yy += sp) for (let xx = sp / 2; xx < v.w; xx += sp) {
      let px = xx + (rnd() - 0.5) * sp, py = yy + (rnd() - 0.5) * sp; const pts = [[px, py]]; let kt = 0;
      for (let s = 0; s < steps; s++) {
        const ll = unproj(px + v.ox, py + v.oy, v.z), w = uv(ll[1], ll[0]); if (!w) break;
        const k = Math.hypot(w[0], w[1]) * KT; kt = k; if (k < 0.3) break;
        const L = 0.25 + k * 0.085; px += w[0] / Math.hypot(w[0], w[1]) * L; py -= w[1] / Math.hypot(w[0], w[1]) * L; pts.push([px, py]);
      }
      if (pts.length < 3) continue;
      const c = rgb(kt, dk).join(",");
      for (let i = 1; i < pts.length; i++) {
        x.strokeStyle = "rgba(" + c + "," + (0.12 + 0.78 * i / pts.length).toFixed(2) + ")"; x.lineWidth = 1.1;
        x.beginPath(); x.moveTo(pts[i - 1][0], pts[i - 1][1]); x.lineTo(pts[i][0], pts[i][1]); x.stroke();
      }
    }
    coastline(v, coast); graticule(v); homeDot(v); scaleBar(v); neatline(v); cv.classList.add("is-on");
    const h = uv(HOME.lat, HOME.lon);
    if (!h) $("w-read").textContent = "No model wind for " + HOME.name;
    if (h) {
      const k = Math.round(Math.hypot(h[0], h[1]) * KT), dir = DIRS[Math.round(((Math.atan2(-h[0], -h[1]) / D + 360) % 360) / 22.5) % 16];
      const el = $("w-read"), sm = document.createElement("small"); sm.textContent = HOME.name;
      el.textContent = k < 1 ? "Calm" : dir + " " + k + " kt"; el.appendChild(sm);
    }
    const valid = new Date(g.valid);
    $("w-time").textContent = "Valid " + etTime(valid) + " " + et(valid, { weekday: "short" });
  }
  function drawRadar(cv, meta, coast) {
    const obs = (meta.frames || []).filter((f) => f.type === "observed");
    if (!meta.ok || !obs.length) { $("r-read").textContent = "Radar unavailable"; return Promise.resolve(); }
    const fr = obs[obs.length - 1], when = new Date(fr.time_epoch * 1000);
    const age = () => { const m = Math.max(0, Math.round((Date.now() - when) / 60000)); $("r-time").innerHTML = "Latest frame " + etTime(when) + '<span class="sc-age"><i> · </i>' + m + " min ago</span>"; };
    age(); setInterval(age, 60000);
    if (meta.attribution) $("r-attr").textContent = meta.attribution;
    if (meta.disclaimer) $("r-disc").textContent = meta.disclaimer;
    const v = view(cv), Z = 7, k = Math.pow(2, v.z - Z), tiles = [];
    const x0 = Math.floor(v.ox / k / 256), x1 = Math.floor((v.ox + v.w) / k / 256), y0 = Math.floor(v.oy / k / 256), y1 = Math.floor((v.oy + v.h) / k / 256);
    for (let ty = y0; ty <= y1; ty++) for (let tx = x0; tx <= x1; tx++) tiles.push([tx, ty]);
    const load = (t) => new Promise((res) => { const im = new Image(); im.decoding = "async"; im.onload = () => res([t, im]); im.onerror = () => res([t, null]);
      im.src = meta.tile_url.replace("{z}", Z).replace("{x}", t[0]).replace("{y}", t[1]).replace("{time}", fr.time); });
    return Promise.all(tiles.map(load)).then((got) => {
      const draw = () => {
        const v2 = view(cv), x = v2.ctx; base(v2, coast);
        const off = document.createElement("canvas"); off.width = v2.w; off.height = v2.h; const ox = off.getContext("2d");
        for (const [t, im] of got) if (im) ox.drawImage(im, t[0] * 256 * k - v2.ox, t[1] * 256 * k - v2.oy, 256 * k, 256 * k);
        let echoes = 0; try { const d = ox.getImageData(8, 8, v2.w - 16, v2.h - 16).data; for (let i = 3; i < d.length; i += 16) if (d[i] > 40) echoes++; } catch (e) { echoes = -1; }
        x.globalAlpha = 0.9; x.drawImage(off, 0, 0, v2.w, v2.h); x.globalAlpha = 1;
        coastline(v2, coast); graticule(v2); homeDot(v2); placeLabels(v2); scaleBar(v2); neatline(v2); cv.classList.add("is-on");
        const compact = sec.classList.contains("sc-b");
        $("r-read").textContent = echoes > 30 ? (compact ? "Echoes" : "Precipitation in view") : echoes >= 0 ? (compact ? "Dry" : "No precipitation in view") : "";
      };
      draw(); return draw;
    });
  }
  let started = false;
  function start() {
    if (started) return; started = true;
    const j = (u) => fetch(u, { credentials: "same-origin" }).then((r) => r.json());
    const coastP = j("/api/home-coast").then(decode);
    const cvW = sec.querySelector(".sc-wind .sc-cv"), cvR = sec.querySelector(".sc-radar .sc-cv");
    let redrawW = null, redrawR = null;
    Promise.all([j("/api/home-wind"), coastP]).then(([g, coast]) => { if (g.ok) { drawWind(cvW, g, coast); redrawW = () => drawWind(cvW, g, coast); } else $("w-read").textContent = "Wind model unavailable"; }).catch(() => { $("w-read").textContent = "Wind model unavailable"; });
    Promise.all([j("/api/radar"), coastP]).then(([m, coast]) => drawRadar(cvR, m, coast)).then((d) => { redrawR = d || null; }).catch(() => { $("r-read").textContent = "Radar unavailable"; });
    matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => { redrawW && redrawW(); redrawR && redrawR(); });
  }
  if ("IntersectionObserver" in window) {
    const io = new IntersectionObserver((es) => { if (es.some((e) => e.isIntersecting)) { io.disconnect(); start(); } }, { rootMargin: "200px 0px" });
    io.observe(sec);
  } else start();
})();
