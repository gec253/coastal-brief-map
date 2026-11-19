/* Sets the header Morning Brief href to the visitor's current region.
   Ed (Nov 19 launch audit, t336u): the link always opens the current region's
   own /brief page. Crystal Coast, Hatteras and Falls Lake have a published
   brief; every other region opens /brief?region=<that region>, the clear
   "No Morning Brief for this area" page with a way back to its conditions.
   Never another region's brief. Default (no region known): crystal-coast, the
   site's default region. The link itself is omitted by the server when
   MORNING_BRIEF_ENABLED is the kill switch, so this is a no-op if #nav-brief
   is missing. */
(function () {
  var DEFAULT = "crystal-coast";

  function briefRegion(id) {
    id = String(id || "").toLowerCase();
    return /^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(id) && id.length <= 40 ? id : DEFAULT;
  }

  function currentRegion() {
    try {
      var q = new URLSearchParams(location.search).get("region");
      if (q) return q;
      var path = location.pathname.replace(/\/$/, "") || "/";
      if (path === "/lake") return "falls-lake";
      return localStorage.getItem("coastalBrief.region") || DEFAULT;
    } catch (e) {
      return DEFAULT;
    }
  }

  function sync(id) {
    var href = "/brief?region=" + encodeURIComponent(briefRegion(id || currentRegion()));
    // Header link and the Map page's Morning Brief rail card.
    ["nav-brief", "folio-brief"].forEach(function (k) {
      var a = document.getElementById(k);
      if (a) a.href = href;
    });
  }

  sync();
  window.CoastalBriefLink = { sync: sync, briefRegion: briefRegion };
})();
