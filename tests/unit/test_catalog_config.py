import pytest

from mealie_enricher.config import load_settings


def test_catalog_is_opt_in_and_does_not_use_llm_credentials_for_decisions():
    settings = load_settings({"MEALIE_API_TOKEN": "test", "LLM_API_KEY": "other-provider"})
    assert settings.catalog.enabled is False
    assert settings.decisions.enabled is False
    assert settings.decisions.api_key == ""


def test_catalog_and_decisions_have_separate_configuration():
    settings = load_settings(
        {
            "MEALIE_API_TOKEN": "test",
            "CATALOG_ENABLED": "true",
            "CATALOG_DB_PATH": "/catalogs/catalogos.duckdb",
            "DECISIONS_ENABLED": "true",
            "OPENAI_API_KEY": "test-only",
            "DECISIONS_MIN_CONFIDENCE": "0.95",
        }
    )
    assert settings.catalog.enabled
    assert settings.catalog.db_path == "/catalogs/catalogos.duckdb"
    assert settings.decisions.api_key == "test-only"
    assert settings.decisions.min_confidence == 0.95
    assert "test-only" not in repr(settings.decisions)
    assert "test-only" not in settings.model_dump_json()


@pytest.mark.parametrize("confidence", ["-1", "1.1", "nan"])
def test_invalid_decision_confidence_rejected(confidence):
    with pytest.raises(ValueError):
        load_settings({"MEALIE_API_TOKEN": "test", "DECISIONS_MIN_CONFIDENCE": confidence})
