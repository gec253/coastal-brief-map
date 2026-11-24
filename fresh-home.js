/* Freshwater homepage fill: replace #conditions only, once official readings arrive.
   Never invent values. Ignore a response if the visitor has already changed region.
   NAV_V2 water switch (.cbw) sits above #conditions and must not be replaced.
   Retry reuses the single-flight refresh and never overwrites verified readings
   with unavailable or older unverified numbers (merge happens on the server). */
(function (root) {
  "use strict";

  var retrying = false;

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

  function setStatus(el, text) {
    if (!el) return;
    var status = el.querySelector(".cg-retry-status, .cg-load, [role='status']");
    if (status) status.textContent = text;
  }

  function markUnavailable(el, requested) {
    if (!el || liveRegion(el) !== requested) return;
    setStatus(el, "Readings unavailable");
    el.removeAttribute("data-fresh-pending");
    el.removeAttribute("aria-busy");
    if (!el.querySelector(".cg-retry")) {
      var box = document.createElement("div");
      box.className = "cg-retry-box";
      box.innerHTML = '<button type="button" class="cg-retry" id="fresh-retry">Retry readings</button>' +
        '<p class="cg-retry-status" role="status" aria-live="polite">Readings unavailable</p>';
      var foot = el.querySelector(".cg-foot");
      if (foot) el.insertBefore(box, foot);
      else el.appendChild(box);
      el.setAttribute("data-fresh-retry", "1");
    }
  }

  function request(rid, pub, retry, signal) {
    var url = "/api/fresh-home?region=" + encodeURIComponent(rid) + "&public=" + pub;
    if (retry) url += "&retry=1";
    return fetch(url, { signal: signal, credentials: "same-origin" }).then(function (r) { return r.json(); });
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
    request(rid, pub, false, ac.signal)
      .then(function (data) {
        var live = liveConditions();
        if (!shouldApply(rid, live, data)) return;
        applyHtml(live, data.html);
      })
      .catch(function () {
        markUnavailable(liveConditions(), rid);
      });
  }

  function retry(btn) {
    var el = liveConditions();
    var rid = liveRegion(el);
    if (!el || !rid || retrying) return;
    retrying = true;
    if (btn) btn.disabled = true;
    el.setAttribute("aria-busy", "true");
    setStatus(el, "Loading official readings…");
    var pub = el.getAttribute("data-fresh-public") === "1" ? "1" : "0";
    var ac = new AbortController();
    function abort() {
      try { ac.abort(); } catch (e) {}
    }
    window.addEventListener("pagehide", abort, { once: true });
    request(rid, pub, true, ac.signal)
      .then(function (data) {
        var live = liveConditions();
        if (!shouldApply(rid, live, data)) return;
        applyHtml(live, data.html);
        var next = liveConditions();
        if (next && data.retryAfterS) {
          setStatus(next, "Readings still unavailable. Try again in a moment.");
        }
      })
      .catch(function () {
        var live = liveConditions();
        if (!live || liveRegion(live) !== rid) return;
        setStatus(live, "Readings unavailable");
        live.removeAttribute("aria-busy");
        var b = live.querySelector(".cg-retry");
        if (b) b.disabled = false;
      })
      .then(function () { retrying = false; }, function () { retrying = false; });
  }

  root.FreshHome = { shouldApply: shouldApply, applyHtml: applyHtml, markUnavailable: markUnavailable, fill: fill, retry: retry };

  if (typeof document !== "undefined") {
    document.addEventListener("click", function (e) {
      var btn = e.target && e.target.closest && e.target.closest(".cg-retry");
      if (!btn) return;
      e.preventDefault();
      retry(btn);
    });
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", function () { fill(liveConditions()); });
    } else {
      fill(liveConditions());
    }
  }
})(typeof window !== "undefined" ? window : this);
