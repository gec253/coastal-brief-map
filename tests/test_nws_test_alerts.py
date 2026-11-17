import unittest
import preview_alerts

class NwsTestAlertsSkipped(unittest.TestCase):
    def test_test_status_alert_is_dropped(self):
        data = {"features": [
            {"properties": {"id": "a", "event": "Tsunami Warning", "status": "Test", "severity": "Extreme"}},
            {"properties": {"id": "b", "event": "Small Craft Advisory", "status": "Actual"}},
        ]}
        events = [i["event"] for i in preview_alerts._items_from_geojson(data)]
        self.assertEqual(events, ["Small Craft Advisory"])

if __name__ == "__main__":
    unittest.main()
