from __future__ import annotations

from .instagram_web import fetch_comments


class InstagramFetchError(RuntimeError):
    """Raised when Instagram comments cannot be fetched."""


async def get_comments_for_post(
    *,
    username: str,
    post_url: str,
) -> list[dict]:
    _ = username
    try:
        comments = await fetch_comments(post_url, limit=100)
    except Exception as exc:
        raise InstagramFetchError(
            f"Instagram browser fetch failed: {exc}"
        ) from exc

    if not comments:
        raise InstagramFetchError(
            "Instagram opened the post, but no comments could be extracted. "
            "Check the saved Instagram login state and whether comments are visible."
        )
    return comments
