import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

Task = Callable[[], Awaitable[None]]


@dataclass
class _Burst:
    timer: asyncio.Task[None] | None = None
    waiters: dict[str, list[tuple[Task, asyncio.Future[None]]]] = field(default_factory=dict)


class SlugQueue:
    def __init__(
        self, debounce_ms: float = 0, *, sleep: Callable[[float], Awaitable[None]] = asyncio.sleep
    ) -> None:
        self.debounce_ms, self.sleep = debounce_ms, sleep
        self.chains: dict[str, asyncio.Task[None]] = {}
        self.bursts: dict[str, _Burst] = {}
        self.background: set[asyncio.Task[None]] = set()

    def run(self, slug: str, key: str, task: Task) -> asyncio.Future[None]:
        if self.debounce_ms <= 0:
            return self.run_now(slug, task)
        future: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        burst = self.bursts.setdefault(slug, _Burst())
        if burst.timer:
            burst.timer.cancel()
        burst.waiters.setdefault(key, []).append((task, future))
        burst.timer = asyncio.create_task(self._flush_after(slug, burst))
        return future

    async def _flush_after(self, slug: str, burst: _Burst) -> None:
        await self.sleep(self.debounce_ms / 1000)
        if self.bursts.get(slug) is not burst:
            return
        self.bursts.pop(slug)
        for waiters in burst.waiters.values():
            run = self.run_now(slug, waiters[0][0])
            settled = asyncio.create_task(self._settle(run, waiters))
            self.background.add(settled)
            settled.add_done_callback(self.background.discard)

    async def _settle(
        self, run: asyncio.Task[None], waiters: list[tuple[Task, asyncio.Future[None]]]
    ) -> None:
        try:
            await run
        except Exception as error:
            for _, future in waiters:
                if not future.done():
                    future.set_exception(error)
        else:
            for _, future in waiters:
                if not future.done():
                    future.set_result(None)

    def run_now(self, slug: str, task: Task) -> asyncio.Task[None]:
        previous = self.chains.get(slug)

        async def execute() -> None:
            if previous:
                try:
                    await previous
                except Exception:
                    pass
            try:
                await task()
            finally:
                if self.chains.get(slug) is asyncio.current_task():
                    self.chains.pop(slug, None)

        run = asyncio.create_task(execute())
        self.chains[slug] = run
        return run

    async def close(self) -> None:
        for burst in self.bursts.values():
            if burst.timer:
                burst.timer.cancel()
            for waiters in burst.waiters.values():
                for _, future in waiters:
                    future.cancel()
        self.bursts.clear()
        await asyncio.gather(*self.chains.values(), *self.background, return_exceptions=True)
