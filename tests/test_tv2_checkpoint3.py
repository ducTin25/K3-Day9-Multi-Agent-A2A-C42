import asyncio
from decimal import Decimal
from pathlib import Path

import pytest

from src.agents.registry import build_hybrid_handlers
from src.contracts import HandoffEnvelope, OrderSellerFacts
from src.preflight import run_preflight
from src.tools.order_tools import build_order_repository, evidence_exists, lookup_order_seller_facts
from src.tracing import TraceSink


ROOT = Path(__file__).resolve().parents[1]


REPRESENTATIVE_CASES = {
    "EC_001": {"status": "delivered", "items": 1, "item_total": Decimal("119.90"), "freight_total": Decimal("12.04")},
    "EC_002": {"status": "delivered", "items": 2, "item_total": Decimal("163.98"), "freight_total": Decimal("16.64")},
    "EC_003": {"status": "canceled", "items": 1, "item_total": Decimal("100.00"), "freight_total": Decimal("9.34")},
    "EC_004": {"status": "delivered", "items": 1, "item_total": Decimal("179.90"), "freight_total": Decimal("32.06")},
    "EC_005": {"status": "unavailable", "items": 0, "item_total": Decimal("0.00"), "freight_total": Decimal("0.00")},
    "EC_025": {"status": "delivered", "items": 3, "item_total": Decimal("133.05"), "freight_total": Decimal("51.27")},
}


def _task(case_id: str, order_id: str) -> HandoffEnvelope:
    return HandoffEnvelope(
        run_id="run-tv2-cp3",
        case_id=case_id,
        correlation_id=f"{case_id}:tv2-cp3",
        sender="coordinator_agent",
        receiver="order_seller_agent",
        message_type="TASK_REQUEST",
        payload={"case_id": case_id, "claimed_order_id": order_id},
    )


@pytest.mark.parametrize("case_id", sorted(REPRESENTATIVE_CASES))
def test_tv2_representative_case_entities_and_evidence(case_id: str) -> None:
    cases, _ = run_preflight(ROOT)
    repository = build_order_repository(ROOT)
    expected = REPRESENTATIVE_CASES[case_id]

    facts = lookup_order_seller_facts(repository, cases[case_id].claimed_order_id)

    assert facts.order_status == expected["status"]
    assert len(facts.items) == expected["items"]
    assert facts.item_total_brl == expected["item_total"]
    assert facts.freight_total_brl == expected["freight_total"]
    assert facts.evidence_ids[0] == f"order:{facts.order_id}"
    assert len(facts.evidence_ids) == len(set(facts.evidence_ids))
    assert len(facts.evidence_ids) <= 10

    for item in facts.items:
        assert f"item:{facts.order_id}:{item.order_item_id}" in facts.evidence_ids
        assert f"seller:{item.seller_id}" in facts.evidence_ids
    if hasattr(repository, "evidence_exists"):
        for evidence_id in facts.evidence_ids:
            assert evidence_exists(repository, evidence_id) is True


def test_tv2_hybrid_registry_uses_real_order_seller_agent(tmp_path: Path) -> None:
    cases, _ = run_preflight(ROOT)
    handlers = build_hybrid_handlers(TraceSink(tmp_path / "trace.jsonl"))

    assert set(handlers) == {
        "order_seller_agent",
        "payment_agent",
        "delivery_agent",
        "policy_agent",
        "verifier_agent",
    }

    raw = asyncio.run(
        handlers["order_seller_agent"](
            _task("EC_002", cases["EC_002"].claimed_order_id)
        )
    )
    facts = OrderSellerFacts.model_validate(raw)

    assert facts.order_id == cases["EC_002"].claimed_order_id
    assert len(facts.items) == 2
    assert facts.item_total_brl == Decimal("163.98")
    assert facts.evidence_ids != [f"order:{facts.order_id}"]
