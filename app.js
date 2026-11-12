/* Coastal Brief NOAA map test. No geolocation. No market data. */
(function () {
  const SST_TIME = "2026-11-09T09:00:00Z";
  const SST_FALLBACK_TIME = "2026-11-08T12:00:00Z";
  const CENTER = [34.7, -76.7];
  const ZOOM = 8;
  const WASH_OPACITY = { light: { wind: 0.72, waves: 0.85, sst: 0.85 }, chart: { wind: 0.55, waves: 0.58, sst: 0.6 }, fullscreen: { wind: 0.72, waves: 0.85, sst: 0.95 } };

  const $ = (id) => document.getElementById(id);
  let map = null;
  let layers = {};
  let activeMarine = "wind";
  let baseKind = "light";
  let leafletReady = false;
  let sstUsingFallback = false;
  let sstLoadTimer = null;

  const THEME_STORE = "coastalBrief.theme";
  const DEFAULT_TIDE_STATION_ID = "8656483";
  const DEFAULT_TIDE_STATION_NAME = "Beaufort, Duke Marine Lab, NC";
  const RADAR_MAX = 6;
  const RADAR_FRAME_MS = 750;
  const RADAR_HOLD_MS = 1200;
  const RADAR_REFRESH_MS = 5 * 60 * 1000;
  const radar = {
    requested: false,
    loading: false,
    ready: false,
    unavailable: false,
    message: "",
    meta: null,
    layers: [],
    index: 0,
    timer: null,
    playing: true,
    includeForecast: false,
    lastFetch: 0,
    inView: true,
  };

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c];
    });
  }
  function prefersReducedMotion() {
    return window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  }
  function currentTheme() {
    return document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light";
  }
  function isDark() {
    return currentTheme() === "dark";
  }
  function syncThemeToggle() {
    const btn = $("theme-toggle");
    if (!btn) return;
    const dark = isDark();
    btn.setAttribute("aria-pressed", dark ? "true" : "false");
    btn.setAttribute("aria-label", dark ? "Switch to light mode" : "Switch to dark mode");
    btn.textContent = dark ? "Light mode" : "Dark mode";
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute("content", "#0B2A3D");
  }
  function setTheme(theme, persist) {
    const t = theme === "dark" ? "dark" : "light";
    document.documentElement.setAttribute("data-theme", t);
    if (persist) {
      try { localStorage.setItem(THEME_STORE, t); } catch (e) {}
    }
    syncThemeToggle();
    if (map) applyBasemapForTheme();
  }
  function initTheme() {
    syncThemeToggle();
    const btn = $("theme-toggle");
    if (btn) {
      btn.addEventListener("click", function () {
        setTheme(isDark() ? "light" : "dark", true);
      });
    }
    try {
      if (!localStorage.getItem(THEME_STORE) && window.matchMedia) {
        const mq = window.matchMedia("(prefers-color-scheme: dark)");
        const onChange = function (e) {
          if (!localStorage.getItem(THEME_STORE)) setTheme(e.matches ? "dark" : "light", false);
        };
        if (mq.addEventListener) mq.addEventListener("change", onChange);
        else if (mq.addListener) mq.addListener(onChange);
      }
    } catch (e) {}
  }
  function markJustPosted(el) {
    if (!el) return;
    el.classList.remove("just-posted");
    void el.offsetWidth;
    el.classList.add("just-posted");
    setTimeout(function () { el.classList.remove("just-posted"); }, 4000);
  }
  function updateMiniBar(parts) {
    if (parts.wind != null) $("mini-wind").textContent = parts.wind;
    if (parts.wtmp != null) $("mini-wtmp").textContent = parts.wtmp;
    if (parts.tide != null) $("mini-tide").textContent = parts.tide;
  }
  function polar(cx, cy, r, deg) {
    const rad = ((deg - 90) * Math.PI) / 180;
    return [cx + r * Math.cos(rad), cy + r * Math.sin(rad)];
  }
  function windCompassSvg(dirDeg, label, speedKt, gustKt) {
    const deg = isFinite(Number(dirDeg)) ? Number(dirDeg) : 0;
    const aria = "Wind compass, " + label + " " + speedKt + " knots, gust " + gustKt + " knots, wind from " + Math.round(deg) + " degrees";
    const tip = polar(38, 38, 24, deg);
    const left = polar(38, 38, 8, deg + 140);
    const right = polar(38, 38, 8, deg - 140);
    return (
      '<svg viewBox="0 0 76 76" role="img" aria-label="' + escapeHtml(aria) + '">' +
      '<circle cx="38" cy="38" r="34" fill="none" stroke="#5BA8A0" stroke-width="2"/>' +
      '<text x="38" y="14" text-anchor="middle" font-size="8" fill="currentColor">N</text>' +
      '<text x="38" y="70" text-anchor="middle" font-size="8" fill="currentColor">S</text>' +
      '<text x="10" y="41" text-anchor="middle" font-size="8" fill="currentColor">W</text>' +
      '<text x="66" y="41" text-anchor="middle" font-size="8" fill="currentColor">E</text>' +
      '<polygon points="' + tip[0].toFixed(1) + "," + tip[1].toFixed(1) + " " +
        left[0].toFixed(1) + "," + left[1].toFixed(1) + " " +
        right[0].toFixed(1) + "," + right[1].toFixed(1) + '" fill="#5BA8A0" stroke="currentColor" stroke-width="1"/>' +
      '<circle cx="38" cy="38" r="3.2" fill="currentColor"/>' +
      "</svg>"
    );
  }
  function thermoSvg(f) {
    const t = isFinite(Number(f)) ? Number(f) : 50;
    const pct = Math.max(0, Math.min(1, (t - 32) / (90 - 32)));
    const bot = 52;
    const top = 14;
    const fillY = bot - (bot - top) * pct;
    const h = bot - fillY + 8;
    const aria = "Water temperature thermometer, " + t + " degrees Fahrenheit";
    return (
      '<svg viewBox="0 0 76 76" role="img" aria-label="' + escapeHtml(aria) + '">' +
      '<rect x="33" y="10" width="10" height="44" rx="5" fill="none" stroke="#5BA8A0" stroke-width="2"/>' +
      '<circle cx="38" cy="60" r="10" fill="#5BA8A0"/>' +
      '<rect x="35" y="' + fillY.toFixed(1) + '" width="6" height="' + h.toFixed(1) + '" fill="currentColor"/>' +
      "</svg>"
    );
  }
  function pressureSvg(inHg, trend) {
    const v = isFinite(Number(inHg)) ? Number(inHg) : 30;
    const pct = Math.max(0, Math.min(1, (v - 28.8) / (31.2 - 28.8)));
    const angle = -120 + 240 * pct;
    const tip = polar(38, 42, 26, angle);
    const a0 = polar(38, 42, 28, -120);
    const a1 = polar(38, 42, 28, 120);
    const arrow = trend === "falling" ? " falling" : trend === "rising" ? " rising" : " steady";
    const aria = "Pressure dial, " + v.toFixed(2) + " inches of mercury," + arrow;
    return (
      '<svg viewBox="0 0 76 76" role="img" aria-label="' + escapeHtml(aria) + '">' +
      '<path d="M ' + a0[0].toFixed(1) + " " + a0[1].toFixed(1) + " A 28 28 0 1 1 " + a1[0].toFixed(1) + " " + a1[1].toFixed(1) + '" fill="none" stroke="#5BA8A0" stroke-width="3" stroke-linecap="round"/>' +
      '<line x1="38" y1="42" x2="' + tip[0].toFixed(1) + '" y2="' + tip[1].toFixed(1) + '" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"/>' +
      '<circle cx="38" cy="42" r="3.2" fill="#5BA8A0"/>' +
      '<text x="16" y="70" font-size="7" fill="currentColor">29</text>' +
      '<text x="52" y="70" font-size="7" text-anchor="end" fill="currentColor">31</text>' +
      "</svg>"
    );
  }
  function swellSvg(heightFt, periodS) {
    const h = isFinite(Number(heightFt)) ? Number(heightFt) : 2;
    const p = isFinite(Number(periodS)) ? Number(periodS) : 8;
    const amp = Math.max(6, Math.min(18, h * 3.5));
    const y = 40;
    function wavePath(offset) {
      let d = "M " + (-20 + offset) + " " + y;
      for (let x = -20; x <= 96; x += 4) {
        const yy = y + Math.sin((x + offset) / 10) * amp;
        d += " L " + x + " " + yy.toFixed(1);
      }
      return d;
    }
    const motion = prefersReducedMotion() ? "" : " swell-wave";
    const aria = "Animated swell, " + h.toFixed(1) + " feet at " + p + " seconds";
    return (
      '<svg viewBox="0 0 76 76" role="img" aria-label="' + escapeHtml(aria) + '">' +
      '<g class="' + motion.trim() + '">' +
      '<path d="' + wavePath(0) + '" fill="none" stroke="#5BA8A0" stroke-width="2.5" stroke-linecap="round"/>' +
      '<path d="' + wavePath(10) + '" fill="none" stroke="currentColor" stroke-width="1.5" opacity="0.55" stroke-linecap="round"/>' +
      "</g></svg>"
    );
  }
  function tideIconSvg(type, label) {
    const high = type === "H";
    const aria = "Next tide, " + (label || (high ? "high" : "low"));
    const pts = high ? "38,14 58,50 18,50" : "18,26 58,26 38,62";
    return (
      '<svg viewBox="0 0 76 76" role="img" aria-label="' + escapeHtml(aria) + '">' +
      '<polygon points="' + pts + '" fill="#5BA8A0" stroke="currentColor" stroke-width="1"/>' +
      "</svg>"
    );
  }
  function formatNextTide(type, timeET, heightFt) {
    const clock = String(timeET || "").replace(" ET", "").replace(" PM", "p").replace(" AM", "a");
    return (type === "H" ? "Hi " : "Lo ") + clock;
  }
  function etYmd(date, addDays) {
    const map = {};
    new Intl.DateTimeFormat("en-US", {
      timeZone: "America/New_York",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).formatToParts(date).forEach(function (part) {
      if (part.type !== "literal") map[part.type] = part.value;
    });
    const utc = new Date(Date.UTC(Number(map.year), Number(map.month) - 1, Number(map.day) + (addDays || 0)));
    return String(utc.getUTCFullYear()) + String(utc.getUTCMonth() + 1).padStart(2, "0") + String(utc.getUTCDate()).padStart(2, "0");
  }
  function loadLiveNextTide() {
    const begin = etYmd(new Date(), 0);
    const end = etYmd(new Date(), 1);
    const url = "/api/tides?station=" + encodeURIComponent(DEFAULT_TIDE_STATION_ID) + "&begin=" + begin + "&end=" + end + "&curve=" + begin;
    return fetch(url)
      .then(function (r) { return r.json(); })
      .then(function (data) {
        const card = $("card-tide");
        if (card) card.classList.remove("is-loading");
        if (!data || !data.ok) {
          $("v-tide").textContent = "—";
          $("s-tide").textContent = (data && data.error) || "Could not load the next tide.";
          $("m-tide").textContent = DEFAULT_TIDE_STATION_NAME;
          $("g-tide").innerHTML = tideIconSvg("H", "unavailable");
          updateMiniBar({ tide: "—" });
          return;
        }
        const now = new Date();
        const preds = data.predictions || [];
        let next = null;
        for (let i = 0; i < preds.length; i++) {
          const d = parseTideTime(preds[i].t);
          if (d && d > now) { next = preds[i]; break; }
        }
        if (!next) {
          $("v-tide").textContent = "—";
          $("s-tide").textContent = "No upcoming tide in the next day.";
          $("m-tide").textContent = (data.station && data.station.name) || DEFAULT_TIDE_STATION_NAME;
          updateMiniBar({ tide: "—" });
          return;
        }
        const clock = formatTideClock(next.t) + " ET";
        const typ = next.type === "H" ? "H" : "L";
        const height = Number(next.v);
        const label = formatNextTide(typ, clock, height);
        $("v-tide").textContent = label;
        $("s-tide").textContent = (isFinite(height) ? height.toFixed(1) + " ft · " : "") + "live NOAA prediction";
        $("m-tide").textContent = ((data.station && data.station.name) || DEFAULT_TIDE_STATION_NAME) + " · " + clock;
        $("g-tide").innerHTML = tideIconSvg(typ, (typ === "H" ? "high " : "low ") + clock);
        updateMiniBar({ tide: label });
        markJustPosted($("card-tide"));
        const tag = document.createElement("span");
        tag.className = "just-posted badge";
        tag.style.marginLeft = "6px";
        tag.textContent = "Just posted";
        if (!$("m-tide").querySelector(".just-posted")) {
          $("m-tide").appendChild(document.createTextNode(" "));
          $("m-tide").appendChild(tag);
          setTimeout(function () { if (tag.parentNode) tag.parentNode.removeChild(tag); }, 4000);
        }
      })
      .catch(function () {
        const card = $("card-tide");
        if (card) card.classList.remove("is-loading");
        $("v-tide").textContent = "—";
        $("s-tide").textContent = "Could not load the next tide.";
        $("m-tide").textContent = DEFAULT_TIDE_STATION_NAME;
        updateMiniBar({ tide: "—" });
      });
  }

  function loadSnapshot() {
    return fetch("/api/snapshot")
      .then((r) => r.json())
      .catch(() => fetch("data/snapshot.json").then((r) => r.json()));
  }

  function loadAds() {
    return fetch("/api/ads").then((r) => r.json());
  }

  function fillWeather(data) {
    const b = data.buoy;
    $("v-waves").textContent = b.waves.heightFt.toFixed(1) + " ft";
    $("s-waves").textContent =
      b.waves.periodS + " s · " + b.waves.timeET + " · from " + b.waves.heightM + " m";
    $("v-wind").textContent = b.wind.dirLabel + " " + b.wind.speedKt + " kt";
    $("s-wind").textContent =
      "gust " + b.wind.gustKt + " kt · " + b.wind.timeET + " · from " + b.wind.speedMs + " m/s";
    $("v-wtmp").textContent = b.waterTemp.fahrenheit + "°F";
    $("s-wtmp").textContent = b.waterTemp.timeET + " · from " + b.waterTemp.celsius + "°C";
    $("v-pres").textContent = b.pressure.inHg.toFixed(2) + " " + (b.pressure.trend === "falling" ? "↓" : b.pressure.trend === "rising" ? "↑" : "→");
    $("s-pres").textContent = b.pressure.trend + " · " + b.pressure.timeET + " · from " + b.pressure.hPa + " hPa";

    $("v-surf").textContent =
      b.surf.swellPeriodS + " s · " + b.surf.swellDir + " · " + b.surf.swellHeightFt.toFixed(1) + " ft";
    $("s-surf").textContent =
      b.surf.periodRead + ". " + b.surf.windVsBeach + ". " +
      b.surf.note + " " + b.name + " (" + b.id + "), " + b.surf.timeET +
      ". Swell height converted from " + b.surf.swellHeightM.toFixed(1) + " m.";

    $("freshness-badge").textContent = "Last updated " + b.surf.timeET;
    $("freshness-badge").classList.remove("amber");

    $("g-waves").innerHTML = swellSvg(b.waves.heightFt, b.waves.periodS);
    $("g-wind").innerHTML = windCompassSvg(b.wind.dirDeg, b.wind.dirLabel, b.wind.speedKt, b.wind.gustKt);
    $("g-wtmp").innerHTML = thermoSvg(b.waterTemp.fahrenheit);
    $("g-pres").innerHTML = pressureSvg(b.pressure.inHg, b.pressure.trend);
    $("m-waves").textContent = b.name + " · " + b.waves.timeET;
    $("m-wind").textContent = b.name + " · " + b.wind.timeET;
    $("m-wtmp").textContent = b.name + " · " + b.waterTemp.timeET;
    $("m-pres").textContent = b.name + " · " + b.pressure.timeET;
    ["card-waves", "card-wind", "card-wtmp", "card-pres"].forEach(function (id) {
      const el = $(id);
      if (el) el.classList.remove("is-loading");
    });
    updateMiniBar({
      wind: b.wind.dirLabel + " " + b.wind.speedKt + " kt",
      wtmp: b.waterTemp.fahrenheit + "°F",
    });
    loadLiveNextTide();

    const fc = data.forecast;
    $("fc-meta").textContent =
      fc.office + ". Issued " + fc.generatedAtET + ". Temperatures are °F as reported. Wind is shown in knots, converted from the NWS mph figures.";
    const strip = $("forecast-strip");
    strip.innerHTML = "";
    const periods = fc.periods.filter((p) => p.name !== "This Afternoon");
    periods.forEach((p) => {
      const el = document.createElement("div");
      el.className = "day";
      el.innerHTML =
        '<div class="dn"></div><div class="dt"></div><div class="dw"></div><div></div>';
      el.children[0].textContent = p.name;
      el.children[1].textContent = p.tempF + "°F";
      el.children[2].textContent = p.windDir + " " + p.windKt;
      el.children[3].textContent = p.short;
      strip.appendChild(el);
    });
  }

  function fillAds(ads) {
    if (!ads) return;
    const mode = ads.mode || (ads.hardPause || !ads.adsOn ? "paused" : (ads.reducedRegions && ads.reducedRegions.length ? "reduced" : "full"));
    const head = ads.adsOn
      ? (mode === "reduced" ? "Ads flag would be ON, at reduced density." : "Ads flag would be ON.")
      : "Ads flag would be OFF (paused).";
    const reasons = (ads.reasons || []).join(" ");
    $("ops-box").innerHTML =
      "<strong>Ad-pause check (site ops, not shown as a public alert):</strong> " +
      head + " " + reasons +
      " A small craft advisory only thins ads on the affected region’s pages. After a hard pause, ads resume only when 12 hours have passed with no gale-or-stronger or tropical warning. Storm mode still needs Ed’s confirmation and is a separate switch. The site flips its own ads-on/off flag in ads.json (AdSense has no on/off API).";
  }

  function tickRow(pairs) {
    return (
      '<div class="tick-row">' +
      pairs
        .map(function (p) {
          return '<span style="left:' + p[0] + '%">' + p[1] + "</span>";
        })
        .join("") +
      "</div>"
    );
  }

  function legendHtml(kind) {
    if (kind === "wind") {
      return (
        "<strong>Wind forecast (knots)</strong> — NWS NDFD color table, official unit knots. " +
        "Colors come from digital.weather.gov’s windspd colormap (1-knot steps, 0–150). " +
        "Checked tonight against live forecast tiles: pixel colors matched the table exactly. Forecast, not the buoy reading." +
        '<div class="bar wind-bar" aria-hidden="true"></div>' +
        tickRow([[0, "0"], [20, "20"], [40, "40"], [60, "60"], [80, "80"], [100, "100 kt"]])
      );
    }
    if (kind === "waves") {
      return (
        "<strong>Wave forecast (feet)</strong> — NWS NDFD significant wave height. Wash and number labels are requested as two separate layers (combining them paints land black). Colors from the official NDFD waveheight table. Forecast, not a beach break." +
        '<div class="bar wave-bar" aria-hidden="true"></div>' +
        tickRow([[0, "0"], [5, "5"], [10, "10"], [15, "15"], [20, "20 ft"]])
      );
    }
    const sstNote = sstUsingFallback
      ? " Using the CoastWatch blended 5 km product as a fallback (latest analysis 8 Nov 2026, 7:00 AM ET) because the usual JPL MUR tiles failed. Coarser than the 1 km MUR layer."
      : " CoastWatch / JPL MUR analysis, 9 Nov 2026, 4:00 AM ET.";
    return (
      "<strong>Sea-surface temperature</strong> —" + sstNote +
      " Source is °C (0–32°C); the scale below is converted to °F. Satellite estimate, not the buoy reading." +
      '<div class="bar sst-bar" aria-hidden="true"></div>' +
      '<div class="scale"><span>32°F</span><span>90°F</span></div>'
    );
  }

  function radarLegendHtml() {
    if (radar.unavailable || !radar.meta) {
      return "<strong>Radar</strong> — " + escapeHtml(radar.message || "Radar coming soon") + " The rest of the map still works.";
    }
    const meta = radar.meta;
    let bar = "";
    let ticks = "";
    const legend = meta.legend || [];
    const safe = legend.filter(function (row) {
      return row && /^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/.test(String(row.color || ""));
    });
    if (safe.length) {
      const stops = safe.map(function (row, i) {
        const pct = safe.length === 1 ? 0 : (i / (safe.length - 1)) * 100;
        return row.color + " " + pct + "%";
      }).join(",");
      bar = '<div class="bar radar-bar" style="background:linear-gradient(90deg,' + stops + ')" aria-hidden="true"></div>';
      const first = safe[0].from_mm_h;
      const mid = safe[Math.floor(safe.length / 2)].from_mm_h;
      const last = safe[safe.length - 1].from_mm_h;
      ticks = tickRow([[0, String(first) + " mm/h"], [50, String(mid)], [100, String(last)]]);
    }
    return (
      "<strong>Weather radar</strong> — NOAA MRMS via WeatherAPI.com. Observed scans are about every 5 minutes; this map loops the last six frames and reuses cached tiles. Frames labeled forecast are a one-hour nowcast, not a completed scan. " +
      escapeHtml(meta.disclaimer || "") + " " +
      escapeHtml(meta.attribution || "") +
      bar + ticks
    );
  }

  function setLegend(kind) {
    $("legend-box").innerHTML = kind === "radar" ? radarLegendHtml() : legendHtml(kind);
  }

  function loadScript(src) {
    return new Promise((resolve, reject) => {
      const s = document.createElement("script");
      s.src = src;
      s.onload = resolve;
      s.onerror = () => reject(new Error("Failed to load " + src));
      document.head.appendChild(s);
    });
  }

  function loadCss(href) {
    return new Promise((resolve, reject) => {
      const l = document.createElement("link");
      l.rel = "stylesheet";
      l.href = href;
      l.onload = resolve;
      l.onerror = () => reject(new Error("Failed to load " + href));
      document.head.appendChild(l);
    });
  }

  /* ERDDAP WMS only accepts EPSG:4326 / CRS:84, not Web Mercator. */
  function Wms4326(url, options) {
    return new (L.TileLayer.extend({
      options: options,
      initialize: function (u, opts) {
        L.TileLayer.prototype.initialize.call(this, u, opts);
      },
      getTileUrl: function (coords) {
        const tileBounds = this._tileCoordsToBounds(coords);
        const size = this.getTileSize();
        const params = {
          service: "WMS",
          version: "1.3.0",
          request: "GetMap",
          layers: this.options.layers,
          styles: this.options.styles || "",
          crs: "EPSG:4326",
          bbox: [
            tileBounds.getSouth(),
            tileBounds.getWest(),
            tileBounds.getNorth(),
            tileBounds.getEast(),
          ].join(","),
          width: size.x,
          height: size.y,
          format: this.options.format || "image/png",
          transparent: "TRUE",
        };
        if (this.options.time) params.time = this.options.time;
        const q = Object.keys(params)
          .map((k) => encodeURIComponent(k) + "=" + encodeURIComponent(params[k]))
          .join("&");
        return this._url + (this._url.indexOf("?") >= 0 ? "&" : "?") + q;
      },
    }))(url, options);
  }

  function withRetry(layer, tries) {
    tries = tries || 3;
    layer.on("tileerror", function (e) {
      const tile = e.tile;
      const n = Number(tile.dataset.retry || 0);
      if (n >= tries) return;
      tile.dataset.retry = String(n + 1);
      const src = e.url || tile.getAttribute("src") || tile.src;
      // Retry the same URL. Do not append extra query flags (ERDDAP can reject them).
      setTimeout(function () {
        tile.src = src;
      }, 800 * Math.pow(2, n));
    });
    return layer;
  }

  function showSstLoading(on, text) {
    const el = $("sst-loading");
    if (!el) return;
    if (on) {
      el.hidden = false;
      el.textContent = text || "Loading water temps…";
    } else {
      el.hidden = true;
    }
  }

  function bindSstLoading(layer) {
    layer.on("loading", function () {
      showSstLoading(true, sstUsingFallback ? "Loading fallback water temps…" : "Loading water temps…");
      if (sstLoadTimer) clearTimeout(sstLoadTimer);
      sstLoadTimer = setTimeout(function () {
        if (activeMarine === "sst") showSstLoading(true, "Water temps are slow — still trying…");
      }, 8000);
    });
    layer.on("load", function () {
      if (sstLoadTimer) clearTimeout(sstLoadTimer);
      showSstLoading(false);
    });
  }

  function makePrimarySst() {
    return withRetry(Wms4326("/proxy/sst/erddap/wms/jplMURSST41/request", {
      layers: "jplMURSST41:analysed_sst",
      format: "image/png",
      transparent: true,
      opacity: WASH_OPACITY[baseKind].sst,
      time: SST_TIME,
      pane: "wash",
      attribution: "SST: NOAA CoastWatch / JPL MUR",
    }), 3);
  }

  function makeFallbackSst() {
    // coastwatch.noaa.gov does not host jplMURSST41 (HTTP 404 on 10 Nov 2026).
    // The live nearby product that did return tiles is the 5 km blended analysis.
    return withRetry(Wms4326("/proxy/sstfb/erddap/wms/noaacwBLENDEDsstDNDaily/request", {
      layers: "noaacwBLENDEDsstDNDaily:analysed_sst",
      format: "image/png",
      transparent: true,
      opacity: WASH_OPACITY[baseKind].sst,
      time: SST_FALLBACK_TIME,
      pane: "wash",
      attribution: "SST fallback: NOAA CoastWatch blended 5 km",
    }), 3);
  }

  function armSstFallback(layer) {
    let failed = 0;
    let switched = false;
    layer.on("tileerror", function (e) {
      const tile = e.tile;
      const n = Number(tile.dataset.retry || 0);
      if (n < 3) return;
      failed += 1;
      if (switched || failed < 3 || sstUsingFallback) return;
      switched = true;
      sstUsingFallback = true;
      showSstLoading(true, "Usual water-temp tiles failed — trying a nearby CoastWatch product…");
      if (map && map.hasLayer(layers.sst)) map.removeLayer(layers.sst);
      layers.sst = makeFallbackSst();
      bindSstLoading(layers.sst);
      if (activeMarine === "sst") {
        layers.sst.addTo(map);
        setLegend("sst");
      }
    });
  }

  function applyWashOpacity() {
    const mode = isFullscreen() ? "fullscreen" : baseKind;
    const op = WASH_OPACITY[mode] || WASH_OPACITY.light;
    if (layers.wind) layers.wind.setOpacity(op.wind);
    if (layers.waves) layers.waves.setOpacity(op.waves);
    if (layers.sst) layers.sst.setOpacity(op.sst);
  }

  function initMap() {
    if (map) return;
    $("map-placeholder").textContent = "Loading map…";
    $("map-status").textContent = "Initializing Leaflet…";

    const startZoom = window.innerWidth <= 700 ? 7 : ZOOM;
    map = L.map("map", {
      center: CENTER,
      zoom: startZoom,
      zoomControl: true,
      attributionControl: true,
    });

    map.createPane("basemap");
    map.getPane("basemap").style.zIndex = 200;
    map.createPane("wash");
    map.getPane("wash").style.zIndex = 350;
    map.createPane("radar");
    map.getPane("radar").style.zIndex = 355;
    map.createPane("labels");
    map.getPane("labels").style.zIndex = 360;

    layers.light = L.tileLayer("https://services.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}", {
      attribution: 'Tiles © <a href="https://www.esri.com/">Esri</a>',
      maxZoom: 16,
      pane: "basemap",
    });
    layers.darkBasemap = L.tileLayer("https://services.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}", {
      attribution: 'Tiles © <a href="https://www.esri.com/">Esri</a>',
      maxZoom: 16,
      pane: "basemap",
    });

    // ENC WMTS default028mm, zoomOffset -2. Used as a base map, not an overlay.
    layers.chart = L.tileLayer(
      "/proxy/enc/arcgis/rest/services/MarineChart_Services/NOAACharts/MapServer/WMTS/tile/1.0.0/MarineChart_Services_NOAACharts/default/default028mm/{z}/{y}/{x}.png",
      {
        zoomOffset: -2,
        minZoom: 2,
        maxNativeZoom: 18,
        opacity: 1,
        pane: "basemap",
        attribution: "Charts: NOAA ENC Chart Display Service",
      }
    );

    layers.wind = L.tileLayer.wms("/proxy/ndfd/ndfd.conus/wms", {
      layers: "ndfd.conus.windspd",
      format: "image/png",
      transparent: true,
      version: "1.3.0",
      opacity: WASH_OPACITY.light.wind,
      uppercase: true,
      VTIT: "1970-01-01T00:00",
      pane: "wash",
      attribution: "Wind: NWS NDFD",
    });

    // Wash and labels stay split: one WMS request for both drops the alpha channel
    // and paints land black.
    layers.waves = L.tileLayer.wms("/proxy/ndfd/ndfd.conus/wms", {
      layers: "ndfd.conus.waveheight",
      format: "image/png",
      transparent: true,
      version: "1.3.0",
      opacity: WASH_OPACITY.light.waves,
      uppercase: true,
      VTIT: "1970-01-01T00:00",
      pane: "wash",
      attribution: "Waves: NWS NDFD (feet)",
    });
    layers.waveLabels = L.tileLayer.wms("/proxy/ndfd/ndfd.conus/wms", {
      layers: "ndfd.conus.waveheight.points",
      format: "image/png",
      transparent: true,
      version: "1.3.0",
      uppercase: true,
      VTIT: "1970-01-01T00:00",
      pane: "labels",
    });

    sstUsingFallback = false;
    layers.sst = makePrimarySst();
    bindSstLoading(layers.sst);
    armSstFallback(layers.sst);

    ["wind", "waves", "waveLabels", "chart"].forEach(function (k) {
      if (layers[k]) withRetry(layers[k], 3);
    });

    streetBasemap().addTo(map);
    layers.wind.addTo(map);
    setLegend("wind");

    const buoy = L.circleMarker([35.026, -75.38], {
      radius: 7,
      color: "#0B2A3D",
      weight: 2,
      fillColor: "#5BA8A0",
      fillOpacity: 1,
    }).addTo(map);
    buoy.bindPopup(
      "<strong>NDBC 41025 — Diamond Shoals</strong><br>Source for the wave, wind, water, pressure, and surf cards."
    );

    const town = L.circleMarker([34.72, -76.73], {
      radius: 6,
      color: "#0B2A3D",
      weight: 2,
      fillColor: "#F3E6D0",
      fillOpacity: 1,
    }).addTo(map);
    town.bindPopup(
      "<strong>Morehead City</strong><br>NWS 7-day forecast point. Map is centered on central coastal NC, not on this pin."
    );

    $("map-placeholder").style.display = "none";
    $("map-shell").classList.remove("is-loading");
    $("map-status").textContent =
      "Map loaded. Starting view is fixed at 34.7°N, 76.7°W (zoom 7 on a phone, 8 on desktop). Use the chips on the side of the map to switch layers. Wind and waves sit on the street map or nautical chart. Water temperature and radar each take over the map. Tiles come through a local NOAA proxy because the wind, wave, and SST services do not send CORS headers.";
    setTimeout(() => map.invalidateSize(), 80);
  }

  function isFullscreen() {
    return activeMarine === "sst" || activeMarine === "radar";
  }

  function syncChips() {
    const fullscreen = isFullscreen();
    document.querySelectorAll(".map-chip[data-chip]").forEach(function (btn) {
      if (btn.classList.contains("is-soon") || btn.getAttribute("aria-disabled") === "true") {
        btn.setAttribute("aria-pressed", "false");
        return;
      }
      const chip = btn.getAttribute("data-chip");
      let on = false;
      if (chip === "chart") on = !fullscreen && baseKind === "chart";
      else if (chip === "wind" || chip === "waves" || chip === "sst" || chip === "radar") on = activeMarine === chip;
      btn.setAttribute("aria-pressed", on ? "true" : "false");
    });
    const shell = $("map-shell");
    if (shell) shell.classList.toggle("is-fullscreen-layer", fullscreen);
  }

  function showChipNote(text) {
    const el = $("chip-note");
    if (!el) return;
    el.textContent = text;
    el.hidden = false;
    if (showChipNote._timer) clearTimeout(showChipNote._timer);
    showChipNote._timer = setTimeout(function () { el.hidden = true; }, 2600);
  }

  const SOON_LABELS = {
    depth: "Depth contours",
    chlorophyll: "Chlorophyll",
    salinity: "Salinity",
    oxygen: "Dissolved oxygen",
    ais: "AIS heat zones",
  };

  function handleChip(chip) {
    if (SOON_LABELS[chip]) {
      showChipNote(SOON_LABELS[chip] + " coming soon");
      return;
    }
    if (chip === "chart") {
      if (isFullscreen()) {
        // Leave the takeover layer and show the nautical chart as the base.
        activeMarine = "wind";
        setMarine("wind");
        setBase("chart");
        return;
      }
      setBase(baseKind === "chart" ? "light" : "chart");
      return;
    }
    if (chip === "wind" || chip === "waves" || chip === "sst" || chip === "radar") {
      setMarine(chip);
    }
  }

  function setMarine(kind) {
    activeMarine = kind;
    syncChips();
    if (kind !== "sst") showSstLoading(false);
    if (kind !== "radar") setRadarVisible(false);
    if (!map) {
      if (kind === "radar") radar.requested = true;
      return;
    }
    ["wind", "waves", "waveLabels", "sst"].forEach((k) => {
      if (layers[k] && map.hasLayer(layers[k])) map.removeLayer(layers[k]);
    });
    applyBaseVisibility();
    if (kind === "radar") {
      setLegend("radar");
      ensureRadar().then(function () {
        if (activeMarine === "radar") {
          setLegend("radar");
          setRadarVisible(true);
        }
      });
      return;
    }
    if (layers[kind]) layers[kind].addTo(map);
    if (kind === "waves" && layers.waveLabels) layers.waveLabels.addTo(map);
    applyWashOpacity();
    setLegend(kind);
  }

  function setBase(kind) {
    baseKind = kind === "chart" ? "chart" : "light";
    syncChips();
    if (!map) return;
    applyBaseVisibility();
    applyWashOpacity();
  }

  function streetBasemap() {
    return isDark() && layers.darkBasemap ? layers.darkBasemap : layers.light;
  }

  function applyBaseVisibility() {
    if (!map) return;
    const fullscreen = isFullscreen();
    const showChart = !fullscreen && baseKind === "chart";
    const showStreet = !fullscreen && baseKind !== "chart";
    const showDarkUnderlay = fullscreen;
    if (layers.chart) {
      if (showChart && !map.hasLayer(layers.chart)) layers.chart.addTo(map);
      if (!showChart && map.hasLayer(layers.chart)) map.removeLayer(layers.chart);
    }
    if (layers.light) {
      if (showStreet && streetBasemap() === layers.light && !map.hasLayer(layers.light)) layers.light.addTo(map);
      if ((!showStreet || streetBasemap() !== layers.light) && map.hasLayer(layers.light)) map.removeLayer(layers.light);
    }
    if (layers.darkBasemap) {
      const wantDark = showDarkUnderlay || (showStreet && streetBasemap() === layers.darkBasemap);
      if (wantDark && !map.hasLayer(layers.darkBasemap)) layers.darkBasemap.addTo(map);
      if (!wantDark && map.hasLayer(layers.darkBasemap)) map.removeLayer(layers.darkBasemap);
    }
  }

  function applyBasemapForTheme() {
    if (!map) return;
    applyBaseVisibility();
  }

  function stopRadarTimer() {
    if (radar.timer) {
      clearTimeout(radar.timer);
      radar.timer = null;
    }
  }
  function radarShouldPlay() {
    return radar.playing && radar.ready && activeMarine === "radar" && radar.inView && !document.hidden;
  }
  function formatRadarClock(frame) {
    if (!frame) return "";
    let d = null;
    if (frame.time_epoch) d = new Date(Number(frame.time_epoch) * 1000);
    if ((!d || isNaN(d)) && frame.time && String(frame.time).length === 12) {
      const t = String(frame.time);
      d = new Date(Date.UTC(+t.slice(0, 4), +t.slice(4, 6) - 1, +t.slice(6, 8), +t.slice(8, 10), +t.slice(10, 12)));
    }
    if (!d || isNaN(d)) return String(frame.time || "");
    const label = new Intl.DateTimeFormat("en-US", {
      timeZone: "America/New_York",
      hour: "numeric",
      minute: "2-digit",
      month: "short",
      day: "numeric",
      timeZoneName: "short",
    }).format(d);
    if (frame.type === "nowcast") return "Forecast · " + label;
    return label;
  }
  function pickRadarFrames(meta, includeForecast) {
    const frames = (meta && meta.frames) || [];
    const observed = frames.filter(function (f) { return f.type !== "nowcast"; });
    const nowcast = frames.filter(function (f) { return f.type === "nowcast"; });
    if (includeForecast && nowcast.length) {
      const keepObs = Math.max(1, RADAR_MAX - Math.min(2, nowcast.length));
      const obs = observed.slice(-keepObs);
      const nc = nowcast.slice(0, RADAR_MAX - obs.length);
      return obs.concat(nc);
    }
    return observed.slice(-RADAR_MAX);
  }
  function showRadarFrame(i, instant) {
    if (!radar.layers.length) return;
    radar.index = ((i % radar.layers.length) + radar.layers.length) % radar.layers.length;
    radar.layers.forEach(function (item, idx) {
      const el = item.layer && item.layer.getContainer && item.layer.getContainer();
      const on = idx === radar.index;
      if (!el) {
        if (item.layer && item.layer.setOpacity) item.layer.setOpacity(on ? 0.8 : 0);
        return;
      }
      el.style.transition = instant || prefersReducedMotion() ? "none" : "opacity 0.45s ease";
      el.classList.toggle("is-on", on);
      el.classList.toggle("is-off", !on);
      el.classList.toggle("is-forecast", item.type === "nowcast");
    });
    const fr = radar.layers[radar.index];
    const clock = $("radar-clock");
    if (clock && fr) clock.textContent = formatRadarClock(fr);
  }
  function tickRadar() {
    stopRadarTimer();
    if (!radarShouldPlay() || radar.layers.length < 2) return;
    const isLast = radar.index === radar.layers.length - 1;
    radar.timer = setTimeout(function () {
      showRadarFrame(radar.index + 1, false);
      tickRadar();
    }, isLast ? RADAR_HOLD_MS : RADAR_FRAME_MS);
  }
  function pauseRadar() { stopRadarTimer(); }
  function resumeRadar() {
    if (radarShouldPlay()) tickRadar();
  }
  function makeRadarLayer(frame, meta) {
    const url = (meta.tile_url || "/api/radar/tile/{z}/{x}/{y}.png?t={time}").replace("{time}", frame.time);
    const layer = L.tileLayer(url, {
      opacity: 1,
      maxNativeZoom: meta.max_zoom || 11,
      maxZoom: 16,
      minZoom: meta.min_zoom || 0,
      pane: "radar",
      className: "leaflet-radar-frame is-off" + (frame.type === "nowcast" ? " is-forecast" : ""),
      attribution: "Radar: NOAA/NSSL MRMS; WeatherAPI.com",
    });
    withRetry(layer, 3);
    return layer;
  }
  function syncRadarLayers(frames, meta) {
    if (!map) return;
    const have = {};
    radar.layers.forEach(function (item) { have[item.time] = item; });
    const next = [];
    frames.forEach(function (f) {
      if (have[f.time]) {
        next.push(have[f.time]);
        delete have[f.time];
      } else {
        const layer = makeRadarLayer(f, meta);
        if (activeMarine === "radar") layer.addTo(map);
        next.push({ time: f.time, type: f.type, time_epoch: f.time_epoch, layer: layer });
      }
    });
    Object.keys(have).forEach(function (t) {
      const item = have[t];
      if (item.layer && map.hasLayer(item.layer)) map.removeLayer(item.layer);
    });
    radar.layers = next;
  }
  function setRadarVisible(on) {
    const note = $("radar-note");
    const controls = $("radar-controls");
    if (controls) controls.hidden = !(on && radar.ready && !radar.unavailable);
    if (note) {
      if (on && radar.unavailable) {
        note.hidden = false;
        note.textContent = radar.message || "Radar coming soon";
      } else {
        note.hidden = true;
      }
    }
    if (!map) return;
    radar.layers.forEach(function (item) {
      if (!item.layer) return;
      if (on && !radar.unavailable) {
        if (!map.hasLayer(item.layer)) item.layer.addTo(map);
      } else if (map.hasLayer(item.layer)) {
        map.removeLayer(item.layer);
      }
    });
    if (on && radar.ready && !radar.unavailable) {
      showRadarFrame(radar.index, true);
      resumeRadar();
    } else {
      pauseRadar();
    }
  }
  function loadRadar(force) {
    if (!radar.requested) return Promise.resolve();
    if (radar.loading) return Promise.resolve();
    const now = Date.now();
    if (!force && radar.meta && now - radar.lastFetch < RADAR_REFRESH_MS) return Promise.resolve();
    radar.loading = true;
    return fetch("/api/radar")
      .then(function (r) { return r.json().then(function (j) { return j; }); })
      .then(function (j) {
        radar.loading = false;
        radar.lastFetch = Date.now();
        j = j || {};
        if (!j.ok) {
          radar.unavailable = true;
          radar.ready = false;
          radar.message = j.message || "Radar coming soon";
          if (activeMarine === "radar") {
            setLegend("radar");
            setRadarVisible(true);
          }
          return;
        }
        radar.unavailable = false;
        radar.message = "";
        radar.meta = j;
        radar.ready = true;
        const frames = pickRadarFrames(j, radar.includeForecast);
        syncRadarLayers(frames, j);
        if (activeMarine === "radar") {
          setLegend("radar");
          setRadarVisible(true);
        }
      })
      .catch(function () {
        radar.loading = false;
        radar.unavailable = true;
        radar.ready = false;
        radar.message = "Radar is unavailable right now.";
        if (activeMarine === "radar") {
          setLegend("radar");
          setRadarVisible(true);
        }
      });
  }
  function ensureRadar() {
    radar.requested = true;
    return loadRadar(false);
  }
  function initRadarControls() {
    const forecast = $("radar-forecast");
    const play = $("radar-play");
    if (forecast) {
      forecast.addEventListener("change", function () {
        radar.includeForecast = !!forecast.checked;
        if (radar.meta) {
          syncRadarLayers(pickRadarFrames(radar.meta, radar.includeForecast), radar.meta);
          showRadarFrame(0, true);
          resumeRadar();
        }
      });
    }
    if (play) {
      play.addEventListener("click", function () {
        radar.playing = !radar.playing;
        play.setAttribute("aria-pressed", radar.playing ? "true" : "false");
        play.textContent = radar.playing ? "Pause" : "Play";
        if (radar.playing) resumeRadar();
        else pauseRadar();
      });
    }
    document.addEventListener("visibilitychange", function () {
      if (document.hidden) pauseRadar();
      else resumeRadar();
    });
    const section = $("map-section");
    if (section && "IntersectionObserver" in window) {
      const io = new IntersectionObserver(function (entries) {
        radar.inView = entries.some(function (e) { return e.isIntersecting; });
        if (radar.inView) resumeRadar();
        else pauseRadar();
      }, { threshold: 0.05 });
      io.observe(section);
    }
    setInterval(function () {
      if (radar.requested) loadRadar(false);
    }, 60 * 1000);
  }

  function activateMap() {
    $("map-shell").classList.add("is-active");
    if (map) setTimeout(() => map.invalidateSize(), 50);
  }
  function releaseMap() {
    $("map-shell").classList.remove("is-active");
  }

  function armLazyMap() {
    const section = $("map-section");
    const start = () => {
      if (leafletReady) {
        initMap();
        return;
      }
      leafletReady = true;
      $("map-status").textContent = "Map entered view — loading Leaflet and NOAA tiles…";
      loadCss("vendor/leaflet/leaflet.css")
        .then(() => loadScript("vendor/leaflet/leaflet.js"))
        .then(() => {
          initMap();
          setBase(baseKind);
          setMarine(activeMarine);
        })
        .catch((err) => {
          $("map-placeholder").textContent = "Could not load the map library.";
          $("map-status").textContent = String(err);
        });
    };

    if (!("IntersectionObserver" in window)) {
      start();
      return;
    }
    const io = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          io.disconnect();
          start();
        }
      },
      { root: null, rootMargin: "80px", threshold: 0.05 }
    );
    io.observe(section);
  }

  document.querySelectorAll(".map-chip[data-chip]").forEach((btn) => {
    btn.addEventListener("click", () => handleChip(btn.getAttribute("data-chip")));
  });
  $("map-cover").addEventListener("click", activateMap);
  $("map-cover").addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      activateMap();
    }
  });
  $("map-release").addEventListener("click", releaseMap);


  /* ---------- Tide search (NOAA CO-OPS predictions only) ---------- */
  const TIDE_STORE = "coastalBrief.tidePick";
  const TIDE_BOX = { south: 33.4, north: 36.95, west: -79.3, east: -75.3 };
  let tideCatalog = { stations: [], aliases: [] };
  let tideActive = null;
  let tideSuggestItems = [];
  let tideInputTimer = null;

  function normTide(s) {
    return String(s || "")
      .toLowerCase()
      .replace(/['’]/g, "")
      .replace(/[^a-z0-9]+/g, " ")
      .trim();
  }
  function tideTokens(s) {
    return normTide(s).split(" ").filter(Boolean);
  }
  function levenshtein(a, b) {
    if (a === b) return 0;
    if (!a.length) return b.length;
    if (!b.length) return a.length;
    const row = new Array(b.length + 1);
    for (let j = 0; j <= b.length; j++) row[j] = j;
    for (let i = 1; i <= a.length; i++) {
      let prev = i - 1;
      row[0] = i;
      for (let j = 1; j <= b.length; j++) {
        const tmp = row[j];
        const cost = a[i - 1] === b[j - 1] ? 0 : 1;
        row[j] = Math.min(row[j] + 1, row[j - 1] + 1, prev + cost);
        prev = tmp;
      }
    }
    return row[b.length];
  }
  function haversineMiles(lat1, lon1, lat2, lon2) {
    const R = 3958.8;
    const toR = Math.PI / 180;
    const dLat = (lat2 - lat1) * toR;
    const dLon = (lon2 - lon1) * toR;
    const x =
      Math.sin(dLat / 2) * Math.sin(dLat / 2) +
      Math.cos(lat1 * toR) * Math.cos(lat2 * toR) * Math.sin(dLon / 2) * Math.sin(dLon / 2);
    return 2 * R * Math.asin(Math.min(1, Math.sqrt(x)));
  }
  function ymdFromDate(d) {
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    return y + m + day;
  }
  function parseTideTime(t) {
    // NOAA lst_ldt: "2026-11-11 08:46" already in local Eastern time.
    const m = /^(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2})$/.exec(t || "");
    if (!m) return null;
    return new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]), Number(m[4]), Number(m[5]));
  }
  function formatTideClock(t) {
    const d = parseTideTime(t);
    if (!d) return t;
    let h = d.getHours();
    const min = String(d.getMinutes()).padStart(2, "0");
    const ap = h >= 12 ? "PM" : "AM";
    h = h % 12;
    if (h === 0) h = 12;
    return h + ":" + min + " " + ap;
  }
  function formatTideDay(t, withYear) {
    const d = parseTideTime(t) || (t ? new Date(t.slice(0, 4), t.slice(4, 6) - 1, t.slice(6, 8)) : null);
    if (!d || isNaN(d)) return t;
    const days = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
    const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
    return days[d.getDay()] + " " + months[d.getMonth()] + " " + d.getDate() + (withYear ? ", " + d.getFullYear() : "");
  }
  function formatFt(v) {
    const n = Number(v);
    if (!isFinite(n)) return "—";
    return n.toFixed(1) + " ft";
  }
  function todayLocal() {
    return new Date();
  }
  function addDays(d, n) {
    const x = new Date(d.getFullYear(), d.getMonth(), d.getDate());
    x.setDate(x.getDate() + n);
    return x;
  }

  function scoreStation(query, station, aliasNames) {
    const q = normTide(query);
    if (!q) return 0;
    const name = normTide(station.name);
    const qTok = tideTokens(query);
    const nTok = tideTokens(station.name);
    let best = 0;
    if (name === q) best = Math.max(best, 100);
    if (name.indexOf(q) === 0) best = Math.max(best, 92);
    if (q.length >= 3 && name.indexOf(q) >= 0) best = Math.max(best, 86);
    if (qTok.length && qTok.every((tok) => nTok.some((nt) => nt === tok || nt.indexOf(tok) === 0))) {
      best = Math.max(best, 84);
    }
    // Token typo: wrightsvile ~ wrightsville
    if (qTok.length) {
      let close = 0;
      qTok.forEach((tok) => {
        let d = Infinity;
        nTok.forEach((nt) => {
          d = Math.min(d, levenshtein(tok, nt));
        });
        const allow = tok.length <= 4 ? 1 : 2;
        if (d <= allow) close += 1;
      });
      if (close === qTok.length) best = Math.max(best, 78 - Math.min(8, levenshtein(q, name)));
    }
    const dName = levenshtein(q, name);
    if (q.length >= 5 && dName <= 2) best = Math.max(best, 80 - dName);
    (aliasNames || []).forEach((al) => {
      const a = normTide(al);
      if (a === q) best = Math.max(best, 100);
      if (a.indexOf(q) === 0 || (q.length >= 3 && a.indexOf(q) >= 0)) best = Math.max(best, 95);
      const da = levenshtein(q, a);
      const allow = a.length <= 6 ? 1 : 2;
      if (q.length >= 4 && da <= allow) best = Math.max(best, 90 - da);
      // typo on last token of a multi-word alias
      const aTok = a.split(" ");
      if (qTok.length === aTok.length && qTok.length) {
        let ok = true;
        let dist = 0;
        for (let i = 0; i < qTok.length; i++) {
          const di = levenshtein(qTok[i], aTok[i]);
          const allowT = qTok[i].length <= 4 ? 1 : 2;
          if (di > allowT) ok = false;
          dist += di;
        }
        if (ok) best = Math.max(best, 88 - dist);
      }
    });
    if (normTide(station.id) === q) best = Math.max(best, 100);
    return best;
  }

  function aliasMap() {
    const m = {};
    (tideCatalog.aliases || []).forEach((row) => {
      const id = row.stationId;
      if (!m[id]) m[id] = [];
      (row.names || []).forEach((n) => m[id].push(n));
    });
    return m;
  }

  function searchStations(query, limit) {
    limit = limit || 8;
    const q = normTide(query);
    if (q.length < 2) return [];
    const aliases = aliasMap();
    const scored = (tideCatalog.stations || []).map((st) => ({
      station: st,
      score: scoreStation(query, st, aliases[st.id] || []),
    }));
    scored.sort((a, b) => b.score - a.score || a.station.name.localeCompare(b.station.name));
    return scored.filter((r) => r.score >= 70).slice(0, limit);
  }

  function nearestStations(lat, lng, n) {
    n = n || 5;
    return (tideCatalog.stations || [])
      .map((st) => ({ station: st, miles: haversineMiles(lat, lng, st.lat, st.lng) }))
      .sort((a, b) => a.miles - b.miles)
      .slice(0, n);
  }

  function setTideStatus(text, isError) {
    const el = $("tide-status");
    el.textContent = text || "";
    el.classList.toggle("is-error", !!isError);
  }

  function hideSuggest() {
    const box = $("tide-suggest");
    box.hidden = true;
    box.innerHTML = "";
    $("tide-q").setAttribute("aria-expanded", "false");
    tideSuggestItems = [];
  }

  function showSuggest(items, query) {
    const box = $("tide-suggest");
    tideSuggestItems = items;
    box.innerHTML = "";
    if (!items.length) {
      hideSuggest();
      return;
    }
    items.forEach((item, i) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.setAttribute("role", "option");
      btn.setAttribute("aria-selected", i === 0 ? "true" : "false");
      const why = item.miles != null ? Math.round(item.miles * 10) / 10 + " mi away" : item.station.state || "";
      btn.innerHTML = '<span class="sn"></span><span class="ss"></span>';
      btn.querySelector(".sn").textContent = item.station.name;
      btn.querySelector(".ss").textContent = (item.station.id ? "#" + item.station.id : "") + (why ? " · " + why : "");
      btn.addEventListener("click", function () {
        hideSuggest();
        selectStation(item.station, query);
      });
      box.appendChild(btn);
    });
    box.hidden = false;
    $("tide-q").setAttribute("aria-expanded", "true");
  }

  function tideCurveSvg(curve, highsLows) {
    if (!curve || curve.length < 4) return "";
    const vals = curve.map((p) => Number(p.v)).filter((n) => isFinite(n));
    if (!vals.length) return "";
    let min = Math.min.apply(null, vals);
    let max = Math.max.apply(null, vals);
    if (max === min) {
      max += 0.5;
      min -= 0.5;
    }
    const pad = (max - min) * 0.12;
    min -= pad;
    max += pad;
    const w = 320;
    const h = 80;
    const left = 4;
    const right = 4;
    const top = 8;
    const bot = 8;
    const innerW = w - left - right;
    const innerH = h - top - bot;
    function xAt(i) {
      return left + (i / (curve.length - 1)) * innerW;
    }
    function yAt(v) {
      return top + ((max - v) / (max - min)) * innerH;
    }
    const pts = curve
      .map((p, i) => {
        const v = Number(p.v);
        return xAt(i).toFixed(1) + "," + yAt(v).toFixed(1);
      })
      .join(" ");
    // Baseline at 0 ft if in range
    let zero = "";
    if (min < 0 && max > 0) {
      const y0 = yAt(0);
      zero = '<line x1="' + left + '" y1="' + y0.toFixed(1) + '" x2="' + (w - right) + '" y2="' + y0.toFixed(1) + '" stroke="#d7c8ae" stroke-width="1" />';
    }
    let marks = "";
    (highsLows || []).forEach((ev) => {
      const evd = parseTideTime(ev.t);
      if (!evd) return;
      // Find nearest curve point
      let bestI = 0;
      let bestD = Infinity;
      curve.forEach((p, i) => {
        const pd = parseTideTime(p.t);
        if (!pd) return;
        const d = Math.abs(pd - evd);
        if (d < bestD) {
          bestD = d;
          bestI = i;
        }
      });
      const v = Number(ev.v);
      const cx = xAt(bestI);
      const cy = yAt(isFinite(v) ? v : Number(curve[bestI].v));
      const fill = ev.type === "H" ? "#0B2A3D" : "#5BA8A0";
      marks += '<circle cx="' + cx.toFixed(1) + '" cy="' + cy.toFixed(1) + '" r="3.2" fill="' + fill + '" />';
    });
    return (
      '<svg class="tide-curve" viewBox="0 0 ' +
      w +
      " " +
      h +
      '" role="img" aria-label="Predicted tide curve for this date, in feet, MLLW">' +
      zero +
      '<polyline fill="none" stroke="#0B2A3D" stroke-width="2" points="' +
      pts +
      '" />' +
      marks +
      "</svg>"
    );
  }

  function renderTideResults(payload, placeLabel) {
    const box = $("tide-results");
    const st = payload.station;
    const preds = payload.predictions || [];
    const curveDay = payload.curveDay;
    const todayPreds = preds.filter((p) => (p.t || "").slice(0, 10).replace(/-/g, "") === curveDay);
    const groups = {};
    preds.forEach((p) => {
      const key = (p.t || "").slice(0, 10);
      if (!groups[key]) groups[key] = [];
      groups[key].push(p);
    });
    const days = Object.keys(groups).sort();
    let html = '<div class="tide-head">';
    html += "<strong></strong>";
    html += '<div class="tide-source"></div>';
    if (st.subordinate) {
      html += '<p class="tide-note">This is a subordinate station. NOAA computes its tides from a nearby harmonic station' +
        (st.referenceId ? " (" + st.referenceId + ")" : "") + ".</p>";
    }
    if (payload.nearbyLabel) {
      html += '<p class="tide-note nearby-note"></p>';
    }
    html += "</div>";
    html += '<div class="tide-today-title"></div>';
    html += '<ul class="tide-events"></ul>';
    html += '<div class="tide-curve-wrap"></div>';
    html += '<div class="tide-days"></div>';
    box.innerHTML = html;
    box.querySelector(".tide-head strong").textContent = st.name + (st.state ? ", " + st.state : "");
    const link = document.createElement("a");
    link.href = payload.sourceUrl;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = "Source: NOAA Tides & Currents";
    box.querySelector(".tide-source").appendChild(link);
    const nearNote = box.querySelector(".tide-head .nearby-note");
    if (nearNote && payload.nearbyLabel) {
      nearNote.textContent = "Showing the nearest NOAA station for “" + payload.nearbyLabel + ".”";
    }
    const focusDate = parseTideTime(curveDay.slice(0, 4) + "-" + curveDay.slice(4, 6) + "-" + curveDay.slice(6, 8) + " 12:00");
    box.querySelector(".tide-today-title").textContent =
      (ymdFromDate(todayLocal()) === curveDay ? "Today — " : "For ") + formatTideDay(curveDay.slice(0, 4) + "-" + curveDay.slice(4, 6) + "-" + curveDay.slice(6, 8) + " 12:00", true);
    const ul = box.querySelector(".tide-events");
    if (!todayPreds.length) {
      const li = document.createElement("li");
      li.textContent = "NOAA has no high/low predictions for this date at this station.";
      ul.appendChild(li);
    } else {
      todayPreds.forEach((p) => {
        const li = document.createElement("li");
        const k = document.createElement("span");
        k.className = "k";
        k.textContent = p.type === "H" ? "High" : "Low";
        li.appendChild(k);
        li.appendChild(document.createTextNode(" " + formatTideClock(p.t) + " · " + formatFt(p.v)));
        ul.appendChild(li);
      });
    }
    box.querySelector(".tide-curve-wrap").innerHTML = tideCurveSvg(payload.curve || [], todayPreds);
    const daysBox = box.querySelector(".tide-days");
    days.forEach((key) => {
      const row = document.createElement("div");
      const keyYmd = key.replace(/-/g, "");
      row.className = "tide-day" + (keyYmd === curveDay ? " is-focus" : "");
      const ev = groups[key]
        .map((p) => (p.type === "H" ? "Hi " : "Lo ") + formatTideClock(p.t) + " " + formatFt(p.v))
        .join(" · ");
      row.innerHTML = '<div class="dd"></div><div class="ev"></div>';
      row.querySelector(".dd").textContent = formatTideDay(key + " 12:00");
      row.querySelector(".ev").textContent = ev;
      daysBox.appendChild(row);
    });
    box.hidden = false;
  }

  function dateWindow() {
    const picker = $("tide-date");
    const today = todayLocal();
    let focus = today;
    if (picker && picker.value) {
      const parts = picker.value.split("-");
      if (parts.length === 3) {
        const d = new Date(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2]));
        if (!isNaN(d)) focus = d;
      }
    }
    const max = addDays(today, 30);
    if (focus > max) focus = max;
    if (focus < today) focus = today;
    // Show today..+6 unless the plan date is later, in which case show the plan date as start of a 7-day window.
    let start = today;
    if (focus - today > 6 * 24 * 3600 * 1000) start = focus;
    const end = addDays(start, 6);
    return { start: start, end: end, focus: focus };
  }

  function loadTide(station, placeLabel, nearby) {
    tideActive = station;
    $("tide-q").value = placeLabel || station.name;
    const win = dateWindow();
    const begin = ymdFromDate(win.start);
    const end = ymdFromDate(win.end);
    const curve = ymdFromDate(win.focus);
    setTideStatus("Loading NOAA tide predictions…");
    $("tide-results").hidden = true;
    const url = "/api/tides?station=" + encodeURIComponent(station.id) + "&begin=" + begin + "&end=" + end + "&curve=" + curve;
    return fetch(url)
      .then((r) => r.json().then((j) => ({ okHttp: r.ok, j: j })))
      .then((res) => {
        if (!res.j || !res.j.ok) {
          setTideStatus((res.j && res.j.error) || "Could not load tide predictions from NOAA.", true);
          return;
        }
        setTideStatus("");
        if (nearby) res.j.nearbyLabel = placeLabel;
        renderTideResults(res.j, placeLabel);
        try {
          localStorage.setItem(
            TIDE_STORE,
            JSON.stringify({ id: station.id, name: station.name, placeLabel: placeLabel || station.name, nearby: !!nearby, savedAt: new Date().toISOString() })
          );
        } catch (e) {}
      })
      .catch(() => {
        setTideStatus("Could not reach NOAA Tides & Currents. Try again in a moment.", true);
      });
  }

  function selectStation(station, placeLabel, nearby) {
    if (tideInputTimer) clearTimeout(tideInputTimer);
    hideSuggest();
    loadTide(station, placeLabel, nearby);
  }

  function showNearbyFallback(place, lat, lng) {
    const near = nearestStations(lat, lng, 5);
    if (!near.length) {
      setTideStatus("No NOAA tide station is close to that place in this coastal list.", true);
      return;
    }
    const box = $("tide-results");
    const top = near[0];
    box.hidden = false;
    box.innerHTML = '<div class="tide-nearby"><p></p><button type="button" class="use-near"></button><ul class="tide-suggest" style="border:0;margin-top:8px"></ul></div>';
    box.querySelector("p").textContent =
      "No station is named “" + place + ".” The nearest NOAA tide station is " +
      top.station.name + " (" + (Math.round(top.miles * 10) / 10) + " miles). Predictions would come from that station.";
    const useBtn = box.querySelector(".use-near");
    useBtn.textContent = "Use " + top.station.name;
    useBtn.addEventListener("click", function () {
      selectStation(top.station, place, true);
    });
    const ul = box.querySelector("ul");
    ul.style.display = "block";
    near.forEach((item) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.innerHTML = '<span class="sn"></span><span class="ss"></span>';
      btn.querySelector(".sn").textContent = item.station.name;
      btn.querySelector(".ss").textContent = (Math.round(item.miles * 10) / 10) + " mi · #" + item.station.id;
      btn.addEventListener("click", function () {
        selectStation(item.station, place, true);
      });
      ul.appendChild(btn);
    });
    setTideStatus("");
  }

  function runTideSearch(query, fromSubmit) {
    const q = (query || "").trim();
    if (q.length < 2) {
      hideSuggest();
      if (fromSubmit) setTideStatus("Type a town, inlet, beach, ramp, or station name.", true);
      return;
    }
    const hits = searchStations(q, 8);
    if (hits.length) {
      if (fromSubmit && hits[0].score >= 84 && (hits.length === 1 || hits[0].score - hits[1].score >= 6)) {
        hideSuggest();
        selectStation(hits[0].station, q);
        return;
      }
      showSuggest(hits, q);
      if (fromSubmit) setTideStatus("Pick a station from the list.");
      return;
    }
    hideSuggest();
    if (!fromSubmit) return;
    // Name search missed — try geocoder, then nearest station.
    setTideStatus("No station matched that name. Looking up the place…");
    $("tide-results").hidden = true;
    fetch("/api/geocode?q=" + encodeURIComponent(q))
      .then((r) => r.json())
      .then((data) => {
        if (!data || !data.ok) {
          setTideStatus((data && data.error) || "No tide station matched that name. Check the spelling, or try a nearby town or inlet.", true);
          return;
        }
        if (!data.matches || !data.matches.length) {
          setTideStatus("No tide station or coastal place matched “" + q + ".” Check the spelling, or try a nearby town, inlet, or station name.", true);
          return;
        }
        const place = data.matches[0];
        showNearbyFallback(q, place.lat, place.lng);
      })
      .catch(() => {
        setTideStatus("No tide station matched that name, and the place-name lookup could not run. Try a station or town name from the list.", true);
      });
  }

  function initTidePickerLimits() {
    const picker = $("tide-date");
    const today = todayLocal();
    picker.min = ymdFromDate(today).replace(/(\d{4})(\d{2})(\d{2})/, "$1-$2-$3");
    picker.max = ymdFromDate(addDays(today, 30)).replace(/(\d{4})(\d{2})(\d{2})/, "$1-$2-$3");
    if (!picker.value) picker.value = picker.min;
  }

  function restoreTidePick() {
    try {
      const raw = localStorage.getItem(TIDE_STORE);
      if (!raw) return;
      const saved = JSON.parse(raw);
      const st = (tideCatalog.stations || []).find((s) => s.id === saved.id);
      if (st) {
        $("tide-q").value = saved.placeLabel || st.name;
        loadTide(st, saved.placeLabel || st.name, !!saved.nearby);
      }
    } catch (e) {}
  }

  function initTides() {
    initTidePickerLimits();
    const form = $("tide-form");
    const input = $("tide-q");
    input.addEventListener("input", function () {
      clearTimeout(tideInputTimer);
      tideInputTimer = setTimeout(function () {
        runTideSearch(input.value, false);
      }, 180);
    });
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      clearTimeout(tideInputTimer);
      runTideSearch(input.value, true);
    });
    $("tide-date").addEventListener("change", function () {
      if (tideActive) loadTide(tideActive, input.value || tideActive.name);
    });
    document.addEventListener("click", function (e) {
      if (!$("tide-search").contains(e.target)) hideSuggest();
    });
    fetch("/api/tide-stations")
      .then((r) => {
        if (!r.ok) throw new Error("stations");
        return r.json();
      })
      .then((data) => {
        tideCatalog = data || { stations: [], aliases: [] };
        restoreTidePick();
      })
      .catch(() => {
        setTideStatus("Could not load the NOAA tide station list.", true);
      });
  }

  initTheme();
  initRadarControls();
  initTides();

  loadSnapshot()
    .then(fillWeather)
    .catch((err) => {
      $("s-waves").textContent = "Could not load readings: " + err;
    })
    .then(() => loadAds().then(fillAds).catch(function () {
      $("ops-box").textContent = "Could not refresh the live ads flag from NWS alerts. The last saved ads.json will be used when the proxy is running.";
    }))
    .finally(armLazyMap);
})();
