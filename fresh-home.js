/* Freshwater homepage fill: replace #conditions only, once official readings arrive.
   Never invent values. Ignore a response if the visitor has already changed region.
   NAV_V2 water switch (.cbw) sits above #conditions and must not be replaced.
   Retry reuses the single-flight refresh and never overwrites verified readings
   with unavailable or older unverified numbers (merge happens on the server).
   The visitor-facing wait does not cancel an in-flight USGS request: keep
   polling /api/fresh-home until the background single-flight lands or the
   window expires. */
(function (root) {
  "use strict";

  var retrying = false;
  var POLL_MS = 2000;
  var POLL_MAX_MS = 60000;

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

  function request(rid, pub, retry, signal, poll) {
    var url = "/api/fresh-home?region=" + encodeURIComponent(rid) + "&public=" + pub;
    if (retry) url += "&retry=1";
    if (poll) url += "&poll=1";
    return fetch(url, { signal: signal, credentials: "same-origin" }).then(function (r) { return r.json(); });
  }

  function startPoll(rid, pub, firstRetry) {
    var ac = new AbortController();
    var started = Date.now();
    var timer = null;
    var stopped = false;
    function abort() {
      stopped = true;
      if (timer) clearTimeout(timer);
      try { ac.abort(); } catch (e) {}
    }
    window.addEventListener("pagehide", abort, { once: true });
    function tick(isPoll, useRetry) {
      if (stopped) return;
      request(rid, pub, useRetry, ac.signal, isPoll)
        .then(function (data) {
          if (stopped) return;
          var live = liveConditions();
          if (liveRegion(live) && liveRegion(live) !== rid) return;
          if (shouldApply(rid, live, data)) {
            applyHtml(live, data.html);
          }
          var next = liveConditions();
          if (next && data && data.retryAfterS) {
            setStatus(next, "Readings still unavailable. Try again in a moment.");
          }
          var done = data && data.complete;
          var elapsed = Date.now() - started;
          if (!done && elapsed < POLL_MAX_MS) {
            timer = setTimeout(function () { tick(true, false); }, POLL_MS);
          } else if (!done) {
            if (next && liveRegion(next) === rid && next.getAttribute("data-fresh-pending") === "1") {
              markUnavailable(next, rid);
            }
          }
        })
        .catch(function (err) {
          if (stopped) return;
          if (err && err.name === "AbortError") return;
          var elapsed = Date.now() - started;
          if (elapsed < POLL_MAX_MS) {
            timer = setTimeout(function () { tick(true, false); }, POLL_MS);
          } else {
            markUnavailable(liveConditions(), rid);
          }
        })
        .then(function () {
          if (useRetry) retrying = false;
        }, function () {
          if (useRetry) retrying = false;
        });
    }
    tick(false, firstRetry);
  }

  function fill(el) {
    if (!el || el.getAttribute("data-fresh-pending") !== "1") return;
    var rid = liveRegion(el);
    if (!rid) return;
    var pub = el.getAttribute("data-fresh-public") === "1" ? "1" : "0";
    startPoll(rid, pub, false);
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
    startPoll(rid, pub, true);
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
