"""Public homepage (/) is the Hybrid page; the previous dashboard lives at /dashboard."""
from __future__ import annotations

import os
import sys
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import sprint_home  # noqa: E402
from test_sprint_home_preview import ALL_PHOTOS, fresh_jordan, salt  # noqa: E402

PREVIEW_IDS = ("carolina-kure", "corolla-duck", "cape-fear-river", "atlantic-beach", "cape-lookout", "new-bern")


def live(region_id="crystal-coast"):
    p = salt(region_id)
    p.pop("testData")
    return p


class HybridPublic(unittest.TestCase):
    KEY = "hybrid-public-test-key-24-chars!"

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

    def setUp(self):
        self._env = {k: os.environ.get(k) for k in ("PREVIEW_KEY", "MORNING_BRIEF_ENABLED", "FRESHWATER_ENABLED")}
        for k in self._env:
            os.environ.pop(k, None)
        self.calls = []

        def fake_assemble(rid=None, preview=False):
            self.calls.append(rid)
            return 200, live(rid or "crystal-coast")
        self.patches = [mock.patch.object(sprint_home, "approved_photos", return_value=ALL_PHOTOS),
                        mock.patch.object(sprint_home.conditions, "assemble", side_effect=fake_assemble)]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def _get(self, path, cookie=False):
        h = {}
        if cookie:
            os.environ["PREVIEW_KEY"] = self.KEY
            h["Cookie"] = "cb_preview=" + self.server._preview_cookie_value(self.KEY)
        c = HTTPConnection("127.0.0.1", self.port, timeout=20)
        c.request("GET", path, headers=h)
        r = c.getresponse()
        return r.status, {k.lower(): v for k, v in r.getheaders()}, r.read()

    def test_home_is_public_hybrid_without_concept_chrome(self):
        s, h, b = self._get("/")
        self.assertEqual(s, 200)
        self.assertIn(b'data-sprint="hybrid"', b)
        for bad in (b"Private concept", b"private concept", b"concept notes", b"noindex", b"Not public", b'class="pv-flag"',
                    b'id="sys-h"', b'="/preview/', b"/preview/sprint-home", b'class="test-banner"', b"TEST DATA"):
            self.assertNotIn(bad, b, bad)
        self.assertNotIn("noindex", h.get("x-robots-tag", ""))
        idx = (sprint_home.ROOT / "index.html").read_text(encoding="utf-8")
        for line in idx.splitlines():
            t = line.strip()
            if t.startswith(("<title>", '<meta name="description"', '<meta property="og:', '<meta name="twitter:')):
                self.assertIn(t.encode(), b)
        self.assertIn(b'<link rel="canonical" href="https://thecoastalbrief.com/">', b)
        self.assertIn(b"Sergiy Galyonkin", b)
        self.assertIn(b"https://creativecommons.org/licenses/by-sa/2.0/", b)
        self.assertIn(b"National Park Service, Cape Hatteras National Seashore (public domain)", b)
        self.assertIn(b"not weather, surf, or fishing advice", b)
        self.assertIn(b"not affiliated", b)
        self.assertIn(b"location is never requested", b)
        self.assertIn(b"data-wave-intro", b)
        self.assertIn(b'href="/dashboard?region=crystal-coast">Full dashboard', b)
        self.assertNotIn(b'href="/?region=crystal-coast">Full dashboard', b)
        self.assertIn(b"/home-photos/bodie-sunrise-800.webp", b)

    def test_index_html_path_is_hybrid_too(self):
        self.assertIn(b'data-sprint="hybrid"', self._get("/index.html")[2])

    def test_dashboard_serves_previous_homepage(self):
        s, h, b = self._get("/dashboard?region=hatteras")
        self.assertEqual(s, 200)
        self.assertIn(b'data-home="folio"', b)
        self.assertIn(b'id="cb-boot-conditions"', b)
        self.assertIn(b'id="region-select"', b)
        self.assertNotIn(b"data-wave-intro", b)
        self.assertIn(b'src="/app.js"', b)
        self.assertEqual(self._get("/dashboard/")[0], 200)

    def test_dashboard_freshwater_region_redirects_to_lake(self):
        for path in ("/dashboard?region=falls-lake", "/dashboard?region=jordan-lake"):
            s, h, _ = self._get(path)
            self.assertEqual(s, 303, path)
            self.assertTrue(h["location"].startswith("/lake?region="), path)

    def _fresh(self, rid, env=None):
        import freshwater
        payload = fresh_jordan()
        payload.pop("testData")
        payload["region"] = {"id": rid, "name": rid.replace("-", " ").title()}
        with mock.patch.object(freshwater, "assemble", return_value=(200, payload)):
            if env:
                os.environ.update(env)
            return self._get("/?region=" + rid)

    def _no_concept(self, b):
        for bad in (b"Private concept", b"private concept", b"concept notes", b"noindex", b'class="pv-flag"',
                    b'id="sys-h"', b'="/preview/', b"/preview/sprint-home", b'class="test-banner"', b"TEST DATA"):
            self.assertNotIn(bad, b, bad)

    def test_falls_lake_renders_fresh_hybrid_with_pier_hero(self):
        s, h, b = self._fresh("falls-lake")
        self.assertEqual(s, 200)
        self.assertIn(b'data-sprint="hybrid" data-water="fresh"', b)
        self.assertIn(b"/home-photos/falls-lake-pier-800", b)
        self.assertIn(b"Sergiy Galyonkin", b)
        self.assertIn(b'href="/lake?region=falls-lake">Full dashboard', b)
        self.assertIn(b'href="/brief?region=falls-lake"', b)
        self.assertIn(b'<a href="/?region=falls-lake" aria-current="page">Freshwater</a>', b)
        self._no_concept(b)
        self.assertNotIn("noindex", h.get("x-robots-tag", ""))

    def test_jordan_lake_has_no_falls_lake_photo(self):
        s, _, b = self._fresh("jordan-lake")
        self.assertEqual(s, 200)
        self.assertIn(b'data-sprint="hybrid" data-water="fresh"', b)
        self.assertNotIn(b"falls-lake-pier", b)
        self.assertIn(b'class="hz-none"', b)
        self.assertIn(b'href="/lake?region=jordan-lake">Full dashboard', b)
        self.assertNotIn(b'href="/brief?region=', b.split(b'class="cg-foot"')[1].split(b"</section>")[0])
        self._no_concept(b)

    def test_neuse_renders(self):
        s, _, b = self._fresh("neuse-river")
        self.assertEqual(s, 200)
        self.assertIn(b'data-sprint="hybrid" data-water="fresh"', b)
        self.assertIn(b'href="/lake?region=neuse-river">Full dashboard', b)
        self._no_concept(b)

    def test_cape_fear_404_without_cookie(self):
        self.assertEqual(self._fresh("cape-fear-river")[0], 404)
        b = sprint_home.page("hybrid", "cape-fear-river", public=True)
        self.assertNotIn(b"cape-fear-river", b)
        self.assertIn(b'data-sprint="hybrid" data-water="salt"', b)

    def test_freshwater_flag_off_falls_back(self):
        s, _, b = self._fresh("falls-lake", env={"FRESHWATER_ENABLED": "0"})
        self.assertEqual(s, 200)
        self.assertIn(b'data-sprint="hybrid" data-water="salt"', b)
        self.assertNotIn(b"falls-lake-pier", b)

    def test_preview_regions_404_publicly_and_never_listed(self):
        s, _, b = self._get("/")
        for rid in PREVIEW_IDS:
            self.assertNotIn(("region=%s" % rid).encode(), b, rid)
        for rid in ("carolina-kure", "corolla-duck", "cape-fear-river"):
            self.assertEqual(self._get("/?region=%s" % rid)[0], 404, rid)
            self.assertEqual(self._get("/dashboard?region=%s" % rid)[0], 404, rid)
        # the public rail matches the public picker
        for rid in ("crystal-coast", "hatteras", "wilmington", "nags-head", "emerald-isle", "topsail"):
            self.assertIn(('href="/?region=%s"' % rid).encode(), b, rid)
        for rid in ("falls-lake", "jordan-lake", "neuse-river"):
            self.assertIn(('href="/?region=%s"' % rid).encode(), b, rid)

    def test_rail_never_lists_preview_regions(self):
        groups = sprint_home.public_region_groups("")
        ids = {r for _, items in groups for r, *_ in items}
        self.assertFalse(ids & set(PREVIEW_IDS), ids)

    def test_unknown_or_nonpublic_region_falls_back_to_default(self):
        self.calls.clear()
        s, _, b = self._get("/?region=../../etc")
        self.assertEqual(s, 200)
        self.assertEqual(self.calls[-1], None)
        b2 = sprint_home.page("hybrid", "carolina-kure", public=True)
        self.assertEqual(self.calls[-1], None)
        self.assertNotIn(b"carolina-kure", b2)

    def test_test_data_not_publicly_triggerable(self):
        for q in ("?testData=1", "?test=1", "?sim=1", "?shot=1&testData=true"):
            s, _, b = self._get("/" + q)
            self.assertEqual(s, 200, q)
            self.assertNotIn(b"TEST DATA", b, q)
            self.assertNotIn(b"data-shot", b, q)

    def test_public_photo_route(self):
        s, h, b = self._get("/home-photos/bodie-sunrise-800.webp")
        self.assertEqual(s, 200)
        self.assertEqual(h["content-type"], "image/webp")
        self.assertIn("max-age=86400", h.get("cache-control", ""))
        self.assertEqual(self._get("/home-photos/falls-lake-pier-1280.avif")[0], 200)
        for bad in ("/home-photos/", "/home-photos/../server.py", "/home-photos/%2e%2e/server.py",
                    "/home-photos/..%2fCREDITS.md", "/home-photos/CREDITS.md", "/home-photos/bodie-sunrise-800.png",
                    "/home-photos/falls_lake_grade.py", "/home-photos/nope-800.webp"):
            self.assertEqual(self._get(bad)[0], 404, bad)
        # the private route stays cookie-gated
        self.assertEqual(self._get("/preview/sprint-home/photos/bodie-sunrise-800.webp")[0], 404)

    def test_private_hybrid_preview_unchanged(self):
        s, _, b = self._get("/preview/home-hybrid", cookie=True)
        self.assertEqual(s, 200)
        self.assertIn(b"Private concept", b)
        self.assertIn(b"concept notes", b)
        self.assertIn(b"noindex", b)
        self.assertEqual(self._get("/preview/home-hybrid")[0], 404)

    def test_brief_kill_switch_drops_brief_links(self):
        os.environ["MORNING_BRIEF_ENABLED"] = "0"
        b = self._get("/")[2]
        self.assertNotIn(b'href="/brief', b)


if __name__ == "__main__":
    unittest.main()
