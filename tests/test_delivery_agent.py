"""Unit and Integration tests for DeliveryAgent (Member 4 / TV4 - Checkpoints 2 & 3)."""

import asyncio
from datetime import datetime, timezone
import json
import os
import unittest

from src.agents.delivery import DeliveryAgent, delivery_agent_handler
from src.agents.policy import PolicyAgent
from src.config import load_runtime_config
from src.contracts import (
    AgentConfig,
    CaseInput,
    DeliveryFacts,
    HandoffEnvelope,
    InvestigationBundle,
    OrderSellerFacts,
    PaymentFacts,
    PolicyDecision,
)
from src.tools.delivery_tools import compare_delivery_timestamps


class AuthoritativeEchoInvoker:
    """Mock invoker for PolicyAgent testing."""

    async def ainvoke(self, messages: list) -> dict:
        payload = json.loads(messages[-1].content)
        return payload["authoritative_policy_tool_result"]


def policy_agent_config() -> AgentConfig:
    return next(agent for agent in load_runtime_config().agents if agent.agent_id == "policy_agent")


class TestDeliveryAgent(unittest.TestCase):

    def setUp(self):
        self.fixtures_dir = os.path.join(
            os.path.dirname(__file__), "fixtures", "delivery"
        )
        self.valid_order_id = "e2a03ccf5ea816036608b2d8c3ab8e60"
        self.policy_agent = PolicyAgent(AuthoritativeEchoInvoker(), policy_agent_config())

    def make_case_input(self, order_id: str) -> CaseInput:
        return CaseInput(
            case_id="EC_001",
            opened_at=datetime.now(timezone.utc),
            claimed_order_id=order_id,
            policy_version="EC_POLICY_V1",
            message="Don hang giao tre, de nghi kiem tra quyen loi.",
            language="vi",
        )

    def create_envelope(self, order_id: str) -> HandoffEnvelope:
        return HandoffEnvelope(
            run_id="run_test_cp2",
            case_id="EC_001",
            correlation_id="corr_test_cp2",
            sender="coordinator_agent",
            receiver="delivery_agent",
            message_type="TASK_REQUEST",
            payload={"claimed_order_id": order_id, "case_id": "EC_001"},
        )

    def test_tool_allowlist_security(self):
        """CP2: Allowed tools pass, unallowed tools raise PermissionError."""
        agent = DeliveryAgent()
        agent.validate_tool_access("get_delivery_timeline")
        agent.validate_tool_access("get_shipping_limits")
        agent.validate_tool_access("compare_delivery_timestamps")

        with self.assertRaises(PermissionError):
            agent.validate_tool_access("get_payments")

        with self.assertRaises(PermissionError):
            agent.validate_tool_access("execute_refund")

    def test_process_task_contract_validity(self):
        """CP2: DeliveryAgent handler adheres to A2A HandoffEnvelope standards."""
        envelope = self.create_envelope(self.valid_order_id)
        result = asyncio.run(delivery_agent_handler(envelope))

        facts = DeliveryFacts.model_validate(result)
        self.assertEqual(facts.order_id, self.valid_order_id)
        self.assertIn(facts.late_stage, ["seller", "logistics", "not_late", "undetermined"])
        self.assertIsInstance(facts.is_late, bool)
        self.assertIsInstance(facts.evidence_ids, list)
        self.assertLessEqual(len(facts.evidence_ids), 10)

    def test_delivery_on_time_facts_and_policy_integration(self):
        """CP3: On-time delivery -> DeliveryFacts(not_late) -> Policy(unsupported_late_claim)."""
        valid_oid = "a" * 32
        timeline = {
            "order_id": valid_oid,
            "delivered_customer_at": "2018-05-10 12:00:00",
            "estimated_delivery_at": "2018-05-15 00:00:00",
            "delivered_carrier_at": "2018-05-05 10:00:00",
        }
        items = [{"order_item_id": 1, "seller_id": "sel_on_time", "shipping_limit_date": "2018-05-07 00:00:00"}]
        raw = compare_delivery_timestamps(valid_oid, timeline, items)

        delivery_facts = DeliveryFacts(
            order_id=valid_oid,
            is_late=raw["is_delivered_late"],
            late_stage=raw["late_stage"],
            violating_seller_ids=[],
            delivered_carrier_at=raw["delivered_carrier_at"],
            delivered_customer_at=raw["delivered_customer_at"],
            estimated_delivery_at=raw["estimated_delivery_at"],
            evidence_ids=raw["evidence_ids"],
        )

        self.assertFalse(delivery_facts.is_late)
        self.assertEqual(delivery_facts.late_stage, "not_late")

        bundle = InvestigationBundle(
            case=self.make_case_input(valid_oid),
            order_seller=OrderSellerFacts(
                order_id=valid_oid,
                order_status="delivered",
                item_total_brl="100.00",
                freight_total_brl="15.00",
            ),
            payment=PaymentFacts(
                order_id=valid_oid,
                payment_total_brl="115.00",
                payment_count=1,
                is_reconciled=True,
            ),
            delivery=delivery_facts,
        )

        envelope = HandoffEnvelope(
            run_id="run_cp3",
            case_id="EC_001",
            correlation_id="corr_cp3",
            sender="coordinator_agent",
            receiver="policy_agent",
            message_type="POLICY_REQUEST",
            payload=bundle.model_dump(mode="json"),
        )

        decision_raw = asyncio.run(self.policy_agent(envelope))
        decision = PolicyDecision.model_validate(decision_raw)
        self.assertEqual(decision.primary_issue, "unsupported_late_claim")
        self.assertEqual(decision.ranked_causes[0].cause_code, "DELIVERY_WITHIN_ESTIMATE")

    def test_delivery_seller_late_facts_and_policy_integration(self):
        """CP3: Seller late handoff -> DeliveryFacts(seller) -> Policy(late_delivery_seller)."""
        valid_oid = "b" * 32
        timeline = {
            "order_id": valid_oid,
            "delivered_customer_at": "2018-05-20 12:00:00",
            "estimated_delivery_at": "2018-05-15 00:00:00",
            "delivered_carrier_at": "2018-05-10 10:00:00",
        }
        items = [{"order_item_id": 1, "seller_id": "sel_late_123", "shipping_limit_date": "2018-05-07 00:00:00"}]
        raw = compare_delivery_timestamps(valid_oid, timeline, items)

        delivery_facts = DeliveryFacts(
            order_id=valid_oid,
            is_late=raw["is_delivered_late"],
            late_stage=raw["late_stage"],
            violating_seller_ids=["sel_late_123"],
            delivered_carrier_at=raw["delivered_carrier_at"],
            delivered_customer_at=raw["delivered_customer_at"],
            estimated_delivery_at=raw["estimated_delivery_at"],
            evidence_ids=raw["evidence_ids"],
        )

        self.assertTrue(delivery_facts.is_late)
        self.assertEqual(delivery_facts.late_stage, "seller")

        bundle = InvestigationBundle(
            case=self.make_case_input(valid_oid),
            order_seller=OrderSellerFacts(
                order_id=valid_oid,
                order_status="delivered",
                item_total_brl="100.00",
                freight_total_brl="15.00",
            ),
            payment=PaymentFacts(
                order_id=valid_oid,
                payment_total_brl="115.00",
                payment_count=1,
                is_reconciled=True,
            ),
            delivery=delivery_facts,
        )

        envelope = HandoffEnvelope(
            run_id="run_cp3",
            case_id="EC_001",
            correlation_id="corr_cp3",
            sender="coordinator_agent",
            receiver="policy_agent",
            message_type="POLICY_REQUEST",
            payload=bundle.model_dump(mode="json"),
        )

        decision_raw = asyncio.run(self.policy_agent(envelope))
        decision = PolicyDecision.model_validate(decision_raw)
        self.assertEqual(decision.primary_issue, "late_delivery_seller")
        self.assertEqual(decision.ranked_causes[0].cause_code, "SELLER_HANDOFF_AFTER_LIMIT")
        self.assertEqual(decision.responsible_parties[0].party_id, "sel_late_123")

    def test_delivery_logistics_late_facts_and_policy_integration(self):
        """CP3: Logistics late delivery -> DeliveryFacts(logistics) -> Policy(late_delivery_logistics)."""
        valid_oid = "c" * 32
        timeline = {
            "order_id": valid_oid,
            "delivered_customer_at": "2018-05-20 12:00:00",
            "estimated_delivery_at": "2018-05-15 00:00:00",
            "delivered_carrier_at": "2018-05-06 10:00:00",
        }
        items = [{"order_item_id": 1, "seller_id": "sel_good_123", "shipping_limit_date": "2018-05-07 00:00:00"}]
        raw = compare_delivery_timestamps(valid_oid, timeline, items)

        delivery_facts = DeliveryFacts(
            order_id=valid_oid,
            is_late=raw["is_delivered_late"],
            late_stage=raw["late_stage"],
            violating_seller_ids=[],
            delivered_carrier_at=raw["delivered_carrier_at"],
            delivered_customer_at=raw["delivered_customer_at"],
            estimated_delivery_at=raw["estimated_delivery_at"],
            evidence_ids=raw["evidence_ids"],
        )

        self.assertTrue(delivery_facts.is_late)
        self.assertEqual(delivery_facts.late_stage, "logistics")

        bundle = InvestigationBundle(
            case=self.make_case_input(valid_oid),
            order_seller=OrderSellerFacts(
                order_id=valid_oid,
                order_status="delivered",
                item_total_brl="100.00",
                freight_total_brl="15.00",
            ),
            payment=PaymentFacts(
                order_id=valid_oid,
                payment_total_brl="115.00",
                payment_count=1,
                is_reconciled=True,
            ),
            delivery=delivery_facts,
        )

        envelope = HandoffEnvelope(
            run_id="run_cp3",
            case_id="EC_001",
            correlation_id="corr_cp3",
            sender="coordinator_agent",
            receiver="policy_agent",
            message_type="POLICY_REQUEST",
            payload=bundle.model_dump(mode="json"),
        )

        decision_raw = asyncio.run(self.policy_agent(envelope))
        decision = PolicyDecision.model_validate(decision_raw)
        self.assertEqual(decision.primary_issue, "late_delivery_logistics")
        self.assertEqual(decision.ranked_causes[0].cause_code, "CARRIER_DELIVERED_AFTER_ESTIMATE")


if __name__ == "__main__":
    unittest.main()
