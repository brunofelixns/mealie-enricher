import pytest

from mealie_enricher.config import get_mealie_token, load_settings
from tests.parity.cases import load_case


def test_defaults_match_executed_reference():
    case = load_case("config-defaults")
    assert load_settings(case["environment"]).model_dump(by_alias=True) == case["expected_result"]


def test_household_tokens_preserve_case_and_ascii_normalization():
    case = load_case("token-overrides")
    settings = load_settings(case["environment"])
    actual = [get_mealie_token(settings, value) for value in case["input"]["household_ids"]]
    assert actual == case["expected_result"]


def test_missing_default_uses_first_household_override():
    settings = load_settings(
        {"MEALIE_API_TOKEN_first": "first", "MEALIE_API_TOKEN_second": "second"}
    )
    assert get_mealie_token(settings) == "first"
    assert get_mealie_token(settings, "second") == "second"


def test_missing_every_token_rejects_startup():
    with pytest.raises(ValueError, match="No Mealie API token configured"):
        load_settings({})


def test_empty_values_and_boolean_parsing_keep_original_defaults():
    settings = load_settings(
        {"MEALIE_API_TOKEN": "test", "PORT": "", "LLM_ENABLED": "TRUE", "LLM_API_KEY": ""}
    )
    assert settings.port == 8000
    assert settings.llm.enabled is True
    assert settings.llm.api_key == ""
