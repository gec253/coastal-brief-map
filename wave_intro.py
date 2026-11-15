"""Cookie-gated /preview/intro: the public homepage plus a signature wave overlay."""
from __future__ import annotations

from pathlib import Path

DIR = Path(__file__).resolve().parent / "preview" / "wave-intro"
SESSION_KEY = "cb-wave-intro-seen"
DURATION_MS = 1800

_OVERLAY = """
<div id="wave-intro" class="wave-intro" role="dialog" aria-label="Site introduction">
  <div class="wi-veil" aria-hidden="true">
    <svg class="wi-veil-svg" viewBox="0 0 1200 1600" preserveAspectRatio="none" focusable="false">
      <path class="wi-veil-sheet" d="M -40 -40 H 1240 V 880 C 1100 960, 1000 840, 860 900 C 720 960, 600 840, 460 910 C 300 980, 160 860, -40 940 Z"/>
    </svg>
  </div>
  <div class="wi-stage" aria-hidden="true">
    <svg class="wi-svg" viewBox="0 0 1200 800" preserveAspectRatio="none" focusable="false">
      <path class="wi-echo" fill="none" d="M -60 428 C 80 428, 160 384, 280 402 C 410 422, 490 474, 630 440 C 750 410, 840 378, 960 364 C 1060 354, 1140 348, 1280 342"/>
      <path class="wi-swell" fill="none" d="M -60 412 C 80 412, 160 368, 280 386 C 410 406, 490 458, 630 424 C 750 394, 840 362, 960 348 C 1060 338, 1140 332, 1280 326"/>
      <g class="wi-curl">
        <path class="wi-crest" fill="none" d="M 760 378 C 900 360, 1040 340, 1110 300 C 1165 272, 1170 236, 1120 214 C 1060 188, 990 206, 968 250 C 954 278, 992 300, 1055 302"/>
        <path class="wi-arc wi-spray-a" fill="none" d="M 1088 200 C 1104 184, 1130 178, 1150 190"/>
        <path class="wi-arc wi-spray-b" fill="none" d="M 1128 224 C 1144 214, 1164 220, 1176 236"/>
        <circle class="wi-dot wi-spray-c" cx="1118" cy="198" r="11"/>
        <circle class="wi-dot wi-spray-d" cx="1150" cy="220" r="13"/>
        <circle class="wi-dot wi-spray-e" cx="1084" cy="188" r="9"/>
        <circle class="wi-dot wi-spray-f" cx="1172" cy="248" r="10"/>
        <circle class="wi-dot wi-spray-g" cx="1130" cy="178" r="8"/>
        <circle class="wi-dot wi-spray-h" cx="1098" cy="170" r="7"/>
      </g>
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
