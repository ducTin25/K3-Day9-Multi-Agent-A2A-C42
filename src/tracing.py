"""JSONL trace sink for the latest run."""

from __future__ import annotations

import json
from pathlib import Path
from threading import Lock

from src.contracts import TraceEvent


class TraceSink:
    def __init__(self, path: Path, *, reset: bool = True) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        if reset:
            self.path.write_text("", encoding="utf-8")

    def emit(self, event: TraceEvent) -> None:
        line = event.model_dump_json(exclude_none=True)
        with self._lock, self.path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(line + "\n")

