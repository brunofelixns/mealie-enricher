import asyncio
import logging
from collections.abc import Awaitable

logger = logging.getLogger(__name__)


class TaskRegistry:
    def __init__(self) -> None:
        self.pending: set[asyncio.Future[None]] = set()

    def start(self, task: Awaitable[None]) -> None:
        future = asyncio.ensure_future(task)
        self.pending.add(future)
        future.add_done_callback(self._done)

    def _done(self, future: asyncio.Future[None]) -> None:
        self.pending.discard(future)
        if not future.cancelled() and (error := future.exception()) is not None:
            logger.error("Background task failed: %s", error)

    async def close(self) -> None:
        for future in self.pending:
            future.cancel()
        await asyncio.gather(*self.pending, return_exceptions=True)
