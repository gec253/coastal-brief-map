"""HTTP gating for private Wilmington, Nags Head and Emerald Isle saltwater previews."""
from __future__ import annotations

import json
import os
import sys
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


STUB = {
    "ok": True,
    "region": {"id": "wilmington", "name": "Wilmington · Wrightsville Beach"},
    "readings": {"wind": {"status": "ok", "station": {"id": "8658163", "name": "Wrightsville Beach, Johnnie Mercer's Pier"}}},
    "tides": {"status": "ok"},
}


class SaltPreviewGating(unittest.TestCase):
    KEY = "preview-test-key-24-chars-ok"

    @classmethod
    def setUpClass(cls):
        import server
        cls.server = server
        cls.httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        cls.host, cls.port = cls.httpd.server_address

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def _req(self, path, env=None, cookie=None):
        saved = {k: os.environ.get(k) for k in ("PREVIEW_KEY", "FRESHWATER_ENABLED")}
        try:
            os.environ.pop("PREVIEW_KEY", None)
            if env:
                os.environ.update({k: v for k, v in env.items() if v is not None})
                for k, v in env.items():
                    if v is None:
                        os.environ.pop(k, None)
            headers = {}
            if cookie:
                headers["Cookie"] = cookie
            conn = HTTPConnection("127.0.0.1", self.port, timeout=8)
            conn.request("GET", path, headers=headers)
            resp = conn.getresponse()
            body = resp.read()
            hdrs = {k.lower(): v for k, v in resp.getheaders()}
            conn.close()
            return resp.status, body, hdrs
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    def _cookie(self):
        return "%s=%s" % (self.server.PREVIEW_COOKIE, self.server._preview_cookie_value(self.KEY))

    def test_public_home_and_existing_regions_are_200(self):
        status, body, _ = self._req("/")
        self.assertEqual(status, 200)
        self.assertIn(b"The Coastal Brief", body)
        self.assertNotIn(b"private preview", body.lower())
        status, body, _ = self._req("/api/regions")
        self.assertEqual(status, 200)
        data = json.loads(body)
        ids = [r["id"] for r in data["regions"]]
        self.assertEqual(ids, ["crystal-coast", "hatteras"])
        self.assertNotIn("wilmington", ids)
        self.assertNotIn("nags-head", ids)
        self.assertNotIn("emerald-isle", ids)

    def test_preview_regions_404_publicly(self):
        for path in (
            "/?region=wilmington",
            "/?region=nags-head",
            "/?region=emerald-isle",
            "/api/conditions?region=wilmington",
            "/api/conditions?region=nags-head",
            "/api/conditions?region=emerald-isle",
        ):
            status, _, _ = self._req(path)
            self.assertEqual(status, 404, path)

    def test_preview_cookie_unlocks_pages_and_api(self):
        env = {"PREVIEW_KEY": self.KEY}
        cookie = self._cookie()
        with patch("conditions.assemble", return_value=(200, STUB)):
            for path in ("/?region=wilmington", "/?region=nags-head", "/?region=emerald-isle"):
                status, body, headers = self._req(path, env=env, cookie=cookie)
                self.assertEqual(status, 200, path)
                self.assertIn(b"The Coastal Brief", body)
                robots = (headers.get("x-robots-tag") or "").lower()
                self.assertIn("noindex", robots, path)
            status, body, _ = self._req("/api/conditions?region=wilmington", env=env, cookie=cookie)
            self.assertEqual(status, 200)
            self.assertTrue(json.loads(body)["ok"])
            status, body, _ = self._req("/api/conditions?region=nags-head", env=env, cookie=cookie)
            self.assertEqual(status, 200)

    def test_api_regions_gains_preview_regions_only_with_cookie(self):
        env = {"PREVIEW_KEY": self.KEY}
        status, body, _ = self._req("/api/regions", env=env)
        ids = [r["id"] for r in json.loads(body)["regions"]]
        self.assertEqual(ids, ["crystal-coast", "hatteras"])
        status, body, _ = self._req("/api/regions", env=env, cookie=self._cookie())
        data = json.loads(body)
        ids = [r["id"] for r in data["regions"]]
        self.assertEqual(ids, ["crystal-coast", "hatteras", "wilmington", "nags-head", "emerald-isle"])
        preview = {r["id"]: r.get("preview") for r in data["regions"]}
        self.assertTrue(preview["wilmington"])
        self.assertTrue(preview["nags-head"])
        self.assertTrue(preview["emerald-isle"])
        self.assertIsNone(preview["crystal-coast"])

    def test_wrong_or_missing_key_still_404s(self):
        env = {"PREVIEW_KEY": self.KEY}
        status, _, _ = self._req("/?region=wilmington", env=env)
        self.assertEqual(status, 404)
        status, _, _ = self._req(
            "/?region=wilmington", env=env,
            cookie="%s=deadbeef" % self.server.PREVIEW_COOKIE,
        )
        self.assertEqual(status, 404)


if __name__ == "__main__":
    unittest.main()
