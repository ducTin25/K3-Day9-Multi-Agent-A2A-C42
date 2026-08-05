import pytest

from src.config import load_runtime_config
from src.models import build_chat_model


def test_openai_model_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    agent = load_runtime_config().agents[0]
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        build_chat_model(agent)
