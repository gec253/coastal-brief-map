"""Public /dashboard basemap: Census land treatment under the NOAA ENC chart (Ed t375u).

No Esri / arcgisonline URLs remain on the dashboard. /lab/wind is listed only
(not changed) and still uses Esri until a separate decision.
"""
from __future__ import annotations

import os
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


class Sources(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = (ROOT / "app.js").read_text(encoding="utf-8")
        cls.html = (ROOT / "index.html").read_text(encoding="utf-8")
        cls.css = (ROOT / "styles.css").read_text(encoding="utf-8")
        cls.dash = (ROOT / "dashboard.js").read_text(encoding="utf-8")
        cls.lab = (ROOT / "wind-lab.js").read_text(encoding="utf-8")
        cls.coast = (ROOT / "wind-coast.js").read_text(encoding="utf-8")

    def test_no_arcgisonline_urls_on_dashboard(self):
        for name, text in (
            ("app.js", self.app),
            ("index.html", self.html),
            ("styles.css", self.css),
            ("dashboard.js", self.dash),
        ):
            lower = text.lower()
            self.assertNotIn("arcgisonline", lower, name)
            self.assertNotIn("esri.com", lower, name)
            self.assertNotIn("map base tiles © esri", lower, name)
            self.assertNotIn("tiles © esri", lower, name)

    def test_uses_existing_census_coast_layer(self):
        self.assertIn("CBCoast.layer", self.app)
        self.assertIn('base: "/wind/coast-"', self.app)
        self.assertIn('loadScript("/wind/coast.js")', self.app)
        self.assertLess(
            self.app.index('loadScript("vendor/leaflet/leaflet.js")'),
            self.app.index('loadScript("/wind/coast.js")'),
        )
        self.assertIn('pane: "basemap"', self.app)
        self.assertIn("maxZoom: 16", self.app)
        self.assertIn("maxNativeZoom: 12", self.app)
        self.assertIn("opts.leaflet", self.coast)

    def test_noaa_enc_chart_overlay_preserved(self):
        self.assertIn(
            "/proxy/enc/arcgis/rest/services/MarineChart_Services/NOAACharts/MapServer/WMTS",
            self.app,
        )
        self.assertIn('attribution: "Charts: NOAA ENC Chart Display Service"', self.app)
        self.assertIn("pane: \"chart\"", self.app)
        # Land fill is still keyed out so the Census backdrop shows through.
        self.assertIn("244", self.app)
        self.assertIn("232", self.app)
        self.assertIn("193", self.app)

    def test_day_and_night_census_palette_and_restyle(self):
        for blob in (self.css, self.app):
            self.assertIn("#F6F1E7", blob)
            self.assertIn("#1B4263", blob)
            self.assertIn("#EAF1F4", blob)
            self.assertIn("#0C2740", blob)
        self.assertIn("--coast-land", self.css)
        self.assertIn("--coast-water", self.css)
        self.assertIn("[data-theme=\"dark\"]", self.css)
        self.assertIn("layers.coast.restyle", self.app)
        self.assertIn("paintCoast", self.app)
        self.assertIn('paintCoast(fullscreen ? "dark" : currentTheme())', self.app)
        # Explicit hex palettes, so radar/SST can force night colors while the page stays in day mode.
        self.assertIn('land: dark ? "#1B4263" : "#F6F1E7"', self.app)
        self.assertIn("applyBasemapForTheme", self.app)

    def test_credits_include_census_and_noaa_not_esri(self):
        self.assertIn("U.S. Census Bureau (2025, 1:500,000", self.app)
        self.assertIn("not endorsed by the Census Bureau", self.app)
        self.assertIn("U.S. Census Bureau 2025 cartographic boundary files", self.html)
        self.assertIn("not endorsed by the Census Bureau", self.html)
        self.assertIn("NOAA Office of Coast Survey ENC Chart Display Service", self.html)
        self.assertNotIn("official chart", self.app.lower())
        self.assertNotIn("official NOAA ENC", self.html)
        # Safety note still points people to official NOAA charts for navigation.
        self.assertIn("Use official NOAA charts aboard", self.app)

    def test_lab_wind_still_uses_esri_and_is_unchanged_here(self):
        # Documented leftover: /lab/wind is private and still on Esri Canvas tiles.
        self.assertIn("services.arcgisonline.com/ArcGIS/rest/services/Canvas/World_", self.lab)
        self.assertIn("Light_Gray_Base", self.lab)
        self.assertIn("Dark_Gray_Base", self.lab)
        self.assertIn("www.esri.com", self.lab)


class Routes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import server
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.base = "http://127.0.0.1:%d" % cls.httpd.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def _get(self, path):
        req = urllib.request.Request(self.base + path)
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return r.status, r.read(), r.headers
        except urllib.error.HTTPError as e:
            return e.code, e.read(), e.headers

    def test_dashboard_page_and_assets_have_no_arcgisonline(self):
        with mock.patch.dict(os.environ, {"HOME_SHOWCASE": "0", "PREVIEW_KEY": ""}):
            status, body, _ = self._get("/dashboard")
        self.assertEqual(status, 200)
        text = body.decode("utf-8", "replace").lower()
        self.assertNotIn("arcgisonline", text)
        self.assertNotIn("esri.com", text)
        self.assertNotIn("map base tiles © esri", text)
        self.assertIn("census bureau", text)
        self.assertIn("enc chart display service", text)
        # Assets the page will load
        for path in ("/app.js", "/styles.css", "/wind/coast.js", "/wind/coast-lo.json", "/wind/coast-hi.json"):
            status, body, headers = self._get(path)
            self.assertEqual(status, 200, path)
            blob = body.decode("utf-8", "replace").lower()
            if path.endswith(".js") or path.endswith(".css"):
                self.assertNotIn("arcgisonline", blob, path)
                self.assertNotIn("esri.com", blob, path)

    def test_lab_wind_stays_private(self):
        with mock.patch.dict(os.environ, {"PREVIEW_KEY": "", "WIND_PARTICLES_ENABLED": ""}):
            status, _, _ = self._get("/lab/wind")
        self.assertEqual(status, 404)


if __name__ == "__main__":
    unittest.main()
