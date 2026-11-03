"""Durable history with bounded in-process views and explicit async write boundaries."""

import asyncio
from collections.abc import Callable

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine

from ..models import ExecutionRecord
from .database import conflict_insert
from .history import ExecutionHistory
from .schema import execution_history


class SqlExecutionHistory(ExecutionHistory):
    def __init__(
        self,
        engine: AsyncEngine,
        max_entries: int = 200,
        *,
        clock_ms: Callable[[], float] | None = None,
        retention_days: int = 0,
    ) -> None:
        super().__init__(max_entries, clock_ms=clock_ms)
        self.engine = engine
        self.retention_days = retention_days
        self.pending: dict[str, ExecutionRecord] = {}
        self.active: dict[str, ExecutionRecord] = {}
        self._write_lock = asyncio.Lock()

    @classmethod
    async def open(
        cls,
        engine: AsyncEngine,
        max_entries: int = 200,
        *,
        clock_ms: Callable[[], float] | None = None,
        retention_days: int = 0,
    ) -> "SqlExecutionHistory":
        history = cls(engine, max_entries, clock_ms=clock_ms, retention_days=retention_days)
        async with engine.connect() as connection:
            rows = await connection.execute(
                select(execution_history.c.payload).where(execution_history.c.status == "running")
            )
            unfinished = list(rows.scalars())
        for payload in unfinished:
            record = ExecutionRecord.model_validate_json(payload)
            record.status = "error"
            record.error = "Execution interrupted by application restart; not automatically retried"
            record.finished_at = record.updated_at = int(history.clock_ms())
            record.duration_ms = max(0, record.finished_at - record.started_at)
            history._record_changed(record)
        await history.flush()
        for record in reversed(await history.fetch_history()):
            history.records[record.id] = record
            history.expires[record.id] = float("inf")
        return history

    def _purge(self) -> None:
        # Persistent history has its own optional retention, never the legacy 24-hour TTL.
        return

    def _lookup(self, record_id: str) -> ExecutionRecord | None:
        return self.records.get(record_id) or self.active.get(record_id)

    def _record_changed(self, record: ExecutionRecord) -> None:
        self.pending[record.id] = record.model_copy(deep=True)
        if record.status == "running":
            self.active[record.id] = record
        else:
            self.active.pop(record.id, None)

    async def flush(self) -> None:
        async with self._write_lock:
            snapshots = list(self.pending.items())
            if not snapshots:
                return
            async with self.engine.begin() as connection:
                for _, record in snapshots:
                    values = {
                        "id": record.id,
                        "started_at": record.started_at,
                        "updated_at": record.updated_at,
                        "slug": record.slug,
                        "status": record.status,
                        "payload": record.model_dump_json(by_alias=True),
                    }
                    statement = conflict_insert(self.engine, execution_history).values(**values)
                    await connection.execute(
                        statement.on_conflict_do_update(
                            index_elements=[execution_history.c.id], set_=values
                        )
                    )
            for record_id, snapshot in snapshots:
                if self.pending.get(record_id) is snapshot:
                    self.pending.pop(record_id)

    async def fetch_history(
        self, since: float | None = None, *, limit: int | None = None, offset: int = 0
    ) -> list[ExecutionRecord]:
        await self.flush()
        async with self.engine.begin() as connection:
            if self.retention_days:
                cutoff = self.clock_ms() - self.retention_days * 86400000
                await connection.execute(
                    delete(execution_history).where(
                        execution_history.c.updated_at < cutoff,
                        execution_history.c.status != "running",
                    )
                )
            statement = select(execution_history.c.payload)
            if since is not None:
                statement = statement.where(execution_history.c.updated_at > since)
            rows = await connection.execute(
                statement.order_by(
                    execution_history.c.started_at.desc(), execution_history.c.id.desc()
                )
                # Pollers advance their watermark after each response: without an
                # explicit limit they must receive every delta, including older jobs.
                .limit(limit if limit is not None else self.max_entries if since is None else None)
                .offset(offset)
            )
            return [ExecutionRecord.model_validate_json(payload) for payload in rows.scalars()]
