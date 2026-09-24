from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Any


class JsonCacheStore:
    """Small atomic JSON cache suitable for this single-process prototype.

    The cache is deliberately human-readable so the prototype can be inspected
    and backed up easily. Writes use an atomic replace to avoid partially written
    JSON if the development server reloads while a cache write is happening.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def _read(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            with self.path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
            return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError, TypeError):
            return {}

    def _write(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(
            prefix=f".{self.path.stem}-",
            suffix=".tmp",
            dir=self.path.parent,
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(
                    data,
                    handle,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, self.path)
        finally:
            try:
                os.unlink(temp_name)
            except FileNotFoundError:
                pass

    def get_entry(self, key: str) -> dict[str, Any] | None:
        with self._lock:
            raw = self._read()
            entry = raw.get(key)
            if not isinstance(entry, dict) or "data" not in entry:
                return None
            return entry

    def get(self, key: str) -> Any | None:
        entry = self.get_entry(key)
        return entry.get("data") if entry else None

    def age_seconds(self, key: str) -> float | None:
        entry = self.get_entry(key)
        if not entry:
            return None
        try:
            return max(0.0, time.time() - float(entry.get("savedAt", 0)))
        except (TypeError, ValueError):
            return None

    def set(self, key: str, data: Any) -> None:
        with self._lock:
            raw = self._read()
            raw[key] = {
                "savedAt": time.time(),
                "data": data,
            }
            self._write(raw)

    def delete(self, key: str) -> None:
        with self._lock:
            raw = self._read()
            if key in raw:
                del raw[key]
                self._write(raw)

    def items(self) -> list[tuple[str, dict[str, Any]]]:
        with self._lock:
            raw = self._read()
            return [
                (key, entry)
                for key, entry in raw.items()
                if isinstance(entry, dict) and "data" in entry
            ]

    def clear(self) -> None:
        with self._lock:
            self._write({})
