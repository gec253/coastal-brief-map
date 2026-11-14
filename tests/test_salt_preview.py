"""Saltwater region gating over HTTP.

Wilmington, Nags Head, Emerald Isle and Topsail went public on 14 Nov 2026 (Ed's OK). The preview
gate itself still exists for future regions, so it is tested with a fake previewReady region.
The Morning Brief stays limited to Crystal Coast and Hatteras (plus Falls Lake)."""
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

SALT_PUBLIC = ["crystal-coast", "hatteras", "wilmington", "nags-head", "emerald-isle", "topsail"]
NEW_PUBLIC = ["wilmington", "nags-head", "emerald-isle", "topsail"]


import conditions  # noqa: E402

_REAL_LOAD_REGIONS = conditions.load_regions


def _cfg_with_fake_preview():
    cfg = _REAL_LOAD_REGIONS()
    fake = dict(next(r for r in cfg["regions"] if r["id"] == "wilmington"), id="fixture-preview", enabled=False)
    cfg["regions"].append(fake)
    return cfg


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

    def test_api_regions_lists_six_saltwater_regions(self):
        status, body, _ = self._req("/api/regions")
        self.assertEqual(status, 200)
        data = json.loads(body)
        ids = [r["id"] for r in data["regions"]]
        self.assertEqual(ids, SALT_PUBLIC)
        self.assertFalse(any(r.get("preview") for r in data["regions"]))
        for rid in ("atlantic-beach", "cape-lookout", "new-bern"):
            self.assertNotIn(rid, ids)
        # Same list with a preview cookie: nothing extra and nothing flagged.
        env = {"PREVIEW_KEY": self.KEY}
        status, body, _ = self._req("/api/regions", env=env, cookie=self._cookie())
        data = json.loads(body)
        self.assertEqual([r["id"] for r in data["regions"]], SALT_PUBLIC)
        self.assertFalse(any(r.get("preview") for r in data["regions"]))

    def test_new_regions_are_public_without_cookie(self):
        stub = lambda rid=None, preview=False: (200, dict(STUB, region={"id": rid, "name": rid}))
        with patch("conditions.assemble", side_effect=stub):
            for rid in NEW_PUBLIC:
                status, body, headers = self._req("/?region=" + rid)
                self.assertEqual(status, 200, rid)
                self.assertIn(b"The Coastal Brief", body)
                self.assertNotIn("noindex", (headers.get("x-robots-tag") or "").lower(), rid)
                self.assertNotIn(b'content="noindex', body, rid)
                status, body, headers = self._req("/api/conditions?region=" + rid)
                self.assertEqual(status, 200, rid)
                self.assertTrue(json.loads(body)["ok"])
                self.assertIn("public", headers.get("cache-control", ""), rid)

    def test_new_regions_have_no_morning_brief(self):
        import brief
        self.assertEqual(brief.enabled_regions(include_fresh=False), ["crystal-coast", "hatteras"])
        self.assertEqual(brief.enabled_regions(include_fresh=True), ["crystal-coast", "hatteras", "falls-lake"])
        for rid in NEW_PUBLIC:
            for path in ("/brief?region=" + rid, "/api/brief?region=" + rid):
                status, _, _ = self._req(path)
                self.assertEqual(status, 404, path)
        for rid in ("crystal-coast", "hatteras"):
            r = next(x for x in brief.conditions.load_regions()["regions"] if x["id"] == rid)
            self.assertIs(r.get("brief"), True, rid)
        # The 5:16 AM wake (and so the workflow's verify/archive) reports only the brief regions.
        from datetime import datetime, timezone
        early = datetime(2026, 11, 15, 9, 0, tzinfo=timezone.utc)  # 4:00 AM ET: builds nothing
        w = brief.wake(include_fresh=True, now=early, background=False)
        self.assertEqual(w["building"], 0)
        self.assertEqual(sorted(w["regions"]), ["crystal-coast", "falls-lake", "hatteras"])

    def test_preview_region_404s_publicly(self):
        with patch("conditions.load_regions", side_effect=_cfg_with_fake_preview):
            for path in ("/?region=fixture-preview", "/api/conditions?region=fixture-preview"):
                status, _, _ = self._req(path)
                self.assertEqual(status, 404, path)
            status, body, _ = self._req("/api/regions")
            self.assertEqual([r["id"] for r in json.loads(body)["regions"]], SALT_PUBLIC)

    def test_preview_cookie_unlocks_pages_and_api(self):
        env = {"PREVIEW_KEY": self.KEY}
        cookie = self._cookie()
        with patch("conditions.load_regions", side_effect=_cfg_with_fake_preview), \
                patch("conditions.assemble", return_value=(200, STUB)):
            status, body, headers = self._req("/?region=fixture-preview", env=env, cookie=cookie)
            self.assertEqual(status, 200)
            self.assertIn(b"The Coastal Brief", body)
            self.assertIn("noindex", (headers.get("x-robots-tag") or "").lower())
            status, body, _ = self._req("/api/conditions?region=fixture-preview", env=env, cookie=cookie)
            self.assertEqual(status, 200)
            self.assertTrue(json.loads(body)["ok"])
            status, body, _ = self._req("/api/regions", env=env, cookie=cookie)
            data = json.loads(body)
            self.assertEqual([r["id"] for r in data["regions"]], SALT_PUBLIC + ["fixture-preview"])
            self.assertTrue(data["regions"][-1].get("preview"))

    def test_wrong_or_missing_key_still_404s(self):
        env = {"PREVIEW_KEY": self.KEY}
        with patch("conditions.load_regions", side_effect=_cfg_with_fake_preview):
            status, _, _ = self._req("/?region=fixture-preview", env=env)
            self.assertEqual(status, 404)
            status, _, _ = self._req(
                "/?region=fixture-preview", env=env,
                cookie="%s=deadbeef" % self.server.PREVIEW_COOKIE,
            )
            self.assertEqual(status, 404)
        for path in ("/preview", "/preview/photos-check", "/preview/masthead"):
            status, _, _ = self._req(path)
            self.assertEqual(status, 404, path)


if __name__ == "__main__":
    unittest.main()
