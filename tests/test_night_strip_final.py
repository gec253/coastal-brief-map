"""Private opt-in design guards; no data/instrument behavior changes."""
import json
import re
import unittest
from pathlib import Path
from PIL import Image
import sprint_home as home
import server

ROOT = Path(__file__).resolve().parents[1]

class NightStripFinal(unittest.TestCase):
    def test_single_night_option_no_tint_or_phone_gate(self):
        for rel in ('index.html', 'styles.css', 'preview/sprint-home/hybrid.css', 'sprint_home.py'):
            s = (ROOT / rel).read_text()
            for old in ('data-night="a"', 'night=a|b', 's==="tint"', 'data-strip="tint"', 'q.get("chart")'):
                self.assertNotIn(old, s)
        self.assertIn('n==="1"||n==="b"', home.NIGHT_BOOT)
        self.assertIn('if(d.hasAttribute("data-night"))d.setAttribute("data-mastchart","")', home.NIGHT_BOOT)

    def test_strip_is_opt_in_and_saltwater_only(self):
        mast = '<header>mast</header>'
        self.assertEqual(home._with_strip(mast, 'fresh'), mast)
        salt = home._with_strip(mast, 'salt')
        self.assertIn('hasAttribute("data-strip")', salt)
        # Markup is escaped in the script string, so it does not create images without the switch.
        self.assertNotIn('<figure', salt)
        self.assertIn('\\u003cfigure', salt)
        self.assertIn(home.STRIP_CREDIT, salt)

    def test_half_strip_sources_and_dimensions(self):
        for side in ('l','r'):
            html = home._strip_half(side, 'alt')
            self.assertIn('sizes="50vw"', html)
            self.assertIn('width="195" height="88"', html)
            self.assertIn('decoding="async" fetchpriority="high"', html)
            self.assertNotIn('loading="lazy"', html)
            for kind, ws in home._STRIP_W.items():
                for w in ws:
                    dims = []
                    for ext in ('avif', 'webp', 'jpg'):
                        f = ROOT / 'static' / 'night-strip' / f'docks-{kind}-{side}-{w}.{ext}'
                        self.assertTrue(f.is_file(), str(f))
                        self.assertTrue(server._static_allowed('/static/night-strip/' + f.name))
                        with Image.open(f) as im:
                            dims.append(im.size)
                            self.assertEqual(im.width, w)
                            self.assertFalse(im.getexif())
                    self.assertEqual(dims[0], dims[1]); self.assertEqual(dims[1], dims[2])
        self.assertIn('type=\\"image/avif\\"', home.NIGHT_BOOT)
        self.assertIn('imagesizes=\\"50vw\\"', home.NIGHT_BOOT)

    def test_chart_only_changes_opt_in_rule(self):
        css = (ROOT / 'preview/sprint-home/hybrid.css').read_text()
        self.assertIn('html[data-mastchart] .mh-hybrid .mh-plate::before', css)
        self.assertIn('/static/night-strip/chart-560.webp', css)
        self.assertNotIn('mix-blend-mode:color', css)
        self.assertLess((ROOT / 'static/night-strip/chart-560.webp').stat().st_size, 8000)

if __name__ == '__main__':
    unittest.main()
