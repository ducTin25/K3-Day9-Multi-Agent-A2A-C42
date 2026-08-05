"""TV1 CLI for preflight and contract-safe stub orchestration."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from src.agents.coordinator import CoordinatorAgent
from src.agents.registry import build_hybrid_handlers
from src.agents.stubs import stub_handlers
from src.config import load_runtime_config
from src.preflight import run_preflight
from src.output_writer import AtomicOutputWriter
from src.runtime import AgentRuntime
from src.tracing import TraceSink
from src.batch import execute_batch


ROOT = Path(__file__).resolve().parents[1]


def write_metadata(run_id: str, mode: str = "stub") -> None:
    config = load_runtime_config()
    payload = {
        "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "framework": config.framework,
        "runtime": config.runtime,
        "schema_version": config.schema_version,
        "agents": [agent.model_dump(mode="json") for agent in config.agents],
        "mode": mode,
    }
    (ROOT / "metadata.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


async def run_stub_case(case_id: str) -> dict:
    load_runtime_config()  # Startup model guard.
    cases, _ = run_preflight(ROOT)
    if case_id not in cases:
        raise ValueError(f"unknown case_id: {case_id}")
    run_id = f"run-{uuid4()}"
    trace = TraceSink(ROOT / "trace.jsonl", reset=True)
    runtime = AgentRuntime(trace, stub_handlers())
    coordinator = CoordinatorAgent(runtime)
    result = await coordinator.run_stub(cases[case_id], run_id)
    write_metadata(run_id)
    return result.model_dump(mode="json")


async def run_hybrid_case(case_id: str, *, write_output: bool = False) -> dict:
    """Run all domain agents plus offline model doubles for staged integration."""
    load_runtime_config()
    cases, _ = run_preflight(ROOT)
    if case_id not in cases:
        raise ValueError(f"unknown case_id: {case_id}")
    run_id = f"run-{uuid4()}"
    trace = TraceSink(ROOT / "trace.jsonl", reset=True)
    runtime = AgentRuntime(trace, build_hybrid_handlers(trace))
    coordinator = CoordinatorAgent(runtime)
    writer = AtomicOutputWriter(ROOT / "output") if write_output else None
    result = await coordinator.run_stub(cases[case_id], run_id, writer=writer)
    write_metadata(run_id, mode="hybrid_cp2")
    return result.model_dump(mode="json")


def _atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


async def run_hybrid_batch(*, concurrency: int = 4, write_output: bool = True) -> dict:
    """Run all 50 cases without API calls, isolating failures by case."""
    load_runtime_config()
    cases, _ = run_preflight(ROOT)
    run_id = f"run-{uuid4()}"
    trace = TraceSink(ROOT / "trace.jsonl", reset=True)
    runtime = AgentRuntime(trace, build_hybrid_handlers(trace))
    coordinator = CoordinatorAgent(runtime)
    writer = AtomicOutputWriter(ROOT / "output") if write_output else None
    if writer is not None:
        for case_id in cases:
            (ROOT / "output" / f"{case_id}.json").unlink(missing_ok=True)
    summary = await execute_batch(
        cases,
        coordinator,
        run_id=run_id,
        writer=writer,
        concurrency=concurrency,
    )
    if writer is not None:
        actual_files = {path.stem for path in (ROOT / "output").glob("EC_*.json")}
        summary["unexpected_output_ids"] = sorted(actual_files - set(cases))
        summary["success"] = summary["success"] and actual_files == set(cases)
    _atomic_write_json(ROOT / "logging" / "run_summary.json", summary)
    write_metadata(run_id, mode="hybrid_cp4_diagnostic")
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--preflight", action="store_true", help="validate all 50 complaint inputs")
    group.add_argument("--case", metavar="EC_NNN", help="run one case")
    group.add_argument("--batch", action="store_true", help="run all 50 cases")
    parser.add_argument("--stub", action="store_true", help="use contract-safe stub agents")
    parser.add_argument(
        "--hybrid",
        action="store_true",
        help="use all real domain agents and offline Policy/Verifier model doubles",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=4,
        help="maximum concurrent cases for --batch (1-16)",
    )
    parser.add_argument(
        "--write-output",
        action="store_true",
        help="atomically write a verified hybrid draft to output/",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        load_runtime_config()
        if args.preflight:
            _, report = run_preflight(ROOT)
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 0
        if args.batch:
            if not args.hybrid or args.stub:
                raise ValueError("--batch currently requires --hybrid")
            result = asyncio.run(
                run_hybrid_batch(
                    concurrency=args.concurrency,
                    write_output=args.write_output,
                )
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if result["success"] else 1
        if args.stub == args.hybrid:
            raise ValueError("choose exactly one execution mode: --stub or --hybrid")
        if args.write_output and not args.hybrid:
            raise ValueError("--write-output is only supported with --hybrid")
        if args.hybrid:
            result = asyncio.run(run_hybrid_case(args.case, write_output=args.write_output))
        else:
            result = asyncio.run(run_stub_case(args.case))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
