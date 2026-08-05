"""Payment fixture + Decimal/tolerance rule verification (Member 3 / TV3 CP0).

payment_tools.py chua duoc trien khai (CP1). File nay khong test tool that,
ma xac nhan hai thu truoc khi ai do code Payment Agent:
1. `expected_payment_facts` trong moi fixture khop contract `PaymentFacts`.
2. Quy tac Decimal (khong nhan payment_value_brl voi payment_installments)
   va quy tac tolerance 0.10 BRL (inclusive) duoc ap dung dung.
"""

from __future__ import annotations

import json
import os
import unittest
from decimal import ROUND_HALF_UP, Decimal

from src.contracts import PaymentFacts

MONEY_QUANTUM = Decimal("0.01")
PAYMENT_TOLERANCE = Decimal("0.10")

FIXTURE_NAMES = [
    "single",
    "split",
    "zero",
    "mismatch",
    "boundary_delta_0_09",
    "boundary_delta_0_10",
    "boundary_delta_0_11",
]


def money(value: str) -> Decimal:
    return Decimal(value).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


class TestPaymentFixtures(unittest.TestCase):

    def setUp(self):
        self.fixtures_dir = os.path.join(os.path.dirname(__file__), "fixtures", "payment")

    def load_fixture(self, name: str):
        path = os.path.join(self.fixtures_dir, f"{name}.json")
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)

    def test_all_fixtures_present(self):
        for name in FIXTURE_NAMES:
            with self.subTest(fixture=name):
                path = os.path.join(self.fixtures_dir, f"{name}.json")
                self.assertTrue(os.path.exists(path), f"missing fixture {path}")

    def test_expected_payment_facts_matches_contract(self):
        for name in FIXTURE_NAMES:
            with self.subTest(fixture=name):
                fixture = self.load_fixture(name)
                PaymentFacts.model_validate(fixture["expected_payment_facts"])

    def test_payment_total_does_not_multiply_installments(self):
        for name in FIXTURE_NAMES:
            with self.subTest(fixture=name):
                fixture = self.load_fixture(name)
                rows = fixture["payments"]
                expected_total = money(fixture["expected_payment_facts"]["payment_total_brl"])

                correct_total = sum((money(row["payment_value_brl"]) for row in rows), Decimal("0.00"))
                wrong_total_multiplied_by_installments = sum(
                    (money(row["payment_value_brl"]) * row["payment_installments"] for row in rows),
                    Decimal("0.00"),
                )

                self.assertEqual(
                    expected_total, correct_total,
                    "payment_total_brl phai la tong payment_value_brl, khong nhan installments",
                )
                if rows and any(row["payment_installments"] > 1 for row in rows):
                    self.assertNotEqual(
                        expected_total, wrong_total_multiplied_by_installments,
                        "fixture nay phai phan biet duoc voi loi nhan payment_installments",
                    )

    def test_reconciliation_delta_and_tolerance(self):
        for name in FIXTURE_NAMES:
            with self.subTest(fixture=name):
                fixture = self.load_fixture(name)
                expected = fixture["expected_payment_facts"]

                payment_total = money(expected["payment_total_brl"])
                reference_total = money(fixture["reference_order_total_brl"])
                delta = abs(payment_total - reference_total).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)

                self.assertEqual(
                    delta, money(expected["reconciliation_delta_brl"]),
                    "reconciliation_delta_brl phai la |payment_total_brl - reference_order_total_brl|",
                )
                self.assertEqual(
                    delta <= PAYMENT_TOLERANCE, expected["is_reconciled"],
                    f"is_reconciled phai la (delta <= {PAYMENT_TOLERANCE}) cho fixture {name}",
                )

    def test_boundary_table_covers_0_09_0_10_0_11(self):
        deltas = {}
        for name in ("boundary_delta_0_09", "boundary_delta_0_10", "boundary_delta_0_11"):
            fixture = self.load_fixture(name)
            deltas[name] = money(fixture["expected_payment_facts"]["reconciliation_delta_brl"])

        self.assertEqual(deltas["boundary_delta_0_09"], Decimal("0.09"))
        self.assertEqual(deltas["boundary_delta_0_10"], Decimal("0.10"))
        self.assertEqual(deltas["boundary_delta_0_11"], Decimal("0.11"))

        self.assertTrue(self.load_fixture("boundary_delta_0_09")["expected_payment_facts"]["is_reconciled"])
        self.assertTrue(self.load_fixture("boundary_delta_0_10")["expected_payment_facts"]["is_reconciled"])
        self.assertFalse(self.load_fixture("boundary_delta_0_11")["expected_payment_facts"]["is_reconciled"])

    def test_evidence_ids_follow_payment_order_seq_format(self):
        for name in FIXTURE_NAMES:
            with self.subTest(fixture=name):
                fixture = self.load_fixture(name)
                expected = fixture["expected_payment_facts"]
                order_id = expected["order_id"]
                expected_ids = {
                    f"payment:{order_id}:{row['payment_sequential']}" for row in fixture["payments"]
                }
                self.assertEqual(set(expected["evidence_ids"]), expected_ids)


if __name__ == "__main__":
    unittest.main()
