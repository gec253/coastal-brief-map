(function () {
  var KEY = "cb-wave-intro-seen";
  var DURATION = 1800;
  var REDUCE_MS = 200;
  var overlay = document.getElementById("wave-intro");
  var skip = document.getElementById("wi-skip");
  var replay = document.getElementById("wi-replay");
  var sound = document.getElementById("wi-sound");
  var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var params = new URLSearchParams(location.search || "");
  var forcePlay = params.get("play") === "1";
  var forceSeen = params.get("seen") === "1";
  var seek = params.get("seek");
  var timer = 0;

  function markSeen() {
    try { sessionStorage.setItem(KEY, "1"); } catch (e) {}
  }

  function clearSeen() {
    try { sessionStorage.removeItem(KEY); } catch (e) {}
  }

  function alreadySeen() {
    if (forcePlay) return false;
    if (forceSeen) return true;
    try { return sessionStorage.getItem(KEY) === "1"; } catch (e) { return false; }
  }

  function hide() {
    if (!overlay) return;
    overlay.classList.add("is-done");
    overlay.setAttribute("hidden", "");
    overlay.setAttribute("aria-hidden", "true");
    overlay.style.pointerEvents = "none";
    document.documentElement.classList.add("intro-seen");
    document.documentElement.classList.remove("intro-play", "intro-reduce");
    if (skip && document.activeElement === skip) skip.blur();
  }

  function finish() {
    markSeen();
    hide();
  }

  function play() {
    if (!overlay) return;
    document.documentElement.classList.remove("intro-seen");
    document.documentElement.classList.add("intro-play");
    if (reduce) document.documentElement.classList.add("intro-reduce");
    overlay.classList.remove("is-done");
    overlay.removeAttribute("hidden");
    overlay.setAttribute("aria-hidden", "false");
    overlay.style.pointerEvents = "auto";
    if (seek !== null && seek !== "") {
      var ms = Math.max(0, parseInt(seek, 10) || 0);
      document.documentElement.setAttribute("data-intro-seek", "");
      document.documentElement.style.setProperty("--intro-ms", String(ms));
      return;
    }
    if (skip) skip.focus();
    var wait = reduce ? REDUCE_MS : DURATION;
    timer = window.setTimeout(finish, wait);
  }

  function skipNow() {
    if (timer) window.clearTimeout(timer);
    document.documentElement.removeAttribute("data-intro-seek");
    finish();
  }

  function replayIntro() {
    if (timer) window.clearTimeout(timer);
    clearSeen();
    document.documentElement.removeAttribute("data-intro-seek");
    document.documentElement.style.removeProperty("--intro-ms");
    seek = "";
    // Retrigger CSS animations.
    if (overlay) {
      overlay.classList.add("is-done");
      void overlay.offsetWidth;
    }
    play();
  }

  if (skip) skip.addEventListener("click", skipNow);
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && overlay && !overlay.hasAttribute("hidden") && !overlay.classList.contains("is-done")) {
      skipNow();
    }
  });
  if (replay) replay.addEventListener("click", replayIntro);

  // Sound hook: remains hidden and inert until a verified public-domain clip is added.
  // Load media only on click, muted by default, never autoplay.
  if (sound) {
    sound.addEventListener("click", function () {
      if (!sound.dataset.src) return;
      sound.hidden = false;
    });
  }

  if (alreadySeen() && !forcePlay) {
    hide();
    markSeen();
    return;
  }
  play();
})();
