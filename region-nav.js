/* Header region picker: saltwater + freshwater groups,
   "From the rivers to the sounds to the sea". Freshwater options
   (Falls Lake, Jordan Lake, Neuse River) go to /lake?region=, matching
   the dash-head select. The freshwater flag is enforced on /lake itself
   (kill switch 404s), same as main. */
(function (global) {
  "use strict";
  var LINE = "From the rivers to the sounds to the sea";

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c];
    });
  }

  function $(id) { return document.getElementById(id); }

  function optionHtml(r, selectedId, disabled) {
    var coming = !!(r.comingSoon || disabled);
    var sel = r.id === selectedId && !coming;
    var label = coming ? esc(r.name) + ' <span class="rn-soon">Coming soon</span>' : esc(r.name);
    var area = r.area ? '<span class="rn-area">' + esc(r.area) + "</span>" : "";
    return '<div class="rn-opt' + (coming ? " is-soon" : "") + (sel ? " is-selected" : "") + '"' +
      ' role="option" id="rn-opt-' + esc(r.id) + '"' +
      ' data-id="' + esc(r.id) + '"' +
      (r.waterType ? ' data-water="' + esc(r.waterType) + '"' : "") +
      (r.href ? ' data-href="' + esc(r.href) + '"' : "") +
      ' aria-selected="' + (sel ? "true" : "false") + '"' +
      (coming ? ' aria-disabled="true"' : "") +
      ' tabindex="' + (coming ? "-1" : "0") + '">' +
      "<span class=\"rn-opt-name\">" + label + "</span>" + area + "</div>";
  }

  function menuHtml(cfg, currentId) {
    var salt = (cfg.regions || []).filter(function (r) { return (r.waterType || "saltwater") === "saltwater"; });
    var fresh = cfg.freshwater || [];
    var html = "";
    html += '<div class="rn-group" role="group" aria-labelledby="rn-salt-h">';
    html += '<p class="rn-g" id="rn-salt-h">Saltwater · the sounds &amp; the sea</p>';
    html += salt.map(function (r) { return optionHtml(r, currentId, false); }).join("");
    html += "</div>";
    html += '<div class="rn-group rn-fresh" role="group" aria-labelledby="rn-fresh-h">';
    html += '<p class="rn-g" id="rn-fresh-h">Freshwater · the rivers</p>';
    if (!fresh.length) {
      fresh = [
        { id: "falls-lake", name: "Falls Lake", waterType: "freshwater", href: "/lake?region=falls-lake" },
        { id: "jordan-lake", name: "Jordan Lake", waterType: "freshwater", href: "/lake?region=jordan-lake" },
        { id: "neuse-river", name: "Neuse River", waterType: "freshwater", href: "/lake?region=neuse-river" }
      ];
    }
    html += fresh.map(function (r) { return optionHtml(r, currentId, r.comingSoon); }).join("");
    html += "</div>";
    return html;
  }

  function optionsOf(menu) {
    return Array.prototype.slice.call(menu.querySelectorAll('[role="option"]:not([aria-disabled="true"])'));
  }

  function bind(root, cfg, opts) {
    if (!root) return;
    opts = opts || {};
    var btn = root.querySelector(".rn-btn") || $("rn-btn");
    var menu = root.querySelector(".rn-menu") || $("rn-menu");
    var nameEl = root.querySelector(".rn-name") || $("rn-name");
    var lineEl = root.querySelector(".rn-line") || $("rn-line");
    if (lineEl) lineEl.textContent = cfg.line || LINE;
    var currentId = opts.currentId || null;
    var salt = (cfg.regions || []);
    function nameFor(id) {
      var r = salt.filter(function (x) { return x.id === id; })[0];
      if (r) return r.name;
      var f = (cfg.freshwater || []).filter(function (x) { return x.id === id; })[0];
      return f ? f.name : (nameEl ? nameEl.textContent : "");
    }
    if (nameEl && currentId) nameEl.textContent = nameFor(currentId);
    if (menu) menu.innerHTML = menuHtml(cfg, currentId);

    function close() {
      if (!btn || !menu) return;
      btn.setAttribute("aria-expanded", "false");
      menu.hidden = true;
    }
    function open() {
      if (!btn || !menu) return;
      btn.setAttribute("aria-expanded", "true");
      menu.hidden = false;
      var sel = menu.querySelector('[role="option"][aria-selected="true"]') || optionsOf(menu)[0];
      if (sel) sel.focus();
    }
    function toggle() {
      if (!btn) return;
      if (btn.getAttribute("aria-expanded") === "true") close(); else open();
    }
    function choose(opt) {
      if (!opt || opt.getAttribute("aria-disabled") === "true") return;
      var id = opt.getAttribute("data-id");
      var water = opt.getAttribute("data-water") || "saltwater";
      var href = opt.getAttribute("data-href");
      close();
      if (water === "freshwater") {
        if (href) location.href = href;
        return;
      }
      if (nameEl) nameEl.textContent = nameFor(id);
      if (typeof opts.onSelect === "function") opts.onSelect(id, { waterType: water, href: href });
      try {
        document.dispatchEvent(new CustomEvent("coastalbrief:region", { detail: { id: id, waterType: water, href: href } }));
      } catch (e) {}
    }

    if (btn && !btn._rnBound) {
      btn._rnBound = true;
      btn.addEventListener("click", function (e) { e.preventDefault(); toggle(); });
      btn.addEventListener("keydown", function (e) {
        if (e.key === "ArrowDown" || e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          open();
        }
      });
    }
    if (menu && !menu._rnBound) {
      menu._rnBound = true;
      menu.addEventListener("click", function (e) {
        var opt = e.target.closest('[role="option"]');
        if (opt) choose(opt);
      });
      menu.addEventListener("keydown", function (e) {
        var items = optionsOf(menu);
        var i = items.indexOf(document.activeElement);
        if (e.key === "Escape") { e.preventDefault(); close(); btn && btn.focus(); return; }
        if (e.key === "ArrowDown") { e.preventDefault(); items[Math.min(items.length - 1, i + 1) || 0].focus(); return; }
        if (e.key === "ArrowUp") { e.preventDefault(); items[Math.max(0, i < 0 ? 0 : i - 1)].focus(); return; }
        if (e.key === "Home") { e.preventDefault(); if (items[0]) items[0].focus(); return; }
        if (e.key === "End") { e.preventDefault(); if (items.length) items[items.length - 1].focus(); return; }
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          choose(document.activeElement && document.activeElement.getAttribute("role") === "option" ? document.activeElement : null);
        }
        if (e.key === "Tab") close();
      });
      document.addEventListener("click", function (e) {
        if (!root.contains(e.target)) close();
      });
      document.addEventListener("keydown", function (e) {
        if (e.key === "Escape" && btn && btn.getAttribute("aria-expanded") === "true") {
          close(); btn.focus();
        }
      });
    }

    root._rnSet = function (id) {
      currentId = id;
      if (nameEl) nameEl.textContent = nameFor(id);
      if (menu) menu.innerHTML = menuHtml(cfg, currentId);
    };
    return root;
  }

  function setCurrent(id) {
    document.querySelectorAll("[data-region-nav]").forEach(function (root) {
      if (typeof root._rnSet === "function") root._rnSet(id);
    });
    var sel = $("region-select");
    if (sel && sel.value !== id && Array.prototype.some.call(sel.options, function (o) { return o.value === id; })) {
      sel.value = id;
    }
  }

  global.CoastalRegionNav = { bind: bind, setCurrent: setCurrent, LINE: LINE };
})(window);
