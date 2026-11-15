(function () {
  var KEY = "cb-wave-intro-seen";
  var TS_KEY = "cb-wave-intro-seen-at";
  var WINDOW_MS = 12 * 60 * 60 * 1000;
  var DURATION = 1900;
  var HARD_MAX = 2000;      // ms from the first frame drawn: never longer
  var REDUCE_MS = 200;
  var overlay = document.getElementById("wave-intro");
  var skip = document.getElementById("wi-skip");
  var replay = document.getElementById("wi-replay");
  var sound = document.getElementById("wi-sound");
  var svg = overlay && overlay.querySelector(".wi-svg");
  var sheet = overlay && overlay.querySelector(".wi-sheet");
  var fill = overlay && overlay.querySelector(".wi-fill");
  var lineIvory = overlay && overlay.querySelector(".wi-line-ivory");
  var lineSea = overlay && overlay.querySelector(".wi-line-sea");
  var lineBrass = overlay && overlay.querySelector(".wi-line-brass");
  var washes = overlay ? overlay.querySelectorAll(".wi-wash") : [];
  var ripples = overlay ? overlay.querySelectorAll(".wi-ripple") : [];
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

  // One swell, two clocks. Every x follows the same monotone vertical
  // descent F(tau), but on its own local clock tau = t - delay(x, t).
  // A travelling bump in the delay is the crest: it rolls left to right
  // while the edge descends, so the edge shape evolves and local speed
  // varies along it. Because d(delay)/dt stays well under 1, tau never
  // runs backwards: the edge never re-covers revealed content.
  var TRAVEL = 1880;        // ms for one point to cross the viewport
  var D_DIAG = 24;          // left leads the right by this much (diagonal)
  var D_CREST = 70;         // crest lag: crest height ~ speed x this
  var D_RIP = 14;           // a broad, slower trough behind the crest
  var CREST_BACK = 0.30;    // long gentle back (in viewport widths)
  var CREST_FACE = 0.15;    // shorter leading face
  // Soft leading edge: translucent wash layers trail the solid navy on the
  // same clock, WASH ms behind it, so the band is thin when the water moves
  // slowly and opens up mid-sweep. Ripples ride the wash behind the crest.
  var WASH = 54;
  var WASH_STEPS = [1, 0.72, 0.46, 0.22];
  var RIPPLE_STEPS = [0.72, 0.46];
  var N = 30;               // edge samples (Catmull-Rom -> cubic Beziers)
  var SEA_OFF = 7, BRASS_OFF = 14, SMIN_K = 12;
  var vw = 390, vh = 844;
  var skipBox = null;

  var BRASS_STOPS = [
    ["0", "#A67C45"],
    ["0.35", "#C4A36A"],
    ["0.5", "#D0B07A"],
    ["0.72", "#C4A36A"],
    ["1", "#A67C45"]
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
    g.setAttribute("gradientUnits", "userSpaceOnUse");
    g.setAttribute("x1", "0");
    g.setAttribute("y1", "0");
    g.setAttribute("x2", "100%");
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
    var box = svg ? svg.getBoundingClientRect() : null;
    vw = (box && box.width) || window.innerWidth || 1;
    vh = (box && box.height) || window.innerHeight || 1;
    var ox = box ? box.left : 0, oy = box ? box.top : 0;
    if (svg) svg.setAttribute("viewBox", "0 0 " + vw.toFixed(2) + " " + vh.toFixed(2));
    if (skip) {
      var sb = skip.getBoundingClientRect();
      skipBox = { x: sb.left - ox + sb.width / 2, top: sb.top - oy };
    }
    var settle = document.querySelector(".wave-settle") || document.querySelector(".mast-wave");
    if (!settle) {
      ruleBox = null;
      return;
    }
    var r = settle.getBoundingClientRect();
    var cs = window.getComputedStyle(settle);
    var sw = parseFloat(cs.strokeWidth) || 1.25;
    var midY = r.height > 0.2 ? (r.top + r.bottom) / 2 : r.top;
    // Browsers paint an inline SVG from a device-pixel-snapped origin, so the
    // real rule sits a fraction of a pixel off its layout position. Apply the
    // same snap so the overlay line and the real rule are the same pixels.
    var mastBox = document.querySelector(".mast-wave-svg");
    if (mastBox) {
      var dpr = window.devicePixelRatio || 1;
      var mt = mastBox.getBoundingClientRect().top;
      midY += Math.round(mt * dpr) / dpr - mt;
    }
    ruleBox = {
      left: r.left - ox,
      right: r.right - ox,
      y: midY - oy,
      thickness: sw
    };
    // Match the overlay brass gradient to the real rule's, pixel for pixel.
    var mast = document.querySelector(".mast-wave-svg");
    var grad = svg && svg.querySelector("#wi-aged-brass");
    if (mast && grad) {
      var m = mast.getBoundingClientRect();
      grad.setAttribute("x1", (m.left - ox).toFixed(2));
      grad.setAttribute("x2", (m.right - ox).toFixed(2));
    }
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
    document.documentElement.classList.remove("intro-play", "intro-reduce", "intro-rule-live");
    if (skip && document.activeElement === skip) skip.blur();
  }

  function finish() {
    markSeen();
    hide();
  }

  // Solve a CSS cubic-bezier(x1, y1, x2, y2) for progress t.
  function bez(a, b, t) {
    var mt = 1 - t;
    return 3 * mt * mt * t * a + 3 * mt * t * t * b + t * t * t;
  }

  function cubic(x1, y1, x2, y2, t) {
    if (t <= 0) return 0;
    if (t >= 1) return 1;
    var lo = 0, hi = 1, mid, i;
    for (i = 0; i < 18; i++) {
      mid = (lo + hi) / 2;
      if (bez(x1, x2, mid) < t) lo = mid;
      else hi = mid;
    }
    return bez(y1, y2, (lo + hi) / 2);
  }

  // Descent: moving from the first frame (no hold), a soft swell of
  // acceleration, then a long natural deceleration as it leaves.
  var Y_START = -(BRASS_OFF + 6);
  function descent(tau) {
    var y1 = vh + 64;
    if (tau <= 0) return Y_START + tau * 0.12; // continues smoothly above the top
    if (tau >= TRAVEL) return y1 + (tau - TRAVEL) * 0.05;
    return Y_START + (y1 - Y_START) * cubic(0.4, 0.08, 0.55, 0.92, tau / TRAVEL);
  }

  function crestAt(t) {
    // Crest centre (in viewport widths) rolls from just off the left to off
    // the right, nearly linearly through the part of the timeline when the
    // edge is over the page, so the peak visibly sweeps the whole width.
    var p = (t - 60) / (TRAVEL + 40);
    if (p < 0) p = 0;
    if (p > 1) p = 1;
    return -0.16 + 1.4 * cubic(0.25, 0.12, 0.7, 0.92, p);
  }

  function delay(u, t, lag) {
    // Crest widths are capped in pixels so a wide desktop still reads as
    // one rolling swell rather than a near-flat line.
    var v = (u - (crestAt(t) - lag)) * vw;
    var sig = v > 0 ? Math.min(Math.max(CREST_FACE * vw, 64), 180) : Math.min(Math.max(CREST_BACK * vw, 120), 380);
    var swell = 0.8 + 0.2 * Math.sin(Math.PI * Math.min(1, Math.max(0, t / DURATION)));
    var crest = D_CREST * swell * Math.exp(-0.5 * (v / sig) * (v / sig));
    var rc = -0.75 + 1.4 * Math.min(1, t / DURATION);
    var rv = (u - rc) / 0.32;
    var rip = D_RIP * (1 - Math.exp(-0.5 * rv * rv));
    return D_DIAG * u + crest + rip;
  }

  function edgeY(x, t, lag) {
    return descent(t - delay(x / vw, t, lag));
  }

  function smin(a, b, k) {
    var h = Math.max(k - Math.abs(a - b), 0) / k;
    return Math.min(a, b) - h * h * k * 0.25;
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

  // Top of a wash layer: the same edge, f * WASH ms further back in time.
  function washY(x, t, f) {
    return descent(t - delay(x / vw, t, 0) - WASH * f);
  }

  function seaY(x, t) {
    return Math.max(edgeY(x, t, 0) + 3, edgeY(x, t, 0.035) + SEA_OFF);
  }

  function brassRaw(x, t) {
    return Math.max(seaY(x, t) + 3, edgeY(x, t, 0.07) + BRASS_OFF);
  }

  // How much of the rule the brass line has landed on (0..1). Monotone in t.
  function landed(t) {
    if (!ruleBox) return 0;
    var M = 16, i, x, hit = 0;
    for (i = 0; i <= M; i++) {
      x = ruleBox.left + (ruleBox.right - ruleBox.left) * (i / M);
      if (brassRaw(x, t) >= ruleBox.y + SMIN_K) hit++;
    }
    return hit / (M + 1);
  }

  function ruleRevealed(t) {
    if (!ruleBox) return true;
    var M = 16, i, x;
    for (i = 0; i <= M; i++) {
      x = ruleBox.left + (ruleBox.right - ruleBox.left) * (i / M);
      if (washY(x, t, 1) < ruleBox.y + ruleBox.thickness + 1) return false;
    }
    return true;
  }

  var state = { minEdge: 0, minWash: 0, handoff: false };

  function draw(raw) {
    if (!sheet) return;
    if (raw < 0) raw = 0;
    if (raw > 1) raw = 1;
    if (!ruleBox) mapRule();
    var t = raw * DURATION;
    var pad = vw * 0.04;
    var i, u, x, xi = [], yi = [], ys = [], yb = [], xb = [], minE = Infinity;
    for (i = 0; i < N; i++) {
      u = i / (N - 1);
      x = -pad + (vw + 2 * pad) * u;
      xi.push(x);
      yi.push(edgeY(x, t, 0));
      ys.push(seaY(x, t));
      if (yi[i] < minE) minE = yi[i];
    }
    var dIvory = curveD(xi, yi);
    // Wash layers: each a band from its own trailing curve down to the solid
    // edge. Flat translucent fills stack into a soft ramp (no filters).
    var k, j, wy, back, minW = Infinity;
    for (k = 0; k < washes.length && k < WASH_STEPS.length; k++) {
      wy = [];
      for (i = 0; i < N; i++) {
        wy.push(washY(xi[i], t, WASH_STEPS[k]));
        if (k === 0 && wy[i] < minW) minW = wy[i];
      }
      back = "";
      for (j = N - 1; j >= 0; j--) back += " L " + xi[j].toFixed(2) + " " + (yi[j] + 1).toFixed(2);
      washes[k].setAttribute("d", curveD(xi, wy) + back + " Z");
    }
    state.minWash = washes.length ? minW : minE;
    // Secondary ripples: short sea-glass strokes on the wash, trailing the
    // crest, faded at both ends by a gradient that follows them.
    var cx = crestAt(t) * vw;
    for (k = 0; k < ripples.length && k < RIPPLE_STEPS.length; k++) {
      var rx0 = cx - vw * (0.42 + 0.1 * k), rx1 = cx - vw * (0.02 + 0.06 * k);
      var rxs = [], rys = [], M = 12;
      for (j = 0; j <= M; j++) {
        x = rx0 + (rx1 - rx0) * (j / M);
        rxs.push(x);
        rys.push(washY(x, t, RIPPLE_STEPS[k]));
      }
      ripples[k].setAttribute("d", curveD(rxs, rys));
      var rg = svg && svg.querySelector("#wi-rip-" + (k + 1));
      if (rg) {
        rg.setAttribute("x1", rx0.toFixed(1));
        rg.setAttribute("x2", rx1.toFixed(1));
      }
    }
    // The SVG sheet is only a band from the edge to just past its lowest
    // point; the composited fill layer carries the navy below it (with a
    // generous overlap so no seam can open on fractional pixels).
    var maxE = -Infinity;
    for (i = 0; i < N; i++) if (yi[i] > maxE) maxE = yi[i];
    var fillTop = Math.max(0, maxE + 24);
    var bandBottom = fillTop + 40;
    sheet.setAttribute("d", dIvory + " L " + (vw + pad).toFixed(2) + " " + bandBottom.toFixed(2) +
      " L " + (-pad).toFixed(2) + " " + bandBottom.toFixed(2) + " Z");
    if (fill) fill.style.transform = "translate3d(0," + fillTop.toFixed(2) + "px,0)";
    if (lineIvory) lineIvory.setAttribute("d", dIvory);
    if (lineSea) lineSea.setAttribute("d", curveD(xi, ys));
    state.minEdge = minE;

    if (lineBrass) {
      // The brass line rides deepest on the swell, lands on the rule from
      // the left as the crest rolls past, and draws in to the rule's length.
      var land = landed(t);
      var s = land * land * (3 - 2 * land);
      for (i = 0; i < N; i++) {
        u = i / (N - 1);
        x = xi[i];
        if (ruleBox) x = x + ((ruleBox.left + (ruleBox.right - ruleBox.left) * u) - x) * s;
        xb.push(x);
        yb.push(ruleBox ? smin(brassRaw(x, t), ruleBox.y, SMIN_K) : brassRaw(x, t));
      }
      if (ruleBox && land >= 1) {
        for (i = 0; i < N; i++) yb[i] = ruleBox.y;
      }
      lineBrass.setAttribute("d", curveD(xb, yb));
      lineBrass.style.strokeWidth = (ruleBox ? ruleBox.thickness : 1.25) + "px";
      // Hand off in the same frame once it lies exactly on the rule and the
      // rule itself is uncovered; the line never fades.
      var live = !!ruleBox && land >= 1 && ruleRevealed(t);
      state.handoff = live;
      lineBrass.style.opacity = live ? "0" : "1";
      document.documentElement.classList.toggle("intro-rule-live", live);
    }
    if (svg) svg.style.opacity = "1";
    if (skip) {
      // Skip sits on the navy at the bottom-left; it eases out before the
      // edge reaches it.
      var sx = skipBox ? skipBox.x : 60;
      var stop = skipBox ? skipBox.top : vh - 60;
      var gap = stop - washY(sx, t, 1);
      var so = gap <= 60 ? 0 : gap >= 200 ? 1 : (gap - 60) / 140;
      skip.style.opacity = String(so);
      skip.style.pointerEvents = so < 0.05 ? "none" : "auto";
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

  var clock = 0;
  var ema = 16.7;
  var playT0 = 0;
  function tick(now) {
    var dt = lastTs ? now - lastTs : 0;
    lastTs = now;
    if (!startTs) startTs = now;
    // Virtual clock: a long main-thread frame advances at most ~2 frames,
    // so a stall never shows up as a visible jump in the swell.
    // Spikes are capped relative to the recent frame rate, so a slow but
    // steady device still runs in real time.
    clock += Math.min(dt, Math.max(34, 2 * ema));
    if (dt > 0) ema = 0.8 * ema + 0.2 * Math.min(dt, 100);
    // Hard 2.0s cap from the first drawn frame, without a jump: once the
    // clock has fallen behind (stalls), it is carried forward in real time
    // so it still reaches the end exactly at HARD_MAX.
    var floor = DURATION - (HARD_MAX - (now - playT0));
    if (clock < floor) clock = floor;
    var raw = clock / DURATION;
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
    // Done as soon as the sheet and its faintest wash have left the screen
    // and the brass line is the real rule: nothing on screen is removed.
    if (state.handoff && state.minWash > vh + 1) {
      raf = 0;
      finish();
      return;
    }
    raf = window.requestAnimationFrame(tick);
  }

  function startLoop() {
    clock = 0;
    ema = 16.7;
    lastTs = 0;
    startTs = 0;
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
    playT0 = window.performance && performance.now ? performance.now() : 0;
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
    // Begin once the deferred page scripts have run, so their start-up work
    // lands on the still frame (plain navy) rather than mid-swell, but never
    // wait more than ~120ms after first paint: on a slow connection those
    // scripts can take seconds and the page must not sit behind the sheet.
    if (document.readyState === "loading") {
      var begun = false;
      var begin = function () {
        if (begun || overlay.classList.contains("is-done")) return;
        begun = true;
        document.removeEventListener("DOMContentLoaded", onReady);
        if (timer) { window.clearTimeout(timer); timer = 0; }
        startLoop();
      };
      var onReady = function () { raf = window.requestAnimationFrame(begin); };
      document.addEventListener("DOMContentLoaded", onReady);
      raf = window.requestAnimationFrame(function () { timer = window.setTimeout(begin, 120); });
    } else {
      startLoop();
    }
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
  window.addEventListener("scroll", mapRule, { passive: true });
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(mapRule).catch(function () {});

  window.__wiDuration = DURATION;
  window.__wiDraw = draw;
  window.__wiMapRule = mapRule;
  window.__wiFinish = finish;
  window.__wiState = state;
  window.__wiEdge = function (x, ms) { return edgeY(x, ms, 0); };
  window.__wiWash = function (x, ms) { return washY(x, ms, 1); };
  window.__wiCrest = function (ms) { return crestAt(ms) * vw; };

  if (!shouldPlay()) {
    hide();
    return;
  }
  play();
})();
