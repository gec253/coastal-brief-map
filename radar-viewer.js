/* /radar private viewer UI. OBSERVED radar, last two hours; FORECAST (nowcast) frames only when the user
   turns them on, labelled and drawn differently. Playback logic lives in radar-player.js (CBRadarPlayer).
   Times are America/New_York (ET). Test fixtures are only ever served by a local test server and are
   labelled "TEST DATA — not current radar" with their real (past) date. */
(function () {
  "use strict";
  const P = window.CBRadarPlayer;
  if (!P || !window.L || !window.CBCoast) return;
  const $ = (id) => document.getElementById(id);
  const q = location.search, root = document.documentElement;
  let dark = root.getAttribute("data-theme") === "dark";
  const mm = (s) => !!(window.matchMedia && matchMedia(s).matches);
  const reduce = mm("(prefers-reduced-motion: reduce)") || /[?&]motion=off\b/.test(q);
  const HOME = L.latLngBounds([33.75, -78.3], [36.55, -75.25]);
  const yieldTask = () => new Promise((r) => (window.scheduler && scheduler.yield ? scheduler.yield().then(r) : setTimeout(r, 0)));

  const clockF = new Intl.DateTimeFormat("en-US", { timeZone: "America/New_York", hour: "numeric", minute: "2-digit" });
  function tickClock() { $("r-clock").textContent = clockF.format(new Date()) + " ET"; }
  tickClock(); setInterval(tickClock, 15000);

  /* Theme: same site preference as /wind and the Morning Brief (localStorage "coastalBrief.theme"). */
  const THEME_STORE = "coastalBrief.theme";
  const sysDark = window.matchMedia ? matchMedia("(prefers-color-scheme: dark)") : null;
  const qTheme = (/[?&]theme=(light|dark)\b/.exec(q) || [])[1] || null;
  let onTheme = null;
  function stored() { try { const t = localStorage.getItem(THEME_STORE); return t === "light" || t === "dark" ? t : null; } catch (e) { return null; } }
  function resolved() { return stored() || (sysDark && sysDark.matches ? "dark" : "light"); }
  const tbtn = $("w-theme");
  function syncToggle() { tbtn.setAttribute("aria-pressed", String(dark)); tbtn.title = dark ? "Switch to day mode" : "Switch to night mode"; }
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
  tbtn.addEventListener("click", function () { applyTheme(dark ? "light" : "dark", true); });
  window.addEventListener("storage", function (e) { if (e.key === THEME_STORE || e.key === null) applyTheme(resolved(), false); });
  if (sysDark) {
    const onSys = function () { if (!stored() && !qTheme) applyTheme(resolved(), false); };
    if (sysDark.addEventListener) sysDark.addEventListener("change", onSys); else if (sysDark.addListener) sysDark.addListener(onSys);
  }
  window.addEventListener("pageshow", function (e) { if (e.persisted) applyTheme(qTheme && !stored() ? qTheme : resolved(), false); });

  const play = $("r-play"), prev = $("r-prev"), next = $("r-next"), scrub = $("r-scrub"), fc = $("r-fc"), status = $("r-status"), tl = $("r-tl"), stage = $("r-stage");

  /* Radar tiles are drawn into <canvas> (like the wind coastline), so a radar image is never the LCP element. */
  const CanvasTiles = L.GridLayer.extend({
    createTile: function (c, done) {
      const t = document.createElement("canvas"), sz = this.getTileSize(); t.width = sz.x; t.height = sz.y;
      const img = new Image(); img.decoding = "async";
      img.onload = function () { t.getContext("2d").drawImage(img, 0, 0, sz.x, sz.y); done(null, t); };
      img.onerror = function () { done(null, t); };            // missing tile = transparent, not an error state
      img.src = L.Util.template(this.options.url, { z: c.z, x: c.x, y: c.y });
      return t;
    },
  });

  async function boot() {
    // Ask for the frame list first (preloaded by the page); show "unavailable" before any map work.
    const metaP = fetch("/api/radar-view").then((r) => r.json()).catch(() => ({ ok: false, reason: "network" }));
    metaP.then(function (m) { if (!m.ok || !m.frames || !m.frames.length) unavailable(m); });
    const map = L.map("rmap", { zoomControl: true, attributionControl: false, zoomSnap: 0.5, minZoom: 5, maxZoom: 9.5, maxBounds: [[30, -84], [40, -69]], fadeAnimation: false });
    map.zoomControl.setPosition("topright");
    map.fitBounds(HOME);
    map.createPane("radar"); map.getPane("radar").style.zIndex = 350; map.getPane("radar").classList.add("leaflet-radar-pane");
    await yieldTask();
    const coastStyle = () => { const c = getComputedStyle(root); return { land: c.getPropertyValue("--coast-land").trim(), line: c.getPropertyValue("--coast-line").trim(), lineWidth: dark ? 1 : 0.9 }; };
    const coast = window.CBCoast.layer(Object.assign({ base: "/wind/coast-" }, coastStyle())).addTo(map);
    // Coastline line on top of the radar so the shore stays readable through heavy echoes.
    onTheme = function () { coast.restyle(coastStyle()); };

    const meta = await metaP;
    window.__radarMeta = { ok: !!meta.ok, fixture: !!meta.fixture, reason: meta.reason || null };
    if (!meta.ok || !meta.frames || !meta.frames.length) return unavailable(meta);

    const fixture = !!meta.fixture;
    if (fixture) {
      $("r-test").hidden = false; $("r-test").textContent = meta.fixture_label + " · " + P.etDate(meta.frames[0].time_epoch) + ", " + new Date(meta.frames[0].time_epoch * 1000).getUTCFullYear(); $("r-badge").textContent = "Test data"; $("r-badge").classList.add("is-test");
      $("r-attrib").textContent = "TEST DATA: synthetic pattern, not radar · Coastline: U.S. Census Bureau, 2025 cartographic boundary file, 1:500,000 (not endorsed by the Census Bureau)";
    } else if (meta.attribution) {
      $("r-attrib").firstChild.textContent = meta.attribution.replace(/\.$/, "") + " · Coastline: U.S. Census Bureau, 2025 cartographic boundary file, 1:500,000 (not endorsed by the Census Bureau)";
    }
    if (meta.legend && meta.legend.length > 1) $("r-ramp").style.background = "linear-gradient(90deg," + meta.legend.map((r) => r.color).join(",") + ")";

    const player = P.create(meta.frames);
    const snap0 = player.snapshot();
    if (!snap0.observedCount) return unavailable({ ok: false, reason: "upstream" });
    fc.disabled = !snap0.forecastCount;
    $("r-obs").style.flexGrow = String(snap0.observedCount); $("r-fcs").style.flexGrow = String(Math.max(1, snap0.forecastCount));

    /* One tile layer per frame, created on demand; all start invisible. Playback only advances to a
       frame whose tiles have loaded, so the map never flashes empty. */
    const layers = new Map(), loaded = new Set(), t0 = performance.now(), loadMs = {};
    const tmpl = meta.tile_url;
    let issue = snap0.latestObserved.time;   // forecast tiles are re-issued with each frame list
    function layerFor(f) {
      let l = layers.get(f.time);
      if (l) return l;
      l = new CanvasTiles({ url: tmpl.replace("{time}", f.time) + (f.type === "forecast" ? "&v=" + issue : ""),
        pane: "radar", opacity: 0, className: "r-frame" + (f.type === "forecast" ? " r-frame-fc" : ""),
        tileSize: meta.tile_size || 256, maxNativeZoom: meta.max_native_zoom || meta.max_zoom || 7, minZoom: 5, maxZoom: 9.5,
        updateWhenIdle: true, keepBuffer: 0,
      });
      l.once("load", function () { loaded.add(f.time); loadMs[f.time] = Math.round(performance.now() - t0); maybeAllLoaded(); });
      l.addTo(map); layers.set(f.time, l);
      return l;
    }
    function maybeAllLoaded() {
      const obs = player.observed();
      if (!window.__radarPreload && obs.every((f) => loaded.has(f.time))) window.__radarPreload = { allObservedMs: Math.max.apply(null, obs.map((f) => loadMs[f.time])), firstMs: loadMs[obs[obs.length - 1].time], frames: obs.length };
    }
    // Background prefetch: the current frame first, then neighbours, two at a time (never all at once).
    let pf = 0;
    function prefetch(center) {
      const list = player.frames(), order = [];
      for (let d = 0; d < list.length; d++) { [center + d, center - d].forEach((i) => { const j = (i + list.length) % list.length; if (order.indexOf(j) < 0) order.push(j); }); }
      const pending = order.map((i) => list[i]).filter((f) => !layers.has(f.time));
      const go = () => { while (pf < 2 && pending.length) { const f = pending.shift(); pf++; const l = layerFor(f); const done = () => { pf--; go(); }; if (loaded.has(f.time)) done(); else l.once("load", done); } };
      go();
    }
    let shown = null;
    function render(s) {
      const f = s.frame; if (!f) return;
      const l = layerFor(f);
      if (shown && shown !== l) shown.setOpacity(0);
      l.setOpacity(f.type === "forecast" ? 0.6 : 0.78); shown = l;
      const fcNow = f.type === "forecast";
      const when = P.etTime(f.epoch);
      $("r-seg").textContent = fcNow ? "Forecast" : "Observed";
      $("r-time").textContent = when; $("r-time").title = P.etLong(f.epoch);
      $("r-tag").textContent = (fcNow ? "Forecast · " : "Observed · ") + P.etTime(f.epoch);
      $("r-tag").classList.toggle("is-fc", fcNow); stage.classList.toggle("is-fc", fcNow);
      $("r-badge").classList.toggle("is-fc", fcNow && !fixture);
      if (!fixture) $("r-badge").textContent = fcNow ? "Forecast" : "Observed";
      const n = fcNow ? (s.index - s.boundary + 1) + "/" + s.forecastCount : (s.index + 1) + "/" + s.observedCount;
      $("r-count").textContent = (fcNow ? "F " : "") + n;
      scrub.max = String(s.count - 1); scrub.value = String(s.index);
      scrub.setAttribute("aria-valuetext", (fcNow ? "Forecast, " : "Observed, ") + P.etLong(f.epoch) + (fixture ? ", test data" : ""));
      tl.classList.toggle("has-fc", s.forecastOn); tl.classList.toggle("on-fc", fcNow);
      $("r-t1").textContent = s.forecastOn ? "+1 h fcst" : "Latest";
      const playing = s.status === "playing";
      play.setAttribute("aria-pressed", String(s.status === "playing"));
      play.setAttribute("aria-label", s.status === "playing" ? "Pause radar loop" : "Play radar loop");
      prev.disabled = s.index <= 0; next.disabled = s.index >= s.count - 1;
      if (!playing) prefetch(s.index);
    }
    function ageText() {
      const lo = player.snapshot().latestObserved; if (!lo) return;
      $("r-age").textContent = fixture ? P.etTime(lo.epoch) + " · test" : P.age(Date.now() / 1000, lo.epoch);
      $("r-age").title = fixture ? "Test data from " + P.etLong(lo.epoch) + ", not current" : P.etLong(lo.epoch);
    }
    player.on(render);
    render(player.snapshot()); ageText(); setInterval(ageText, 30000);
    [play, prev, next, scrub].forEach((b) => { b.disabled = false; }); render(player.snapshot());
    status.hidden = true;

    let timer = null;
    function schedule() {
      clearTimeout(timer); timer = null;
      if (player.snapshot().status !== "playing" || document.hidden) return;
      timer = setTimeout(function () {
        const list = player.frames();
        const before = player.snapshot().index;
        player.tick((i) => loaded.has(list[i].time));
        if (player.snapshot().index === before) prefetch(before + 1);   // buffering: wait for the next frame
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
    fc.addEventListener("change", function () { player.setForecast(fc.checked); });
    document.addEventListener("keydown", function (e) {
      if (e.target && /input|button|textarea/i.test(e.target.tagName) && e.target !== scrub) return;
      if (e.key === " ") { e.preventDefault(); player.toggle(); schedule(); }
    });
    document.addEventListener("visibilitychange", function () { if (document.hidden) { clearTimeout(timer); timer = null; } else schedule(); });
    /* Real data: re-read the frame list every 3 min (the server's radar.json cache TTL) while the page is
       visible, so the newest observed frame keeps arriving. Old frames' layers are dropped. */
    let lastLatest = snap0.latestObserved.time;
    function refresh() {
      if (fixture || document.hidden) return;
      fetch("/api/radar-view").then((r) => r.json()).then(function (m) {
        if (!m.ok || !m.frames || !m.frames.length || m.fixture) return;
        player.update(m.frames);
        const s = player.snapshot(); if (!s.latestObserved || s.latestObserved.time === lastLatest) return;
        lastLatest = s.latestObserved.time; issue = lastLatest;
        const keep = new Set(player.observed().map((f) => f.time));   // forecast layers are rebuilt
        layers.forEach(function (l, t) { if (!keep.has(t)) { if (shown === l) shown = null; map.removeLayer(l); layers.delete(t); loaded.delete(t); } });
        fc.disabled = !s.forecastCount;
        $("r-obs").style.flexGrow = String(s.observedCount); $("r-fcs").style.flexGrow = String(Math.max(1, s.forecastCount));
        window.__radarRefreshes = (window.__radarRefreshes || 0) + 1;
        render(player.snapshot()); ageText(); prefetch(s.observedCount - 1);
      }).catch(function () {});
    }
    setInterval(refresh, 180000);
    document.addEventListener("visibilitychange", function () { if (!document.hidden) refresh(); });
    window.__radarRefresh = refresh;
    window.__radarView = { map: map, player: player, loaded: loaded, layers: layers, fixture: fixture, reduce: reduce };
    // Start on the latest observed frame; autoplay (from the oldest frame) unless reduced motion.
    prefetch(snap0.index);
    if (!reduce) { player.seek(0); player.play(); schedule(); }
  }

  function unavailable(meta) {
    window.__radarView = { unavailable: true, reason: meta.reason || null };
    status.hidden = true;
    const plan = meta.reason === "plan" || meta.reason === "coming_soon";
    $("r-unavail-h").textContent = plan ? "Radar unavailable on current data plan" : "Radar is unavailable right now";
    $("r-unavail-b").textContent = plan
      ? "The radar feed isn't included in our current weather-data plan, so no radar frames are shown. Nothing here is old or simulated radar."
      : "We couldn't load radar frames. Try again in a few minutes. No old frames are shown in their place.";
    $("r-unavail").hidden = false; $("r-badge").textContent = "Radar off";
    $("r-legend").hidden = true; document.querySelector(".r-fc").hidden = true;
    $("r-time").textContent = "—"; $("r-age").textContent = "—"; $("r-count").textContent = "—";
  }

  boot();
})();
