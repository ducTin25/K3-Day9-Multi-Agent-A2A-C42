"""Unit tests for src/finance.py Decimal/rounding helpers (Member 3 / TV3 CP1)."""

import unittest
from decimal import Decimal

from src.finance import (
    MoneyError,
    is_within_tolerance,
    reconciliation_delta,
    sum_money,
    to_money,
)


class TestToMoney(unittest.TestCase):

    def test_parses_string_and_rounds_half_up(self):
        self.assertEqual(to_money("99.335"), Decimal("99.34"))
        self.assertEqual(to_money("99.334"), Decimal("99.33"))

    def test_rejects_negative(self):
        with self.assertRaises(MoneyError):
            to_money("-1.00")

    def test_rejects_invalid(self):
        with self.assertRaises(MoneyError):
            to_money("not-a-number")


class TestSumMoney(unittest.TestCase):

    def test_sums_multiple_rows(self):
        self.assertEqual(sum_money(["50.00", "100.00"]), Decimal("150.00"))

    def test_empty_iterable_is_zero(self):
        self.assertEqual(sum_money([]), Decimal("0.00"))

    def test_never_multiplies_by_installments(self):
        # payment_value_brl da la tong tien ca row; sum_money chi cong don gian.
        payment_value = "99.33"
        installments = 8
        self.assertEqual(sum_money([payment_value]), Decimal("99.33"))
        self.assertNotEqual(sum_money([payment_value]), Decimal(payment_value) * installments)


class TestReconciliationTolerance(unittest.TestCase):

    def test_delta_is_absolute(self):
        self.assertEqual(reconciliation_delta("99.90", "100.00"), Decimal("0.10"))
        self.assertEqual(reconciliation_delta("100.00", "99.90"), Decimal("0.10"))

    def test_boundary_0_09_within_tolerance(self):
        self.assertTrue(is_within_tolerance("99.91", "100.00"))

    def test_boundary_0_10_within_tolerance_inclusive(self):
        self.assertTrue(is_within_tolerance("99.90", "100.00"))

    def test_boundary_0_11_outside_tolerance(self):
        self.assertFalse(is_within_tolerance("99.89", "100.00"))


if __name__ == "__main__":
    unittest.main()
