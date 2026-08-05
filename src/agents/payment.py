"""Payment Agent implementation (Member 3 / TV3 - Checkpoint 2)."""

from __future__ import annotations

from typing import Any

from src.contracts import HandoffEnvelope, PaymentFacts
from src.tools.payment_tools import (
    get_order_financial_reference,
    get_order_payments,
    reconcile_payments,
)

# Agent metadata and tool allowlist declaration
PAYMENT_AGENT_CONFIG = {
    "agent_id": "payment_agent",
    "role": "payment_investigator",
    "prompt_version": "payment-v1",
    "allowed_tools": [
        "get_order_payments",
        "get_order_financial_reference",
        "reconcile_payments",
    ],
    "input_schema": "CaseInput@1",
    "output_schema": "PaymentFacts@1",
}

PAYMENT_SYSTEM_PROMPT = """You are the PaymentAgent in an e-commerce dispute resolution multi-agent system.
Your sole responsibility is to retrieve payment rows for an order and reconcile them against
the order's item + freight total.

Rules:
1. You may ONLY call tools in your allowed_tools list:
   - get_order_payments
   - get_order_financial_reference
   - reconcile_payments
2. payment_value_brl is the full amount of a payment row, never multiply it by
   payment_installments to derive a total.
3. All money math uses Decimal, rounded to 2 decimal places only after summing.
4. reconciliation is within tolerance when |payment_total_brl - reference_order_total_brl| <= 0.10 BRL.
5. Do not determine delivery lateness, seller responsibility, or refund/action decisions.
6. Every payment evidence ID you emit must follow payment:<order_id>:<payment_sequential>
   and be built only from payment rows that were actually retrieved.
"""


class PaymentAgent:
    """Payment Agent that processes TASK_REQUEST envelopes and returns PaymentFacts."""

    def __init__(self, data_dir: str | None = None, repository: Any = None) -> None:
        self.config = PAYMENT_AGENT_CONFIG
        self.system_prompt = PAYMENT_SYSTEM_PROMPT
        self.data_dir = data_dir
        self.repository = repository

    def validate_tool_access(self, tool_name: str) -> None:
        """Enforce tool allowlist security guard."""
        if tool_name not in self.config["allowed_tools"]:
            raise PermissionError(
                f"PaymentAgent is not authorized to execute tool '{tool_name}'."
            )

    async def process_task(self, envelope: HandoffEnvelope) -> dict[str, Any]:
        """Process incoming TASK_REQUEST envelope and return PaymentFacts payload dict."""
        order_id = envelope.payload.get("claimed_order_id") or envelope.payload.get("order_id")
        if not order_id:
            raise ValueError("Task payload must contain 'claimed_order_id' or 'order_id'")

        # 1. Execute allowed tools
        self.validate_tool_access("get_order_payments")
        payment_rows = get_order_payments(order_id, data_dir=self.data_dir, repository=self.repository)

        self.validate_tool_access("get_order_financial_reference")
        reference = get_order_financial_reference(order_id, data_dir=self.data_dir, repository=self.repository)

        self.validate_tool_access("reconcile_payments")
        raw_facts = reconcile_payments(order_id, payment_rows, reference["reference_order_total_brl"])

        # 2. Format PaymentFacts Pydantic model (payments/evidence already sorted by
        # payment_sequential inside reconcile_payments)
        facts = PaymentFacts(
            order_id=order_id,
            payments=raw_facts["payments"],
            payment_total_brl=raw_facts["payment_total_brl"],
            payment_count=raw_facts["payment_count"],
            reconciliation_delta_brl=raw_facts["reconciliation_delta_brl"],
            is_reconciled=raw_facts["is_reconciled"],
            evidence_ids=raw_facts["evidence_ids"][:10],
        )

        return facts.model_dump(mode="json")


async def payment_agent_handler(
    envelope: HandoffEnvelope, data_dir: str | None = None, repository: Any = None
) -> dict[str, Any]:
    """Handler function compatible with AgentRuntime."""
    agent = PaymentAgent(data_dir=data_dir, repository=repository)
    return await agent.process_task(envelope)
