from __future__ import annotations

import asyncio
import html
import json
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from .cache_store import JsonCacheStore

from playwright.sync_api import (
    Browser,
    BrowserContext,
    Error as PlaywrightError,
    Page,
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)


class InstagramWebError(RuntimeError):
    """Raised when the Instagram web session cannot provide the requested data."""


BASE_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BASE_DIR / "backend" / ".env")

PROFILE_DIR = Path(
    os.getenv("INSTAGRAM_USER_DATA_DIR", "data/instagram_profile")
)
if not PROFILE_DIR.is_absolute():
    PROFILE_DIR = (BASE_DIR / PROFILE_DIR).resolve()

STORAGE_STATE_PATH = PROFILE_DIR / "storage_state.json"
CACHE_DIR = BASE_DIR / "data" / "instagram_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

COMMENT_EXTRACTION_VERSION = "2026-09-29-4"
BROWSER_RECOVERY_ATTEMPTS = max(1, min(3, int(os.getenv("INSTAGRAM_BROWSER_RECOVERY_ATTEMPTS", "2"))))

POST_RE = re.compile(
    r"https?://(?:www\.)?instagram\.com/(p|reel|reels)/([^/?#]+)/?",
    re.IGNORECASE,
)


def _env_bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() not in {"0", "false", "no", "off"}


def _to_int(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return max(0, int(value))
    text = str(value).strip().lower().replace(",", "")
    match = re.fullmatch(r"([\d.]+)\s*([kmb])?", text)
    if not match:
        return 0
    try:
        number = float(match.group(1))
    except ValueError:
        return 0
    suffix = match.group(2)
    if suffix == "k":
        number *= 1_000
    elif suffix == "m":
        number *= 1_000_000
    elif suffix == "b":
        number *= 1_000_000_000
    return max(0, int(number))


def normalize_instagram_url(url: str) -> str:
    value = str(url or "").strip()
    match = POST_RE.search(value)
    if not match:
        raise InstagramWebError(f"Invalid Instagram post/reel URL: {value}")
    media_type = match.group(1).lower()
    shortcode = match.group(2)
    canonical_type = "p" if media_type == "p" else "reel"
    return f"https://www.instagram.com/{canonical_type}/{shortcode}"


def _is_username(value: str) -> bool:
    value = value.strip().lstrip("@")
    return bool(value) and len(value) <= 30 and bool(re.fullmatch(r"[A-Za-z0-9._]+", value))


def _is_timestamp(value: str) -> bool:
    value = value.strip()
    return bool(
        re.fullmatch(
            r"(?:\d+\s*[smhdwy]|\d+\s*(?:seconds?|minutes?|hours?|days?|weeks?|months?|years?)\s*ago)",
            value,
            re.IGNORECASE,
        )
    )


def _is_month_date(value: str) -> bool:
    return bool(
        re.fullmatch(
            r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2}(?:,\s*\d{4})?",
            value.strip(),
            re.IGNORECASE,
        )
    )


