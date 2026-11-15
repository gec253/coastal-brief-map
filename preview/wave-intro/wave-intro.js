(function () {
  var KEY = "cb-wave-intro-seen";
  var TS_KEY = "cb-wave-intro-seen-at";
  var WINDOW_MS = 12 * 60 * 60 * 1000;
  var DURATION = 1300;
  var REDUCE_MS = 200;
  var overlay = document.getElementById("wave-intro");
  var skip = document.getElementById("wi-skip");
  var replay = document.getElementById("wi-replay");
  var sound = document.getElementById("wi-sound");
  var svg = overlay && overlay.querySelector(".wi-svg");
  var sheet = overlay && overlay.querySelector(".wi-sheet");
  var lineIvory = overlay && overlay.querySelector(".wi-line-ivory");
  var lineSea = overlay && overlay.querySelector(".wi-line-sea");
  var lineBrass = overlay && overlay.querySelector(".wi-line-brass");
  var reduceMedia = window.matchMedia && (
    window.matchMedia("(prefers-reduced-motion: reduce)").matches ||
    window.matchMedia("(prefers-reduced-data: reduce)").matches
  );
  var params = new URLSearchParams(location.search || "");
  var forcePlay = params.get("play") === "1";
  var forceSeen = params.get("seen") === "1";
  var seek = params.get("seek");
  var timer = 0;
  var raf = 0;
  var startTs = 0;
  var lastTs = 0;
  var reduce = !!reduceMedia;
  var ruleBox = null;

  // Handmade swell profile in viewBox units (y positive down). Long,
  // asymmetric, modest amplitude — not a repeating sine and not a break.
  var XS = [-140, 40, 200, 380, 560, 740, 900, 1140];
  // One long coastal swell and a quieter following ripple, not a repeating sine.
  var BASE = [14, 28, 40, 8, -44, -16, 12, 18];
  var LAYERS = [
    { yOff: 32, amp: 0.55, drift: 0.18, phase: 0.41, shift: 130 },
    { yOff: 16, amp: 0.78, drift: -0.12, phase: 0.67, shift: -90 },
    { yOff: 0, amp: 1, drift: 0.08, phase: 0.1, shift: 0 }
  ];
  var MORPH = [
    [0.31, 0.17, 0.41, 0.22],
    [0.44, 0.63, 0.28, 0.11],
    [0.22, 0.39, 0.47, 0.71],
    [0.38, 0.08, 0.33, 0.54],
    [0.27, 0.52, 0.19, 0.36],
    [0.49, 0.14, 0.41, 0.67],
    [0.18, 0.58, 0.29, 0.21],
    [0.36, 0.44, 0.23, 0.59]
  ];


  var BRASS_STOPS = [
    ["0", "#8C6A3C"],
    ["0.35", "#C4A36A"],
    ["0.5", "#B08A52"],
    ["0.72", "#C4A36A"],
    ["1", "#8C6A3C"]
  ];

  function svgEl(name) {
    return document.createElementNS("http://www.w3.org/2000/svg", name);
  }

  function paintGradient(svg, id) {
    if (!svg || svg.querySelector("#" + id)) return;
    var defs = svg.querySelector("defs");
    if (!defs) {
      defs = svgEl("defs");
      svg.insertBefore(defs, svg.firstChild);
    }
    var g = svgEl("linearGradient");
    g.setAttribute("id", id);
    g.setAttribute("x1", "0");
    g.setAttribute("y1", "0");
    g.setAttribute("x2", "1");
    g.setAttribute("y2", "0");
    var i, s;
    for (i = 0; i < BRASS_STOPS.length; i++) {
      s = svgEl("stop");
      s.setAttribute("offset", BRASS_STOPS[i][0]);
      s.setAttribute("stop-color", BRASS_STOPS[i][1]);
      g.appendChild(s);
    }
    defs.appendChild(g);
  }

  function ensureAgedBrass() {
    var mast = document.querySelector(".mast-wave-svg");
    if (!mast) return;
    paintGradient(mast, "wi-rule-brass");
    var settle = mast.querySelector(".wave-settle");
    if (settle) settle.setAttribute("stroke", "url(#wi-rule-brass)");
  }

  function mapRule() {
    var settle = document.querySelector(".wave-settle") || document.querySelector(".mast-wave");
    if (!settle) {
      ruleBox = null;
      return;
    }
    var r = settle.getBoundingClientRect();
    var cs = window.getComputedStyle(settle);
    var sw = parseFloat(cs.strokeWidth) || 1.15;
    var vw = window.innerWidth || 1;
    var vh = window.innerHeight || 1;
    var top = r.top;
    var bottom = r.bottom;
    var thickness = r.height > 0.2 ? r.height : sw;
    var midY = r.height > 0.2 ? (top + bottom) / 2 : top;
    ruleBox = {
      x1: (r.left / vw) * 1000,
      x2: (r.right / vw) * 1000,
      y: (midY / vh) * 1000,
      thickness: thickness,
      left: r.left,
      right: r.right,
      midY: midY
    };
  }

  function markSeen() {
    try { sessionStorage.setItem(KEY, "1"); } catch (e) {}
    try { localStorage.setItem(TS_KEY, String(Date.now())); } catch (e) {}
  }

  function clearSeen() {
    try { sessionStorage.removeItem(KEY); } catch (e) {}
    try { localStorage.removeItem(TS_KEY); } catch (e) {}
  }

  function seenRecently() {
    try { if (sessionStorage.getItem(KEY) === "1") return true; } catch (e) {}
    try {
      var ts = parseInt(localStorage.getItem(TS_KEY) || "", 10);
      if (ts && (Date.now() - ts) < WINDOW_MS) return true;
    } catch (e) {}
    return false;
  }

  function sameOriginReferrer() {
    try {
      if (!document.referrer) return false;
      return new URL(document.referrer).origin === location.origin;
    } catch (e) { return false; }
  }

  function isBackForward() {
    try {
      var nav = performance.getEntriesByType && performance.getEntriesByType("navigation")[0];
      if (nav && nav.type === "back_forward") return true;
      if (performance.navigation && performance.navigation.type === 2) return true;
    } catch (e) {}
    return false;
  }

  function isTopLevelLanding() {
    if (window.top !== window) return false;
    var path = location.pathname.replace(/\/+$/, "") || "/";
    return path === "/" || path === "/preview/intro";
  }

  function shouldPlay() {
    if (forcePlay) return true;
    if (forceSeen) return false;
    if (!isTopLevelLanding()) return false;
    if (isBackForward()) return false;
    if (sameOriginReferrer()) return false;
    if (seenRecently()) return false;
    return true;
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

  // CSS cubic-bezier(.65, 0, .35, 1) sampled for the travel ease.
  function sampleBezier(a, b, t) {
    var mt = 1 - t;
    return 3 * mt * mt * t * a + 3 * mt * t * t * b + t * t * t;
  }

  function easeTravel(t) {
    if (t <= 0) return 0;
    if (t >= 1) return 1;
    var lo = 0, hi = 1, mid, i;
    for (i = 0; i < 12; i++) {
      mid = (lo + hi) / 2;
      if (sampleBezier(0.65, 0.35, mid) < t) lo = mid;
      else hi = mid;
    }
    mid = (lo + hi) / 2;
    return sampleBezier(0, 1, mid);
  }

  function baseAt(x) {
    var i, t, x0, x1;
    if (x <= XS[0]) return BASE[0];
    if (x >= XS[XS.length - 1]) return BASE[BASE.length - 1];
    for (i = 0; i < XS.length - 1; i++) {
      if (x <= XS[i + 1]) {
        x0 = XS[i];
        x1 = XS[i + 1];
        t = (x - x0) / (x1 - x0);
        // Smoothstep the spatial interpolation so joins stay soft.
        t = t * t * (3 - 2 * t);
        return BASE[i] * (1 - t) + BASE[i + 1] * t;
      }
    }
    return BASE[BASE.length - 1];
  }

  function pointY(i, raw, layer) {
    var m = MORPH[i];
    var wobble =
      8 * Math.sin((raw * m[0] + m[2]) * Math.PI * 2) +
      5 * Math.sin((raw * m[1] + m[3] + layer.phase) * Math.PI * 2);
    var drift = layer.drift * raw * 18;
    // Gentle left-to-right tilt so the front is slightly diagonal,
    // not a level curtain.
    var tilt = (XS[i] / 1000 - 0.36) * 36;
    var env = 0.92 + 0.08 * Math.cos(raw * 1.05 + layer.phase);
    return baseAt(XS[i] + layer.shift) * layer.amp * env + wobble * layer.amp + drift + tilt + layer.yOff;
  }

  function curveD(xs, ys) {
    var i, d, p0, p1, p2, p3, c1x, c1y, c2x, c2y, n;
    n = xs.length;
    d = "M " + xs[0].toFixed(2) + " " + ys[0].toFixed(2);
    for (i = 0; i < n - 1; i++) {
      p0 = i === 0 ? 0 : i - 1;
      p1 = i;
      p2 = i + 1;
      p3 = i + 2 >= n ? n - 1 : i + 2;
      c1x = xs[p1] + (xs[p2] - xs[p0]) / 6;
      c1y = ys[p1] + (ys[p2] - ys[p0]) / 6;
      c2x = xs[p2] - (xs[p3] - xs[p1]) / 6;
      c2y = ys[p2] - (ys[p3] - ys[p1]) / 6;
      d += " C " + c1x.toFixed(2) + " " + c1y.toFixed(2) + ", " +
        c2x.toFixed(2) + " " + c2y.toFixed(2) + ", " +
        xs[p2].toFixed(2) + " " + ys[p2].toFixed(2);
    }
    return d;
  }

  function settleT(raw) {
    // Flatten the brass line onto the measured rule and hold still
    // for the last beats so the handoff frame can match.
    if (raw <= 0.36) return 0;
    if (raw >= 0.84) return 1;
    return easeTravel((raw - 0.36) / 0.48);
  }

  function morphToRule(xs, ys, t) {
    if (!ruleBox || t <= 0) return { xs: xs, ys: ys };
    var i, n = xs.length, outX = [], outY = [];
    for (i = 0; i < n; i++) {
      var u = n === 1 ? 0 : i / (n - 1);
      var tx = ruleBox.x1 + u * (ruleBox.x2 - ruleBox.x1);
      outX.push(xs[i] + (tx - xs[i]) * t);
      outY.push(ys[i] + (ruleBox.y - ys[i]) * t);
    }
    return { xs: outX, ys: outY };
  }

  function layerYs(raw, eased, layer) {
    // Travel: start just above the viewport, end just below it, with
    // room for amplitude so t=0 is fully covered and t=1 is clear.
    // Line is already kissing the top at t=0, and leaves the bottom
    // near the end so the last beats are a settle, not a blank hold.
    var front = 28 + eased * 1060;
    var i, ys = [];
    for (i = 0; i < XS.length; i++) ys.push(front + pointY(i, raw, layer));
    return ys;
  }

  function draw(raw) {
    if (!sheet) return;
    if (raw < 0) raw = 0;
    if (raw > 1) raw = 1;
    if (!ruleBox) mapRule();
    var eased = easeTravel(raw);
    var st = settleT(raw);
    var ivoryYs = layerYs(raw, eased, LAYERS[2]);
    var seaYs = layerYs(raw, eased, LAYERS[1]);
    var brassYs = layerYs(raw, eased, LAYERS[0]);
    var ivory = { xs: XS.slice(), ys: ivoryYs };
    var sea = { xs: XS.slice(), ys: seaYs };
    var brass = morphToRule(XS.slice(), brassYs, st);
    var dIvory = curveD(ivory.xs, ivory.ys);
    sheet.setAttribute("d", dIvory + " L 1140 1400 L -140 1400 Z");
    if (lineSea) lineSea.setAttribute("d", curveD(sea.xs, sea.ys));
    if (lineIvory) lineIvory.setAttribute("d", dIvory);
    if (lineBrass) {
      lineBrass.setAttribute("d", curveD(brass.xs, brass.ys));
      // Thickness eases onto the measured rule; the line itself never fades.
      var startW = 0.9;
      var endW = ruleBox ? ruleBox.thickness : 1.15;
      lineBrass.style.strokeWidth = (startW + (endW - startW) * st) + "px";
      lineBrass.style.opacity = "1";
    }
    // Ivory and sea trail the departing sheet and fade with it.
    // The brass heritage line stays until the handoff frame.
    var trailFade = raw < 0.86 ? 1 : 1 - (raw - 0.86) / 0.14;
    if (lineIvory) lineIvory.style.opacity = String(0.96 * trailFade);
    if (lineSea) lineSea.style.opacity = String(0.55 * trailFade);
    if (svg) svg.style.opacity = "1";
    if (skip) {
      var s = 1;
      if (raw > 0.22) s = raw >= 0.4 ? 0 : 1 - (raw - 0.22) / 0.18;
      skip.style.opacity = String(s);
      skip.style.pointerEvents = s < 0.05 ? "none" : "auto";
    }
  }

  function stopLoop() {
    if (raf) {
      window.cancelAnimationFrame(raf);
      raf = 0;
    }
    if (timer) {
      window.clearTimeout(timer);
      timer = 0;
    }
    startTs = 0;
    lastTs = 0;
  }

  function tick(now) {
    if (!startTs) startTs = now;
    var elapsed = now - startTs;
    var raw = elapsed / DURATION;
    var dt = lastTs ? now - lastTs : 0;
    lastTs = now;
    if (typeof window.__wiOnFrame === "function") {
      try { window.__wiOnFrame(now, raw, dt); } catch (e) {}
    }
    if (raw >= 1) {
      draw(1);
      raf = 0;
      finish();
      return;
    }
    draw(raw);
    raf = window.requestAnimationFrame(tick);
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
    if (svg) svg.style.opacity = "1";
    ensureAgedBrass();
    mapRule();
    stopLoop();
    if (seek !== null && seek !== "") {
      var ms = Math.max(0, parseInt(seek, 10) || 0);
      document.documentElement.setAttribute("data-intro-seek", "");
      document.documentElement.style.setProperty("--intro-ms", String(ms));
      draw(Math.min(1, ms / DURATION));
      return;
    }
    if (reduce) {
      draw(0);
      if (skip) skip.focus();
      timer = window.setTimeout(finish, REDUCE_MS);
      return;
    }
    draw(0);
    if (skip) skip.focus();
    raf = window.requestAnimationFrame(tick);
  }

  function skipNow() {
    stopLoop();
    document.documentElement.removeAttribute("data-intro-seek");
    finish();
  }

  function replayIntro() {
    stopLoop();
    clearSeen();
    document.documentElement.removeAttribute("data-intro-seek");
    document.documentElement.style.removeProperty("--intro-ms");
    seek = "";
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

  if (sound) {
    sound.addEventListener("click", function () {
      if (!sound.dataset.src) return;
      sound.hidden = false;
    });
  }

  ensureAgedBrass();
  window.addEventListener("resize", mapRule);
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(mapRule).catch(function () {});

  window.__wiDuration = DURATION;
  window.__wiDraw = draw;
  window.__wiMapRule = mapRule;
  window.__wiFinish = finish;

  if (!shouldPlay()) {
    hide();
    return;
  }
  play();
})();
