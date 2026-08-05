from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.contracts import VerifyResult
from src.output_writer import AtomicOutputWriter, OutputWriteError


ORDER_ID = "a" * 32


def valid_output() -> dict:
    return {
        "case_id": "EC_001",
        "assessment": {
            "primary_issue": "unsupported_late_claim",
            "case_status": "no_action",
            "confidence": 1.0,
        },
        "affected_entities": {
            "order_ids": [ORDER_ID],
            "item_ids": [],
            "seller_ids": [],
            "payment_ids": [],
        },
        "root_cause_analysis": {
            "ranked_causes": [{"cause_code": "DELIVERY_WITHIN_ESTIMATE", "rank": 1}],
            "responsible_parties": [],
        },
        "evidence_ids": [f"order:{ORDER_ID}", "policy:DELIVERY_WITHIN_ESTIMATE"],
        "financial_resolution": {
            "currency": "BRL",
            "item_total_brl": 0.0,
            "freight_total_brl": 0.0,
            "payment_total_brl": 0.0,
            "recommended_refund_brl": 0.0,
        },
        "resolution_actions": ["reject_late_refund"],
    }


def test_writer_atomically_writes_verified_schema_valid_output(tmp_path: Path) -> None:
    writer = AtomicOutputWriter(tmp_path)
    path = writer.write_verified(
        valid_output(), VerifyResult(valid=True), expected_case_id="EC_001"
    )
    assert path == tmp_path / "EC_001.json"
    assert json.loads(path.read_text(encoding="utf-8"))["case_id"] == "EC_001"
    assert list(tmp_path.glob("*.tmp")) == []


def test_writer_rejects_unverified_output_without_creating_file(tmp_path: Path) -> None:
    writer = AtomicOutputWriter(tmp_path)
    with pytest.raises(OutputWriteError, match="did not pass Verifier"):
        writer.write_verified(
            valid_output(), VerifyResult(valid=False), expected_case_id="EC_001"
        )
    assert list(tmp_path.iterdir()) == []


def test_writer_rejects_schema_error_and_case_mismatch(tmp_path: Path) -> None:
    writer = AtomicOutputWriter(tmp_path)
    payload = valid_output()
    payload["assessment"]["confidence"] = 2.0
    with pytest.raises(OutputWriteError, match="schema validation failed"):
        writer.write_verified(payload, VerifyResult(valid=True), expected_case_id="EC_001")
    payload = valid_output()
    with pytest.raises(OutputWriteError, match="does not match"):
        writer.write_verified(payload, VerifyResult(valid=True), expected_case_id="EC_002")
    assert list(tmp_path.iterdir()) == []
