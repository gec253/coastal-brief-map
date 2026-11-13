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


GOOD = {"category": "fishing", "water_type": "saltwater", "consent": "yes", "cf-turnstile-response": "local-test-pass",
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
            self.assertFalse(photos.admin_configured())
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

    def test_real_backend_needs_turnstile(self):
        os.environ.update({"PHOTO_BACKEND": "supabase", "SUPABASE_URL": "https://example.supabase.co", "SUPABASE_SERVICE_ROLE_KEY": "k"})
        photos._backend = None
        try:
            self.assertFalse(photos.uploads_active())          # no Turnstile keys
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
        for drop, code in (("consent", 400), ("category", 400), ("water_type", 400), ("cf-turnstile-response", 400)):
            f = dict(GOOD); f.pop(drop)
            ct, body = multipart(f, jpeg_with_gps())
            self.assertEqual(photos.handle_submit(ct, body, "2.2.2.2")[0], code, drop)
        ct, body = multipart(dict(GOOD, website="spam"), jpeg_with_gps())
        self.assertEqual(photos.handle_submit(ct, body, "2.2.2.2")[0], 400)
        ct, body = multipart(GOOD, None)
        self.assertEqual(photos.handle_submit(ct, body, "2.2.2.3")[0], 400)

    def test_rate_limit(self):
        ct, body = multipart(dict(GOOD, category="life"), jpeg_with_gps(800, 600, 1))
        codes = [photos.handle_submit(ct, body, "3.3.3.3")[0] for _ in range(6)]
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


if __name__ == "__main__":
    unittest.main()
