from pathlib import Path

import pytest
from pydantic import ValidationError

from src.config import load_runtime_config


ROOT = Path(__file__).resolve().parents[1]


def test_agent_config_has_six_models_within_limit() -> None:
    config = load_runtime_config(ROOT / "src" / "config" / "agents.yaml")
    assert len(config.agents) == 6
    assert all(agent.model_name == "o4-mini" for agent in config.agents)
    assert all(agent.parameter_count is None for agent in config.agents)
    assert all(agent.parameter_count_upper_bound == 10_000_000_000 for agent in config.agents)
    assert all(agent.parameter_count_source == "user_attested" for agent in config.agents)


def test_model_guard_rejects_model_over_10b(tmp_path: Path) -> None:
    config_text = (ROOT / "src" / "config" / "agents.yaml").read_text(encoding="utf-8")
    config_text = config_text.replace("10000000000", "11000000000", 1)
    path = tmp_path / "agents.yaml"
    path.write_text(config_text, encoding="utf-8")
    with pytest.raises(ValidationError):
        load_runtime_config(path)
