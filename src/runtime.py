"""Agent runtime services owned by TV1."""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from src.contracts import HandoffEnvelope, TraceEvent
from src.tracing import TraceSink


AgentHandler = Callable[[HandoffEnvelope], Awaitable[dict[str, Any]]]


class AgentRuntime:
    def __init__(self, trace: TraceSink, handlers: dict[str, AgentHandler], timeout_seconds: float = 30.0) -> None:
        self.trace = trace
        self.handlers = handlers
        self.timeout_seconds = timeout_seconds

    async def invoke(self, envelope: HandoffEnvelope) -> dict[str, Any]:
        if envelope.receiver not in self.handlers:
            raise KeyError(f"no handler registered for {envelope.receiver}")
        started = time.perf_counter()
        self._trace(envelope, "invocation_started", "started")
        try:
            result = await asyncio.wait_for(
                self.handlers[envelope.receiver](envelope), timeout=self.timeout_seconds
            )
        except Exception as exc:
            duration = int((time.perf_counter() - started) * 1000)
            self._trace(envelope, "invocation_failed", "failed", duration, error=str(exc))
            raise
        duration = int((time.perf_counter() - started) * 1000)
        self._trace(envelope, "invocation_succeeded", "succeeded", duration, summary=result)
        return result

    def _trace(
        self,
        envelope: HandoffEnvelope,
        event: str,
        status: str,
        duration_ms: int = 0,
        *,
        summary: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        self.trace.emit(
            TraceEvent(
                run_id=envelope.run_id,
                case_id=envelope.case_id,
                correlation_id=envelope.correlation_id,
                agent=envelope.receiver,
                event=event,
                timestamp=datetime.now(timezone.utc),
                sender=envelope.sender,
                receiver=envelope.receiver,
                attempt=envelope.attempt,
                duration_ms=duration_ms,
                status=status,
                evidence_ids=envelope.evidence_ids,
                output_summary=summary or {},
                error=error,
            )
        )

