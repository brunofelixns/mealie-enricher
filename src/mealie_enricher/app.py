import asyncio
import time
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from alembic.config import Config
from fastapi import FastAPI, Request
from sqlalchemy.engine import URL
from starlette.exceptions import HTTPException
from starlette.responses import Response

from alembic import command

from .agents.estimator_agent import AgentLlmRunner
from .clients.mealie import MealieClient
from .clients.open_food_facts import OffClient
from .config import Settings, load_settings
from .routes import backfill, estimate, history, webhook
from .routes.common import LegacyJSONResponse, PayloadError, internal_error
from .runtime.rate_limiter import RateLimiter
from .runtime.slug_queue import SlugQueue
from .runtime.tasks import TaskRegistry
from .services.estimator import Estimator
from .services.llm_estimator import LlmEstimator
from .services.mealie_theme import MealieThemeClient
from .services.processing import ProcessingService
from .services.tagging import TaggingService
from .storage.cache import SqliteCache
from .storage.dev_seed import seed_dev_history
from .storage.history import ExecutionHistory


class _Cors:
    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope["headers"])
        if scope["method"] == "OPTIONS":
            if b"origin" not in headers or b"access-control-request-method" not in headers:
                response = Response(
                    "Invalid Preflight Request",
                    status_code=400,
                    headers={"content-type": "text/plain", "access-control-allow-origin": "*"},
                )
            else:
                extra = {
                    "access-control-allow-origin": "*",
                    "access-control-allow-methods": "GET,HEAD,POST",
                    "vary": "Access-Control-Request-Headers",
                }
                if b"access-control-request-headers" in headers:
                    extra["access-control-allow-headers"] = headers[
                        b"access-control-request-headers"
                    ].decode()
                response = Response(status_code=204, headers=extra)
            await response(scope, receive, send)
            return

        async def wrapped(message: Any) -> None:
            if message["type"] == "http.response.start":
                message["headers"].append((b"access-control-allow-origin", b"*"))
            if scope["method"] == "HEAD" and message["type"] == "http.response.body":
                message["body"] = b""
            await send(message)

        child_scope = {**scope, "method": "GET"} if scope["method"] == "HEAD" else scope
        await self.app(child_scope, receive, wrapped)


def _migrate_cache(path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    location = Path(__file__).resolve().parents[2] / "alembic.ini"
    if not location.exists():
        location = Path.cwd() / "alembic.ini"
    config = Config(str(location))
    config.set_main_option(
        "sqlalchemy.url", URL.create("sqlite", database=path).render_as_string().replace("%", "%%")
    )
    command.upgrade(config, "head")


def create_app(
    settings: Settings | None = None,
    *,
    http: httpx.AsyncClient | None = None,
    clock_ms: Callable[[], float] | None = None,
) -> FastAPI:
    settings = settings if settings is not None else load_settings()
    now = clock_ms or (lambda: time.time() * 1000)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        await asyncio.to_thread(_migrate_cache, settings.cache.db_path)
        cache = await SqliteCache.open(
            settings.cache.db_path, settings.off.cache_ttl_ms, clock_ms=now
        )
        client = (
            http
            if http is not None
            else httpx.AsyncClient(
                timeout=None,
                trust_env=False,
                limits=httpx.Limits(max_connections=None, max_keepalive_connections=None),
            )
        )
        try:
            limiter = RateLimiter(settings.off, settings.llm)
            queue = SlugQueue(settings.events.debounce_ms)
            events = ExecutionHistory(int(settings.history.max_entries), clock_ms=now)
            seed_dev_history(settings.history, events)
            tasks = TaskRegistry()
            off = OffClient(settings.off, client, cache, limiter)
            llm = LlmEstimator(settings.llm, AgentLlmRunner(settings.llm, client), cache, limiter)
            mealie = MealieClient(settings, client)
            tagging = TaggingService(mealie, Estimator(off, llm))
            app.state.settings, app.state.http, app.state.cache = settings, client, cache
            app.state.history, app.state.tasks, app.state.queue = events, tasks, queue
            app.state.theme = MealieThemeClient(settings.mealie, client, clock_ms=now)
            app.state.processing = ProcessingService(settings, mealie, tagging, queue, events)
            yield
        finally:
            if hasattr(app.state, "tasks"):
                await app.state.tasks.close()
                await app.state.queue.close()
            await cache.close()
            if http is None:
                await client.aclose()

    app = FastAPI(
        lifespan=lifespan,
        default_response_class=LegacyJSONResponse,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        redirect_slashes=False,
    )
    app.add_middleware(_Cors)
    for router in (webhook.router, estimate.router, backfill.router, history.router):
        app.include_router(router)

    @app.get("/health")
    async def health() -> LegacyJSONResponse:
        timestamp = (
            datetime.fromtimestamp(now() / 1000, timezone.utc)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z")
        )
        return LegacyJSONResponse({"status": "ok", "timestamp": timestamp})

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, error: HTTPException) -> LegacyJSONResponse:
        if error.status_code in {404, 405}:
            path = request.url.path + ("?" + request.url.query if request.url.query else "")
            return LegacyJSONResponse(
                {
                    "message": f"Route {request.method}:{path} not found",
                    "error": "Not Found",
                    "statusCode": 404,
                },
                status_code=404,
            )
        return LegacyJSONResponse({"error": error.detail}, status_code=error.status_code)

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, error: Exception) -> LegacyJSONResponse:
        return internal_error(str(error))

    @app.exception_handler(PayloadError)
    async def payload_error(request: Request, error: PayloadError) -> LegacyJSONResponse:
        return LegacyJSONResponse(
            {
                "statusCode": error.status,
                "code": error.code,
                "error": "Bad Request" if error.status == 400 else "Unsupported Media Type",
                "message": str(error),
            },
            status_code=error.status,
        )

    return app
