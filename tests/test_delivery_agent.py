"""Unit tests for DeliveryAgent (Member 4 / TV4 - Checkpoint 2)."""

import asyncio
import json
import os
import unittest

from src.agents.delivery import DeliveryAgent, delivery_agent_handler
from src.contracts import DeliveryFacts, HandoffEnvelope


class TestDeliveryAgent(unittest.TestCase):

    def setUp(self):
        self.fixtures_dir = os.path.join(
            os.path.dirname(__file__), "fixtures", "delivery"
        )
        self.valid_order_id = "e2a03ccf5ea816036608b2d8c3ab8e60"

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
        agent = DeliveryAgent()
        # Allowed tools should pass
        agent.validate_tool_access("get_delivery_timeline")
        agent.validate_tool_access("get_shipping_limits")
        agent.validate_tool_access("compare_delivery_timestamps")

        # Unallowed tool must raise PermissionError
        with self.assertRaises(PermissionError):
            agent.validate_tool_access("get_payments")

        with self.assertRaises(PermissionError):
            agent.validate_tool_access("execute_refund")

    def test_process_task_contract_validity(self):
        envelope = self.create_envelope(self.valid_order_id)
        result = asyncio.run(delivery_agent_handler(envelope))

        # Result must validate against DeliveryFacts Pydantic model
        facts = DeliveryFacts.model_validate(result)
        self.assertEqual(facts.order_id, self.valid_order_id)
        self.assertIn(facts.late_stage, ["seller", "logistics", "not_late", "undetermined"])
        self.assertIsInstance(facts.is_late, bool)
        self.assertIsInstance(facts.evidence_ids, list)

    def test_delivery_agent_scenarios(self):
        agent = DeliveryAgent()
        
        # Test with mock timeline data
        envelope = self.create_envelope("00010242fe8c5a6d1ba2dd792cb16214")
        result = asyncio.run(agent.process_task(envelope))
        self.assertIn("order_id", result)
        self.assertIn("late_stage", result)


if __name__ == "__main__":
    unittest.main()
