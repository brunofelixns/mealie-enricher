import pytest

from mealie_enricher.config import load_settings


def test_nova_is_opt_in_and_independent_of_catalog_matching():
    defaults = load_settings({"MEALIE_API_TOKEN": "test"})
    assert defaults.nova_enabled is False
    settings = load_settings(
        {
            "MEALIE_API_TOKEN": "test",
            "NOVA_ENABLED": "true",
            "OPENAI_API_KEY": "test-openai",
        }
    )
    assert settings.nova_enabled is True
    assert not settings.catalog.enabled
    assert not settings.decisions.enabled
    assert settings.decisions.api_key == "test-openai"
    assert "test-openai" not in settings.model_dump_json()


def test_nova_prefers_decisions_key_and_does_not_reuse_other_provider_key():
    settings = load_settings(
        {
            "MEALIE_API_TOKEN": "test",
            "NOVA_ENABLED": "true",
            "DECISIONS_API_KEY": "test-decisions",
            "OPENAI_API_KEY": "test-openai",
            "LLM_API_KEY": "test-other",
        }
    )
    assert settings.decisions.api_key == "test-decisions"
    assert "test-decisions" not in repr(settings)


def test_nova_requires_a_decisions_key_at_startup(tmp_path):
    from mealie_enricher.agents.nova_decisions import OpenAINovaClassifier

    settings = load_settings({"MEALIE_API_TOKEN": "test", "NOVA_ENABLED": "true"})
    with pytest.raises(ValueError, match="API key"):
        OpenAINovaClassifier(settings.decisions)
