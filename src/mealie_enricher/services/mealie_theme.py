import asyncio
import logging
import re
import time
from collections.abc import Callable
from typing import Any

import httpx

from ..config import MealieSettings
from ..models import MealieTheme, MealieThemeColors

DEFAULT_COLORS = MealieThemeColors(
    primary="#D65108",
    accent="#007A99",
    secondary="#973542",
    success="#28A745",
    info="#1976D2",
    warning="#FF6D00",
    error="#EF5350",
)
DEFAULT_THEME = MealieTheme(light=DEFAULT_COLORS.model_copy(), dark=DEFAULT_COLORS.model_copy())
logger = logging.getLogger(__name__)


class MealieThemeClient:
    def __init__(
        self,
        settings: MealieSettings,
        http: httpx.AsyncClient,
        *,
        clock_ms: Callable[[], float] | None = None,
    ) -> None:
        self.settings, self.http = settings, http
        self.clock_ms = clock_ms or (lambda: time.time() * 1000)
        self.cached: MealieTheme | None = None
        self.expires_at = 0.0

    async def get_theme(self) -> MealieTheme:
        if self.cached is not None and self.clock_ms() < self.expires_at:
            return self.cached
        try:
            async with asyncio.timeout(self.settings.timeout_ms / 1000):
                response = await self.http.get(
                    self.settings.url.rstrip("/") + "/api/app/about/theme",
                    timeout=self.settings.timeout_ms / 1000,
                    follow_redirects=True,
                )
            response.raise_for_status()
            raw = response.json()

            def colors(mode: str) -> MealieThemeColors:
                values: dict[str, Any] = {}
                for key, fallback in DEFAULT_COLORS.model_dump().items():
                    value = raw.get(mode + key[0].upper() + key[1:])
                    value = value.strip() if isinstance(value, str) else ""
                    values[key] = (
                        value
                        if re.fullmatch(r"#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?", value)
                        else fallback
                    )
                return MealieThemeColors(**values)

            self.cached = MealieTheme(light=colors("light"), dark=colors("dark"))
            self.expires_at = self.clock_ms() + 7200000
        except Exception as error:
            logger.warning("Could not load Mealie theme, using default colors: %s", error)
            self.cached = DEFAULT_THEME
            self.expires_at = self.clock_ms() + 30000
        return self.cached
