/* Catch wall: loads data/catch-wall.json and renders a lazy masonry grid. No market data. */
(function () {
  const THEME_STORE = "coastalBrief.theme";
  const $ = (id) => document.getElementById(id);

  function currentTheme() {
    return document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light";
  }
  function syncThemeToggle() {
    const btn = $("theme-toggle");
    if (!btn) return;
    const dark = currentTheme() === "dark";
    btn.setAttribute("aria-pressed", dark ? "true" : "false");
    btn.setAttribute("aria-label", dark ? "Switch to light mode" : "Switch to dark mode");
    btn.textContent = dark ? "Light mode" : "Dark mode";
  }
  function setTheme(theme, persist) {
    const t = theme === "dark" ? "dark" : "light";
    document.documentElement.setAttribute("data-theme", t);
    if (persist) {
      try { localStorage.setItem(THEME_STORE, t); } catch (e) {}
    }
    syncThemeToggle();
  }
  function initTheme() {
    syncThemeToggle();
    const btn = $("theme-toggle");
    if (btn) {
      btn.addEventListener("click", function () {
        setTheme(currentTheme() === "dark" ? "light" : "dark", true);
      });
    }
    try {
      if (!localStorage.getItem(THEME_STORE) && window.matchMedia) {
        const mq = window.matchMedia("(prefers-color-scheme: dark)");
        const onChange = function (e) {
          if (!localStorage.getItem(THEME_STORE)) setTheme(e.matches ? "dark" : "light", false);
        };
        if (mq.addEventListener) mq.addEventListener("change", onChange);
        else if (mq.addListener) mq.addListener(onChange);
      }
    } catch (e) {}
  }

  function render(photos) {
    const wall = $("catch-wall");
    const status = $("catch-status");
    wall.innerHTML = "";
    photos.forEach(function (photo) {
      const fig = document.createElement("figure");
      const img = document.createElement("img");
      img.src = photo.src;
      img.alt = photo.alt || "Placeholder tile reserved for a future catch photo";
      img.loading = "lazy";
      img.decoding = "async";
      if (photo.width) img.width = photo.width;
      if (photo.height) img.height = photo.height;
      fig.appendChild(img);
      wall.appendChild(fig);
    });
    if (status) status.textContent = "";
  }

  initTheme();
  const status = $("catch-status");
  if (status) status.textContent = "Loading the wall…";
  fetch("/data/catch-wall.json")
    .then(function (r) {
      if (!r.ok) throw new Error("Could not load the catch wall list.");
      return r.json();
    })
    .then(function (data) {
      render((data && data.photos) || []);
    })
    .catch(function (err) {
      if (status) status.textContent = String(err.message || err);
    });
})();
