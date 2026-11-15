"""Cookie-gated /preview/intro: the public homepage plus a signature wave overlay."""
from __future__ import annotations

from pathlib import Path

DIR = Path(__file__).resolve().parent / "preview" / "wave-intro"
SESSION_KEY = "cb-wave-intro-seen"
DURATION_MS = 1400
HARD_MAX_MS = 1700

# Aged-brass stops shared by the masthead rule and the swell's leading edge.
_BRASS_STOPS = (
    '<stop offset="0" stop-color="#9C7440"/>'
    '<stop offset="0.22" stop-color="#B38E55"/>'
    '<stop offset="0.5" stop-color="#D2B47E"/>'
    '<stop offset="0.78" stop-color="#B38E55"/>'
    '<stop offset="1" stop-color="#9C7440"/>'
)

# The rule's gradient lives outside the overlay (which is display:none once
# the intro ends), in the masthead SVG's own user space (viewBox 0..1200).
_DEFS = (
    '<svg class="wi-defs" width="0" height="0" aria-hidden="true" focusable="false">'
    '<defs><linearGradient id="wi-rule-aged" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="1200" y2="0">'
    + _BRASS_STOPS
    + "</linearGradient></defs></svg>\n"
)

_OVERLAY = """
<div id="wave-intro" class="wave-intro" role="dialog" aria-label="Site introduction">
  <div class="wi-fill" aria-hidden="true"></div>
  <svg class="wi-svg" viewBox="0 0 1000 1000" preserveAspectRatio="none" focusable="false" aria-hidden="true">
    <defs>
      <linearGradient id="wi-brass-aged" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="1000" y2="0">""" + _BRASS_STOPS + """</linearGradient>
      <linearGradient id="wi-foam" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="1000" y2="0">
        <stop offset="0" stop-color="#A9CFC4" stop-opacity="0"/>
        <stop offset="0.62" stop-color="#A9CFC4" stop-opacity="1"/>
        <stop offset="1" stop-color="#A9CFC4" stop-opacity="0"/>
      </linearGradient>
      <clipPath id="wi-brass-clip" clipPathUnits="userSpaceOnUse"><rect x="0" y="-200" width="0" height="0"/></clipPath>
    </defs>
    <path class="wi-contour wi-contour-top" d="M -140 -80 H 1140 V 1400 H -140 Z"/>
    <path class="wi-contour wi-contour-mid" d="M -140 -80 H 1140 V 1400 H -140 Z"/>
    <path class="wi-sheet" d="M -140 -80 H 1140 V 1400 H -140 Z"/>
    <path class="wi-line wi-line-foam" fill="none" stroke="url(#wi-foam)" d=""/>
    <path class="wi-line wi-line-brass" fill="none" stroke="url(#wi-brass-aged)" clip-path="url(#wi-brass-clip)" d=""/>
  </svg>
  <button type="button" class="wi-skip" id="wi-skip">Skip intro</button>
  <button type="button" class="wi-sound" id="wi-sound" hidden aria-pressed="false" data-sound-hook>Sound</button>
</div>
"""

_REPLAY = (
    '<p class="wi-replay-wrap">'
    '<button type="button" class="wi-replay" id="wi-replay">Replay intro</button>'
    "</p>\n"
)

_BOOT = """<script>
(function(){
  var key = "cb-wave-intro-seen";
  var tsKey = "cb-wave-intro-seen-at";
  var windowMs = 12 * 60 * 60 * 1000;
  var q = new URLSearchParams(location.search || "");
  var force = q.get("play") === "1";
  var seen = q.get("seen") === "1";
  var seek = q.get("seek");
  var reduce = window.matchMedia && (
    window.matchMedia("(prefers-reduced-motion: reduce)").matches ||
    window.matchMedia("(prefers-reduced-data: reduce)").matches
  );
  function recent() {
    try { if (sessionStorage.getItem(key) === "1") return true; } catch (e) {}
    try {
      var ts = parseInt(localStorage.getItem(tsKey) || "", 10);
      if (ts && (Date.now() - ts) < windowMs) return true;
    } catch (e) {}
    return false;
  }
  function sameOriginRef() {
    try {
      if (!document.referrer) return false;
      return new URL(document.referrer).origin === location.origin;
    } catch (e) { return false; }
  }
  function backFwd() {
    try {
      var n = performance.getEntriesByType && performance.getEntriesByType("navigation")[0];
      if (n && n.type === "back_forward") return true;
      if (performance.navigation && performance.navigation.type === 2) return true;
    } catch (e) {}
    return false;
  }
  function topLanding() {
    if (window.top !== window) return false;
    var path = location.pathname.replace(/\\/+$/, "") || "/";
    return path === "/" || path === "/preview/intro";
  }
  try {
    if (!force && (seen || recent() || sameOriginRef() || backFwd() || !topLanding())) {
      document.documentElement.classList.add("intro-seen");
      return;
    }
    if (seek !== null && seek !== "") {
      document.documentElement.classList.add("intro-play");
      document.documentElement.setAttribute("data-intro-seek", "");
      document.documentElement.style.setProperty("--intro-ms", String(Math.max(0, parseInt(seek, 10) || 0)));
      return;
    }
    if (reduce) {
      // Reduced motion: no overlay at all, the page as it is.
      document.documentElement.classList.add("intro-seen");
      return;
    }
    document.documentElement.classList.add("intro-play");
  } catch (e) {
    document.documentElement.classList.add("intro-play");
  }
})();
</script>
"""


def _css() -> str:
    return (DIR / "wave-intro.css").read_text(encoding="utf-8")


def _js() -> str:
    return (DIR / "wave-intro.js").read_text(encoding="utf-8")


def paint(data: bytes) -> bytes:
    """Add the intro overlay, styles, and replay control to a Folio homepage."""
    attrs = b'<html lang="en" data-tiles="v2" data-preview data-concept="a" data-home="folio">'
    wanted = b'<html lang="en" data-tiles="v2" data-preview data-concept="a" data-home="folio" data-wave-intro>'
    if attrs not in data:
        raise RuntimeError("wave intro: unexpected homepage html")
    data = data.replace(attrs, wanted, 1)

    head = (
        b'  <style id="wave-intro-css">\n'
        + _css().encode("utf-8")
        + b"\n  </style>\n  "
        + _BOOT.encode("utf-8")
    )
    if b"</head>" not in data:
        raise RuntimeError("wave intro: missing </head>")
    data = data.replace(b"</head>", head + b"</head>", 1)

    body = data.find(b"<body")
    if body < 0:
        raise RuntimeError("wave intro: missing <body>")
    gt = data.find(b">", body)
    if gt < 0:
        raise RuntimeError("wave intro: malformed <body>")
    data = data[: gt + 1] + _DEFS.encode("utf-8") + _OVERLAY.encode("utf-8") + data[gt + 1 :]

    foot = b"    </div>\n  </footer>"
    if foot not in data:
        raise RuntimeError("wave intro: footer wrap not found")
    data = data.replace(foot, b"      " + _REPLAY.encode("utf-8") + foot, 1)

    script = b'  <script>\n' + _js().encode("utf-8") + b"\n  </script>\n"
    data = data.replace(b"</body>", script + b"</body>", 1)
    return data
