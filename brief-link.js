/* Sets the header Morning Brief href to the visitor's current coast region.
   Default: crystal-coast. Only saltwater regions (crystal-coast, hatteras) and
   Falls Lake have a public brief; Jordan Lake and Neuse River (and any
   unknown id) fall back to crystal-coast. The link itself is omitted by the
   server when MORNING_BRIEF_ENABLED is the kill switch, so this is a no-op
   if #nav-brief is missing. */
(function () {
  var DEFAULT = "crystal-coast";
  var SALT = { "crystal-coast": true, "hatteras": true };

  function briefRegion(id) {
    if (SALT[id]) return id;
    if (id === "falls-lake") return "falls-lake";
    return DEFAULT;
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
    var a = document.getElementById("nav-brief");
    if (!a) return;
    a.href = "/brief?region=" + encodeURIComponent(briefRegion(id || currentRegion()));
  }

  sync();
  window.CoastalBriefLink = { sync: sync, briefRegion: briefRegion };
})();
