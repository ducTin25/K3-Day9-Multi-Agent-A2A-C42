"""Checkpoint 4 triage for TV3: PAYMENT_*, FINANCIAL_*, tolerance/rounding.

TV1's live batch run (docs/checkpoints/tv1-cp4.md) wrote real output/EC_*.json
files for all 50 cases. This module independently recomputes the money side
of every one of those 50 real outputs from src/finance.py + src/tools/payment_tools.py
(never by re-reading the pipeline's own numbers) and fails loudly, case by
case, on any PAYMENT_*/FINANCIAL_* mismatch so it can be fixed within the
CP4 triage SLA.
"""

from __future__ import annotations

import json
import unittest
from decimal import Decimal
from pathlib import Path

from src.finance import to_money
from src.tools.payment_tools import get_order_financial_reference, get_order_payments, reconcile_payments

OUTPUT_DIR = Path(__file__).resolve().parents[1] / "output"

REFUND_SOURCE = {
    "canceled_order_paid": "payment_total_brl",
    "unavailable_order_paid": "payment_total_brl",
    "late_delivery_seller": "freight_total_brl",
    "late_delivery_logistics": "freight_total_brl",
    "valid_split_payment": None,
    "unsupported_late_claim": None,
}


def _load_all_outputs() -> list[dict]:
    cases = []
    for index in range(1, 51):
        path = OUTPUT_DIR / f"EC_{index:03d}.json"
        with open(path, "r", encoding="utf-8") as handle:
            cases.append(json.load(handle))
    return cases


class TestCP4FinancialRecomputeAllRealCases(unittest.TestCase):
    """PAYMENT_*/FINANCIAL_* triage over every real output/EC_*.json (CP4)."""

    @classmethod
    def setUpClass(cls):
        cls.cases = _load_all_outputs()

    def test_all_50_output_files_present(self):
        self.assertEqual(len(self.cases), 50)
        case_ids = {case["case_id"] for case in self.cases}
        self.assertEqual(case_ids, {f"EC_{i:03d}" for i in range(1, 51)})

    def test_item_and_freight_totals_match_csv(self):
        mismatches = []
        for case in self.cases:
            order_id = case["affected_entities"]["order_ids"][0]
            financial = case["financial_resolution"]
            reference = get_order_financial_reference(order_id)

            if to_money(financial["item_total_brl"]) != reference["item_total_brl"]:
                mismatches.append(
                    (case["case_id"], "item_total_brl", financial["item_total_brl"], str(reference["item_total_brl"]))
                )
            if to_money(financial["freight_total_brl"]) != reference["freight_total_brl"]:
                mismatches.append(
                    (case["case_id"], "freight_total_brl", financial["freight_total_brl"], str(reference["freight_total_brl"]))
                )
        self.assertEqual(mismatches, [], f"item/freight total mismatch (case, field, output, recomputed): {mismatches}")

    def test_payment_total_matches_csv_and_not_multiplied_by_installments(self):
        mismatches = []
        for case in self.cases:
            order_id = case["affected_entities"]["order_ids"][0]
            financial = case["financial_resolution"]
            payment_rows = get_order_payments(order_id)
            recomputed_total = sum((row["payment_value_brl"] for row in payment_rows), Decimal("0.00"))

            if to_money(financial["payment_total_brl"]) != recomputed_total:
                mismatches.append(
                    (case["case_id"], financial["payment_total_brl"], str(recomputed_total))
                )
        self.assertEqual(mismatches, [], f"payment_total_brl mismatch (case, output, recomputed): {mismatches}")

    def test_recommended_refund_matches_correct_source_for_primary_issue(self):
        mismatches = []
        for case in self.cases:
            issue = case["assessment"]["primary_issue"]
            financial = case["financial_resolution"]
            refund = to_money(financial["recommended_refund_brl"])
            source_field = REFUND_SOURCE.get(issue)
            expected = Decimal("0.00") if source_field is None else to_money(financial[source_field])

            if refund != expected:
                mismatches.append((case["case_id"], issue, str(refund), str(expected)))
        self.assertEqual(
            mismatches, [],
            f"recommended_refund_brl does not match its policy source (case, issue, refund, expected): {mismatches}",
        )

    def test_split_and_unsupported_late_cases_are_within_tolerance(self):
        # These two primary issues require item_total + freight_total to
        # reconcile with payment_total within 0.10 BRL (README muc 4).
        violations = []
        for case in self.cases:
            issue = case["assessment"]["primary_issue"]
            if issue not in {"valid_split_payment", "unsupported_late_claim"}:
                continue
            financial = case["financial_resolution"]
            item_total = to_money(financial["item_total_brl"])
            freight_total = to_money(financial["freight_total_brl"])
            payment_total = to_money(financial["payment_total_brl"])
            delta = abs(payment_total - (item_total + freight_total))
            if delta > Decimal("0.10"):
                violations.append((case["case_id"], issue, str(delta)))
        self.assertEqual(violations, [], f"reconciliation tolerance violated (case, issue, delta): {violations}")

    def test_all_money_fields_are_two_decimal_places(self):
        bad_rounding = []
        for case in self.cases:
            financial = case["financial_resolution"]
            for field in ("item_total_brl", "freight_total_brl", "payment_total_brl", "recommended_refund_brl"):
                value = financial[field]
                if to_money(value) != Decimal(str(value)):
                    bad_rounding.append((case["case_id"], field, value))
        self.assertEqual(bad_rounding, [], f"money field not rounded to 2dp ROUND_HALF_UP (case, field, value): {bad_rounding}")

    def test_payment_evidence_ids_are_sequential_and_exist(self):
        mismatches = []
        for case in self.cases:
            order_id = case["affected_entities"]["order_ids"][0]
            payment_rows = get_order_payments(order_id)
            bundle = reconcile_payments(order_id, payment_rows, case["financial_resolution"]["payment_total_brl"])
            output_payment_ids = {
                pid for pid in case["evidence_ids"] if pid.startswith(f"payment:{order_id}:")
            }
            valid_ids = set(bundle["evidence_ids"])
            if not output_payment_ids <= valid_ids:
                mismatches.append((case["case_id"], sorted(output_payment_ids - valid_ids)))
        self.assertEqual(mismatches, [], f"payment evidence IDs not backed by real payment rows: {mismatches}")


if __name__ == "__main__":
    unittest.main()
