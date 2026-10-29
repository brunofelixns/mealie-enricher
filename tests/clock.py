import asyncio


async def flush() -> None:
    for _ in range(12):
        await asyncio.sleep(0)


class Clock:
    def __init__(self, milliseconds: float = 0) -> None:
        self.ms = milliseconds
        self.waiters: list[tuple[float, asyncio.Future[None]]] = []

    def now(self) -> float:
        return self.ms

    async def sleep(self, seconds: float) -> None:
        future: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        self.waiters.append((self.ms + seconds * 1000, future))
        await future

    async def advance(self, milliseconds: float) -> None:
        self.ms += milliseconds
        remaining = []
        for due, future in self.waiters:
            if due <= self.ms and not future.done():
                future.set_result(None)
            elif not future.done():
                remaining.append((due, future))
        self.waiters = remaining
        await flush()
