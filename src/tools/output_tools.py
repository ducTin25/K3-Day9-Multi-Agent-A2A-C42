"""Deterministic final-output assembly owned by TV5.

The assembler converts frozen domain facts plus a verified policy decision into
the submission schema. It never invokes a model and never writes an output
file; Coordinator/runner remains responsible for orchestration and atomic I/O.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from time import perf_counter
from typing import Any, Iterable, Mapping

from src.contracts import InvestigationBundle, PolicyDecision

from .audit import TraceEmitter, emit_tool_event

MONEY_QUANTUM = Decimal("0.01")


class DraftAssemblyError(ValueError):
    """Raised when facts cannot be safely assembled into one case output."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _money_number(value: Decimal) -> float:
    return float(value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP))


def _unique_sorted(values: Iterable[str], *, limit: int) -> list[str]:
    return sorted({value for value in values if value})[:limit]


def _payment_ids(bundle: InvestigationBundle) -> list[str]:
    order_id = bundle.payment.order_id
    ids = {
        f"{order_id}:{row.payment_sequential}"
        for row in bundle.payment.payments
    }
    prefix = f"payment:{order_id}:"
    for evidence_id in bundle.payment.evidence_ids:
        if evidence_id.startswith(prefix):
            sequence = evidence_id[len(prefix) :]
            if sequence.isdigit() and int(sequence) > 0:
                ids.add(f"{order_id}:{int(sequence)}")
    return sorted(ids, key=lambda value: int(value.rsplit(":", 1)[1]))[:5]


def _evidence_ids(
    bundle: InvestigationBundle, decision: PolicyDecision
) -> list[str]:
    # Policy evidence is mandatory for auditability, so reserve its slots first.
    policy = _unique_sorted(decision.policy_evidence_ids, limit=3)
    domain = _unique_sorted(
        (
            *bundle.order_seller.evidence_ids,
            *bundle.payment.evidence_ids,
            *bundle.delivery.evidence_ids,
        ),
        limit=10,
    )
    return (policy + [item for item in domain if item not in policy])[:10]


def _validate_order_identity(bundle: InvestigationBundle) -> None:
    expected = bundle.case.claimed_order_id
    actual = {
        "order_seller.order_id": bundle.order_seller.order_id,
        "payment.order_id": bundle.payment.order_id,
        "delivery.order_id": bundle.delivery.order_id,
    }
    mismatches = {path: value for path, value in actual.items() if value != expected}
    if mismatches:
        detail = ", ".join(f"{path}={value}" for path, value in sorted(mismatches.items()))
        raise DraftAssemblyError(
            "DRAFT_ORDER_ID_MISMATCH",
            f"Expected all facts for order {expected}; got {detail}",
        )


def _assemble(
    bundle: InvestigationBundle, decision: PolicyDecision
) -> dict[str, Any]:
    _validate_order_identity(bundle)
    order_id = bundle.order_seller.order_id
    items = sorted(bundle.order_seller.items, key=lambda item: item.order_item_id)
    return {
        "case_id": bundle.case.case_id,
        "assessment": {
            "primary_issue": decision.primary_issue,
            "case_status": decision.case_status,
            "confidence": decision.confidence,
        },
        "affected_entities": {
            "order_ids": [order_id],
            "item_ids": [f"{order_id}:{item.order_item_id}" for item in items[:5]],
            "seller_ids": _unique_sorted(
                (item.seller_id for item in items), limit=5
            ),
            "payment_ids": _payment_ids(bundle),
        },
        "root_cause_analysis": {
            "ranked_causes": [
                cause.model_dump(mode="json") for cause in decision.ranked_causes
            ],
            "responsible_parties": [
                party.model_dump(mode="json")
                for party in decision.responsible_parties
            ],
        },
        "evidence_ids": _evidence_ids(bundle, decision),
        "financial_resolution": {
            "currency": "BRL",
            "item_total_brl": _money_number(bundle.order_seller.item_total_brl),
            "freight_total_brl": _money_number(bundle.order_seller.freight_total_brl),
            "payment_total_brl": _money_number(bundle.payment.payment_total_brl),
            "recommended_refund_brl": _money_number(
                decision.recommended_refund_brl
            ),
        },
        "resolution_actions": list(decision.resolution_actions),
    }


def assemble_output(
    bundle: InvestigationBundle | Mapping[str, Any],
    decision: PolicyDecision | Mapping[str, Any],
    *,
    trace_emit: TraceEmitter | None = None,
    trace_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build one schema-shaped draft and emit hashes, never raw data or secrets."""

    started = perf_counter()
    try:
        validated_bundle = InvestigationBundle.model_validate(bundle)
        validated_decision = PolicyDecision.model_validate(decision)
        output = _assemble(validated_bundle, validated_decision)
    except Exception as exc:
        code = getattr(exc, "code", "DRAFT_CONTRACT_INVALID")
        emit_tool_event(
            trace_emit,
            context=trace_context,
            event_type="TOOL_FAILED",
            stage="draft_assembly",
            agent_id="policy_agent",
            tool_name="assemble_output",
            status="failed",
            duration_ms=int((perf_counter() - started) * 1000),
            input_value={"bundle": bundle, "decision": decision},
            error={"code": code, "message": str(exc)},
        )
        raise

    emit_tool_event(
        trace_emit,
        context=trace_context,
        event_type="TOOL_COMPLETED",
        stage="draft_assembly",
        agent_id="policy_agent",
        tool_name="assemble_output",
        status="success",
        duration_ms=int((perf_counter() - started) * 1000),
        input_value={"bundle": validated_bundle, "decision": validated_decision},
        output_value=output,
    )
    return output

