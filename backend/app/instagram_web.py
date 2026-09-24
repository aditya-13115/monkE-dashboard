from __future__ import annotations

import asyncio
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from .cache_store import JsonCacheStore

from playwright.sync_api import (
    Browser,
    BrowserContext,
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

POST_RE = re.compile(
    r"https?://(?:www\.)?instagram\.com/(?:p|reel|reels)/([^/?#]+)/?",
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
    return match.group(0).rstrip("/")


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
    One shared Playwright browser/context/page for the entire FastAPI process.

    The Playwright objects are created and used on the same dedicated worker
    thread. This avoids both:
      1. Windows asyncio subprocess issues with the Sync API.
      2. The 'popup bomb' caused by launching a browser per card/request.
    """

    def __init__(self) -> None:
        self._executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="monke-instagram",
        )
        self._playwright = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._started = False
        self._closed = False
        self._post_cache: dict[str, tuple[float, dict[str, Any]]] = {}
        self._cache_ttl = int(os.getenv("INSTAGRAM_CACHE_SECONDS", "1800"))
        self._cache_store = JsonCacheStore(CACHE_DIR / "post_live.json")

    async def _run(self, fn, *args):
        if self._closed:
            raise InstagramWebError("Instagram browser service is closed.")
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, lambda: fn(*args))

    def _cache_get_sync(self, normalized: str) -> dict[str, Any] | None:
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
        self._post_cache[normalized] = (time.monotonic(), snapshot)
        self._cache_store.set(normalized, snapshot)

    def _ensure_started_sync(self) -> None:
        if self._started and self._page is not None:
            return

        if not STORAGE_STATE_PATH.exists():
            raise InstagramWebError(
                f"Instagram login state not found: {STORAGE_STATE_PATH}. "
                "Run 'uv run python -m app.instagram_login' once and log in manually."
            )

        self.PROFILE_DIR = PROFILE_DIR
        self._playwright = sync_playwright().start()

        try:
            self._browser = self._playwright.chromium.launch(
                headless=_env_bool("INSTAGRAM_HEADLESS", True),
            )
            self._context = self._browser.new_context(
                storage_state=str(STORAGE_STATE_PATH),
                viewport={"width": 1440, "height": 1000},
                locale="en-US",
                timezone_id="Asia/Kolkata",
                java_script_enabled=True,
            )
            self._context.set_default_timeout(8_000)
            self._context.set_default_navigation_timeout(
                int(os.getenv("INSTAGRAM_TIMEOUT_MS", "45000"))
            )
            self._page = self._context.new_page()
            self._started = True
        except Exception:
            self._safe_close_sync()
            raise

    def _safe_close_sync(self) -> None:
        self._started = False
        try:
            if self._context is not None:
                self._context.close()
        except Exception:
            pass
        try:
            if self._browser is not None:
                self._browser.close()
        except Exception:
            pass
        try:
            if self._playwright is not None:
                self._playwright.stop()
        except Exception:
            pass
        self._page = None
        self._context = None
        self._browser = None
        self._playwright = None

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

    def _extract_comments_from_json_sync(
        self,
        payload: Any,
        post_url: str,
        output: list[dict[str, Any]],
        seen: set[str],
    ) -> None:
        if isinstance(payload, dict):
            text = payload.get("text")
            owner = payload.get("owner")
            user = payload.get("user")
            owner_obj = owner if isinstance(owner, dict) else user if isinstance(user, dict) else None
            username = ""
            if owner_obj:
                username = str(
                    owner_obj.get("username")
                    or owner_obj.get("handle")
                    or ""
                ).strip()
            typename = str(payload.get("__typename", "")).lower()
            internal_typename = str(payload.get("_typename", "")).lower()
            looks_like_comment = bool(
                isinstance(text, str)
                and text.strip()
                and (
                    payload.get("pk")
                    or payload.get("comment_id")
                    or "comment" in typename
                    or "comment" in internal_typename
                )
                and username
            )
            if looks_like_comment:
                comment = text.strip()
                comment_id = str(
                    payload.get("pk")
                    or payload.get("comment_id")
                    or f"{username}:{comment}"
                )
                if comment_id not in seen:
                    seen.add(comment_id)
                    output.append(
                        {
                            "comment": comment,
                            "likes": _to_int(
                                payload.get(
                                    "like_count",
                                    payload.get("comment_like_count", 0),
                                )
                            ),
                            "post_url": post_url,
                            "username": username,
                        }
                    )
            for value in payload.values():
                self._extract_comments_from_json_sync(value, post_url, output, seen)
        elif isinstance(payload, list):
            for value in payload:
                self._extract_comments_from_json_sync(value, post_url, output, seen)

    def _click_comment_controls_sync(self, page: Page) -> None:
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
                    if strategy == "button":
                        locator = page.get_by_role(
                            "button",
                            name=re.compile(pattern, re.IGNORECASE),
                        )
                    else:
                        locator = page.get_by_text(
                            re.compile(pattern, re.IGNORECASE),
                            exact=False,
                        )
                    for i in range(min(locator.count(), 4)):
                        try:
                            item = locator.nth(i)
                            if item.is_visible():
                                item.click(timeout=1_500)
                                page.wait_for_timeout(800)
                        except Exception:
                            continue
                except Exception:
                    continue

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

    def _fetch_post_sync(
        self,
        post_url: str,
        include_comments: bool,
        comment_limit: int,
        force: bool,
    ) -> dict[str, Any]:
        self._ensure_started_sync()
        assert self._page is not None
        page = self._page
        normalized = normalize_instagram_url(post_url)

        if not force:
            cached = self._cache_get_sync(normalized)
            if cached is not None:
                # `commentsFetched` distinguishes a preview cache from a
                # complete analysis-source cache. An empty commentsData list
                # is still a valid cached result for a post with no exposed
                # comments, so do not use truthiness of the list itself.
                comments_fetched = bool(cached.get("commentsFetched", False))
                age = self._cache_age_seconds_sync(normalized)
                fresh = age is None or age <= self._cache_ttl
                cache_is_usable = (not include_comments or comments_fetched)

                # Persistent cache is intentionally served even when stale.
                # Refreshing live data is an explicit user action (`force=true`)
                # so browser reloads never trigger a new Instagram navigation.
                if cache_is_usable:
                    cached["cacheAgeSeconds"] = round(age or 0, 1)
                    cached["cacheFresh"] = fresh
                    cached["cacheHit"] = True
                    return cached

        response_comments: list[dict[str, Any]] = []
        response_seen: set[str] = set()

        def on_response(response) -> None:
            try:
                if "instagram.com" not in response.url.lower():
                    return
                content_type = response.headers.get("content-type", "").lower()
                if "json" not in content_type:
                    return
                payload = response.json()
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
                page.goto(
                    normalized,
                    wait_until="domcontentloaded",
                    timeout=int(os.getenv("INSTAGRAM_TIMEOUT_MS", "45000")),
                )
            except PlaywrightTimeoutError:
                pass

            page.wait_for_timeout(int(os.getenv("INSTAGRAM_INITIAL_WAIT_MS", "1500")))
            self._dismiss_popups_sync(page)
            self._click_comment_controls_sync(page)
            page.wait_for_timeout(int(os.getenv("INSTAGRAM_COMMENT_WAIT_MS", "500")))

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

            comments = self._extract_comments_from_text_sync(
                body,
                normalized,
            )

            # Scroll only when comments are requested. Preview/thumbnail calls
            # do not need to hammer the page by loading the full comment list.
            if include_comments:
                for _ in range(max(1, int(os.getenv("INSTAGRAM_COMMENT_ROUNDS", "6")))):
                    if len(comments) >= comment_limit:
                        break
                    self._scroll_comments_sync(page)
                    self._click_comment_controls_sync(page)
                    updated_body = self._body_text_sync(page)
                    more = self._extract_comments_from_text_sync(
                        updated_body,
                        normalized,
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
                    if len(comments) >= comment_limit:
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
                "commentsFetched": bool(include_comments),
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
            await loop.run_in_executor(self._executor, self._safe_close_sync)
        finally:
            self._executor.shutdown(wait=False, cancel_futures=True)


_BROWSER = InstagramBrowser()


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
