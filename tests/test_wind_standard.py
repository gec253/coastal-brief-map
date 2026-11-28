"""Sitewide wind standard (Ed, Phase 3C.1): the reported direction is where the wind comes FROM;
every graphic arrow points where the air is going, (FROM + 180) mod 360. Numbers and FROM labels
keep the meteorological direction. Calm, variable and missing directions draw no arrow."""
import math
import re
import unittest
from pathlib import Path

import byl_page
import signature_helm
import sprint_home

ROOT = Path(__file__).resolve().parents[1]
BEARINGS = [0, 22.5, 45, 90, 135, 180, 225, 270, 315, 337.5]
NUM = r"-?\d+(?:\.\d+)?"


def bearing(dx, dy):
    """Screen vector (y grows downward) to a compass bearing."""
    return math.degrees(math.atan2(dx, -dy)) % 360


def rot(pt, a, cx=0.0, cy=0.0):
    r = math.radians(a)
    x, y = pt[0] - cx, pt[1] - cy
    return (cx + x * math.cos(r) - y * math.sin(r), cy + x * math.sin(r) + y * math.cos(r))


def arrow_bearing(points, a=0.0, cx=0.0, cy=0.0):
    """The arrowhead's first point is its tip: direction = tip minus the centroid of the others."""
    pts = [rot(p, a, cx, cy) for p in points]
    tip, rest = pts[0], pts[1:]
    mx, my = sum(p[0] for p in rest) / len(rest), sum(p[1] for p in rest) / len(rest)
    return bearing(tip[0] - mx, tip[1] - my)


def path_points(d):
    return [(float(x), float(y)) for x, y in re.findall(r"[ML]\s*(%s)[ ,](%s)" % (NUM, NUM), d)]


def close(a, b, tol=0.6):
    return abs(((a - b) + 180) % 360 - 180) <= tol


def expect(deg):
    return (deg + 180) % 360


class RotationMath(unittest.TestCase):
    def test_examples_from_the_standard(self):
        for frm, toward in ((0, 180), (90, 270), (180, 0), (270, 90), (225, 45), (22.5, 202.5), (135, 315), (315, 135)):
            self.assertEqual(expect(frm), toward)

    def test_bearing_helper(self):
        self.assertTrue(close(bearing(0, -1), 0))
        self.assertTrue(close(bearing(1, 0), 90))
        self.assertTrue(close(bearing(0, 1), 180))
        self.assertTrue(close(bearing(-1, 0), 270))


class HomepageHelmDial(unittest.TestCase):
    """Public homepage brass compass (signature_helm.dial_html): rim pointer whose tip points inward."""

    def render(self, deg, **kw):
        t = dict(state="ok", num="12", unit="kt", dir="", dial=deg, gust="", sub="")
        t.update(kw)
        return signature_helm.dial_html(t)

    def test_pointer_points_downwind(self):
        for deg in BEARINGS:
            h = self.render(deg)
            a = float(re.search(r'<g transform="rotate\((%s) 80 80\)"><path d="([^"]+)"' % NUM, h).group(1))
            d = re.search(r'<g transform="rotate\(%s 80 80\)"><path d="([^"]+)"' % NUM, h).group(1)
            self.assertTrue(close(arrow_bearing(path_points(d), a, 80, 80), expect(deg)), deg)

    def test_no_pointer_without_direction(self):
        self.assertNotIn("pointer", self.render(None))
        self.assertNotIn('class="pointer"', self.render(90, state="off", off="Not reporting"))

    def test_calm_model_wind_has_no_pointer(self):
        src = (ROOT / "signature_helm.py").read_text()
        self.assertIn('dial=None if calm else deg', src)
        self.assertIn('calm = kt < 0.5', src)


class SprintHomeDial(unittest.TestCase):
    def test_tile_dial_points_downwind(self):
        for deg in BEARINGS:
            h = sprint_home._dial(deg)
            d = re.search(r'<path d="([^"]+)" class="d-mark"', h).group(1)
            self.assertTrue(close(arrow_bearing(path_points(d)), expect(deg)), deg)

    def test_no_dial_without_direction(self):
        self.assertEqual(sprint_home._dial(None), "")


