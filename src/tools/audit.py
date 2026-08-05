"""Trace-compatible helpers for deterministic tools.

Tools emit event dictionaries through a callback. They never write trace files
directly; the runtime owned by TV1 remains the only trace writer.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Callable, Mapping
from uuid import uuid4

TraceEmitter = Callable[[dict[str, Any]], None]


def stable_hash(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def emit_tool_event(
    emitter: TraceEmitter | None,
    *,
    context: Mapping[str, Any] | None,
    event_type: str,
    stage: str,
    agent_id: str,
    tool_name: str,
    status: str,
    duration_ms: int,
    input_value: Any | None = None,
    output_value: Any | None = None,
    error: Mapping[str, Any] | None = None,
) -> None:
    if emitter is None:
        return

    trace_context = dict(context or {})
    event = {
        "schema_version": "1.0",
        "run_id": trace_context.get("run_id"),
        "event_id": str(uuid4()),
        "parent_event_id": trace_context.get("parent_event_id"),
        "case_id": trace_context.get("case_id"),
        "correlation_id": trace_context.get("correlation_id"),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_type": event_type,
        "stage": stage,
        "agent_id": agent_id,
        "attempt": int(trace_context.get("attempt", 0)),
        "tool_name": tool_name,
        "input_hash": stable_hash(input_value) if input_value is not None else None,
        "output_hash": stable_hash(output_value) if output_value is not None else None,
        "status": status,
        "duration_ms": max(0, int(duration_ms)),
        "error": dict(error) if error else None,
    }
    emitter(event)
