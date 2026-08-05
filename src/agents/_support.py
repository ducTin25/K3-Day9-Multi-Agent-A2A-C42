"""Shared adapters for TV5 agents without adding domain logic to runtime."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Protocol, Sequence

from langchain_core.messages import BaseMessage

from src.contracts import HandoffEnvelope, TraceEvent
from src.tracing import TraceSink


class StructuredInvoker(Protocol):
    async def ainvoke(self, messages: Sequence[BaseMessage]) -> Any: ...


def load_prompt(path: Path) -> str:
    prompt = path.read_text(encoding="utf-8").strip()
    if not prompt:
        raise ValueError(f"prompt is empty: {path}")
    return prompt


def require_tools(actual: list[str], required: set[str], *, agent_id: str) -> None:
    missing = required - set(actual)
    if missing:
        raise ValueError(f"{agent_id} is missing required tools: {sorted(missing)}")


def tool_trace_emitter(
    trace: TraceSink | None, envelope: HandoffEnvelope
) -> Callable[[dict[str, Any]], None] | None:
    """Bridge TV5 tool audit dictionaries into TV1's TraceEvent contract."""

    if trace is None:
        return None

    def emit(audit: dict[str, Any]) -> None:
        raw_status = str(audit.get("status", "success"))
        status = "failed" if raw_status == "failed" else "succeeded"
        error = audit.get("error")
        trace.emit(
            TraceEvent(
                run_id=envelope.run_id,
                case_id=envelope.case_id,
                correlation_id=envelope.correlation_id,
                agent=str(audit.get("agent_id") or envelope.receiver),
                event=str(audit.get("event_type", "TOOL_COMPLETED")).lower(),
                timestamp=datetime.now(timezone.utc),
                sender=envelope.receiver,
                receiver=envelope.receiver,
                attempt=envelope.attempt,
                duration_ms=int(audit.get("duration_ms", 0)),
                status=status,
                evidence_ids=envelope.evidence_ids,
                output_summary={
                    "stage": audit.get("stage"),
                    "tool_name": audit.get("tool_name"),
                    "input_hash": audit.get("input_hash"),
                    "output_hash": audit.get("output_hash"),
                    "tool_status": raw_status,
                },
                error=json.dumps(error, ensure_ascii=False, default=str) if error else None,
            )
        )

    return emit
