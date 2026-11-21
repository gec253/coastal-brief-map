"""Ed t397u: the wave intro measures the rule in the first animation frame, not inside the parser's task."""
import re
import unittest
from pathlib import Path

JS = (Path(__file__).resolve().parents[1] / "preview" / "wave-intro" / "wave-intro.js").read_text(encoding="utf-8")


class StartupLayout(unittest.TestCase):
    def test_play_defers_measure_and_first_draw_to_raf(self):
        body = JS[JS.index("function play() {"):JS.index("function skipNow()")]
        raf = body.index("requestAnimationFrame(function () {")
        for call in ("mapRule();", "draw(0);", "startLoop();", "draw(Math.min(1, ms / DURATION));", "skip.focus();"):
            self.assertGreater(body.index(call), raf, call)
        self.assertLess(body.index("stopLoop();"), raf)
        self.assertLess(body.index("playT0 ="), body.index("draw(0);"))

    def test_skip_cancels_pending_first_frame(self):
        body = JS[JS.index("function play() {"):JS.index("function skipNow()")]
        self.assertRegex(body, r"raf = window\.requestAnimationFrame\(function \(\) \{\s*raf = 0;")
        self.assertIn("window.cancelAnimationFrame(raf)", JS)


if __name__ == "__main__":
    unittest.main()
