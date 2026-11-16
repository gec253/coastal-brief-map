"""Public /brief and /lake presentation: Folio chrome, slim brief assets, lake height."""
import os
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class BriefLakePublic(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for k in ("MORNING_BRIEF_ENABLED", "FRESHWATER_ENABLED", "PREVIEW_KEY"):
            os.environ.pop(k, None)
        import server
        cls.server = server
        cls._orig_get_ads = server.get_ads

        def _fake_ads(force=False):
            return {"adsOn": False, "mode": "paused"}

        server.get_ads = _fake_ads
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.port = cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.base = "http://127.0.0.1:%d" % cls.port

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.server.get_ads = cls._orig_get_ads
        for k in ("MORNING_BRIEF_ENABLED", "FRESHWATER_ENABLED", "PREVIEW_KEY"):
            os.environ.pop(k, None)

    def setUp(self):
        for k in ("MORNING_BRIEF_ENABLED", "FRESHWATER_ENABLED", "PREVIEW_KEY"):
            os.environ.pop(k, None)

    def _get(self, path):
        with urllib.request.urlopen(self.base + path, timeout=30) as r:
            return r.status, r.read()

    def _assert_folio_chrome(self, body, current):
        self.assertIn(b'data-concept="a"', body)
        self.assertIn(b'<header class="site" data-identity', body)
        self.assertIn(b'id="masthead"', body)
        self.assertIn(b'id="compact-bar"', body)
        self.assertIn(b'id="region-nav"', body)
        self.assertIn(b'id="rn-btn"', body)
        self.assertIn(b'id="rn-menu"', body)
        self.assertIn(b'id="nav-brief"', body)
        self.assertIn(b"Know the Water. Live the Coast.", body)
        self.assertNotIn(b'<header class="mb-top">', body)
        self.assertEqual(body.count(b'<header class="site"'), 1)
        self.assertEqual(body.count(b'id="compact-bar"'), 1)
        self.assertEqual(body.count(b'id="rn-btn"'), 1)
        self.assertEqual(body.count(b'id="theme-toggle"'), 1)
        if current == "brief":
            self.assertIn(b'id="nav-brief" aria-current="page"', body)

    def test_brief_uses_folio_chrome_and_slim_assets(self):
        status, body = self._get("/brief?region=crystal-coast")
        self.assertEqual(status, 200)
        self._assert_folio_chrome(body, "brief")
        self.assertIn(b'href="/brief.css"', body)
        self.assertIn(b'href="/folio-chrome.css"', body)
        self.assertNotIn(b'href="/styles.css"', body)
        self.assertNotIn(b'href="styles.css"', body)
        self.assertIn(b'rel="preload" href="/fonts/fraunces-var.woff2" as="font"', body)
        self.assertEqual(body.count(b'rel="preload" href="/fonts/'), 1)
        self.assertNotIn(b"fraunces-italic-var.woff2", body)
        self.assertNotIn(b"source-sans-3-var.woff2", body)
        self.assertNotIn(b"barlow-condensed-600.woff2", body)
        self.assertIn(b'src="/region-nav.js"', body)
        self.assertIn(b'src="/identity.js"', body)
        self.assertIn(b'src="/brief-link.js"', body)
        self.assertIn(b'class="mast-date-short"', body)
        self.assertIn(b'class="mast-date-full"', body)

    def test_falls_lake_brief_uses_folio_chrome(self):
        status, body = self._get("/brief?region=falls-lake")
        self.assertEqual(status, 200)
        self._assert_folio_chrome(body, "brief")
        self.assertIn(b'data-water="freshwater"', body)
        self.assertIn(b'href="/brief.css"', body)
        self.assertNotIn(b'href="/styles.css"', body)

    def test_brief_print_button_is_present_and_hidden_in_print(self):
        # brief-polish look on public pages: the same button, now an icon with the accessible name "Print"
        btn = b'<button type="button" class="mb-print" onclick="window.print()" aria-label="Print">'
        for path in ("/brief?region=crystal-coast", "/brief?region=falls-lake"):
            status, body = self._get(path)
            self.assertEqual(status, 200, path)
            self.assertIn(btn, body, path)
            self.assertEqual(body.count(b'class="mb-print"'), 1, path)
        status, body = self._get("/lake")
        self.assertEqual(status, 200)
        self.assertNotIn(b'class="mb-print"', body)
        status, body = self._get("/")
        self.assertEqual(status, 200)
        self.assertNotIn(b'class="mb-print"', body)
        css = (ROOT / "brief.css").read_text()
        self.assertIn("@media print", css)
        self.assertRegex(css, r"\.mb-print,\s*\.theme-toggle[^{]*\{\s*display:\s*none")

    def test_brief_css_has_fallbacks_nowrap_and_dark_navy(self):
        css = (ROOT / "brief.css").read_text()
        self.assertIn("font-display:optional", css)
        self.assertIn("Fraunces Fallback", css)
        self.assertIn("Source Sans 3 Fallback", css)
        self.assertIn("Barlow Condensed Fallback", css)
        self.assertIn("html[data-concept] .mb-gkind", css)
        self.assertIn("white-space: nowrap", css)
        self.assertIn("#0F2A3C", css)
        self.assertIn("min-height: 44px", css)

    def test_lake_uses_folio_chrome_and_reserves_height(self):
        status, body = self._get("/lake")
        self.assertEqual(status, 200)
        self._assert_folio_chrome(body, "lake")
        self.assertIn(b'data-page="lake"', body)
        self.assertIn(b'href="/styles.css"', body)
        self.assertIn(b'id="fw-lake"', body)
        self.assertIn(b"#fw-lake.is-loading", body)
        self.assertIn(b"min-height: var(--fh)", body)
        self.assertIn(b"--rh-al: 0px", body)
        self.assertNotIn(b'id="fw-alert" role="status" style="min-height:var(--rh-al)"', body)
        self.assertIn(b"al-zones", body)
        self.assertIn(b'src="/region-nav.js"', body)
        self.assertIn(b'src="/identity.js"', body)
        self.assertIn(b'src="/lake.js"', body)
        self.assertIn(b'href="/lake?region=falls-lake"', body)
        self.assertIn(b'href="/lake?region=jordan-lake"', body)
        self.assertIn(b'data-region="falls-lake"', body)
        status, neuse = self._get("/lake?region=neuse-river")
        self.assertEqual(status, 200)
        self.assertIn(b'data-region="neuse-river"', neuse)
        self.assertNotIn(b'data-region="falls-lake"', neuse)
        status, jordan = self._get("/lake?region=jordan-lake")
        self.assertEqual(status, 200)
        self.assertIn(b'data-region="jordan-lake"', jordan)
        css = (ROOT / "styles.css").read_text()
        self.assertIn('html[data-page="lake"][data-region="neuse-river"] #fw-grid', css)
        self.assertIn('html[data-page="lake"][data-region="neuse-river"] #fw-inflows-sec', css)
        self.assertIn('html[data-page="lake"][data-region="neuse-river"] #fw-river-sec', css)

    def test_public_homepage_unchanged_by_brief_lake_chrome(self):
        status, body = self._get("/dashboard")
        self.assertEqual(status, 200)
        self.assertIn(b'data-home="folio"', body)
        self.assertNotIn(b'data-page="lake"', body)
        self.assertNotIn(b'href="/brief.css"', body)


if __name__ == "__main__":
    unittest.main()
