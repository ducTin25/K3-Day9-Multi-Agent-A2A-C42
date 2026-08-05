"""Unit tests for PaymentAgent (Member 3 / TV3 - Checkpoint 2)."""

import asyncio
import unittest
from decimal import Decimal

from src.agents.payment import PaymentAgent, payment_agent_handler
from src.contracts import HandoffEnvelope, PaymentFacts


class TestPaymentAgent(unittest.TestCase):

    def setUp(self):
        # order with 1 item (79.80 + freight 19.53 = 99.33) and 1 payment row 99.33
        self.single_payment_order_id = "b81ef226f3fe1789b1e8b2acac839d17"
        # order with 1 item (49.75 + freight 20.80 = 70.55) and 2 payment rows 17.92 + 52.63
        self.split_payment_order_id = "0016dfedd97fc2950e388d2971d718c7"

    def create_envelope(self, order_id: str) -> HandoffEnvelope:
        return HandoffEnvelope(
            run_id="run_test_cp2",
            case_id="EC_001",
            correlation_id="corr_test_cp2",
            sender="coordinator_agent",
            receiver="payment_agent",
            message_type="TASK_REQUEST",
            payload={"claimed_order_id": order_id, "case_id": "EC_001"},
        )

    def test_tool_allowlist_security(self):
        agent = PaymentAgent()
        agent.validate_tool_access("get_order_payments")
        agent.validate_tool_access("get_order_financial_reference")
        agent.validate_tool_access("reconcile_payments")

        with self.assertRaises(PermissionError):
            agent.validate_tool_access("issue_refund")

        with self.assertRaises(PermissionError):
            agent.validate_tool_access("get_delivery_timeline")

    def test_missing_order_id_raises(self):
        agent = PaymentAgent()
        envelope = HandoffEnvelope(
            run_id="run_test_cp2",
            case_id="EC_001",
            correlation_id="corr_test_cp2",
            sender="coordinator_agent",
            receiver="payment_agent",
            message_type="TASK_REQUEST",
            payload={"case_id": "EC_001"},
        )
        with self.assertRaises(ValueError):
            asyncio.run(agent.process_task(envelope))

    def test_process_task_contract_validity_single_payment(self):
        envelope = self.create_envelope(self.single_payment_order_id)
        result = asyncio.run(payment_agent_handler(envelope))

        facts = PaymentFacts.model_validate(result)
        self.assertEqual(facts.order_id, self.single_payment_order_id)
        self.assertEqual(facts.payment_count, 1)
        self.assertEqual(facts.payment_total_brl, Decimal("99.33"))
        self.assertEqual(facts.reconciliation_delta_brl, Decimal("0.00"))
        self.assertTrue(facts.is_reconciled)
        self.assertEqual(facts.evidence_ids, [f"payment:{self.single_payment_order_id}:1"])

    def test_process_task_split_payment_ids_are_sequential(self):
        agent = PaymentAgent()
        envelope = self.create_envelope(self.split_payment_order_id)
        result = asyncio.run(agent.process_task(envelope))

        facts = PaymentFacts.model_validate(result)
        self.assertEqual(facts.payment_count, 2)
        self.assertEqual(facts.payment_total_brl, Decimal("70.55"))
        self.assertTrue(facts.is_reconciled)

        # Payment IDs must be sequential (1, 2, ...), matching payment_sequential order.
        sequentials = [row.payment_sequential for row in facts.payments]
        self.assertEqual(sequentials, sorted(sequentials))
        self.assertEqual(sequentials, list(range(1, len(sequentials) + 1)))
        self.assertEqual(
            facts.evidence_ids,
            [f"payment:{self.split_payment_order_id}:{seq}" for seq in sequentials],
        )

    def test_output_uses_decimal_derived_totals_not_multiplied_by_installments(self):
        # single_payment_order has payment_installments possibly > 1; total must still
        # equal the row's own payment_value_brl, never value * installments.
        envelope = self.create_envelope(self.single_payment_order_id)
        result = asyncio.run(payment_agent_handler(envelope))
        facts = PaymentFacts.model_validate(result)

        row = facts.payments[0]
        self.assertEqual(facts.payment_total_brl, row.payment_value_brl)
        if row.payment_installments > 1:
            self.assertNotEqual(
                facts.payment_total_brl, row.payment_value_brl * row.payment_installments
            )

    def test_unknown_order_returns_zero_facts(self):
        envelope = self.create_envelope("0" * 32)
        result = asyncio.run(payment_agent_handler(envelope))
        facts = PaymentFacts.model_validate(result)

        self.assertEqual(facts.payment_count, 0)
        self.assertEqual(facts.payment_total_brl, Decimal("0.00"))
        self.assertTrue(facts.is_reconciled)
        self.assertEqual(facts.evidence_ids, [])


if __name__ == "__main__":
    unittest.main()
