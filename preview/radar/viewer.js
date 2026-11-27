/* Private /preview/radar viewer. Reuses CBRadarPlayer (/radar/player.js, unchanged) and
   CBCoast (/wind/coast.js, unchanged). OBSERVED radar for the last two hours; FORECAST
   (nowcast) frames follow the observed loop, labelled and subtly hatched. Default rate
   unit is in/h from the provider's exact mm/h bins (1 in = 25.4 mm). Times are America/New_York. */
(function () {
  "use strict";
  const P = window.CBRadarPlayer;
  if (!P || !window.L || !window.CBCoast) return;
  const $ = (id) => document.getElementById(id);
  const q = location.search, root = document.documentElement;
  let dark = root.getAttribute("data-theme") === "dark";
  const mm = (s) => !!(window.matchMedia && matchMedia(s).matches);
  const reduce = mm("(prefers-reduced-motion: reduce)") || /[?&]motion=off\b/.test(q);
  const AT = (/[?&]at=(-?\d{1,2}(?:\.\d{1,5})?),(-?\d{1,3}(?:\.\d{1,5})?)(?:&|$)/.exec(q) || []).slice(1).map(Number);
  const HOME = AT.length === 2 && AT[0] >= 32.5 && AT[0] <= 38 && AT[1] >= -86.5 && AT[1] <= -73
    ? L.latLngBounds([AT[0] - 0.9, AT[1] - 1.2], [AT[0] + 0.9, AT[1] + 1.2])
    : L.latLngBounds([33.75, -78.3], [36.55, -75.25]);
  const MAX_BOUNDS = [[32.5, -86.5], [38.0, -74.0]];
  const yieldTask = () => new Promise((r) => (window.scheduler && scheduler.yield ? scheduler.yield().then(r) : setTimeout(r, 0)));
  const STALE_MIN = 15;
  const MM_PER_IN = 25.4;
  function mmhToInh(mm) { return mm / MM_PER_IN; }
  /* Exact inches from a provider mm/h threshold. Used in the About panel. */
  function formatInhExact(mm) {
    const inches = mm / MM_PER_IN;
    if (inches < 1) return inches.toFixed(4);
    return inches.toFixed(3);
  }
  /* Rounded legend labels. Colour mapping still uses the exact from_mm_h edges. */
  const INH_TICK = { 0.1: "<0.01", 0.5: "0.02", 1: "0.04", 2: "0.08", 4: "0.15", 8: "0.3", 16: "0.6", 32: "1.25", 64: "2.5+" };
  function formatInh(mm) {
    const keys = Object.keys(INH_TICK);
    let best = keys[0], d = 1e9;
    for (let i = 0; i < keys.length; i++) {
      const k = Number(keys[i]), dk = Math.abs(k - mm);
      if (dk < d) { d = dk; best = keys[i]; }
    }
    if (d < 1e-6) return INH_TICK[best];
    const inches = mm / MM_PER_IN;
    if (inches < 0.01) return "<0.01";
    if (inches >= 2.5) return "2.5+";
    if (inches < 0.1) return String(Math.round(inches * 100) / 100);
    if (inches < 1) {
      const tenth = Math.round(inches * 10) / 10;
      if (Math.abs(inches - tenth) < 0.04) return String(tenth);
      return (Math.round(inches * 100) / 100).toFixed(2);
    }
    return (Math.round(inches * 20) / 20).toFixed(2);
  }
  function classifyView(s) {
    if (!s || !s.available) return "unavailable";
    if (s.loading) return "loading";
    if (s.fail > 0) return "incomplete";
    if (!s.opaque) return "clear";
    return "precip";
  }
  function classifyCoverage(s) {
    if (!s || !s.available) return "unavailable";
    if (s.stale) return "stale";
    return classifyView(s);
  }
  window.CBRadarPreview = { MM_PER_IN: MM_PER_IN, mmhToInh: mmhToInh, formatInh: formatInh, formatInhExact: formatInhExact, INH_TICK: INH_TICK, classifyView: classifyView, classifyCoverage: classifyCoverage, STALE_MIN: STALE_MIN };

  const clockF = new Intl.DateTimeFormat("en-US", { timeZone: "America/New_York", hour: "numeric", minute: "2-digit" });
  function tickClock() { $("r-clock").textContent = clockF.format(new Date()) + " ET"; }
  tickClock(); setInterval(tickClock, 15000);

  const THEME_STORE = "coastalBrief.theme";
  const sysDark = window.matchMedia ? matchMedia("(prefers-color-scheme: dark)") : null;
  const qTheme = (/[?&]theme=(light|dark)\b/.exec(q) || [])[1] || null;
  let onTheme = null;
  function stored() { try { const t = localStorage.getItem(THEME_STORE); return t === "light" || t === "dark" ? t : null; } catch (e) { return null; } }
  function resolved() { return stored() || (sysDark && sysDark.matches ? "dark" : "light"); }
  const tbtn = $("w-theme");
  function syncToggle() { if (!tbtn) return; tbtn.setAttribute("aria-pressed", String(dark)); tbtn.title = dark ? "Switch to day mode" : "Switch to night mode"; }
  function applyTheme(t, persist) {
    t = t === "dark" ? "dark" : "light";
    if (persist) { try { localStorage.setItem(THEME_STORE, t); } catch (e) {} }
    const d = t === "dark";
    if (d === dark && root.getAttribute("data-theme") === t) { syncToggle(); return; }
    dark = d; root.setAttribute("data-theme", t);
    if (d) root.setAttribute("data-night", "b"); else root.removeAttribute("data-night");
    syncToggle(); if (onTheme) onTheme();
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

  const play = $("r-play"), prev = $("r-prev"), next = $("r-next"), scrub = $("r-scrub"), status = $("r-status"), tl = $("r-tl"), stage = $("r-stage");

  function hatchImageData(ctx, w, h) {
    /* Subtle texture on forecast precip only: every 4th diagonal sample is dimmed, not erased. */
    const img = ctx.getImageData(0, 0, w, h), d = img.data;
    for (let y = 0; y < h; y++) {
      for (let x = 0; x < w; x++) {
        if (((x + y) % 4) !== 0) continue;
        const i = (y * w + x) * 4;
        if (d[i + 3] > 0) d[i + 3] = Math.max(1, Math.floor(d[i + 3] * 0.55));
      }
    }
    ctx.putImageData(img, 0, 0);
  }
  function canvasHasPrecip(ctx, w, h) {
    const d = ctx.getImageData(0, 0, w, h).data;
    for (let i = 3; i < d.length; i += 16) { if (d[i] > 8) return true; }
    return false;
  }
  function paintMissing(ctx, w, h) {
    /* Uncertainty texture — not a clear/no-rain tile. */
    ctx.clearRect(0, 0, w, h);
    ctx.fillStyle = "rgba(110, 120, 130, 0.16)";
    ctx.fillRect(0, 0, w, h);
    ctx.strokeStyle = "rgba(70, 80, 90, 0.28)";
    ctx.lineWidth = 1;
    for (let i = -h; i < w; i += 10) {
      ctx.beginPath();
      ctx.moveTo(i, 0);
      ctx.lineTo(i + h, h);
      ctx.stroke();
    }
  }

  const CanvasTiles = L.GridLayer.extend({
    createTile: function (c, done) {
      const canvas = document.createElement("canvas"), sz = this.getTileSize(); canvas.width = sz.x; canvas.height = sz.y;
      const url = L.Util.template(this.options.url, { z: c.z, x: c.x, y: c.y });
      const onFeed = this.options.onFeed, hatch = !!this.options.hatch;
      function failTile() {
        const ctx = canvas.getContext("2d");
        paintMissing(ctx, sz.x, sz.y);
        canvas._radarFail = true;
        canvas._radarOpaque = false;
        done(null, canvas);
      }
      fetch(url, { cache: "default" }).then(function (res) {
        if (onFeed && (res.status === 429 || (res.headers && res.headers.get("X-Radar-Cache") === "stale"))) {
          onFeed(res.status === 429 ? "rate_limit" : "stale", res);
        }
        if (!res.ok) { failTile(); return null; }
        return res.blob();
      }).then(function (blob) {
        if (!blob) return;
        const img = new Image();
        const src = URL.createObjectURL(blob);
        img.onload = function () {
          URL.revokeObjectURL(src);
          const ctx = canvas.getContext("2d");
          ctx.drawImage(img, 0, 0, sz.x, sz.y);
          canvas._radarFail = false;
          canvas._radarOpaque = canvasHasPrecip(ctx, sz.x, sz.y);
          if (hatch) hatchImageData(ctx, sz.x, sz.y);
          done(null, canvas);
        };
        img.onerror = function () { URL.revokeObjectURL(src); failTile(); };
        img.src = src;
      }).catch(function () { failTile(); });
      return canvas;
    },
  });

  const MIN_WINDOW = 6;

  function officialLegend(legend) {
    const ramp = $("r-ramp"), ticks = $("r-ticks");
    if (!ramp || !legend || !legend.length) return;
    ramp.textContent = "";
    legend.forEach(function (row) {
      const i = document.createElement("i");
      i.style.background = row.color;
      ramp.appendChild(i);
    });
    if (ticks) {
      ticks.textContent = "";
      const want = [0.1, 1, 8, 64];
      const n = legend.length;
      want.forEach(function (v) {
        let idx = -1, best = 1e9;
        legend.forEach(function (row, k) {
          const d = Math.abs((row.from_mm_h || 0) - v);
          if (d < best) { best = d; idx = k; }
        });
        if (idx < 0) return;
        const span = document.createElement("span");
        span.textContent = formatInh(v);
        const left = ((idx + 0.5) / n) * 100;
        span.style.left = left + "%";
        ticks.appendChild(span);
      });
    }
    const bins = $("r-bins");
    if (bins) {
      bins.textContent = "Legend labels are rounded for reading; colours still change at the provider’s exact millimetre-per-hour edges (inches = millimetres ÷ 25.4). Exact values: " + legend.map(function (row) {
        const mm = row.from_mm_h;
        return mm + " mm/h = " + formatInhExact(mm) + " in/h (legend " + formatInh(mm) + ")";
      }).join("; ") + ".";
    }
  }


  function decodeBorderLines(doc) {
    const q = doc.q || 10000;
    return (doc.lines || []).map(function (ln) {
      const a = ln.r, out = new Float64Array(a.length);
      let x = 0, y = 0;
      for (let i = 0; i < a.length; i += 2) { x += a[i]; y += a[i + 1]; out[i] = x / q; out[i + 1] = y / q; }
      return out;
    });
  }
  function addBorderLayer(map) {
    if (!window.CBCoastMath || !window.L) return null;
    map.createPane("borders");
    map.getPane("borders").style.zIndex = 250;
    const project = window.CBCoastMath.project;
    const dataP = fetch("/preview/radar/borders.json").then(function (r) { return r.json(); }).then(decodeBorderLines);
    const Borders = L.GridLayer.extend({
      createTile: function (c, done) {
        const dpr = Math.min(window.devicePixelRatio || 1, 2);
        const t = document.createElement("canvas");
        t.width = t.height = Math.round(256 * dpr);
        dataP.then(function (lines) {
          const ctx = t.getContext("2d");
          ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
          const ox = c.x * 256, oy = c.y * 256;
          ctx.strokeStyle = getComputedStyle(document.documentElement).getPropertyValue("--rv-border").trim() || "rgba(28,48,60,0.42)";
          ctx.lineWidth = c.z >= 8 ? 1.15 : 1;
          ctx.lineJoin = "round";
          ctx.lineCap = "round";
          ctx.beginPath();
          for (let i = 0; i < lines.length; i++) {
            const r = lines[i];
            for (let j = 0; j < r.length; j += 2) {
              const pt = project(r[j], r[j + 1], c.z);
              if (j === 0) ctx.moveTo(pt[0] - ox, pt[1] - oy);
              else ctx.lineTo(pt[0] - ox, pt[1] - oy);
            }
          }
          ctx.stroke();
          done(null, t);
        }, function (e) { done(e, t); });
        return t;
      },
    });
    return new Borders({ pane: "borders", updateWhenIdle: true, keepBuffer: 1, attribution: "" }).addTo(map);
  }

  async function boot() {
    const metaP = fetch("/api/radar-view").then((r) => r.json()).catch(() => ({ ok: false, reason: "network" }));
    metaP.then(function (m) { if (!m.ok || !m.frames || !m.frames.length) unavailable(m); });
    const map = L.map("rmap", { zoomControl: false, attributionControl: false, zoomSnap: 0.5, minZoom: 5, maxZoom: 9.5, maxBounds: MAX_BOUNDS, maxBoundsViscosity: 0.75, fadeAnimation: false });
    map.fitBounds(HOME);
    map.createPane("radar"); map.getPane("radar").style.zIndex = 350; map.getPane("radar").classList.add("leaflet-radar-pane");
    await yieldTask();
    const coastStyle = () => { const c = getComputedStyle(root); return { land: c.getPropertyValue("--coast-land").trim(), line: c.getPropertyValue("--coast-line").trim(), lineWidth: dark ? 1 : 0.9 }; };
    const coast = window.CBCoast.layer(Object.assign({ base: "/preview/radar/coast-" }, coastStyle())).addTo(map);
    let borderLayer = null;
    onTheme = function () { coast.restyle(coastStyle()); if (borderLayer && borderLayer.redraw) borderLayer.redraw(); paintLabels(); };

    let labData = null, labVis = [];
    const labRoot = $("r-labels");
    function hits(a, b) { return a.l < b.r && a.r > b.l && a.t < b.b && a.b > b.t; }
    function addBox(list, el, pad) {
      if (!el || el.hidden || (el.hasAttribute && el.hasAttribute("hidden"))) return;
      const r = el.getBoundingClientRect();
      if (r.width < 2 || r.height < 2) return;
      const st = $("r-stage").getBoundingClientRect();
      list.push({ l: r.left - st.left - pad, t: r.top - st.top - pad, r: r.right - st.left + pad, b: r.bottom - st.top + pad });
    }
    function reserved() {
      const box = [];
      addBox(box, $("r-legend"), 6);
      addBox(box, $("r-tag"), 6);
      addBox(box, $("r-load"), 4);
      addBox(box, $("r-limit"), 6);
      addBox(box, $("r-cover"), 4);
      addBox(box, document.querySelector(".rv-zoom"), 6);
      addBox(box, document.querySelector(".w-about summary"), 6);
      const about = document.querySelector(".w-about");
      if (about && about.open) addBox(box, about.querySelector(".w-about-body"), 8);
      addBox(box, document.querySelector(".w-attrib"), 4);
      if (status && !status.hidden) addBox(box, status, 4);
      return box;
    }
    function paintLabels() {
      if (!labRoot) return;
      labVis = [];
      labRoot.textContent = "";
      if (!labData || !labData.places) return;
      const z = map.getZoom(), box = reserved(), kept = [];
      const st = $("r-stage").getBoundingClientRect();
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
    function loadLabels() {
      fetch("/preview/radar/labels.json").then(function (r) { return r.json(); }).then(function (d) { labData = d; paintLabels(); }).catch(function () {});
    }
    if (window.requestIdleCallback) requestIdleCallback(loadLabels, { timeout: 1500 }); else setTimeout(loadLabels, 400);
    map.on("moveend zoomend", function () { paintLabels(); });
    window.addEventListener("resize", paintLabels);
    const aboutEl = document.querySelector(".w-about");
    if (aboutEl) aboutEl.addEventListener("toggle", paintLabels);
    $("r-zin").addEventListener("click", function () { map.zoomIn(); });
    $("r-zout").addEventListener("click", function () { map.zoomOut(); });

    const meta = await metaP;
    window.__radarMeta = { ok: !!meta.ok, fixture: !!meta.fixture, reason: meta.reason || null, limited: !!meta.limited, preview: true };
    if (!meta.ok || !meta.frames || !meta.frames.length) return unavailable(meta);
    function showLimit(kind, message) {
      const el = $("r-limit");
      if (!el) return;
      const text = message || (
        kind === "rate_limit"
          ? "Too many radar requests. Showing cached observed frames where available. Incomplete or forecast frames are not shown."
          : "Radar is temporarily limited. Showing cached observed frames where available. Incomplete or forecast frames are not shown."
      );
      el.textContent = text;
      el.hidden = false;
      window.__radarLimited = kind || true;
      paintLabels();
    }
    if (meta.limited) showLimit(meta.limit_reason, meta.limit_message);

    const fixture = !!meta.fixture;
    if (fixture) {
      $("r-test").hidden = false; $("r-test").textContent = meta.fixture_label + " · " + P.etDate(meta.frames[0].time_epoch) + ", " + new Date(meta.frames[0].time_epoch * 1000).getUTCFullYear(); $("r-badge").textContent = "Test data"; $("r-badge").classList.add("is-test");
    } else if (meta.attribution) {
      const full = $("r-credit-full");
      if (full) full.textContent = String(meta.attribution).replace(/\.$/, "") + ".";
      $("r-attrib").setAttribute("title", String(meta.attribution));
    }
    if (meta.legend && meta.legend.length) officialLegend(meta.legend);

    const player = P.create(meta.frames);
    const snap0 = player.snapshot();
    if (!snap0.observedCount) return unavailable({ ok: false, reason: "upstream" });
    if (snap0.forecastCount) player.setForecast(true);

    const layers = new Map(), loaded = new Set(), t0 = performance.now(), loadMs = {};
    const tmpl = meta.tile_url;
    let issue = snap0.latestObserved.time;
    function layerFor(f) {
      let l = layers.get(f.time);
      if (l) return l;
      l = new CanvasTiles({ url: tmpl.replace("{time}", f.time) + (f.type === "forecast" ? "&v=" + issue : ""),
        pane: "radar", opacity: 0, className: "r-frame" + (f.type === "forecast" ? " r-frame-fc" : ""),
        tileSize: meta.tile_size || 256, maxNativeZoom: meta.max_native_zoom || meta.max_zoom || 7, minZoom: 5, maxZoom: 9.5,
        updateWhenIdle: true, keepBuffer: 1, hatch: f.type === "forecast",
        onFeed: function (kind) { showLimit(kind); },
      });
      l.once("load", function () { loaded.add(f.time); loadMs[f.time] = Math.round(performance.now() - t0); maybeAllLoaded(); updateFill(); });
      l.addTo(map); layers.set(f.time, l);
      return l;
    }
    function maybeAllLoaded() {
      const obs = player.observed();
      if (!window.__radarPreload && obs.every((f) => loaded.has(f.time))) window.__radarPreload = { allObservedMs: Math.max.apply(null, obs.map((f) => loadMs[f.time])), firstMs: loadMs[obs[obs.length - 1].time], frames: obs.length };
    }
    function frameReady(f) {
      const l = f && layers.get(f.time);
      if (!l || !loaded.has(f.time)) return false;
      let cur = 0;
      for (const k in l._tiles) { const tl = l._tiles[k]; if (tl.current) { cur++; if (!tl.loaded) return false; } }
      return cur > 0;
    }
    const inflight = new Set();
    let front = null;
    let backgroundPreload = false;
    function pump() {
      const list = player.frames();
      const cur = player.snapshot().frame;
      const lim = backgroundPreload ? 2 : 1;
      const order = [];
      if (front !== null) order.push(front);
      if (cur) {
        const ci = list.findIndex(function (f) { return f.time === cur.time; });
        if (ci >= 0) order.push(ci);
      }
      if (backgroundPreload) Array.prototype.push.apply(order, player.loadOrder());
      for (let k = 0; k < order.length && inflight.size < lim; k++) {
        const f = list[order[k]];
        if (!f || layers.has(f.time)) continue;
        inflight.add(f.time); const l = layerFor(f);
        l.once("load", function () { inflight.delete(f.time); pump(); loadingUI(); });
      }
      const ff = front !== null && list[front];
      if (!ff || layers.has(ff.time)) front = null;
    }
    function prefetch(i) {
      const f = player.frames()[i];
      if (f && !layers.has(f.time)) front = i;
      if (backgroundPreload || (player.snapshot().frame && f && f.time === player.snapshot().frame.time)) pump();
    }
    function startBackgroundPreload() {
      if (backgroundPreload) return;
      backgroundPreload = true;
      window.__radarBackgroundPreload = true;
      pump();
    }
    function afterFirstPaint() {
      function go() { startBackgroundPreload(); if (!borderLayer) borderLayer = addBorderLayer(map); if (!reduce) { player.play(); schedule(); } }
      if (window.requestIdleCallback) requestIdleCallback(go, { timeout: 600 });
      else setTimeout(go, 0);
    }
    const loadEl = $("r-load");
    let loadTxt = "";
    function viewStats(l) {
      let ok = 0, fail = 0, loading = 0, current = 0, opaque = false;
      if (!l || !l._tiles) return { ok: 0, fail: 0, loading: true, current: 0, opaque: false };
      for (const k in l._tiles) {
        const tl = l._tiles[k];
        if (!tl.current) continue;
        current++;
        if (!tl.loaded) { loading++; continue; }
        const el = tl.el;
        if (el && el._radarFail) fail++;
        else {
          ok++;
          if (el && el._radarOpaque) opaque = true;
        }
      }
      return { ok: ok, fail: fail, loading: loading > 0 || current === 0, current: current, opaque: opaque };
    }
    function coverageUI() {
      const el = $("r-cover");
      if (!el) return;
      const s = player.snapshot(), f = s.frame, lo = s.latestObserved;
      const ageMin = lo ? Math.max(0, Math.round((Date.now() / 1000 - lo.epoch) / 60)) : 0;
      const stale = !fixture && ageMin >= STALE_MIN;
      const st = viewStats(f && layers.get(f.time));
      const loading = !frameReady(f) || st.loading;
      const payload = { available: true, stale: stale, loading: loading, fail: st.fail, opaque: st.opaque };
      const kind = classifyCoverage(payload);
      const view = classifyView(payload);
      let text = "", cls = "";
      if (view === "incomplete") { text = "Incomplete coverage. Missing tiles are not clear skies."; cls = "is-incomplete"; }
      else if (view === "clear") { text = "No precipitation in view"; cls = "is-clear"; }
      el.textContent = text;
      el.className = "r-cover" + (cls ? " " + cls : "");
      el.hidden = !text;
      window.__radarCoverage = { kind: kind, view: view, stale: stale, fail: st.fail, ok: st.ok, opaque: st.opaque, loading: loading, ageMin: ageMin };
    }
    function reveal() {
      const f = player.snapshot().frame, l = f && layers.get(f.time);
      if (!l || !frameReady(f) || l === shown) return;
      const op = f.type === "forecast" ? 0.72 : (dark ? 0.92 : 0.86);
      const prev = shown;
      l.setOpacity(op);
      shown = l;
      if (prev && prev !== l) {
        if (reduce) prev.setOpacity(0);
        else {
          requestAnimationFrame(function () {
            requestAnimationFrame(function () { if (shown !== prev) prev.setOpacity(0); });
          });
        }
      }
    }
    function loadingUI() {
      reveal();
      coverageUI();
      const list = player.frames(), s = player.snapshot();
      const n = list.filter(frameReady).length, total = list.length, cur = frameReady(s.frame);
      window.__radarLoading = { ready: n, total: total, current: cur };
      const txt = !cur ? "Loading radar… " + n + "/" + total : "";
      if (txt !== loadTxt) { loadTxt = txt; loadEl.textContent = txt; loadEl.hidden = !txt; paintLabels(); }
    }
    function updateFill() {
      const obs = player.observed();
      const n = obs.filter(function (f) { return loaded.has(f.time); }).length;
      const el = $("r-fill");
      if (el && obs.length) el.style.width = Math.round((n / obs.length) * 100) + "%";
    }
    function placeThumb(s) {
      const thumb = $("r-thumb"), track = tl && tl.querySelector(".rv-track");
      if (!thumb || !track || s.count < 1) return;
      const rect = track.getBoundingClientRect();
      const hasFc = s.forecastOn && s.forecastCount > 0;
      const nowEl = $("r-now-mark"), fcs = $("r-fcs");
      let x = 0;
      if (!hasFc) {
        x = s.count === 1 ? 0.5 : s.index / (s.count - 1);
      } else {
        const obsW = 120, gap = 6, fcW = 60, total = obsW + gap + fcW;
        if (s.segment !== "forecast") {
          x = (s.observedCount <= 1 ? 0 : (s.index / (s.observedCount - 1))) * (obsW / total);
        } else {
          const fi = s.index - s.boundary;
          const t = s.forecastCount <= 1 ? 1 : (fi + 1) / s.forecastCount;
          x = (obsW + gap) / total + t * (fcW / total);
        }
      }
      const w = rect.width;
      thumb.style.left = Math.round(x * w) + "px";
    }
    let shown = null;
    function relLabel(s) {
      const f = s.frame, lo = s.latestObserved;
      if (!f) return { a: "Frame", b: "—" };
      if (f.type === "forecast") {
        const m = lo ? Math.round((f.epoch - lo.epoch) / 60) : 0;
        return { a: "Forecast", b: "+" + m + " min" };
      }
      if (lo && f.time === lo.time) return { a: "Frame", b: "Latest" };
      const m = lo ? Math.round((lo.epoch - f.epoch) / 60) : 0;
      return { a: "Frame", b: "−" + m + " min" };
    }
    function render(s) {
      const f = s.frame; if (!f) return;
      layerFor(f);
      reveal();
      if (backgroundPreload) {
        prefetch(Math.max(0, s.index - 1));
        prefetch(Math.min(s.count - 1, s.index + 1));
        if (s.index + 2 < s.count) prefetch(s.index + 2);
      }
      const fcNow = f.type === "forecast";
      const when = P.etTime(f.epoch);
      root.setAttribute("data-frame", fcNow ? "fc" : "obs");
      $("r-seg").textContent = fcNow ? "Forecast valid" : "Observed";
      $("r-time").textContent = when; $("r-time").title = P.etLong(f.epoch);
      const tag = $("r-tag");
      if (fcNow) {
        const m = s.latestObserved ? Math.round((f.epoch - s.latestObserved.epoch) / 60) : 0;
        tag.hidden = false;
        tag.textContent = "Forecast +" + m + " min · not observed";
      } else {
        tag.hidden = true; tag.textContent = "";
      }
      if (!fixture) $("r-badge").textContent = fcNow ? "Forecast" : "Observed";
      const rel = relLabel(s);
      $("r-rel-a").textContent = rel.a; $("r-rel-b").textContent = rel.b;
      scrub.max = String(s.count - 1); scrub.value = String(s.index);
      scrub.setAttribute("aria-valuetext", (fcNow ? "Forecast valid " : "Observed ") + P.etLong(f.epoch) + (fcNow && s.latestObserved ? ", " + Math.round((f.epoch - s.latestObserved.epoch) / 60) + " minutes after the latest scan" : "") + (fixture ? ", test data" : ""));
      const hasFc = s.forecastOn && s.forecastCount > 0;
      tl.classList.toggle("has-fc", hasFc);
      $("r-now-mark").hidden = !hasFc;
      $("r-fcs").hidden = !hasFc;
      $("r-t-fc").hidden = !hasFc;
      if (hasFc) {
        $("r-obs").style.flexGrow = "120";
        $("r-fcs").style.flexGrow = "60";
      }
      placeThumb(s);
      const playing = s.status === "playing";
      play.setAttribute("aria-pressed", String(playing));
      play.setAttribute("aria-label", playing ? "Pause radar loop" : "Play radar loop");
      const lbl = $("r-play-lbl"); if (lbl) lbl.textContent = playing ? "Pause" : "Play";
      prev.disabled = s.index <= 0; next.disabled = s.index >= s.count - 1;
      if (!frameReady(f)) prefetch(s.index);
      loadingUI();
      ageText();
    }
    function ageText() {
      const s = player.snapshot(), lo = s.latestObserved; if (!lo) return;
      const ageEl = $("r-age"), dot = $("r-age-dot"), key = $("r-age-k");
      const m = Math.max(0, Math.round((Date.now() / 1000 - lo.epoch) / 60));
      const stale = !fixture && m >= STALE_MIN;
      if (dot) dot.classList.toggle("is-stale", stale);
      if (s.segment === "forecast") {
        if (key) key.textContent = "From scan";
        ageEl.innerHTML = "";
        if (dot) ageEl.appendChild(dot);
        ageEl.appendChild(document.createTextNode(P.etTime(lo.epoch).replace(" ET","") + " · " + (fixture ? "test" : P.age(Date.now() / 1000, lo.epoch))));
      } else {
        if (key) key.textContent = "Data age";
        ageEl.innerHTML = "";
        if (dot) ageEl.appendChild(dot);
        const label = fixture ? (P.etTime(lo.epoch) + " · test") : (stale ? ("Stale · " + P.age(Date.now() / 1000, lo.epoch)) : P.age(Date.now() / 1000, lo.epoch));
        ageEl.appendChild(document.createTextNode(label));
      }
      ageEl.title = fixture ? "Test data from " + P.etLong(lo.epoch) + ", not current" : P.etLong(lo.epoch);
    }
    player.on(render);
    render(player.snapshot()); ageText(); setInterval(ageText, 30000);
    [play, prev, next, scrub].forEach((b) => { b.disabled = false; }); render(player.snapshot());
    status.hidden = true;
    paintLabels();

    let timer = null;
    function schedule() {
      clearTimeout(timer); timer = null;
      if (player.snapshot().status !== "playing" || document.hidden) return;
      timer = setTimeout(function () {
        const list = player.frames();
        player.tick((i) => frameReady(list[i]), MIN_WINDOW);
        loadingUI();
        schedule();
      }, player.holdMs());
    }
    player.on(function () { if (!timer) schedule(); });
    play.addEventListener("click", function () { player.toggle(); schedule(); });
    prev.addEventListener("click", function () { player.step(-1); });
    next.addEventListener("click", function () { player.step(1); });
    scrub.addEventListener("pointerdown", function () { player.beginScrub(); });
    scrub.addEventListener("input", function () { if (player.snapshot().status !== "scrubbing") player.beginScrub(); player.seek(+scrub.value); });
    const endScrub = function () { player.endScrub(); schedule(); };
    scrub.addEventListener("change", endScrub); scrub.addEventListener("pointerup", endScrub); scrub.addEventListener("blur", endScrub);
    document.addEventListener("keydown", function (e) {
      if (e.target && /input|button|textarea/i.test(e.target.tagName) && e.target !== scrub) return;
      if (e.key === " ") { e.preventDefault(); player.toggle(); schedule(); }
    });
    document.addEventListener("visibilitychange", function () { if (document.hidden) { clearTimeout(timer); timer = null; } else schedule(); });

    let lastLatest = snap0.latestObserved.time;
    function refresh() {
      if (fixture || document.hidden) return;
      fetch("/api/radar-view").then((r) => r.json()).then(function (m) {
        if (!m.ok || !m.frames || !m.frames.length || m.fixture) return;
        if (m.limited) showLimit(m.limit_reason, m.limit_message);
        player.update(m.frames);
        const s = player.snapshot();
        if (s.forecastCount && !s.forecastOn) player.setForecast(true);
        if (!s.latestObserved || s.latestObserved.time === lastLatest) return;
        lastLatest = s.latestObserved.time; issue = lastLatest;
        const keep = new Set(player.observed().map((f) => f.time));
        layers.forEach(function (l, t) { if (!keep.has(t)) { if (shown === l) shown = null; map.removeLayer(l); layers.delete(t); loaded.delete(t); inflight.delete(t); } });
        window.__radarRefreshes = (window.__radarRefreshes || 0) + 1;
        render(player.snapshot()); ageText(); pump();
      }).catch(function () {});
    }
    setInterval(refresh, 180000);
    document.addEventListener("visibilitychange", function () { if (!document.hidden) refresh(); });
    window.__radarRefresh = refresh;
    window.__radarView = { map: map, player: player, loaded: loaded, layers: layers, fixture: fixture, reduce: reduce, labels: function () { return { data: labData, visible: labVis, paint: paintLabels, reserved: reserved }; }, preview: true, coverage: function () { return window.__radarCoverage; }, classifyCoverage: classifyCoverage, classifyView: classifyView, formatInh: formatInh, STALE_MIN: STALE_MIN, maxBounds: MAX_BOUNDS, backgroundPreload: function () { return backgroundPreload; } };
    setInterval(function () { if (loadTxt) loadingUI(); }, 500);
    map.on("moveend zoomend", function () { setTimeout(function () { loadingUI(); paintLabels(); }, 50); });
    (function waitFirst() {
      const first = player.snapshot().latestObserved || player.snapshot().frame;
      if (first) layerFor(first);
      if (first && frameReady(first)) {
        status.hidden = true;
        reveal();
        requestAnimationFrame(function () { requestAnimationFrame(afterFirstPaint); });
        return;
      }
      requestAnimationFrame(waitFirst);
    })();

    $("r-center").addEventListener("click", function () { map.flyToBounds(HOME, { duration: reduce ? 0 : 0.6 }); });
    let meDot = null;
    $("r-locate").addEventListener("click", function () {
      if (!navigator.geolocation) { status.textContent = "Location isn't available in this browser."; status.hidden = false; return; }
      status.textContent = "Finding your location…"; status.hidden = false;
      navigator.geolocation.getCurrentPosition(function (p) {
        const ll = L.latLng(p.coords.latitude, p.coords.longitude);
        const bounds = L.latLngBounds(MAX_BOUNDS);
        if (!bounds.contains(ll)) {
          status.textContent = "Your location is outside this map’s North Carolina coverage.";
          status.hidden = false;
          return;
        }
        status.hidden = true;
        if (meDot) map.removeLayer(meDot);
        meDot = L.circleMarker(ll, { radius: 7, className: "r-me-dot", weight: 2, color: "#fff", fillColor: getComputedStyle(root).getPropertyValue("--accent").trim() || "#0B4F6C", fillOpacity: 1, pane: "markerPane" }).addTo(map);
        map.setView(ll, Math.max(map.getZoom(), 8), { animate: !reduce });
        paintLabels();
      }, function () { status.textContent = "Location wasn't shared."; status.hidden = false; },
      { enableHighAccuracy: false, timeout: 10000, maximumAge: 300000 });
    });
  }

  function unavailable(meta) {
    window.__radarView = { unavailable: true, reason: meta.reason || null, preview: true };
    status.hidden = true;
    const plan = meta.reason === "plan" || meta.reason === "coming_soon";
    const quota = meta.reason === "quota" || meta.reason === "rate_limit";
    $("r-unavail-h").textContent = plan ? "Radar unavailable on current data plan" : (quota ? "Radar is temporarily limited" : "Radar is unavailable right now");
    $("r-unavail-b").textContent = plan
      ? "The radar feed isn't included in our current weather-data plan, so no radar frames are shown. Nothing here is old or simulated radar."
      : (quota
        ? (meta.limit_message || meta.message || "Radar is temporarily limited. Try again in a few minutes. No old frames are shown in their place.")
        : "We couldn't load radar frames. Try again in a few minutes. No old frames are shown in their place.");
    $("r-unavail").hidden = false; $("r-badge").textContent = "Radar off";
    $("r-legend").hidden = true;
    $("r-time").textContent = "—"; $("r-age").textContent = "—";
  }

  boot();
})();
