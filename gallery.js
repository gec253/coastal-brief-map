/* Photo galleries: Catch Wall, Coastal Life, All photos. Approved photos only. */
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const THEME_STORE = "coastalBrief.theme";
  const VIEWS = {
    catch: { h: "Catch Wall", eyebrow: "Community photos · Fishing", lead: "Catches from North Carolina water, shared by the people who caught them.", path: "/catch-wall" },
    life: { h: "Coastal Life", eyebrow: "Community photos · The coast", lead: "Boats, beaches, sunsets, waterfronts, watermen, and the people who make the coast home.", path: "/coastal-life" },
    all: { h: "All photos", eyebrow: "Community photos", lead: "Everything on the Catch Wall and Coastal Life, newest first.", path: "/photos" },
  };

  /* ---------- theme (shared with the home page) ---------- */
  function currentTheme() { return document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light"; }
  function syncThemeToggle() {
    const btn = $("theme-toggle");
    if (!btn) return;
    const dark = currentTheme() === "dark";
    btn.setAttribute("aria-pressed", dark ? "true" : "false");
    btn.setAttribute("aria-label", dark ? "Switch to light mode" : "Switch to dark mode");
    btn.textContent = dark ? "Light mode" : "Dark mode";
  }
  function setTheme(t, persist) {
    document.documentElement.setAttribute("data-theme", t === "dark" ? "dark" : "light");
    if (persist) { try { localStorage.setItem(THEME_STORE, t); } catch (e) {} }
    syncThemeToggle();
  }
  syncThemeToggle();
  if ($("theme-toggle")) $("theme-toggle").addEventListener("click", function () { setTheme(currentTheme() === "dark" ? "light" : "dark", true); });

  /* ---------- view state (path or ?view=) ---------- */
  function viewFromUrl() {
    const q = new URLSearchParams(location.search).get("view");
    if (q && VIEWS[q]) return q;
    if (/^\/coastal-life/.test(location.pathname)) return "life";
    if (/^\/photos/.test(location.pathname)) return "all";
    return "catch";
  }
  let view = viewFromUrl();
  let all = null;            // every approved photo, fetched once
  let shown = [];            // photos in the current view
  let config = { uploads: false };

  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])); }

  function credit(p) {
    const what = [p.species, p.location].filter(Boolean).join(" · ");
    return { what: what, who: p.name ? "Photo: " + p.name : "" };
  }
  function altText(p) {
    const base = p.category === "fishing" ? (p.species ? p.species + " catch" : "Fishing photo") : "Coastal life photo";
    return base + (p.location ? " near " + p.location : "") + (p.caption ? ". " + p.caption : "") + (p.name ? ". Shared by " + p.name : "");
  }

  function syncChrome() {
    const v = VIEWS[view];
    $("gal-h").textContent = v.h;
    $("gal-eyebrow").textContent = v.eyebrow;
    $("gal-lead").textContent = v.lead;
    document.title = v.h + " — The Coastal Brief";
    document.querySelectorAll(".gal-tabs a").forEach(function (a) {
      if (a.dataset.view === view) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
    });
    document.querySelectorAll(".site-nav a[data-nav]").forEach(function (a) {
      if (a.dataset.nav === view) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
    });
  }

  /* ---------- balanced columns (no CSS columns: even bottoms, stable order) ---------- */
  function colCount() {
    const w = $("gallery").clientWidth || window.innerWidth;
    return w >= 1060 ? 4 : w >= 640 ? 3 : 2;
  }
  function srcset(p) { return ["400", "800", "1600"].filter((k) => p.src && p.src[k]).map((k) => p.src[k] + " " + Math.min(+k, p.w || +k) + "w").join(", "); }

  function render() {
    const g = $("gallery");
    shown = (all || []).filter((p) => view === "all" || (view === "catch" ? p.category === "fishing" : p.category === "life"));
    g.innerHTML = "";
    $("gal-empty").hidden = true;
    if (!shown.length) { renderEmpty(); return; }
    const n = colCount();
    const cols = [], heights = [];
    for (let i = 0; i < n; i++) { const c = document.createElement("div"); c.className = "gal-col"; g.appendChild(c); cols.push(c); heights.push(0); }
    const sizes = n === 2 ? "50vw" : n === 3 ? "(max-width: 1100px) 33vw, 360px" : "300px";
    shown.forEach(function (p, i) {
      const ratio = (p.h && p.w) ? p.h / p.w : 1;
      let k = 0;
      for (let j = 1; j < n; j++) if (heights[j] < heights[k] - 0.02) k = j;
      heights[k] += ratio + 0.12;
      const c = credit(p);
      const fig = document.createElement("figure");
      fig.className = "gal-item";
      fig.innerHTML =
        '<button type="button" class="gal-open" data-i="' + i + '" style="aspect-ratio:' + (p.w || 1) + " / " + (p.h || 1) + '">' +
        '<img src="' + esc(p.src["800"] || p.src["400"]) + '" srcset="' + esc(srcset(p)) + '" sizes="' + sizes + '" width="' + (p.w || 800) + '" height="' + (p.h || 800) + '" loading="' + (i < n * 2 ? "eager" : "lazy") + '" decoding="async" alt="' + esc(altText(p)) + '"></button>' +
        ((c.what || c.who) ? '<figcaption>' + (c.what ? '<span class="gi-what">' + esc(c.what) + "</span>" : "") + (c.who ? '<span class="gi-who">' + esc(c.who) + "</span>" : "") + "</figcaption>" : "");
      cols[k].appendChild(fig);
    });
    $("gal-count").textContent = shown.length + (shown.length === 1 ? " photo" : " photos") + " in " + VIEWS[view].h;
  }

  function renderEmpty() {
    const e = $("gal-empty");
    const what = view === "catch" ? "catch" : view === "life" ? "coastal moment" : "photo";
    e.innerHTML =
      '<div class="ph-grid" aria-hidden="true">' + [0, 1, 2].map((i) => '<div class="ph-tile ph-' + i + '"><span>Your photo here</span></div>').join("") + "</div>" +
      '<div class="ph-text"><h3>No photos here yet.</h3><p>' +
      (config.uploads
        ? "Be the first to share a " + what + ". Every photo is reviewed before it appears."
        : "Photo sharing opens soon. When it does, every photo will be reviewed before it appears.") +
      "</p>" + (config.uploads ? '<button type="button" class="btn-share" data-share>Share your photo</button>' : "") + "</div>";
    e.hidden = false;
    $("gal-count").textContent = "No photos in " + VIEWS[view].h + " yet";
    const b = e.querySelector("[data-share]");
    if (b) b.addEventListener("click", openShare);
  }

  let lastCols = 0;
  window.addEventListener("resize", function () {
    const n = colCount();
    if (n !== lastCols && shown.length) { lastCols = n; render(); }
  });

  document.querySelectorAll(".gal-tabs a").forEach(function (a) {
    a.addEventListener("click", function (ev) {
      if (ev.metaKey || ev.ctrlKey || ev.shiftKey || ev.button) return;
      ev.preventDefault();
      if (a.dataset.view === view) return;
      view = a.dataset.view;
      history.pushState({ view: view }, "", VIEWS[view].path);
      syncChrome(); render();
    });
  });
  window.addEventListener("popstate", function () { view = viewFromUrl(); syncChrome(); render(); });

  /* ---------- lightbox ---------- */
  const lb = $("lightbox");
  let lbIndex = 0, lbOpener = null;
  function lbShow(i) {
    lbIndex = (i + shown.length) % shown.length;
    const p = shown[lbIndex];
    const img = $("lb-img");
    img.removeAttribute("srcset");
    img.src = p.src["1600"] || p.src["800"];
    img.srcset = srcset(p);
    img.sizes = "100vw";
    img.alt = altText(p);
    img.width = p.w || 800; img.height = p.h || 800;
    const c = credit(p);
    $("lb-caption").innerHTML = [p.caption ? esc(p.caption) : "", c.what ? '<span class="gi-what">' + esc(c.what) + "</span>" : "", c.who ? '<span class="gi-who">' + esc(c.who) + "</span>" : ""].filter(Boolean).join(" ");
    $("lb-count").textContent = (lbIndex + 1) + " of " + shown.length;
    $("lb-prev").hidden = $("lb-next").hidden = shown.length < 2;
  }
  function lbOpen(i, opener) {
    lbOpener = opener;
    lbShow(i);
    if (lb.showModal) lb.showModal(); else lb.setAttribute("open", "");
    document.body.classList.add("no-scroll");
    $("lb-close").focus();
  }
  function lbClose() {
    if (lb.open) lb.close();
  }
  lb.addEventListener("close", function () {
    document.body.classList.remove("no-scroll");
    if (lbOpener) lbOpener.focus();
  });
  $("gallery").addEventListener("click", function (e) {
    const b = e.target.closest(".gal-open");
    if (b) lbOpen(+b.dataset.i, b);
  });
  $("lb-prev").addEventListener("click", () => lbShow(lbIndex - 1));
  $("lb-next").addEventListener("click", () => lbShow(lbIndex + 1));
  $("lb-close").addEventListener("click", lbClose);
  lb.addEventListener("click", function (e) { if (e.target === lb) lbClose(); });
  function trapTab(dlg, e) {
    if (e.key !== "Tab") return;
    const f = [...dlg.querySelectorAll("button, [href], input, select, textarea, [tabindex]:not([tabindex='-1'])")].filter((x) => !x.hidden && !x.disabled && x.offsetParent !== null);
    if (!f.length) return;
    const first = f[0], last = f[f.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  }
  lb.addEventListener("keydown", function (e) {
    if (e.key === "ArrowLeft") { e.preventDefault(); lbShow(lbIndex - 1); }
    else if (e.key === "ArrowRight") { e.preventDefault(); lbShow(lbIndex + 1); }
    else trapTab(lb, e);
  });
  let sx = null, sy = null;
  function swipeStart(x, y) { sx = x; sy = y; }
  function swipeEnd(x, y) {
    if (sx == null) return;
    const dx = x - sx, dy = y - sy;
    sx = null;
    if (Math.abs(dx) > 50 && Math.abs(dx) > Math.abs(dy) * 1.5 && shown.length > 1) lbShow(lbIndex + (dx < 0 ? 1 : -1));
  }
  if ("ontouchstart" in window) {
    lb.addEventListener("touchstart", function (e) { if (e.touches.length === 1) swipeStart(e.touches[0].clientX, e.touches[0].clientY); }, { passive: true });
    lb.addEventListener("touchend", function (e) { const t = e.changedTouches[0]; if (t) swipeEnd(t.clientX, t.clientY); }, { passive: true });
  } else {
    lb.addEventListener("pointerdown", function (e) { swipeStart(e.clientX, e.clientY); });
    lb.addEventListener("pointerup", function (e) { swipeEnd(e.clientX, e.clientY); });
  }

  /* ---------- share form (only when the server says uploads are on) ---------- */
  const dlg = $("share-dlg");
  let shareOpener = null, turnstileLoaded = false, turnstileId = null;
  function loadTurnstile() {
    if (turnstileLoaded || !config.turnstileSiteKey) return;
    turnstileLoaded = true;
    window.cbTurnstileReady = function () {
      turnstileId = window.turnstile.render("#sh-turnstile", { sitekey: config.turnstileSiteKey, theme: currentTheme(), size: "flexible" });
    };
    const s = document.createElement("script");
    s.src = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit&onload=cbTurnstileReady";
    s.async = true; s.defer = true;
    document.head.appendChild(s);
  }
  function openShare(e) {
    if (!config.uploads) return;
    shareOpener = (e && e.currentTarget) || $("share-open");
    $("share-form").hidden = false; $("share-done").hidden = true;
    const cat = $("share-form").querySelector("input[name=category][value='" + (view === "life" ? "life" : "fishing") + "']");
    if (cat && !$("share-form").querySelector("input[name=category]:checked")) cat.checked = true;
    syncSpecies();
    loadTurnstile();
    if (dlg.showModal) dlg.showModal(); else dlg.setAttribute("open", "");
    document.body.classList.add("no-scroll");
    $("share-close").focus();
  }
  dlg.addEventListener("close", function () { document.body.classList.remove("no-scroll"); if (shareOpener) shareOpener.focus(); });
  dlg.addEventListener("keydown", (e) => trapTab(dlg, e));
  $("share-close").addEventListener("click", () => dlg.close());
  $("share-done-close").addEventListener("click", () => dlg.close());
  $("share-open").addEventListener("click", openShare);
  function syncSpecies() {
    const c = $("share-form").querySelector("input[name=category]:checked");
    $("sh-species-wrap").hidden = !(c && c.value === "fishing");
  }
  $("share-form").querySelectorAll("input[name=category]").forEach((r) => r.addEventListener("change", syncSpecies));
  let previewUrl = null;
  $("sh-photo").addEventListener("change", function () {
    const f = this.files && this.files[0];
    const box = $("sh-preview"), img = $("sh-preview-img");
    if (previewUrl) { URL.revokeObjectURL(previewUrl); previewUrl = null; }
    $("sh-error").textContent = "";
    if (!f) { box.hidden = true; return; }
    if (f.size > (config.maxBytes || 15728640)) { $("sh-error").textContent = "That file is larger than 15 MB. Please choose a smaller photo."; this.value = ""; box.hidden = true; return; }
    $("sh-preview-name").textContent = f.name + " · " + (f.size / 1048576).toFixed(1) + " MB";
    previewUrl = URL.createObjectURL(f);
    img.hidden = false;
    img.onerror = function () { img.hidden = true; }; // e.g. HEIC outside Safari: name still shown
    img.src = previewUrl;
    box.hidden = false;
  });
  $("share-form").addEventListener("submit", function (e) {
    e.preventDefault();
    const form = e.currentTarget, err = $("sh-error"), btn = $("sh-submit");
    err.textContent = "";
    if (!form.querySelector("input[name=category]:checked")) { err.textContent = "Please choose Fishing or Coastal Life."; return; }
    if (!$("sh-photo").files.length) { err.textContent = "Please choose a photo."; $("sh-photo").focus(); return; }
    if (!form.consent.checked) { err.textContent = "Please confirm you own the photo or have permission to share it."; form.consent.focus(); return; }
    const fd = new FormData(form);
    if (!config.turnstileSiteKey) fd.set("cf-turnstile-response", "local-test-pass"); // local fake backend only; real servers require Turnstile
    btn.disabled = true; btn.textContent = "Sending…";
    fetch("/api/photos/submit", { method: "POST", body: fd, credentials: "same-origin" })
      .then((r) => r.json().catch(() => ({ ok: false, error: "The server did not answer clearly. Please try again." })))
      .then(function (res) {
        if (!res.ok) throw new Error(res.error || "Could not send the photo.");
        form.reset(); $("sh-preview").hidden = true;
        form.hidden = true; $("share-done").hidden = false; $("share-done").focus();
      })
      .catch(function (x) { err.textContent = String(x.message || x); if (window.turnstile && turnstileId != null) window.turnstile.reset(turnstileId); })
      .finally(function () { btn.disabled = false; btn.textContent = "Send for review"; });
  });

  /* ---------- boot ---------- */
  syncChrome();
  lastCols = colCount();
  fetch("/api/photos/config").then((r) => r.ok ? r.json() : {}).catch(() => ({})).then(function (c) {
    config = c || { uploads: false };
    $("share-open").hidden = !config.uploads;
    $("share-soon").hidden = !!config.uploads;
    return fetch("/api/photos?view=all");
  }).then((r) => r.ok ? r.json() : { photos: [] }).catch(() => ({ photos: [] })).then(function (d) {
    all = (d && d.photos) || [];
    render();
  });
})();
