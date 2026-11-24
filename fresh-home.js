/* Freshwater homepage fill: replace #conditions only, once official readings arrive.
   Never invent values. Ignore a response if the visitor has already changed region.
   NAV_V2 water switch (.cbw) sits above #conditions and must not be replaced. */
(function (root) {
  "use strict";

  function liveConditions() {
    return document.getElementById("conditions");
  }

  function liveRegion(el) {
    if (!el) return "";
    return el.getAttribute("data-fresh-region") || "";
  }

  function shouldApply(requested, el, data) {
    if (!el || !requested) return false;
    if (liveRegion(el) && liveRegion(el) !== requested) return false;
    if (data && data.region && data.region.id && data.region.id !== requested) return false;
    return !!(data && data.html);
  }

  function applyHtml(el, html) {
    var wrap = document.createElement("div");
    wrap.innerHTML = html;
    var next = wrap.querySelector("#conditions");
    if (!next || !el || !el.parentNode) return false;
    el.replaceWith(next);
    return true;
  }

  function markUnavailable(el, requested) {
    if (!el || liveRegion(el) !== requested) return;
    var status = el.querySelector(".cg-load, [role='status']");
    if (status) status.textContent = "Readings unavailable";
    el.removeAttribute("data-fresh-pending");
    el.removeAttribute("aria-busy");
  }

  function fill(el) {
    if (!el || el.getAttribute("data-fresh-pending") !== "1") return;
    var rid = liveRegion(el);
    if (!rid) return;
    var pub = el.getAttribute("data-fresh-public") === "1" ? "1" : "0";
    var ac = new AbortController();
    function abort() {
      try { ac.abort(); } catch (e) {}
    }
    window.addEventListener("pagehide", abort, { once: true });
    fetch("/api/fresh-home?region=" + encodeURIComponent(rid) + "&public=" + pub, { signal: ac.signal, credentials: "same-origin" })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        var live = liveConditions();
        if (!shouldApply(rid, live, data)) return;
        applyHtml(live, data.html);
      })
      .catch(function () {
        markUnavailable(liveConditions(), rid);
      });
  }

  root.FreshHome = { shouldApply: shouldApply, applyHtml: applyHtml, markUnavailable: markUnavailable, fill: fill };

  if (typeof document !== "undefined") {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", function () { fill(liveConditions()); });
    } else {
      fill(liveConditions());
    }
  }
})(typeof window !== "undefined" ? window : this);
