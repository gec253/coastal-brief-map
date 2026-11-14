"""Private /preview/identity gating; public homepage stays the published design."""
from __future__ import annotations

import os
import re
import sys
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ROOT = Path(__file__).resolve().parents[1]


def _slice(body: bytes, start: bytes, end: bytes) -> bytes:
    i = body.find(start)
    if i < 0:
        return b""
    j = body.find(end, i)
    return body[i:j] if j >= 0 else body[i:]


class IdentityPreview(unittest.TestCase):
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
        saved = {k: os.environ.get(k) for k in ("PREVIEW_KEY", "MORNING_BRIEF_ENABLED", "FRESHWATER_ENABLED")}
        try:
            os.environ.pop("PREVIEW_KEY", None)
            if env:
                for k, v in env.items():
                    if v is None:
                        os.environ.pop(k, None)
                    else:
                        os.environ[k] = v
            headers = {}
            if cookie:
                headers["Cookie"] = cookie
            conn = HTTPConnection("127.0.0.1", self.port, timeout=12)
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

    def test_preview_404_without_cookie(self):
        for path in ("/preview/identity", "/preview/identity.css", "/preview/identity?shot=1"):
            status, _, _ = self._req(path)
            self.assertEqual(status, 404, path)
            status, _, _ = self._req(path, env={"PREVIEW_KEY": self.KEY})
            self.assertEqual(status, 404, path + " key set, no cookie")

    def test_public_homepage_unchanged(self):
        status, body, hdrs = self._req("/")
        self.assertEqual(status, 200)
        self.assertNotIn("noindex", hdrs.get("x-robots-tag", ""))
        self.assertIn(b'data-concept="a"', body)
        self.assertIn(b'data-home="magazine"', body)
        self.assertIn(b"home-photo-band", body)
        self.assertIn(b"/featured/bodie-sunrise", body)
        self.assertIn(b"Live marine instruments", body)
        self.assertNotIn(b"data-identity-sprint", body)
        self.assertNotIn(b"data-preview", body)
        self.assertNotIn(b"mast-motto", body)
        self.assertNotIn(b"folio-photo", body)
        self.assertNotIn(b"folio-rail", body)
        self.assertNotIn(b"/preview/identity", body)
        # Photo band still sits above the conditions panel on the public homepage.
        self.assertLess(body.find(b"home-photo-band"), body.find(b'id="conditions"'))

    def test_public_homepage_unchanged_with_preview_cookie(self):
        status, body, hdrs = self._req("/", env={"PREVIEW_KEY": self.KEY}, cookie=self._cookie())
        self.assertEqual(status, 200)
        self.assertIn(b'data-home="magazine"', body)
        self.assertNotIn(b"data-identity-sprint", body)
        self.assertNotIn(b"data-preview", body)
        self.assertNotIn("noindex", hdrs.get("x-robots-tag", ""))

    def test_cookie_unlocks_identity_preview(self):
        env = {"PREVIEW_KEY": self.KEY}
        ck = self._cookie()
        status, body, hdrs = self._req("/preview/identity", env=env, cookie=ck)
        self.assertEqual(status, 200)
        self.assertEqual(hdrs.get("cache-control"), "no-store")
        self.assertIn("noindex", hdrs.get("x-robots-tag", ""))
        self.assertIn(b'name="robots" content="noindex, nofollow"', body)
        self.assertIn(b"data-identity-sprint", body)
        self.assertIn(b"data-preview", body)
        self.assertIn(b'data-concept="a"', body)
        self.assertIn(b"Know the Water. Live the Coast.", body)
        self.assertIn(b'id="conditions"', body)
        self.assertIn(b"folio-photo", body)
        self.assertIn(b"/featured/bodie-sunrise", body)
        self.assertIn(b"Photograph: U.S. National Park Service, Cape Hatteras National Seashore", body)
        self.assertIn(b"folio-rail", body)
        self.assertIn(b"Falls Lake", body)
        self.assertIn(b'id="region-select"', body)
        self.assertIn(b'id="region-nav"', body)
        self.assertNotIn(b"home-photo-band", body)
        # Photo strip comes after the conditions panel, before tide search.
        cond = body.find(b'id="conditions"')
        photo = body.find(b'<section class="folio-photo"')
        tide = body.find(b'id="tide-search"')
        self.assertTrue(0 < cond < photo < tide, (cond, photo, tide))

        status, css, hdrs = self._req("/preview/identity.css", env=env, cookie=ck)
        self.assertEqual(status, 200)
        self.assertEqual(hdrs.get("cache-control"), "no-store")
        self.assertIn("noindex", hdrs.get("x-robots-tag", ""))
        self.assertIn(b"data-identity-sprint", css)

    def test_no_value_or_label_drift(self):
        env = {"PREVIEW_KEY": self.KEY}
        ck = self._cookie()
        pub_status, pub, _ = self._req("/")
        status, body, _ = self._req("/preview/identity", env=env, cookie=ck)
        self.assertEqual(pub_status, 200)
        self.assertEqual(status, 200)
        for label in (b">Wind<", b">Seas<", b">Water<", b">Next low<", b'data-title="Tide"', b"Observed", b"Forecast", b"Predicted"):
            self.assertIn(label, pub)
            self.assertIn(label, body)
        pub_glance = _slice(pub, b'id="glance-strip"', b"</nav>")
        id_glance = _slice(body, b'id="glance-strip"', b"</nav>")
        self.assertTrue(pub_glance)
        self.assertEqual(pub_glance, id_glance)
        # Event names and until-lines must match the public homepage.
        pub_ev = re.findall(br'class="al-ev">([^<]+)', pub)
        id_ev = re.findall(br'class="al-ev">([^<]+)', body)
        self.assertEqual(pub_ev, id_ev)
        pub_meta = re.findall(br'class="al-meta">([^<]+)', pub)
        id_meta = re.findall(br'class="al-meta">([^<]+)', body)
        self.assertEqual(pub_meta, id_meta)
        # No invented lake photograph.
        self.assertNotIn(b"falls-lake", _slice(body, b'<section class="folio-photo"', b"</section>").lower())

    def test_hub_lists_identity_card(self):
        status, body, hdrs = self._req("/preview", env={"PREVIEW_KEY": self.KEY}, cookie=self._cookie())
        self.assertEqual(status, 200)
        self.assertIn("noindex", hdrs.get("x-robots-tag", ""))
        self.assertIn(b'href="/preview/identity"', body)
        self.assertIn(b"Chartroom Folio", body)
