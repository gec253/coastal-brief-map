"""Feedback storage on the Catch Wall's Supabase (private bucket objects under feedback/), mocked."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from urllib.parse import unquote

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import feedback  # noqa: E402
import photos  # noqa: E402


class MockSupabase(photos.SupabaseBackend):
    """SupabaseBackend whose HTTP layer is an in-memory Storage emulation."""

    def __init__(self, public=False, fail=False):
        super().__init__("https://example.supabase.co", "sb_secret_test")
        self.objects = {}
        self.calls = []
        self.public = public
        self.fail = fail

    def _req(self, method, path, body=None, headers=None, timeout=20):
        self.calls.append((method, path, headers or {}))
        if self.fail:
            raise photos.StorageError("%s %s -> 500" % (method, path))
        if method == "GET" and path.startswith("/storage/v1/bucket/"):
            return 200, json.dumps({"public": self.public}).encode()
        if method == "POST" and path.startswith("/storage/v1/object/list/"):
            bucket = path.rsplit("/", 1)[1]
            q = json.loads(body)
            pre = q["prefix"].rstrip("/") + "/"
            names = sorted((k[len(pre):] for (b, k) in self.objects if b == bucket and k.startswith(pre)),
                           reverse=True)[: q["limit"]]
            return 200, json.dumps([{"name": n} for n in names]).encode()
        if path.startswith("/storage/v1/object/"):
            bucket, key = path[len("/storage/v1/object/"):].split("/", 1)
            key = unquote(key)
            if method == "POST":
                self.objects[(bucket, key)] = body
                return 200, b"{}"
            if method == "GET":
                if (bucket, key) not in self.objects:
                    raise photos.StorageError("GET -> 404")
                return 200, self.objects[(bucket, key)]
        raise AssertionError("unexpected call %s %s" % (method, path))


class FeedbackSupabaseTests(unittest.TestCase):
    def setUp(self):
        feedback.reset_rate()
        feedback.set_store(None)

    def tearDown(self):
        feedback.set_store(None)
        feedback.reset_rate()

    def test_default_store_uses_supabase_when_configured(self):
        sb = MockSupabase()
        with mock.patch.object(photos, "backend", return_value=sb):
            self.assertIsInstance(feedback.store(), feedback.SupabaseFeedbackStore)

    def test_default_store_falls_back_to_json(self):
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.dict(os.environ, {"FEEDBACK_PATH": str(Path(d) / "fb.json")}), \
                mock.patch.object(photos, "backend", return_value=None):
            st = feedback.store()
            self.assertIsInstance(st, feedback.JsonFileStore)
            code, p = feedback.submit({"like": "local"}, "9.9.9.9")
            self.assertEqual(code, 200)
            self.assertTrue((Path(d) / "fb.json").exists())

    def test_fake_photo_backend_is_not_used_for_feedback(self):
        fake = mock.Mock(name="fake")
        fake.name = "fake"
        with mock.patch.object(photos, "backend", return_value=fake):
            self.assertIsInstance(feedback.store(), feedback.JsonFileStore)

    def test_submit_writes_private_object_and_admin_reads_it(self):
        sb = MockSupabase()
        with mock.patch.object(photos, "backend", return_value=sb):
            code, p = feedback.submit({"bugs": "tide typo", "page": "/", "email": "ed@example.com"},
                                      "5.5.5.5", "UA")
            self.assertEqual(code, 200)
            keys = [k for (b, k) in sb.objects]
            self.assertEqual(len(keys), 1)
            self.assertTrue(keys[0].startswith("feedback/") and keys[0].endswith(".json"))
            self.assertIn(p["id"], keys[0])
            bucket = list(sb.objects)[0][0]
            self.assertEqual(bucket, sb.pending)
            self.assertNotEqual(bucket, sb.approved)
            rec = json.loads(list(sb.objects.values())[0])
            self.assertEqual(rec["bugs"], "tide typo")
            self.assertNotIn("5.5.5.5", json.dumps(rec))  # no raw IP stored
            listing = feedback.admin_list()
            self.assertTrue(listing["ok"])
            self.assertEqual(listing["items"][0]["bugs"], "tide typo")
            self.assertTrue(any(m == "POST" and "/object/list/" in path for m, path, _ in sb.calls))
            # never written through a public URL
            self.assertFalse(any("/object/public/" in path for _, path, _ in sb.calls))

    def test_admin_list_newest_first(self):
        sb = MockSupabase()
        st = feedback.SupabaseFeedbackStore(sb)
        st.save({"id": "a", "created_at": "2026-11-16T10:00:00+00:00", "like": "old"})
        st.save({"id": "b", "created_at": "2026-11-16T12:00:00+00:00", "like": "new"})
        feedback.set_store(st)
        items = feedback.admin_list()["items"]
        self.assertEqual([i["like"] for i in items], ["new", "old"])

    def test_refuses_public_bucket(self):
        sb = MockSupabase(public=True)
        with mock.patch.object(photos, "backend", return_value=sb):
            code, p = feedback.submit({"like": "x"}, "6.6.6.6")
        self.assertEqual(code, 503)
        self.assertEqual(sb.objects, {})

    def test_storage_error_is_503_and_admin_error(self):
        sb = MockSupabase(fail=True)
        with mock.patch.object(photos, "backend", return_value=sb):
            code, p = feedback.submit({"like": "x"}, "7.7.7.7")
            self.assertEqual(code, 503)
            self.assertFalse(p["ok"])
            listing = feedback.admin_list()
            self.assertFalse(listing["ok"])
            self.assertNotIn("sb_secret_test", json.dumps(listing))

    def test_honeypot_rate_limit_and_length_cap_still_apply(self):
        sb = MockSupabase()
        with mock.patch.object(photos, "backend", return_value=sb):
            code, p = feedback.submit({"like": "spam", "website": "http://bot"}, "8.8.8.8")
            self.assertEqual(code, 200)
            self.assertEqual(sb.objects, {})
            code, p = feedback.submit({"like": "x" * 5000}, "8.8.8.8")
            self.assertEqual(code, 200)
            rec = json.loads(list(sb.objects.values())[0])
            self.assertEqual(len(rec["like"]), feedback.MAX_FIELD)
            for i in range(feedback.RATE_PER_HOUR - 1):
                feedback.submit({"like": "ok %d" % i}, "8.8.8.8")
            code, p = feedback.submit({"like": "too many"}, "8.8.8.8")
            self.assertEqual(code, 429)
            code, p = feedback.submit({}, "1.2.3.4")
            self.assertEqual(code, 400)


if __name__ == "__main__":
    unittest.main()
