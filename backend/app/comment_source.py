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


class InstagramFetchError(RuntimeError):
    """Raised when Instagram comments cannot be fetched."""


INSTAGRAM_URL_RE = re.compile(
    r"https?://(?:www\.)?instagram\.com/(?:p|reel|reels)/[^/?#]+/?",
    re.IGNORECASE,
)


def normalize_instagram_url(url: str) -> str:
    """
    Normalize an Instagram post/reel URL.

    Supported:
        https://www.instagram.com/p/ABC123/
        https://www.instagram.com/reel/ABC123/
        https://www.instagram.com/reels/ABC123/
    """

    url = str(url or "").strip()

    if not url:
        raise InstagramFetchError(
            "The Excel row does not contain an Instagram post URL."
        )

    match = INSTAGRAM_URL_RE.search(url)

    if not match:
        raise InstagramFetchError(
            f"Invalid Instagram post/reel URL: {url}"
        )

    return match.group(0).rstrip("/")


def _to_int(value: Any) -> int:
    """
    Convert values like:
        123
        1,234
        1.2k
        3.5m
    into integers.
    """

    if value is None:
        return 0

    if isinstance(value, bool):
        return int(value)

    if isinstance(value, (int, float)):
        return max(0, int(value))

    text = str(value).strip().lower()

    match = re.match(
        r"^([\d,.]+)\s*([km])?$",
        text,
    )

    if not match:
        return 0

    try:
        number = float(
            match.group(1).replace(",", "")
        )
    except ValueError:
        return 0

    suffix = match.group(2)

    if suffix == "k":
        number *= 1_000

    elif suffix == "m":
        number *= 1_000_000

    return max(0, int(number))


def _extract_likes(text: str) -> int:
    """
    Extract visible comment like counts.
    """

    patterns = [
        r"([\d,.]+\s*[km]?)\s+likes?\b",
        r"([\d,.]+\s*[km]?)\s+like\b",
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            text,
            re.IGNORECASE,
        )

        if match:
            return _to_int(
                match.group(1)
            )

    return 0


def _clean_comment_text(
    text: str,
    username: str = "",
) -> str:
    """
    Clean an Instagram comment block.
    """

    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]

    if username:
        lines = [
            line
            for line in lines
            if line.strip() != username.strip()
        ]

    noise_patterns = [
        r"^\d+[smhdw]$",
        r"^\d+\s*(?:seconds?|minutes?|hours?|days?|weeks?)\s*ago$",
        r"^like$",
        r"^likes$",
        r"^reply$",
        r"^replies$",
        r"^follow$",
        r"^following$",
        r"^edited$",
        r"^see translation$",
        r"^view all.*repl",
        r"^view .*repl",
        r"^more$",
    ]

    cleaned: list[str] = []

    for line in lines:

        if any(
            re.match(
                pattern,
                line,
                re.IGNORECASE,
            )
            for pattern in noise_patterns
        ):
            continue

        if line.lower() in {
            "like",
            "reply",
            "follow",
            "following",
            "translation",
            "see translation",
        }:
            continue

        cleaned.append(line)

    return " ".join(cleaned).strip()


def _extract_comments_from_dom(
    page: Page,
    post_url: str,
) -> list[dict[str, Any]]:
    """
    Extract comments from the rendered Instagram DOM.

    This is the main fallback because Instagram can change its
    internal network payload format.
    """

    comments: list[dict[str, Any]] = []

    seen: set[tuple[str, str]] = set()

    items = page.locator("li")

    try:
        count = items.count()
    except Exception:
        return comments

    for index in range(count):

        try:

            item = items.nth(index)

            if not item.is_visible():
                continue

            raw_text = item.inner_text(
                timeout=1500
            ).strip()

            if not raw_text:
                continue

            if len(raw_text) > 2500:
                continue

            lines = [
                line.strip()
                for line in raw_text.splitlines()
                if line.strip()
            ]

            if len(lines) < 2:
                continue

            username = ""

            # Try to discover username from a link.
            try:

                links = item.locator("a")

                link_count = links.count()

                for i in range(
                    min(link_count, 5)
                ):

                    href = links.nth(i).get_attribute(
                        "href"
                    )

                    text = links.nth(i).inner_text().strip()

                    if (
                        href
                        and text
                        and "/" in href
                        and "instagram.com" not in href
                        and text.lower()
                        not in {
                            "like",
                            "reply",
                            "follow",
                        }
                    ):

                        username = text.lstrip("@")
                        break

            except Exception:
                pass

            # Usually first line is the username.
            if not username and lines:

                candidate = lines[0].strip()

                if (
                    1 <= len(candidate) <= 40
                    and re.fullmatch(
                        r"@?[A-Za-z0-9._]+",
                        candidate,
                    )
                ):

                    username = candidate.lstrip("@")

            comment = _clean_comment_text(
                raw_text,
                username,
            )

            if not comment:
                continue

            if len(comment) < 2:
                continue

            lowered = comment.lower()

            if lowered in {
                "view all comments",
                "view more comments",
                "more comments",
                "log in",
                "sign up",
            }:
                continue

            likes = _extract_likes(
                raw_text
            )

            key = (
                username.lower(),
                comment.lower(),
            )

            if key in seen:
                continue

            seen.add(key)

            comments.append(
                {
                    "comment": comment,
                    "likes": likes,
                    "post_url": post_url,
                    "username": username,
                }
            )

        except Exception:
            continue

    return comments


