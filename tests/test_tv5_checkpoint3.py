from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from langchain_core.messages import HumanMessage

from src.agents.policy import PolicyAgent
from src.agents.verifier import VerifierAgent
from src.config import load_runtime_config
from src.contracts import (
    CaseInput,
    DeliveryFacts,
    HandoffEnvelope,
    InvestigationBundle,
    ItemFact,
    OrderSellerFacts,
    PaymentFacts,
    PolicyDecision,
    VerifyResult,
)
from src.runtime import AgentRuntime
from src.tools.output_tools import assemble_output
from src.tracing import TraceSink

ORDER_ID = "c" * 32
SELLER_ID = "d" * 32


class EchoAuthoritativeToolResult:
    """Fake structured model that preserves the real agent invocation boundary."""

    def __init__(self, key: str) -> None:
        self.key = key
        self.calls: list[Any] = []

    async def ainvoke(self, messages: Any) -> Any:
        self.calls.append(messages)
        human = next(message for message in reversed(messages) if isinstance(message, HumanMessage))
        return json.loads(str(human.content))[self.key]


def agent_config(agent_id: str):
    return next(item for item in load_runtime_config().agents if item.agent_id == agent_id)


def bundle_for(
    issue: str,
    case_number: int,
) -> InvestigationBundle:
    status = {
        "canceled_order_paid": "canceled",
        "unavailable_order_paid": "unavailable",
    }.get(issue, "delivered")
    is_late = issue in {"late_delivery_seller", "late_delivery_logistics"}
    violating = [SELLER_ID] if issue == "late_delivery_seller" else []
    late_stage = (
        "seller"
        if issue == "late_delivery_seller"
        else "logistics"
        if issue == "late_delivery_logistics"
        else "not_late"
    )
    payment_count = 2 if issue == "valid_split_payment" else 1
    case = CaseInput(
        case_id=f"EC_{case_number:03d}",
        opened_at=datetime(2018, 10, 18, tzinfo=timezone.utc),
        claimed_order_id=ORDER_ID,
        policy_version="EC_POLICY_V1",
        message="Representative integration case",
    )
    order = OrderSellerFacts(
        order_id=ORDER_ID,
        order_status=status,
        items=[
            ItemFact(
                order_item_id=1,
                seller_id=SELLER_ID,
                price_brl=Decimal("100.00"),
                freight_brl=Decimal("15.00"),
            )
        ],
        item_total_brl=Decimal("100.00"),
        freight_total_brl=Decimal("15.00"),
        evidence_ids=[f"order:{ORDER_ID}", f"item:{ORDER_ID}:1", f"seller:{SELLER_ID}"],
    )
    payment = PaymentFacts(
        order_id=ORDER_ID,
        payments=[],
        payment_total_brl=Decimal("115.00"),
        payment_count=payment_count,
        reconciliation_delta_brl=Decimal("0.00"),
        is_reconciled=True,
        evidence_ids=[f"payment:{ORDER_ID}:1"],
    )
    delivery = DeliveryFacts(
        order_id=ORDER_ID,
        is_late=is_late,
        late_stage=late_stage,
        violating_seller_ids=violating,
        evidence_ids=[f"order:{ORDER_ID}", f"item:{ORDER_ID}:1"],
    )
    return InvestigationBundle(case=case, order_seller=order, payment=payment, delivery=delivery)


def handoff(
    bundle: InvestigationBundle,
    receiver: str,
    message_type: str,
    payload: dict[str, Any],
    *,
    attempt: int = 0,
) -> HandoffEnvelope:
    return HandoffEnvelope(
        run_id="run-tv5-cp3",
        case_id=bundle.case.case_id,
        correlation_id=f"{bundle.case.case_id}:cp3",
        sender="coordinator_agent",
        receiver=receiver,
        message_type=message_type,
        attempt=attempt,
        payload=payload,
    )


def runtime_with_tv5_agents(trace_path: Path) -> tuple[AgentRuntime, EchoAuthoritativeToolResult, EchoAuthoritativeToolResult]:
    trace = TraceSink(trace_path)
    policy_model = EchoAuthoritativeToolResult("authoritative_policy_tool_result")
    verifier_model = EchoAuthoritativeToolResult("authoritative_verification_tool_result")
    policy = PolicyAgent(policy_model, agent_config("policy_agent"), trace=trace)
    verifier = VerifierAgent(verifier_model, agent_config("verifier_agent"), trace=trace)
    return (
        AgentRuntime(trace, {"policy_agent": policy, "verifier_agent": verifier}),
        policy_model,
        verifier_model,
    )


ISSUES = [
    "canceled_order_paid",
    "unavailable_order_paid",
    "late_delivery_seller",
    "late_delivery_logistics",
    "valid_split_payment",
    "unsupported_late_claim",
]


