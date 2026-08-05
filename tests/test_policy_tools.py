from __future__ import annotations

import json
import unittest
from pathlib import Path

from src.tools.policy_tools import PolicyEvaluationError, evaluate_policy


FIXTURE = Path(__file__).parent / "fixtures" / "policy" / "golden_cases.json"


class PolicyToolsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.golden_cases = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def test_all_six_policy_branches(self) -> None:
        self.assertEqual(6, len(self.golden_cases))
        for case in self.golden_cases:
            with self.subTest(case=case["name"]):
                result = evaluate_policy(case["bundle"])
                expected = case["expected"]
                self.assertEqual(expected["primary_issue"], result["primary_issue"])
                self.assertEqual(expected["cause"], result["ranked_causes"][0]["cause_code"])
                self.assertEqual(expected["refund"], result["recommended_refund_brl"])
                self.assertEqual([expected["action"]], result["resolution_actions"])
                self.assertEqual(expected["rule_rank"], result["matched_rule_rank"])

    def test_priority_prefers_canceled_over_late_and_split(self) -> None:
        result = evaluate_policy(self.golden_cases[0]["bundle"])
        self.assertEqual("canceled_order_paid", result["primary_issue"])
        self.assertEqual(1, result["matched_rule_rank"])

    def test_unresolved_bundle_fails_without_inventing_issue(self) -> None:
        bundle = {
            "policy_version": "EC_POLICY_V1",
            "order_seller": {"order_status": "processing", "freight_total_brl": "1.00"},
            "payment": {"payment_total_brl": "1.00", "payment_count": 1, "is_reconciled_within_0_10": False},
            "delivery": {"is_delivered_late": None, "seller_handoff_violations": []},
        }
        with self.assertRaisesRegex(PolicyEvaluationError, "does not match") as raised:
            evaluate_policy(bundle)
        self.assertEqual("POLICY_UNRESOLVED", raised.exception.code)

    def test_tool_emits_trace_event_through_callback_only(self) -> None:
        events = []
        evaluate_policy(
            self.golden_cases[5]["bundle"],
            trace_emit=events.append,
            trace_context={"run_id": "run-test", "case_id": "EC_001", "correlation_id": "c1"},
        )
        self.assertEqual(1, len(events))
        event = events[0]
        self.assertEqual("TOOL_COMPLETED", event["event_type"])
        self.assertEqual("policy_agent", event["agent_id"])
        self.assertEqual("run-test", event["run_id"])
        self.assertIsNotNone(event["input_hash"])


if __name__ == "__main__":
    unittest.main()
