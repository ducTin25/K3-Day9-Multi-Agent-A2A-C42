"""Compare a candidate run with a baseline and report regressions."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.summarize_run import read_json, read_jsonl, resolve_run, summarize_run

HIGHER_IS_BETTER = (
    "cases_verified",
    "cases_written",
    "completion_rate",
    "first_pass_verify_rate",
    "repair_success_rate",
    "cases_with_all_six_agents",
    "multi_agent_integrity_rate",
)
LOWER_IS_BETTER = ("cases_failed", "verifier_reject_count")


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    os.replace(temporary, path)


def _load_metrics(run_dir: Path) -> dict[str, Any]:
    metrics = read_json(run_dir / "metrics.json")
    return metrics if isinstance(metrics, dict) else summarize_run(run_dir)


def _flatten(value: Any, path: str = "$") -> dict[str, Any]:
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key in sorted(value):
            result.update(_flatten(value[key], f"{path}.{key}"))
        return result
    if isinstance(value, list):
        result = {}
        for index, item in enumerate(value):
            result.update(_flatten(item, f"{path}[{index}]"))
        return result
    return {path: value}


def _case_outputs(run_dir: Path) -> dict[str, Any]:
    outputs: dict[str, Any] = {}
    for record in read_jsonl(run_dir / "cases.jsonl"):
        case_id = record.get("case_id")
        output = record.get("output") or record.get("final_output")
        if case_id and isinstance(output, Mapping):
            outputs[str(case_id)] = output
    return outputs


def compare_runs(baseline_dir: Path, candidate_dir: Path) -> dict[str, Any]:
    baseline_metrics = _load_metrics(baseline_dir.resolve())
    candidate_metrics = _load_metrics(candidate_dir.resolve())
    deltas: dict[str, Any] = {}
    regressions: list[dict[str, Any]] = []

    for metric in HIGHER_IS_BETTER + LOWER_IS_BETTER:
        before = baseline_metrics.get(metric, 0)
        after = candidate_metrics.get(metric, 0)
        delta = after - before
        deltas[metric] = {"baseline": before, "candidate": after, "delta": delta}
        is_regression = delta < 0 if metric in HIGHER_IS_BETTER else delta > 0
        if is_regression:
            regressions.append({"type": "metric", "metric": metric, "baseline": before, "candidate": after})

    if candidate_metrics.get("metadata_errors"):
        regressions.append({"type": "hard_gate", "metric": "metadata_errors", "candidate": candidate_metrics["metadata_errors"]})

    baseline_outputs = _case_outputs(baseline_dir)
    candidate_outputs = _case_outputs(candidate_dir)
    case_diffs: dict[str, list[dict[str, Any]]] = {}
    for case_id in sorted(set(baseline_outputs) | set(candidate_outputs)):
        before = _flatten(baseline_outputs.get(case_id))
        after = _flatten(candidate_outputs.get(case_id))
        changes = []
        for path in sorted(set(before) | set(after)):
            if before.get(path) != after.get(path):
                changes.append({"path": path, "baseline": before.get(path), "candidate": after.get(path)})
        if changes:
            case_diffs[case_id] = changes

    return {
        "baseline_run_id": baseline_metrics.get("run_id") or baseline_dir.name,
        "candidate_run_id": candidate_metrics.get("run_id") or candidate_dir.name,
        "improved_or_equal": not regressions,
        "metric_deltas": deltas,
        "regressions": regressions,
        "changed_case_count": len(case_diffs),
        "case_diffs": case_diffs,
    }


def render_report(comparison: Mapping[str, Any]) -> str:
    rows = "\n".join(
        f"| `{metric}` | {values['baseline']} | {values['candidate']} | {values['delta']:+} |"
        for metric, values in comparison.get("metric_deltas", {}).items()
    )
    regressions = "\n".join(
        f"- `{item.get('metric')}`: baseline={item.get('baseline')}, candidate={item.get('candidate')}"
        for item in comparison.get("regressions", [])
    ) or "- None"
    return f"""# Run comparison

- Baseline: `{comparison.get('baseline_run_id')}`
- Candidate: `{comparison.get('candidate_run_id')}`
- Improved or equal: **{comparison.get('improved_or_equal')}**
- Changed cases: {comparison.get('changed_case_count', 0)}

## Metrics

| Metric | Baseline | Candidate | Delta |
| --- | ---: | ---: | ---: |
{rows}

## Regressions

{regressions}
"""


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline")
    parser.add_argument("candidate")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "logging" / "comparisons")
    args = parser.parse_args(argv)
    baseline_dir = resolve_run(args.baseline)
    candidate_dir = resolve_run(args.candidate)
    try:
        comparison = compare_runs(baseline_dir, candidate_dir)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"compare_runs: {exc}", file=sys.stderr)
        return 1

    stem = f"{comparison['baseline_run_id']}__{comparison['candidate_run_id']}"
    _atomic_write(args.output_dir / f"{stem}.json", json.dumps(comparison, ensure_ascii=False, indent=2) + "\n")
    _atomic_write(args.output_dir / f"{stem}.md", render_report(comparison))
    print(json.dumps(comparison, ensure_ascii=False, indent=2))
    return 0 if comparison["improved_or_equal"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
