"""Model client factory for real agent adapters."""

from __future__ import annotations

import os

from langchain_openai import ChatOpenAI

from src.contracts import AgentConfig


def build_chat_model(config: AgentConfig) -> ChatOpenAI:
    """Create an OpenAI client without reading or logging the API key value."""
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is required for real OpenAI agent invocations")
    return ChatOpenAI(
        model=config.model_name,
        reasoning_effort="low",
        timeout=60,
        max_retries=1,
    )
