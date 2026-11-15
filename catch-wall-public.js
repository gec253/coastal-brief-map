/* Public Catch Wall: lightbox and share form. The gallery is server-rendered. */
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const THEME_STORE = "coastalBrief.theme";
  const boot = window.__CW_BOOT || { view: "catch", water: "all", photos: [] };
  const view = boot.view || "catch";
  const water = boot.water || "all";
  const shown = boot.photos || [];
  let config = { uploads: false };

  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])); }
  function formatTaken(v) {
    const m = String(v || "").match(/^(\d{4})-(\d{2})-(\d{2})/);
    if (!m) return "";
    const months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
    const d = new Date(Date.UTC(+m[1], +m[2] - 1, +m[3]));
    if (isNaN(d.getTime())) return "";
    return d.getUTCDate() + " " + months[d.getUTCMonth()] + " " + d.getUTCFullYear();
  }
  function credit(p) {
    const place = p.location || p.region || "";
    const what = [p.species, place, formatTaken(p.takenOn)].filter(Boolean).join(" · ");
    return { what: what, who: p.name ? "Photo: " + p.name : "" };
  }
  function altText(p) {
    const base = p.category === "fishing" ? (p.species ? p.species + " catch" : "Fishing photo") : "Coastal life photo";
    return base + (p.location ? " near " + p.location : "") + (p.caption ? ". " + p.caption : "") + (p.name ? ". Shared by " + p.name : "");
  }
  function srcset(p) { return ["400", "800", "1600"].filter((k) => p.src && p.src[k]).map((k) => p.src[k] + " " + Math.min(+k, p.w || +k) + "w").join(", "); }

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

  /* ---------- lightbox ---------- */
  const lb = $("lightbox");
  if (lb) {
    let lbIndex = 0, lbOpener = null;
    function lbShow(i) {
      if (!shown.length) return;
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
    function lbClose() { if (lb.open) lb.close(); }
    lb.addEventListener("close", function () {
      document.body.classList.remove("no-scroll");
      if (lbOpener) lbOpener.focus();
    });
    const gallery = $("gallery");
    if (gallery) {
      gallery.addEventListener("click", function (e) {
        const b = e.target.closest(".cw-open");
        if (b) lbOpen(+b.dataset.i, b);
      });
    }
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
    window.__cwTrapTab = trapTab;
  }

  /* ---------- share form (only when the server says uploads are on) ---------- */
  const dlg = $("share-dlg");
  let shareOpener = null, turnstileLoaded = false, turnstileId = null;
  function trapTab(dlg, e) {
    if (window.__cwTrapTab) return window.__cwTrapTab(dlg, e);
    if (e.key !== "Tab") return;
    const f = [...dlg.querySelectorAll("button, [href], input, select, textarea, [tabindex]:not([tabindex='-1'])")].filter((x) => !x.hidden && !x.disabled && x.offsetParent !== null);
    if (!f.length) return;
    const first = f[0], last = f[f.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  }
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
  function syncSpecies() {
    const form = $("share-form");
    if (!form) return;
    const c = form.querySelector("input[name=category]:checked");
    const wrap = $("sh-species-wrap");
    if (wrap) wrap.hidden = !(c && c.value === "fishing");
  }
  function fillRegions() {
    const sel = $("sh-region");
    if (!sel || sel.dataset.filled) return;
    const regions = config.regions || [];
    regions.forEach(function (r) {
      const o = document.createElement("option");
      o.value = r.id;
      o.textContent = r.name;
      sel.appendChild(o);
    });
    const other = document.createElement("option");
    other.value = "other";
    other.textContent = "Other / not listed";
    sel.appendChild(other);
    sel.dataset.filled = "1";
  }
  function openShare(e) {

    if (!config.uploads) return;
    shareOpener = (e && e.currentTarget) || $("share-open");
    $("share-form").hidden = false; $("share-done").hidden = true;
    const cat = $("share-form").querySelector("input[name=category][value='" + (view === "life" ? "life" : "fishing") + "']");
    if (cat && !$("share-form").querySelector("input[name=category]:checked")) cat.checked = true;
    const wt = $("share-form").querySelector("input[name=water_type][value='" + (water === "fresh" ? "freshwater" : "saltwater") + "']");
    if (wt && water !== "all" && !$("share-form").querySelector("input[name=water_type]:checked")) wt.checked = true;
    syncSpecies();
    fillRegions();
    loadTurnstile();
    if (dlg.showModal) dlg.showModal(); else dlg.setAttribute("open", "");
    document.body.classList.add("no-scroll");
    $("share-close").focus();
  }
  if (dlg) {
    dlg.addEventListener("close", function () { document.body.classList.remove("no-scroll"); if (shareOpener) shareOpener.focus(); });
    dlg.addEventListener("keydown", (e) => trapTab(dlg, e));
    $("share-close").addEventListener("click", () => dlg.close());
    $("share-done-close").addEventListener("click", () => dlg.close());
    if ($("share-open")) $("share-open").addEventListener("click", openShare);
    document.querySelectorAll("[data-share]").forEach(function (b) {
      if (b.id === "share-open") return;
      b.addEventListener("click", openShare);
    });
    $("share-form").querySelectorAll("input[name=category]").forEach((r) => r.addEventListener("change", syncSpecies));
    let previewUrl = null;
    function showPickedFile(f, input) {
      const box = $("sh-preview"), img = $("sh-preview-img");
      if (previewUrl) { URL.revokeObjectURL(previewUrl); previewUrl = null; }
      $("sh-error").textContent = "";
      if (!f) { box.hidden = true; return false; }
      const cap = config.maxBytes || 10485760;
      if (f.size > cap) {
        $("sh-error").textContent = "That file is larger than 10 MB. Please choose a smaller photo.";
        if (input) input.value = "";
        box.hidden = true;
        return false;
      }
      $("sh-preview-name").textContent = f.name + " · " + (f.size / 1048576).toFixed(1) + " MB";
      previewUrl = URL.createObjectURL(f);
      img.hidden = false;
      img.onerror = function () { img.hidden = true; };
      img.src = previewUrl;
      box.hidden = false;
      return true;
    }
    $("sh-photo").addEventListener("change", function () {
      showPickedFile(this.files && this.files[0], this);
    });
    (function () {
      const drop = $("sh-drop");
      if (!drop) return;
      ["dragenter", "dragover"].forEach(function (ev) {
        drop.addEventListener(ev, function (e) { e.preventDefault(); e.stopPropagation(); drop.classList.add("is-drop"); });
      });
      ["dragleave", "drop"].forEach(function (ev) {
        drop.addEventListener(ev, function (e) { e.preventDefault(); e.stopPropagation(); drop.classList.remove("is-drop"); });
      });
      drop.addEventListener("drop", function (e) {
        const f = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
        if (!f) return;
        const input = $("sh-photo");
        try {
          const dt = new DataTransfer();
          dt.items.add(f);
          input.files = dt.files;
        } catch (err) {}
        showPickedFile(f, input);
      });
    })();
    $("share-form").addEventListener("submit", function (e) {
      e.preventDefault();
      const form = e.currentTarget, err = $("sh-error"), btn = $("sh-submit");
      err.textContent = "";
      if (!form.querySelector("input[name=category]:checked")) { err.textContent = "Please choose Fishing or Coastal Life."; return; }
      if (!form.querySelector("input[name=water_type]:checked")) { err.textContent = "Please choose Saltwater or Freshwater."; return; }
      if (!$("sh-photo").files.length) { err.textContent = "Please choose a photo."; $("sh-photo").focus(); return; }
      if (!$("sh-name").value.trim()) { err.textContent = "Please enter your name."; $("sh-name").focus(); return; }
      if (!form.consent.checked) { err.textContent = "Please confirm you took the photo or have permission to share it."; form.consent.focus(); return; }
      if (!form.age.checked) { err.textContent = "Please confirm you are 13 or older, or have a parent or guardian's permission."; form.age.focus(); return; }
      const fd = new FormData(form);
      if (config.turnstileSiteKey && !fd.get("cf-turnstile-response")) {
        err.textContent = "Please complete the spam check and try again.";
        return;
      }
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
  }

  fetch("/api/photos/config").then((r) => r.ok ? r.json() : {}).catch(() => ({})).then(function (c) {
    config = c || { uploads: false };
    if ($("share-open")) $("share-open").hidden = !config.uploads;
    if ($("share-soon")) $("share-soon").hidden = !!config.uploads;
    document.querySelectorAll("[data-share]").forEach(function (b) {
      if (b.id === "share-open") return;
      b.hidden = !config.uploads;
    });
  });
})();
