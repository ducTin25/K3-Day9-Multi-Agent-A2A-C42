"""Contract-safe stub agents for TV1 orchestration tests only."""

from __future__ import annotations

from typing import Any

from src.contracts import HandoffEnvelope


async def order_seller_stub(envelope: HandoffEnvelope) -> dict[str, Any]:
    order_id = envelope.payload["claimed_order_id"]
    return {
        "order_id": order_id,
        "order_status": "delivered",
        "items": [],
        "item_total_brl": "0.00",
        "freight_total_brl": "0.00",
        "evidence_ids": [f"order:{order_id}"],
    }


async def payment_stub(envelope: HandoffEnvelope) -> dict[str, Any]:
    order_id = envelope.payload["claimed_order_id"]
    return {
        "order_id": order_id,
        "payments": [],
        "payment_total_brl": "0.00",
        "payment_count": 0,
        "reconciliation_delta_brl": "0.00",
        "is_reconciled": True,
        "evidence_ids": [],
    }


async def delivery_stub(envelope: HandoffEnvelope) -> dict[str, Any]:
    order_id = envelope.payload["claimed_order_id"]
    return {
        "order_id": order_id,
        "is_late": False,
        "late_stage": "not_late",
        "violating_seller_ids": [],
        "evidence_ids": [f"order:{order_id}"],
    }


async def policy_stub(envelope: HandoffEnvelope) -> dict[str, Any]:
    return {
        "primary_issue": "unsupported_late_claim",
        "case_status": "no_action",
        "confidence": 1.0,
        "ranked_causes": [{"cause_code": "DELIVERY_WITHIN_ESTIMATE", "rank": 1}],
        "responsible_parties": [],
        "recommended_refund_brl": "0.00",
        "resolution_actions": ["reject_late_refund"],
        "policy_evidence_ids": ["policy:DELIVERY_WITHIN_ESTIMATE"],
    }


async def verifier_stub(envelope: HandoffEnvelope) -> dict[str, Any]:
    return {"valid": True, "repairable": False, "errors": []}


def stub_handlers() -> dict[str, Any]:
    return {
        "order_seller_agent": order_seller_stub,
        "payment_agent": payment_stub,
        "delivery_agent": delivery_stub,
        "policy_agent": policy_stub,
        "verifier_agent": verifier_stub,
    }

