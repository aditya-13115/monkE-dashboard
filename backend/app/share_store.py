from __future__ import annotations

import secrets
import time
from pathlib import Path
from typing import Any

from .cache_store import JsonCacheStore


class ShareLinkError(RuntimeError):
    pass


class ShareLinkStore:
    def __init__(self, path: Path) -> None:
        self.store = JsonCacheStore(path)

    def _payload(self) -> dict[str, Any]:
        payload = self.store.get("links")
        return payload if isinstance(payload, dict) else {}

    def _write(self, payload: dict[str, Any]) -> None:
        self.store.set("links", payload)

    def create(self, brand: str, campaign_ids: list[str], label: str = "") -> dict[str, Any]:
        token = secrets.token_urlsafe(24)
        payload = self._payload()
        while token in payload:
            token = secrets.token_urlsafe(24)
        item = {
            "token": token,
            "brand": brand,
            "campaignIds": campaign_ids,
            "label": label.strip(),
            "createdAt": time.time(),
        }
        payload[token] = item
        self._write(payload)
        return item

    def get(self, token: str) -> dict[str, Any] | None:
        item = self._payload().get(token)
        return item if isinstance(item, dict) else None

    def list(self) -> list[dict[str, Any]]:
        return sorted(
            [x for x in self._payload().values() if isinstance(x, dict)],
            key=lambda x: float(x.get("createdAt", 0)),
            reverse=True,
        )

    def delete(self, token: str) -> bool:
        payload = self._payload()
        if token not in payload:
            return False
        del payload[token]
        self._write(payload)
        return True
