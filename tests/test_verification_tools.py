from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from src.tools.verification_tools import REQUIRED_AGENT_IDS, validate_metadata, verify_output


def valid_output() -> dict:
    order_id = "abc123"
    seller_id = "seller123"
    return {
        "case_id": "EC_001",
        "assessment": {"primary_issue": "late_delivery_seller", "case_status": "action_required", "confidence": 0.95},
        "affected_entities": {
            "order_ids": [order_id],
            "item_ids": [f"{order_id}:1"],
            "seller_ids": [seller_id],
            "payment_ids": [f"{order_id}:1"],
        },
        "root_cause_analysis": {
            "ranked_causes": [{"cause_code": "SELLER_HANDOFF_AFTER_LIMIT", "rank": 1}],
            "responsible_parties": [{"party_type": "seller", "party_id": seller_id}],
        },
        "evidence_ids": [
            f"order:{order_id}",
            f"item:{order_id}:1",
            f"payment:{order_id}:1",
            f"seller:{seller_id}",
            "policy:SELLER_HANDOFF_AFTER_LIMIT",
        ],
        "financial_resolution": {
            "currency": "BRL",
            "item_total_brl": 100.0,
            "freight_total_brl": 15.0,
            "payment_total_brl": 115.0,
            "recommended_refund_brl": 15.0,
        },
        "resolution_actions": ["refund_freight"],
    }


class VerificationToolsTests(unittest.TestCase):
    def test_valid_output_passes_and_emits_trace(self) -> None:
        events = []
        result = verify_output(
            valid_output(),
            expected_case_id="EC_001",
            evidence_lookup=lambda _: True,
            trace_emit=events.append,
            trace_context={"run_id": "r1", "case_id": "EC_001"},
        )
        self.assertTrue(result["valid"])
        self.assertEqual([], result["errors"])
        self.assertEqual("verifier_agent", events[0]["agent_id"])

    def test_wrong_refund_and_missing_evidence_are_rejected(self) -> None:
        output = valid_output()
        output["financial_resolution"]["recommended_refund_brl"] = 115.0
        result = verify_output(output, evidence_lookup=lambda evidence: not evidence.startswith("seller:"))
        codes = {error["code"] for error in result["errors"]}
        self.assertFalse(result["valid"])
        self.assertIn("FINANCIAL_REFUND_MISMATCH", codes)
        self.assertIn("EVIDENCE_NOT_FOUND", codes)

    def test_schema_files_are_valid_json(self) -> None:
        schemas = Path(__file__).parents[1] / "src" / "schemas"
        for path in schemas.glob("*.schema.json"):
            with self.subTest(path=path.name):
                self.assertIsInstance(json.loads(path.read_text(encoding="utf-8")), dict)

    def test_metadata_accepts_six_evidenced_small_models(self) -> None:
        metadata = {
            "framework": "custom-python",
            "runtime": "python-3.12",
            "agents": [
                {
                    "agent_id": agent_id,
                    "model_name": "documented-8b-model",
                    "parameter_count": 8_000_000_000,
                    "prompt_version": "v1",
                    "tools": [],
                    "fallback_models": [],
                }
                for agent_id in sorted(REQUIRED_AGENT_IDS)
            ],
        }
        self.assertEqual([], validate_metadata(metadata))

    def test_gpt_4o_mini_without_published_parameter_count_is_unverified(self) -> None:
        metadata = {
            "framework": "custom-python",
            "runtime": "python-3.12",
            "agents": [
                {
                    "agent_id": agent_id,
                    "model_name": "gpt-4o-mini",
                    "parameter_count": None,
                    "parameter_limit_status": "unverified",
                    "prompt_version": "v1",
                    "tools": [],
                    "fallback_models": [],
                }
                for agent_id in sorted(REQUIRED_AGENT_IDS)
            ],
        }
        errors = validate_metadata(metadata)
        self.assertEqual(6, sum(error["code"] == "MODEL_PARAMETER_COUNT_UNVERIFIED" for error in errors))

    def test_model_over_10b_is_hard_failure(self) -> None:
        metadata = {
            "framework": "custom-python",
            "runtime": "python-3.12",
            "agents": [
                {"agent_id": agent_id, "model_name": "too-large", "parameter_count": 10_000_000_001, "prompt_version": "v1", "tools": [], "fallback_models": []}
                for agent_id in sorted(REQUIRED_AGENT_IDS)
            ],
        }
        self.assertTrue(any(error["code"] == "MODEL_PARAMETER_LIMIT_EXCEEDED" for error in validate_metadata(metadata)))


if __name__ == "__main__":
    unittest.main()
