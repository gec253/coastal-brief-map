(function () {
  var KEY = "cb-wave-intro-seen";
  var DURATION = 1900;
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


  function mapMastHole() {
    var hole = document.getElementById("wi-mast-hole");
    if (!hole) return;
    var name = document.querySelector(".mast-nameplate") || document.querySelector("header.site h1");
    var motto = document.querySelector(".mast-motto");
    if (!name) return;
    var a = name.getBoundingClientRect();
    var left = a.left, top = a.top, right = a.right, bottom = a.bottom;
    if (motto) {
      var b = motto.getBoundingClientRect();
      if (b.width && b.height) {
        left = Math.min(left, b.left);
        top = Math.min(top, b.top);
        right = Math.max(right, b.right);
        bottom = Math.max(bottom, b.bottom);
      }
    }
    var padX = 20, padY = 10;
    var vw = window.innerWidth || 1;
    var vh = window.innerHeight || 1;
    // Veil SVG viewBox is 1200 x 1600, drawn at 100% x 200% of the viewport,
    // so 1200 units = 100vw and 800 units = 100vh.
    hole.setAttribute("x", ((left - padX) / vw) * 1200);
    hole.setAttribute("y", ((top - padY) / vh) * 800);
    hole.setAttribute("width", ((right - left + padX * 2) / vw) * 1200);
    hole.setAttribute("height", ((bottom - top + padY * 2) / vh) * 800);
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
    mapMastHole();
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(mapMastHole).catch(function () {});
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

  window.addEventListener("resize", mapMastHole);
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
