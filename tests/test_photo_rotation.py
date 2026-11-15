"""Daily featured photo (photo_rotation): ET-day selection, manifest validation and fallback,
category/location interleaving, preview-only overrides, and the preload matching the photo."""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import threading
import unittest
from datetime import date, datetime, timezone
from http.client import HTTPConnection
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import photo_rotation as R  # noqa: E402
import sprint_home  # noqa: E402

FIX = R.FIXTURE


def entry(i, cat, loc=None, **kw):
    e = {"id": "p%d" % i, "category": cat, "location": loc or "Place %d" % i, "description": "d%d" % i,
         "alt": "alt %d" % i, "photographer": "", "credit": "Community photo · Catch Wall", "license": "",
         "license_url": "", "source_url": "", "width": 1600, "height": 1200,
         "sources": {"webp": {"800": "photos/bodie-sunrise-800.webp"}, "jpg": {"800": "photos/bodie-sunrise-800.jpg"}},
         "placeholder": "#334455", "focal": "50% 50%", "approved": True}
    e.update(kw)
    return e


def write_manifest(entries, d: Path) -> Path:
    (d / "photos").mkdir(exist_ok=True)
    for f in ("bodie-sunrise-800.webp", "bodie-sunrise-800.jpg"):
        (d / "photos" / f).write_bytes((FIX.parent / "photos" / f).read_bytes())
    p = d / "manifest.json"
    p.write_text(json.dumps({"photos": entries}))
    return p


def assert_interleaved(tc, order):
    n = len(order)
    for i in range(n):
        a, b = order[i], order[(i + 1) % n]   # includes the wrap, last -> first
        tc.assertNotEqual(a["category"], b["category"], (i, a["id"], b["id"]))
        tc.assertNotEqual(R.loc_key(a), R.loc_key(b), (i, a["id"], b["id"]))


class Selection(unittest.TestCase):
    def setUp(self):
        self.man = R.load(FIX)
        self.photos = [dict(p, sources={"jpg": {800: "x.jpg"}}) if p.get("catch_wall_id") else p for p in self.man["photos"]]

    def test_et_midnight_boundary(self):
        # 23:59:59 ET on Nov 15 (04:59:59Z Nov 16) is still Nov 15; 00:00:00 ET is Nov 16.
        before = datetime(2026, 11, 16, 4, 59, 59, tzinfo=timezone.utc)
        after = datetime(2026, 11, 16, 5, 0, 0, tzinfo=timezone.utc)
        self.assertEqual(R.et_date(before), date(2026, 11, 15))
        self.assertEqual(R.et_date(after), date(2026, 11, 16))
        self.assertNotEqual(R.pick(self.photos, R.et_date(before))["id"], R.pick(self.photos, R.et_date(after))["id"])

    def test_dst_change_dates(self):
        # Spring forward (Mar 8 2026, ET midnight = 05:00Z before, 04:00Z after) and fall back (Nov 1 2026).
        self.assertEqual(R.et_date(datetime(2026, 3, 9, 3, 59, 59, tzinfo=timezone.utc)), date(2026, 3, 8))
        self.assertEqual(R.et_date(datetime(2026, 3, 9, 4, 0, 0, tzinfo=timezone.utc)), date(2026, 3, 9))
        self.assertEqual(R.et_date(datetime(2026, 11, 1, 3, 59, 59, tzinfo=timezone.utc)), date(2026, 10, 31))
        self.assertEqual(R.et_date(datetime(2026, 11, 1, 4, 0, 0, tzinfo=timezone.utc)), date(2026, 11, 1))
        # 23:30 ET on the fall-back day (UTC-5) is still Nov 1.
        self.assertEqual(R.et_date(datetime(2026, 11, 2, 4, 30, tzinfo=timezone.utc)), date(2026, 11, 1))

    def test_same_photo_all_day_and_deterministic(self):
        d = date(2026, 11, 15)
        ids = {R.pick(self.photos, d)["id"] for _ in range(5)}
        self.assertEqual(len(ids), 1)
        order = R.rotation_order(self.photos)
        self.assertEqual(R.pick(self.photos, d)["id"], order[d.toordinal() % len(order)]["id"])


