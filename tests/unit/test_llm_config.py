import pytest

from mealie_enricher.config import load_settings


@pytest.mark.parametrize("model", ["gpt-5-mini", "gpt-6.1-sol", "gpt-6.1-terra", "o3", "o4-mini"])
@pytest.mark.parametrize("blank_limits", [False, True])
def test_reasoning_model_defaults_allow_room_for_reasoning_and_output(model, blank_limits):
    env = {"MEALIE_API_TOKEN": "synthetic", "LLM_MODEL": model}
    if blank_limits:
        env.update(LLM_MAX_TOKENS_GRAMS="", LLM_MAX_TOKENS_NUTRIENTS="")
    settings = load_settings(env).llm
    assert settings.max_tokens_grams == 1024
    assert settings.max_tokens_nutrients == 2048


def test_explicit_reasoning_token_limits_are_respected():
    settings = load_settings(
        {
            "MEALIE_API_TOKEN": "synthetic",
            "LLM_MODEL": "gpt-6.1-sol",
            "LLM_MAX_TOKENS_GRAMS": "512",
            "LLM_MAX_TOKENS_NUTRIENTS": "4096",
        }
    ).llm
    assert settings.max_tokens_grams == 512
    assert settings.max_tokens_nutrients == 4096


@pytest.mark.parametrize("model", ["mistral-small-latest", "gpt-4o-mini", "gpt-5-chat-latest"])
def test_classic_model_token_defaults_are_unchanged(model):
    settings = load_settings({"MEALIE_API_TOKEN": "synthetic", "LLM_MODEL": model}).llm
    assert settings.max_tokens_grams == 10
    assert settings.max_tokens_nutrients == 200
