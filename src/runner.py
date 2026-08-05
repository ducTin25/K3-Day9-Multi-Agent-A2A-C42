"""TV1 CLI for preflight and contract-safe stub orchestration."""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from src.agents.coordinator import CoordinatorAgent
from src.agents.registry import build_hybrid_handlers
from src.agents.stubs import stub_handlers
from src.config import load_runtime_config
from src.preflight import run_preflight
from src.runtime import AgentRuntime
from src.tracing import TraceSink


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


async def run_hybrid_case(case_id: str) -> dict:
    """Run real TV4/TV5 handlers and offline stubs for pending TV2/TV3 agents."""
    load_runtime_config()
    cases, _ = run_preflight(ROOT)
    if case_id not in cases:
        raise ValueError(f"unknown case_id: {case_id}")
    run_id = f"run-{uuid4()}"
    trace = TraceSink(ROOT / "trace.jsonl", reset=True)
    runtime = AgentRuntime(trace, build_hybrid_handlers(trace))
    coordinator = CoordinatorAgent(runtime)
    result = await coordinator.run_stub(cases[case_id], run_id)
    write_metadata(run_id, mode="hybrid_cp2")
    return result.model_dump(mode="json")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--preflight", action="store_true", help="validate all 50 complaint inputs")
    group.add_argument("--case", metavar="EC_NNN", help="run one case")
    parser.add_argument("--stub", action="store_true", help="use contract-safe stub agents")
    parser.add_argument(
        "--hybrid",
        action="store_true",
        help="use real TV4/TV5 agents and offline TV2/TV3 stubs",
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
        if args.stub == args.hybrid:
            raise ValueError("choose exactly one execution mode: --stub or --hybrid")
        target = run_hybrid_case if args.hybrid else run_stub_case
        result = asyncio.run(target(args.case))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
