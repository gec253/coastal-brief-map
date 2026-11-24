import time
import unittest
from unittest import mock

import freshwater


class FreshwaterWarmTest(unittest.TestCase):
    def setUp(self):
        self.rid = next(iter(freshwater.warm_ids()))
        self.saved = dict(freshwater._ASSEMBLED)
        freshwater.reset_caches()

    def tearDown(self):
        freshwater.reset_caches()
        freshwater._ASSEMBLED.update(self.saved)

    def test_stale_cache_served_immediately_and_refreshed_in_background(self):
        payload = {"ok": True, "marker": "old"}
        freshwater._ASSEMBLED[self.rid] = (time.time() - freshwater.ASSEMBLED_TTL - 30, payload)
        with mock.patch.object(freshwater, "ensure_refresh") as ref:
            t0 = time.time()
            status, got = freshwater.assemble(self.rid)
            self.assertLess(time.time() - t0, 0.5)
            time.sleep(0.1)
        self.assertEqual(status, 200)
        self.assertEqual(got.get("marker"), "old")
        ref.assert_called_once_with(self.rid)

    def test_very_old_cache_is_not_served(self):
        freshwater._ASSEMBLED[self.rid] = (time.time() - freshwater.ASSEMBLED_SERVE_MAX - 5, {"ok": True, "marker": "ancient"})
        with mock.patch.object(freshwater, "usgs_iv", side_effect=RuntimeError("stop")), \
                mock.patch.object(freshwater, "usgs_daily_stats", return_value=None), \
                mock.patch.object(freshwater, "nwps", return_value={"status": "unavailable"}), \
                mock.patch.object(freshwater, "qpf_block", return_value={"status": "unavailable"}), \
                mock.patch.object(freshwater, "alerts_point", return_value={"status": "unavailable", "items": []}), \
                mock.patch.object(freshwater, "usace_guide_check", return_value={"status": "unavailable"}), \
                mock.patch("conditions.forecast_block", return_value={"status": "unavailable"}):
            status, body = freshwater.assemble(self.rid, wait=2)
        self.assertEqual(status, 200)
        self.assertNotEqual(body.get("marker"), "ancient")
        el = (body.get("lake") or {}).get("elevation")
        self.assertTrue(el is None or not (isinstance(el, dict) and el.get("value") is not None))


if __name__ == "__main__":
    unittest.main()