class InstagramBrowser:
    """
    Persistent Instagram browser service with bounded parallel workers.

    Each executor worker owns its own Playwright Sync API instance, browser,
    context, and page. This is important because Playwright Sync API objects
    are thread-affine. The workers are reused across fetches, so a bulk campaign
    sync can process several Instagram URLs concurrently without creating a new
    browser for every request.

    When visible debug mode is enabled, concurrency is deliberately reduced to
    one worker by default to avoid the old multi-window/popup-bomb behaviour.
    Set INSTAGRAM_ALLOW_VISIBLE_PARALLEL=true only when you explicitly want
    multiple visible browser windows.
    """

    def __init__(self) -> None:
        configured = max(1, min(10, int(os.getenv("INSTAGRAM_FETCH_CONCURRENCY", "8"))))
        if not _env_bool("INSTAGRAM_HEADLESS", True) and not _env_bool(
            "INSTAGRAM_ALLOW_VISIBLE_PARALLEL", False
        ):
            configured = 1

        self._fetch_concurrency = configured
        self._executor = ThreadPoolExecutor(
            max_workers=configured,
            thread_name_prefix="monke-instagram",
        )
        self._thread_local = threading.local()
        self._session_lock = threading.RLock()
        self._cache_lock = threading.RLock()
        self._sessions: dict[int, dict[str, Any]] = {}
        self._closed = False
        self._post_cache: dict[str, tuple[float, dict[str, Any]]] = {}
        self._cache_ttl = int(os.getenv("INSTAGRAM_CACHE_SECONDS", "1800"))
        self._empty_comment_retry_ttl = max(
            60,
            int(os.getenv("INSTAGRAM_EMPTY_COMMENT_RETRY_SECONDS", "900")),
        )
        self._cache_store = JsonCacheStore(CACHE_DIR / "post_live.json")

    async def _run(self, fn, *args):
        if self._closed:
            raise InstagramWebError("Instagram browser service is closed.")
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, lambda: fn(*args))

    def _cache_get_sync(self, normalized: str) -> dict[str, Any] | None:
        with self._cache_lock:
            memory = self._post_cache.get(normalized)
            if memory is not None:
                return json.loads(json.dumps(memory[1]))

            disk = self._cache_store.get(normalized)
            if not isinstance(disk, dict):
                return None

            self._post_cache[normalized] = (
                time.monotonic(),
                json.loads(json.dumps(disk)),
            )
            return json.loads(json.dumps(disk))

    def _cache_age_seconds_sync(self, normalized: str) -> float | None:
        entry = self._cache_store.get_entry(normalized)
        if entry is None:
            memory = self._post_cache.get(normalized)
            if memory is None:
                return None
            # Memory-only fallback is always considered fresh for the current
            # process. Persistent entries carry their wall-clock timestamp.
            return 0.0
        try:
            return max(0.0, time.time() - float(entry.get("savedAt", 0)))
        except (TypeError, ValueError):
            return None

    def _cache_save_sync(self, normalized: str, data: dict[str, Any]) -> None:
        snapshot = json.loads(json.dumps(data))
        with self._cache_lock:
            self._post_cache[normalized] = (time.monotonic(), snapshot)
            self._cache_store.set(normalized, snapshot)

    def _ensure_started_sync(self) -> Page:
        session = getattr(self._thread_local, "session", None)
        if session is not None:
            page = session.get("page")
            if page is not None:
                try:
                    if not page.is_closed():
                        return page
                except Exception:
                    pass

        if self._closed:
            raise InstagramWebError("Instagram browser service is closed.")

        # A crashed/closed worker page should not leave its old browser session
        # hanging around before the worker creates a replacement.
        if session is not None:
            self._safe_close_sync()

        if not STORAGE_STATE_PATH.exists():
            raise InstagramWebError(
                f"Instagram login state not found: {STORAGE_STATE_PATH}. "
                "Run 'uv run python -m app.instagram_login' once and log in manually."
            )

        playwright = sync_playwright().start()
        try:
            browser = playwright.chromium.launch(
                headless=_env_bool("INSTAGRAM_HEADLESS", True),
                args=[
                    "--disable-gpu",
                    "--disable-dev-shm-usage",
                    "--no-first-run",
                    "--no-default-browser-check",
                ],
            )
            context = browser.new_context(
                storage_state=str(STORAGE_STATE_PATH),
                viewport={"width": 1440, "height": 1000},
                locale="en-US",
                timezone_id="Asia/Kolkata",
                java_script_enabled=True,
            )
            context.set_default_timeout(8_000)
            context.set_default_navigation_timeout(
                int(os.getenv("INSTAGRAM_TIMEOUT_MS", "45000"))
            )
            page = context.new_page()
            session = {
                "playwright": playwright,
                "browser": browser,
                "context": context,
                "page": page,
            }
            self._thread_local.session = session
            with self._session_lock:
                self._sessions[threading.get_ident()] = session
            return page
        except Exception:
            try:
                playwright.stop()
            except Exception:
                pass
            raise

    def _safe_close_sync(self) -> None:
        session = getattr(self._thread_local, "session", None)
        if not session:
            return
        self._thread_local.session = None
        with self._session_lock:
            self._sessions.pop(threading.get_ident(), None)
        for key in ("context", "browser"):
            try:
                obj = session.get(key)
                if obj is not None:
                    obj.close()
            except Exception:
                pass
        try:
            session.get("playwright").stop()
        except Exception:
            pass

    def _dismiss_popups_sync(self, page: Page) -> None:
        for label in (
            "Not now",
            "Close",
            "Cancel",
            "Allow all cookies",
            "Only allow essential cookies",
            "Allow essential cookies",
        ):
            try:
                locator = page.get_by_role(
                    "button",
                    name=re.compile(
                        f"^{re.escape(label)}$",
                        re.IGNORECASE,
                    ),
                )
                for i in range(min(locator.count(), 2)):
                    try:
                        button = locator.nth(i)
                        if button.is_visible():
                            button.click(timeout=1_200)
                            page.wait_for_timeout(250)
                    except Exception:
                        continue
            except Exception:
                continue

    def _body_text_sync(self, page: Page) -> str:
        try:
            return page.locator("body").inner_text(timeout=10_000)
        except Exception:
            return ""

    def _meta_sync(self, page: Page, selector: str) -> str:
        try:
            locator = page.locator(selector)
            if locator.count():
                return (locator.first.get_attribute("content") or "").strip()
        except Exception:
            pass
        return ""

    def _extract_metrics_sync(self, page: Page, body: str, description: str) -> dict[str, int]:
        metrics = {
            "likes": 0,
            "comments": 0,
            "views": 0,
            "shares": 0,
            "saves": 0,
        }

        # Metadata descriptions often contain the cleanest English phrasing,
        # so use broad patterns there first.
        for key, pattern in {
            "likes": r"([\d,.]+\s*[kmb]?)\s+likes\b",
            "comments": r"([\d,.]+\s*[kmb]?)\s+comments\b",
            "views": r"([\d,.]+\s*[kmb]?)\s+(?:views?|plays?)\b",
            "shares": r"([\d,.]+\s*[kmb]?)\s+shares\b",
            "saves": r"([\d,.]+\s*[kmb]?)\s+saves\b",
        }.items():
            match = re.search(pattern, str(description or ""), re.IGNORECASE)
            if match:
                metrics[key] = _to_int(match.group(1))

        lines = [x.strip() for x in body.splitlines() if x.strip()]
        label_map = {
            "like": "likes",
            "likes": "likes",
            "comment": "comments",
            "comments": "comments",
            "share": "shares",
            "shares": "shares",
            "save": "saves",
            "saves": "saves",
        }

        # Label -> number: Like / 325, Comment / 18, etc.
        for index, line in enumerate(lines[:-1]):
            key = label_map.get(line.lower())
            if not key:
                continue
            candidate = lines[index + 1]
            if re.fullmatch(r"[\d,.]+\s*[kmb]?", candidate, re.IGNORECASE):
                metrics[key] = _to_int(candidate)

        # Number -> label: 325 / Like, 18 / Comment. Do not use the reverse
        # form for Share/Save because Instagram commonly places action labels
        # immediately after the comment count with no share/save count.
        for index in range(1, len(lines)):
            label = lines[index].lower()
            if label not in {"like", "likes", "comment", "comments"}:
                continue
            candidate = lines[index - 1]
            # If the candidate number itself follows another metric label, it
            # belongs to that previous label (Like / 325 / Comment / 18).
            if index >= 2 and lines[index - 2].lower() in label_map:
                continue
            if re.fullmatch(r"[\d,.]+\s*[kmb]?", candidate, re.IGNORECASE):
                metrics[label_map[label]] = _to_int(candidate)

        # Free-form public pages sometimes use explicit plural phrases in body
        # text. Keep these plural-only to avoid interpreting `18 Share` as a
        # share counter when it is actually the label following the comment count.
        body_patterns = {
            "likes": r"([\d,.]+\s*[kmb]?)\s+likes\b",
            "comments": r"([\d,.]+\s*[kmb]?)\s+comments\b",
            "views": r"([\d,.]+\s*[kmb]?)\s+(?:views?|plays?)\b",
            "shares": r"([\d,.]+\s*[kmb]?)\s+shares\b",
            "saves": r"([\d,.]+\s*[kmb]?)\s+saves\b",
        }
        for key, pattern in body_patterns.items():
            match = re.search(pattern, body, re.IGNORECASE)
            if match and not metrics[key]:
                metrics[key] = _to_int(match.group(1))

        return metrics

    def _extract_comments_from_text_sync(self, body: str, post_url: str) -> list[dict[str, Any]]:
        lines = [
            re.sub(r"\s+", " ", line.strip())
            for line in body.splitlines()
            if line.strip()
        ]

        ignore = {
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
            "view all comments",
            "view more comments",
            "more comments",
            "log in to like or comment",
            "see more",
        }

        comments: list[dict[str, Any]] = []
        seen: set[str] = set()

        # Anchor the parser on the end of each comment ('Like' or 'Reply') and
        # search backwards for username + timestamp. This is more robust than
        # requiring a particular DOM tree, which Instagram changes frequently.
        for i, line in enumerate(lines):
            if line.lower() not in {"like", "likes", "reply", "replies"}:
                continue

            username = ""
            timestamp_idx = -1
            start = max(0, i - 12)
            for j in range(i - 1, start - 1, -1):
                if _is_timestamp(lines[j]) and j - 1 >= 0 and _is_username(lines[j - 1]):
                    username = lines[j - 1].lstrip("@")
                    timestamp_idx = j
                    break

            if not username:
                continue

            comment_lines = []
            for value in lines[timestamp_idx + 1 : i]:
                if value.lower() in ignore:
                    continue
                if _is_month_date(value):
                    continue
                if re.fullmatch(r"[\d,.]+\s*[kmb]?", value, re.IGNORECASE):
                    # A bare numeric immediately before Like can be a comment-like
                    # count. Keep it out of the comment text.
                    continue
                comment_lines.append(value)

            comment = " ".join(comment_lines).strip()
            if not comment:
                continue
            if comment.lower() in ignore:
                continue

            key = f"{username.lower()}::{comment.lower()}"
            if key in seen:
                continue
            seen.add(key)

            # When a numeric 'likes' count is actually rendered near a comment,
            # capture it; otherwise leave it at 0 and let sentiment sampling fall
            # back honestly to the available comments.
            likes = 0
            if i - 1 >= timestamp_idx + 1:
                candidate = lines[i - 1]
                if re.fullmatch(r"[\d,.]+\s*[kmb]?", candidate, re.IGNORECASE):
                    likes = _to_int(candidate)

            comments.append(
                {
                    "comment": comment,
                    "likes": likes,
                    "post_url": post_url,
                    "username": username,
                }
            )

        return comments

    def _extract_metrics_from_json_sync(
        self,
        payload: Any,
        metrics: dict[str, int],
    ) -> None:
        """Extract public media counters from Instagram's page/network JSON."""
        key_map = {
            "like_count": "likes",
            "comment_count": "comments",
            "play_count": "views",
            "video_view_count": "views",
            "view_count": "views",
            "video_play_count": "views",
            "reshare_count": "shares",
            "share_count": "shares",
            "save_count": "saves",
            "saved_count": "saves",
        }
        if isinstance(payload, dict):
            for key, target in key_map.items():
                if key in payload:
                    value = _to_int(payload.get(key))
                    if value:
                        metrics[target] = max(metrics.get(target, 0), value)
            for value in payload.values():
                self._extract_metrics_from_json_sync(value, metrics)
        elif isinstance(payload, list):
            for value in payload:
                self._extract_metrics_from_json_sync(value, metrics)


    def _extract_comments_from_json_sync(
        self,
        payload: Any,
        post_url: str,
        output: list[dict[str, Any]],
        seen: set[str],
    ) -> None:
        if isinstance(payload, dict):
            text = (
                payload.get("text")
                or payload.get("comment_text")
                or payload.get("body")
            )

            owner = payload.get("owner")
            user = payload.get("user")
            author = payload.get("author")
            creator = payload.get("created_by")
            owner_obj = next(
                (
                    value
                    for value in (owner, user, author, creator)
                    if isinstance(value, dict)
                    and (
                        value.get("username")
                        or value.get("handle")
                        or value.get("user_name")
                    )
                ),
                None,
            )

            username = ""
            if owner_obj:
                username = str(
                    owner_obj.get("username")
                    or owner_obj.get("handle")
                    or owner_obj.get("user_name")
                    or ""
                ).strip()

            typename = str(payload.get("__typename", "")).lower()
            internal_typename = str(payload.get("_typename", "")).lower()
            key_text = " ".join(str(key).lower() for key in payload.keys())

            looks_like_comment = bool(
                isinstance(text, str)
                and text.strip()
                and username
                and (
                    payload.get("comment_id")
                    or "comment" in typename
                    or "comment" in internal_typename
                    or "comment_like_count" in payload
                    or "parent_comment_id" in payload
                    or "comments" in key_text
                )
            )

            if looks_like_comment:
                comment = text.strip()
                comment_id = str(
                    payload.get("pk")
                    or payload.get("comment_id")
                    or payload.get("id")
                    or f"{username}:{comment}"
                )
                if comment_id not in seen:
                    seen.add(comment_id)
                    likes = (
                        payload.get("like_count")
                        or payload.get("comment_like_count")
                        or payload.get("likes")
                        or 0
                    )
                    output.append(
                        {
                            "comment": comment,
                            "likes": _to_int(likes),
                            "post_url": post_url,
                            "username": username,
                        }
                    )

            for value in payload.values():
                self._extract_comments_from_json_sync(value, post_url, output, seen)

        elif isinstance(payload, list):
            for value in payload:
                self._extract_comments_from_json_sync(value, post_url, output, seen)


    def _extract_comments_from_html_sync(
        self,
        html_text: str,
        post_url: str,
        output: list[dict[str, Any]],
        seen: set[str],
    ) -> None:
        """Extract comments from raw HTML application/json script tags.

        Instagram frequently embeds the initial comment connection in a
        `script[type=application/json]` block. This works for both /p/ posts
        and /reel/ pages and is less dependent on the current DOM structure.
        """
        if not html_text:
            return

        pattern = re.compile(
            r"<script\b[^>]*\btype=[\"\']application/json[\"\'][^>]*>(.*?)</script>",
            re.IGNORECASE | re.DOTALL,
        )
        for match in pattern.finditer(html_text):
            text = html.unescape(match.group(1) or "").strip()
            if not text or not any(
                marker in text.lower()
                for marker in ("comment", "comments_connection", "xigcomment", "xdtcomment", "comment_like_count")
            ):
                continue
            try:
                payload = json.loads(text)
            except (TypeError, ValueError):
                continue
            self._extract_comments_from_json_sync(payload, post_url, output, seen)

    def _extract_embedded_json_comments_sync(
        self,
        page: Page,
        post_url: str,
        output: list[dict[str, Any]],
        seen: set[str],
    ) -> None:
        """Extract comments from both raw HTML and DOM script nodes."""
        try:
            raw_html = page.content()
        except Exception:
            raw_html = ""
        self._extract_comments_from_html_sync(raw_html, post_url, output, seen)

        # DOM fallback for pages whose script markup is normalized by the
        # browser in a way that differs from page.content().
        try:
            scripts = page.locator('script[type="application/json"]')
            script_texts = scripts.evaluate_all(
                "nodes => nodes.map(node => node.textContent || '')"
            )
        except Exception:
            script_texts = []

        for raw in script_texts:
            text = str(raw or "").strip()
            if not text or not any(
                marker in text.lower()
                for marker in ("comment", "comments_connection", "xigcomment", "xdtcomment", "comment_like_count")
            ):
                continue
            try:
                payload = json.loads(text)
            except (TypeError, ValueError):
                continue
            self._extract_comments_from_json_sync(payload, post_url, output, seen)

    def _click_comment_controls_sync(self, page: Page) -> bool:
        """Open Instagram's comment surface using several stable UI strategies."""
        clicked = False
        patterns = [
            r"view all .*comments?",
            r"view .*more comments?",
            r"more comments?",
            r"load more comments?",
            r"view comments",
        ]

        for pattern in patterns:
            for strategy in ("button", "text"):
                try:
                    locator = (
                        page.get_by_role("button", name=re.compile(pattern, re.IGNORECASE))
                        if strategy == "button"
                        else page.get_by_text(re.compile(pattern, re.IGNORECASE), exact=False)
                    )
                    for i in range(min(locator.count(), 4)):
                        try:
                            item = locator.nth(i)
                            if item.is_visible():
                                item.click(timeout=1_500)
                                clicked = True
                                page.wait_for_timeout(700)
                        except Exception:
                            continue
                except Exception:
                    continue

        # Reels often expose only an icon/button whose accessible name contains
        # "comment". Avoid reply/input controls and click the first useful action.
        try:
            locator = page.get_by_role(
                "button",
                name=re.compile(r"comment", re.IGNORECASE),
            )
            for i in range(min(locator.count(), 8)):
                try:
                    button = locator.nth(i)
                    if not button.is_visible():
                        continue
                    label = (button.get_attribute("aria-label") or "").lower()
                    if any(token in label for token in ("reply", "add a comment", "send")):
                        continue
                    button.click(timeout=1_500)
                    clicked = True
                    page.wait_for_timeout(900)
                    break
                except Exception:
                    continue
        except Exception:
            pass

        return clicked

    def _scroll_comments_sync(self, page: Page) -> None:
        try:
            dialogs = page.locator('[role="dialog"]')
            if dialogs.count():
                dialog = dialogs.last
                if dialog.is_visible():
                    dialog.evaluate("el => el.scrollTop = el.scrollHeight")
                    page.wait_for_timeout(900)
                    return
        except Exception:
            pass
        try:
            page.mouse.wheel(0, 1500)
            page.wait_for_timeout(900)
        except Exception:
            pass

    def _comments_cache_usable_sync(
        self,
        cached: dict[str, Any],
        age: float | None,
    ) -> bool:
        """Only reuse a comment cache when the extractor actually found comments."""
        _ = age
        if not cached.get("commentsFetchAttempted", False):
            return False
        if cached.get("commentExtractionVersion") != COMMENT_EXTRACTION_VERSION:
            return False
        return int(cached.get("commentsExtracted", 0) or 0) > 0

    def _is_recoverable_browser_error(self, exc: BaseException) -> bool:
        message = str(exc).lower()
        return any(
            marker in message
            for marker in (
                "page crashed",
                "browser has been closed",
                "target page, context or browser has been closed",
                "target closed",
                "crashed",
            )
        )

    def _fetch_post_once_sync(
        self,
        post_url: str,
        include_comments: bool,
        comment_limit: int,
        force: bool,
    ) -> dict[str, Any]:
        normalized = normalize_instagram_url(post_url)

        if not force:
            cached = self._cache_get_sync(normalized)
            if cached is not None:
                # `commentsFetched` distinguishes a preview cache from a
                # complete analysis-source cache. An empty commentsData list
                # is still a valid cached result for a post with no exposed
                # comments, so do not use truthiness of the list itself.
                age = self._cache_age_seconds_sync(normalized)
                fresh = age is None or age <= self._cache_ttl
                cache_is_usable = (
                    not include_comments
                    or self._comments_cache_usable_sync(cached, age)
                )

                # Persistent cache is intentionally served even when stale.
                # Refreshing live data is an explicit user action (`force=true`)
                # so browser reloads never trigger a new Instagram navigation.
                if cache_is_usable:
                    cached["cacheAgeSeconds"] = round(age or 0, 1)
                    cached["cacheFresh"] = fresh
                    cached["cacheHit"] = True
                    return cached

        # Only start Chromium when a network fetch is actually required.
        # This keeps cache-only page loads working even if the Instagram login
        # state is unavailable or Chromium is temporarily unavailable.
        page = self._ensure_started_sync()

        response_comments: list[dict[str, Any]] = []
        response_seen: set[str] = set()
        response_metrics = {"likes": 0, "comments": 0, "views": 0, "shares": 0, "saves": 0}

        def on_response(response) -> None:
            try:
                if "instagram.com" not in response.url.lower():
                    return
                content_type = response.headers.get("content-type", "").lower()
                if "json" not in content_type:
                    return
                payload = response.json()
                self._extract_metrics_from_json_sync(payload, response_metrics)
                self._extract_comments_from_json_sync(
                    payload,
                    normalized,
                    response_comments,
                    response_seen,
                )
            except Exception:
                pass

        page.on("response", on_response)
        try:
            try:
                # `commit` returns as soon as the navigation commits, which
                # makes recovery from a Chromium renderer crash much faster than
                # waiting for DOMContentLoaded on an Instagram page that may keep
                # long-running background requests alive.
                page.goto(
                    normalized,
                    wait_until="commit",
                    timeout=int(os.getenv("INSTAGRAM_TIMEOUT_MS", "45000")),
                )
            except PlaywrightTimeoutError:
                pass

            page.wait_for_timeout(int(os.getenv("INSTAGRAM_INITIAL_WAIT_MS", "1800")))
            self._dismiss_popups_sync(page)
            self._click_comment_controls_sync(page)
            page.wait_for_timeout(int(os.getenv("INSTAGRAM_COMMENT_WAIT_MS", "700")))

            body = self._body_text_sync(page)
            description = self._meta_sync(
                page,
                'meta[property="og:description"]',
            ) or self._meta_sync(
                page,
                'meta[name="description"]',
            )
            thumbnail = self._meta_sync(
                page,
                'meta[property="og:image"]',
            ) or self._meta_sync(
                page,
                'meta[name="twitter:image"]',
            )

            metrics = self._extract_metrics_sync(
                page,
                body,
                description,
            )

            # Page-embedded JSON is often the cleanest source for post/reel
            # counters. Prefer those public counters when present.
            try:
                scripts = page.locator('script[type="application/json"]')
                for raw_script in scripts.evaluate_all("nodes => nodes.map(node => node.textContent || '')"):
                    text_script = str(raw_script or "").strip()
                    if not text_script or not any(marker in text_script for marker in ("like_count", "comment_count", "play_count", "video_view_count")):
                        continue
                    try:
                        self._extract_metrics_from_json_sync(json.loads(text_script), metrics)
                    except (TypeError, ValueError):
                        continue
            except Exception:
                pass

            for key, value in response_metrics.items():
                if value:
                    metrics[key] = max(metrics.get(key, 0), value)

            comments = self._extract_comments_from_text_sync(
                body,
                normalized,
            )

            self._extract_embedded_json_comments_sync(
                page,
                normalized,
                comments,
                {(row["username"].lower(), row["comment"].lower()) for row in comments},
            )

            # Scroll only when comments are requested. Preview/thumbnail calls
            # do not need to hammer the page by loading the full comment list.
            if include_comments:
                rounds = max(1, int(os.getenv("INSTAGRAM_COMMENT_ROUNDS", "6")))
                stagnant_rounds = 0
                previous_count = len(comments)

                for round_index in range(rounds):
                    if len(comments) >= comment_limit:
                        break

                    self._click_comment_controls_sync(page)
                    self._scroll_comments_sync(page)
                    page.wait_for_timeout(350 if round_index else 500)

                    updated_body = self._body_text_sync(page)
                    more = self._extract_comments_from_text_sync(
                        updated_body,
                        normalized,
                    )
                    self._extract_embedded_json_comments_sync(
                        page,
                        normalized,
                        comments,
                        {(row["username"].lower(), row["comment"].lower()) for row in comments},
                    )
                    existing = {
                        (row["username"].lower(), row["comment"].lower())
                        for row in comments
                    }
                    for row in more:
                        key = (row["username"].lower(), row["comment"].lower())
                        if key not in existing:
                            existing.add(key)
                            comments.append(row)

                    if len(comments) == previous_count:
                        stagnant_rounds += 1
                    else:
                        stagnant_rounds = 0
                    previous_count = len(comments)

                    # If Instagram did not add anything after two attempts,
                    # stop rather than spending 5-10x longer on a page that
                    # simply exposes no additional public comments.
                    if stagnant_rounds >= 2:
                        break

                for row in response_comments:
                    key = (row["username"].lower(), row["comment"].lower())
                    existing = {
                        (item["username"].lower(), item["comment"].lower())
                        for item in comments
                    }
                    if key not in existing:
                        comments.append(row)

            engagement = (
                metrics["likes"]
                + metrics["comments"]
                + metrics["shares"]
                + metrics["saves"]
            )

            data = {
                "postUrl": normalized,
                "thumbnailUrl": thumbnail,
                "description": description,
                "likes": metrics["likes"],
                "comments": metrics["comments"],
                "views": metrics["views"],
                "shares": metrics["shares"],
                "saves": metrics["saves"],
                "engagement": engagement,
                "commentsData": comments[:comment_limit],
                "commentsExtracted": len(comments),
                "commentsFetched": bool(include_comments and comments),
                "commentsFetchAttempted": bool(include_comments),
                "commentsEmptyConfirmed": bool(include_comments and not comments),
                "commentExtractionVersion": COMMENT_EXTRACTION_VERSION,
                "source": "instagram_web",
                "lastSyncedAt": time.time(),
                "cacheHit": False,
                "cacheFresh": True,
                "cacheAgeSeconds": 0,
            }

            self._cache_save_sync(normalized, data)
            return data
        finally:
            try:
                page.remove_listener("response", on_response)
            except Exception:
                pass

    def _fetch_post_sync(
        self,
        post_url: str,
        include_comments: bool,
        comment_limit: int,
        force: bool,
    ) -> dict[str, Any]:
        normalized = normalize_instagram_url(post_url)
        last_error: BaseException | None = None

        for attempt in range(1, BROWSER_RECOVERY_ATTEMPTS + 1):
            try:
                result = self._fetch_post_once_sync(
                    normalized,
                    include_comments,
                    comment_limit,
                    force,
                )
                if attempt > 1:
                    result["browserRecovered"] = True
                    result["browserRecoveryAttempt"] = attempt
                return result
            except PlaywrightError as exc:
                last_error = exc
                if not self._is_recoverable_browser_error(exc):
                    raise

                print(
                    f"[Instagram] browser recovery {attempt}/{BROWSER_RECOVERY_ATTEMPTS} "
                    f"for {normalized}: {exc}",
                    flush=True,
                )
                self._safe_close_sync()

                if attempt >= BROWSER_RECOVERY_ATTEMPTS:
                    break

                time.sleep(0.4 * attempt)

            except Exception as exc:
                # Some Playwright/Chromium builds surface renderer crashes
                # through a generic RuntimeError rather than PlaywrightError.
                last_error = exc
                if not self._is_recoverable_browser_error(exc):
                    raise

                print(
                    f"[Instagram] generic browser recovery {attempt}/{BROWSER_RECOVERY_ATTEMPTS} "
                    f"for {normalized}: {exc}",
                    flush=True,
                )
                self._safe_close_sync()

                if attempt >= BROWSER_RECOVERY_ATTEMPTS:
                    break

                time.sleep(0.4 * attempt)

        # A failed forced refresh should not destroy a previously successful
        # sentiment workflow. If a complete cached analysis source exists, use
        # it as a stale fallback instead of turning a renderer crash into HTTP 500.
        cached = self._cache_get_sync(normalized)
        cached_age = self._cache_age_seconds_sync(normalized)
        if include_comments and isinstance(cached, dict) and self._comments_cache_usable_sync(cached, cached_age):
            cached["cacheHit"] = True
            cached["cacheFresh"] = False
            cached["cacheFallback"] = True
            cached["cacheAgeSeconds"] = round(cached_age or 0, 1)
            cached["browserRecoveryFailed"] = True
            return cached

        detail = str(last_error) if last_error else "Unknown Chromium error"
        raise InstagramWebError(
            f"Instagram Chromium renderer crashed while opening {normalized}. "
            f"The browser was restarted {BROWSER_RECOVERY_ATTEMPTS} time(s) but could not recover. "
            f"Details: {detail}"
        ) from last_error

    async def fetch_post(
        self,
        post_url: str,
        *,
        include_comments: bool = False,
        comment_limit: int = 100,
        force: bool = False,
    ) -> dict[str, Any]:
        return await self._run(
            self._fetch_post_sync,
            post_url,
            include_comments,
            comment_limit,
            force,
        )

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        loop = asyncio.get_running_loop()
        try:
            # Wake multiple worker threads so each thread gets a chance to close
            # its own thread-affine Playwright session.
            await asyncio.gather(
                *(
                    loop.run_in_executor(self._executor, self._safe_close_sync)
                    for _ in range(self._fetch_concurrency)
                ),
                return_exceptions=True,
            )
        finally:
            self._executor.shutdown(wait=True, cancel_futures=True)


