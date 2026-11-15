"""Cookie-gated /preview/intro: the public homepage plus a signature wave overlay."""
from __future__ import annotations

from pathlib import Path

DIR = Path(__file__).resolve().parent / "preview" / "wave-intro"
SESSION_KEY = "cb-wave-intro-seen"
DURATION_MS = 1800

_OVERLAY = """
<div id="wave-intro" class="wave-intro" role="dialog" aria-label="Site introduction">
  <div class="wi-veil" aria-hidden="true"></div>
  <div class="wi-stage" aria-hidden="true">
    <svg class="wi-svg" viewBox="0 0 1200 360" preserveAspectRatio="xMidYMid meet" focusable="false">
      <path class="wi-echo" fill="none" d="M-20 214 C 140 214, 220 188, 360 198 S 560 250, 720 200 S 900 160, 1100 176"/>
      <path class="wi-swell" fill="none" d="M-20 200 C 130 200, 210 168, 350 180 S 560 248, 720 186 C 850 148, 940 116, 1020 86 C 1055 72, 1082 54, 1090 40 C 1096 28, 1084 26, 1074 34 C 1064 44, 1076 56, 1096 58"/>
      <circle class="wi-spray" fill="currentColor" r="1.5" cx="1082" cy="32"/>
      <circle class="wi-spray" fill="currentColor" r="1.15" cx="1098" cy="44"/>
      <circle class="wi-spray" fill="currentColor" r="1.3" cx="1068" cy="24"/>
      <circle class="wi-spray" fill="currentColor" r="1.05" cx="1110" cy="54"/>
      <circle class="wi-spray" fill="currentColor" r="1.2" cx="1090" cy="20"/>
    </svg>
  </div>
  <p class="wi-motto">Know the Water. Live the Coast.</p>
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
  var q = new URLSearchParams(location.search || "");
  var force = q.get("play") === "1";
  var seen = q.get("seen") === "1";
  var seek = q.get("seek");
  var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  try {
    if (!force && (seen || sessionStorage.getItem(key) === "1")) {
      document.documentElement.classList.add("intro-seen");
      return;
    }
    if (seek !== null && seek !== "") {
      document.documentElement.classList.add("intro-play");
      document.documentElement.setAttribute("data-intro-seek", "");
      document.documentElement.style.setProperty("--intro-ms", String(Math.max(0, parseInt(seek, 10) || 0)));
      return;
    }
    if (reduce) document.documentElement.classList.add("intro-reduce");
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
    data = data[: gt + 1] + _OVERLAY.encode("utf-8") + data[gt + 1 :]

    foot = b"    </div>\n  </footer>"
    if foot not in data:
        raise RuntimeError("wave intro: footer wrap not found")
    data = data.replace(foot, b"      " + _REPLAY.encode("utf-8") + foot, 1)

    script = b'  <script>\n' + _js().encode("utf-8") + b"\n  </script>\n"
    data = data.replace(b"</body>", script + b"</body>", 1)
    return data
