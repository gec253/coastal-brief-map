"""Private Catch Wall redesign: /preview/catch-wall (presentation only)."""
from __future__ import annotations

import os
import re
import sys
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import catch_wall_preview as cwp  # noqa: E402

STORE = "https://example.supabase.co/storage/v1/object/public/photos-approved/"


def ph(pid, **kw):
    p = {"id": pid, "category": "fishing", "water": "saltwater", "w": 4032, "h": 3024, "name": "", "species": "",
         "location": "", "region": "", "takenOn": "", "caption": "", "featured": False,
         "src": {k: "%s%s/%s.webp" % (STORE, pid, k) for k in ("400", "800", "1600")}}
    p.update(kw)
    return p


APPROVED = [
    ph("aaaaaaaa-0000-0000-0000-000000000001", water="freshwater", location="Weldon", w=3024, h=4032),
    ph("aaaaaaaa-0000-0000-0000-000000000002", species="Striped Bass", location="Roanoke River"),
    ph("aaaaaaaa-0000-0000-0000-000000000003", species="Red Drum", region="New Bern \u00b7 Neuse River", w=3024, h=4032),
    ph("aaaaaaaa-0000-0000-0000-000000000004", species="Flounder", name="Pat Example", location="Bogue Sound"),
]
NOT_SHOWN = [
    ph("bbbbbbbb-0000-0000-0000-000000000001", status="pending", species="Pending Fish"),
    ph("bbbbbbbb-0000-0000-0000-000000000002", status="rejected", species="Rejected Fish"),
    ph("bbbbbbbb-0000-0000-0000-000000000003", category="life", location="Coastal Life Only Place"),
    ph("bbbbbbbb-0000-0000-0000-000000000004", approved=False, species="Unapproved Fish"),
]


def render(live=None):
    return cwp.page(APPROVED + NOT_SHOWN if live is None else live).decode("utf-8")


def main_part(doc):
    return doc.split('<main id="main">', 1)[1].split("</main>", 1)[0]


class Content(unittest.TestCase):
    def test_only_approved_catch_photos_render(self):
        doc = render()
        for p in APPROVED:
            self.assertIn(p["id"], doc)
        for p in NOT_SHOWN:
            self.assertNotIn(p["id"], doc)
        for word in ("Pending Fish", "Rejected Fish", "Unapproved Fish", "Coastal Life Only Place"):
            self.assertNotIn(word, doc)
        self.assertEqual(len(re.findall(r"<figure class=\"pl ", doc)), len(APPROVED))

    def test_reads_the_existing_approved_list(self):
        import catch_wall_public
        with mock.patch.object(catch_wall_public, "load_approved", return_value=APPROVED[:2]) as m:
            doc = cwp.page().decode("utf-8")
        m.assert_called_once()
        self.assertEqual(len(re.findall(r"<figure class=\"pl ", doc)), 2)

    def test_every_image_has_alt_dimensions_and_credit(self):
        body = main_part(render())
        figs = re.findall(r"<figure class=\"pl .*?</figure>", body, re.S)
        self.assertTrue(figs)
        for f in figs:
            img = re.search(r"<img [^>]*>", f).group(0)
            alt = re.search(r'alt="([^"]*)"', img).group(1)
            self.assertTrue(alt.strip(), img)
            self.assertRegex(img, r'width="\d+" height="\d+"')
            cr = re.search(r'<span class="pl-cr">([^<]+)</span>', f)
            self.assertTrue(cr and cr.group(1).strip(), f)
        self.assertEqual(len(re.findall(r"<img ", body)), len(figs))

    def test_credits_are_stored_or_concise_community_credit(self):
        doc = render()
        self.assertIn("Photo: Pat Example \u00b7 Catch Wall", doc)
        self.assertEqual(doc.count(cwp.NO_PHOTOGRAPHER), 3 * 2)  # plate caption + lightbox payload

    def test_only_stored_fields_no_invented_details(self):
        doc = render()
        self.assertNotIn("<time>", main_part(doc))  # no takenOn stored, so no dates
        self.assertNotRegex(doc, r"\b\d+(\.\d+)? ?(lb|lbs|pounds|inches|in\.)\b")

    def test_no_placeholder_or_empty_slots(self):
        doc = re.sub(r"<style.*?</style>", "", render(), flags=re.S)  # shared Hybrid CSS still defines slot classes
        for bad in ("Awaiting", "awaiting", "placeholder", "ph-empty", "mz-slot", "Coming soon", "lorem"):
            self.assertNotIn(bad, doc)
        fresh_only = render([APPROVED[0]])
        self.assertIn('id="sec-fresh"', fresh_only)
        self.assertNotIn('id="sec-salt"', fresh_only)  # empty sections are omitted, not shown blank
        self.assertNotIn('chip-salt', fresh_only)

    def test_salt_and_fresh_sections_and_jump_chips(self):
        doc = render()
        self.assertIn('id="sec-salt"', doc)
        self.assertIn('id="sec-fresh"', doc)
        self.assertIn('href="#sec-salt"', doc)
        self.assertIn('href="#sec-fresh"', doc)

    def test_submit_links_to_existing_flow(self):
        doc = render()
        hrefs = re.findall(r'<a class="cw-submit" href="([^"]+)"', doc)
        self.assertTrue(hrefs)
        self.assertTrue(all(h == "/catch-wall" for h in hrefs), hrefs)
        self.assertNotIn("/api/photos/submit", doc)
        self.assertNotIn("<form", doc)

    def test_lazy_below_fold_and_accessible_detail(self):
        body = main_part(render())
        imgs = re.findall(r"<img [^>]*>", body)
        self.assertIn('loading="eager"', imgs[0])
        self.assertTrue(all('loading="lazy"' in i for i in imgs[1:]))
        doc = render()
        self.assertIn('<dialog class="lb" id="lb" aria-labelledby="lb-t">', doc)
        self.assertIn('aria-label="Close photo"', doc)
        self.assertIn("e.key==='Tab'", doc)
        self.assertIn('name="robots" content="noindex, nofollow"', doc)

    def test_escapes_submitted_text(self):
        doc = render([ph("cccccccc-0000-0000-0000-000000000001", species='<script>x</script>"')])
        self.assertNotIn("<script>x</script>", doc)


