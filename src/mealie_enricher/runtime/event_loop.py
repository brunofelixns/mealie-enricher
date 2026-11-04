"""Psycopg async connections require a selector event loop on Windows."""

import asyncio
from collections.abc import Callable


def selector_loop_factory(use_subprocess: bool = False) -> Callable[[], asyncio.AbstractEventLoop]:
    return asyncio.SelectorEventLoop
