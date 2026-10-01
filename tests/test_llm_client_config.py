import pytest

from src.config import build_config
from src.schemas import Issue, ScoredIssue
from src.services.llm_client import MockLLMClient, OpenAICompatibleLLMClient, get_llm_client


def test_real_mode_requires_api_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "")

    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        build_config(mode="real")


def test_build_config_reads_real_mode_env(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-test")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.example.com/v1")

    config = build_config(mode="real")

    assert config["llm_api_key"] == "test-key"
    assert config["llm_model"] == "gpt-test"
    assert config["llm_base_url"] == "https://api.example.com/v1"


def test_get_llm_client_returns_mock_for_mock_mode():
    assert isinstance(get_llm_client({"mode": "mock"}), MockLLMClient)


def test_get_llm_client_returns_real_client_for_real_mode():
    client = get_llm_client(
        {
            "mode": "real",
            "llm_api_key": "test-key",
            "llm_model": "gpt-test",
            "llm_base_url": "https://api.example.com/v1",
        }
    )

    assert isinstance(client, OpenAICompatibleLLMClient)


def test_real_client_normalizes_pain_point_alias_response():
    class AliasResponseClient(OpenAICompatibleLLMClient):
        def __init__(self):
            pass

        def _json_chat(self, system, payload):
            return {
                "pain_points": [
                    {
                        "pain_point": "Tools cannot be selected when only two tools are provided.",
                        "issues": [4798],
                    }
                ]
            }

    scored_issue = ScoredIssue(
        issue=Issue(
            id=4798,
            title="Tool selection broken with two tools",
            body="When only two tools are provided, selection is unreliable.",
            url="https://github.com/browser-use/browser-use/issues/4798",
        ),
        score=7,
        signals=["high reaction count"],
    )

    pain_points = AliasResponseClient().extract_pain_points([scored_issue])

    assert len(pain_points) == 1
    assert pain_points[0].pain_id == "pain_001"
    assert pain_points[0].source_issue_id == 4798
    assert pain_points[0].evidence_url == "https://github.com/browser-use/browser-use/issues/4798"
    assert pain_points[0].pain == "Tools cannot be selected when only two tools are provided."
