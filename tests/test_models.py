import pytest

from src.config import load_runtime_config
from src.models import build_chat_model


def test_verify_result_schema_has_no_untyped_nodes() -> None:
    from src.contracts import VerifyResult

    def visit(value):
        if isinstance(value, dict):
            assert value != {}, "Structured Outputs does not accept an untyped schema node"
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(VerifyResult.model_json_schema())


def test_openai_model_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    agent = load_runtime_config().agents[0]
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        build_chat_model(agent)
