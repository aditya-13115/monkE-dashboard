from __future__ import annotations

import asyncio
import os
import re
from pathlib import Path
from typing import Any

from playwright.sync_api import (
    Browser,
    BrowserContext,
    Page,
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)


class InstagramWebError(RuntimeError):
    """Instagram browser extraction error."""


BASE_DIR = Path(__file__).resolve().parents[2]

PROFILE_DIR = Path(
    os.getenv(
        "INSTAGRAM_USER_DATA_DIR",
        "data/instagram_profile",
    )
)

if not PROFILE_DIR.is_absolute():
    PROFILE_DIR = (
        BASE_DIR / PROFILE_DIR
    ).resolve()

PROFILE_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

STORAGE_STATE_PATH = (
    PROFILE_DIR / "storage_state.json"
)


POST_RE = re.compile(
    r"(?:instagram\.com)/(?:p|reel|reels)/([^/?#]+)/?",
    re.IGNORECASE,
)


def _is_headless() -> bool:
    return (
        os.getenv(
            "INSTAGRAM_HEADLESS",
            "true",
        )
        .strip()
        .lower()
        not in {
            "false",
            "0",
            "no",
        }
    )


def _to_int(value: Any) -> int:

    if value is None:
        return 0

    if isinstance(value, bool):
        return int(value)

    if isinstance(
        value,
        (int, float),
    ):
        return max(
            0,
            int(value),
        )

    text = (
        str(value)
        .strip()
        .lower()
        .replace(",", "")
    )

    match = re.fullmatch(
        r"([\d.]+)\s*([kmb])?",
        text,
    )

    if not match:
        return 0

    try:
        number = float(
            match.group(1)
        )
    except ValueError:
        return 0

    suffix = match.group(2)

    if suffix == "k":
        number *= 1_000

    elif suffix == "m":
        number *= 1_000_000

    elif suffix == "b":
        number *= 1_000_000_000

    return int(number)


def _extract_meta(
    page: Page,
    prop: str,
) -> str:

    try:

        locator = page.locator(
            f'meta[property="{prop}"]'
        )

        if locator.count() > 0:

            return (
                locator.first
                .get_attribute(
                    "content"
                )
                or ""
            ).strip()

    except Exception:
        pass

    return ""


def _dismiss_popups(
    page: Page,
) -> None:

    labels = [
        "Not now",
        "Close",
        "Cancel",
        "Allow all cookies",
        "Only allow essential cookies",
        "Allow essential cookies",
    ]

    for label in labels:

        try:

            locator = page.get_by_role(
                "button",
                name=re.compile(
                    f"^{re.escape(label)}$",
                    re.IGNORECASE,
                ),
            )

            count = locator.count()

            for index in range(
                min(count, 3)
            ):

                try:

                    button = locator.nth(
                        index
                    )

                    if button.is_visible():

                        button.click(
                            timeout=1200
                        )

                        page.wait_for_timeout(
                            300
                        )

                except Exception:
                    continue

        except Exception:
            continue


def _page_body_text(
    page: Page,
) -> str:

    try:

        return page.locator(
            "body"
        ).inner_text(
            timeout=10000
        )

    except Exception:

        return ""


def _extract_visible_metrics(
    page: Page,
) -> dict[str, int]:

    text = _page_body_text(
        page
    )

    result = {
        "likes": 0,
        "comments": 0,
        "views": 0,
    }

    if not text:
        return result

    likes_match = re.search(
        r"([\d,.]+\s*[kmb]?)\s+likes?\b",
        text,
        re.IGNORECASE,
    )

    comments_match = re.search(
        r"([\d,.]+\s*[kmb]?)\s+comments?\b",
        text,
        re.IGNORECASE,
    )

    views_match = re.search(
        r"([\d,.]+\s*[kmb]?)\s+(?:views?|plays?)\b",
        text,
        re.IGNORECASE,
    )

    if likes_match:

        result["likes"] = _to_int(
            likes_match.group(1)
        )

    if comments_match:

        result["comments"] = _to_int(
            comments_match.group(1)
        )

    if views_match:

        result["views"] = _to_int(
            views_match.group(1)
        )

    return result


def _extract_body_comments(
    page: Page,
    post_url: str,
) -> list[dict[str, Any]]:

    text = _page_body_text(
        page
    )

    if not text:
        return []

    lines = [
        re.sub(
            r"\s+",
            " ",
            line.strip(),
        )
        for line in text.splitlines()
        if line.strip()
    ]

    timestamp_pattern = re.compile(
        r"""
        (?:
            \d+\s*[smhdwy]
            |
            \d+\s*
            (?:
                seconds?
                |
                minutes?
                |
                hours?
                |
                days?
                |
                weeks?
                |
                months?
                |
                years?
            )
            \s*ago
        )
        """,
        re.IGNORECASE | re.VERBOSE,
    )

    username_pattern = re.compile(
        r"@?[A-Za-z0-9._]{1,30}"
    )

    ignored = {
        "like",
        "likes",
        "reply",
        "replies",
        "follow",
        "following",
        "see translation",
        "translated",
        "edited",
        "more",
        "close",
        "cancel",
        "not now",
        "log in",
        "sign up",
        "login",
        "signup",
    }

    comments: list[
        dict[str, Any]
    ] = []

    seen: set[str] = set()

    index = 0

    while index < len(lines):

        current = lines[index]

        if not username_pattern.fullmatch(
            current
        ):

            index += 1
            continue

        username = (
            current
            .lstrip("@")
            .strip()
        )

        if username.lower() in ignored:

            index += 1
            continue

        if index + 1 >= len(lines):

            index += 1
            continue

        timestamp = lines[index + 1]

        if not timestamp_pattern.fullmatch(
            timestamp
        ):

            index += 1
            continue

        comment_parts: list[str] = []

        cursor = index + 2

        found_action = False

        while cursor < len(lines):

            value = lines[cursor]

            lower = value.lower()

            if lower in {
                "like",
                "likes",
                "reply",
                "replies",
            }:

                found_action = True
                break

            # Another username followed by a timestamp
            # means a new comment started.
            if (
                cursor + 1 < len(lines)
                and username_pattern.fullmatch(
                    lines[cursor]
                )
                and timestamp_pattern.fullmatch(
                    lines[cursor + 1]
                )
            ):

                break

            if lower not in ignored:

                if lower not in {
                    "log in to like or comment",
                    "view all comments",
                    "view more comments",
                    "more comments",
                    "see more",
                }:

                    comment_parts.append(
                        value
                    )

            cursor += 1

        comment = " ".join(
            comment_parts
        ).strip()

        if found_action and comment:

            key = (
                f"{username.lower()}:"
                f"{comment.lower()}"
            )

            if key not in seen:

                seen.add(key)

                comments.append(
                    {
                        "comment": comment,
                        "likes": 0,
                        "post_url": post_url,
                        "username": username,
                    }
                )

        index = max(
            index + 1,
            cursor + 1,
        )

    return comments


