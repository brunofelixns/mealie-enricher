from mealie_enricher.config import load_settings


def test_database_url_is_explicit_and_excluded_from_config_output():
    url = "postgresql://user:private-password@postgres/enricher"
    settings = load_settings({"MEALIE_API_TOKEN": "synthetic", "DATABASE_URL": url})
    assert settings.database_url == url
    assert "private-password" not in repr(settings)
    assert "database_url" not in settings.model_dump()
    assert load_settings({"MEALIE_API_TOKEN": "synthetic"}).database_url == ""


def test_persistent_history_has_no_retention_limit_by_default():
    settings = load_settings({"MEALIE_API_TOKEN": "synthetic"})
    assert settings.history.retention_days == 0
    settings = load_settings({"MEALIE_API_TOKEN": "synthetic", "HISTORY_RETENTION_DAYS": "90"})
    assert settings.history.retention_days == 90
