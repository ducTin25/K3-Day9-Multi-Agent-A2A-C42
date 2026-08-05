"""Financial audit for Checkpoint 3 (Member 3 / TV3).

TV3's CP3 role is a cross-check, not a new module: "Theo dõi totals va refund
source; xu ly sai khac contract giua order totals/payment" + "Review financial
output TV5" + "Tat ca tien recompute khop Decimal va rule".

Two independent audits:
1. order_seller.item_total_brl/freight_total_brl (TV2, src/data/olist_repository.py)
   vs the Payment domain's own reference totals (TV3, src/tools/payment_tools.py) -
   both read the same CSVs independently; this proves they still agree today
   and gives a regression test if either implementation ever drifts.
2. Refund-per-rule recompute, done from scratch with src/finance.py (not by
   importing src/tools/policy_tools.py's branches), cross-checked against
   TV5's real evaluate_policy() on the same 6 golden cases TV5 already owns
   (tests/fixtures/policy/golden_cases.json).
"""

from __future__ import annotations

import csv
import json
import os
import unittest
from decimal import Decimal
from pathlib import Path

from src.data.olist_repository import OlistRepository
from src.finance import to_money
from src.tools.payment_tools import get_order_financial_reference
from src.tools.policy_tools import evaluate_policy

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures", "policy")


def _sample_orders_with_payments(limit: int) -> list[str]:
    """Deterministic sample of real order_ids that have at least one payment row."""
    order_ids: list[str] = []
    seen: set[str] = set()
    with open(DATA_DIR / "olist_order_payments_dataset.csv", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            order_id = row["order_id"]
            if order_id not in seen:
                seen.add(order_id)
                order_ids.append(order_id)
            if len(order_ids) >= limit:
                break
    return order_ids


class TestOrderTotalsCrossCheckWithPaymentDomain(unittest.TestCase):
    """Audit 1: order_seller totals (TV2) must agree with the Payment domain's
    own independently-computed reference totals (TV3) for the same order_id."""

    @classmethod
    def setUpClass(cls):
        cls.repository = OlistRepository(DATA_DIR)
        cls.sample_order_ids = _sample_orders_with_payments(limit=40)

    def test_item_and_freight_totals_agree_across_domains(self):
        mismatches = []
        for order_id in self.sample_order_ids:
            try:
                order_seller_facts = self.repository.get_order_seller_facts(order_id)
            except KeyError:
                continue
            reference = get_order_financial_reference(order_id)

            if order_seller_facts.item_total_brl != reference["item_total_brl"]:
                mismatches.append(
                    (order_id, "item_total_brl", order_seller_facts.item_total_brl, reference["item_total_brl"])
                )
            if order_seller_facts.freight_total_brl != reference["freight_total_brl"]:
                mismatches.append(
                    (order_id, "freight_total_brl", order_seller_facts.freight_total_brl, reference["freight_total_brl"])
                )

        self.assertEqual(
            mismatches, [],
            f"order_seller (TV2) and payment_tools (TV3) totals disagree for: {mismatches[:10]}",
        )

    def test_sample_is_non_trivial(self):
        # Guard against the audit silently checking zero orders if data/ changes shape.
        self.assertGreaterEqual(len(self.sample_order_ids), 30)


def _recompute_expected_refund(bundle: dict) -> Decimal:
    """Independent re-derivation of the EC_POLICY_V1 refund amount straight from
    README muc 4, using src/finance.py only. Deliberately does not import
    src/tools/policy_tools.py so this is a real second implementation, not a
    call into the code under audit."""

    order = bundle["order_seller"]
    payment = bundle["payment"]
    delivery = bundle["delivery"]

    order_status = str(order.get("order_status") or "").lower()
    payment_total = to_money(payment.get("payment_total_brl", 0))
    freight_total = to_money(order.get("freight_total_brl", 0))

    if order_status == "canceled" and payment_total > 0:
        return payment_total
    if order_status == "unavailable" and payment_total > 0:
        return payment_total

    is_late = delivery.get("is_delivered_late")
    violations = delivery.get("seller_handoff_violations") or []
    if is_late is True and violations:
        return freight_total
    if is_late is True and not violations:
        return freight_total

    payment_count = int(payment.get("payment_count", 0))
    reconciled = payment.get("is_reconciled_within_0_10") is True
    if payment_count >= 2 and reconciled:
        return Decimal("0.00")
    if is_late is False and reconciled:
        return Decimal("0.00")

    raise AssertionError("bundle does not match any EC_POLICY_V1 rule")


class TestRefundRecomputeAgainstPolicyAgent(unittest.TestCase):
    """Audit 2: independently recomputed refund must match TV5's real
    evaluate_policy() output for every golden case TV5 already maintains."""

    def load_golden_cases(self):
        path = os.path.join(FIXTURES_DIR, "golden_cases.json")
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)

    def test_all_golden_cases_recompute_to_same_refund(self):
        cases = self.load_golden_cases()
        self.assertEqual(len(cases), 6, "expected all 6 EC_POLICY_V1 branches")

        for case in cases:
            with self.subTest(case=case["name"]):
                bundle = case["bundle"]
                policy_result = evaluate_policy(bundle)
                independent_refund = _recompute_expected_refund(bundle)

                self.assertEqual(
                    to_money(policy_result["recommended_refund_brl"]),
                    independent_refund,
                    f"policy_agent refund vs independent Decimal recompute mismatch for {case['name']}",
                )
                self.assertEqual(
                    independent_refund, to_money(case["expected"]["refund"]),
                    f"independent recompute vs fixture 'expected' mismatch for {case['name']}",
                )


if __name__ == "__main__":
    unittest.main()
