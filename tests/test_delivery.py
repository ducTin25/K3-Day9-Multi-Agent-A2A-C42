"""Unit tests for Delivery tools and timestamp comparator (Member 4 / TV4 CP0 & CP1)."""

import json
import os
import unittest
from src.tools.delivery_tools import compare_delivery_timestamps, get_delivery_timeline, get_shipping_limits


class TestDeliveryTools(unittest.TestCase):

    def setUp(self):
        self.fixtures_dir = os.path.join(
            os.path.dirname(__file__), "fixtures", "delivery"
        )

    def load_fixture(self, name: str):
        path = os.path.join(self.fixtures_dir, f"{name}.json")
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def test_on_time_delivery_fixture(self):
        fixture = self.load_fixture("on_time")
        timeline = {
            "order_id": fixture["order_id"],
            "delivered_customer_at": fixture["delivered_customer_at"],
            "estimated_delivery_at": fixture["estimated_delivery_at"],
            "delivered_carrier_at": fixture["delivered_carrier_at"],
        }
        items = fixture["items"]
        result = compare_delivery_timestamps(fixture["order_id"], timeline, items)
        self.assertEqual(result, fixture["expected_delivery_facts"])

    def test_seller_late_delivery_fixture(self):
        fixture = self.load_fixture("seller_late")
        timeline = {
            "order_id": fixture["order_id"],
            "delivered_customer_at": fixture["delivered_customer_at"],
            "estimated_delivery_at": fixture["estimated_delivery_at"],
            "delivered_carrier_at": fixture["delivered_carrier_at"],
        }
        items = fixture["items"]
        result = compare_delivery_timestamps(fixture["order_id"], timeline, items)
        self.assertEqual(result, fixture["expected_delivery_facts"])

    def test_logistics_late_delivery_fixture(self):
        fixture = self.load_fixture("logistics_late")
        timeline = {
            "order_id": fixture["order_id"],
            "delivered_customer_at": fixture["delivered_customer_at"],
            "estimated_delivery_at": fixture["estimated_delivery_at"],
            "delivered_carrier_at": fixture["delivered_carrier_at"],
        }
        items = fixture["items"]
        result = compare_delivery_timestamps(fixture["order_id"], timeline, items)
        self.assertEqual(result, fixture["expected_delivery_facts"])

    def test_missing_timestamp_fixture(self):
        fixture = self.load_fixture("missing_timestamp")
        timeline = {
            "order_id": fixture["order_id"],
            "delivered_customer_at": fixture["delivered_customer_at"],
            "estimated_delivery_at": fixture["estimated_delivery_at"],
            "delivered_carrier_at": fixture["delivered_carrier_at"],
        }
        items = fixture["items"]
        result = compare_delivery_timestamps(fixture["order_id"], timeline, items)
        self.assertEqual(result, fixture["expected_delivery_facts"])

    def test_multi_item_seller_late(self):
        timeline = {
            "delivered_customer_at": "2018-06-01 10:00:00",
            "estimated_delivery_at": "2018-05-25 10:00:00",
            "delivered_carrier_at": "2018-05-20 10:00:00",
        }
        items = [
            {"order_item_id": 1, "seller_id": "sel_1", "shipping_limit_date": "2018-05-18 10:00:00"},
            {"order_item_id": 2, "seller_id": "sel_2", "shipping_limit_date": "2018-05-22 10:00:00"},
        ]
        result = compare_delivery_timestamps("ord_multi", timeline, items)
        self.assertTrue(result["is_delivered_late"])
        self.assertEqual(result["late_stage"], "seller")
        self.assertEqual(len(result["seller_handoff_violations"]), 1)
        self.assertEqual(result["seller_handoff_violations"][0]["order_item_id"], 1)


if __name__ == "__main__":
    unittest.main()
