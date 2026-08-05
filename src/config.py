"""Runtime configuration loader and <=10B startup guard."""

from __future__ import annotations

from pathlib import Path

import yaml

from src.contracts import RuntimeConfig


DEFAULT_CONFIG_PATH = Path(__file__).parent / "config" / "agents.yaml"


def load_runtime_config(path: Path = DEFAULT_CONFIG_PATH) -> RuntimeConfig:
    with path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)
    return RuntimeConfig.model_validate(raw)

