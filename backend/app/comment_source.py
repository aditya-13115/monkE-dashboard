from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import httpx

BASE_DIR = Path(__file__).resolve().parents[2]
COMMENTS_FILE = BASE_DIR / "data" / "comments.json"


class CommentsNotConfiguredError(RuntimeError):
    pass


def _load_local_comments(post_url: str) -> list[dict[str, Any]]:
    if not COMMENTS_FILE.exists():
        return []

    try:
        data = json.loads(COMMENTS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Could not read {COMMENTS_FILE.name}: {exc}") from exc

    if isinstance(data, dict):
        rows = data.get(post_url, [])
    else:
        rows = data

    if not isinstance(rows, list):
        return []

    return rows


def _meta_configured() -> bool:
    return bool(
        os.getenv("META_ACCESS_TOKEN")
        and os.getenv("META_IG_USER_ID")
    )


async def _fetch_comments_from_meta(
    username: str,
    post_url: str,
) -> list[dict[str, Any]]:
    """
    Fetch comments for a creator/business account's media through the
    Instagram Graph API Business Discovery flow.

    This requires an authenticated Meta/Instagram setup with access to the
    relevant creator/business accounts. It is intentionally server-side.
    """

    access_token = os.environ["META_ACCESS_TOKEN"]
    ig_user_id = os.environ["META_IG_USER_ID"]
    version = os.getenv("META_GRAPH_VERSION", "v23.0")
    base = f"https://graph.facebook.com/{version}"

    fields = (
        "business_discovery.username("
        + username.replace("@", "")
        + "){media.limit(100){id,permalink}}"
    )

    async with httpx.AsyncClient(timeout=20.0) as client:
        discovery = await client.get(
            f"{base}/{ig_user_id}",
            params={
                "fields": fields,
                "access_token": access_token,
            },
        )
        discovery.raise_for_status()
        payload = discovery.json()

        media = (
            payload.get("business_discovery", {})
            .get("media", {})
            .get("data", [])
        )

        matched_media = None
        normalized_post = post_url.rstrip("/")

        for item in media:
            permalink = str(item.get("permalink", "")).rstrip("/")
            if permalink == normalized_post:
                matched_media = item
                break

        if not matched_media:
            return []

        comments_response = await client.get(
            f"{base}/{matched_media['id']}/comments",
            params={
                "fields": "id,text,like_count,username,timestamp",
                "limit": 100,
                "access_token": access_token,
            },
        )
        comments_response.raise_for_status()
        comments_payload = comments_response.json()

    rows = []
    for item in comments_payload.get("data", []):
        text = str(item.get("text", "")).strip()
        if not text:
            continue
        rows.append(
            {
                "comment": text,
                "likes": int(item.get("like_count", 0) or 0),
                "post_url": post_url,
                "username": str(item.get("username", "") or ""),
            }
        )

    return rows


async def get_comments_for_post(
    *,
    username: str,
    post_url: str,
) -> list[dict[str, Any]]:
    # Local JSON is useful for development/testing and does not require API auth.
    local = _load_local_comments(post_url)
    if local:
        return local

    if _meta_configured():
        return await _fetch_comments_from_meta(
            username=username,
            post_url=post_url,
        )

    raise CommentsNotConfiguredError(
        "No Instagram comment source is connected. "
        "Set META_ACCESS_TOKEN and META_IG_USER_ID for live comments, "
        "or add data/comments.json for local testing."
    )