def _launch_browser() -> tuple[
    Any,
    Browser,
    BrowserContext,
]:
    """
    IMPORTANT:

    Do NOT use launch_persistent_context() here.

    We load storage_state.json into a normal browser context.
    That prevents the 'Opening in existing browser session'
    error when another Chromium instance is open.
    """

    if not STORAGE_STATE_PATH.exists():

        raise InstagramWebError(
            "Instagram login state not found:\n"
            f"{STORAGE_STATE_PATH}\n\n"
            "Run:\n"
            "uv run python -m app.instagram_login\n"
            "and log into Instagram once."
        )

    playwright = (
        sync_playwright().start()
    )

    try:

        browser = (
            playwright.chromium.launch(
                headless=_is_headless(),
            )
        )

        context = (
            browser.new_context(
                storage_state=str(
                    STORAGE_STATE_PATH
                ),
                viewport={
                    "width": 1440,
                    "height": 1000,
                },
                locale="en-US",
                timezone_id="Asia/Kolkata",
                java_script_enabled=True,
            )
        )

        return (
            playwright,
            browser,
            context,
        )

    except Exception:

        playwright.stop()
        raise


def _fetch_comments_sync(
    post_url: str,
    limit: int = 100,
) -> list[dict[str, Any]]:

    (
        playwright,
        browser,
        context,
    ) = _launch_browser()

    try:

        page = context.new_page()

        try:

            page.goto(
                post_url,
                wait_until="domcontentloaded",
                timeout=int(
                    os.getenv(
                        "INSTAGRAM_TIMEOUT_MS",
                        "45000",
                    )
                ),
            )

        except PlaywrightTimeoutError:
            pass

        page.wait_for_timeout(
            4000
        )

        _dismiss_popups(
            page
        )

        page.wait_for_timeout(
            1500
        )

        comments = (
            _extract_body_comments(
                page,
                post_url,
            )
        )

        for _ in range(10):

            if len(comments) >= limit:
                break

            try:

                page.mouse.wheel(
                    0,
                    1400,
                )

                page.wait_for_timeout(
                    1000
                )

                more = (
                    _extract_body_comments(
                        page,
                        post_url,
                    )
                )

                existing = {
                    (
                        row["username"].lower(),
                        row["comment"].lower(),
                    )
                    for row in comments
                }

                for row in more:

                    key = (
                        row["username"].lower(),
                        row["comment"].lower(),
                    )

                    if key not in existing:

                        existing.add(key)

                        comments.append(
                            row
                        )

            except Exception:
                break

        print(
            "[Instagram] Extracted "
            f"{len(comments)} comments from "
            f"{post_url}"
        )

        return comments[:limit]

    finally:

        try:
            context.close()
        except Exception:
            pass

        try:
            browser.close()
        except Exception:
            pass

        try:
            playwright.stop()
        except Exception:
            pass


def _fetch_preview_sync(
    post_url: str,
) -> dict[str, Any]:

    (
        playwright,
        browser,
        context,
    ) = _launch_browser()

    try:

        page = context.new_page()

        try:

            page.goto(
                post_url,
                wait_until="domcontentloaded",
                timeout=int(
                    os.getenv(
                        "INSTAGRAM_TIMEOUT_MS",
                        "45000",
                    )
                ),
            )

        except PlaywrightTimeoutError:
            pass

        page.wait_for_timeout(
            3500
        )

        _dismiss_popups(
            page
        )

        metrics = (
            _extract_visible_metrics(
                page
            )
        )

        thumbnail = _extract_meta(
            page,
            "og:image",
        )

        description = _extract_meta(
            page,
            "og:description",
        )

        return {
            "postUrl": post_url,
            "thumbnailUrl": thumbnail,
            "likes": metrics["likes"],
            "comments": metrics["comments"],
            "views": metrics["views"],
            "engagement": (
                metrics["likes"]
                + metrics["comments"]
            ),
            "source": "instagram_web",
            "description": description,
        }

    finally:

        try:
            context.close()
        except Exception:
            pass

        try:
            browser.close()
        except Exception:
            pass

        try:
            playwright.stop()
        except Exception:
            pass


async def fetch_comments(
    post_url: str,
    limit: int = 100,
) -> list[dict[str, Any]]:

    return await asyncio.to_thread(
        _fetch_comments_sync,
        post_url,
        limit,
    )


async def fetch_post_preview(
    post_url: str,
) -> dict[str, Any]:

    return await asyncio.to_thread(
        _fetch_preview_sync,
        post_url,
    )