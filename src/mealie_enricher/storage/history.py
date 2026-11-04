import time
import uuid
from collections import OrderedDict
from collections.abc import Callable

from ..models import ExecutionEstimate, ExecutionRecord, ExecutionStatus, ExecutionTrigger


class _Handle:
    def __init__(self, history: "ExecutionHistory", record_id: str) -> None:
        self.history, self.record_id, self.finished = history, record_id, False

    def _get(self) -> ExecutionRecord | None:
        if self.finished:
            return None
        self.history._purge()
        return self.history._lookup(self.record_id)

    def _touch(self, record: ExecutionRecord) -> None:
        record.updated_at = int(self.history.clock_ms())
        if self.record_id in self.history.records:
            self.history.records.move_to_end(self.record_id)
            self.history.expires[self.record_id] = self.history.clock_ms() + 86400000
        self.history._record_changed(record)

    def set_recipe(self, name: str, household_id: str | None) -> None:
        record = self._get()
        if record:
            record.recipe_name, record.household_id = name, household_id
            self._touch(record)

    def complete(
        self, status: ExecutionStatus, changes: list[str], estimate: ExecutionEstimate | None = None
    ) -> None:
        record = self._get()
        self.finished = True
        if record:
            record.status, record.changes, record.estimate = status, changes, estimate
            record.finished_at = int(self.history.clock_ms())
            record.duration_ms = record.finished_at - record.started_at
            self._touch(record)

    def fail(self, error: Exception | str) -> None:
        record = self._get()
        self.finished = True
        if record:
            message = str(error) or type(error).__name__
            record.status = "error"
            record.error = message.encode("utf-16-le", "surrogatepass")[:600].decode(
                "utf-16-le", "surrogatepass"
            )
            record.finished_at = int(self.history.clock_ms())
            record.duration_ms = record.finished_at - record.started_at
            self._touch(record)


class ExecutionHistory:
    def __init__(
        self, max_entries: int = 200, *, clock_ms: Callable[[], float] | None = None
    ) -> None:
        self.max_entries = max_entries
        self.clock_ms = clock_ms or (lambda: time.time() * 1000)
        self.records: OrderedDict[str, ExecutionRecord] = OrderedDict()
        self.expires: dict[str, float] = {}

    def _lookup(self, record_id: str) -> ExecutionRecord | None:
        return self.records.get(record_id)

    def _record_changed(self, record: ExecutionRecord) -> None:
        pass

    async def flush(self) -> None:
        """Persistence boundary; the legacy memory-only history has no writes."""

    async def fetch_history(
        self, since: float | None = None, *, limit: int | None = None, offset: int = 0
    ) -> list[ExecutionRecord]:
        records = self.get_history(since)
        return records[offset : offset + (limit if limit is not None else self.max_entries)]

    def _purge(self) -> None:
        for key in list(self.records):
            if self.clock_ms() > self.expires[key]:
                self.records.pop(key)
                self.expires.pop(key)

    def record_start(self, trigger: ExecutionTrigger, slug: str) -> _Handle:
        self._purge()
        record_id, now = str(uuid.uuid4()), int(self.clock_ms())
        self.records[record_id] = ExecutionRecord(
            id=record_id, started_at=now, updated_at=now, trigger=trigger, slug=slug
        )
        self.expires[record_id] = self.clock_ms() + 86400000
        self._record_changed(self.records[record_id])
        while len(self.records) > self.max_entries:
            key, _ = self.records.popitem(last=False)
            self.expires.pop(key)
        return _Handle(self, record_id)

    def get_history(self, since: float | None = None) -> list[ExecutionRecord]:
        self._purge()
        return sorted(
            (
                record
                for record in reversed(self.records.values())
                if since is None or record.updated_at > since
            ),
            key=lambda record: record.started_at,
            reverse=True,
        )

    def seed_record(self, record: ExecutionRecord) -> None:
        self._purge()
        self.records[record.id] = record
        self.expires[record.id] = self.clock_ms() + 86400000
        self._record_changed(record)
        while len(self.records) > self.max_entries:
            key, _ = self.records.popitem(last=False)
            self.expires.pop(key)
