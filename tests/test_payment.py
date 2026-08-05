"""Unit tests for Payment tools (Member 3 / TV3 CP1).

Covers the CP1 self-check: sum row, split payment va tolerance pass.
Uses both the CP0 fixtures (tests/fixtures/payment/) and real rows from
data/*.csv to prove the tool works against the actual dataset, not just
synthetic fixtures.
"""

import json
import os
import unittest
from decimal import Decimal

from src.tools.payment_tools import (
    get_order_financial_reference,
    get_order_payments,
    reconcile_payments,
)


class TestPaymentToolsFixtures(unittest.TestCase):
    """reconcile_payments() against every CP0 fixture (single/split/zero/mismatch/boundary)."""

    def setUp(self):
        self.fixtures_dir = os.path.join(os.path.dirname(__file__), "fixtures", "payment")

    def load_fixture(self, name: str):
        path = os.path.join(self.fixtures_dir, f"{name}.json")
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)

    def _assert_fixture(self, name: str):
        fixture = self.load_fixture(name)
        result = reconcile_payments(
            fixture["order_id"], fixture["payments"], fixture["reference_order_total_brl"]
        )
        expected = fixture["expected_payment_facts"]

        self.assertEqual(str(result["payment_total_brl"]), expected["payment_total_brl"])
        self.assertEqual(result["payment_count"], expected["payment_count"])
        self.assertEqual(str(result["reconciliation_delta_brl"]), expected["reconciliation_delta_brl"])
        self.assertEqual(result["is_reconciled"], expected["is_reconciled"])
        self.assertEqual(sorted(result["evidence_ids"]), sorted(expected["evidence_ids"]))

    def test_single_fixture(self):
        self._assert_fixture("single")

    def test_split_fixture(self):
        self._assert_fixture("split")

    def test_zero_fixture(self):
        self._assert_fixture("zero")

    def test_mismatch_fixture(self):
        self._assert_fixture("mismatch")

    def test_boundary_0_09_fixture(self):
        self._assert_fixture("boundary_delta_0_09")

    def test_boundary_0_10_fixture(self):
        self._assert_fixture("boundary_delta_0_10")

    def test_boundary_0_11_fixture(self):
        self._assert_fixture("boundary_delta_0_11")


class TestPaymentToolsRealData(unittest.TestCase):
    """Integration checks against the real Olist CSVs in data/."""

    def test_sum_single_payment_row_matches_real_order(self):
        # order b81ef226f3fe1789b1e8b2acac839d17: 1 item (price 79.80, freight 19.53),
        # 1 payment row of 99.33 -> exact reconciliation.
        order_id = "b81ef226f3fe1789b1e8b2acac839d17"
        payments = get_order_payments(order_id)
        reference = get_order_financial_reference(order_id)

        self.assertEqual(len(payments), 1)
        self.assertEqual(payments[0]["payment_value_brl"], Decimal("99.33"))
        self.assertEqual(reference["item_total_brl"], Decimal("79.80"))
        self.assertEqual(reference["freight_total_brl"], Decimal("19.53"))
        self.assertEqual(reference["reference_order_total_brl"], Decimal("99.33"))

        result = reconcile_payments(order_id, payments, reference["reference_order_total_brl"])
        self.assertEqual(result["payment_total_brl"], Decimal("99.33"))
        self.assertEqual(result["reconciliation_delta_brl"], Decimal("0.00"))
        self.assertTrue(result["is_reconciled"])
        self.assertEqual(result["evidence_ids"], [f"payment:{order_id}:1"])

    def test_split_payment_matches_real_order(self):
        # order 0016dfedd97fc2950e388d2971d718c7: item 49.75 + freight 20.80 = 70.55,
        # 2 payment rows (17.92 + 52.63 = 70.55) -> valid split payment.
        order_id = "0016dfedd97fc2950e388d2971d718c7"
        payments = get_order_payments(order_id)
        reference = get_order_financial_reference(order_id)

        self.assertEqual(len(payments), 2)
        self.assertEqual(reference["reference_order_total_brl"], Decimal("70.55"))

        result = reconcile_payments(order_id, payments, reference["reference_order_total_brl"])
        self.assertEqual(result["payment_count"], 2)
        self.assertEqual(result["payment_total_brl"], Decimal("70.55"))
        self.assertTrue(result["is_reconciled"])
        self.assertEqual(
            result["evidence_ids"],
            [f"payment:{order_id}:1", f"payment:{order_id}:2"],
        )

    def test_unknown_order_returns_empty(self):
        payments = get_order_payments("0" * 32)
        reference = get_order_financial_reference("0" * 32)
        self.assertEqual(payments, [])
        self.assertEqual(reference["reference_order_total_brl"], Decimal("0.00"))

        result = reconcile_payments("0" * 32, payments, reference["reference_order_total_brl"])
        self.assertEqual(result["payment_count"], 0)
        self.assertEqual(result["payment_total_brl"], Decimal("0.00"))
        self.assertTrue(result["is_reconciled"])
        self.assertEqual(result["evidence_ids"], [])


if __name__ == "__main__":
    unittest.main()