_BROWSER = InstagramBrowser()


def get_instagram_fetch_concurrency() -> int:
    """Return the actual worker count after visible/headless safety rules."""
    return int(_BROWSER._fetch_concurrency)


def get_cached_post_data(post_url: str) -> dict[str, Any] | None:
    """Read persisted post data without launching Playwright."""
    normalized = normalize_instagram_url(post_url)
    data = _BROWSER._cache_get_sync(normalized)
    if data is None:
        return None
    age = _BROWSER._cache_age_seconds_sync(normalized)
    data["cacheAgeSeconds"] = round(age or 0, 1)
    data["cacheFresh"] = age is None or age <= _BROWSER._cache_ttl
    data["cacheHit"] = True
    return data


def get_all_cached_post_data(*, include_comments: bool = False) -> dict[str, dict[str, Any]]:
    """Read the persistent post cache once, without launching Playwright.

    Campaign-level reads omit comment bodies by default so /api/campaign stays
    small even when many posts have 100-comment sentiment samples cached.
    """
    output: dict[str, dict[str, Any]] = {}
    for normalized, entry in _BROWSER._cache_store.items():
        data = entry.get("data")
        if not isinstance(data, dict):
            continue
        try:
            age = max(0.0, time.time() - float(entry.get("savedAt", 0)))
        except (TypeError, ValueError):
            age = 0.0
        snapshot = json.loads(json.dumps(data))
        if not include_comments:
            snapshot.pop("commentsData", None)
        snapshot["cacheAgeSeconds"] = round(age, 1)
        snapshot["cacheFresh"] = age <= _BROWSER._cache_ttl
        snapshot["cacheHit"] = True
        output[normalized] = snapshot
    return output


async def fetch_post_preview(
    post_url: str,
    *,
    force: bool = False,
) -> dict[str, Any]:
    return await _BROWSER.fetch_post(
        post_url,
        include_comments=False,
        force=force,
    )


async def fetch_comments(
    post_url: str,
    limit: int = 100,
    *,
    force: bool = False,
) -> list[dict[str, Any]]:
    data = await _BROWSER.fetch_post(
        post_url,
        include_comments=True,
        comment_limit=limit,
        force=force,
    )
    return list(data.get("commentsData", []))


async def fetch_post_analysis_source(
    post_url: str,
    *,
    comment_limit: int = 100,
    force: bool = False,
) -> dict[str, Any]:
    return await _BROWSER.fetch_post(
        post_url,
        include_comments=True,
        comment_limit=comment_limit,
        force=force,
    )


async def shutdown_instagram_browser() -> None:
    await _BROWSER.close()
