/* Picker bind for pages that do not run dashboard.js (lake, catch-wall).
   The homepage is bound by dashboard.js. Dateline is server-rendered.
   The folio is CSS position:sticky — no scroll listener. */
(function (global) {
  "use strict";
  var STORE = "coastalBrief.region";
  function $(id) { return document.getElementById(id); }
  function currentId() {
    try {
      var q = new URLSearchParams(location.search).get("region");
      if (q) return q;
      var path = (location.pathname || "/").replace(/\/$/, "") || "/";
      if (path === "/lake") return "falls-lake";
      return localStorage.getItem(STORE) || "crystal-coast";
    } catch (e) {
      return "crystal-coast";
    }
  }
  function setRegion(id, rec) {
    rec = rec || (global.CoastalRegionNav && CoastalRegionNav.find && CoastalRegionNav.find(id)) || { id: id, name: id };
    var line = $("mast-region-line");
    if (line) {
      var bits = [];
      if (rec.name) bits.push(rec.name);
      if (rec.area) bits.push(rec.area);
      var text = bits.join(" · ");
      line.textContent = text;
      line.hidden = !text;
    }
    if (rec.waterType) {
      try { document.documentElement.setAttribute("data-water", rec.waterType); } catch (e) {}
    }
  }
  function bindPickerIfNeeded() {
    var root = document.querySelector("[data-region-nav]");
    var nav = global.CoastalRegionNav;
    if (!root || !nav || root._rnSet) return;
    if ($("region-select")) return;
    var cfg = (typeof nav.defaultCatalog === "function") ? nav.defaultCatalog() : { regions: [], freshwater: [] };
    var id = currentId();
    nav.bind(root, cfg, {
      currentId: id,
      onSelect: function (rid, info) {
        info = info || {};
        try { localStorage.setItem(STORE, rid); } catch (e) {}
        if (global.CoastalBriefLink) CoastalBriefLink.sync(rid);
        setRegion(rid, nav.find && nav.find(rid));
        var path = (location.pathname || "/").replace(/\/$/, "") || "/";
        if (info.waterType === "freshwater") {
          var href = info.href || ("/lake?region=" + encodeURIComponent(rid));
          if (path !== "/lake" || (location.search || "").indexOf(rid) === -1) location.href = href;
          return;
        }
        if (path === "/lake") location.href = "/?region=" + encodeURIComponent(rid);
      }
    });
    setRegion(id);
    if (global.CoastalBriefLink) CoastalBriefLink.sync(id);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", bindPickerIfNeeded);
  else bindPickerIfNeeded();
  global.CoastalIdentity = { setRegion: setRegion, currentId: currentId };
})(window);