class Gate(unittest.TestCase):
    KEY = "catch-wall-test-key-24-chars"

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

    def _get(self, path, key=None, cookie=False):
        saved = os.environ.get("PREVIEW_KEY")
        try:
            if key:
                os.environ["PREVIEW_KEY"] = key
            else:
                os.environ.pop("PREVIEW_KEY", None)
            h = {}
            if cookie:
                h["Cookie"] = "cb_preview=" + self.server._preview_cookie_value(self.KEY)
            with mock.patch.object(cwp, "catch_photos", return_value=APPROVED):
                c = HTTPConnection("127.0.0.1", self.port, timeout=10)
                c.request("GET", path, headers=h)
                r = c.getresponse()
                return r.status, dict(r.getheaders()), r.read()
        finally:
            if saved is None:
                os.environ.pop("PREVIEW_KEY", None)
            else:
                os.environ["PREVIEW_KEY"] = saved

    def test_route_is_cookie_gated(self):
        self.assertEqual(self._get(cwp.ROUTE)[0], 404)
        self.assertEqual(self._get(cwp.ROUTE, key=self.KEY)[0], 404)
        status, headers, body = self._get(cwp.ROUTE, key=self.KEY, cookie=True)
        self.assertEqual(status, 200)
        self.assertIn(b"The Catch Wall", body)
        self.assertIn("noindex", headers.get("X-Robots-Tag", ""))

    def test_wrong_cookie_is_404(self):
        saved = os.environ.get("PREVIEW_KEY")
        os.environ["PREVIEW_KEY"] = self.KEY
        try:
            c = HTTPConnection("127.0.0.1", self.port, timeout=10)
            c.request("GET", cwp.ROUTE, headers={"Cookie": "cb_preview=nope"})
            self.assertEqual(c.getresponse().status, 404)
        finally:
            if saved is None:
                os.environ.pop("PREVIEW_KEY", None)
            else:
                os.environ["PREVIEW_KEY"] = saved


if __name__ == "__main__":
    unittest.main()
