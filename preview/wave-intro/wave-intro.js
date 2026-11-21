(function () {
  var KEY = "cb-wave-intro-seen";
  var TS_KEY = "cb-wave-intro-seen-at";
  var WINDOW_MS = 12 * 60 * 60 * 1000;
  var DURATION = 1300;
  var HARD_MAX = 1500;      // ms from play(): never longer, even after a stall
  var overlay = document.getElementById("wave-intro");
  var skip = document.getElementById("wi-skip");
  var replay = document.getElementById("wi-replay");
  var sound = document.getElementById("wi-sound");
  var svg = overlay && overlay.querySelector(".wi-svg");
  var sheet = overlay && overlay.querySelector(".wi-sheet");
  var fill = overlay && overlay.querySelector(".wi-fill");
  var lines = overlay && overlay.querySelector(".wi-lines");
  var contours = overlay ? overlay.querySelectorAll(".wi-contour") : [];
  var lineFoam = overlay && overlay.querySelector(".wi-line-foam");
  var lineBrass = overlay && overlay.querySelector(".wi-line-brass");
  var brassGrad = overlay && overlay.querySelector("#wi-brass-aged");
  var foamGrad = overlay && overlay.querySelector("#wi-foam");
  var brassClip = overlay && overlay.querySelector("#wi-brass-clip rect");
  var reduceMedia = window.matchMedia && (
    window.matchMedia("(prefers-reduced-motion: reduce)").matches ||
    window.matchMedia("(prefers-reduced-data: reduce)").matches
  );
  var params = new URLSearchParams(location.search || "");
  var forcePlay = params.get("play") === "1";
  var forceSeen = params.get("seen") === "1";
  var seek = params.get("seek");
  var raf = 0;
  var timer = 0;
  var lastTs = 0;
  var reduce = !!reduceMedia;
  var ruleBox = null;

  // V7: ONE wash of water, one direction, over a page that is already
  // there. The page renders underneath from the first frame and stays
  // interactive (the overlay takes no pointer events, Skip aside). The
  // swell starts already part-way down the screen and already moving, then
  // runs out like swash up a beach: it slows, thins and its wash fades, so
  // the ending is almost nothing and attention lands on the conditions.
  //
  // Every x follows one monotone descent F(tau) on its own local clock
  // tau = t - delay(x, t); a single broad crest drifts gently right. The
  // crest's drift keeps d(delay)/dt far under 1 (MAX_RATE guard), so every
  // edge sample only moves DOWN, and the drawn edge (a quadratic B-spline,
  // positive weights) only moves down too: what is revealed stays revealed.
  // The wash's opacity only ever falls, so what is still under it only
  // ever gets clearer.
  //
  // Depth: the navy wash plus one subtle secondary contour (a muted sea-
  // green band: the same surface a few ms further back in time, LAGS), and
  // a fine seafoam leading line.
  var TRAVEL = 1700;        // ms of the descent curve (it leaves the screen earlier)
  var START = 0.13;         // edge already 12% down the screen on frame 0
  var POW = 2.3;            // ease-out power: fastest at the start, rolls out
  var D_DIAG = 22;          // left leads the right slightly
  var D_CREST = 40;         // crest lag: crest height ~ speed x this
  var LAGS = [0, 14];       // navy wash, sea-green secondary contour (top)
  var AMPS = [1, 1.12];
  var CREST_BACK = 0.5;     // long gentle back (viewport widths)
  var CREST_FACE = 0.3;     // shorter leading face
  var CREST_FROM = 0.1, CREST_TO = 0.95; // a gentle drift, not a sweep
  var MAX_RATE = 0.75;      // d(delay)/dt guard (must stay < 1)
  var WASH_FROM = 0.84, WASH_TO = 0.22; // wash opacity: only ever falls
  // Brass settle: near the masthead rule every layer's height is remapped
  // through y - B*tanh((y - rule)/W), a smooth monotone curve with a soft
  // plateau at the rule. The aged-brass top edge lies down along the rule
  // as it reaches it; the brass is drawn only above the rule (a clip), so
  // the line that stays behind is the real rule, already on the page in
  // the same aged-brass gradient. It never fades: it settles.
  var SETTLE_W = 16, SETTLE_FLAT = 0.7;
  var N = 40;               // edge samples (quadratic B-spline)
  var vw = 390, vh = 844;
  var skipBox = null;

  function mapRule() {
    var box = svg ? svg.getBoundingClientRect() : null;
    vw = (box && box.width) || window.innerWidth || 1;
    vh = (box && box.height) || window.innerHeight || 1;
    var ox = box ? box.left : 0, oy = box ? box.top : 0;
    if (svg) svg.setAttribute("viewBox", "0 0 " + vw.toFixed(2) + " " + vh.toFixed(2));
    if (lines) lines.setAttribute("viewBox", "0 0 " + vw.toFixed(2) + " " + vh.toFixed(2));
    if (skip) {
      var sb = skip.getBoundingClientRect();
      skipBox = { x: sb.left - ox + sb.width / 2, top: sb.top - oy };
    }
    var settle = document.querySelector(".wave-settle");
    if (!settle) {
      ruleBox = null;
      if (brassClip) brassClip.setAttribute("height", "0");
      return;
    }
    var r = settle.getBoundingClientRect();
    var midY = r.height > 0.2 ? (r.top + r.bottom) / 2 : r.top;
    ruleBox = { left: r.left - ox, right: r.right - ox, y: midY - oy };
    // The overlay's brass uses the rule's own gradient, mapped onto the
    // rule's own span, so where the two meet they are the same colour.
    if (brassGrad) {
      brassGrad.setAttribute("x1", ruleBox.left.toFixed(2));
      brassGrad.setAttribute("x2", ruleBox.right.toFixed(2));
    }
    if (brassClip) {
      brassClip.setAttribute("x", ruleBox.left.toFixed(2));
      brassClip.setAttribute("width", Math.max(0, ruleBox.right - ruleBox.left).toFixed(2));
      brassClip.setAttribute("y", "-200");
      brassClip.setAttribute("height", Math.max(0, 200 + ruleBox.y + 0.4).toFixed(2));
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
    if (reduce && !(seek !== null && seek !== "")) return false;
    if (forcePlay) return true;
    if (forceSeen) return false;
    if (!isTopLevelLanding()) return false;
    if (isBackForward()) return false;
    if (sameOriginReferrer()) return false;
    if (seenRecently()) return false;
    return true;
  }

  // Removal happens only once every part of the overlay is below the
  // viewport (or on Skip), so taking it out of the page changes no pixel.
  // The page itself is never restyled: no class on html/body changes
  // anything the reader can see.
  function hide() {
    if (!overlay) return;
    overlay.setAttribute("hidden", "");
    overlay.setAttribute("aria-hidden", "true");
    document.documentElement.classList.add("intro-seen");
    document.documentElement.classList.remove("intro-play");
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

  function settleB() { return ruleBox ? SETTLE_FLAT * SETTLE_W : 0; }

  // Descent: on screen and moving on frame 0, then a smooth ease-out
  // (1 - (1 - s)^POW): no acceleration from rest, no bounce, no stop on
  // screen. Before tau = 0 (points still on their delay) the edge keeps
  // its starting speed, so there is no kink in time.
  function descent(tau) {
    var b = settleB();
    var y0 = START * vh, y1 = vh * 1.1 + b + 30;
    var v0 = (y1 - y0) * POW / TRAVEL;
    if (tau <= 0) return y0 + tau * v0;
    if (tau >= TRAVEL) return y1 + (tau - TRAVEL) * 0.02;
    return y0 + (y1 - y0) * (1 - Math.pow(1 - tau / TRAVEL, POW));
  }

  // Wash opacity: a smooth monotone fall from WASH_FROM to WASH_TO over the
  // run (smoothstep), so covered content only ever gets clearer.
  function washAt(t) {
    var s = Math.min(1, Math.max(0, t / (DURATION - 100)));
    s = s * s * (3 - 2 * s);
    return WASH_FROM + (WASH_TO - WASH_FROM) * s;
  }

  // Smooth, monotone remap with a soft plateau at the masthead rule.
  function settle(y) {
    if (!ruleBox) return y;
    return y - settleB() * Math.tanh((y - ruleBox.y) / SETTLE_W);
  }

  function crestAt(t) {
    // Crest centre (viewport widths): one slow, eased drift to the right.
    var p = t / (TRAVEL + 80);
    if (p < 0) p = 0;
    if (p > 1) p = 1;
    return CREST_FROM + (CREST_TO - CREST_FROM) * cubic(0.4, 0.15, 0.6, 0.9, p);
  }

  // Asymmetric bump with a smoothly varying width: C-infinity, no kink at
  // the peak (a long back, a shorter face).
  function bump(v) {
    var face = Math.min(Math.max(CREST_FACE * vw, 110), 300);
    var back = Math.min(Math.max(CREST_BACK * vw, 180), 520);
    var s = 0.5 * (face + back) + 0.5 * (face - back) * Math.tanh(v / 40);
    return Math.exp(-0.5 * (v / s) * (v / s));
  }

  function delay(u, t, amp) {
    var v = (u - crestAt(t)) * vw;
    return D_DIAG * u + D_CREST * amp * bump(v);
  }

  // Height of layer k (0 = navy wash, 1 = sea-green secondary contour, top).
  function layerY(x, t, k) {
    return settle(descent(t - delay(x / vw, t, AMPS[k]) - LAGS[k]));
  }

  // Quadratic B-spline through the sample midpoints, with the samples as
  // control points. x is evenly spaced, so at any fixed x the curve's height
  // is a fixed, non-negative blend of neighbouring samples: if every sample
  // only moves down, so does every point of the drawn edge (no overshoot,
  // unlike an interpolating spline).
  function curveD(xs, ys) {
    var n = xs.length, i, mx, my;
    var d = "M " + xs[0].toFixed(2) + " " + ys[0].toFixed(2);
    mx = (xs[0] + xs[1]) / 2;
    my = (ys[0] + ys[1]) / 2;
    d += " L " + mx.toFixed(2) + " " + my.toFixed(2);
    for (i = 1; i < n - 1; i++) {
      mx = (xs[i] + xs[i + 1]) / 2;
      my = (ys[i] + ys[i + 1]) / 2;
      d += " Q " + xs[i].toFixed(2) + " " + ys[i].toFixed(2) + ", " + mx.toFixed(2) + " " + my.toFixed(2);
    }
    d += " L " + xs[n - 1].toFixed(2) + " " + ys[n - 1].toFixed(2);
    return d;
  }

  // Worst-case d(delay)/dt over the whole timeline (all layers, all x).
  function maxDelayRate() {
    var worst = 0, t, i, k, u, r;
    for (t = 0; t <= DURATION; t += 4) {
      for (i = 0; i <= 80; i++) {
        u = -0.05 + 1.1 * i / 80;
        for (k = 0; k < AMPS.length; k++) {
          r = (delay(u, t + 2, AMPS[k]) - delay(u, t - 2, AMPS[k])) / 4;
          if (r > worst) worst = r;
        }
      }
    }
    return worst;
  }

  var state = { minTop: -Infinity, t: 0 };
  var TOP = LAGS.length - 1;

  function draw(raw) {
    if (!sheet) return;
    if (raw < 0) raw = 0;
    if (raw > 1) raw = 1;
    if (!ruleBox) mapRule();
    var t = raw * DURATION;
    // The wash opacity is applied to the two wash layers themselves (the
    // fill and the band SVG), which meet edge to edge on a whole device
    // pixel, so nothing overlaps or doubles and no offscreen group is needed.
    var wa = washAt(t).toFixed(4);
    if (fill) fill.style.opacity = wa;
    if (svg) svg.style.opacity = wa;
    var pad = vw * 0.04;
    var i, k, u, xi = [], ys = [], minTop = Infinity, maxBody = -Infinity;
    for (k = 0; k <= TOP; k++) ys.push([]);
    for (i = 0; i < N; i++) {
      u = i / (N - 1);
      xi.push(-pad + (vw + 2 * pad) * u);
    }
    for (i = 0; i < N; i++) {
      for (k = 0; k <= TOP; k++) ys[k].push(layerY(xi[i], t, k));
      if (ys[TOP][i] < minTop) minTop = ys[TOP][i];
      if (ys[0][i] > maxBody) maxBody = ys[0][i];
    }
    // The SVG paints only a band from the leading edge to just past the
    // body's lowest point; the composited fill carries the navy below it.
    var dpr = window.devicePixelRatio || 1;
    var fillTop = Math.max(0, Math.ceil((maxBody + 1) * dpr) / dpr);
    var bandBottom = fillTop.toFixed(3);
    var close = " L " + (vw + pad).toFixed(2) + " " + bandBottom + " L " + (-pad).toFixed(2) + " " + bandBottom + " Z";
    var dTop = curveD(xi, ys[TOP]);
    for (k = 0; k < contours.length; k++) {
      // contours[0] is the top (leading) contour, then the next one down.
      var layer = TOP - k;
      contours[k].setAttribute("d", (layer === TOP ? dTop : curveD(xi, ys[layer])) + close);
    }
    sheet.setAttribute("d", curveD(xi, ys[0]) + close);
    if (fill) fill.style.transform = "translate3d(0," + fillTop.toFixed(3) + "px,0)";
    if (lineFoam) lineFoam.setAttribute("d", dTop);
    if (lineBrass) lineBrass.setAttribute("d", dTop);
    if (foamGrad) {
      // The seafoam highlight lives only on the crest's shoulder.
      var cx = crestAt(t) * vw;
      foamGrad.setAttribute("x1", (cx - 0.42 * vw).toFixed(2));
      foamGrad.setAttribute("x2", (cx + 0.3 * vw).toFixed(2));
    }
    state.minTop = minTop;
    state.t = t;
    if (skip) {
      // Skip sits on the navy at the bottom-left; it eases out well before
      // the swell reaches it, so it never sits over the page.
      var sx = skipBox ? skipBox.x : 60;
      var stop = skipBox ? skipBox.top : vh - 60;
      var gap = stop - layerY(sx, t, TOP);
      var so = gap <= 70 ? 0 : gap >= 210 ? 1 : (gap - 70) / 140;
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
    lastTs = 0;
  }

  var clock = 0;
  var ema = 16.7;
  var playT0 = 0;
  function tick(now) {
    // The first tick advances one nominal frame, so the swell is already
    // moving on the frame after first paint (no held frame at the start).
    var dt = lastTs ? now - lastTs : 16.7;
    lastTs = now;
    // Virtual clock: a long main-thread frame advances at most ~2 frames,
    // so a stall never shows up as a visible jump in the swell. Spikes are
    // capped relative to the recent frame rate, so a slow but steady device
    // still runs in real time.
    clock += Math.min(dt, Math.max(34, 2 * ema));
    if (dt > 0) ema = 0.8 * ema + 0.2 * Math.min(dt, 100);
    // Hard 1.8s cap from play(), without a cut: once the clock has fallen
    // behind (stalls), it is carried forward in real time so the swell
    // still clears the screen by HARD_MAX.
    var floor = DURATION - (HARD_MAX - (now - playT0));
    if (clock < floor) clock = floor;
    var raw = clock / DURATION;
    if (typeof window.__wiOnFrame === "function") {
      try { window.__wiOnFrame(now, raw, dt); } catch (e) {}
    }
    draw(raw);
    // Done once the whole swell, stroke included, is below the screen, so
    // removing the overlay is invisible. At raw = 1 it always is.
    if (raw >= 1 || state.minTop > vh + 3) {
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
    raf = window.requestAnimationFrame(tick);
  }

  function play() {
    if (!overlay) return;
    document.documentElement.classList.remove("intro-seen");
    document.documentElement.classList.add("intro-play");
    overlay.removeAttribute("hidden");
    overlay.setAttribute("aria-hidden", "false");
    mapRule();
    stopLoop();
    playT0 = window.performance && performance.now ? performance.now() : 0;
    if (seek !== null && seek !== "") {
      var ms = Math.max(0, parseInt(seek, 10) || 0);
      document.documentElement.setAttribute("data-intro-seek", "");
      draw(Math.min(1, ms / DURATION));
      return;
    }
    draw(0);
    if (skip) skip.focus();
    // Start at once: frame 0 is already in motion, so holding it for the
    // page's deferred scripts would read as a stutter. The virtual clock
    // below caps any stall to ~2 frames instead.
    startLoop();
  }

  // Skip works in the same event: the overlay is gone before the handler
  // returns.
  function skipNow() {
    stopLoop();
    document.documentElement.removeAttribute("data-intro-seek");
    finish();
  }

  function replayIntro() {
    stopLoop();
    clearSeen();
    document.documentElement.removeAttribute("data-intro-seek");
    seek = "";
    if (reduce) return;
    play();
  }

  if (skip) skip.addEventListener("click", skipNow);
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && overlay && !overlay.hasAttribute("hidden")) {
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

  window.addEventListener("resize", mapRule);
  window.addEventListener("scroll", mapRule, { passive: true });
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(mapRule).catch(function () {});

  window.__wiDuration = DURATION;
  window.__wiDraw = draw;
  window.__wiMapRule = mapRule;
  window.__wiFinish = finish;
  window.__wiState = state;
  window.__wiTop = function (x, ms) { return layerY(x, ms, TOP); };
  window.__wiLayer = function (x, ms, k) { return layerY(x, ms, k); };
  window.__wiCrest = function (ms) { return crestAt(ms) * vw; };
  window.__wiRule = function () { return ruleBox; };
  window.__wiMaxDelayRate = maxDelayRate;
  window.__wiMaxRate = MAX_RATE;
  window.__wiWash = washAt;

  if (!shouldPlay()) {
    if (reduce) markSeen();
    hide();
    return;
  }
  play();
  // Scout (v7b): the phone mini-bar stays pinned (see wave-intro.css) through
  // the intro and until the visitor's first scroll or interaction; then the
  // page's normal glance-on-screen auto-hide takes over, so the bar never
  // slides away by itself.
  (function releaseBarOnFirstInteraction() {
    var root = document.documentElement;
    var evs = ["scroll", "wheel", "touchstart", "pointerdown", "keydown"];
    function release() {
      root.classList.add("bar-released");
      for (var i = 0; i < evs.length; i++) {
        window.removeEventListener(evs[i], release, true);
      }
    }
    for (var i = 0; i < evs.length; i++) {
      window.addEventListener(evs[i], release, { capture: true, passive: true });
    }
  })();
})();
