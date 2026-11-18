import time
import unittest
from unittest import mock

import freshwater


class FreshwaterWarmTest(unittest.TestCase):
    def setUp(self):
        self.rid = next(iter(freshwater.warm_ids()))
        self.saved = dict(freshwater._ASSEMBLED)

    def tearDown(self):
        freshwater._ASSEMBLED.clear()
        freshwater._ASSEMBLED.update(self.saved)
        freshwater._REFRESHING.discard(self.rid)

    def test_stale_cache_served_immediately_and_refreshed_in_background(self):
        payload = {"ok": True, "marker": "old"}
        freshwater._ASSEMBLED[self.rid] = (time.time() - freshwater.ASSEMBLED_TTL - 30, payload)
        with mock.patch.object(freshwater, "_refresh") as ref:
            t0 = time.time()
            status, got = freshwater.assemble(self.rid)
            self.assertLess(time.time() - t0, 0.5)
            time.sleep(0.1)
        self.assertEqual(status, 200)
        self.assertIs(got, payload)
        ref.assert_called_once_with(self.rid)

    def test_very_old_cache_is_not_served(self):
        freshwater._ASSEMBLED[self.rid] = (time.time() - freshwater.ASSEMBLED_SERVE_MAX - 5, {"ok": True, "marker": "ancient"})
        with mock.patch.object(freshwater, "usgs_iv", side_effect=RuntimeError("stop")):
            with self.assertRaises(RuntimeError):
                freshwater.assemble(self.rid)


if __name__ == "__main__":
    unittest.main()
