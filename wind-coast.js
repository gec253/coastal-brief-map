/* /wind coastline: U.S. Census Bureau 2025 cartographic boundary land (1:500,000), drawn by us in the
   page palette, one 256 px tile per task (no long tasks), crisp at the device pixel ratio. Replaces the
   Esri tiles on /wind. Data: /wind/coast-lo.json (zoom < 8), /wind/coast-hi.json (zoom >= 8), built by
   scripts/build_wind_coast.py. The pure math (decode, project, pointInLand) also loads in Node for tests. */
(function (root) {
  "use strict";
  const D = Math.PI / 180, MAXLAT = 85.0511287798;
  // Same Web Mercator pixel space as Leaflet's L.CRS.EPSG3857 (256 px tiles).
  function project(lon, lat, z) {
    const s = 256 * Math.pow(2, z), la = Math.max(Math.min(MAXLAT, lat), -MAXLAT), sn = Math.sin(la * D);
    return [s * (0.5 + lon / 360), s * (0.5 - Math.log((1 + sn) / (1 - sn)) / (4 * Math.PI))];
  }
  function unproject(x, y, z) {
    const s = 256 * Math.pow(2, z);
    return [x / s * 360 - 180, Math.atan(Math.sinh(Math.PI * (1 - 2 * y / s))) / D];
  }
  // Delta-encoded 1e-4° integer rings -> Float64Array [lon, lat, lon, lat, ...] in degrees.
  function decode(doc) {
    const q = doc.q;
    return doc.polys.map(function (p) {
      return {
        b: p.b.map((v) => v / q),
        r: p.r.map(function (a) {
          const out = new Float64Array(a.length);
          let x = 0, y = 0;
          for (let i = 0; i < a.length; i += 2) { x += a[i]; y += a[i + 1]; out[i] = x / q; out[i + 1] = y / q; }
          return out;
        }),
      };
    });
  }
  // Even-odd point in land test over decoded polygons.
  function pointInLand(polys, lon, lat) {
    for (const p of polys) {
      if (lon < p.b[0] || lon > p.b[2] || lat < p.b[1] || lat > p.b[3]) continue;
      let inside = false;
      for (const r of p.r) {
        for (let i = 0, j = r.length - 2; i < r.length; j = i, i += 2) {
          const xi = r[i], yi = r[i + 1], xj = r[j], yj = r[j + 1];
          if ((yi > lat) !== (yj > lat) && lon < (xj - xi) * (lat - yi) / (yj - yi) + xi) inside = !inside;
        }
      }
      if (inside) return true;
    }
    return false;
  }
  const CoastMath = { project, unproject, decode, pointInLand, HI_ZOOM: 8 };
  if (typeof module === "object" && module.exports) { module.exports = CoastMath; return; }
  root.CBCoastMath = CoastMath;
  if (typeof document === "undefined" || !root.L) return;

  /* Leaflet layer. opts: land, line (CSS colours), lineWidth, base (URL prefix). The map container
     background is the water colour, so tiles only paint land and the shoreline. */
  function layer(opts) {
    const cache = {};
    function data(lod) {
      if (!cache[lod]) cache[lod] = fetch(opts.base + lod + ".json").then((r) => r.json()).then(decode);
      return cache[lod];
    }
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const stats = { tiles: 0, maxMs: 0, totalMs: 0 };
    function draw(t, c, polys) {
      const t0 = performance.now();
      const x = t.getContext("2d"), ox = c.x * 256, oy = c.y * 256;
      x.setTransform(1, 0, 0, 1, 0, 0); x.clearRect(0, 0, t.width, t.height);
      x.setTransform(dpr, 0, 0, dpr, 0, 0);
      const nw = unproject(ox - 2, oy - 2, c.z), se = unproject(ox + 258, oy + 258, c.z);
      x.beginPath();
      let any = false;
      for (const p of polys) {
        if (p.b[2] < nw[0] || p.b[0] > se[0] || p.b[3] < se[1] || p.b[1] > nw[1]) continue;
        any = true;
        for (const r of p.r) {
          for (let i = 0; i < r.length; i += 2) {
            const pt = project(r[i], r[i + 1], c.z), px = pt[0] - ox, py = pt[1] - oy;
            if (i) x.lineTo(px, py); else x.moveTo(px, py);
          }
          x.closePath();
        }
      }
      if (any) {
        x.fillStyle = opts.land; x.fill("evenodd");
        x.lineJoin = "round"; x.strokeStyle = opts.line; x.lineWidth = opts.lineWidth * (c.z >= CoastMath.HI_ZOOM ? 1.15 : 1); x.stroke();
      }
      const ms = performance.now() - t0;
      stats.tiles++; stats.totalMs += ms; if (ms > stats.maxMs) stats.maxMs = ms;
    }
    // One tile per animation frame: drawing is cheap (1-8 ms), but each finished canvas is copied to the
    // compositor on the next commit, so finishing several tiles in one frame makes one long frame.
    const queue = [];
    let pumping = false;
    function pump() {
      const t0 = performance.now();
      let job = queue.shift();
      if (job) { draw(job.t, job.c, job.polys); if (job.done) job.done(null, job.t); }
      // Restyle jobs (theme switch) repaint tiles already on screen: a few per frame within ~6 ms.
      while (job && job.restyle && queue.length && queue[0].restyle && performance.now() - t0 < 6) {
        job = queue.shift(); draw(job.t, job.c, job.polys);
      }
      if (queue.length) schedule(); else pumping = false;
    }
    function schedule() {
      pumping = true;
      // rAF doesn't run in hidden tabs; fall back to a timer so tiles still finish there.
      if (document.hidden || !root.requestAnimationFrame) setTimeout(pump, 16); else requestAnimationFrame(pump);
    }
    const Coast = L.GridLayer.extend({
      createTile: function (c, done) {
        const t = document.createElement("canvas");
        t.width = t.height = Math.round(256 * dpr);
        data(c.z >= CoastMath.HI_ZOOM ? "hi" : "lo").then(function (polys) {
          queue.push({ t: t, c: c, polys: polys, done: done });
          if (!pumping) schedule();
        }, function (e) { done(e, t); });
        return t;
      },
    });
    const l = new Coast({ updateWhenIdle: true, keepBuffer: 1, maxNativeZoom: 12 });
    l.stats = stats; l.data = data;
    // Theme switch: new land/line colours, repaint the tiles already shown (no reload, no blank tiles).
    l.restyle = function (o) {
      for (const k in o) opts[k] = o[k];
      for (let i = queue.length - 1; i >= 0; i--) if (queue[i].restyle) queue.splice(i, 1);
      const tiles = this._tiles || {};
      for (const key in tiles) {
        const tl = tiles[key];
        if (!tl.loaded || !tl.el) continue;
        const c = tl.coords;
        data(c.z >= CoastMath.HI_ZOOM ? "hi" : "lo").then(function (polys) {
          queue.push({ t: tl.el, c: c, polys: polys, restyle: true });
          if (!pumping) schedule();
        });
      }
      return this;
    };
    return l;
  }
  root.CBCoast = { layer: layer };
})(typeof window !== "undefined" ? window : this);
