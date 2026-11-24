"""t453u NAV_V2 private preview: shared masthead, phone-first section nav, Guides cards.

Off by default (byte-identical public output); on with NAV_V2=1 or the preview cookie."""
from __future__ import annotations

import os
import re
import subprocess
import sys
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import nav_v2  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
KEY = "preview-test-key-24-chars-ok"
PROD = "4aabd47"
ENV_KEYS = ("PREVIEW_KEY", "NAV_V2", "MORNING_BRIEF_ENABLED", "FRESHWATER_ENABLED",
            "PUBLIC_WHATS_BITING", "PUBLIC_RAMPS", "PUBLIC_RAMP_MAP")
LIVE = {"PUBLIC_WHATS_BITING": "1", "PUBLIC_RAMPS": "1", "MORNING_BRIEF_ENABLED": "1", "FRESHWATER_ENABLED": "1"}


class Server(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import server
        cls.server = server
        cls.httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.port = cls.httpd.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def _req(self, path, env=None, cookie=None):
        saved = {k: os.environ.get(k) for k in ENV_KEYS}
        try:
            for k in ENV_KEYS:
                os.environ.pop(k, None)
            for k, v in (env or {}).items():
                os.environ[k] = v
            conn = HTTPConnection("127.0.0.1", self.port, timeout=60)
            conn.request("GET", path, headers={"Cookie": cookie} if cookie else {})
            r = conn.getresponse()
            body = r.read()
            conn.close()
            return r.status, body
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    def _cookie(self):
        return "%s=%s" % (self.server.PREVIEW_COOKIE, self.server._preview_cookie_value(KEY))


PAGES = (("/reports", "biting"), ("/reports/crystal-coast", "biting"), ("/ramps", "ramps"),
         ("/ramps/usace-jordan-poes-ridge", "ramps"), ("/feedback", ""))


class OffByDefault(Server):
    def test_no_v2_markup_without_flag_or_cookie(self):
        for path, _ in PAGES + (("/", "conditions"),):
            status, body = self._req(path, env=LIVE)
            self.assertEqual(status, 200, path)
            for marker in (b"data-nav-v2", b"cb-nav-v2", b'class="cbn"', b'class="cbg"'):
                self.assertNotIn(marker, body, path)

    def test_wrong_cookie_and_flag_values_stay_off(self):
        env = dict(LIVE, PREVIEW_KEY=KEY)
        _, body = self._req("/reports", env=env, cookie="cb_preview=nope")
        self.assertNotIn(b"data-nav-v2", body)
        for v in ("0", "false", "off", ""):
            _, body = self._req("/ramps", env=dict(LIVE, NAV_V2=v))
            self.assertNotIn(b"data-nav-v2", body, v)

    def test_preview_cookie_turns_it_on(self):
        env = dict(LIVE, PREVIEW_KEY=KEY)
        _, body = self._req("/reports", env=env, cookie=self._cookie())
        self.assertIn(b"data-nav-v2", body)


class SecondaryPages(Server):
    def test_one_masthead_one_nav_and_current_section(self):
        env = dict(LIVE, NAV_V2="1")
        for path, key in PAGES:
            status, body = self._req(path, env=env)
            self.assertEqual(status, 200, path)
            self.assertEqual(body.count(b"data-nav-v2"), 1, path)
            self.assertEqual(body.count(b'<nav class="cbn"'), 1, path)
            self.assertEqual(body.count(b'id="cb-nav-v2"'), 1, path)
            self.assertIn(b'class="cbm-name"><a href="/">The Coastal Brief</a>', body, path)
            nav = re.search(rb'<nav class="cbn".*?</nav>', body, re.S).group(0)
            cur = re.findall(rb'class="cbn-a cbn-(\w+)"[^>]*aria-current="page"', nav)
            self.assertEqual(cur, [key.encode()] if key else [], path)
            for label in (b"Conditions", b"Morning Brief", "What\u2019s Biting?".encode(), b"Find a Ramp",
                          b"Catch Wall", b"Coastal Life"):
                self.assertIn(label, nav, path)
            for old in (b'class="wb-top"', b'class="rf-top"', b'<header class="mh">'):
                self.assertNotIn(old, body, path)
            self.assertLessEqual(body.count(b'id="theme-toggle"'), 1, path)
            self.assertIn(b'class="skip"', body, path)

    def test_theme_toggle_kept_on_reports_and_ramps(self):
        env = dict(LIVE, NAV_V2="1")
        for path in ("/reports", "/ramps"):
            _, body = self._req(path, env=env)
            self.assertEqual(body.count(b'id="theme-toggle"'), 1, path)

    def test_gated_items_follow_public_flags(self):
        env = {"NAV_V2": "1", "MORNING_BRIEF_ENABLED": "1", "PUBLIC_RAMPS": "1"}
        _, body = self._req("/ramps", env=env)
        nav = re.search(rb'<nav class="cbn".*?</nav>', body, re.S).group(0)
        self.assertNotIn("What\u2019s Biting?".encode(), nav)
        self.assertIn(b"Find a Ramp", nav)

    def test_no_brief_page_and_ramp_404s_unchanged(self):
        env = dict(LIVE, NAV_V2="1")
        status, body = self._req("/brief?region=wilmington", env=env)
        self.assertEqual(status, 404)
        self.assertIn(b"data-nav-v2", body)
        self.assertIn(b"No Morning Brief for this area", body)
        for path in ("/ramps.json", "/ramps/map", "/ramps/local-atlantic-beach-west-bogue-sound"):
            status, _ = self._req(path, env=env)
            self.assertEqual(status, 404, path)


class Homepage(Server):
    def test_home_nav_and_guides_cards(self):
        env = dict(LIVE, NAV_V2="1")
        status, body = self._req("/?region=crystal-coast", env=env)
        self.assertEqual(status, 200)
        self.assertIn(b'<header class="mh mh-hybrid">', body)  # homepage masthead is the reference, kept
        self.assertNotIn(b'<nav class="mh-sec"', body)
        self.assertNotIn(b'class="folio-guides"', body)
        nav = re.search(rb'<nav class="cbn".*?</nav>', body, re.S).group(0)
        self.assertRegex(nav, rb'class="cbn-a cbn-conditions" href="/\?region=crystal-coast" aria-current="page"')
        self.assertIn(b'id="nav-brief"', nav)
        g = re.search(rb'<section class="cbg".*?</section>', body, re.S).group(0)
        self.assertIn(b'href="/reports/crystal-coast"', g)
        self.assertIn(b'href="/ramps?region=crystal-coast"', g)
        self.assertIn(b'href="/dashboard?region=crystal-coast"', g)
        self.assertNotIn(b"not yet listed", g)

    def test_uncovered_region_keeps_coverage_note(self):
        env = dict(LIVE, NAV_V2="1")
        _, body = self._req("/?region=wilmington", env=env)
        g = re.search(rb'<section class="cbg".*?</section>', body, re.S).group(0)
        self.assertIn(b'href="/ramps"', g)
        self.assertIn(b"Ramps are not yet listed for this area", g)

    def test_freshwater_dashboard_card(self):
        self.assertIn('href="/lake?region=falls-lake"', nav_v2.guides_html("falls-lake"))

    def test_ramps_off_hides_find_a_ramp(self):
        env = {"NAV_V2": "1", "PUBLIC_WHATS_BITING": "1"}
        _, body = self._req("/", env=env)
        self.assertNotIn(b"Find a Ramp", body)


class WaterChoice(Server):
    """Ed t454u: obvious Saltwater / Freshwater choice and area picker on the homepage."""

    def _water(self, rid):
        _, body = self._req("/?region=%s" % rid, env=dict(LIVE, NAV_V2="1"))
        m = re.search(rb'<section class="cbw".*?</section>', body, re.S)
        self.assertIsNotNone(m, rid)
        return body, m.group(0)

    def test_salt_region_marks_saltwater_and_offers_freshwater(self):
        body, w = self._water("hatteras")
        self.assertIn(b'class="cbw-s cbw-saltwater" href="/?region=hatteras" aria-current="true"', w)
        self.assertIn(b'class="cbw-s cbw-freshwater" href="/?region=falls-lake">', w)
        self.assertIn(b'<option value="hatteras" selected>', w)
        self.assertLess(body.find(b'<section class="cbw"'), body.find(b'<section class="cg'))

    def test_fresh_region_marks_freshwater_and_offers_saltwater(self):
        _, w = self._water("jordan-lake")
        self.assertIn(b'class="cbw-s cbw-freshwater" href="/?region=jordan-lake" aria-current="true"', w)
        self.assertIn(b'class="cbw-s cbw-saltwater" href="/">', w)
        self.assertIn(b'<option value="jordan-lake" selected>', w)

    def test_picker_lists_exactly_the_public_regions_from_the_page(self):
        body, w = self._water("crystal-coast")
        rr = re.search(rb'<nav class="rr".*?</nav>', body, re.S).group(0)
        listed = re.findall(rb'href="/\?region=([a-z-]+)"', rr)
        opts = re.findall(rb'<option value="([a-z-]+)"', w)
        self.assertEqual(opts, listed)
        self.assertEqual(len(opts), 9)
        self.assertIn(b'<form class="cbw-pick" action="/" method="get">', w)
        self.assertIn(b'name="region"', w)

    def test_water_choice_only_with_nav_v2(self):
        _, body = self._req("/?region=hatteras", env=LIVE)
        self.assertNotIn(b'class="cbw"', body)


class IdentityPages(unittest.TestCase):
    """catch-wall.html carries the identity header used by Catch Wall, the brief, /dashboard and /lake."""

    def test_region_picker_toggle_and_brief_link_are_moved_not_rebuilt(self):
        src = (ROOT / "catch-wall.html").read_bytes()
        out = nav_v2.apply(src, "/catch-wall")
        self.assertNotIn(b'id="compact-bar"', out)
        self.assertEqual(out.count(b"data-region-nav"), src.count(b"data-region-nav"))
        self.assertEqual(out.count(b'id="rn-menu"'), 1)
        self.assertEqual(out.count(b'id="theme-toggle"'), 1)
        self.assertEqual(out.count(b'id="nav-brief"'), 1)
        self.assertIn(b'id="sticky-sentinel"', out)
        self.assertIn(b'<h1 class="cbm-name">', out)
        self.assertRegex(out, rb'class="cbn-a cbn-catch" href="/catch-wall" aria-current="page"')

    def test_unknown_pages_are_untouched(self):
        src = (ROOT / "catch-wall.html").read_bytes()
        for path in ("/wind", "/radar", "/preview", "/admin", "/ramps/map", "/api/conditions"):
            self.assertIs(nav_v2.apply(src, path), src, path)
        self.assertEqual(nav_v2.apply(b"<html><body>x</body></html>", "/reports"), b"<html><body>x</body></html>")


class Budget(unittest.TestCase):
    def test_css_is_small_and_adds_no_fonts_or_libraries(self):
        tag = nav_v2.style_tag(True).decode()
        self.assertLess(len(tag.encode()), 12000)
        self.assertNotIn("@import", tag)
        self.assertEqual(re.findall(r'url\("(/fonts/[^"]+)"\)', tag), ["/fonts/fraunces-var.woff2"])
        self.assertIn("min-height:46px", tag)
        self.assertIn("min-height:44px", tag)

    def test_only_preview_files_changed_from_production(self):
        proc = subprocess.run(["git", "diff", "--name-only", PROD, "--", "."], cwd=ROOT,
                              capture_output=True, text=True, check=True)
        changed = {x for x in proc.stdout.split() if x != "data/ads.json"}
        # 15f1fdd landed NAV_V2 on production. This freshwater first-paint repair may also change:
        repair = {
            "freshwater.py", "sprint_home.py", "server.py", "fresh-home.js",
            "preview/sprint-home/hybrid.css",
            "tests/test_nav_v2.py", "tests/test_freshwater_first_paint.py",
            "tests/test_freshwater_warm.py", "tests/test_ramp_finder_preview.py",
            "tests/test_freshwater.py",
        }
        self.assertLessEqual(changed, {"nav_v2.py", "server.py", "tests/test_nav_v2.py"} | repair, changed)


if __name__ == "__main__":
    unittest.main()
