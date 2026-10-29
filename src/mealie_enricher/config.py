import math
import os
import re
from collections.abc import Mapping

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from .models import WireModel, camel_case


class MealieSettings(WireModel):
    url: str = "http://mealie:9000"
    api_token: str = ""
    timeout_ms: float = 30000


class OffSettings(WireModel):
    base_url: str = "https://world.openfoodfacts.org"
    search_base_url: str = "https://search.openfoodfacts.org"
    language: str = "de"
    search_rate_limit: float = 10
    product_rate_limit: float = 15
    cache_ttl_ms: float = 86400000
    max_retries: float = 3
    retry_backoff_ms: float = 500
    user_agent: str = "mealie-calorie-estimator/1.12.3 (mail@timo-reymann.de)"


class LlmSettings(WireModel):
    enabled: bool = False
    base_url: str = "https://api.mistral.ai/v1"
    endpoint_url: str = "/chat/completions"
    api_key: str = ""
    model: str = "mistral-small-latest"
    rate_limit: float = 30
    temperature: float = 0.1
    max_tokens_grams: float = 10
    max_tokens_nutrients: float = 200


class EstimateSettings(WireModel):
    strategy: str = "all"
    tag: str = "estimate"


class EventSettings(WireModel):
    debounce_ms: float = 2000


class CacheSettings(WireModel):
    db_path: str = "data/cache.db"


class HistorySettings(WireModel):
    recipe_url_template: str = ""
    seed_dev_data: bool = False
    max_entries: float = 200


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        alias_generator=camel_case,
        populate_by_name=True,
        extra="ignore",
        env_prefix="__MEALIE_INTERNAL_",
    )
    port: float = 8000
    mealie: MealieSettings = Field(default_factory=MealieSettings)
    off: OffSettings = Field(default_factory=OffSettings, alias="openFoodFacts")
    llm: LlmSettings = Field(default_factory=LlmSettings)
    estimate: EstimateSettings = Field(default_factory=EstimateSettings)
    events: EventSettings = Field(default_factory=EventSettings)
    cache: CacheSettings = Field(default_factory=CacheSettings)
    history: HistorySettings = Field(default_factory=HistorySettings)
    log_level: str = "info"
    token_overrides: dict[str, str] = Field(default_factory=dict, exclude=True)


def _parse_int(value: str) -> float:
    match = re.match(r"^[+-]?\d+", value.strip(), flags=re.ASCII)
    return float(int(match[0])) if match else math.nan


def _parse_float(value: str) -> float:
    match = re.match(r"^[+-]?(?:Infinity|(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)", value.strip())
    return float(match[0]) if match else math.nan


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    values = dict(os.environ if env is None else env)

    def value(name: str, default: str = "") -> str:
        return values.get(name) or default

    def integer(name: str, default: int) -> float:
        return _parse_int(value(name, str(default)))

    tokens = {key: val for key, val in values.items() if key.startswith("MEALIE_API_TOKEN_")}
    if not value("MEALIE_API_TOKEN") and not tokens:
        raise ValueError(
            "No Mealie API token configured. Set MEALIE_API_TOKEN or at least one "
            "MEALIE_API_TOKEN_<HOUSEHOLD_ID> environment variable."
        )
    mealie = MealieSettings(
        url=value("MEALIE_URL", "http://mealie:9000"),
        api_token=value("MEALIE_API_TOKEN"),
        timeout_ms=integer("MEALIE_TIMEOUT_MS", 30000),
    )
    off = OffSettings(
        base_url=value("OFF_BASE_URL", "https://world.openfoodfacts.org"),
        search_base_url=value("OFF_SEARCH_BASE_URL", "https://search.openfoodfacts.org"),
        language=value("OFF_LANGUAGE", "de"),
        search_rate_limit=integer("OFF_SEARCH_RATE_LIMIT", 10),
        product_rate_limit=integer("OFF_PRODUCT_RATE_LIMIT", 15),
        cache_ttl_ms=integer("OFF_CACHE_TTL", 86400) * 1000,
        max_retries=integer("OFF_MAX_RETRIES", 3),
        retry_backoff_ms=integer("OFF_RETRY_BACKOFF_MS", 500),
        user_agent=value("OFF_USER_AGENT", OffSettings().user_agent),
    )
    llm = LlmSettings(
        enabled=value("LLM_ENABLED", "false").lower() == "true",
        base_url=value("LLM_BASE_URL", "https://api.mistral.ai/v1"),
        endpoint_url=value("LLM_ENDPOINT_URL", "/chat/completions"),
        api_key=value("LLM_API_KEY"),
        model=value("LLM_MODEL", "mistral-small-latest"),
        rate_limit=integer("LLM_RATE_LIMIT", 30),
        temperature=_parse_float(value("LLM_TEMPERATURE", "0.1")),
        max_tokens_grams=integer("LLM_MAX_TOKENS_GRAMS", 10),
        max_tokens_nutrients=integer("LLM_MAX_TOKENS_NUTRIENTS", 200),
    )
    return Settings(
        port=integer("PORT", 8000),
        mealie=mealie,
        openFoodFacts=off,
        llm=llm,
        estimate=EstimateSettings(
            strategy=value("ESTIMATE_STRATEGY", "all"), tag=value("ESTIMATE_TAG", "estimate")
        ),
        events=EventSettings(debounce_ms=integer("EVENT_DEBOUNCE_MS", 2000)),
        cache=CacheSettings(db_path=value("CACHE_DB_PATH", "data/cache.db")),
        history=HistorySettings(
            recipe_url_template=value("MEALIE_RECIPE_URL_TEMPLATE", mealie.url + "/recipe/{slug}"),
            seed_dev_data=value("DEV_SEED_HISTORY", "false").lower() == "true",
            max_entries=integer("HISTORY_MAX_ENTRIES", 200),
        ),
        log_level=value("LOG_LEVEL", "info"),
        token_overrides=tokens,
    )


def get_mealie_token(settings: Settings, household_id: str | None = None) -> str:
    if household_id:
        key = "MEALIE_API_TOKEN_" + re.sub(r"\W", "_", household_id, flags=re.ASCII)
        if settings.token_overrides.get(key):
            return settings.token_overrides[key]
    if settings.mealie.api_token:
        return settings.mealie.api_token
    return next(iter(settings.token_overrides.values()), "")
