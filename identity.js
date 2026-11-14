/* Newspaper masthead helpers: ET dateline, region line from the region
   list, sticky folio bar (IntersectionObserver, no in-flow height change),
   and a picker bind on pages that do not run dashboard.js. */
(function (global) {
  "use strict";
  var STORE = "coastalBrief.region";

  function $(id) { return document.getElementById(id); }

  function fillDateline() {
    var el = $("mast-dateline");
    if (!el) return;
    try {
      var fmt = new Intl.DateTimeFormat("en-US", {
        weekday: "long", month: "long", day: "numeric", year: "numeric",
        timeZone: "America/New_York"
      });
      var label = fmt.format(new Date()) + " · Eastern Time";
      var t = el.querySelector("time") || el;
      t.textContent = label;
      if (t.tagName === "TIME") {
        var parts = new Intl.DateTimeFormat("en-CA", { timeZone: "America/New_York", year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date());
        t.setAttribute("datetime", parts);
      }
    } catch (e) {}
  }

  function recordFor(id) {
    var nav = global.CoastalRegionNav;
    if (nav && typeof nav.find === "function") return nav.find(id);
    return null;
  }

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
    rec = rec || recordFor(id) || { id: id, name: id };
    var line = $("mast-region-line");
    if (line) {
      var bits = [];
      if (rec.name) bits.push(rec.name);
      if (rec.area) bits.push(rec.area);
      var text = bits.join(" · ");
      line.textContent = text;
      line.hidden = !text;
    }
    if (document.documentElement && rec.waterType) {
      document.documentElement.setAttribute("data-water", rec.waterType);
    }
  }

  function watchSticky() {
    var bar = $("compact-bar");
    var sen = $("sticky-sentinel");
    if (!bar || !sen || !("IntersectionObserver" in global)) return;
    var io = new IntersectionObserver(function (entries) {
      var e = entries[0];
      bar.classList.toggle("is-stuck", !!(e && !e.isIntersecting));
    }, { root: null, threshold: 0 });
    io.observe(sen);
  }

  function bindPickerIfNeeded() {
    var root = document.querySelector("[data-region-nav]");
    var nav = global.CoastalRegionNav;
    if (!root || !nav || root._rnSet) return;
    if ($("region-select")) return; // dashboard.js binds the homepage picker
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
        if (path === "/lake") {
          location.href = "/?region=" + encodeURIComponent(rid);
        }
      }
    });
    setRegion(id);
    if (global.CoastalBriefLink) CoastalBriefLink.sync(id);
  }

  fillDateline();
  watchSticky();
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bindPickerIfNeeded);
  } else {
    bindPickerIfNeeded();
  }

  global.CoastalIdentity = { setRegion: setRegion, currentId: currentId };
})(window);