class BylInstruments(unittest.TestCase):
    def test_compass_points_downwind(self):
        for deg in BEARINGS:
            h = byl_page.compass_svg(deg, 10)
            a = float(re.search(r'<g transform="rotate\((%s)\)">' % NUM, h).group(1))
            d = re.search(r'<g transform="rotate\(%s\)"><path d="([^"]+)"' % NUM, h).group(1)
            self.assertTrue(close(arrow_bearing(path_points(d), a), expect(deg)), deg)

    def test_compass_without_direction(self):
        self.assertNotIn("rotate(", byl_page.compass_svg(None, 0))

    def test_hourly_arrows_point_downwind(self):
        for name, deg in byl_page.DIRS.items():
            h = byl_page.wind_bars_svg([{"t": "2026-11-28T18:00:00+00:00", "mph": 8, "dir": name}])
            m = re.search(r'translate\(%s,%s\) rotate\((%s)\)"><path d="([^"]+)"' % (NUM, NUM, NUM), h)
            self.assertTrue(close(arrow_bearing(path_points(m.group(2)), float(m.group(1))), expect(deg)), name)

    def test_hourly_calm_and_variable_draw_no_arrow(self):
        for mph, d in ((0, "N"), (5, ""), (5, "VRB")):
            h = byl_page.wind_bars_svg([{"t": "2026-11-28T18:00:00+00:00", "mph": mph, "dir": d}])
            self.assertNotIn("rotate(", h, (mph, d))

    def _card(self, **kw):
        c = dict(key="wind_obs", kind="rel", label="Wind", source="NWS KEWN", when="1:00 PM", note="", kt=8, mph=9, gust_kt=None, gust_mph=None, deg=225, dir="SW", calm=False)
        c.update(kw)
        return byl_page.card_html(c)

    def test_card_calm_variable_unavailable(self):
        self.assertIn("From SW", self._card())
        h = self._card(kt=0, mph=0, deg=0, dir="N", calm=True)
        self.assertIn("Calm", h)
        self.assertNotIn("rotate(", h)
        h = self._card(deg=None, dir="")
        self.assertIn("Direction variable or not reported", h)
        self.assertNotIn("rotate(", h)


class JsInstruments(unittest.TestCase):
    """JS needles: every wind rotation goes through FROM + 180 (static guard; the browser audit
    in the Phase 3C.1 report renders each one)."""

    def test_wind_viewer_compass(self):
        src = (ROOT / "wind-viewer.js").read_text()
        self.assertIn('"rotate(" + ((st.dirDeg + 180) % 360) + " 32 32)"', src)
        self.assertNotIn('"rotate(" + st.dirDeg + " 32 32)"', src)
        self.assertIn('"FROM " + Math.round(st.dirDeg)', src)  # label keeps the met direction
        self.assertIn('d.textContent = "CALM"', src)
        # Native needle points up (north) at rotation 0.
        html = (ROOT / "wind.html").read_text()
        self.assertIn('<polygon points="32,6 40,27 32,22 24,27"/>', html)

    def test_dashboard_harbor_compass(self):
        src = (ROOT / "dashboard.js").read_text()
        self.assertIn("rotate(' + ((v.dirDeg + 180) % 360) + 'deg); transform-origin: 30px 30px", src)
        self.assertNotIn("rotate(' + v.dirDeg + 'deg)", src)

    def test_dashboard_dial_and_particles_agree(self):
        src = (ROOT / "dashboard.js").read_text()
        # Needle: head on the FROM rim with its tip pointing inward (downwind); particles travel FROM + 180.
        self.assertIn("const tip = polar(C, R - 52, 0), bl = polar(C, R - 4, -6.5), br = polar(C, R - 4, 6.5)", src)
        self.assertIn("const toward = ((dir + 180) * Math.PI) / 180;", src)
        self.assertIn("const dirOk = isNum(v.dirDeg) && !(has && v.speedKt < 0.5);", src)

    def test_tiles_lab(self):
        self.assertIn("rotate(' + ((fromDeg + 180) % 360) + 'deg)", (ROOT / "tiles-lab.js").read_text())

    def test_engine_arrows_follow_uv(self):
        src = (ROOT / "wind-lab.js").read_text()
        self.assertIn("a = Math.atan2(-tmp[1], tmp[0])", src)  # canvas angle of (u, -v): toward
        self.assertIn("Math.atan2(-u, -v)", src)  # FROM for labels


if __name__ == "__main__":
    unittest.main()


class HelmCalmLabel(unittest.TestCase):
    def test_calm_reads_calm_not_from_calm(self):
        h = signature_helm.dial_html(dict(state="ok", num="0", unit="kt", dir="Calm", dial=None, gust="", sub=""))
        self.assertIn('<span class="dir">Calm</span>', h)
        self.assertNotIn("from Calm", h)
        self.assertNotIn('class="pointer"', h)
        self.assertIn('<span class="dir">from SW</span>', signature_helm.dial_html(dict(state="ok", num="9", unit="kt", dir="SW", dial=225, gust="", sub="")))


class CompassLetterContrast(unittest.TestCase):
    """Dark-mode compass lettering (Ed t576u): BYL cardinal letters take the theme ink colour
    (cream on navy in dark = 12:1; measured in the browser)."""

    def test_letters_are_inside_the_styled_group_and_use_ink(self):
        h = byl_page.compass_svg(225, 10)
        self.assertIn('<g class="cmp-l">', h)
        css = (ROOT / "preview/before-you-launch/byl.css").read_text()
        self.assertIn(".cmp-l text{font:700 11px \"Barlow Condensed\",sans-serif;fill:var(--ink)}", css)
        self.assertRegex(css, r"html\.dark,\.dark\{[^}]*--ink:#F6F1E7")