class Manifest(unittest.TestCase):
    def test_fixture_is_valid_and_approved_only(self):
        man = R.load(FIX)
        ids = [p["id"] for p in man["photos"]]
        self.assertIn("bodie-sunrise", ids)
        self.assertIn("falls-lake-pier", ids)
        self.assertNotIn("cw-striped-bass-roanoke", ids)   # approved:false
        self.assertIn(("cw-striped-bass-roanoke", "not approved"), man["skipped"])
        falls = next(p for p in man["photos"] if p["id"] == "falls-lake-pier")
        self.assertIn("Falls Lake", falls["location"])

    def test_bad_entries_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            bad = [entry(1, "saltwater"), entry(2, "ocean"), entry(3, "heritage", approved="yes"),
                   entry(4, "lifestyle", sources={"jpg": {"800": "../etc/passwd.jpg"}}),
                   entry(5, "freshwater", license="CC BY 2.0", license_url=""),
                   entry(6, "freshwater", placeholder="red"), entry(1, "heritage")]
            man = R.load(write_manifest(bad, Path(d)))
            self.assertEqual([p["id"] for p in man["photos"]], ["p1"])
            self.assertEqual(len(man["skipped"]), 6)

    def test_fallback_to_fixture(self):
        with tempfile.TemporaryDirectory() as d:
            broken = Path(d) / "manifest.json"
            broken.write_text("{not json")
            with mock.patch.object(R, "manifest_candidates", return_value=[Path(d) / "missing.json", broken, FIX]):
                self.assertEqual(R.active()["path"], FIX)
            only_unapproved = write_manifest([entry(1, "saltwater", approved=False)], Path(d))
            with mock.patch.object(R, "manifest_candidates", return_value=[only_unapproved, FIX]):
                self.assertEqual(R.active()["path"], FIX)
            good = write_manifest([entry(1, "saltwater"), entry(2, "heritage")], Path(d))
            with mock.patch.object(R, "manifest_candidates", return_value=[good, FIX]):
                self.assertEqual(R.active()["path"], good)

    def test_env_path_first(self):
        with mock.patch.dict(os.environ, {"PHOTO_ROTATION_MANIFEST": "/tmp/x.json"}):
            self.assertEqual(R.manifest_candidates()[0], Path("/tmp/x.json"))


class Order(unittest.TestCase):
    def test_fixture_cycle_with_wrap(self):
        man = R.load(FIX)
        order = R.rotation_order(man["photos"])
        self.assertEqual(len(order), len(man["photos"]))
        assert_interleaved(self, order)
        # Full calendar cycle: consecutive days never repeat category or location.
        days = [R.pick(man["photos"], date.fromordinal(date(2026, 11, 1).toordinal() + i)) for i in range(len(order) * 2)]
        for a, b in zip(days, days[1:]):
            self.assertNotEqual(a["category"], b["category"])
            self.assertNotEqual(R.loc_key(a), R.loc_key(b))

    def test_balanced_set_is_plain_cycle(self):
        ps = [entry(i, c) for i, c in enumerate(R.CATEGORIES * 3)]
        order = R.rotation_order(ps)
        self.assertEqual([p["category"] for p in order[:4]], list(R.CATEGORIES))
        assert_interleaved(self, order)

    def test_uneven_and_shared_locations(self):
        ps = [entry(0, "saltwater", "Beaufort"), entry(1, "saltwater", "Beaufort"), entry(2, "saltwater"),
              entry(3, "heritage", "Beaufort"), entry(4, "freshwater"), entry(5, "lifestyle", "Rx Chicken& Oysters"),
              entry(6, "lifestyle", "Rx Chicken & Oysters"), entry(7, "freshwater")]
        order = R.rotation_order(ps)
        self.assertEqual(sorted(p["id"] for p in order), sorted(p["id"] for p in ps))
        assert_interleaved(self, order)

    def test_impossible_set_still_returns_everything(self):
        ps = [entry(i, "heritage") for i in range(3)] + [entry(9, "saltwater")]
        order = R.rotation_order(ps)
        self.assertEqual(len(order), 4)


