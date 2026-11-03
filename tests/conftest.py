import asyncio

import pytest

from mealie_enricher.storage.cache import SqliteCache


def pytest_asyncio_loop_factories():
    return {"selector": asyncio.SelectorEventLoop}


@pytest.fixture
async def cache(tmp_path):
    cache = await SqliteCache.open(str(tmp_path / "cache.db"), 86400000)
    try:
        yield cache
    finally:
        await cache.close()
