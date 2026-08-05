"""Create machine-readable and human-readable summaries for one run."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.tools.verification_tools import REQUIRED_AGENT_IDS, validate_metadata


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSON: {exc}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number}: expected a JSON object")
            records.append(value)
    return records


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    os.replace(temporary, path)


def _case_id(record: Mapping[str, Any]) -> str | None:
    value = record.get("case_id")
    return str(value) if value else None


def compute_metrics(run_dir: Path) -> dict[str, Any]:
    trace = read_jsonl(run_dir / "trace.jsonl")
    case_records = read_jsonl(run_dir / "cases.jsonl")
    explicit_errors = read_jsonl(run_dir / "errors.jsonl")
    verifier_feedback = read_jsonl(run_dir / "verifier_feedback.jsonl")
    config = read_json(run_dir / "config_snapshot.json", {}) or {}
    run = read_json(run_dir / "run.json", {}) or {}

    event_counts = Counter(str(event.get("event_type", "UNKNOWN")) for event in trace)
    agent_invocations = Counter()
    tool_calls = Counter()
    errors_by_code = Counter()
    errors_by_owner = Counter()
    agent_sets: dict[str, set[str]] = defaultdict(set)
    duration_by_agent: dict[str, list[int]] = defaultdict(list)

    received_cases: set[str] = set()
    verified_cases: set[str] = set()
    written_cases: set[str] = set()
    failed_cases: set[str] = set()
    first_pass_verified: set[str] = set()
    repaired_cases: set[str] = set()
    repair_success_cases: set[str] = set()

    for event in trace:
        case_id = _case_id(event)
        event_type = str(event.get("event_type", ""))
        agent_id = event.get("agent_id")
        if case_id and agent_id and event_type in {"AGENT_STARTED", "AGENT_RESPONSE", "AGENT_FAILED"}:
            agent_sets[case_id].add(str(agent_id))
        if agent_id and event_type == "AGENT_STARTED":
            agent_invocations[str(agent_id)] += 1
        if agent_id and isinstance(event.get("duration_ms"), int):
            duration_by_agent[str(agent_id)].append(int(event["duration_ms"]))
        tool_name = event.get("tool_name")
        if tool_name and event_type in {"TOOL_STARTED", "TOOL_COMPLETED", "TOOL_FAILED"}:
            tool_calls[str(tool_name)] += 1
        if case_id and event_type == "CASE_RECEIVED":
            received_cases.add(case_id)
        if case_id and event_type in {"VERIFY_PASSED", "VERIFIER_PASSED"}:
            verified_cases.add(case_id)
            if int(event.get("attempt", 0)) == 0:
                first_pass_verified.add(case_id)
            else:
                repair_success_cases.add(case_id)
        if case_id and event_type == "OUTPUT_WRITTEN":
            written_cases.add(case_id)
        if case_id and event_type == "CASE_FAILED":
            failed_cases.add(case_id)
        if case_id and event_type == "REPAIR_REQUESTED":
            repaired_cases.add(case_id)
        error = event.get("error")
        if isinstance(error, Mapping):
            codes = error.get("codes") or [error.get("code")]
            for code in codes:
                if code:
                    errors_by_code[str(code)] += 1

    for record in explicit_errors + verifier_feedback:
        code = record.get("error_code") or record.get("code")
        owner = record.get("owner") or record.get("repair_target")
        if code:
            errors_by_code[str(code)] += 1
        if owner:
            errors_by_owner[str(owner)] += 1

    for record in case_records:
        case_id = _case_id(record)
        if not case_id:
            continue
        state = str(record.get("state") or record.get("status") or "").upper()
        if state in {"RECEIVED", "RUNNING", "VERIFIED", "WRITTEN", "COMPLETED", "FAILED"}:
            received_cases.add(case_id)
        if state in {"VERIFIED", "WRITTEN", "COMPLETED"}:
            verified_cases.add(case_id)
        if state in {"WRITTEN", "COMPLETED"}:
            written_cases.add(case_id)
        if state == "FAILED":
            failed_cases.add(case_id)

    case_universe = received_cases | set(agent_sets) | {_case_id(record) for record in case_records}
    case_universe.discard(None)
    complete_agent_cases = {
        case_id for case_id, agents in agent_sets.items() if REQUIRED_AGENT_IDS.issubset(agents)
    }

    metadata_errors = validate_metadata(config)
    verifier_checks = len(verified_cases) + event_counts["VERIFY_REJECTED"] + event_counts["VERIFIER_REJECTED"]
    denominator = max(1, len(case_universe))
    metrics = {
        "run_id": run.get("run_id") or run_dir.name,
        "reproducible": not metadata_errors and bool(run.get("dataset_checksum") or run.get("input_checksum")),
        "cases_received": len(received_cases),
        "cases_verified": len(verified_cases),
        "cases_written": len(written_cases),
        "cases_failed": len(failed_cases),
        "completion_rate": round(len(written_cases) / denominator, 6),
        "first_pass_verify_rate": round(len(first_pass_verified) / max(1, len(verified_cases)), 6),
        "repair_success_rate": round(len(repair_success_cases) / max(1, len(repaired_cases)), 6),
        "verifier_reject_count": event_counts["VERIFY_REJECTED"] + event_counts["VERIFIER_REJECTED"],
        "verifier_check_count": verifier_checks,
        "cases_with_all_six_agents": len(complete_agent_cases),
        "multi_agent_integrity_rate": round(len(complete_agent_cases) / denominator, 6),
        "missing_agent_cases": sorted(set(case_universe) - complete_agent_cases),
        "event_counts": dict(sorted(event_counts.items())),
        "agent_invocations": dict(sorted(agent_invocations.items())),
        "tool_calls": dict(sorted(tool_calls.items())),
        "errors_by_code": dict(sorted(errors_by_code.items())),
        "errors_by_owner": dict(sorted(errors_by_owner.items())),
        "metadata_errors": metadata_errors,
        "agent_duration_ms": {
            agent: {
                "count": len(values),
                "total": sum(values),
                "average": round(sum(values) / len(values), 2),
                "max": max(values),
            }
            for agent, values in sorted(duration_by_agent.items())
            if values
        },
    }
    return metrics


def render_summary(metrics: Mapping[str, Any]) -> str:
    error_rows = "\n".join(
        f"| `{code}` | {count} |" for code, count in metrics.get("errors_by_code", {}).items()
    ) or "| _none_ | 0 |"
    metadata_status = "PASS" if not metrics.get("metadata_errors") else "FAIL"
    return f"""# Run summary — {metrics.get('run_id')}

