from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.compare_runs import compare_runs
from scripts.summarize_run import summarize_run
from src.tools.verification_tools import REQUIRED_AGENT_IDS


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def write_jsonl(path: Path, values) -> None:
    path.write_text("".join(json.dumps(value) + "\n" for value in values), encoding="utf-8")


def good_metadata() -> dict:
    return {
        "framework": "custom-python",
        "runtime": "python-3.12",
        "agents": [
            {"agent_id": agent, "model_name": "documented-8b", "parameter_count": 8_000_000_000, "prompt_version": "v1", "tools": [], "fallback_models": []}
            for agent in sorted(REQUIRED_AGENT_IDS)
        ],
    }


def create_run(path: Path, *, run_id: str, complete: bool) -> None:
    path.mkdir(parents=True)
    write_json(path / "run.json", {"run_id": run_id, "dataset_checksum": "sha256:test"})
    write_json(path / "config_snapshot.json", good_metadata())
    events = [{"event_type": "CASE_RECEIVED", "case_id": "EC_001"}]
    for agent in sorted(REQUIRED_AGENT_IDS):
        events.extend(
            [
                {"event_type": "AGENT_STARTED", "case_id": "EC_001", "agent_id": agent},
                {"event_type": "AGENT_RESPONSE", "case_id": "EC_001", "agent_id": agent, "duration_ms": 10},
            ]
        )
    if complete:
        events.extend(
            [
                {"event_type": "VERIFY_PASSED", "case_id": "EC_001", "attempt": 0},
                {"event_type": "OUTPUT_WRITTEN", "case_id": "EC_001"},
            ]
        )
    else:
        events.append({"event_type": "CASE_FAILED", "case_id": "EC_001"})
    write_jsonl(path / "trace.jsonl", events)
    write_jsonl(path / "cases.jsonl", [{"case_id": "EC_001", "state": "WRITTEN" if complete else "FAILED", "output": {"case_id": "EC_001", "value": 1 if complete else 0}}])
    write_jsonl(path / "errors.jsonl", [] if complete else [{"case_id": "EC_001", "error_code": "POLICY_TEST", "owner": "policy_agent"}])
    write_jsonl(path / "verifier_feedback.jsonl", [])


class RunReportingTests(unittest.TestCase):
    def test_summary_builds_metrics_and_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            run = Path(temp) / "run-good"
            create_run(run, run_id="run-good", complete=True)
            metrics = summarize_run(run)
            self.assertEqual(1, metrics["cases_written"])
            self.assertEqual(1, metrics["cases_with_all_six_agents"])
            self.assertTrue(metrics["reproducible"])
            self.assertTrue((run / "metrics.json").exists())
            self.assertTrue((run / "summary.md").exists())

    def test_candidate_improvement_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            baseline = Path(temp) / "baseline"
            candidate = Path(temp) / "candidate"
            create_run(baseline, run_id="baseline", complete=False)
            create_run(candidate, run_id="candidate", complete=True)
            summarize_run(baseline)
            summarize_run(candidate)
            comparison = compare_runs(baseline, candidate)
            self.assertTrue(comparison["improved_or_equal"])
            self.assertEqual(1, comparison["changed_case_count"])

    def test_regression_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            baseline = Path(temp) / "baseline"
            candidate = Path(temp) / "candidate"
            create_run(baseline, run_id="baseline", complete=True)
            create_run(candidate, run_id="candidate", complete=False)
            summarize_run(baseline)
            summarize_run(candidate)
            comparison = compare_runs(baseline, candidate)
            self.assertFalse(comparison["improved_or_equal"])
            self.assertTrue(comparison["regressions"])


if __name__ == "__main__":
    unittest.main()
