"""The planner model id picks the LangChain chat model by prefix (no network calls)."""
import pytest

from wattwalk.agent import deep


def test_ollama_prefix_builds_chat_ollama_with_large_context():
    pytest.importorskip("langchain_ollama")
    model = deep.make_model("ollama/qwen3:8b")
    assert type(model).__name__ == "ChatOllama"
    assert model.model == "qwen3:8b"
    assert model.num_ctx == deep.OLLAMA_CONTEXT_TOKENS >= 16384
    assert model.temperature == 0


def test_bedrock_id_builds_chat_bedrock_converse():
    pytest.importorskip("langchain_aws")
    model = deep.make_model("us.anthropic.claude-sonnet-4-5")
    assert type(model).__name__ == "ChatBedrockConverse"


def test_missing_planner_id_says_use_scripted(monkeypatch):
    monkeypatch.setattr(deep.config, "PLANNER_MODEL_ID", "")
    with pytest.raises(RuntimeError, match="scripted"):
        deep.make_model()
