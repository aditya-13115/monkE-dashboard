from __future__ import annotations

import hmac
import os

from fastapi import Header, HTTPException


def configured_admin_key() -> str:
    return os.getenv("MONKE_ADMIN_KEY", "").strip()


def admin_auth_enabled() -> bool:
    return bool(configured_admin_key())


def require_admin(x_admin_key: str | None = Header(default=None)) -> None:
    """Lightweight prototype admin boundary.

    Keep MONKE_ADMIN_KEY server-side. The browser stores the key only for the
    current tab/session. If the variable is not configured, local development
    remains backwards-compatible and the internal dashboard is open.
    """
    expected = configured_admin_key()
    if not expected:
        return
    if not x_admin_key or not hmac.compare_digest(x_admin_key, expected):
        raise HTTPException(status_code=401, detail="Admin authentication required.")
