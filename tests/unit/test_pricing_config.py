import pytest

from mealie_enricher.config import load_settings


def test_pricing_is_opt_in_and_postal_code_is_configurable():
    settings = load_settings({"MEALIE_API_TOKEN": "test"})
    assert not settings.pricing.enabled
    assert settings.pricing.postal_code == "27004"
    assert settings.pricing.sync_interval_hours == 168
    changed = load_settings({"MEALIE_API_TOKEN": "test", "MERCADONA_POSTAL_CODE": "28040"})
    assert changed.pricing.postal_code == "28040"


@pytest.mark.parametrize(
    "updates",
    [
        {"MERCADONA_POSTAL_CODE": "2700"},
        {"PRICING_SYNC_INTERVAL_HOURS": "0"},
        {"PRICING_SYNC_INTERVAL_HOURS": "NaN"},
        {"PRICING_MAX_CANDIDATES": "255"},
        {"PRICING_REQUEST_DELAY_SECONDS": "-1"},
    ],
)
def test_pricing_rejects_invalid_operational_settings(updates):
    with pytest.raises(ValueError):
        load_settings({"MEALIE_API_TOKEN": "test", **updates})


def test_pricing_reuses_decisions_key_but_requires_own_control_token():
    values = {"MEALIE_API_TOKEN": "test", "PRICING_ENABLED": "true", "OPENAI_API_KEY": "test-key"}
    with pytest.raises(ValueError, match="PRICING_ADMIN_TOKEN"):
        load_settings(values)
    settings = load_settings({**values, "PRICING_ADMIN_TOKEN": "pricing-admin-test-token"})
    assert settings.pricing.enabled
    assert not settings.decisions.enabled
    assert settings.decisions.api_key == "test-key"
    assert "pricing-admin-test-token" not in repr(settings.pricing)
    assert "pricing-admin-test-token" not in settings.pricing.model_dump_json()


def test_pricing_cannot_start_without_decisions_credentials():
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        load_settings(
            {
                "MEALIE_API_TOKEN": "test",
                "PRICING_ENABLED": "true",
                "PRICING_ADMIN_TOKEN": "pricing-admin-test-token",
            }
        )
