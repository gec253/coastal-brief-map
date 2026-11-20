/* /radar playback state machine + Eastern Time formatting. No DOM: runs in the browser (CBRadarPlayer)
   and in Node for tests. OBSERVED and FORECAST frames are kept in separate lists; forecast frames are
   only ever appended after the last observed frame, and only when the user turns them on. */
(function (root, factory) {
  const P = factory();
  if (typeof module === "object" && module.exports) module.exports = P; else root.CBRadarPlayer = P;
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";
  const HOLD_MS = 500, LAST_HOLD_MS = 1600, WINDOW_S = 2 * 3600;

  function norm(frames) {
    const out = [];
    (frames || []).forEach(function (f) {
      if (!f || !/^\d{12}$/.test(String(f.time || ""))) return;
      const e = Number(f.time_epoch);
      out.push({ time: String(f.time), epoch: isFinite(e) && e > 0 ? e : epochFromCode(String(f.time)), type: f.type === "nowcast" ? "forecast" : "observed" });
    });
    out.sort(function (a, b) { return a.epoch - b.epoch; });
    return out;
  }
  function epochFromCode(c) {   // yyyyMMddHHmm, UTC (WeatherAPI tile time code)
    return Date.UTC(+c.slice(0, 4), +c.slice(4, 6) - 1, +c.slice(6, 8), +c.slice(8, 10), +c.slice(10, 12)) / 1000;
  }

  function create(frames, opts) {
    opts = opts || {};
    const all = norm(frames);
    let observed, forecast;
    function split(all) {
      observed = all.filter(function (f) { return f.type === "observed"; });
      const latest = observed.length ? observed[observed.length - 1].epoch : 0;
      observed = observed.filter(function (f) { return f.epoch >= latest - WINDOW_S; });   // two-hour observed window
      forecast = all.filter(function (f) { return f.type === "forecast" && f.epoch > latest; });
    }
    split(all);
    const s = { status: observed.length ? "paused" : "empty", index: Math.max(0, observed.length - 1), forecastOn: false, wasPlaying: false };
    const listeners = [];
    function list() { return s.forecastOn ? observed.concat(forecast) : observed; }
    function emit() { const st = snapshot(); listeners.forEach(function (fn) { fn(st); }); return st; }
    function clamp(i) { const n = list().length; return Math.max(0, Math.min(n - 1, i | 0)); }
    function snapshot() {
      const l = list(), f = l[s.index] || null;
      return { status: s.status, index: s.index, count: l.length, observedCount: observed.length, forecastCount: forecast.length,
               forecastOn: s.forecastOn, boundary: observed.length, frame: f, segment: f ? f.type : null,
               latestObserved: observed[observed.length - 1] || null };
    }
    const api = {
      snapshot: snapshot,
      frames: list,
      observed: function () { return observed.slice(); },
      forecast: function () { return forecast.slice(); },
      on: function (fn) { listeners.push(fn); return api; },
      play: function () { if (s.status === "empty") return snapshot(); if (s.status === "scrubbing") s.wasPlaying = true; else s.status = "playing"; return emit(); },
      pause: function () { if (s.status === "empty") return snapshot(); if (s.status === "scrubbing") s.wasPlaying = false; else s.status = "paused"; return emit(); },
      toggle: function () { return s.status === "playing" ? api.pause() : api.play(); },
      step: function (d) { if (s.status === "empty") return snapshot(); s.status = "paused"; s.index = clamp(s.index + (d < 0 ? -1 : 1)); return emit(); },
      seek: function (i) { if (s.status === "empty") return snapshot(); s.index = clamp(i); return emit(); },
      beginScrub: function () { if (s.status === "empty") return snapshot(); s.wasPlaying = s.status === "playing"; s.status = "scrubbing"; return emit(); },
      endScrub: function () { if (s.status !== "scrubbing") return snapshot(); s.status = s.wasPlaying ? "playing" : "paused"; return emit(); },
      /* Advance one frame while playing; wraps to the oldest observed frame after the end. `ready(i)`
         says whether frame i has finished loading: playback waits rather than show a blank map. */
      tick: function (ready, minWindow) {
        if (s.status !== "playing") return snapshot();
        const n = list().length;
        if (!ready) { s.index = s.index + 1 >= n ? 0 : s.index + 1; return emit(); }
        const w = api.readyWindow(ready);
        // Never step onto a frame that isn't fully loaded: loop the contiguous ready window around the
        // newest observed frame, and stay put until it holds `minWindow` frames (or every frame is ready).
        if (!w || (w.size < Math.min(minWindow || 1, n) && w.size < n)) return snapshot();
        const nx = s.index >= w.start && s.index < w.end ? s.index + 1 : w.start;
        if (nx === s.index) return snapshot();
        s.index = nx; return emit();
      },
      /* Contiguous run of ready frames that contains the newest observed frame: {start, end, size}. */
      readyWindow: function (ready) {
        const l = list(), a = observed.length - 1;
        if (a < 0 || !ready(a)) return null;
        let st = a, en = a;
        while (st > 0 && ready(st - 1)) st--;
        while (en < l.length - 1 && ready(en + 1)) en++;
        return { start: st, end: en, size: en - st + 1 };
      },
      /* Preload order: newest observed first, back to the oldest, then forecast frames (when shown) in time order. */
      loadOrder: function () {
        const o = [];
        for (let i = observed.length - 1; i >= 0; i--) o.push(i);
        if (s.forecastOn) for (let i = observed.length; i < observed.length + forecast.length; i++) o.push(i);
        return o;
      },
      holdMs: function () { return s.index >= list().length - 1 ? LAST_HOLD_MS : HOLD_MS; },
      setForecast: function (on) {
        on = !!on && forecast.length > 0;
        if (on === s.forecastOn) return snapshot();
        s.forecastOn = on;
        if (!on && s.index >= observed.length) s.index = observed.length - 1;
        return emit();
      },
      /* Swap in a refreshed frame list (new radar.json). Keeps play state and the forecast switch; stays on
         the same frame if it still exists, follows the newest observed frame if that was showing. */
      update: function (frames) {
        const cur = list()[s.index] || null, atLatest = s.index === observed.length - 1;
        split(norm(frames));
        if (!observed.length) { s.status = "empty"; s.index = 0; return emit(); }
        if (s.status === "empty") s.status = "paused";
        if (!forecast.length) s.forecastOn = false;
        const l = list(), j = cur ? l.findIndex(function (f) { return f.time === cur.time; }) : -1;
        s.index = atLatest || j < 0 ? (cur && cur.type === "forecast" && s.forecastOn ? observed.length : observed.length - 1) : j;
        return emit();
      },
      segmentOf: function (i) { return i < observed.length ? "observed" : "forecast"; },
    };
    return api;
  }

  /* Eastern Time, DST-correct via Intl (America/New_York). */
  const fT = new Intl.DateTimeFormat("en-US", { timeZone: "America/New_York", hour: "numeric", minute: "2-digit" });
  const fL = new Intl.DateTimeFormat("en-US", { timeZone: "America/New_York", weekday: "short", month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit", timeZoneName: "short" });
  const fD = new Intl.DateTimeFormat("en-US", { timeZone: "America/New_York", month: "short", day: "numeric" });
  function etTime(epoch) { return fT.format(new Date(epoch * 1000)) + " ET"; }
  function etLong(epoch) { return fL.format(new Date(epoch * 1000)); }       // "Sun, Mar 8, 2026, 3:00 AM EDT"
  function etDate(epoch) { return fD.format(new Date(epoch * 1000)); }
  function age(nowS, epoch) {
    const m = Math.max(0, Math.round((nowS - epoch) / 60));
    if (m < 1) return "just now";
    if (m < 60) return m + " min ago";
    const h = Math.floor(m / 60), r = m % 60;
    return h + " h" + (r ? " " + r + " min" : "") + " ago";
  }
  return { create: create, norm: norm, etTime: etTime, etLong: etLong, etDate: etDate, age: age, epochFromCode: epochFromCode, HOLD_MS: HOLD_MS, LAST_HOLD_MS: LAST_HOLD_MS };
});
