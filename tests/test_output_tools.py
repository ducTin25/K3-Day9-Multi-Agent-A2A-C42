from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from src.agents.tv5_handlers import assemble_tv5_draft
from src.contracts import InvestigationBundle, PolicyDecision
from src.tools.output_tools import DraftAssemblyError, assemble_output
from src.tools.policy_tools import evaluate_policy
from src.tools.verification_tools import verify_output
from src.tracing import TraceSink
from tests.test_tv5_checkpoint3 import handoff
from tests.test_tv5_checkpoint3 import bundle_for


def decision_for(bundle: InvestigationBundle) -> PolicyDecision:
    return PolicyDecision.model_validate(evaluate_policy(bundle))


@pytest.mark.parametrize(
    ("issue", "case_number"),
    [
        ("canceled_order_paid", 11),
        ("unavailable_order_paid", 12),
        ("late_delivery_seller", 13),
        ("late_delivery_logistics", 14),
        ("valid_split_payment", 15),
        ("unsupported_late_claim", 16),
    ],
)
def test_assemble_output_passes_verifier_for_all_policy_branches(
    issue: str, case_number: int
) -> None:
    bundle = bundle_for(issue, case_number)
    output = assemble_output(bundle, decision_for(bundle))

    assert output["assessment"]["primary_issue"] == issue
    assert output["evidence_ids"][0].startswith("policy:")
    assert verify_output(output, expected_case_id=bundle.case.case_id)["valid"] is True


def test_assemble_output_emits_trace_metadata_without_raw_payload() -> None:
    bundle = bundle_for("late_delivery_seller", 17)
    events: list[dict] = []

    output = assemble_output(
        bundle,
        decision_for(bundle),
        trace_emit=events.append,
        trace_context={
            "run_id": "run-cp3",
            "case_id": bundle.case.case_id,
            "correlation_id": "correlation-cp3",
            "attempt": 1,
        },
    )

    assert output["case_id"] == bundle.case.case_id
    assert len(events) == 1
    event = events[0]
    assert event["tool_name"] == "assemble_output"
    assert event["stage"] == "draft_assembly"
    assert event["agent_id"] == "policy_agent"
    assert event["attempt"] == 1
    assert event["input_hash"] and event["output_hash"]
    assert "bundle" not in event and "decision" not in event and "output" not in event


def test_assemble_output_rejects_cross_order_facts_and_traces_failure() -> None:
    bundle = bundle_for("unsupported_late_claim", 18)
    invalid = deepcopy(bundle.model_dump(mode="json"))
    invalid["payment"]["order_id"] = "e" * 32
    events: list[dict] = []

    with pytest.raises(DraftAssemblyError, match="Expected all facts for order"):
        assemble_output(
            invalid,
            decision_for(bundle),
            trace_emit=events.append,
            trace_context={"case_id": bundle.case.case_id},
        )

    assert len(events) == 1
    assert events[0]["event_type"] == "TOOL_FAILED"
    assert events[0]["error"]["code"] == "DRAFT_ORDER_ID_MISMATCH"
    assert events[0]["output_hash"] is None


def test_tv5_integration_seam_writes_sanitized_trace_event(tmp_path: Path) -> None:
    bundle = bundle_for("valid_split_payment", 19)
    decision = decision_for(bundle)
    trace_path = tmp_path / "trace.jsonl"
    trace = TraceSink(trace_path)
    policy_request = handoff(
        bundle,
        "policy_agent",
        "POLICY_REQUEST",
        bundle.model_dump(mode="json"),
    )

    output = assemble_tv5_draft(bundle, decision, policy_request, trace)

    assert verify_output(output, expected_case_id=bundle.case.case_id)["valid"] is True
    events = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]
    assert len(events) == 1
    event = events[0]
    assert event["agent"] == "policy_agent"
    assert event["event"] == "tool_completed"
    assert event["output_summary"]["tool_name"] == "assemble_output"
    assert event["output_summary"]["input_hash"]
    assert event["output_summary"]["output_hash"]
    assert "bundle" not in event["output_summary"]
