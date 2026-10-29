import asyncio

from mealie_enricher.config import LlmSettings, OffSettings
from mealie_enricher.runtime.rate_limiter import RateLimiter
from tests.clock import Clock, flush


async def test_fixed_window_waits_in_seconds_and_limits_are_independent():
    clock = Clock()
    limiter = RateLimiter(
        OffSettings(search_rate_limit=2), LlmSettings(), clock_ms=clock.now, sleep=clock.sleep
    )
    await limiter.wait("search")
    await limiter.wait("search")
    pending = asyncio.create_task(limiter.wait("search"))
    await flush()
    await limiter.wait("product")
    await limiter.wait("llm")
    await clock.advance(1000)
    assert not pending.done()
    for _ in range(59):
        await clock.advance(1000)
    await pending
