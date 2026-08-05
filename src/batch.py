"""Concurrent CP4 batch execution with per-case failure isolation."""

from __future__ import annotations

import asyncio
from collections import Counter
from datetime import datetime, timezone
from typing import Mapping

from src.agents.coordinator import CoordinatorAgent
from src.contracts import CaseInput, CaseRunResult, TraceEvent
from src.output_writer import AtomicOutputWriter


async def execute_batch(
    cases: Mapping[str, CaseInput],
    coordinator: CoordinatorAgent,
    *,
    run_id: str,
    writer: AtomicOutputWriter | None,
    concurrency: int = 4,
) -> dict:
    if not 1 <= concurrency <= 16:
        raise ValueError("concurrency must be between 1 and 16")
    semaphore = asyncio.Semaphore(concurrency)
    errors: list[dict[str, str]] = []

    async def run_one(case: CaseInput) -> CaseRunResult | None:
        async with semaphore:
            try:
                return await coordinator.run_stub(case, run_id, writer=writer)
            except Exception as exc:
                errors.append(
                    {
                        "case_id": case.case_id,
                        "error_type": type(exc).__name__,
                        "message": str(exc),
                    }
                )
                coordinator.runtime.trace.emit(
                    TraceEvent(
                        run_id=run_id,
                        case_id=case.case_id,
                        correlation_id=f"{case.case_id}:batch-failure",
                        agent="coordinator_agent",
                        event="case_failed",
                        timestamp=datetime.now(timezone.utc),
                        status="failed",
                        output_summary={"error_type": type(exc).__name__},
                        error=str(exc),
                    )
                )
                return None

    ordered_cases = [cases[case_id] for case_id in sorted(cases)]
    raw_results = await asyncio.gather(*(run_one(case) for case in ordered_cases))
    results = [result for result in raw_results if result is not None]
    results.sort(key=lambda result: result.case_id)
    errors.sort(key=lambda error: error["case_id"])
    expected_ids = set(cases)
    verified_ids = {result.case_id for result in results if result.state == "VERIFIED"}
    written_ids = {result.case_id for result in results if result.output_path}
    terminal_ids = {result.case_id for result in results} | {
        error["case_id"] for error in errors
    }
    issue_counts = Counter(
        result.primary_issue for result in results if result.primary_issue is not None
    )
    return {
        "run_id": run_id,
        "mode": "hybrid_cp4_diagnostic",
        "concurrency": concurrency,
        "received": len(cases),
        "verified": len(verified_ids),
        "written": len(written_ids),
        "failed": len(expected_ids - verified_ids),
        "terminal": len(terminal_ids),
        "missing_terminal_ids": sorted(expected_ids - terminal_ids),
        "missing_verified_ids": sorted(expected_ids - verified_ids),
        "missing_written_ids": sorted(expected_ids - written_ids) if writer else [],
        "primary_issue_counts": dict(sorted(issue_counts.items())),
        "errors": errors,
        "results": [result.model_dump(mode="json") for result in results],
        "success": (
            len(verified_ids) == len(cases)
            and len(terminal_ids) == len(cases)
            and (writer is None or len(written_ids) == len(cases))
        ),
    }