def _collect_comment_objects(
    payload: Any,
    post_url: str,
    output: list[dict[str, Any]],
    seen: set[str],
) -> None:
    """
    Recursively inspect Instagram JSON responses
    and extract comment objects where identifiable.
    """

    if isinstance(payload, dict):

        text = payload.get("text")

        owner = payload.get("owner")
        user = payload.get("user")

        if isinstance(owner, dict):
            owner_obj = owner

        elif isinstance(user, dict):
            owner_obj = user

        else:
            owner_obj = None

        username = ""

        if owner_obj:

            username = str(
                owner_obj.get("username")
                or owner_obj.get("handle")
                or ""
            ).strip()

        typename = str(
            payload.get(
                "__typename",
                "",
            )
        ).lower()

        internal_typename = str(
            payload.get(
                "_typename",
                "",
            )
        ).lower()

        looks_like_comment = bool(
            text
            and isinstance(text, str)
            and (
                payload.get("pk")
                or payload.get("comment_id")
                or "comment" in typename
                or "comment" in internal_typename
            )
            and username
        )

        if looks_like_comment:

            comment_text = text.strip()

            if comment_text:

                comment_id = str(
                    payload.get("pk")
                    or payload.get("comment_id")
                    or f"{username}:{comment_text}"
                )

                if comment_id not in seen:

                    seen.add(
                        comment_id
                    )

                    likes = _to_int(
                        payload.get(
                            "like_count",
                            payload.get(
                                "comment_like_count",
                                0,
                            ),
                        )
                    )

                    output.append(
                        {
                            "comment": comment_text,
                            "likes": likes,
                            "post_url": post_url,
                            "username": username,
                        }
                    )

        for value in payload.values():

            _collect_comment_objects(
                value,
                post_url,
                output,
                seen,
            )

    elif isinstance(payload, list):

        for value in payload:

            _collect_comment_objects(
                value,
                post_url,
                output,
                seen,
            )


def _click_comment_buttons(
    page: Page,
) -> None:
    """
    Expand visible Instagram comment controls.
    """

    patterns = [
        r"view all .*comments?",
        r"view .*more comments?",
        r"more comments?",
        r"load more comments?",
    ]

    for _ in range(5):

        clicked_any = False

        for pattern in patterns:

            try:

                locator = page.get_by_role(
                    "button",
                    name=re.compile(
                        pattern,
                        re.IGNORECASE,
                    ),
                )

                count = locator.count()

                for index in range(
                    min(count, 3)
                ):

                    button = locator.nth(index)

                    try:

                        if button.is_visible():

                            button.click(
                                timeout=1500
                            )

                            clicked_any = True

                            page.wait_for_timeout(
                                700
                            )

                    except Exception:
                        continue

            except Exception:
                continue

        if not clicked_any:
            break


def _dismiss_common_dialogs(
    page: Page,
) -> None:
    """
    Dismiss common cookie/login popup dialogs if they appear.
    """

    patterns = [
        r"not now",
        r"close",
        r"cancel",
        r"allow all cookies",
        r"allow essential cookies",
        r"only allow essential cookies",
    ]

    for pattern in patterns:

        try:

            locator = page.get_by_role(
                "button",
                name=re.compile(
                    f"^{pattern}$",
                    re.IGNORECASE,
                ),
            )

            count = locator.count()

            for index in range(
                min(count, 2)
            ):

                button = locator.nth(index)

                try:

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


def _parse_json_response(
    response: Any,
    post_url: str,
    comments: list[dict[str, Any]],
    seen: set[str],
) -> None:
    """
    Parse an Instagram JSON response synchronously.
    """

    try:

        url = response.url.lower()

        if "instagram.com" not in url:
            return

        # Instagram may use multiple request endpoints.
        # Don't depend on one exact GraphQL URL.
        content_type = (
            response.headers.get(
                "content-type",
                "",
            )
            .lower()
        )

        if "json" not in content_type:
            return

        payload = response.json()

        _collect_comment_objects(
            payload,
            post_url,
            comments,
            seen,
        )

    except Exception:
        pass


