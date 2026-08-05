import asyncio
from decimal import Decimal
from pathlib import Path

import pytest

from src.agents.order_seller import OrderSellerAgent, order_seller_agent_handler
from src.config import load_runtime_config
from src.contracts import HandoffEnvelope, OrderSellerFacts
from src.tools.order_tools import build_order_repository


ROOT = Path(__file__).resolve().parents[1]


def _envelope(case_id: str, order_id: str) -> HandoffEnvelope:
    return HandoffEnvelope(
        run_id="run_test_order_seller_cp2",
        case_id=case_id,
        correlation_id=f"{case_id}:order_seller:attempt-0",
        sender="coordinator_agent",
        receiver="order_seller_agent",
        message_type="TASK_REQUEST",
        payload={"case_id": case_id, "claimed_order_id": order_id},
    )


def _config():
    return next(
        agent
        for agent in load_runtime_config(ROOT / "src" / "config" / "agents.yaml").agents
        if agent.agent_id == "order_seller_agent"
    )


def test_order_seller_agent_tool_allowlist_blocks_payment_and_refund_tools() -> None:
    agent = OrderSellerAgent(config=_config())

    agent.validate_tool_access("lookup_order_seller_facts")

    with pytest.raises(PermissionError):
        agent.validate_tool_access("lookup_payments")
    with pytest.raises(PermissionError):
        agent.validate_tool_access("issue_full_refund")


def test_order_seller_agent_returns_multi_item_contract_output() -> None:
    repository = build_order_repository(ROOT)
    envelope = _envelope("EC_002", "8067c5e4834f3c0a3c8a4e921d65c5b1")

    result = asyncio.run(
        order_seller_agent_handler(envelope, repository=repository, config=_config())
    )
    facts = OrderSellerFacts.model_validate(result)

    assert facts.order_id == "8067c5e4834f3c0a3c8a4e921d65c5b1"
    assert facts.order_status == "delivered"
    assert len(facts.items) == 2
    assert facts.item_total_brl == Decimal("163.98")
    assert facts.freight_total_brl == Decimal("16.64")
    assert "payment:" not in " ".join(facts.evidence_ids)


def test_order_seller_agent_handles_no_item_order() -> None:
    repository = build_order_repository(ROOT)
    envelope = _envelope("EC_005", "9a31fd9d697e9670777501f720773fd9")

    result = asyncio.run(
        order_seller_agent_handler(envelope, repository=repository, config=_config())
    )
    facts = OrderSellerFacts.model_validate(result)

    assert facts.order_status == "unavailable"
    assert facts.items == []
    assert facts.item_total_brl == Decimal("0.00")
    assert facts.freight_total_brl == Decimal("0.00")
    assert facts.evidence_ids == ["order:9a31fd9d697e9670777501f720773fd9"]


def test_order_seller_agent_rejects_wrong_envelope_target() -> None:
    agent = OrderSellerAgent(config=_config())
    envelope = HandoffEnvelope(
        run_id="run_test_order_seller_cp2",
        case_id="EC_001",
        correlation_id="EC_001:wrong-target",
        sender="coordinator_agent",
        receiver="payment_agent",
        message_type="TASK_REQUEST",
        payload={"claimed_order_id": "e2a03ccf5ea816036608b2d8c3ab8e60"},
    )

    with pytest.raises(ValueError, match="TASK_REQUEST addressed to order_seller_agent"):
        asyncio.run(agent.process_task(envelope))

