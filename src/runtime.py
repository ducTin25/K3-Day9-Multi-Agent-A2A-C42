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
    def __init__(
        self,
        trace: TraceSink,
        handlers: dict[str, AgentHandler],
        timeout_seconds: float = 30.0,
        max_retries: int = 1,
    ) -> None:
        if max_retries not in (0, 1):
            raise ValueError("max_retries must be 0 or 1 for the CP2 runtime")
        self.trace = trace
        self.handlers = handlers
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries

    async def invoke(self, envelope: HandoffEnvelope) -> dict[str, Any]:
        if envelope.receiver not in self.handlers:
            raise KeyError(f"no handler registered for {envelope.receiver}")
        retries_available = min(self.max_retries, max(0, 1 - envelope.attempt))
        for retry in range(retries_available + 1):
            attempt_envelope = envelope.model_copy(update={"attempt": envelope.attempt + retry})
            started = time.perf_counter()
            self._trace(attempt_envelope, "invocation_started", "started")
            try:
                result = await asyncio.wait_for(
                    self.handlers[attempt_envelope.receiver](attempt_envelope),
                    timeout=self.timeout_seconds,
                )
            except Exception as exc:
                duration = int((time.perf_counter() - started) * 1000)
                error_type = self._classify_error(exc)
                self._trace(
                    attempt_envelope,
                    "invocation_failed",
                    "failed",
                    duration,
                    summary={"error_type": error_type},
                    error=str(exc),
                )
                if retry >= retries_available or not self._is_retryable(exc):
                    raise
                self._trace(
                    attempt_envelope,
                    "retry_scheduled",
                    "succeeded",
                    summary={"next_attempt": attempt_envelope.attempt + 1, "error_type": error_type},
                )
                continue
            duration = int((time.perf_counter() - started) * 1000)
            self._trace(
                attempt_envelope,
                "invocation_succeeded",
                "succeeded",
                duration,
                summary=result,
            )
            return result
        raise RuntimeError("agent invocation exhausted without a terminal result")

    @staticmethod
    def _is_retryable(exc: Exception) -> bool:
        return isinstance(exc, (TimeoutError, ConnectionError, OSError))

    @staticmethod
    def _classify_error(exc: Exception) -> str:
        if isinstance(exc, TimeoutError):
            return "timeout"
        if isinstance(exc, ConnectionError):
            return "connection"
        if isinstance(exc, OSError):
            return "io"
        if isinstance(exc, (ValueError, TypeError)):
            return "contract"
        return "agent"

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
