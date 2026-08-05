"""Delivery Agent implementation (Member 4 / TV4 - Checkpoint 2)."""

from __future__ import annotations

from typing import Any
from src.contracts import DeliveryFacts, HandoffEnvelope
from src.tools.delivery_tools import (
    compare_delivery_timestamps,
    get_delivery_timeline,
    get_shipping_limits,
)

# Agent metadata and tool allowlist declaration
DELIVERY_AGENT_CONFIG = {
    "agent_id": "delivery_agent",
    "role": "delivery_investigator",
    "prompt_version": "delivery-v1",
    "allowed_tools": [
        "get_delivery_timeline",
        "get_shipping_limits",
        "compare_delivery_timestamps",
    ],
    "input_schema": "DeliveryTask@1",
    "output_schema": "DeliveryFacts@1",
}

DELIVERY_SYSTEM_PROMPT = """You are the DeliveryAgent in an e-commerce dispute resolution multi-agent system.
Your sole responsibility is to investigate order delivery timestamps and seller handoff compliance.

Rules:
1. You may ONLY call tools in your allowed_tools list:
   - get_delivery_timeline
   - get_shipping_limits
   - compare_delivery_timestamps
2. Do not attempt financial reconciliation, payment calculations, or refund determinations.
3. Classify delivery status objectively based on actual timestamps:
   - 'not_late' if delivered_customer_at <= estimated_delivery_at
   - 'seller' if delivered_customer_at > estimated_delivery_at and carrier handoff > shipping_limit_date
   - 'logistics' if delivered_customer_at > estimated_delivery_at and carrier handoff <= shipping_limit_date
   - 'undetermined' if timestamps are missing
"""


class DeliveryAgent:
    """Delivery Agent that processes TASK_REQUEST envelopes and returns DeliveryFacts."""

    def __init__(self, data_dir: str | None = None, repository: Any = None) -> None:
        self.config = DELIVERY_AGENT_CONFIG
        self.system_prompt = DELIVERY_SYSTEM_PROMPT
        self.data_dir = data_dir
        self.repository = repository

    def validate_tool_access(self, tool_name: str) -> None:
        """Enforce tool allowlist security guard."""
        if tool_name not in self.config["allowed_tools"]:
            raise PermissionError(
                f"DeliveryAgent is not authorized to execute tool '{tool_name}'."
            )

    async def process_task(self, envelope: HandoffEnvelope) -> dict[str, Any]:
        """Process incoming TASK_REQUEST envelope and return DeliveryFacts payload dict."""
        order_id = envelope.payload.get("claimed_order_id") or envelope.payload.get("order_id")
        if not order_id:
            raise ValueError("Task payload must contain 'claimed_order_id' or 'order_id'")

        # 1. Execute allowed tools
        self.validate_tool_access("get_delivery_timeline")
        timeline = get_delivery_timeline(order_id, data_dir=self.data_dir, repository=self.repository)

        self.validate_tool_access("get_shipping_limits")
        limits = get_shipping_limits(order_id, data_dir=self.data_dir, repository=self.repository)

        self.validate_tool_access("compare_delivery_timestamps")
        raw_facts = compare_delivery_timestamps(order_id, timeline, limits)

        # 2. Extract violating seller IDs
        violating_seller_ids = list(
            {v["seller_id"] for v in raw_facts.get("seller_handoff_violations", []) if v.get("seller_id")}
        )

        # 3. Format DeliveryFacts Pydantic model
        facts = DeliveryFacts(
            order_id=order_id,
            is_late=raw_facts["is_delivered_late"],
            late_stage=raw_facts["late_stage"],
            violating_seller_ids=violating_seller_ids[:5],
            delivered_carrier_at=raw_facts["delivered_carrier_at"],
            delivered_customer_at=raw_facts["delivered_customer_at"],
            estimated_delivery_at=raw_facts["estimated_delivery_at"],
            evidence_ids=raw_facts["evidence_ids"][:10],
        )

        return facts.model_dump(mode="json")


async def delivery_agent_handler(envelope: HandoffEnvelope, data_dir: str | None = None, repository: Any = None) -> dict[str, Any]:
    """Handler function compatible with AgentRuntime."""
    agent = DeliveryAgent(data_dir=data_dir, repository=repository)
    return await agent.process_task(envelope)