class Render(unittest.TestCase):
    def test_preload_matches_chosen_photo(self):
        p = R.featured(photo_id="bodie-sunrise", approved=[])
        pre = R.preload_html(p)
        pic = R.picture_html(p)
        first = re.search(r'<source type="([^"]+)" srcset="([^"]+)"', pic)
        self.assertIn('type="%s"' % first.group(1), pre)
        self.assertIn('imagesrcset="%s"' % first.group(2), pre)
        self.assertIn('fetchpriority="high"', pre)
        self.assertIn('imagesizes="100vw"', pre)
        self.assertIn('width="1600" height="1200"', pic)
        self.assertIn("image/webp", pic)
        self.assertIn("-800.jpg", pic)
        self.assertIn('alt="%s"' % p["alt"].replace("'", "&#x27;"), pic)

    def test_page_preload_and_hero_agree(self):
        for pid in ("bodie-sunrise", "falls-lake-pier"):
            f = R.featured(photo_id=pid, approved=[])
            with mock.patch.object(sprint_home, "_featured", return_value=f):
                from test_sprint_home_preview import render, salt
                h = render("hybrid", salt("wilmington"))
            self.assertIn('data-photo="%s"' % pid, h)
            self.assertIn(R.preload_html(f).strip(), h)
            self.assertEqual(h.count('rel="preload" as="image"'), 1)

    def test_licenses(self):
        falls = R.credit_html(R.featured(photo_id="falls-lake-pier", approved=[]))
        self.assertIn('href="https://creativecommons.org/licenses/by-sa/2.0/" rel="noopener license">CC BY-SA 2.0</a>', falls)
        self.assertIn('href="https://www.flickr.com/photos/sergesegal/52741376400/" rel="noopener">Sergiy Galyonkin</a>', falls)
        self.assertIn("public domain", R.credit_html(R.featured(photo_id="bodie-sunrise", approved=[])))

    def test_community_entry_uses_store_and_drops_when_unapproved(self):
        rec = {"id": "3e41ed83-23a3-4032-8a5f-c7957b788e3f", "src": {"800": "https://x.example/a-800.webp", "1600": "https://x.example/a-1600.webp"}}
        p = R.featured(photo_id="cw-red-drum-new-bern", approved=[rec])
        self.assertEqual(p["sources"], {"webp": {800: rec["src"]["800"], 1600: rec["src"]["1600"]}})
        self.assertIn("Community photo · Catch Wall", R.horizon_html(p))
        # Not in the approved store: the override is ignored and a manifest photo shows instead.
        self.assertNotEqual(R.featured(photo_id="cw-red-drum-new-bern", approved=[])["id"], "cw-red-drum-new-bern")


class Overrides(unittest.TestCase):
    KEY = "photo-rotation-test-key-24chars!"

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
        from test_hybrid_public import live
        from test_sprint_home_preview import ALL_PHOTOS
        self._env = {k: os.environ.get(k) for k in ("PREVIEW_KEY", "FRESHWATER_ENABLED")}
        os.environ["PREVIEW_KEY"] = self.KEY
        os.environ.pop("FRESHWATER_ENABLED", None)
        self.patches = [mock.patch.object(sprint_home, "approved_photos", return_value=ALL_PHOTOS),
                        mock.patch.object(sprint_home.conditions, "assemble", side_effect=lambda rid=None, preview=False: (200, live(rid or "crystal-coast"))),
                        mock.patch.object(R, "manifest_candidates", return_value=[FIX])]
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
        c = HTTPConnection("127.0.0.1", self.port, timeout=20)
        h = {"Cookie": "cb_preview=%s" % self.server._preview_cookie_value(self.KEY)} if cookie else {}
        c.request("GET", path, headers=h)
        r = c.getresponse()
        return r.status, r.read()

    def _photo(self, body):
        m = re.search(rb'data-photo="([a-z0-9-]+)"', body)
        return m.group(1).decode() if m else None

    def test_public_path_ignores_overrides(self):
        today = R.featured(approved=sprint_home.approved_photos())["id"]
        other = next(p["id"] for p in R.load(FIX)["photos"] if p["id"] != today)
        for q in ("/?photo=%s" % other, "/?date=2027-01-01", "/?region=crystal-coast&photo=%s" % other):
            s, b = self._get(q, cookie=True)
            self.assertEqual(s, 200)
            self.assertEqual(self._photo(b), today, q)

    def test_preview_route_honours_overrides(self):
        s, b = self._get("/preview/home-hybrid?photo=falls-lake-pier", cookie=True)
        self.assertEqual((s, self._photo(b)), (200, "falls-lake-pier"))
        man = R.load(FIX)
        d = date(2027, 1, 1)
        s, b = self._get("/preview/home-hybrid?date=%s" % d.isoformat(), cookie=True)
        want = R.featured(day=d, approved=sprint_home.approved_photos(), manifest=man)["id"]
        self.assertEqual(self._photo(b), want)
        s, _ = self._get("/preview/home-hybrid?photo=falls-lake-pier")   # no cookie: gated
        self.assertEqual(s, 404)

    def test_only_manifest_files_are_served(self):
        s, b = self._get("/featured-photos/photos/bodie-sunrise-800.jpg")
        self.assertEqual(s, 200)
        self.assertTrue(b.startswith(b"\xff\xd8"))
        for bad in ("/featured-photos/photos/../../server.py", "/featured-photos/CREDITS.md", "/featured-photos/photos/nope-800.jpg"):
            self.assertEqual(self._get(bad)[0], 404, bad)


if __name__ == "__main__":
    unittest.main()
