"""Photo pipeline tests. Fixtures are generated at run time (solid colours and
gradients drawn by Pillow); nothing here is a real photo and nothing is published.

Run:  python -m unittest tests.test_photos   (needs Pillow + pillow-heif)
"""
import io
import json
import os
import shutil
import sys
import tempfile
import threading
from http.client import HTTPConnection
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

TMP = tempfile.mkdtemp(prefix="cb-photos-test-")
os.environ.update({"PHOTO_UPLOADS_ENABLED": "1", "PHOTO_BACKEND": "fake", "PHOTO_FAKE_DIR": TMP,
                   "PHOTO_SESSION_SECRET": "x" * 40})
os.environ.pop("RENDER", None)
os.environ.pop("TURNSTILE_SECRET_KEY", None)

import photos  # noqa: E402
from PIL import Image  # noqa: E402

os.environ["PHOTO_ADMIN_PASSWORD_HASH"] = photos.hash_password("correct horse battery staple")


def jpeg_with_gps(w=1200, h=900, orientation=6):
    im = Image.new("RGB", (w, h), (30, 90, 120))
    for x in range(0, w, 40):
        im.paste((200, 120, 60), (x, 0, x + 8, h))
    exif = Image.Exif()
    exif[0x0112] = orientation                      # Orientation: rotate 90 CW
    exif[0x010F] = "TestCam"                        # Make
    gps = {1: "N", 2: (34.0, 43.0, 12.0), 3: "W", 4: (76.0, 40.0, 5.0)}
    exif[0x8825] = gps                              # GPSInfo
    b = io.BytesIO()
    im.save(b, "JPEG", exif=exif.tobytes(), quality=90)
    return b.getvalue()


def heic_bytes(w=1000, h=750):
    import pillow_heif
    pillow_heif.register_heif_opener()
    b = io.BytesIO()
    Image.new("RGB", (w, h), (10, 140, 160)).save(b, "HEIF", quality=70)
    return b.getvalue()


def multipart(fields, file_bytes=None, filename="x.jpg", ctype="image/jpeg"):
    bd = "----cbtestboundary"
    out = b""
    for k, v in fields.items():
        out += ("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n" % (bd, k, v)).encode()
    if file_bytes is not None:
        out += ("--%s\r\nContent-Disposition: form-data; name=\"photo\"; filename=\"%s\"\r\nContent-Type: %s\r\n\r\n" % (bd, filename, ctype)).encode()
        out += file_bytes + b"\r\n"
    out += ("--%s--\r\n" % bd).encode()
    return "multipart/form-data; boundary=" + bd, out


GOOD = {"category": "fishing", "water_type": "saltwater", "consent": "yes", "age": "yes",
        "species": "Red drum", "location": "Cape Lookout", "caption": "Test fixture", "display_name": "Tester"}