@pytest.mark.parametrize(("issue", "case_number"), list(zip(ISSUES, range(1, 7))))
def test_six_representative_branches_policy_to_verifier(
    tmp_path: Path, issue: str, case_number: int
) -> None:
    bundle = bundle_for(issue, case_number)
    runtime, _, _ = runtime_with_tv5_agents(tmp_path / f"{issue}.jsonl")
    decision_raw = asyncio.run(
        runtime.invoke(
            handoff(
                bundle,
                "policy_agent",
                "POLICY_REQUEST",
                bundle.model_dump(mode="json"),
            )
        )
    )
    decision = PolicyDecision.model_validate(decision_raw)
    result_raw = asyncio.run(
        runtime.invoke(
            handoff(
                bundle,
                "verifier_agent",
                "VERIFY_REQUEST",
                {
                    "bundle": bundle.model_dump(mode="json"),
                    "decision": decision.model_dump(mode="json"),
                    "draft_output": assemble_output(bundle, decision),
                },
            )
        )
    )
    result = VerifyResult.model_validate(result_raw)
    assert decision.primary_issue == issue
    assert result.valid is True
    assert result.errors == []


def test_policy_repair_reruns_only_policy_and_verifier(tmp_path: Path) -> None:
    bundle = bundle_for("late_delivery_seller", 7)
    runtime, _, _ = runtime_with_tv5_agents(tmp_path / "policy-repair.jsonl")
    wrong = PolicyDecision(
        primary_issue="unsupported_late_claim",
        case_status="no_action",
        confidence=1.0,
        ranked_causes=[{"cause_code": "DELIVERY_WITHIN_ESTIMATE", "rank": 1}],
        responsible_parties=[],
        recommended_refund_brl=Decimal("0.00"),
        resolution_actions=["reject_late_refund"],
        policy_evidence_ids=["policy:DELIVERY_WITHIN_ESTIMATE"],
    )
    rejected = VerifyResult.model_validate(
        asyncio.run(
            runtime.invoke(
                handoff(
                    bundle,
                    "verifier_agent",
                    "VERIFY_REQUEST",
                    {
                        "bundle": bundle.model_dump(mode="json"),
                        "decision": wrong.model_dump(mode="json"),
                    },
                )
            )
        )
    )
    assert rejected.valid is False
    assert {error.repair_target for error in rejected.errors} == {"policy_agent"}

    repaired_decision = PolicyDecision.model_validate(
        asyncio.run(
            runtime.invoke(
                handoff(
                    bundle,
                    "policy_agent",
                    "POLICY_REQUEST",
                    bundle.model_dump(mode="json"),
                    attempt=1,
                )
            )
        )
    )
    accepted = VerifyResult.model_validate(
        asyncio.run(
            runtime.invoke(
                handoff(
                    bundle,
                    "verifier_agent",
                    "VERIFY_REQUEST",
                    {
                        "bundle": bundle.model_dump(mode="json"),
                        "decision": repaired_decision.model_dump(mode="json"),
                        "draft_output": assemble_output(bundle, repaired_decision),
                    },
                    attempt=1,
                )
            )
        )
    )
    assert accepted.valid is True

    events = [
        json.loads(line)
        for line in (tmp_path / "policy-repair.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert {event["agent"] for event in events} <= {"policy_agent", "verifier_agent"}
    assert any(event["agent"] == "policy_agent" and event["attempt"] == 1 for event in events)
    assert any(event["agent"] == "verifier_agent" and event["attempt"] == 1 for event in events)


def test_payment_repair_is_targeted_and_reverified(tmp_path: Path) -> None:
    bundle = bundle_for("valid_split_payment", 8)
    runtime, _, _ = runtime_with_tv5_agents(tmp_path / "payment-repair.jsonl")
    decision = PolicyDecision.model_validate(
        asyncio.run(
            runtime.invoke(
                handoff(
                    bundle,
                    "policy_agent",
                    "POLICY_REQUEST",
                    bundle.model_dump(mode="json"),
                )
            )
        )
    )
    invalid_draft = assemble_output(bundle, decision)
    invalid_draft["financial_resolution"]["payment_total_brl"] = 150.0
    rejected = VerifyResult.model_validate(
        asyncio.run(
            runtime.invoke(
                handoff(
                    bundle,
                    "verifier_agent",
                    "VERIFY_REQUEST",
                    {
                        "bundle": bundle.model_dump(mode="json"),
                        "decision": decision.model_dump(mode="json"),
                        "draft_output": invalid_draft,
                    },
                )
            )
        )
    )
    assert rejected.valid is False
    assert any(error.code == "FINANCIAL_TOTAL_MISMATCH" for error in rejected.errors)
    assert {error.repair_target for error in rejected.errors} == {"payment_agent"}

    corrected_draft = assemble_output(bundle, decision)
    accepted = VerifyResult.model_validate(
        asyncio.run(
            runtime.invoke(
                handoff(
                    bundle,
                    "verifier_agent",
                    "VERIFY_REQUEST",
                    {
                        "bundle": bundle.model_dump(mode="json"),
                        "decision": decision.model_dump(mode="json"),
                        "draft_output": corrected_draft,
                    },
                    attempt=1,
                )
            )
        )
    )
    assert accepted.valid is True
    events = [
        json.loads(line)
        for line in (tmp_path / "payment-repair.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert not any(event["agent"] in {"order_seller_agent", "delivery_agent"} for event in events)
    assert any(event["agent"] == "verifier_agent" and event["attempt"] == 1 for event in events)
