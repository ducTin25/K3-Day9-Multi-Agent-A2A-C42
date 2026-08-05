"""Deterministic EC_POLICY_V1 evaluation for PolicyAgent.

This module does not read CSV files, invoke models, or write outputs. It accepts
the immutable investigation bundle produced by CoordinatorAgent and returns a
structured decision that PolicyAgent can hand off for verification.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from time import perf_counter
from typing import Any, Mapping, Sequence

from .audit import TraceEmitter, emit_tool_event

MONEY_QUANTUM = Decimal("0.01")
PAYMENT_TOLERANCE = Decimal("0.10")
SUPPORTED_POLICY_VERSION = "EC_POLICY_V1"


class PolicyEvaluationError(ValueError):
    """Raised when the bundle cannot be resolved by EC_POLICY_V1."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def money(value: Any, *, field: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise PolicyEvaluationError(
            "POLICY_INVALID_MONEY", f"{field} is not a valid monetary value"
        ) from exc
    if not parsed.is_finite() or parsed < 0:
        raise PolicyEvaluationError(
            "POLICY_INVALID_MONEY", f"{field} must be finite and non-negative"
        )
    return parsed.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def _required_mapping(bundle: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = bundle.get(key)
    if not isinstance(value, Mapping):
        raise PolicyEvaluationError(
            "POLICY_BUNDLE_INVALID", f"InvestigationBundle.{key} must be an object"
        )
    return value


def _seller_parties(violations: Sequence[Any]) -> list[dict[str, str]]:
    seller_ids = sorted(
        {
            str(item.get("seller_id"))
            for item in violations
            if isinstance(item, Mapping) and item.get("seller_id")
        }
    )
    if not seller_ids:
        raise PolicyEvaluationError(
            "POLICY_SELLER_ID_MISSING",
            "Seller handoff violation must identify at least one seller",
        )
    return [{"party_type": "seller", "party_id": seller_id} for seller_id in seller_ids[:3]]


def _decision(
    *,
    primary_issue: str,
    cause_code: str,
    parties: list[dict[str, str]],
    refund: Decimal,
    action: str,
    matched_rule_rank: int,
) -> dict[str, Any]:
    return {
        "policy_version": SUPPORTED_POLICY_VERSION,
        "primary_issue": primary_issue,
        "case_status": "action_required" if refund > 0 else "no_action",
        "ranked_causes": [{"cause_code": cause_code, "rank": 1}],
        "responsible_parties": parties,
        "recommended_refund_brl": float(refund),
        "resolution_actions": [action],
        "policy_evidence_ids": [f"policy:{cause_code}"],
        "matched_rule_rank": matched_rule_rank,
    }


def _evaluate(bundle: Mapping[str, Any]) -> dict[str, Any]:
    policy_version = bundle.get("policy_version")
    if policy_version != SUPPORTED_POLICY_VERSION:
        raise PolicyEvaluationError(
            "POLICY_VERSION_UNSUPPORTED",
            f"Expected {SUPPORTED_POLICY_VERSION}, got {policy_version!r}",
        )

    order = _required_mapping(bundle, "order_seller")
    payment = _required_mapping(bundle, "payment")
    delivery = _required_mapping(bundle, "delivery")

    payment_total = money(payment.get("payment_total_brl", 0), field="payment_total_brl")
    freight_total = money(order.get("freight_total_brl", 0), field="freight_total_brl")
    order_status = str(order.get("order_status") or "").lower()

    if order_status == "canceled" and payment_total > 0:
        return _decision(
            primary_issue="canceled_order_paid",
            cause_code="ORDER_CANCELED_AFTER_PAYMENT",
            parties=[{"party_type": "platform", "party_id": "OLIST_PLATFORM"}],
            refund=payment_total,
            action="issue_full_refund",
            matched_rule_rank=1,
        )

    if order_status == "unavailable" and payment_total > 0:
        return _decision(
            primary_issue="unavailable_order_paid",
            cause_code="ORDER_UNAVAILABLE_AFTER_PAYMENT",
            parties=[{"party_type": "platform", "party_id": "OLIST_PLATFORM"}],
            refund=payment_total,
            action="issue_full_refund",
            matched_rule_rank=2,
        )

    is_late = delivery.get("is_delivered_late")
    violations = delivery.get("seller_handoff_violations") or []
    if not isinstance(violations, Sequence) or isinstance(violations, (str, bytes)):
        raise PolicyEvaluationError(
            "POLICY_BUNDLE_INVALID", "seller_handoff_violations must be an array"
        )

    if is_late is True and violations:
        return _decision(
            primary_issue="late_delivery_seller",
            cause_code="SELLER_HANDOFF_AFTER_LIMIT",
            parties=_seller_parties(violations),
            refund=freight_total,
            action="refund_freight",
            matched_rule_rank=3,
        )

    if is_late is True and not violations:
        return _decision(
            primary_issue="late_delivery_logistics",
            cause_code="CARRIER_DELIVERED_AFTER_ESTIMATE",
            parties=[
                {
                    "party_type": "logistics_provider",
                    "party_id": "LOGISTICS_PROVIDER",
                }
            ],
            refund=freight_total,
            action="refund_freight",
            matched_rule_rank=4,
        )

    try:
        payment_count = int(payment.get("payment_count", 0))
    except (TypeError, ValueError) as exc:
        raise PolicyEvaluationError(
            "POLICY_BUNDLE_INVALID", "payment_count must be an integer"
        ) from exc
    reconciled = payment.get("is_reconciled_within_0_10") is True

    if payment_count >= 2 and reconciled:
        return _decision(
            primary_issue="valid_split_payment",
            cause_code="MULTIPLE_PAYMENTS_RECONCILED",
            parties=[],
            refund=Decimal("0.00"),
            action="explain_valid_split_payment",
            matched_rule_rank=5,
        )

    if is_late is False and reconciled:
        return _decision(
            primary_issue="unsupported_late_claim",
            cause_code="DELIVERY_WITHIN_ESTIMATE",
            parties=[],
            refund=Decimal("0.00"),
            action="reject_late_refund",
            matched_rule_rank=6,
        )

    raise PolicyEvaluationError(
        "POLICY_UNRESOLVED",
        "InvestigationBundle does not match any EC_POLICY_V1 rule",
    )


def evaluate_policy(
    bundle: Mapping[str, Any],
    *,
    trace_emit: TraceEmitter | None = None,
    trace_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate EC_POLICY_V1 in strict priority order.

    The callback receives trace-compatible tool events. This function never
    writes directly to ``trace.jsonl``.
    """

    started = perf_counter()
    try:
        result = _evaluate(bundle)
    except PolicyEvaluationError as exc:
        emit_tool_event(
            trace_emit,
            context=trace_context,
            event_type="TOOL_FAILED",
            stage="policy_decision",
            agent_id="policy_agent",
            tool_name="evaluate_policy",
            status="failed",
            duration_ms=int((perf_counter() - started) * 1000),
            input_value=bundle,
            error={"code": exc.code, "message": str(exc)},
        )
        raise

    emit_tool_event(
        trace_emit,
        context=trace_context,
        event_type="TOOL_COMPLETED",
        stage="policy_decision",
        agent_id="policy_agent",
        tool_name="evaluate_policy",
        status="success",
        duration_ms=int((perf_counter() - started) * 1000),
        input_value=bundle,
        output_value=result,
    )
    return result
