"""Real acquisition counters, bounded checkpoints and safe progress reporting."""

import logging
import time
from typing import Any

from .state import PricingState

logger = logging.getLogger(__name__)


class PricingProgress:
    def __init__(self, state: PricingState) -> None:
        self.state = state
        self._saved_at = self._logged_at = 0.0
        if state.data.get("phase") == "interrupted" and state.data.get("progress"):
            state.data["progress"].setdefault("finished_at", time.time())

    def begin(self, stage: str) -> None:
        self.state.data["progress"] = {"started_at": time.time()}
        self.update(stage, 0, None, None)

    def update(
        self, stage: str, completed: int, total: int | None, current: str | None = None
    ) -> None:
        now = time.time()
        data = self.state.data.setdefault("progress", {"started_at": now})
        changed_stage = data.get("stage") != stage
        if changed_stage:
            data["stage_started_at"] = now
        data.update(
            stage=stage, completed=completed, total=total, current=current, last_activity_at=now
        )
        if stage == "products":
            data.update(downloaded_products=completed, total_products=total)
        if stage == "categories":
            data.update(downloaded_categories=completed, total_categories=total)
        boundary = changed_stage or completed == 1 or (total is not None and completed == total)
        if boundary or now - self._saved_at >= 5:
            self.state.save()
            self._saved_at = now
        if boundary or now - self._logged_at >= 30:
            logger.info(
                "Mercadona progress stage=%s completed=%s/%s current=%s",
                stage,
                completed,
                total if total is not None else "?",
                current or "-",
            )
            self._logged_at = now

    def finish(self) -> None:
        data = self.state.data.get("progress")
        if data:
            data["finished_at"] = time.time()
            self.state.save()

    def snapshot(self) -> dict[str, Any]:
        data = dict(self.state.data.get("progress", {}))
        now = time.time()
        completed, total = data.get("completed", 0), data.get("total")
        end = data.get("finished_at") or now
        started = data.get("started_at")
        stage_started = data.get("stage_started_at")
        activity = data.get("last_activity_at")
        percent = round(min(100, completed / total * 100), 1) if total else None
        eta = None
        if total and completed and stage_started and not data.get("finished_at"):
            eta = round(max(0, (total - completed) * (now - stage_started) / completed))
        data.update(
            completed=completed,
            total=total,
            percent=percent,
            elapsed_seconds=round(max(0, end - started), 1) if started else 0,
            seconds_since_activity=round(max(0, now - activity), 1) if activity else None,
            eta_seconds=eta,
        )
        return data
