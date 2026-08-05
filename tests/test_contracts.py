from pathlib import Path

import pytest
from pydantic import ValidationError

from src.config import load_runtime_config
from src.contracts import DeliveryFacts, PaymentFacts, PolicyDecision
from src.tools.delivery_tools import compare_delivery_timestamps
from src.tools.policy_tools import evaluate_policy


ROOT = Path(__file__).resolve().parents[1]


def test_agent_config_has_six_models_within_limit() -> None:
    config = load_runtime_config(ROOT / "src" / "config" / "agents.yaml")
    assert len(config.agents) == 6
    assert all(agent.model_name == "o4-mini" for agent in config.agents)
    assert all(agent.parameter_count is None for agent in config.agents)
    assert all(agent.parameter_count_upper_bound == 10_000_000_000 for agent in config.agents)
    assert all(agent.parameter_count_source == "user_attested" for agent in config.agents)


def test_model_guard_rejects_model_over_10b(tmp_path: Path) -> None:
    config_text = (ROOT / "src" / "config" / "agents.yaml").read_text(encoding="utf-8")
    config_text = config_text.replace("10000000000", "11000000000", 1)
    path = tmp_path / "agents.yaml"
    path.write_text(config_text, encoding="utf-8")
    with pytest.raises(ValidationError):
        load_runtime_config(path)


def test_tv4_delivery_output_matches_tv1_contract() -> None:
    order_id = "a" * 32
    result = compare_delivery_timestamps(
        order_id,
        {
            "delivered_customer_at": "2018-05-20 14:00:00",
            "estimated_delivery_at": "2018-05-15 00:00:00",
            "delivered_carrier_at": "2018-05-10 10:00:00",
        },
        [
            {
                "order_item_id": 1,
                "seller_id": "seller_xyz",
                "shipping_limit_date": "2018-05-07 00:00:00",
            }
        ],
    )
    facts = DeliveryFacts.model_validate(result)
    assert facts.is_delivered_late is True
    assert facts.seller_handoff_violations[0].seller_id == "seller_xyz"


def test_tv3_payment_field_and_tv5_policy_output_match_tv1_contract() -> None:
    payment = PaymentFacts.model_validate(
        {
            "order_id": "a" * 32,
            "payments": [],
            "payment_total_brl": "115.00",
            "payment_count": 2,
            "reconciliation_delta_brl": "0.00",
            "is_reconciled_within_0_10": True,
            "evidence_ids": [],
        }
    )
    raw_decision = evaluate_policy(
        {
            "policy_version": "EC_POLICY_V1",
            "order_seller": {"order_status": "canceled", "freight_total_brl": "15.00"},
            "payment": payment.model_dump(mode="json"),
            "delivery": {"is_delivered_late": True, "seller_handoff_violations": []},
        }
    )
    decision = PolicyDecision.model_validate(raw_decision)
    assert decision.primary_issue == "canceled_order_paid"
    assert decision.policy_version == "EC_POLICY_V1"