class PhotoPipeline(unittest.TestCase):
    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(TMP, ignore_errors=True)

    def setUp(self):
        photos.LIMITS = photos.RateLimiter()

    def test_flag_off_refuses(self):
        os.environ["PHOTO_UPLOADS_ENABLED"] = "0"
        try:
            ct, body = multipart(GOOD, jpeg_with_gps())
            self.assertEqual(photos.handle_submit(ct, body, "1.1.1.1")[0], 404)
            self.assertFalse(photos.public_config()["uploads"])
            self.assertFalse(photos.public_config()["public"])
            self.assertFalse(photos.admin_configured())
            self.assertTrue(photos.admin_ready())
            self.assertTrue(photos.uploads_available(preview=True))
            self.assertEqual(photos.handle_submit(ct, body, "1.1.1.1", preview=True)[0], 200)
        finally:
            os.environ["PHOTO_UPLOADS_ENABLED"] = "1"

    def test_fake_backend_refused_on_render(self):
        os.environ["RENDER"] = "true"
        photos._backend = None
        try:
            self.assertIsNone(photos.backend())
            self.assertFalse(photos.uploads_active())
        finally:
            os.environ.pop("RENDER")
            photos._backend = None

    def test_real_backend_without_turnstile_is_active(self):
        os.environ.update({"PHOTO_BACKEND": "supabase", "SUPABASE_URL": "https://example.supabase.co", "SUPABASE_SERVICE_ROLE_KEY": "k"})
        os.environ.pop("TURNSTILE_SECRET_KEY", None)
        os.environ.pop("TURNSTILE_SITE_KEY", None)
        photos._backend = None
        try:
            self.assertTrue(photos.uploads_active())           # Turnstile is optional
            self.assertFalse(photos.turnstile_required())
            self.assertFalse(photos.verify_turnstile("local-test-pass", "1.1.1.1"))
        finally:
            os.environ["PHOTO_BACKEND"] = "fake"
            photos._backend = None

    def test_strips_exif_and_orients(self):
        out = photos.process_image(jpeg_with_gps(1200, 900, orientation=6))
        self.assertEqual((out["w"], out["h"]), (900, 1200))        # rotated by orientation
        for name, blob in out["files"].items():
            im = Image.open(io.BytesIO(blob))
            self.assertEqual(im.format, "WEBP")
            self.assertFalse(im.info.get("exif"), name)
            self.assertFalse(im.getexif(), name)
            self.assertNotIn(b"GPS", blob)
            self.assertNotIn(b"TestCam", blob)
        self.assertEqual(Image.open(io.BytesIO(out["files"]["400"])).size[0], 400)
        self.assertEqual(Image.open(io.BytesIO(out["files"]["1600"])).size[0], 900)  # never upscaled

    def test_heic(self):
        out = photos.process_image(heic_bytes())
        self.assertEqual((out["w"], out["h"]), (1000, 750))
        self.assertIn("800", out["files"])

    def test_rejects_non_images(self):
        for bad in (b"<html><script>alert(1)</script></html>" * 10, b"GIF89a" + b"\0" * 100,
                    b"\xff\xd8\xff" + b"garbage" * 50):
            with self.assertRaises(photos.ImageRejected):
                photos.process_image(bad)

    def test_rejects_tiny_and_huge(self):
        b = io.BytesIO(); Image.new("RGB", (100, 100)).save(b, "PNG")
        with self.assertRaises(photos.ImageRejected):
            photos.process_image(b.getvalue())
        with self.assertRaises(photos.ImageRejected):
            photos.process_image(b"\xff\xd8\xff" + b"0" * (photos.MAX_BYTES + 1))
        old = photos.MAX_PIXELS
        photos.MAX_PIXELS = 1_000_000
        try:
            with self.assertRaises(photos.ImageRejected):
                photos.process_image(jpeg_with_gps(1500, 1000))
        finally:
            photos.MAX_PIXELS = old

    def test_submit_validation(self):
        cases = (("consent", 400), ("age", 400), ("category", 400), ("water_type", 400), ("display_name", 400))
        for i, (drop, code) in enumerate(cases):
            f = dict(GOOD); f.pop(drop)
            ct, body = multipart(f, jpeg_with_gps())
            self.assertEqual(photos.handle_submit(ct, body, "2.2.2.%s" % (10 + i))[0], code, drop)
        ct, body = multipart(dict(GOOD, website="spam"), jpeg_with_gps())
        self.assertEqual(photos.handle_submit(ct, body, "2.2.3.1")[0], 400)
        ct, body = multipart(GOOD, None)
        self.assertEqual(photos.handle_submit(ct, body, "2.2.3.2")[0], 400)
        ct, body = multipart(dict(GOOD, taken_on="2099-01-01"), jpeg_with_gps())
        self.assertEqual(photos.handle_submit(ct, body, "2.2.3.3")[0], 400)
        ct, body = multipart(dict(GOOD, region="not-a-region"), jpeg_with_gps())
        self.assertEqual(photos.handle_submit(ct, body, "2.2.3.4")[0], 400)

    def test_anonymous_hides_public_name(self):
        ct, body = multipart(dict(GOOD, anonymous="yes", display_name="Pat", taken_on="2024-06-15", region="crystal-coast"), jpeg_with_gps())
        st, res = photos.handle_submit(ct, body, "8.8.8.8")
        self.assertEqual(st, 200, res)
        b = photos.backend()
        row = [r for r in b.select(status="pending") if r["ip_hash"] == photos.ip_hash("8.8.8.8")][0]
        self.assertEqual(row["display_name"], "Pat")
        self.assertTrue(row["anonymous"])
        self.assertEqual(row["taken_on"], "2024-06-15")
        self.assertEqual(row["region_id"], "crystal-coast")
        self.assertFalse([p for p in photos.public_photos("all")["photos"] if p["id"] == row["id"]])
        photos.admin_action(__import__("json").dumps({"id": row["id"], "action": "approve"}).encode())
        pub = [p for p in photos.public_photos("catch")["photos"] if p["id"] == row["id"]][0]
        self.assertEqual(pub["name"], "")
        self.assertEqual(pub["takenOn"], "2024-06-15")
        self.assertIn("Morehead", pub["region"])
        photos.admin_action(__import__("json").dumps({"id": row["id"], "action": "remove"}).encode())

    def test_rate_limit(self):
        ct, body = multipart(dict(GOOD, category="life"), jpeg_with_gps(800, 600, 1))
        codes = [photos.handle_submit(ct, body, "3.3.3.3")[0] for _ in range(6)]
        self.assertEqual(codes[:5], [200] * 5)
        self.assertEqual(codes[5], 429)

    def test_session_rate_limit(self):
        ct, body = multipart(dict(GOOD, category="life"), jpeg_with_gps(800, 600, 1))
        codes = [photos.handle_submit(ct, body, "9.9.9.%s" % i, session_id="sess-test-token-aaaa")[0] for i in range(6)]
        self.assertEqual(codes[:5], [200] * 5)
        self.assertEqual(codes[5], 429)

    def test_full_moderation_flow(self):
        ct, body = multipart(GOOD, jpeg_with_gps())
        st, res = photos.handle_submit(ct, body, "4.4.4.4")
        self.assertEqual(st, 200, res)
        b = photos.backend()
        row = [r for r in b.select(status="pending") if r["ip_hash"] == photos.ip_hash("4.4.4.4")][0]
        pid = row["id"]
        self.assertNotIn("4.4.4.4", json.dumps(row))                       # IP stored only as a hash
        # pending is private: not in the public list, not in the public bucket
        self.assertFalse([p for p in photos.public_photos("all")["photos"] if p["id"] == pid])
        self.assertFalse((Path(TMP) / "approved" / pid).exists())
        self.assertIsNotNone(photos.admin_image(pid, "thumb"))
        # edit + approve
        st, _ = photos.admin_action(json.dumps({"id": pid, "action": "edit", "caption": "Edited", "category": "life", "species": "ignored", "water_type": "freshwater"}).encode())
        self.assertEqual(photos.admin_action(json.dumps({"id": pid, "action": "edit", "water_type": "brackish"}).encode())[0], 400)
        self.assertEqual(st, 200)
        st, _ = photos.admin_action(json.dumps({"id": pid, "action": "approve"}).encode())
        self.assertEqual(st, 200)
        pub = [p for p in photos.public_photos("life")["photos"] if p["id"] == pid]
        self.assertEqual(len(pub), 1)
        self.assertEqual(pub[0]["caption"], "Edited")
        self.assertEqual(pub[0]["water"], "freshwater")
        self.assertEqual(pub[0]["species"], "")                              # species cleared for Coastal Life
        self.assertFalse([p for p in photos.public_photos("catch")["photos"] if p["id"] == pid])
        self.assertTrue([p for p in photos.public_photos("all")["photos"] if p["id"] == pid])
        self.assertFalse((Path(TMP) / "pending" / pid).exists() and any((Path(TMP) / "pending" / pid).iterdir()))
        self.assertIsNone(photos.admin_image(pid, "thumb"))                 # private copy deleted
        # feature, then remove
        photos.admin_action(json.dumps({"id": pid, "action": "edit", "featured": True}).encode())
        self.assertTrue([p for p in photos.public_photos("all", True)["photos"] if p["id"] == pid])
        st, _ = photos.admin_action(json.dumps({"id": pid, "action": "remove"}).encode())
        self.assertEqual(st, 200)
        self.assertFalse([p for p in photos.public_photos("all")["photos"] if p["id"] == pid])
        self.assertFalse([p for p in photos.public_photos("all", True)["photos"] if p["id"] == pid])

    def test_reject(self):
        ct, body = multipart(GOOD, jpeg_with_gps())
        photos.handle_submit(ct, body, "5.5.5.5")
        pid = [r for r in photos.backend().select(status="pending") if r["ip_hash"] == photos.ip_hash("5.5.5.5")][0]["id"]
        self.assertEqual(photos.admin_action(json.dumps({"id": pid, "action": "reject"}).encode())[0], 200)
        self.assertIsNone(photos.admin_image(pid, "800"))
        self.assertEqual(photos.admin_action(json.dumps({"id": pid, "action": "approve"}).encode())[0], 409)

    def test_auth(self):
        st, _, cookie = photos.admin_login(b'{"password":"wrong"}', "6.6.6.6")
        self.assertEqual(st, 401); self.assertIsNone(cookie)
        st, res, cookie = photos.admin_login(b'{"password":"correct horse battery staple"}', "6.6.6.7")
        self.assertEqual(st, 200)
        self.assertIn("HttpOnly", cookie); self.assertIn("SameSite=Strict", cookie)
        value = cookie.split(";")[0]
        self.assertEqual(photos.read_session(value), res["csrf"])
        self.assertIsNone(photos.read_session(value[:-2] + "00"))            # tampered
        for _ in range(6):
            photos.admin_login(b'{"password":"nope"}', "7.7.7.7")
        self.assertEqual(photos.admin_login(b'{"password":"correct horse battery staple"}', "7.7.7.7")[0], 429)

    def test_text_cleaning(self):
        self.assertEqual(photos.clean_text("  a\x00b \n\n c  ", "caption"), "ab c")
        self.assertEqual(len(photos.clean_text("x" * 999, "species")), 60)



