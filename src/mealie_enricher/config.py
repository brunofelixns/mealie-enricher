import math
import os
import re
from collections.abc import Mapping

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from .models import WireModel, camel_case
from .pricing.config import PricingSettings


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

    @property
    def uses_reasoning_tokens(self) -> bool:
        model = self.model.lower()
        return re.match(
            r"^(?:gpt-[56](?:[.-]|$)|o[134](?:-|$))", model
        ) is not None and not model.endswith("-chat-latest")


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
    retention_days: int = Field(default=0, ge=0, exclude=True)


class CatalogSettings(WireModel):
    enabled: bool = False
    db_path: str = "data/catalogs/catalogos.duckdb"


class DecisionSettings(WireModel):
    enabled: bool = False
    api_key: str = Field(default="", repr=False, exclude=True)
    model: str = "gpt-6-luna"
    timeout_seconds: float = Field(default=20, gt=0, le=120)
    min_confidence: float = Field(default=0.9, ge=0.5, le=1, allow_inf_nan=False)
    max_concurrency: int = Field(default=2, ge=1, le=16)


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
    database_url: str = Field(default="", repr=False, exclude=True)
    history: HistorySettings = Field(default_factory=HistorySettings)
    catalog: CatalogSettings = Field(default_factory=CatalogSettings, exclude=True)
    decisions: DecisionSettings = Field(default_factory=DecisionSettings, exclude=True)
    nova_enabled: bool = Field(default=False, exclude=True)
    pricing: PricingSettings = Field(default_factory=PricingSettings, exclude=True)
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
    llm_model = value("LLM_MODEL", "mistral-small-latest")
    reasoning_tokens = LlmSettings(model=llm_model).uses_reasoning_tokens
    llm = LlmSettings(
        enabled=value("LLM_ENABLED", "false").lower() == "true",
        base_url=value("LLM_BASE_URL", "https://api.mistral.ai/v1"),
        endpoint_url=value("LLM_ENDPOINT_URL", "/chat/completions"),
        api_key=value("LLM_API_KEY"),
        model=llm_model,
        rate_limit=integer("LLM_RATE_LIMIT", 30),
        temperature=_parse_float(value("LLM_TEMPERATURE", "0.1")),
        max_tokens_grams=integer("LLM_MAX_TOKENS_GRAMS", 1024 if reasoning_tokens else 10),
        max_tokens_nutrients=integer("LLM_MAX_TOKENS_NUTRIENTS", 2048 if reasoning_tokens else 200),
    )
    pricing = PricingSettings(
        enabled=value("PRICING_ENABLED", "false").lower() == "true",
        postal_code=value("MERCADONA_POSTAL_CODE", "27004"),
        data_dir=value("PRICING_DATA_DIR", "data/supermarkets"),
        sync_interval_hours=float(value("PRICING_SYNC_INTERVAL_HOURS", "168")),
        auto_sync=value("PRICING_AUTO_SYNC", "true").lower() == "true",
        request_delay_seconds=float(value("PRICING_REQUEST_DELAY_SECONDS", "2")),
        max_products=int(value("PRICING_MAX_PRODUCTS", "10000")),
        max_candidates=int(value("PRICING_MAX_CANDIDATES", "12")),
        max_decisions_per_run=int(value("PRICING_MAX_DECISIONS_PER_RUN", "500")),
        admin_token=value("PRICING_ADMIN_TOKEN"),
    )
    if pricing.enabled:
        if not value("DECISIONS_API_KEY", value("OPENAI_API_KEY")):
            raise ValueError("PRICING_ENABLED requires DECISIONS_API_KEY or OPENAI_API_KEY")
        if len(pricing.admin_token) < 16:
            raise ValueError("PRICING_ADMIN_TOKEN must contain at least 16 characters")
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
        database_url=value("DATABASE_URL"),
        history=HistorySettings(
            recipe_url_template=value("MEALIE_RECIPE_URL_TEMPLATE", mealie.url + "/recipe/{slug}"),
            seed_dev_data=value("DEV_SEED_HISTORY", "false").lower() == "true",
            max_entries=integer("HISTORY_MAX_ENTRIES", 200),
            retention_days=int(integer("HISTORY_RETENTION_DAYS", 0)),
        ),
        catalog=CatalogSettings(
            enabled=value("CATALOG_ENABLED", "false").lower() == "true",
            db_path=value("CATALOG_DB_PATH", "data/catalogs/catalogos.duckdb"),
        ),
        decisions=DecisionSettings(
            enabled=value("DECISIONS_ENABLED", "false").lower() == "true",
            api_key=value("DECISIONS_API_KEY", value("OPENAI_API_KEY")),
            model=value("DECISIONS_MODEL", "gpt-6-luna"),
            timeout_seconds=_parse_float(value("DECISIONS_TIMEOUT_SECONDS", "20")),
            min_confidence=_parse_float(value("DECISIONS_MIN_CONFIDENCE", "0.9")),
            max_concurrency=int(integer("DECISIONS_MAX_CONCURRENCY", 2)),
        ),
        nova_enabled=value("NOVA_ENABLED", "false").lower() == "true",
        pricing=pricing,
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
