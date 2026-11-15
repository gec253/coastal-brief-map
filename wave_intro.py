"""Cookie-gated /preview/intro: the public homepage plus a signature wave overlay."""
from __future__ import annotations

from pathlib import Path

DIR = Path(__file__).resolve().parent / "preview" / "wave-intro"
SESSION_KEY = "cb-wave-intro-seen"
DURATION_MS = 1900

_OVERLAY = """
<div id="wave-intro" class="wave-intro" role="dialog" aria-label="Site introduction">
  <div class="wi-veil" aria-hidden="true">
    <svg class="wi-veil-svg" viewBox="0 0 1200 1600" preserveAspectRatio="none" focusable="false">
      <defs>
        <mask id="wi-cut-mask" maskUnits="userSpaceOnUse">
          <rect x="-80" y="-80" width="1360" height="1760" fill="#fff"/>
          <rect id="wi-mast-hole" x="0" y="0" width="0" height="0" fill="#000"/>
        </mask>
      </defs>
      <path class="wi-veil-sheet wi-veil-solid" d="M -40 -40 H 1240 V 880 C 1100 960, 1000 840, 860 900 C 720 960, 600 840, 460 910 C 300 980, 160 860, -40 940 Z"/>
      <path class="wi-veil-sheet wi-veil-cut" mask="url(#wi-cut-mask)" d="M -40 -40 H 1240 V 880 C 1100 960, 1000 840, 860 900 C 720 960, 600 840, 460 910 C 300 980, 160 860, -40 940 Z"/>
    </svg>
  </div>
  <div class="wi-stage" aria-hidden="true">
    <svg class="wi-svg" viewBox="0 0 1200 800" preserveAspectRatio="none" focusable="false">
      <path class="wi-echo" fill="none" d="M -60 428 C 80 428, 160 384, 280 402 C 410 422, 490 474, 630 440 C 750 410, 840 378, 960 364 C 1060 354, 1140 348, 1280 342"/>
      <path class="wi-swell" fill="none" d="M -60 412 C 80 412, 160 368, 280 386 C 410 406, 490 458, 630 424 C 750 394, 840 362, 960 348 C 1060 338, 1140 332, 1280 326"/>
      <g class="wi-rise">
        <path class="wi-crest wi-crest-a" fill="none" d="M 800 360 C 900 350, 1000 325, 1080 295 C 1120 278, 1155 265, 1180 258"/>
      </g>
      <g class="wi-break">
        <path class="wi-crest wi-crest-b" fill="none" d="M 800 360 C 900 350, 1000 320, 1070 285 C 1110 260, 1145 245, 1175 248 C 1195 250, 1198 265, 1185 278 C 1170 292, 1148 296, 1130 288"/>
      </g>
      <g class="wi-fall">
        <path class="wi-crest wi-crest-c" fill="none" d="M 800 360 C 900 352, 1000 328, 1065 300 C 1110 278, 1150 270, 1178 278 C 1195 284, 1192 302, 1172 312 C 1152 322, 1130 320, 1118 312"/>
      </g>
      <g class="wi-engraving">
        <path class="wi-hatch" fill="none" d="M 1140 268 C 1155 262, 1170 263, 1178 270"/>
        <path class="wi-hatch" fill="none" d="M 1136 276 C 1150 270, 1164 271, 1172 278"/>
        <path class="wi-hatch" fill="none" d="M 1134 284 C 1146 278, 1158 279, 1166 285"/>
        <circle class="wi-spray" cx="1208" cy="238" r="3.2"/>
        <circle class="wi-spray" cx="1216" cy="250" r="2.6"/>
        <circle class="wi-spray" cx="1200" cy="232" r="2.4"/>
        <circle class="wi-spray" cx="1222" cy="242" r="2.2"/>
      </g>
    </svg>
  </div>
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
