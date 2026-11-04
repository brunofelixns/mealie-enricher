"""Durable control metadata and a single writer per local data directory."""

import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any


class PricingOwner:
    def __init__(self, directory: str) -> None:
        path = Path(directory)
        path.mkdir(parents=True, exist_ok=True)
        self._file = (path / ".pricing.lock").open("a+b")
        try:
            if sys.platform == "win32":
                import msvcrt

                if self._file.seek(0, 2) == 0:
                    self._file.write(b"0")
                    self._file.flush()
                self._file.seek(0)
                msvcrt.locking(self._file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            self._file.close()
            raise RuntimeError("Another pricing process owns this data directory") from error

    def close(self) -> None:
        self._file.close()


class PricingState:
    def __init__(self, directory: str) -> None:
        self.path = Path(directory) / "state.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data: dict[str, Any] = {
            "schema_version": 1,
            "next_run": None,
            "running": False,
            "phase": "idle",
            "pending_refresh": False,
            "last_success": None,
            "last_attempt": None,
            "last_error": None,
            "selections": {},
        }
        if self.path.exists():
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(loaded, dict) or loaded.get("schema_version") != 1:
                raise ValueError("Invalid pricing state schema")
            self.data.update(loaded)
        if self.data["running"]:
            self.data.update(running=False, phase="interrupted", last_error="interrupted")
            self.save()

    def save(self) -> None:
        temporary = self.path.with_name(f".state-{uuid.uuid4().hex}.tmp")
        try:
            with temporary.open("w", encoding="utf-8") as stream:
                json.dump(self.data, stream, ensure_ascii=False, allow_nan=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            temporary.unlink(missing_ok=True)