class PhotoUploadGate(unittest.TestCase):
    """Flag off stays hidden to the public; the preview cookie unlocks a private test."""
    KEY = "preview-test-key-24-chars-ok"

    @classmethod
    def setUpClass(cls):
        import server
        cls.server = server
        os.environ["PREVIEW_KEY"] = cls.KEY
        cls.httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        cls.host, cls.port = cls.httpd.server_address
        cls.origin = "http://127.0.0.1:%s" % cls.port

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        os.environ.pop("PREVIEW_KEY", None)

    def setUp(self):
        photos.LIMITS = photos.RateLimiter()
        os.environ["PHOTO_UPLOADS_ENABLED"] = "0"
        photos._backend = None

    def tearDown(self):
        os.environ["PHOTO_UPLOADS_ENABLED"] = "1"
        photos._backend = None

    def _cookie(self):
        return "%s=%s" % (self.server.PREVIEW_COOKIE, self.server._preview_cookie_value(self.KEY))

    def _req(self, method, path, body=None, headers=None, cookie=None):
        h = dict(headers or {})
        if cookie:
            prior = h.get("Cookie")
            h["Cookie"] = (prior + "; " + cookie) if prior else cookie
        conn = HTTPConnection("127.0.0.1", self.port, timeout=8)
        conn.request(method, path, body=body, headers=h)
        resp = conn.getresponse()
        data = resp.read()
        hdrs = {k.lower(): v for k, v in resp.getheaders()}
        conn.close()
        return resp.status, data, hdrs

    def test_public_is_404_when_flag_off(self):
        st, body, _ = self._req("GET", "/api/photos/config")
        self.assertEqual(st, 200)
        cfg = json.loads(body)
        self.assertFalse(cfg["uploads"])
        self.assertFalse(cfg.get("public"))
        ct, raw = multipart(GOOD, jpeg_with_gps())
        st, body, _ = self._req(
            "POST", "/api/photos/submit", body=raw,
            headers={"Content-Type": ct, "Origin": self.origin},
        )
        self.assertEqual(st, 404)
        st, _, _ = self._req("GET", "/admin")
        self.assertEqual(st, 404)
        st, _, _ = self._req("GET", "/preview/photos-check")
        self.assertEqual(st, 404)
        st, _, _ = self._req("GET", "/preview/photos-check", cookie="cb_preview=deadbeef")
        self.assertEqual(st, 404)

    def test_preview_cookie_unlocks_submit_admin_and_check(self):
        ck = self._cookie()
        st, body, hdrs = self._req("GET", "/api/photos/config", cookie=ck)
        self.assertEqual(st, 200)
        self.assertIn("noindex", hdrs.get("x-robots-tag", ""))
        self.assertIn("no-store", hdrs.get("cache-control", ""))
        cfg = json.loads(body)
        self.assertTrue(cfg["uploads"])
        self.assertFalse(cfg["public"])
        self.assertEqual(cfg["maxBytes"], 10 * 1024 * 1024)
        self.assertFalse(cfg.get("turnstileSiteKey"))

        ct, raw = multipart(GOOD, jpeg_with_gps())
        st, body, hdrs = self._req(
            "POST", "/api/photos/submit", body=raw,
            headers={"Content-Type": ct, "Origin": self.origin, "Cookie": ck},
        )
        self.assertEqual(st, 200, body)
        res = json.loads(body)
        self.assertTrue(res["ok"])
        self.assertEqual(res["status"], "pending")
        self.assertIn("cb_submit=", hdrs.get("set-cookie", ""))

        st, page, hdrs = self._req("GET", "/admin", cookie=ck)
        self.assertEqual(st, 200)
        self.assertIn("noindex", hdrs.get("x-robots-tag", ""))
        self.assertIn(b"Photo review", page)

        st, body, hdrs = self._req("GET", "/preview/photos-check", cookie=ck)
        self.assertEqual(st, 200)
        self.assertIn("noindex", hdrs.get("x-robots-tag", ""))
        self.assertIn("no-store", hdrs.get("cache-control", ""))
        report = json.loads(body)
        for key in ("pillow", "pillowHeif", "backendConfigured", "tableReachable",
                    "pendingRoundTrip", "pendingBucketPrivate", "approvedBucketPublic",
                    "adminConfigured", "pendingCount"):
            self.assertIn(key, report)
        blob = json.dumps(report).lower()
        self.assertNotIn("sb_secret", blob)
        self.assertNotIn("service_role", blob)
        self.assertNotIn("scrypt$", blob)
        self.assertTrue(report["backendConfigured"])
        self.assertEqual(report["backend"], "fake")
        self.assertTrue(report["tableReachable"])
        self.assertGreaterEqual(report["pendingCount"], 1)
        self.assertTrue(report["adminConfigured"])
        self.assertFalse(report["uploadsFlag"])

    def test_catch_wall_hides_share_button_in_markup(self):
        st, body, _ = self._req("GET", "/catch-wall")
        self.assertEqual(st, 200)
        self.assertIn(b'id="share-open" hidden', body)
        self.assertIn(b"Photo sharing opens soon", body)


if __name__ == "__main__":
    unittest.main()


class PublicConfigRegions(unittest.TestCase):
    def test_unreleased_regions_hidden_publicly(self):
        pub = {r["id"] for r in photos.public_config(False)["regions"]}
        pv = {r["id"] for r in photos.public_config(True)["regions"]}
        self.assertIn("crystal-coast", pub)
        # Public since 14 Nov 2026.
        for rid in ("wilmington", "nags-head", "emerald-isle", "topsail"):
            self.assertIn(rid, pub)
            self.assertIn(rid, pv)
        for rid in ("atlantic-beach", "cape-lookout", "new-bern"):
            self.assertNotIn(rid, pub)
