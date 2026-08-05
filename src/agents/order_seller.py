"""OrderSellerAgent implementation for TV2 Checkpoint 2."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.agents._support import load_prompt, require_tools
from src.contracts import AgentConfig, HandoffEnvelope, OrderSellerFacts
from src.data.olist_repository import OlistRepository, ProcessedOlistRepository
from src.tools.order_tools import build_order_repository, lookup_order_seller_facts


ROOT = Path(__file__).resolve().parents[2]
PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "order_seller_v1.txt"

ORDER_SELLER_AGENT_CONFIG = {
    "agent_id": "order_seller_agent",
    "role": "order_seller",
    "prompt_version": "order-seller-v1",
    "allowed_tools": [
        "lookup_order_seller_facts",
        "list_case_order_ids",
        "evidence_exists",
    ],
    "input_schema": "CaseInput",
    "output_schema": "OrderSellerFacts",
}


class OrderSellerAgent:
    """Order and seller domain agent with a strict tool boundary."""

    REQUIRED_TOOLS = {"lookup_order_seller_facts"}

    def __init__(
        self,
        repository: OlistRepository | ProcessedOlistRepository | None = None,
        *,
        root: Path = ROOT,
        config: AgentConfig | None = None,
        prompt_path: Path = PROMPT_PATH,
    ) -> None:
        self.config = config
        allowed_tools = (
            config.allowed_tools if config is not None else ORDER_SELLER_AGENT_CONFIG["allowed_tools"]
        )
        agent_id = config.agent_id if config is not None else "order_seller_agent"
        if agent_id != "order_seller_agent":
            raise ValueError("OrderSellerAgent requires order_seller_agent config")
        require_tools(allowed_tools, self.REQUIRED_TOOLS, agent_id=agent_id)
        self.allowed_tools = set(allowed_tools)
        self.repository = repository if repository is not None else build_order_repository(root)
        self.system_prompt = load_prompt(prompt_path)

    def validate_tool_access(self, tool_name: str) -> None:
        if tool_name not in self.allowed_tools:
            raise PermissionError(
                f"OrderSellerAgent is not authorized to execute tool '{tool_name}'."
            )

    async def process_task(self, envelope: HandoffEnvelope) -> dict[str, Any]:
        if envelope.receiver != "order_seller_agent" or envelope.message_type != "TASK_REQUEST":
            raise ValueError("OrderSellerAgent only accepts TASK_REQUEST addressed to order_seller_agent")

        order_id = envelope.payload.get("claimed_order_id") or envelope.payload.get("order_id")
        if not order_id:
            raise ValueError("Task payload must contain 'claimed_order_id' or 'order_id'")

        self.validate_tool_access("lookup_order_seller_facts")
        facts = OrderSellerFacts.model_validate(
            lookup_order_seller_facts(self.repository, str(order_id))
        )
        return facts.model_dump(mode="json")


async def order_seller_agent_handler(
    envelope: HandoffEnvelope,
    *,
    repository: OlistRepository | ProcessedOlistRepository | None = None,
    root: Path = ROOT,
    config: AgentConfig | None = None,
) -> dict[str, Any]:
    agent = OrderSellerAgent(repository=repository, root=root, config=config)
    return await agent.process_task(envelope)

