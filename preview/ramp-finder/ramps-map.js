/* Private Ramp Finder map prototype (Ed t421u).
   Vendored Leaflet only. Pins are drawn solely from official inventory coordinates.
   No third-party tile keys, no Esri, no OSM Foundation default tiles. */
(function () {
  "use strict";

  var VENDOR_CSS = "/vendor/leaflet/leaflet.css";
  var VENDOR_JS = "/vendor/leaflet/leaflet.js";
  var TOPO_URL = "https://basemap.nationalmap.gov/arcgis/rest/services/USGSTopo/MapServer/tile/{z}/{y}/{x}";
  var AERIAL_URL = "https://basemap.nationalmap.gov/arcgis/rest/services/USGSImageryOnly/MapServer/tile/{z}/{y}/{x}";
  var USGS_ATTR = "Map services and data available from U.S. Geological Survey, National Geospatial Program";
  var MAX_ZOOM = 16;

  var dataNode = document.getElementById("rf-map-data");
  var stage = document.getElementById("rf-map");
  if (!dataNode || !stage) return;

  var payload;
  try {
    payload = JSON.parse(dataNode.textContent);
  } catch (err) {
    stage.innerHTML = "<p class=\"rf-map-placeholder\">The map data could not be read.</p>";
    return;
  }

  var records = (payload && payload.records) || [];
  var markersById = {};
  var map, topoLayer, aerialLayer, markerLayer;
  var selectedId = null;
  var reduceMotion = false;
  try {
    reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  } catch (e) {}

  function loadCss(href) {
    return new Promise(function (resolve, reject) {
      if (document.querySelector('link[href="' + href + '"]')) return resolve();
      var link = document.createElement("link");
      link.rel = "stylesheet";
      link.href = href;
      link.onload = function () { resolve(); };
      link.onerror = function () { reject(new Error("css")); };
      document.head.appendChild(link);
    });
  }

  function loadScript(src) {
    return new Promise(function (resolve, reject) {
      if (window.L) return resolve(window.L);
      var s = document.createElement("script");
      s.src = src;
      s.async = true;
      s.onload = function () { resolve(window.L); };
      s.onerror = function () { reject(new Error("js")); };
      document.head.appendChild(s);
    });
  }

  function loadLeaflet() {
    if (window.L) return Promise.resolve(window.L);
    return loadCss(VENDOR_CSS).then(function () { return loadScript(VENDOR_JS); });
  }

  function isPin(rec) {
    return !!(rec && rec.has_pin && typeof rec.lat === "number" && typeof rec.lon === "number"
      && isFinite(rec.lat) && isFinite(rec.lon));
  }

  function markerKind(rec) {
    if (rec.dated_notice) return "dated";
    if (rec.standing_caution) return "caution";
    if (rec.listing_class === "limited") return "limited";
    if (rec.listing_class === "needs_review") return "review";
    return "general";
  }

  function visibleFromDom() {
    var items = document.querySelectorAll(".rf-sync-item[data-ramp-id]");
    var ids = {};
    Array.prototype.forEach.call(items, function (el) { ids[el.getAttribute("data-ramp-id")] = true; });
    return records.filter(function (rec) { return ids[rec.id]; });
  }

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  function popupHtml(rec) {
    var bits = [];
    bits.push('<div class="rf-popup">');
    bits.push("<h3>" + esc(rec.name) + "</h3>");
    if (rec.waterbody) bits.push('<p class="rf-popup-water">' + esc(rec.waterbody) + "</p>");
    if (rec.dated_notice) {
      bits.push('<p class="rf-popup-notice"><strong>Current dated notice.</strong> ' + esc(rec.dated_notice) + "</p>");
    }
    if (rec.standing_caution) {
      bits.push('<p class="rf-popup-caution"><strong>Standing caution.</strong> ' + esc(rec.standing_caution) + "</p>");
    }
    if (rec.restriction) {
      bits.push("<p><strong>Restrictions.</strong> " + esc(rec.restriction) + "</p>");
    }
    if (rec.flags && rec.flags.fee_conflict) {
      bits.push("<p>Official sources list more than one fee. See the detail page for both figures and sources.</p>");
    }
    if (rec.flags && rec.flags.hours_uncertain) {
      bits.push("<p>Official sources disagree about hours. See the detail page for both descriptions.</p>");
    }
    bits.push('<p class="rf-popup-disclaimer">Not a live open/closed confirmation.</p>');
    bits.push('<div class="rf-popup-actions">');
    if (rec.detail_url) bits.push('<a class="btn" href="' + esc(rec.detail_url) + '">Ramp details</a>');
    if (rec.apple_url) bits.push('<a class="btn" href="' + esc(rec.apple_url) + '" rel="noopener noreferrer">Apple Maps directions</a>');
    if (rec.google_url) bits.push('<a class="btn" href="' + esc(rec.google_url) + '" rel="noopener noreferrer" target="_blank">Google Maps directions</a>');
    bits.push("</div></div>");
    return bits.join("");
  }

  function makeIcon(rec, selected) {
    var kind = markerKind(rec);
    var cls = "rf-pin rf-pin-" + kind + (selected ? " is-selected" : "");
    return window.L.divIcon({
      className: "rf-pin-wrap",
      html: '<button type="button" class="' + cls + '" aria-label="' + esc(rec.name) + '"><span></span></button>',
      iconSize: [44, 44],
      iconAnchor: [22, 38],
      popupAnchor: [0, -30]
    });
  }

  function setListSelection(id, opts) {
    Array.prototype.forEach.call(document.querySelectorAll(".rf-sync-item"), function (el) {
      var on = el.getAttribute("data-ramp-id") === id;
      el.classList.toggle("is-selected", on);
      var btn = el.querySelector(".rf-sync-select");
      if (btn) btn.setAttribute("aria-pressed", on ? "true" : "false");
    });
    if (opts && opts.scrollList) {
      var row = document.querySelector('.rf-sync-item[data-ramp-id="' + id + '"]');
      if (row && row.scrollIntoView) {
        row.scrollIntoView({ block: "nearest", behavior: reduceMotion ? "auto" : "smooth" });
      }
    }
  }

  function announce(text) {
    var status = document.getElementById("rf-map-status");
    if (status) status.textContent = text;
  }

  function selectRecord(rec, fromMap) {
    selectedId = rec ? rec.id : null;
    Object.keys(markersById).forEach(function (id) {
      var rec2 = records.find(function (r) { return r.id === id; });
      if (rec2) markersById[id].setIcon(makeIcon(rec2, id === selectedId));
    });
    if (!rec) {
      setListSelection("");
      return;
    }
    setListSelection(rec.id, { scrollList: !!fromMap });
    var marker = markersById[rec.id];
    if (marker) {
      if (!fromMap) {
        var stage = document.getElementById("rf-map");
        if (stage && stage.scrollIntoView) {
          stage.scrollIntoView({ block: "nearest", behavior: reduceMotion ? "auto" : "smooth" });
        }
        var z = Math.max(map.getZoom(), 12);
        if (reduceMotion) map.setView(marker.getLatLng(), z, { animate: false });
        else map.flyTo(marker.getLatLng(), z, { duration: 0.6 });
      }
      marker.openPopup();
    } else {
      if (map) map.closePopup();
      announce(rec.name + " has no map pin — address directions. Official coordinates are not on file.");
    }
  }

  function addMarkers() {
    if (markerLayer) markerLayer.clearLayers();
    markersById = {};
    var visible = visibleFromDom();
    var pinRecs = visible.filter(isPin);
    pinRecs.forEach(function (rec) {
      var marker = window.L.marker([rec.lat, rec.lon], {
        icon: makeIcon(rec, rec.id === selectedId),
        title: rec.name,
        keyboard: true,
        riseOnHover: true
      });
      marker.bindPopup(popupHtml(rec), { maxWidth: 300, className: "rf-leaflet-popup", autoPanPadding: [20, 72] });
      marker.on("click", function () { selectRecord(rec, true); });
      marker.addTo(markerLayer);
      markersById[rec.id] = marker;
    });
    return pinRecs;
  }

  function fitVisible(pinRecs) {
    if (!pinRecs.length) {
      // No official pins in this view — do not invent a region center.
      return;
    }
    if (pinRecs.length === 1) {
      map.setView([pinRecs[0].lat, pinRecs[0].lon], 12, { animate: !reduceMotion });
      return;
    }
    var bounds = window.L.latLngBounds(pinRecs.map(function (r) { return [r.lat, r.lon]; }));
    map.fitBounds(bounds, { padding: [28, 28], maxZoom: pinRecs.length < 6 ? 12 : 10, animate: !reduceMotion });
  }

  function initMap(L) {
    var placeholder = stage.querySelector(".rf-map-placeholder");
    if (placeholder) placeholder.remove();

    map = L.map(stage, {
      zoomControl: false,
      attributionControl: true,
      scrollWheelZoom: true,
      tapHold: false
    });
    L.control.zoom({ position: "topright" }).addTo(map);
    map.attributionControl.setPrefix('<a href="https://leafletjs.com" title="A JavaScript library for interactive maps">Leaflet</a>');

    topoLayer = L.tileLayer(TOPO_URL, {
      attribution: USGS_ATTR,
      maxZoom: MAX_ZOOM,
      maxNativeZoom: MAX_ZOOM,
      tileSize: 256,
      updateWhenIdle: true
    });
    aerialLayer = L.tileLayer(AERIAL_URL, {
      attribution: USGS_ATTR,
      maxZoom: MAX_ZOOM,
      maxNativeZoom: MAX_ZOOM,
      tileSize: 256,
      updateWhenIdle: true
    });
    topoLayer.addTo(map);
    markerLayer = L.layerGroup().addTo(map);

    var pins = addMarkers();
    fitVisible(pins);
    map.whenReady(function () { map.invalidateSize(); });
    requestAnimationFrame(function () { map.invalidateSize(); });

    var topoBtn = document.getElementById("rf-basemap-topo");
    var aerialBtn = document.getElementById("rf-basemap-aerial");
    function setBasemap(which) {
      var aerial = which === "aerial";
      if (aerial) {
        if (map.hasLayer(topoLayer)) map.removeLayer(topoLayer);
        if (!map.hasLayer(aerialLayer)) aerialLayer.addTo(map);
        markerLayer.addTo(map);
      } else {
        if (map.hasLayer(aerialLayer)) map.removeLayer(aerialLayer);
        if (!map.hasLayer(topoLayer)) topoLayer.addTo(map);
        markerLayer.addTo(map);
      }
      if (topoBtn) {
        topoBtn.classList.toggle("is-active", !aerial);
        topoBtn.setAttribute("aria-pressed", aerial ? "false" : "true");
      }
      if (aerialBtn) {
        aerialBtn.classList.toggle("is-active", aerial);
        aerialBtn.setAttribute("aria-pressed", aerial ? "true" : "false");
      }
    }
    if (topoBtn) topoBtn.addEventListener("click", function () { setBasemap("topo"); });
    if (aerialBtn) aerialBtn.addEventListener("click", function () { setBasemap("aerial"); });
  }

  function onListClick(ev) {
    var btn = ev.target.closest && ev.target.closest(".rf-sync-select");
    if (!btn) return;
    ev.preventDefault();
    var id = btn.getAttribute("data-ramp-id");
    var rec = records.find(function (r) { return r.id === id; });
    if (rec) selectRecord(rec, false);
  }

  document.addEventListener("click", onListClick);

  function boot() {
    loadLeaflet().then(initMap).catch(function () {
      stage.innerHTML = "<p class=\"rf-map-placeholder\">The map library could not be loaded. The list below still works.</p>";
    });
  }

  // Lazy-load after first paint so the reserved map frame does not shift.
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      requestAnimationFrame(boot);
    });
  } else {
    requestAnimationFrame(boot);
  }
})();
