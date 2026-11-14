/* Coastal Brief — Conditions at a glance (Phase 1 dashboard).
   Every value shown here comes from /api/conditions, which names the station,
   source, and observation time for each reading. Nothing is estimated here:
   missing readings show as unavailable, old ones as stale. */
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const REGION_STORE = "coastalBrief.region";
  const REFRESH_MS = 5 * 60 * 1000;
  const SVGNS = "http://www.w3.org/2000/svg";
  const state = { regions: [], regionId: null, data: null, windAngle: null, prev: {}, timer: null, loading: false };

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c];
    });
  }
  function reduced() {
    return window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  }
  function isNum(v) { return typeof v === "number" && isFinite(v); }
  function fmt(v, d) { return isNum(v) ? v.toFixed(d == null ? 0 : d) : "—"; }

  // ---------- time (always Eastern) ----------
  const ET = "America/New_York";
  const dayKey = new Intl.DateTimeFormat("en-CA", { timeZone: ET, year: "numeric", month: "2-digit", day: "2-digit" });
  const clockFmt = new Intl.DateTimeFormat("en-US", { timeZone: ET, hour: "numeric", minute: "2-digit" });
  const hourFmt = new Intl.DateTimeFormat("en-US", { timeZone: ET, hour: "numeric" });
  const wdFmt = new Intl.DateTimeFormat("en-US", { timeZone: ET, weekday: "short" });
  function toDate(t) { return t instanceof Date ? t : new Date(t); }
  function clock(t) { return clockFmt.format(toDate(t)); }
  function etTime(t, withZone) {
    const d = toDate(t);
    if (isNaN(d)) return "—";
    const same = dayKey.format(d) === dayKey.format(new Date());
    return (same ? "" : wdFmt.format(d) + " ") + clock(d) + (withZone === false ? "" : " ET");
  }
  function ago(min) {
    if (!isNum(min)) return "";
    if (min < 1) return "just now";
    if (min < 90) return Math.round(min) + " min ago";
    const h = min / 60;
    return (h < 10 ? h.toFixed(1) : Math.round(h)) + " h ago";
  }
  function ageNow(iso) { return (Date.now() - new Date(iso).getTime()) / 60000; }

  // ---------- source captions ----------
  const RAW_LABELS = {
    WSPD_ms: ["Wind speed (WSPD)", "m/s"], GST_ms: ["Gust (GST)", "m/s"], WDIR_degT: ["Direction (WDIR)", "° true"],
    WVHT_m: ["Significant wave height (WVHT)", "m"], DPD_s: ["Dominant period (DPD)", "s"], APD_s: ["Average period (APD)", "s"],
    MWD_degT: ["Mean wave direction (MWD)", "° true"], SwH_m: ["Swell height (SwH)", "m"], SwP_s: ["Swell period (SwP)", "s"],
    SwD: ["Swell direction (SwD)", ""], WWH_m: ["Wind-wave height (WWH)", "m"], WWP_s: ["Wind-wave period (WWP)", "s"],
    WWD: ["Wind-wave direction (WWD)", ""], WTMP_C: ["Water temperature (WTMP)", "°C"], ATMP_C: ["Air temperature (ATMP)", "°C"],
    PRES_hPa: ["Pressure (PRES)", "hPa"], PTDY_hPa: ["3-hour tendency (PTDY)", "hPa"], v_F: ["Reported value", "°F"],
    v_mb: ["Pressure", "mb"], v_mb_3h_ago: ["Pressure 3 hours earlier", "mb"], s_kt: ["Wind speed", "kt"], g_kt: ["Gust", "kt"],
    d_degT: ["Direction", "° true"], temperature_C: ["Temperature", "°C"],
  };
  function rawList(raw) {
    if (!raw) return "";
    const parts = [];
    Object.keys(raw).forEach(function (k) {
      const v = raw[k];
      const lab = RAW_LABELS[k] || [k, ""];
      parts.push("<li>" + esc(lab[0]) + ": <b>" + (v == null ? "missing" : esc(v) + (lab[1] ? " " + esc(lab[1]) : "")) + "</b></li>");
    });
    return '<ul class="src-raw">' + parts.join("") + "</ul>";
  }
  function srcCaption(r, opts) {
    opts = opts || {};
    const st = (r && r.station) || {};
    if (!r || !st.id) return '<div class="src src-none">Source not available</div>';
    const when = r.time ? etTime(r.time) : (r.lastReport ? "last report " + etTime(r.lastReport) : "no recent report");
    const where = isNum(st.distanceMi) ? st.distanceMi + " mi " + (st.bearingFromAnchor || "") + " of " + (st.anchor || "the region") : "";
    const fallback = (r.tried || []).filter(function (t) { return t.id !== st.id; });
    let body = '<p class="src-title"><b>' + esc(st.name) + "</b> (" + esc(st.id) + ")</p>" +
      "<p>" + esc(st.network || "") + " · " + esc(st.agency || "") + "</p>" +
      (where ? "<p>" + esc(where) + ". " + esc(st.setting || "") + ".</p>" : "") +
      (r.time ? "<p>Observed " + esc(etTime(r.time)) + " (" + esc(ago(ageNow(r.time))) + "). Marked stale after " + esc(r.staleAfterMin) + " min.</p>" : "") +
      (r.status === "unavailable" ? "<p>No usable report right now" + (r.lastReport ? "; last report " + esc(etTime(r.lastReport)) : "") + ". Nothing is shown in its place.</p>" : "") +
      (r.note ? "<p>" + esc(r.note) + "</p>" : "") +
      (fallback.length ? "<p>Preferred station " + esc(fallback.map(function (t) { return t.id + " (" + t.result + ")"; }).join(", ")) + ", so this reading is from " + esc(st.id) + ".</p>" : "") +
      (r.raw ? "<p>As reported" + (r.rawUnits ? " (" + esc(r.rawUnits) + ")" : "") + ":</p>" + rawList(r.raw) : "") +
      (opts.note ? "<p>" + esc(opts.note) + "</p>" : "") +
      '<p class="src-links">' + (st.url ? '<a href="' + esc(st.url) + '" target="_blank" rel="noopener">Station page</a>' : "") +
      (r.dataUrl ? ' · <a href="' + esc(r.dataUrl) + '" target="_blank" rel="noopener">Raw data</a>' : "") + "</p>";
    return '<details class="src"><summary><span class="src-id">' + esc(st.id) + "</span><span class=\"src-name\">" + esc(opts.label || st.name) +
      "</span><span class=\"src-time\">" + esc(when) + "</span></summary><div class=\"src-body\">" + body + "</div></details>";
  }
  function kindTag(kind) {
    if (kind === "pred-obs") return '<span class="tag tag-predicted">Predicted</span><span class="tag tag-observed">Observed</span>';
    const label = kind === "forecast" ? "Forecast" : kind === "predicted" ? "Predicted" : "Observed";
    return '<span class="tag tag-' + esc(kind || "observed") + '">' + label + "</span>";
  }
  function statusChip(r) {
    if (!r) return "";
    if (r.status === "stale") return '<span class="chip-stale" title="Older than this station\'s normal reporting gap">Stale · ' + esc(etTime(r.time)) + "</span>";
    if (r.status === "unavailable") return '<span class="chip-off">Not reporting</span>';
    return "";
  }
  function head(title, r, kind) {
    return '<header class="inst-h"><h3 class="inst-k">' + esc(title) + "</h3>" + statusChip(r) + kindTag(kind || (r && r.kind)) + "</header>";
  }
  function stateClass(el, r) {
    el.classList.remove("is-loading", "is-stale", "is-off");
    if (!r || r.status === "unavailable") el.classList.add("is-off");
    else if (r.status === "stale") el.classList.add("is-stale");
  }
  function val(r) { return r && r.status !== "unavailable" ? r.values || {} : {}; }

  // ---------- number tweening ----------
  function tweenAll(root) {
    root.querySelectorAll("[data-num]").forEach(function (el) {
      const key = el.getAttribute("data-key");
      const to = Number(el.getAttribute("data-num"));
      const dec = Number(el.getAttribute("data-dec") || 0);
      const from = state.prev[key];
      state.prev[key] = to;
      if (!isFinite(to)) return;
      if (reduced() || from == null || !isFinite(from) || from === to) { el.textContent = to.toFixed(dec); return; }
      const t0 = performance.now();
      const dur = 700;
      function step(t) {
        const k = Math.min(1, (t - t0) / dur);
        const e = 1 - Math.pow(1 - k, 3);
        el.textContent = (from + (to - from) * e).toFixed(dec);
        if (k < 1) requestAnimationFrame(step);
      }
      el.textContent = from.toFixed(dec);
      requestAnimationFrame(step);
    });
  }
  function numSpan(key, v, dec) {
    if (!isNum(v)) return '<span class="num-off">—</span>';
    return '<span data-key="' + key + '" data-num="' + v + '" data-dec="' + (dec || 0) + '">' + v.toFixed(dec || 0) + "</span>";
  }

  // ---------- wind ----------
  function polar(c, r, deg) {
    const a = ((deg - 90) * Math.PI) / 180;
    return [c + r * Math.cos(a), c + r * Math.sin(a)];
  }
  function windDialSvg() {
    const C = 150, R = 140;
    let ticks = "";
    for (let a = 0; a < 360; a += 5) {
      const major = a % 30 === 0, mid = a % 10 === 0;
      const r1 = R - 6, r0 = r1 - (major ? 14 : mid ? 8 : 4);
      const p0 = polar(C, r0, a), p1 = polar(C, r1, a);
      ticks += '<line x1="' + p0[0].toFixed(2) + '" y1="' + p0[1].toFixed(2) + '" x2="' + p1[0].toFixed(2) + '" y2="' + p1[1].toFixed(2) +
        '" class="' + (major ? "tk-major" : mid ? "tk-mid" : "tk-minor") + '"/>';
    }
    let nums = "";
    [30, 60, 120, 150, 210, 240, 300, 330].forEach(function (a) {
      const p = polar(C, R - 34, a);
      nums += '<text x="' + p[0].toFixed(1) + '" y="' + (p[1] + 3.5).toFixed(1) + '" class="dial-deg">' + a + "</text>";
    });
    let card = "";
    [["N", 0], ["E", 90], ["S", 180], ["W", 270]].forEach(function (c) {
      const p = polar(C, R - 36, c[1]);
      card += '<text x="' + p[0].toFixed(1) + '" y="' + (p[1] + 6).toFixed(1) + '" class="dial-card' + (c[0] === "N" ? " is-n" : "") + '">' + c[0] + "</text>";
    });
    const tip = polar(C, R - 52, 0), bl = polar(C, R - 4, -6.5), br = polar(C, R - 4, 6.5), notch = polar(C, R - 14, 0);
    const tail0 = polar(C, 62, 180), tail1 = polar(C, R - 56, 180);
    return (
      '<svg class="dial" viewBox="0 0 300 300" aria-hidden="true" focusable="false">' +
      '<defs><radialGradient id="dialFace" cx="50%" cy="38%" r="70%"><stop offset="0%" class="face-hi"/><stop offset="100%" class="face-lo"/></radialGradient></defs>' +
      '<circle cx="150" cy="150" r="147" class="bezel"/>' +
      '<circle cx="150" cy="150" r="' + R + '" class="face" fill="url(#dialFace)"/>' +
      '<circle cx="150" cy="150" r="' + (R - 48) + '" class="ring-in"/>' +
      '<circle cx="150" cy="150" r="62" class="ring-core"/>' +
      ticks + nums + card +
      '<path d="M150 4 L144 -4 L156 -4 Z" class="lubber" transform="translate(0 8)"/>' +
      '<g class="needle" id="wind-needle" style="transform: rotate(0deg)">' +
      '<line x1="' + tail0[0] + '" y1="' + tail0[1] + '" x2="' + tail1[0].toFixed(1) + '" y2="' + tail1[1].toFixed(1) + '" class="needle-tail"/>' +
      '<path d="M' + bl[0].toFixed(2) + " " + bl[1].toFixed(2) + " L" + tip[0].toFixed(2) + " " + tip[1].toFixed(2) + " L" + br[0].toFixed(2) + " " + br[1].toFixed(2) +
      " L" + notch[0].toFixed(2) + " " + notch[1].toFixed(2) + ' Z" class="needle-head"/>' +
      "</g></svg>"
    );
  }
  function renderWind(r) {
    const el = $("i-wind");
    const v = val(r);
    stateClass(el, r);
    const has = isNum(v.speedKt);
    if (!el.querySelector(".dial")) {
      el.innerHTML = head("Wind", r) +
        '<div class="wind-body"><div class="dial-wrap">' + windDialSvg() +
        '<div class="dial-center"><div class="wind-speed" id="wind-speed"></div><div class="wind-unit">knots</div><div class="wind-gust" id="wind-gust"></div></div></div>' +
        '<div class="wind-side"><div class="wind-from" id="wind-from"></div><dl class="readouts" id="wind-reads"></dl></div></div>' +
        '<div class="inst-foot" id="wind-src"></div>' +
        '<div class="harbor" id="i-harbor"></div>';
    } else {
      el.querySelector(".inst-h").outerHTML = head("Wind", r);
    }
    $("wind-speed").innerHTML = has ? numSpan("wspd", Math.round(v.speedKt)) : '<span class="num-off">—</span>';
    $("wind-gust").innerHTML = isNum(v.gustKt) ? "gust <b>" + numSpan("wgst", Math.round(v.gustKt)) + "</b>" : (has ? "gust not reported" : "");
    $("wind-from").innerHTML = isNum(v.dirDeg)
      ? '<span class="from-k">From</span><span class="from-c">' + esc(v.dirCompass) + '</span><span class="from-d">' + numSpan("wdir", v.dirDeg) + "°</span>"
      : '<span class="from-k">Direction</span><span class="from-c">—</span>';
    $("wind-reads").innerHTML =
      "<div><dt>Sustained</dt><dd>" + (has ? fmt(v.speedKt, 1) + " kt" : "—") + "</dd></div>" +
      "<div><dt>Gust</dt><dd>" + (isNum(v.gustKt) ? fmt(v.gustKt, 1) + " kt" : "—") + "</dd></div>" +
      "<div><dt>Heading</dt><dd>" + (isNum(v.dirDeg) ? fmt(v.dirDeg) + "° true" : "—") + "</dd></div>";
    $("wind-src").innerHTML = srcCaption(r, { note: "The pointer sits on the side the wind is blowing from. Speeds are converted from m/s to knots (× 1.944)." });
    const needle = $("wind-needle");
    const dial = el.querySelector(".dial");
    dial.setAttribute("role", "img");
    dial.setAttribute("aria-label", has && isNum(v.dirDeg)
      ? "Wind from " + v.dirCompass + ", " + Math.round(v.dirDeg) + " degrees, " + Math.round(v.speedKt) + " knots" + (isNum(v.gustKt) ? ", gusting " + Math.round(v.gustKt) : "")
      : "Wind direction not available");
    needle.classList.toggle("is-hidden", !isNum(v.dirDeg));
    if (isNum(v.dirDeg)) setNeedle(v.dirDeg);
    flow.set(isNum(v.dirDeg) && has ? v.dirDeg : null, has ? v.speedKt : 0, r && r.status === "ok");
  }

  // Needle: a lightly damped spring, so it swings to the new heading and
  // settles with one small overshoot. Always takes the short way round.
  const needleSpring = { cur: null, vel: 0, target: 0, raf: 0, last: 0 };
  function applyNeedle(a) {
    const n = $("wind-needle");
    if (n) n.style.transform = "rotate(" + a.toFixed(2) + "deg)";
  }
  function setNeedle(deg) {
    const S = needleSpring;
    if (S.cur == null) {
      S.cur = reduced() ? deg : deg - 70;
      S.target = deg;
    } else {
      const delta = ((deg - (S.target % 360)) + 540) % 360 - 180;
      S.target = S.target + delta;
    }
    state.windAngle = S.target;
    if (reduced()) { S.cur = S.target; S.vel = 0; applyNeedle(S.cur); return; }
    applyNeedle(S.cur);
    if (S.raf) return;
    S.last = performance.now();
    function step(t) {
      const dt = Math.min(0.05, (t - S.last) / 1000);
      S.last = t;
      const k = 38, c = 9.5; // stiffness, damping (≈ 0.77 damping ratio: one soft overshoot)
      const acc = k * (S.target - S.cur) - c * S.vel;
      S.vel += acc * dt;
      S.cur += S.vel * dt;
      applyNeedle(S.cur);
      if (Math.abs(S.target - S.cur) < 0.05 && Math.abs(S.vel) < 0.05) {
        S.cur = S.target; S.vel = 0; applyNeedle(S.cur); S.raf = 0; return;
      }
      S.raf = requestAnimationFrame(step);
    }
    S.raf = requestAnimationFrame(step);
  }

  // Air-flow streaks inside the dial ring. Drift direction is the observed
  // wind direction (toward which it blows) and pace scales with observed
  // speed. Nothing is drawn without a current reading, when calm, off
  // screen, in a hidden tab, or with reduced motion.
  const flow = (function () {
    let cv = null, ctx = null, dir = null, kt = 0, live = false, raf = 0, parts = [], last = 0, dpr = 1, size = 0;
    function ensure() {
      const wrap = document.querySelector("#i-wind .dial-wrap");
      if (!wrap) return false;
      cv = wrap.querySelector("canvas.flow");
      if (!cv) {
        cv = document.createElement("canvas");
        cv.className = "flow";
        cv.setAttribute("aria-hidden", "true");
        wrap.insertBefore(cv, wrap.querySelector(".dial-center"));
      }
      dpr = Math.min(2, window.devicePixelRatio || 1);
      size = wrap.clientWidth;
      if (cv.width !== Math.round(size * dpr) || cv.height !== Math.round(size * dpr)) { cv.width = Math.round(size * dpr); cv.height = Math.round(size * dpr); }
      ctx = cv.getContext("2d");
      return !!ctx;
    }
    // positions are in dial units (viewBox 300, centre 150); band r 64–91
    function spawn(p) {
      const ang = Math.random() * Math.PI * 2, r = Math.sqrt(64 * 64 + Math.random() * (91 * 91 - 64 * 64));
      p.x = Math.cos(ang) * r; p.y = Math.sin(ang) * r; p.life = 0; p.span = 1.4 + Math.random() * 1.6;
    }
    function seed() {
      parts = [];
      for (let i = 0; i < 42; i++) { const p = {}; spawn(p); p.life = Math.random() * p.span; parts.push(p); }
    }
    function visible() {
      const d = $("conditions");
      return !document.hidden && !(d && d.classList.contains("is-offscreen"));
    }
    function frame(t) {
      raf = 0;
      if (!ctx || dir == null || !live || reduced()) return;
      if (!visible()) return; // resumes on visibility/scroll events
      const dt = Math.min(0.05, (t - (last || t)) / 1000);
      last = t;
      const S = size * dpr, C = S / 2, unit = S / 300;
      ctx.clearRect(0, 0, S, S);
      // blowing toward dir+180; screen y grows downward
      const toward = ((dir + 180) * Math.PI) / 180;
      const vx = Math.sin(toward), vy = -Math.cos(toward);
      const dark = document.documentElement.getAttribute("data-theme") === "dark";
      ctx.lineCap = "round";
      ctx.lineWidth = 1.7 * dpr;
      const spd = 14 + Math.min(40, kt) * 2.2; // dial units per second
      const len = 7 + Math.min(30, kt) * 0.55;
      for (const p of parts) {
        p.x += vx * spd * dt; p.y += vy * spd * dt; p.life += dt;
        const rr = Math.hypot(p.x, p.y);
        if (p.life > p.span || rr > 91 || rr < 64) { spawn(p); continue; }
        const edge = Math.min(1, (91 - rr) / 6, (rr - 64) / 6);
        const fade = Math.sin(Math.PI * (p.life / p.span)) * edge;
        ctx.strokeStyle = dark ? "rgba(169,214,204," + (0.62 * fade).toFixed(3) + ")" : "rgba(43,111,143," + (0.5 * fade).toFixed(3) + ")";
        ctx.beginPath();
        ctx.moveTo(C + (p.x - vx * len) * unit, C + (p.y - vy * len) * unit);
        ctx.lineTo(C + p.x * unit, C + p.y * unit);
        ctx.stroke();
      }
      raf = requestAnimationFrame(frame);
    }
    function kick() {
      if (!raf && ctx && dir != null && live && !reduced() && visible()) { last = 0; raf = requestAnimationFrame(frame); }
    }
    document.addEventListener("visibilitychange", kick);
    window.addEventListener("scroll", kick, { passive: true });
    window.addEventListener("resize", function () { if (ensure()) kick(); });
    return {
      set: function (d, speed, fresh) {
        if (!ensure()) return;
        dir = d; kt = speed || 0;
        // only animate a current (not stale) reading of at least 1 knot
        live = d != null && fresh && kt >= 1;
        if (!parts.length) seed();
        if (!live || reduced()) { ctx.clearRect(0, 0, cv.width, cv.height); if (raf) { cancelAnimationFrame(raf); raf = 0; } return; }
        kick();
      },
    };
  })();

  // ---------- seas ----------
  function waveSvg(hFt, periodS, cls) {
    const h = isNum(hFt) ? hFt : 0;
    const amp = Math.max(3, Math.min(26, 3 + h * 2.6));
    const lam = Math.max(46, Math.min(150, (isNum(periodS) ? periodS : 7) * 12));
    function path(a, l, y, phase) {
      let d = "M" + (-l) + " 120 L" + (-l) + " " + y;
      for (let x = -l; x <= 400 + l; x += 4) {
        const yy = y - a * Math.sin(((x + phase) / l) * 2 * Math.PI) - a * 0.18 * Math.sin(((x + phase) / l) * 4 * Math.PI + 0.8);
        d += " L" + x + " " + yy.toFixed(2);
      }
      return d + " L" + (400 + l) + " 120 Z";
    }
    const base = 64;
    return '<svg class="wave-art ' + (cls || "") + '" viewBox="0 0 400 110" preserveAspectRatio="none" aria-hidden="true" focusable="false">' +
      '<defs><linearGradient id="wg-' + (cls || "s") + '" x1="0" y1="0" x2="0" y2="1"><stop offset="0" class="wg-top"/><stop offset="1" class="wg-bot"/></linearGradient></defs>' +
      '<g class="wave-layer back" style="--lam:' + lam * 0.8 + 'px"><path d="' + path(amp * 0.6, lam * 0.8, base - 8, 20) + '" class="wave-back"/></g>' +
      '<g class="wave-layer front" style="--lam:' + lam + 'px"><path d="' + path(amp, lam, base + 6, 0) + '" fill="url(#wg-' + (cls || "s") + ')" class="wave-front"/></g>' +
      '<line x1="0" x2="400" y1="' + (base + 6) + '" y2="' + (base + 6) + '" class="wave-mean"/>' +
      "</svg>";
  }
  function dirArrow(deg, label) {
    if (!isNum(deg)) return "";
    // Arrow points the way the waves travel (toward), from the reported "from" direction.
    return '<svg class="dir-arrow" viewBox="0 0 24 24" aria-hidden="true" style="transform: rotate(' + ((deg + 180) % 360) + 'deg)"><path d="M12 3 L17 13 L13 11.5 L13 21 L11 21 L11 11.5 L7 13 Z"/></svg>';
  }
  const COMPASS_DEG = { N: 0, NNE: 22.5, NE: 45, ENE: 67.5, E: 90, ESE: 112.5, SE: 135, SSE: 157.5, S: 180, SSW: 202.5, SW: 225, WSW: 247.5, W: 270, WNW: 292.5, NW: 315, NNW: 337.5 };
  function renderSeas(r) {
    const el = $("i-seas");
    const v = val(r);
    stateClass(el, r);
    el.innerHTML = head("Seas", r) +
      '<div class="big-read"><span class="big-num">' + numSpan("hs", v.heightFt, 1) + '</span><span class="big-unit">ft</span></div>' +
      '<div class="big-label">Significant wave height</div>' +
      waveSvg(v.heightFt, v.dominantPeriodS, "seas") +
      '<dl class="readouts three">' +
      "<div><dt>Dominant period</dt><dd>" + (isNum(v.dominantPeriodS) ? fmt(v.dominantPeriodS) + " s" : "—") + "</dd></div>" +
      "<div><dt>Average period</dt><dd>" + (isNum(v.averagePeriodS) ? fmt(v.averagePeriodS, 1) + " s" : "—") + "</dd></div>" +
      "<div><dt>Mean direction</dt><dd>" + (isNum(v.meanDirDeg) ? dirArrow(v.meanDirDeg) + "from " + esc(v.meanDirCompass) + " " + fmt(v.meanDirDeg) + "°" : "—") + "</dd></div>" +
      "</dl>" +
      '<div class="inst-foot">' + srcCaption(r, { note: "Significant wave height is the average of the highest third of waves, all wave trains combined. Converted from meters (× 3.281)." }) + "</div>";
    tweenAll(el);
  }

  // ---------- swell ----------
  function renderSwell(r) {
    const el = $("i-swell");
    const v = val(r);
    stateClass(el, r);
    const sw = v.heightFt, ww = v.windWaveFt;
    const max = Math.max(isNum(sw) ? sw : 0, isNum(ww) ? ww : 0, 1);
    function bar(label, h, p, d, cls) {
      const pct = isNum(h) ? Math.max(2, (h / max) * 100) : 0;
      return '<div class="energy ' + cls + '"><div class="energy-k">' + label + "</div>" +
        '<div class="energy-track"><span style="--w:' + pct.toFixed(1) + '%"></span></div>' +
        '<div class="energy-v">' + (isNum(h) ? fmt(h, 1) + " ft" : "—") + (isNum(p) ? " · " + fmt(p, 1) + " s" : "") + (d ? " · from " + esc(d) : "") + "</div></div>";
    }
    const unavailable = !r || r.status === "unavailable";
    el.innerHTML = head("Swell", r) +
      (unavailable
        ? '<div class="big-read"><span class="big-num num-off">—</span></div><div class="big-label">Swell data unavailable for this area right now</div>'
        : '<div class="swell-top"><div><div class="big-read"><span class="big-num">' + numSpan("swh", sw, 1) + '</span><span class="big-unit">ft</span></div>' +
          '<div class="big-label">Swell height</div></div>' +
          '<dl class="readouts stack"><div><dt>Swell period</dt><dd>' + (isNum(v.periodS) ? fmt(v.periodS, 1) + " s" : "—") + "</dd></div>" +
          "<div><dt>Swell direction</dt><dd>" + (v.dirCompass ? dirArrow(COMPASS_DEG[v.dirCompass]) + "from " + esc(v.dirCompass) : "—") + "</dd></div></dl></div>" +
          '<div class="energy-wrap">' + bar("Swell", sw, v.periodS, v.dirCompass, "is-swell") + bar("Wind sea", ww, v.windWavePeriodS, v.windWaveDirCompass, "is-wind") + "</div>") +
      '<div class="inst-foot">' + srcCaption(r, { label: (r && r.station ? r.station.name + " spectrum" : ""), note: "NDBC splits the buoy's measured wave spectrum into swell and wind sea. Direction is reported as a compass point only. Converted from meters." }) + "</div>";
    tweenAll(el);
  }

  // ---------- tides ----------
  function renderTide(t) {
    const el = $("i-tide");
    el.classList.remove("is-loading", "is-off");
    if (!t || t.status !== "ok") {
      el.classList.add("is-off");
      el.innerHTML = head("Tide", null, "predicted") + '<div class="big-label">Tide predictions are unavailable right now.</div>' +
        '<div class="inst-foot">' + predCaption(t) + "</div>";
      return;
    }
    const now = Date.now();
    const events = t.events || [];
    const next = events.filter(function (e) { return e.t > now; });
    const prev = events.filter(function (e) { return e.t <= now; }).pop();
    const n0 = next[0];
    const curve = t.curve || [];
    const nowH = interp(curve, now);
    const rising = n0 ? n0.type === "H" : null;
    const mins = n0 ? Math.round((n0.t - now) / 60000) : null;
    const inTxt = mins == null ? "" : (mins >= 60 ? Math.floor(mins / 60) + " h " + (mins % 60) + " min" : mins + " min");
    el.innerHTML = head("Tide", null, t.observed && t.observed.status !== "unavailable" ? "pred-obs" : "predicted") +
      '<div class="tide-top">' +
      '<div class="tide-next">' + (n0
        ? '<div class="tide-next-k">Next ' + (n0.type === "H" ? "high" : "low") + "</div>" +
          '<div class="big-read"><span class="big-num">' + esc(clock(n0.t).replace(/\s?(AM|PM)/, "")) + '</span><span class="big-unit">' + esc(/PM/.test(clock(n0.t)) ? "PM" : "AM") + ' ET</span></div>' +
          '<div class="big-label">' + fmt(n0.v, 1) + " ft · in " + esc(inTxt) + "</div>"
        : '<div class="big-label">No upcoming tide in the prediction window.</div>') + "</div>" +
      '<div class="tide-state">' + (isNum(nowH) ? '<div class="ts-row"><span class="ts-k">Predicted now</span><span class="ts-v">' + fmt(nowH, 1) + " ft</span></div>" +
        '<div class="ts-row"><span class="ts-k">Trend</span><span class="ts-v">' + (rising == null ? "—" : rising ? "Rising ↑" : "Falling ↓") + "</span></div>" : "") +
        (prev ? '<div class="ts-row"><span class="ts-k">Last ' + (prev.type === "H" ? "high" : "low") + '</span><span class="ts-v">' + esc(etTime(prev.t, false)) + "</span></div>" : "") +
      "</div></div>" +
      obsStrip(t.observed) +
      '<div class="tide-legend" aria-hidden="true"><span class="lg lg-pred"><i></i>Predicted tide</span>' +
      (t.observed && t.observed.status !== "unavailable" ? '<span class="lg lg-obs"><i></i>Observed water level</span>' : "") +
      '<span class="lg lg-now"><i></i>Now</span></div>' +
      '<div class="tide-chart" id="tide-chart"></div>' +
      '<ol class="tide-list">' + next.slice(0, 4).map(function (e) {
        return '<li class="' + (e.type === "H" ? "is-high" : "is-low") + '"><span class="tl-k">' + (e.type === "H" ? "High" : "Low") + '</span><span class="tl-t">' + esc(etTime(e.t)) + '</span><span class="tl-v">' + fmt(e.v, 1) + " ft</span></li>";
      }).join("") + "</ol>" +
      '<div class="inst-foot">' + predCaption(t) + obsCaption(t.observed, t.station) + "</div>";
    drawTideChart(t);
  }
  function obsStrip(o) {
    if (!o || o.status === "unavailable") {
      return '<div class="tide-obs is-off"><div class="to-cell"><span class="ts-k">Observed water level</span><span class="to-v num-off">—</span>' +
        '<span class="to-s">' + (o && o.lastReport ? "Not reporting since " + esc(etTime(o.lastReport)) : "Not reporting right now") + "</span></div></div>";
    }
    const L = o.latest || {};
    const d = L.diff;
    const diffTxt = !isNum(d) ? "—" : (Math.abs(d) < 0.05 ? "±0.0" : (d > 0 ? "+" : "−") + Math.abs(d).toFixed(1)) + " ft";
    const diffWord = !isNum(d) ? "" : Math.abs(d) < 0.05 ? "about as predicted" : d > 0 ? "higher than predicted" : "lower than predicted";
    return '<div class="tide-obs' + (o.status === "stale" ? " is-stale" : "") + '">' +
      '<div class="to-cell to-obs"><span class="ts-k">Observed</span><span class="to-v">' + numSpan("wlo", L.v, 1) + ' <small>ft</small></span><span class="to-s">' + esc(etTime(L.t)) + (o.status === "stale" ? ' <span class="chip-stale">Stale</span>' : "") + "</span></div>" +
      '<div class="to-cell"><span class="ts-k">Predicted then</span><span class="to-v">' + (isNum(L.predicted) ? fmt(L.predicted, 1) : "—") + ' <small>ft</small></span><span class="to-s">same minute</span></div>' +
      '<div class="to-cell to-diff"><span class="ts-k">Difference</span><span class="to-v">' + esc(diffTxt) + '</span><span class="to-s">' + esc(diffWord) + "</span></div></div>";
  }
  function obsCaption(o, st) {
    st = st || {};
    if (!o) return "";
    return '<details class="src"><summary><span class="src-id">' + esc(st.id || "") + '</span><span class="src-name">Observed water level</span><span class="src-time">' +
      esc(o.status === "unavailable" ? (o.lastReport ? "last report " + etTime(o.lastReport) : "no recent report") : etTime(o.time)) + "</span></summary>" +
      '<div class="src-body"><p>Measured water level at ' + esc(st.name || "the tide station") + " (" + esc(st.id || "") + "), NOAA CO-OPS, every 6 minutes, in feet above MLLW, the same datum as the predictions. " +
      "These are preliminary readings that NOAA has not yet verified. The difference is observed minus predicted at the same minute; wind, pressure, and river flow cause it.</p>" +
      "<p>Marked stale after " + esc(o.staleAfterMin || 30) + " minutes without a new reading; hidden after 6 hours.</p>" +
      '<p class="src-links">' + (o.sourceUrl ? '<a href="' + esc(o.sourceUrl) + '" target="_blank" rel="noopener">NOAA water levels page</a>' : "") +
      (o.dataUrl ? ' · <a href="' + esc(o.dataUrl) + '" target="_blank" rel="noopener">Raw data</a>' : "") + "</p></div></details>";
  }
  function predCaption(t) {
    const st = (t && t.station) || {};
    if (!st.id) return "";
    return '<details class="src"><summary><span class="src-id">' + esc(st.id) + '</span><span class="src-name">' + esc(st.name) + '</span><span class="src-time">Predicted · MLLW</span></summary>' +
      '<div class="src-body"><p class="src-title"><b>' + esc(st.name) + "</b> (" + esc(st.id) + ")</p><p>" + esc(st.network || "") + " · " + esc(st.agency || "") + "</p>" +
      (isNum(st.distanceMi) ? "<p>" + esc(st.distanceMi + " mi " + (st.bearingFromAnchor || "") + " of " + st.anchor + ". " + (st.setting || "")) + ".</p>" : "") +
      "<p>Astronomical tide predictions at 6-minute steps, in feet above mean lower low water (MLLW). These are predictions, not measured water levels; wind and pressure can push the real tide higher or lower. Times are Eastern.</p>" +
      '<p class="src-links">' + (t.sourceUrl ? '<a href="' + esc(t.sourceUrl) + '" target="_blank" rel="noopener">NOAA prediction page</a>' : "") + "</p></div></details>";
  }
  function interp(curve, t) {
    for (let i = 1; i < curve.length; i++) {
      if (curve[i][0] >= t && curve[i - 1][0] <= t) {
        const a = curve[i - 1], b = curve[i];
        return a[1] + ((b[1] - a[1]) * (t - a[0])) / (b[0] - a[0]);
      }
    }
    return null;
  }
  function drawTideChart(t) {
    const box = $("tide-chart");
    if (!box || !t || !t.curve) return;
    const W = Math.max(280, Math.round(box.clientWidth || 600));
    const phone = W < 560;
    const H = phone ? 190 : 230;
    const padL = 8, padR = 8, padT = 34, padB = 30;
    const now = Date.now();
    const t0 = now - (phone ? 4 : 6) * 3600e3, t1 = now + (phone ? 16 : 18) * 3600e3;
    const pts = t.curve.filter(function (p) { return p[0] >= t0 - 6 * 60e3 && p[0] <= t1 + 6 * 60e3; });
    if (pts.length < 10) { box.innerHTML = '<p class="fine">Not enough prediction points for a graph.</p>'; return; }
    const obs = (t.observed && t.observed.status !== "unavailable" && t.observed.points || []).filter(function (p) { return p[0] >= t0 && p[0] <= t1; });
    let vmin = Infinity, vmax = -Infinity;
    pts.concat(obs).forEach(function (p) { vmin = Math.min(vmin, p[1]); vmax = Math.max(vmax, p[1]); });
    const span = Math.max(0.5, vmax - vmin);
    vmin -= span * 0.12; vmax += span * 0.12;
    const x = function (tt) { return padL + ((tt - t0) / (t1 - t0)) * (W - padL - padR); };
    const y = function (v) { return padT + (1 - (v - vmin) / (vmax - vmin)) * (H - padT - padB); };
    let line = "";
    pts.forEach(function (p, i) { line += (i ? " L" : "M") + x(p[0]).toFixed(1) + " " + y(p[1]).toFixed(1); });
    const area = line + " L" + x(pts[pts.length - 1][0]).toFixed(1) + " " + (H - padB) + " L" + x(pts[0][0]).toFixed(1) + " " + (H - padB) + " Z";
    // hour grid every 3 h on the hour (Eastern)
    let grid = "";
    const startHour = Math.ceil(t0 / 3600e3) * 3600e3;
    for (let tt = startHour; tt <= t1; tt += 3600e3) {
      const hr = Number(new Intl.DateTimeFormat("en-US", { timeZone: ET, hour: "numeric", hourCycle: "h23" }).format(new Date(tt)));
      if (hr % 3 !== 0) continue;
      const xx = x(tt);
      const mid = hr === 0;
      grid += '<line x1="' + xx.toFixed(1) + '" x2="' + xx.toFixed(1) + '" y1="' + padT + '" y2="' + (H - padB) + '" class="' + (mid ? "tg-mid" : "tg") + '"/>';
      if (xx > 18 && xx < W - 18) grid += '<text x="' + xx.toFixed(1) + '" y="' + (H - 10) + '" class="tg-t">' + (mid ? wdFmt.format(new Date(tt)) : hourFmt.format(new Date(tt)).replace(" ", "").toLowerCase()) + "</text>";
    }
    let marks = "";
    (t.events || []).forEach(function (e) {
      if (e.t < t0 || e.t > t1) return;
      const xx = x(e.t), yy = y(e.v);
      const high = e.type === "H";
      const ty = high ? yy - 12 : yy + 22;
      const anchor = xx < 40 ? "start" : xx > W - 40 ? "end" : "middle";
      marks += '<circle cx="' + xx.toFixed(1) + '" cy="' + yy.toFixed(1) + '" r="4.5" class="' + (high ? "tm-h" : "tm-l") + '"/>' +
        '<text x="' + xx.toFixed(1) + '" y="' + ty.toFixed(1) + '" text-anchor="' + anchor + '" class="tm-t"><tspan class="tm-k">' + (high ? "H " : "L ") + "</tspan>" +
        esc(clock(e.t).replace(" ", "").toLowerCase()) + " · " + fmt(e.v, 1) + "′</text>";
    });
    let obsSvg = "";
    if (obs.length) {
      let ol = "";
      let prev = null;
      obs.forEach(function (p) {
        // break the line across gaps longer than 20 minutes instead of drawing through missing data
        ol += (prev && p[0] - prev[0] <= 20 * 60e3 ? " L" : "M") + x(p[0]).toFixed(1) + " " + y(p[1]).toFixed(1);
        prev = p;
      });
      obsSvg = '<path d="' + ol + '" class="t-obs-line"/>';
      obs.forEach(function (p, i) {
        if (i % 2 === 0 || i === obs.length - 1) obsSvg += '<circle cx="' + x(p[0]).toFixed(1) + '" cy="' + y(p[1]).toFixed(1) + '" r="' + (i === obs.length - 1 ? 4.2 : 2.1) + '" class="' + (i === obs.length - 1 ? "t-obs-last" : "t-obs-dot") + '"/>';
      });
    }
    const nx = x(now), nh = interp(t.curve, now);
    const ny = isNum(nh) ? y(nh) : null;
    const nowMark = '<line x1="' + nx.toFixed(1) + '" x2="' + nx.toFixed(1) + '" y1="' + (padT - 18) + '" y2="' + (H - padB) + '" class="tn-line"/>' +
      '<text x="' + nx.toFixed(1) + '" y="' + (padT - 22) + '" class="tn-t">Now ' + esc(clock(now).replace(" ", "").toLowerCase()) + "</text>" +
      (ny != null ? '<circle cx="' + nx.toFixed(1) + '" cy="' + ny.toFixed(1) + '" r="9" class="tn-halo"/><circle cx="' + nx.toFixed(1) + '" cy="' + ny.toFixed(1) + '" r="4.5" class="tn-dot"/>' : "");
    const past = '<rect x="' + padL + '" y="' + padT + '" width="' + Math.max(0, nx - padL).toFixed(1) + '" height="' + (H - padT - padB) + '" class="t-past"/>';
    box.innerHTML = '<svg viewBox="0 0 ' + W + " " + H + '" width="' + W + '" height="' + H + '" role="img" aria-label="Predicted tide curve for the next ' + (phone ? 16 : 18) + ' hours' + (obs.length ? ', with observed water level for the past hours' : '') + '">' +
      '<defs><linearGradient id="tideFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0" class="tf-top"/><stop offset="1" class="tf-bot"/></linearGradient>' +
      '<clipPath id="tideReveal"><rect x="0" y="0" width="' + W + '" height="' + H + '" class="reveal-rect"/></clipPath></defs>' +
      past + grid +
      '<line x1="' + padL + '" x2="' + (W - padR) + '" y1="' + (H - padB) + '" y2="' + (H - padB) + '" class="t-base"/>' +
      '<g clip-path="url(#tideReveal)"><path d="' + area + '" fill="url(#tideFill)" class="t-area"/><path d="' + line + '" class="t-line"/></g>' +
      obsSvg + marks + nowMark + "</svg>";
    const rr = box.querySelector(".reveal-rect");
    if (rr && !reduced() && !box.dataset.revealed) {
      box.dataset.revealed = "1";
      rr.setAttribute("width", "0");
      requestAnimationFrame(function () { rr.style.transition = "width 1.1s cubic-bezier(.2,.7,.2,1)"; rr.setAttribute("width", String(W)); rr.style.width = W + "px"; });
    }
  }

  // ---------- secondary ----------
  function renderWater(r, rOff) {
    const el = $("i-water");
    const v = val(r), o = val(rOff);
    stateClass(el, (r && r.status !== "unavailable") ? r : rOff);
    function col(key, label, rr, vv, note) {
      return '<div class="wcol' + (rr && rr.status === "stale" ? " is-stale" : "") + (rr && rr.status === "unavailable" ? " is-off" : "") + '">' +
        '<div class="sub-k">' + esc(label) + "</div>" +
        '<div class="mid-read"><span class="mid-num">' + numSpan(key, vv.f, 0) + '</span><span class="mid-unit">°F</span></div>' +
        '<div class="mid-label">' + esc((rr && rr.role) || "") + (isNum(vv.c) ? " · " + fmt(vv.c, 1) + " °C" : "") + " " + statusChip(rr) + "</div>" +
        '<div class="inst-foot">' + srcCaption(rr, { note: note }) + "</div></div>";
    }
    el.innerHTML = head("Water temp", null, "observed") +
      '<div class="wcols">' + col("wt", "Inshore", r, v, "") + col("wto", "Offshore", rOff, o, "Converted from °C.") + "</div>";
    tweenAll(el);
  }
  function renderAir(r) {
    const el = $("i-air");
    const v = val(r);
    stateClass(el, r);
    el.innerHTML = head("Air temp", r) +
      '<div class="mid-read"><span class="mid-num">' + numSpan("at", v.f, 0) + '</span><span class="mid-unit">°F</span></div>' +
      '<div class="mid-label">' + esc((r && r.role) || "") + (isNum(v.c) ? " · " + fmt(v.c, 1) + " °C" : "") + "</div>" +
      '<div class="inst-foot">' + srcCaption(r) + "</div>";
    tweenAll(el);
  }
  function baroSvg(inHg) {
    const lo = 29.0, hi = 31.0;
    const C = 60, R = 46;
    function arcPt(frac, rr) { return polar(C, rr, -110 + 220 * frac); }
    const a0 = arcPt(0, R), a1 = arcPt(1, R);
    let ticks = "";
    for (let i = 0; i <= 20; i++) {
      const f = i / 20, p0 = arcPt(f, R - (i % 5 === 0 ? 9 : 5)), p1 = arcPt(f, R);
      ticks += '<line x1="' + p0[0].toFixed(1) + '" y1="' + p0[1].toFixed(1) + '" x2="' + p1[0].toFixed(1) + '" y2="' + p1[1].toFixed(1) + '" class="' + (i % 5 === 0 ? "tk-major" : "tk-minor") + '"/>';
    }
    const has = isNum(inHg);
    const f = has ? Math.max(0, Math.min(1, (inHg - lo) / (hi - lo))) : 0.5;
    const tip = arcPt(f, R - 12);
    return '<svg class="baro" viewBox="0 0 120 96" aria-hidden="true"><path d="M' + a0[0].toFixed(1) + " " + a0[1].toFixed(1) + " A" + R + " " + R + " 0 1 1 " + a1[0].toFixed(1) + " " + a1[1].toFixed(1) + '" class="baro-arc"/>' + ticks +
      (has ? '<line x1="60" y1="60" x2="' + tip[0].toFixed(1) + '" y2="' + tip[1].toFixed(1) + '" class="baro-needle"/>' : "") + '<circle cx="60" cy="60" r="3.5" class="baro-hub"/>' +
      '<text x="22" y="92" class="baro-t">29</text><text x="60" y="10" class="baro-t">30</text><text x="98" y="92" class="baro-t">31</text></svg>';
  }
  function renderPressure(r) {
    const el = $("i-pres");
    const v = val(r);
    stateClass(el, r);
    const arrow = v.trend === "rising" ? "↑" : v.trend === "falling" ? "↓" : v.trend === "steady" ? "→" : "";
    el.innerHTML = head("Barometer", r) +
      '<div class="baro-row">' + baroSvg(v.inHg) + '<div><div class="mid-read"><span class="mid-num">' + numSpan("pr", v.inHg, 2) + '</span><span class="mid-unit">inHg</span></div>' +
      '<div class="mid-label">' + (isNum(v.hPa) ? fmt(v.hPa, 1) + " hPa" : "") + "</div>" +
      '<div class="trend trend-' + esc(v.trend || "none") + '">' + (v.trend ? arrow + " " + esc(v.trend[0].toUpperCase() + v.trend.slice(1)) + (isNum(v.change3hHPa) ? " · " + (v.change3hHPa > 0 ? "+" : "") + fmt(v.change3hHPa, 1) + " hPa / 3 h" : "") : "Trend not available") + "</div></div></div>" +
      '<div class="inst-foot">' + srcCaption(r, { note: (v.trendBasis ? "Trend: " + v.trendBasis + ". Rising or falling means a change of 1 hPa or more in 3 hours. " : "") + "Converted from hPa (× 0.02953)." }) + "</div>";
    tweenAll(el);
  }
  function renderHarbor(r) {
    const el = $("i-harbor");
    if (!el) return;
    const v = val(r);
    stateClass(el, r);
    el.innerHTML = '<div class="harbor-row">' +
      (isNum(v.dirDeg) ? '<svg class="mini-compass" viewBox="0 0 60 60" aria-hidden="true"><circle cx="30" cy="30" r="26" class="mc-ring"/><text x="30" y="13" class="mc-n">N</text>' +
        '<g style="transform: rotate(' + v.dirDeg + 'deg); transform-origin: 30px 30px"><path d="M30 5 L35.5 17 L30 14.5 L24.5 17 Z" class="mc-ptr"/><line x1="30" y1="16" x2="30" y2="50" class="mc-tail"/></g></svg>' : '<span class="mini-compass"></span>') +
      '<div class="harbor-txt"><div class="sub-k">' + esc((r && r.role) || "Inlet wind") + "</div>" +
      '<div class="harbor-v"><span class="sub-v">' + (isNum(v.speedKt) ? numSpan("hw", Math.round(v.speedKt), 0) + " kt" : "—") + "</span>" +
      '<span class="harbor-d">' + (isNum(v.dirDeg) ? "from " + esc(v.dirCompass) + " " + fmt(v.dirDeg) + "°" : "") + (isNum(v.gustKt) ? " · gust " + fmt(v.gustKt) + " kt" : "") + "</span>" + statusChip(r) + "</div></div></div>" +
      '<div class="inst-foot">' + srcCaption(r, { note: "Wind at the harbor station is often lighter than at the cape. Reported in knots." }) + "</div>";
    tweenAll(el);
  }
  function renderMarine(m) {
    const el = $("i-marine");
    el.classList.remove("is-loading", "is-off");
    if (!m || m.status !== "ok") {
      el.classList.add("is-off");
      el.innerHTML = head("Marine forecast", null, "forecast") + '<p class="mf-text">The NWS marine forecast is unavailable right now.</p>';
      return;
    }
    el.innerHTML = head("Marine forecast", null, "forecast") +
      '<p class="mf-zone"><b>' + esc(m.zone) + "</b> · " + esc(m.zoneName) + "</p>" +
      '<div class="mf-periods">' + (m.periods || []).slice(0, 2).map(function (p) {
        return '<div class="mf-p"><div class="mf-name">' + esc(p.name) + '</div><p class="mf-text">' + esc(p.text) + "</p></div>";
      }).join("") + "</div>" +
      '<div class="inst-foot"><details class="src"><summary><span class="src-id">' + esc(m.zone) + '</span><span class="src-name">' + esc(m.office) + '</span><span class="src-time">Issued ' + esc(etTime(m.updated)) + "</span></summary>" +
      '<div class="src-body"><p>Official NWS coastal waters forecast for zone ' + esc(m.zone) + " (" + esc(m.zoneName) + "). Shown as written by the National Weather Service.</p>" +
      '<p class="src-links"><a href="' + esc(m.sourceUrl) + '" target="_blank" rel="noopener">Full forecast at weather.gov</a></p></div></details></div>';
  }
  function renderAlerts(a, m) {
    const box = $("dash-alert");
    const items = (a && a.items) || [];
    if (!items.length) {
      box.hidden = false;
      box.className = "dash-alert is-clear";
      // Same three-part layout as an active alert, so the box keeps its height.
      box.innerHTML = (a && a.status === "ok"
        ? '<div class="al-item"><span class="al-dot"></span><span class="al-ev">No NWS alerts right now</span><span class="al-meta">No watches, warnings, or advisories for ' + esc((a.zones || []).join(", ")) + ".</span></div>"
        : '<div class="al-item"><span class="al-dot"></span><span class="al-ev">Alerts unavailable</span><span class="al-meta">Could not check NWS alerts. See weather.gov before heading out.</span></div>') +
        '<a class="al-link" href="https://www.weather.gov/mhx/" target="_blank" rel="noopener">NWS details</a>';
      return;
    }
    box.hidden = false;
    box.className = "dash-alert is-active";
    box.innerHTML = items.map(function (it) {
      return '<div class="al-item"><span class="al-dot"></span><span class="al-ev">' + esc(it.event) + "</span>" +
        '<span class="al-meta">' + (it.ends ? "until " + esc(etTime(it.ends)) : "") + (it.areas ? " · " + esc(it.areas) : "") + "</span></div>";
    }).join("") + '<a class="al-link" href="https://www.weather.gov/mhx/" target="_blank" rel="noopener">NWS details</a>';
  }

  // ---------- seven-day forecast ----------
  // Land point forecast (NWS gridpoint) grouped into days, with the NWS
  // coastal waters (marine zone) forecast for the same day shown separately
  // and labelled as the marine zone. Values are only those NWS publishes;
  // the only derived bits are knots (from NWS mph) and seas/wind phrases
  // quoted from the marine text.
  const WD = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
  const dayKeyFmt = new Intl.DateTimeFormat("en-CA", { timeZone: "America/New_York", year: "numeric", month: "2-digit", day: "2-digit" });
  const fcWdFmt = new Intl.DateTimeFormat("en-US", { timeZone: "America/New_York", weekday: "short" });
  const mdFmt = new Intl.DateTimeFormat("en-US", { timeZone: "America/New_York", month: "short", day: "numeric" });
  function fcDayKey(t) { return dayKeyFmt.format(toDate(t)); }

  function skyKind(txt) {
    const t = (txt || "").toLowerCase();
    if (/thunder|t-storm/.test(t)) return "storm";
    if (/snow|sleet|flurr|ice|freezing/.test(t)) return "snow";
    if (/rain|shower|drizzle/.test(t)) return "rain";
    if (/fog|haze|smoke|mist/.test(t)) return "fog";
    if (/partly sunny|mostly cloudy|partly cloudy/.test(t)) return /mostly cloudy/.test(t) ? "cloud" : "part";
    if (/cloudy|overcast/.test(t)) return "cloud";
    if (/sunny|clear|fair/.test(t)) return "clear";
    return "cloud";
  }
  function skyIcon(kind, night) {
    const sun = night
      ? '<path class="sk-moon" d="M27 9a10 10 0 1 0 8 15A11 11 0 0 1 27 9z"/>'
      : '<circle class="sk-sun" cx="22" cy="18" r="7"/><g class="sk-rays">' + [0, 45, 90, 135, 180, 225, 270, 315].map(function (a) {
          const r = (a * Math.PI) / 180;
          return '<line x1="' + (22 + Math.cos(r) * 10.5).toFixed(1) + '" y1="' + (18 + Math.sin(r) * 10.5).toFixed(1) + '" x2="' + (22 + Math.cos(r) * 13.5).toFixed(1) + '" y2="' + (18 + Math.sin(r) * 13.5).toFixed(1) + '"/>';
        }).join("") + "</g>";
    const cloud = '<path class="sk-cloud" d="M14 34h20a7 7 0 0 0 0-14 9.5 9.5 0 0 0-18 2.4A5.8 5.8 0 0 0 14 34z"/>';
    let body = "";
    if (kind === "clear") body = sun;
    else if (kind === "part") body = sun + cloud;
    else if (kind === "cloud") body = cloud;
    else if (kind === "rain") body = cloud + '<g class="sk-rain"><line x1="18" y1="37" x2="16" y2="42"/><line x1="25" y1="37" x2="23" y2="42"/><line x1="32" y1="37" x2="30" y2="42"/></g>';
    else if (kind === "storm") body = cloud + '<path class="sk-bolt" d="M25 34l-4 6h4l-2 6 6-8h-4l2-4z"/>';
    else if (kind === "snow") body = cloud + '<g class="sk-snow"><circle cx="18" cy="40" r="1.4"/><circle cx="25" cy="42" r="1.4"/><circle cx="32" cy="40" r="1.4"/></g>';
    else if (kind === "fog") body = '<g class="sk-fog"><line x1="9" y1="20" x2="37" y2="20"/><line x1="12" y1="26" x2="40" y2="26"/><line x1="9" y1="32" x2="34" y2="32"/></g>';
    return '<svg class="sky sky-' + kind + '" viewBox="0 0 46 46" aria-hidden="true">' + body + "</svg>";
  }

  // Marine periods carry names only ("Tonight", "Fri", "Fri Night", "Sat").
  // Map each to the calendar day it belongs to; unknown names are skipped.
  function marineByDay(m, firstDate) {
    const out = {};
    if (!m || m.status !== "ok") return out;
    const base = toDate(firstDate || Date.now());
    const todayWd = WD.indexOf(fcWdFmt.format(base));
    (m.periods || []).forEach(function (p) {
      const nm = (p.name || "").trim();
      let off = null;
      if (/^(today|this afternoon|tonight|rest of today|rest of tonight|this evening|overnight)$/i.test(nm)) off = 0;
      else {
        const wd = WD.indexOf(nm.slice(0, 3).replace(/^(\w)(\w+)/, function (_, a, b) { return a.toUpperCase() + b.toLowerCase(); }));
        if (wd >= 0 && todayWd >= 0) off = (wd - todayWd + 7) % 7;
      }
      if (off == null) return;
      const k = fcDayKey(base.getTime() + off * 86400000);
      (out[k] = out[k] || []).push(p);
    });
    return out;
  }
  function marineGist(text) {
    const t = text || "";
    const wind = (t.match(/\b([NESW]{1,3}|[Vv]ariable) winds? [^.]*?\d+(?: to \d+)? kt/) || [])[0];
    const seas = (t.match(/\bSeas [^.]*?\d+(?: to \d+)? ft(?: or less)?/) || [])[0];
    return { wind: wind || null, seas: seas || null };
  }

  function renderForecast(f, region, m) {
    const h = $("fc-place");
    if (h) h.textContent = (f && f.label) || (region && region.name) || "";
    const strip = $("forecast-strip");
    const meta = $("fc-meta");
    const foot = $("fc-foot");
    if (!strip) return;
    if (!f || f.status !== "ok") {
      strip.innerHTML = '<p class="fc-off">The NWS forecast is unavailable right now. See <a href="https://www.weather.gov/mhx/" target="_blank" rel="noopener">weather.gov/mhx</a>.</p>';
      if (meta) meta.textContent = "";
      if (foot) foot.textContent = "";
      return;
    }
    if (meta) meta.textContent = "Land forecast for " + f.label + " from " + f.office + ", updated " + etTime(f.updated) + ". Wind in knots (converted from NWS mph). Tap a day for the full text.";
    // group periods into calendar days
    const days = [];
    const byKey = {};
    (f.periods || []).forEach(function (p) {
      const k = fcDayKey(p.start);
      if (!byKey[k]) { byKey[k] = { key: k, start: p.start, day: null, night: null }; days.push(byKey[k]); }
      if (p.isDaytime) byKey[k].day = p; else byKey[k].night = p;
    });
    const mDays = marineByDay(m, days[0] && days[0].start);
    const temps = [];
    days.forEach(function (d) { [d.day, d.night].forEach(function (p) { if (p && isNum(p.tempF)) temps.push(p.tempF); }); });
    const tMin = Math.min.apply(null, temps), tMax = Math.max.apply(null, temps);
    const span = Math.max(1, tMax - tMin);
    const todayK = fcDayKey(Date.now());

    strip.innerHTML = days.slice(0, 7).map(function (d, i) {
      const lead = d.day || d.night;
      const hi = d.day && isNum(d.day.tempF) ? d.day.tempF : null;
      const lo = d.night && isNum(d.night.tempF) ? d.night.tempF : null;
      const name = d.key === todayK ? (d.day ? "Today" : "Tonight") : fcWdFmt.format(toDate(d.start));
      const kind = skyKind(lead.short);
      const pops = [d.day && d.day.pop, d.night && d.night.pop].filter(isNum);
      const pop = pops.length ? Math.max.apply(null, pops) : null;
      const wl = lead.windKt ? (lead.windDir ? lead.windDir + " " : "") + lead.windKt : "—";
      // temperature bar positioned on the week's range
      const a = isNum(lo) ? lo : hi, b = isNum(hi) ? hi : lo;
      const bar = isNum(a) ? '<span class="fc-bar" aria-hidden="true"><i style="left:' + (((a - tMin) / span) * 100).toFixed(1) + "%;right:" + (100 - ((b - tMin) / span) * 100).toFixed(1) + '%"></i></span>' : "";
      const mp = mDays[d.key] || [];
      const gist = mp.length ? marineGist(mp[0].text) : null;
      const zone = m && m.zone ? m.zone : "marine zone";
      const marineChip = gist && (gist.seas || gist.wind)
        ? '<span class="fc-marine" title="From the NWS marine zone forecast for ' + esc(zone) + '"><b>Marine</b> ' + esc(gist.seas || gist.wind) + "</span>"
        : "";
      const tempTxt = isNum(hi)
        ? '<span class="fc-hi" aria-label="High ' + hi + '°F">' + hi + "°</span>" + (isNum(lo) ? '<span class="fc-lo" aria-label="Low ' + lo + '°F">' + lo + "°</span>" : '<span class="fc-lo fc-na">—</span>')
        : (isNum(lo) ? '<span class="fc-k fc-lowk">Low</span><span class="fc-hi" aria-label="Low ' + lo + '°F">' + lo + "°</span>" : '<span class="fc-hi fc-na">—</span><span></span>');
      const body =
        '<div class="fc-body">' +
        '<div class="fc-col"><h3>Land · ' + esc(f.label) + "</h3>" +
        (d.day ? '<p><b>' + esc(d.day.name) + ".</b> " + esc(d.day.detail || d.day.short || "") + "</p>" : "") +
        (d.night ? '<p><b>' + esc(d.night.name) + ".</b> " + esc(d.night.detail || d.night.short || "") + "</p>" : "") +
        "</div>" +
        (mp.length
          ? '<div class="fc-col fc-col-m"><h3>Marine zone ' + esc(zone) + (m.zoneName ? " · " + esc(m.zoneName) : "") + "</h3>" +
            mp.map(function (q) { return "<p><b>" + esc(q.name) + ".</b> " + esc(q.text) + "</p>"; }).join("") + "</div>"
          : (m && m.status === "ok" ? '<div class="fc-col fc-col-m"><h3>Marine zone ' + esc(zone) + '</h3><p class="fc-na">The NWS marine zone forecast does not reach this day.</p></div>' : "")) +
        "</div>";
      return '<details class="fc-day' + (d.day ? "" : " is-night") + '"' + (i === 0 && window.innerWidth > 600 ? " open" : "") + ">" +
        "<summary>" +
        '<span class="fc-when"><span class="fc-name">' + esc(name) + '</span><span class="fc-date">' + esc(mdFmt.format(toDate(d.start))) + "</span></span>" +
        skyIcon(kind, !d.day) +
        '<span class="fc-short">' + esc(lead.short || "") + (marineChip ? "<br>" + marineChip : "") + "</span>" +
        '<span class="fc-temps">' + tempTxt + bar + "</span>" +
        '<span class="fc-wind"><span class="fc-k">Wind</span>' + esc(wl) + "</span>" +
        '<span class="fc-pop' + (pop >= 30 ? " is-wet" : "") + '"><span class="fc-k">Rain</span>' + (isNum(pop) ? pop + "%" : "—") + "</span>" +
        '<span class="fc-chev" aria-hidden="true"></span>' +
        "</summary>" + body + "</details>";
    }).join("");
    if (foot) {
      foot.innerHTML = "The land forecast is for the town, not the water offshore. Marine lines come from the NWS coastal waters forecast" +
        (m && m.zone ? " for zone " + esc(m.zone) : "") + (m && m.updated ? ", issued " + esc(etTime(m.updated)) : "") +
        ', and cover about five days. <a href="' + esc(f.sourceUrl) + '" target="_blank" rel="noopener">Point forecast</a>' +
        (m && m.sourceUrl ? ' · <a href="' + esc(m.sourceUrl) + '" target="_blank" rel="noopener">Marine zone forecast</a>' : "") + ".";
    }
  }

  // ---------- sources table ----------
  function renderSources(d) {
    const box = $("sources-table");
    if (!box) return;
    const R = d.readings || {};
    const rows = [
      ["Wind", R.wind], ["Seas", R.seas], ["Swell", R.swell], ["Water temp (inshore)", R.waterTemp],
      ["Water temp (offshore)", R.waterTempOffshore], ["Air temp", R.airTemp], ["Barometer", R.pressure], ["Inlet wind", R.harborWind],
    ];
    let html = '<table><thead><tr><th>Reading</th><th>Type</th><th>Station</th><th>Where</th><th>Time</th></tr></thead><tbody>';
    rows.forEach(function (row) {
      const r = row[1] || {};
      const st = r.station || {};
      html += "<tr><td>" + esc(row[0]) + "</td><td>" + kindTag(r.kind || "observed") + "</td><td>" + (st.url ? '<a href="' + esc(st.url) + '" target="_blank" rel="noopener">' : "") + esc(st.name || "—") + " (" + esc(st.id || "—") + ")" + (st.url ? "</a>" : "") +
        "</td><td>" + (isNum(st.distanceMi) ? esc(st.distanceMi + " mi " + st.bearingFromAnchor + " of " + st.anchor) : "") + "</td><td>" +
        (r.status === "unavailable" ? "Not reporting" : esc(etTime(r.time)) + (r.status === "stale" ? " (stale)" : "")) + "</td></tr>";
    });
    const t = d.tides || {}, f = d.forecast || {}, m = d.marine || {};
    html += "<tr><td>Tide</td><td>" + kindTag("predicted") + "</td><td>" + esc((t.station || {}).name || "—") + " (" + esc((t.station || {}).id || "") + ")</td><td>" + (isNum((t.station || {}).distanceMi) ? esc(t.station.distanceMi + " mi " + t.station.bearingFromAnchor + " of " + t.station.anchor) : "") + "</td><td>NOAA CO-OPS predictions" + (t.observed && t.observed.status !== "unavailable" ? " and observed water level (preliminary)" : "") + "</td></tr>";
    html += "<tr><td>Marine forecast</td><td>" + kindTag("forecast") + "</td><td>NWS zone " + esc(m.zone || "") + "</td><td>" + esc(m.zoneName || "") + "</td><td>" + (m.updated ? "Issued " + esc(etTime(m.updated)) : "—") + "</td></tr>";
    html += "<tr><td>7-day forecast</td><td>" + kindTag("forecast") + "</td><td>" + esc(f.office || "NWS") + "</td><td>" + esc(f.label || "") + " point forecast</td><td>" + (f.updated ? "Updated " + esc(etTime(f.updated)) : "—") + "</td></tr>";
    html += "</tbody></table>";
    box.innerHTML = html + '<p class="fine">' + esc(d.staleRule || "") + " Readings come from different stations, so they describe different places, from offshore buoys to shore and harbor stations. Data are from NOAA and the National Weather Service; The Coastal Brief is not affiliated with or endorsed by NOAA.</p>";
  }

  // ---------- header bits ----------
  function renderHeaderBits(d) {
    const badge = $("freshness-badge");
    const w = d.readings && d.readings.wind;
    if (badge) {
      badge.textContent = "Updated " + etTime(d.generatedAt);
      badge.classList.toggle("amber", !!(w && w.status !== "ok"));
    }
    const loc = $("loc-line");
    if (loc) loc.textContent = d.region.name + " · " + (d.region.area || "") + ". Location is not requested from your browser.";
    const sub = $("dash-sub");
    if (sub) sub.textContent = d.region.area || "";
    const mini = { wind: null, wtmp: null, tide: null };
    const wv = val(w);
    mini.wind = isNum(wv.speedKt) ? (wv.dirCompass ? wv.dirCompass + " " : "") + Math.round(wv.speedKt) + " kt" : "—";
    const wt = val(d.readings.waterTemp);
    mini.wtmp = isNum(wt.f) ? Math.round(wt.f) + "°F" : "—";
    const nxt = ((d.tides && d.tides.events) || []).filter(function (e) { return e.t > Date.now(); })[0];
    mini.tide = nxt ? (nxt.type === "H" ? "Hi " : "Lo ") + clock(nxt.t).replace(" PM", "p").replace(" AM", "a") : "—";
    if ($("mini-wind")) $("mini-wind").textContent = mini.wind;
    if ($("mini-wtmp")) $("mini-wtmp").textContent = mini.wtmp;
    if ($("mini-tide")) $("mini-tide").textContent = mini.tide;
  }

  // Phone summary: the four readings people check first, so the first screen
  // answers "what is it doing out there". Each cell jumps to its instrument.
  function renderGlance(d) {
    const box = $("glance-strip");
    if (!box) return;
    const R = d.readings || {};
    function cell(id, k, v, s, r) {
      const stale = r && r.status === "stale";
      const off = !r || r.status === "unavailable" || v === "—";
      return '<a class="gs-cell' + (stale ? " is-stale" : "") + (off ? " is-off" : "") + '" href="#' + id + '">' +
        '<span class="gs-k">' + esc(k) + (stale ? ' <span class="gs-stale">stale</span>' : "") + "</span>" +
        '<span class="gs-v">' + esc(off ? "—" : v) + "</span>" +
        '<span class="gs-s">' + esc(off ? "not reporting" : s) + "</span></a>";
    }
    const w = val(R.wind), se = val(R.seas), wt = val(R.waterTemp);
    const ev = ((d.tides && d.tides.events) || []).filter(function (e) { return e.t > Date.now(); })[0];
    const tideR = d.tides && d.tides.status === "ok" ? { status: "ok" } : null;
    box.innerHTML =
      cell("i-wind", "Wind", isNum(w.speedKt) ? (w.dirCompass ? w.dirCompass + " " : "") + Math.round(w.speedKt) + " kt" : "—",
        isNum(w.gustKt) ? "gust " + Math.round(w.gustKt) + " kt" : "observed", R.wind) +
      cell("i-seas", "Seas", isNum(se.heightFt) ? fmt(se.heightFt, 1) + " ft" : "—",
        isNum(se.dominantPeriodS) ? Math.round(se.dominantPeriodS) + " s" + (se.meanDirCompass ? " · " + se.meanDirCompass : "") : "observed", R.seas) +
      cell("i-water", "Water", isNum(wt.f) ? Math.round(wt.f) + "°F" : "—", "inshore station", R.waterTemp) +
      cell("i-tide", ev ? (ev.type === "H" ? "Next high" : "Next low") : "Tide", ev ? clock(ev.t) : "—",
        ev && isNum(ev.v) ? fmt(ev.v, 1) + " ft predicted" : "predicted", ev ? tideR : null);
    box.hidden = false;
    if (!state.glanceIO && window.IntersectionObserver) {
      state.glanceIO = new IntersectionObserver(function (ents) {
        ents.forEach(function (e) { document.body.classList.toggle("glance-on-screen", e.isIntersecting); });
      });
      state.glanceIO.observe(box);
    }
  }

  function render(d) {
    state.data = d;
    renderGlance(d);
    const R = d.readings || {};
    renderAlerts(d.alerts, d.marine);
    renderWind(R.wind);
    tweenAll($("i-wind"));
    renderSeas(R.seas);
    renderSwell(R.swell);
    renderTide(d.tides);
    renderWater(R.waterTemp, R.waterTempOffshore);
    renderAir(R.airTemp);
    renderPressure(R.pressure);
    renderHarbor(R.harborWind);
    tweenAll($("i-wind"));
    renderMarine(d.marine);
    renderForecast(d.forecast, d.region, d.marine);
    renderSources(d);
    renderHeaderBits(d);
    $("conditions").classList.remove("is-booting");
    document.dispatchEvent(new CustomEvent("cb:conditions", { detail: d }));
  }

  function showError(msg) {
    ["i-wind", "i-seas", "i-swell", "i-tide", "i-water", "i-air", "i-pres", "i-marine"].forEach(function (id) {
      const el = $(id);
      if (el && el.classList.contains("is-loading")) {
        el.classList.remove("is-loading");
        el.classList.add("is-off");
        el.innerHTML = '<header class="inst-h"><h3 class="inst-k">' + esc(el.getAttribute("data-title") || "") + '</h3></header><p class="mid-label">' + esc(msg) + "</p>";
      }
    });
    const badge = $("freshness-badge");
    if (badge) { badge.textContent = "Readings unavailable"; badge.classList.add("amber"); }
    const al = $("dash-alert");
    if (al && al.classList.contains("is-pending")) {
      al.className = "dash-alert is-clear";
      al.innerHTML = '<div class="al-item"><span class="al-dot"></span><span class="al-ev">Alerts unavailable</span><span class="al-meta">Could not check NWS alerts. See weather.gov before heading out.</span></div><a class="al-link" href="https://www.weather.gov/mhx/" target="_blank" rel="noopener">NWS details</a>';
    }
    const gs = $("glance-strip");
    if (gs) gs.querySelectorAll(".gs-cell.is-loading").forEach(function (c) {
      c.classList.remove("is-loading"); c.classList.add("is-off");
      const sub = c.querySelector(".gs-s"); if (sub) sub.textContent = "unavailable";
    });
  }

  function load(regionId, quiet) {
    if (state.loading) return Promise.resolve();
    state.loading = true;
    const dash = $("conditions");
    if (!quiet) dash.classList.add("is-switching");
    return fetch("/api/conditions?region=" + encodeURIComponent(regionId))
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (!d || !d.ok) throw new Error((d && d.error) || "Conditions unavailable");
        render(d);
      })
      .catch(function (e) { showError("Could not load live readings right now. Nothing is shown in their place."); })
      .finally(function () { state.loading = false; dash.classList.remove("is-switching"); });
  }

  function pickInitial(def) {
    let id = null;
    try { id = new URLSearchParams(location.search).get("region"); } catch (e) {}
    if (!id) { try { id = localStorage.getItem(REGION_STORE); } catch (e) {} }
    const ok = state.regions.some(function (r) { return r.id === id; });
    return ok ? id : def;
  }
  function setRegion(id, persist) {
    if (id === state.regionId) return;
    state.regionId = id;
    state.windAngle = state.windAngle; // keep needle continuity across regions
    if (persist) {
      try { localStorage.setItem(REGION_STORE, id); } catch (e) {}
      try {
        const u = new URL(location.href);
        u.searchParams.set("region", id);
        history.replaceState(null, "", u.toString());
      } catch (e) {}
    }
    const sel = $("region-select");
    if (sel && sel.value !== id) sel.value = id;
    if (window.CoastalRegionNav) CoastalRegionNav.setCurrent(id);
    if (window.CoastalBriefLink) CoastalBriefLink.sync(id);
    const tc = $("tide-chart");
    if (tc) delete tc.dataset.revealed;
    load(id, false);
  }

  const FRESHWATER = [
    { id: "falls-lake", name: "Falls Lake" },
    { id: "jordan-lake", name: "Jordan Lake" },
    { id: "neuse-river", name: "Neuse River" }
  ];
  function isFreshwater(id) {
    return FRESHWATER.some(function (r) { return r.id === id; });
  }

  function init() {
    const sel = $("region-select");
    fetch("/api/regions").then(function (r) { return r.json(); }).then(function (cfg) {
      state.regions = (cfg && cfg.regions) || [];
      if (!state.regions.length) throw new Error("no regions");
      // Saltwater regions stay on this dashboard. Freshwater options go to
      // /lake?region=, same as the compact select on main. The header picker
      // is bound to that same list (not /api/regions, which stays saltwater).
      let urlRegion = null;
      try { urlRegion = new URLSearchParams(location.search).get("region"); } catch (e) {}
      if (isFreshwater(urlRegion)) {
        location.replace("/lake?region=" + encodeURIComponent(urlRegion));
        return;
      }
      sel.innerHTML = '<optgroup label="Saltwater">' + state.regions.filter(function (r) { return (r.waterType || "saltwater") === "saltwater"; })
        .map(function (r) { return '<option value="' + esc(r.id) + '">' + esc(r.name) + "</option>"; }).join("") +
        '</optgroup><optgroup label="Freshwater">' + FRESHWATER.map(function (r) {
          return '<option value="' + esc(r.id) + '">' + esc(r.name) + "</option>";
        }).join("") + "</optgroup>";
      sel.disabled = state.regions.length < 1;
      sel.addEventListener("change", function () {
        if (isFreshwater(sel.value)) {
          location.href = "/lake?region=" + encodeURIComponent(sel.value);
          return;
        }
        setRegion(sel.value, true);
      });
      var initial = pickInitial(cfg.default);
      if (window.CoastalRegionNav) {
        var navCfg = Object.assign({}, cfg, {
          line: (cfg && cfg.line) || "From the rivers to the sounds to the sea",
          freshwater: FRESHWATER.map(function (r) {
            return { id: r.id, name: r.name, waterType: "freshwater", available: true, comingSoon: false, href: "/lake?region=" + r.id };
          })
        });
        CoastalRegionNav.bind(document.getElementById("region-nav"), navCfg, {
          currentId: initial,
          onSelect: function (id) { setRegion(id, true); }
        });
      }
      setRegion(initial, false);

    }).catch(function () { showError("Could not load the region list."); });
    let rt = null;
    window.addEventListener("resize", function () {
      clearTimeout(rt);
      rt = setTimeout(function () { if (state.data) drawTideChart(state.data.tides); }, 150);
    });
    state.timer = setInterval(function () {
      if (document.visibilityState === "visible" && state.regionId) load(state.regionId, true);
    }, REFRESH_MS);
    // Coming back to a tab (or unlocking a phone) after a while: refresh now
    // rather than showing old readings until the next timer tick.
    document.addEventListener("visibilitychange", function () {
      if (document.visibilityState !== "visible" || !state.regionId || !state.data) return;
      const age = Date.now() - new Date(state.data.generatedAt).getTime();
      if (!(age < REFRESH_MS)) load(state.regionId, true);
    });
    // Pause the gentle wave motion when the dashboard is off screen.
    if ("IntersectionObserver" in window) {
      new IntersectionObserver(function (ents) {
        ents.forEach(function (e) { $("conditions").classList.toggle("is-offscreen", !e.isIntersecting); });
      }).observe($("conditions"));
    }
  }
  window.CoastalDash = { region: function () { return state.data && state.data.region; }, data: function () { return state.data; } };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
