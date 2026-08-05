"""Validate and normalize complaint inputs by their internal case_id."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from src.contracts import CaseInput


EXPECTED_CASE_IDS = {f"EC_{index:03d}" for index in range(1, 51)}


def _to_case_input(payload: dict[str, Any]) -> CaseInput:
    request = payload.get("customer_request", {})
    return CaseInput(
        case_id=payload.get("case_id"),
        opened_at=payload.get("opened_at"),
        claimed_order_id=request.get("claimed_order_id"),
        policy_version=payload.get("policy_version"),
        message=request.get("message"),
        language=request.get("language", "vi"),
    )


def discover_inputs(input_dir: Path) -> tuple[dict[str, CaseInput], list[dict[str, str]]]:
    cases: dict[str, CaseInput] = {}
    sources: list[dict[str, str]] = []
    candidates = sorted(path for path in input_dir.iterdir() if path.is_file() and path.name != ".gitkeep")
    for path in candidates:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            case = _to_case_input(payload)
        except (json.JSONDecodeError, OSError, ValidationError) as exc:
            raise ValueError(f"invalid complaint input {path.name}: {exc}") from exc
        if case.case_id in cases:
            raise ValueError(f"duplicate case_id {case.case_id} in {path.name}")
        cases[case.case_id] = case
        sources.append(
            {
                "source_file": path.name,
                "case_id": case.case_id,
                "canonical_file": f"{case.case_id}.json",
            }
        )
    return cases, sources


def load_order_ids(orders_csv: Path) -> set[str]:
    with orders_csv.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if "order_id" not in (reader.fieldnames or []):
            raise ValueError("orders CSV is missing required order_id column")
        return {row["order_id"] for row in reader if row.get("order_id")}


def run_preflight(root: Path) -> tuple[dict[str, CaseInput], dict[str, Any]]:
    cases, sources = discover_inputs(root / "input")
    actual_ids = set(cases)
    missing_ids = sorted(EXPECTED_CASE_IDS - actual_ids)
    extra_ids = sorted(actual_ids - EXPECTED_CASE_IDS)
    order_ids = load_order_ids(root / "data" / "olist_orders_dataset.csv")
    missing_orders = sorted(
        {case.claimed_order_id for case in cases.values() if case.claimed_order_id not in order_ids}
    )
    report = {
        "valid": not missing_ids and not extra_ids and not missing_orders and len(cases) == 50,
        "case_count": len(cases),
        "missing_case_ids": missing_ids,
        "extra_case_ids": extra_ids,
        "missing_order_ids": missing_orders,
        "normalized_sources": sources,
    }
    if not report["valid"]:
        raise ValueError(json.dumps(report, ensure_ascii=False, indent=2))
    return dict(sorted(cases.items())), report

