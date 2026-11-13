/* Home coastal-life strip: shows photos the editor marked "featured", else honest placeholders. */
(function () {
  "use strict";
  const box = document.getElementById("cs-tiles");
  if (!box) return;
  const run = function () {
    fetch("/api/photos?view=all&featured=1").then((r) => (r.ok ? r.json() : null)).then(function (d) {
      const list = (d && d.photos) || [];
      if (!list.length) return;
      const tiles = box.querySelectorAll(".cs-tile");
      list.slice(0, tiles.length).forEach(function (p, i) {
        const t = tiles[i];
        const img = document.createElement("img");
        img.src = p.thumb || (p.src && p.src["400"]);
        img.alt = (p.category === "fishing" ? (p.species || "Fishing") : "Coastal life") + " photo" + (p.location ? " near " + p.location : "");
        img.loading = "lazy"; img.decoding = "async"; img.width = 120; img.height = 90;
        t.textContent = "";
        t.appendChild(img);
        t.style.borderStyle = "solid";
      });
      box.setAttribute("aria-label", "Community photos from the coast");
    }).catch(function () {});
  };
  if ("requestIdleCallback" in window) requestIdleCallback(run, { timeout: 3000 }); else setTimeout(run, 1200);
})();