def _get_profile_dir() -> Path:
    """
    Persistent browser profile.

    This lets the browser keep cookies/session data between requests.
    If Instagram asks you to log in, you can run with
    INSTAGRAM_HEADLESS=false, log in manually once, and reuse the session.
    """

    configured = os.getenv(
        "INSTAGRAM_USER_DATA_DIR",
        "data/instagram_profile",
    )

    profile_dir = Path(configured)

    if not profile_dir.is_absolute():
        profile_dir = (
            Path(__file__).resolve().parents[2]
            / profile_dir
        )

    profile_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    return profile_dir


def _fetch_comments_sync(
    post_url: str,
) -> list[dict[str, Any]]:
    """
    IMPORTANT:
    This is synchronous Playwright.

    It deliberately does NOT use Playwright's async API,
    avoiding the Windows asyncio subprocess problem seen
    with the previous implementation.
    """

    headless = (
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

    timeout_ms = int(
        os.getenv(
            "INSTAGRAM_TIMEOUT_MS",
            "45000",
        )
    )

    comments: list[dict[str, Any]] = []

    seen: set[str] = set()

    with sync_playwright() as playwright:

        browser_context: BrowserContext | None = None
        browser: Browser | None = None

        try:

            profile_dir = _get_profile_dir()

            # Persistent context preserves cookies/session.
            browser_context = (
                playwright.chromium.launch_persistent_context(
                    user_data_dir=str(
                        profile_dir
                    ),
                    headless=headless,
                    viewport={
                        "width": 1440,
                        "height": 1000,
                    },
                    locale="en-US",
                    timezone_id="Asia/Kolkata",
                    java_script_enabled=True,
                )
            )

            # Persistent context already IS the browser context.
            page = (
                browser_context.pages[0]
                if browser_context.pages
                else browser_context.new_page()
            )

            def handle_response(response) -> None:

                _parse_json_response(
                    response,
                    post_url,
                    comments,
                    seen,
                )

            page.on(
                "response",
                handle_response,
            )

            try:

                page.goto(
                    post_url,
                    wait_until="domcontentloaded",
                    timeout=timeout_ms,
                )

            except PlaywrightTimeoutError:

                # Instagram can leave background resources open.
                # Continue if the page itself loaded.
                pass

            page.wait_for_timeout(
                3500
            )

            _dismiss_common_dialogs(
                page
            )

            _click_comment_buttons(
                page
            )

            # Scroll gradually to load more comments.
            for _ in range(10):

                try:

                    page.mouse.wheel(
                        0,
                        1400,
                    )

                    page.wait_for_timeout(
                        900
                    )

                    _click_comment_buttons(
                        page
                    )

                except Exception:
                    break

                if len(comments) >= 150:
                    break

            page.wait_for_timeout(
                1500
            )

            # DOM extraction.
            dom_comments = (
                _extract_comments_from_dom(
                    page,
                    post_url,
                )
            )

            for row in dom_comments:

                key = (
                    f"{row['username'].lower()}:"
                    f"{row['comment'].lower()}"
                )

                if key in seen:
                    continue

                seen.add(key)

                comments.append(
                    row
                )

            # Final deduplication.
            unique: list[dict[str, Any]] = []
            unique_keys: set[str] = set()

            for row in comments:

                key = (
                    f"{row.get('username', '').lower()}:"
                    f"{row.get('comment', '').lower()}"
                )

                if key in unique_keys:
                    continue

                unique_keys.add(key)

                unique.append(
                    row
                )

            return unique

        finally:

            if browser_context is not None:

                try:
                    browser_context.close()
                except Exception:
                    pass

            elif browser is not None:

                try:
                    browser.close()
                except Exception:
                    pass


async def get_comments_for_post(
    *,
    username: str,
    post_url: str,
) -> list[dict[str, Any]]:
    """
    Public async function used by FastAPI.

    Playwright itself runs synchronously inside a worker thread,
    so it doesn't interfere with Uvicorn's Windows event loop.
    """

    # Username remains part of the interface because the campaign
    # record contains it, but the exact Excel POST LINK is what
    # determines which Instagram post is opened.
    _ = username

    normalized_url = normalize_instagram_url(
        post_url
    )

    try:

        comments = await asyncio.to_thread(
            _fetch_comments_sync,
            normalized_url,
        )

    except Exception as exc:

        raise InstagramFetchError(
            f"Instagram browser fetch failed: {exc}"
        ) from exc

    if not comments:

        raise InstagramFetchError(
            "Instagram opened the post, but no publicly visible comments "
            "could be extracted. The post may be private, comments may "
            "be disabled, Instagram may require login, or Instagram may "
            "have changed its page structure."
        )

    return comments