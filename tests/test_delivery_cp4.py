"""Checkpoint 4 Audit & Triage test suite for TV4 (Delivery Agent).

Audits all 50 generated output JSON files in output/ to ensure:
1. 0 undetermined or unhandled delivery cases.
2. 100% correct primary issue & root cause mapping for delivery cases:
   - late_delivery_seller (8 cases)
   - late_delivery_logistics (8 cases)
   - unsupported_late_claim (9 cases)
3. Correct responsible parties and evidence ID formats.
"""

import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "output"


class TestDeliveryCheckpoint4(unittest.TestCase):

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
            self.assertIn("assessment", data)
            self.assertIn("financial_resolution", data)
            self.assertIn("root_cause_analysis", data)

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
            
            # Cause code
            causes = [c["cause_code"] for c in data["root_cause_analysis"]["ranked_causes"]]
            self.assertIn("SELLER_HANDOFF_AFTER_LIMIT", causes)

            # Responsible party
            parties = data["root_cause_analysis"]["responsible_parties"]
            self.assertTrue(any(p["party_type"] == "seller" for p in parties))

            # Refund equals freight
            fin = data["financial_resolution"]
            self.assertEqual(fin["recommended_refund_brl"], fin["freight_total_brl"])
            self.assertGreater(fin["recommended_refund_brl"], 0.0)

            # Evidence IDs contain seller: and item: and policy:SELLER_HANDOFF_AFTER_LIMIT
            ev = data["evidence_ids"]
            self.assertTrue(any(e.startswith("seller:") for e in ev))
            self.assertTrue(any(e.startswith("item:") for e in ev))
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

            # Cause code
            causes = [c["cause_code"] for c in data["root_cause_analysis"]["ranked_causes"]]
            self.assertIn("CARRIER_DELIVERED_AFTER_ESTIMATE", causes)

            # Responsible party
            parties = data["root_cause_analysis"]["responsible_parties"]
            self.assertTrue(any(p["party_type"] == "logistics_provider" for p in parties))

            # Refund equals freight
            fin = data["financial_resolution"]
            self.assertEqual(fin["recommended_refund_brl"], fin["freight_total_brl"])
            self.assertGreater(fin["recommended_refund_brl"], 0.0)

            # Evidence IDs contain policy:CARRIER_DELIVERED_AFTER_ESTIMATE
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

            # Cause code
            causes = [c["cause_code"] for c in data["root_cause_analysis"]["ranked_causes"]]
            self.assertIn("DELIVERY_WITHIN_ESTIMATE", causes)

            # 0.0 refund
            fin = data["financial_resolution"]
            self.assertEqual(fin["recommended_refund_brl"], 0.0)

            # Evidence IDs contain policy:DELIVERY_WITHIN_ESTIMATE
            ev = data["evidence_ids"]
            self.assertIn("policy:DELIVERY_WITHIN_ESTIMATE", ev)


if __name__ == "__main__":
    unittest.main()