## Outcome

| Metric | Value |
| --- | ---: |
| Cases received | {metrics.get('cases_received', 0)} |
| Cases verified | {metrics.get('cases_verified', 0)} |
| Cases written | {metrics.get('cases_written', 0)} |
| Cases failed | {metrics.get('cases_failed', 0)} |
| First-pass verify rate | {metrics.get('first_pass_verify_rate', 0):.2%} |
| Repair success rate | {metrics.get('repair_success_rate', 0):.2%} |
| Multi-agent integrity rate | {metrics.get('multi_agent_integrity_rate', 0):.2%} |
| Metadata/model gate | {metadata_status} |

## Errors

| Error code | Count |
| --- | ---: |
{error_rows}

## Improvement gate

- Missing-agent cases: {', '.join(metrics.get('missing_agent_cases', [])) or 'none'}
- Metadata errors: {len(metrics.get('metadata_errors', []))}
- Promote only when 50 cases are verified/written, metadata passes, and multi-agent integrity is 100%.
"""


def summarize_run(run_dir: Path) -> dict[str, Any]:
    run_dir = run_dir.resolve()
    metrics = compute_metrics(run_dir)
    _atomic_write(run_dir / "metrics.json", json.dumps(metrics, ensure_ascii=False, indent=2) + "\n")
    _atomic_write(run_dir / "summary.md", render_summary(metrics))
    return metrics


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", help="Run ID or path to logging/runs/<run_id>")
    return parser


def resolve_run(value: str) -> Path:
    candidate = Path(value)
    return candidate if candidate.exists() else ROOT / "logging" / "runs" / value


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    run_dir = resolve_run(args.run)
    try:
        metrics = summarize_run(run_dir)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"summarize_run: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(metrics, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
