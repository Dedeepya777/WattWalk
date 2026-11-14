"""The planner model id picks the LangChain chat model by prefix (no network calls)."""
import pytest


def _deep():
    # Import inside the tests: importing deep at module level also imports the agent tools/providers
    # during collection, which hides the import-failure check in test_agent.py.
    from wattwalk.agent import deep

    return deep


def test_deepseek_prefix_builds_chat_openai(monkeypatch):
    pytest.importorskip("langchain_openai")
    deep = _deep()
    monkeypatch.setattr(deep.config, "DEEPSEEK_API_KEY", "sk-test-key")
    model = deep.make_model("deepseek/deepseek-flash")
    assert type(model).__name__ == "ChatOpenAI"
    assert model.model_name == "deepseek-flash"
    assert "deepseek" in str(model.openai_api_base).lower()


def test_deepseek_alias_normalizes(monkeypatch):
    pytest.importorskip("langchain_openai")
    deep = _deep()
    monkeypatch.setattr(deep.config, "DEEPSEEK_API_KEY", "sk-test-key")
    model = deep.make_model("deepseek/DeepSeek-V4.1-Flash-1017")
    assert type(model).__name__ == "ChatOpenAI"
    assert model.model_name == "deepseek-flash"


def test_bedrock_id_builds_chat_bedrock_converse():
    pytest.importorskip("langchain_aws")
    deep = _deep()
    model = deep.make_model("us.anthropic.claude-sonnet-4-5")
    assert type(model).__name__ == "ChatBedrockConverse"


def test_missing_planner_id_says_use_scripted(monkeypatch):
    deep = _deep()
    monkeypatch.setattr(deep.config, "PLANNER_MODEL_ID", "")
    with pytest.raises(RuntimeError, match="scripted"):
        deep.make_model()
