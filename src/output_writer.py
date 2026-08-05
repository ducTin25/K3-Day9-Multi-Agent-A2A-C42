"""Atomic output writer gated by independent verification."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping

from jsonschema import Draft202012Validator

from src.contracts import VerifyResult


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCHEMA = ROOT / "src" / "schemas" / "output.schema.json"


class OutputWriteError(ValueError):
    pass


class AtomicOutputWriter:
    def __init__(self, output_dir: Path, schema_path: Path = DEFAULT_SCHEMA) -> None:
        self.output_dir = output_dir
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        self.validator = Draft202012Validator(schema)

    def write_verified(
        self,
        payload: Mapping[str, Any],
        verification: VerifyResult,
        *,
        expected_case_id: str,
    ) -> Path:
        if not verification.valid:
            raise OutputWriteError("refusing to write output that did not pass Verifier")
        if payload.get("case_id") != expected_case_id:
            raise OutputWriteError("output case_id does not match the requested case")
        errors = sorted(self.validator.iter_errors(dict(payload)), key=lambda item: list(item.path))
        if errors:
            details = "; ".join(
                f"{'.'.join(map(str, error.path)) or '$'}: {error.message}" for error in errors
            )
            raise OutputWriteError(f"output schema validation failed: {details}")

        self.output_dir.mkdir(parents=True, exist_ok=True)
        destination = self.output_dir / f"{expected_case_id}.json"
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="\n",
                suffix=".tmp",
                prefix=f".{expected_case_id}.",
                dir=self.output_dir,
                delete=False,
            ) as handle:
                temporary = Path(handle.name)
                json.dump(dict(payload), handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, destination)
        except Exception:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
            raise
        return destination

