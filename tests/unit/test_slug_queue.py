import asyncio

from mealie_enricher.runtime.slug_queue import SlugQueue
from tests.clock import Clock, flush


async def test_debounce_restarts_and_each_key_runs_once_in_insertion_order():
    clock = Clock()
    queue = SlugQueue(100, sleep=clock.sleep)
    order = []

    async def run(name):
        order.append(name)

    pending = [
        queue.run("same", "webhook", lambda: run("webhook")),
        queue.run("same", "estimate", lambda: run("estimate")),
        queue.run("same", "webhook", lambda: run("duplicate")),
    ]
    await flush()
    await clock.advance(60)
    pending.append(queue.run("same", "webhook", lambda: run("late")))
    await flush()
    await clock.advance(60)
    assert order == []
    await clock.advance(40)
    await asyncio.gather(*pending)
    assert order == ["webhook", "estimate"]
    await queue.close()


async def test_same_slug_is_serial_and_another_slug_can_run_concurrently():
    queue = SlugQueue()
    gate = asyncio.Event()
    order = []

    async def first():
        order.append("first-start")
        await gate.wait()
        order.append("first-end")

    async def second():
        order.append("second")

    async def other():
        order.append("other")

    pending = [queue.run_now("a", first), queue.run_now("a", second), queue.run_now("b", other)]
    await flush()
    assert order == ["first-start", "other"]
    gate.set()
    await asyncio.gather(*pending)
    assert order == ["first-start", "other", "first-end", "second"]
    await queue.close()


async def test_failure_rejects_all_waiters_and_next_task_still_runs():
    clock = Clock()
    queue = SlugQueue(100, sleep=clock.sleep)

    async def fail():
        raise ValueError("boom")

    first = queue.run("same", "webhook", fail)
    second = queue.run("same", "webhook", fail)
    combined = asyncio.gather(first, second, return_exceptions=True)
    await flush()
    await clock.advance(100)
    failures = await combined
    assert [str(error) for error in failures] == ["boom", "boom"]
    ran = []

    async def success():
        ran.append(True)

    await queue.run_now("same", success)
    assert ran == [True]
    await queue.close()
