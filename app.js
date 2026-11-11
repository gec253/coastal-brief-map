/* Coastal Brief NOAA map test. No geolocation. No market data. */
(function () {
  const SST_TIME = "2026-11-09T09:00:00Z";
  const SST_FALLBACK_TIME = "2026-11-08T12:00:00Z";
  const CENTER = [34.7, -76.7];
  const ZOOM = 8;
  const WASH_OPACITY = { light: { wind: 0.72, waves: 0.85, sst: 0.85 }, chart: { wind: 0.55, waves: 0.58, sst: 0.6 } };

  const $ = (id) => document.getElementById(id);
  let map = null;
  let layers = {};
  let activeMarine = "wind";
  let baseKind = "light";
  let leafletReady = false;
  let sstUsingFallback = false;
  let sstLoadTimer = null;

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

    const tide = data.tides.nextTide;
    $("v-tide").textContent = (tide.type === "H" ? "Hi " : "Lo ") + tide.timeET.replace(" ET", "").replace(" PM", "p").replace(" AM", "a");
    $("s-tide").textContent = tide.heightFt.toFixed(1) + " ft · " + data.tides.stationName + " · prediction";

    $("v-surf").textContent =
      b.surf.swellPeriodS + " s · " + b.surf.swellDir + " · " + b.surf.swellHeightFt.toFixed(1) + " ft";
    $("s-surf").textContent =
      b.surf.periodRead + ". " + b.surf.windVsBeach + ". " +
      b.surf.note + " " + b.name + " (" + b.id + "), " + b.surf.timeET +
      ". Swell height converted from " + b.surf.swellHeightM.toFixed(1) + " m.";

    $("freshness-badge").textContent = "Last updated " + b.surf.timeET;
    $("freshness-badge").classList.remove("amber");

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

  function setLegend(kind) {
    $("legend-box").innerHTML = legendHtml(kind);
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
    const op = WASH_OPACITY[baseKind];
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
    map.createPane("labels");
    map.getPane("labels").style.zIndex = 360;

    layers.light = L.tileLayer("https://services.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}", {
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

    layers.light.addTo(map);
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
    $("map-status").textContent =
      "Map loaded. Starting view is fixed at 34.7°N, 76.7°W (zoom 7 on a phone, 8 on desktop). One marine layer at a time. Choose Light map or Nautical chart as the base. Tiles come through a local NOAA proxy because the wind, wave, and SST services do not send CORS headers.";
    setTimeout(() => map.invalidateSize(), 80);
  }

  function setMarine(kind) {
    activeMarine = kind;
    document.querySelectorAll(".switcher button[data-layer]").forEach((btn) => {
      btn.setAttribute("aria-pressed", btn.getAttribute("data-layer") === kind ? "true" : "false");
    });
    if (kind !== "sst") showSstLoading(false);
    if (!map) return;
    ["wind", "waves", "waveLabels", "sst"].forEach((k) => {
      if (layers[k] && map.hasLayer(layers[k])) map.removeLayer(layers[k]);
    });
    if (layers[kind]) layers[kind].addTo(map);
    if (kind === "waves" && layers.waveLabels) layers.waveLabels.addTo(map);
    applyWashOpacity();
    setLegend(kind);
  }

  function setBase(kind) {
    baseKind = kind;
    document.querySelectorAll(".switcher button[data-base]").forEach((btn) => {
      btn.setAttribute("aria-pressed", btn.getAttribute("data-base") === kind ? "true" : "false");
    });
    if (!map) return;
    if (kind === "chart") {
      if (map.hasLayer(layers.light)) map.removeLayer(layers.light);
      if (layers.chart && !map.hasLayer(layers.chart)) layers.chart.addTo(map);
    } else {
      if (layers.chart && map.hasLayer(layers.chart)) map.removeLayer(layers.chart);
      if (layers.light && !map.hasLayer(layers.light)) layers.light.addTo(map);
    }
    applyWashOpacity();
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
          setMarine(activeMarine);
          const pressed = document.querySelector(".switcher button[data-base][aria-pressed='true']");
          setBase(pressed ? pressed.getAttribute("data-base") : "light");
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

  document.querySelectorAll(".switcher button[data-layer]").forEach((btn) => {
    btn.addEventListener("click", () => setMarine(btn.getAttribute("data-layer")));
  });
  document.querySelectorAll(".switcher button[data-base]").forEach((btn) => {
    btn.addEventListener("click", () => setBase(btn.getAttribute("data-base")));
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
