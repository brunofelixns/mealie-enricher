import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Literal

from ..config import LlmSettings, OffSettings

RateLimitType = Literal["search", "product", "llm"]


class RateLimiter:
    def __init__(
        self,
        off: OffSettings,
        llm: LlmSettings,
        *,
        clock_ms: Callable[[], float] | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.limits = {
            "search": off.search_rate_limit,
            "product": off.product_rate_limit,
            "llm": llm.rate_limit,
        }
        self.clock_ms = clock_ms or (lambda: time.monotonic() * 1000)
        self.sleep = sleep
        self.windows: dict[str, tuple[float, int]] = {}
        self.lock = asyncio.Lock()

    async def wait(self, kind: RateLimitType) -> None:
        while True:
            async with self.lock:
                now = self.clock_ms()
                expiry, used = self.windows.get(kind, (now + 60000, 0))
                if now >= expiry:
                    expiry, used = now + 60000, 0
                if used < self.limits[kind]:
                    self.windows[kind] = expiry, used + 1
                    return
            await self.sleep(1)
