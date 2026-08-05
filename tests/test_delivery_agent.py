"""Comprehensive Unit and Integration Test Suite for TV4 Delivery Agent (Checkpoints 0-5).

Includes:
- Low-level tool & timestamp comparator tests (CP0 & CP1)
- Agent allowlist security & contract validation (CP2)
- Representative branch policy integration tests (CP3)
- Output audit & triage validation for all 50 cases (CP4 & CP5)
"""

import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
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

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "output"


class AuthoritativeEchoInvoker:
    """Mock invoker for PolicyAgent testing."""

    async def ainvoke(self, messages: list) -> dict:
        payload = json.loads(messages[-1].content)
        return payload["authoritative_policy_tool_result"]


def policy_agent_config() -> AgentConfig:
    return next(agent for agent in load_runtime_config().agents if agent.agent_id == "policy_agent")


class TestDeliveryTools(unittest.TestCase):
    """CP0 & CP1: Tool and timestamp comparator unit tests."""

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


class TestDeliveryAgent(unittest.TestCase):
    """CP2 & CP3: Agent security, contract, and PolicyAgent integration tests."""

    def setUp(self):
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


class TestDeliveryOutputAudit(unittest.TestCase):
    """CP4 & CP5: Batch output audit across all 50 official output JSON files."""

    def setUp(self):
        self.output_files = sorted(OUTPUT_DIR.glob("EC_*.json"))
        self.assertEqual(len(self.output_files), 50, "Expected exactly 50 output JSON files in output/")

    def test_all_50_outputs_valid_json_and_case_id_match(self):
        """Verify all 50 output files exist, are valid JSON, and case_id matches filename."""
        for path in self.output_files:
            case_id = path.stem
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.assertEqual(data.get("case_id"), case_id, f"case_id mismatch in {path.name}")

    def test_delivery_distribution_and_zero_undetermined(self):
        """Audit primary issue distribution for delivery cases and ensure 0 undetermined."""
        counts = {}
        for path in self.output_files:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            issue = data["assessment"]["primary_issue"]
            counts[issue] = counts.get(issue, 0) + 1

        self.assertEqual(counts.get("late_delivery_seller"), 8)
        self.assertEqual(counts.get("late_delivery_logistics"), 8)
        self.assertEqual(counts.get("unsupported_late_claim"), 9)
        self.assertNotIn("undetermined", counts)
        self.assertNotIn("POLICY_UNRESOLVED", counts)

    def test_late_delivery_seller_cases(self):
        """Audit late_delivery_seller outputs: seller responsible party, freight refund, refund_freight action."""
        seller_late_files = []
        for path in self.output_files:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data["assessment"]["primary_issue"] == "late_delivery_seller":
                seller_late_files.append(data)

        self.assertEqual(len(seller_late_files), 8)
        for data in seller_late_files:
            self.assertEqual(data["assessment"]["case_status"], "action_required")
            self.assertEqual(data["resolution_actions"], ["refund_freight"])
            causes = [c["cause_code"] for c in data["root_cause_analysis"]["ranked_causes"]]
            self.assertIn("SELLER_HANDOFF_AFTER_LIMIT", causes)
            parties = data["root_cause_analysis"]["responsible_parties"]
            self.assertTrue(any(p["party_type"] == "seller" for p in parties))
            fin = data["financial_resolution"]
            self.assertEqual(fin["recommended_refund_brl"], fin["freight_total_brl"])
            ev = data["evidence_ids"]
            self.assertTrue(any(e.startswith("seller:") for e in ev))
            self.assertIn("policy:SELLER_HANDOFF_AFTER_LIMIT", ev)

    def test_late_delivery_logistics_cases(self):
        """Audit late_delivery_logistics outputs: logistics_provider responsible party, freight refund, refund_freight action."""
        logistics_late_files = []
        for path in self.output_files:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data["assessment"]["primary_issue"] == "late_delivery_logistics":
                logistics_late_files.append(data)

        self.assertEqual(len(logistics_late_files), 8)
        for data in logistics_late_files:
            self.assertEqual(data["assessment"]["case_status"], "action_required")
            self.assertEqual(data["resolution_actions"], ["refund_freight"])
            causes = [c["cause_code"] for c in data["root_cause_analysis"]["ranked_causes"]]
            self.assertIn("CARRIER_DELIVERED_AFTER_ESTIMATE", causes)
            parties = data["root_cause_analysis"]["responsible_parties"]
            self.assertTrue(any(p["party_type"] == "logistics_provider" for p in parties))
            fin = data["financial_resolution"]
            self.assertEqual(fin["recommended_refund_brl"], fin["freight_total_brl"])
            ev = data["evidence_ids"]
            self.assertIn("policy:CARRIER_DELIVERED_AFTER_ESTIMATE", ev)

    def test_unsupported_late_claim_cases(self):
        """Audit unsupported_late_claim outputs: no responsible party, 0.0 refund, reject_late_refund action."""
        unsupported_late_files = []
        for path in self.output_files:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data["assessment"]["primary_issue"] == "unsupported_late_claim":
                unsupported_late_files.append(data)

        self.assertEqual(len(unsupported_late_files), 9)
        for data in unsupported_late_files:
            self.assertEqual(data["assessment"]["case_status"], "no_action")
            self.assertEqual(data["resolution_actions"], ["reject_late_refund"])
            causes = [c["cause_code"] for c in data["root_cause_analysis"]["ranked_causes"]]
            self.assertIn("DELIVERY_WITHIN_ESTIMATE", causes)
            fin = data["financial_resolution"]
            self.assertEqual(fin["recommended_refund_brl"], 0.0)
            ev = data["evidence_ids"]
            self.assertIn("policy:DELIVERY_WITHIN_ESTIMATE", ev)


if __name__ == "__main__":
    unittest.main()
