from __future__ import annotations

import copy
import hashlib
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .cache_store import JsonCacheStore
from .comment_source import InstagramFetchError
from .data_loader import load_campaign
from .instagram_web import (
    STORAGE_STATE_PATH,
    fetch_post_analysis_source,
    fetch_post_preview,
    get_all_cached_post_data,
    get_cached_post_data,
    shutdown_instagram_browser,
    normalize_instagram_url,
)
from .sentiment import GroqKeysExhaustedError, MODEL as SENTIMENT_MODEL, analyze_comments

BASE_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BASE_DIR / "backend" / ".env")
DEFAULT_XLSX = BASE_DIR / "data" / "ASIAN PAINTS (1).xlsx"
XLSX_PATH = Path(os.getenv("CAMPAIGN_XLSX_PATH", str(DEFAULT_XLSX)))
if not XLSX_PATH.is_absolute():
    XLSX_PATH = (BASE_DIR / XLSX_PATH).resolve()

CACHE_DIR = BASE_DIR / "data" / "instagram_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
CAMPAIGN_STORE = JsonCacheStore(CACHE_DIR / "campaign.json")
SENTIMENT_STORE = JsonCacheStore(CACHE_DIR / "sentiment.json")
SENTIMENT_CACHE_SECONDS = max(300, int(os.getenv("SENTIMENT_CACHE_SECONDS", "86400")))

_campaign_base_memory: tuple[int, dict[str, Any]] | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await shutdown_instagram_browser()


app = FastAPI(
    title="Monk-E Campaign Intelligence API",
    version="5.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class Comment(BaseModel):
    comment: str = Field(min_length=1)
    likes: int = 0
    post_url: str = ""
    username: str = ""


class SentimentRequest(BaseModel):
    comments: list[Comment]
    sample_size: int | None = Field(default=None, ge=10, le=100)


def _workbook_signature() -> int:
    try:
        return int(XLSX_PATH.stat().st_mtime_ns)
    except OSError:
        return 0


def _load_base_campaign() -> dict[str, Any]:
    global _campaign_base_memory

    if not XLSX_PATH.exists():
        raise FileNotFoundError(f"Campaign workbook not found: {XLSX_PATH}")

    signature = _workbook_signature()
    if _campaign_base_memory and _campaign_base_memory[0] == signature:
        return _campaign_base_memory[1]

    cached = CAMPAIGN_STORE.get("campaign")
    if isinstance(cached, dict) and int(cached.get("workbookMtimeNs", -1)) == signature:
        base = cached.get("data")
        if isinstance(base, dict):
            _campaign_base_memory = (signature, base)
            return base

    base = load_campaign(XLSX_PATH)
    CAMPAIGN_STORE.set(
        "campaign",
        {
            "workbookMtimeNs": signature,
            "data": base,
        },
    )
    _campaign_base_memory = (signature, base)
    return base


def _pct(value: float, denominator: float) -> float:
    return round(value / denominator * 100, 2) if denominator else 0.0


def merge_live_post(post: dict[str, Any], live: dict[str, Any]) -> dict[str, Any]:
    combined = dict(post)
    public_engagement = int(live.get("engagement", 0) or 0)
    reach = int(post.get("reach", 0) or 0)
    combined.update(
        {
            "thumbnailUrl": live.get("thumbnailUrl") or post.get("thumbnailUrl", ""),
            "liveLikes": int(live.get("likes", 0) or 0),
            "liveComments": int(live.get("comments", 0) or 0),
            "liveViews": int(live.get("views", 0) or 0),
            "liveShares": int(live.get("shares", 0) or 0),
            "liveSaves": int(live.get("saves", 0) or 0),
            "liveEngagement": public_engagement,
            "liveCommentsExtracted": int(live.get("commentsExtracted", 0) or 0),
            "liveDataAvailable": True,
            "liveDataSource": "instagram_web",
            "liveCacheHit": bool(live.get("cacheHit", False)),
            "liveCacheFresh": bool(live.get("cacheFresh", True)),
            "liveCacheAgeSeconds": float(live.get("cacheAgeSeconds", 0) or 0),
            "lastSyncedAt": live.get("lastSyncedAt"),
            "dataSources": {
                "campaign": "excel",
                "reach": "excel",
                "followers": "excel",
                "engagement": "instagram_web_public",
                "likes": "instagram_web_public",
                "comments": "instagram_web_public",
                "views": "instagram_web_public",
                "thumbnail": "instagram_web_public",
            },
        }
    )
    if reach:
        combined["liveEngagementRateReach"] = _pct(public_engagement, reach)
    return combined


def _campaign_with_live_cache() -> dict[str, Any]:
    base = copy.deepcopy(_load_base_campaign())
    cached_posts = get_all_cached_post_data(include_comments=False)
    records: list[dict[str, Any]] = []

    total_live_likes = 0
    total_live_comments = 0
    total_live_views = 0
    total_live_engagement = 0
    live_posts = 0

    for record in base.get("records", []):
        try:
            key = normalize_instagram_url(record.get("postLink", ""))
        except Exception:
            key = ""
        cached = cached_posts.get(key) if key else None
        merged = merge_live_post(record, cached) if cached else record
        records.append(merged)

        if merged.get("liveDataAvailable"):
            live_posts += 1
            total_live_likes += int(merged.get("liveLikes", 0) or 0)
            total_live_comments += int(merged.get("liveComments", 0) or 0)
            total_live_views += int(merged.get("liveViews", 0) or 0)
            total_live_engagement += int(merged.get("liveEngagement", 0) or 0)

    base["records"] = records
    base_summary = base.get("summary", {})
    base_summary.update(
        {
            "livePostsSynced": live_posts,
            "liveCoveragePct": _pct(live_posts, len(records)),
            "liveLikes": total_live_likes,
            "liveComments": total_live_comments,
            "liveViews": total_live_views,
            "liveEngagement": total_live_engagement,
            "liveEngagementRateOfReach": _pct(total_live_engagement, base_summary.get("totalReach", 0)),
        }
    )
    base["summary"] = base_summary

    category_records: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        category_records.setdefault(record["category"], []).append(record)

    categories: list[dict[str, Any]] = []
    for category in base.get("categories", []):
        rows = category_records.get(category["name"], [])
        live_rows = [r for r in rows if r.get("liveDataAvailable")]
        live_engagement = sum(int(r.get("liveEngagement", 0) or 0) for r in live_rows)
        live_views = sum(int(r.get("liveViews", 0) or 0) for r in live_rows)
        categories.append(
            {
                **category,
                "livePosts": len(live_rows),
                "liveEngagement": live_engagement,
                "liveViews": live_views,
                "liveEngagementRate": _pct(live_engagement, category.get("reach", 0)),
            }
        )
    base["categories"] = categories
    base["liveData"] = {
        "cached": True,
        "coverage": live_posts,
        "totalRecords": len(records),
        "note": "Public Instagram metrics are cached when available; reach remains from the workbook because owner-only reach is not reliably public.",
    }
    return base


def get_campaign() -> dict[str, Any]:
    return _campaign_with_live_cache()


def get_post(post_id: int) -> dict[str, Any]:
    campaign = get_campaign()
    for record in campaign.get("records", []):
        if int(record["id"]) == post_id:
            return record
    raise HTTPException(status_code=404, detail=f"Post {post_id} was not found.")


def _sentiment_key(post_url: str) -> str:
    normalized = normalize_instagram_url(post_url)
    return hashlib.sha256(
        f"{SENTIMENT_MODEL}|{normalized}".encode("utf-8")
    ).hexdigest()


def _cached_sentiment(post_url: str) -> dict[str, Any] | None:
    entry = SENTIMENT_STORE.get_entry(_sentiment_key(post_url))
    if not entry:
        return None
    try:
        age = max(0.0, time.time() - float(entry.get("savedAt", 0)))
    except (TypeError, ValueError):
        return None
    if age > SENTIMENT_CACHE_SECONDS:
        return None
    data = entry.get("data")
    return copy.deepcopy(data) if isinstance(data, dict) else None


def _save_sentiment(post_url: str, payload: dict[str, Any]) -> None:
    SENTIMENT_STORE.set(_sentiment_key(post_url), payload)


@app.get("/health")
def health():
    groq_keys = [x.strip() for x in os.getenv("GROQ_API_KEYS", "").split(",") if x.strip()]
    return {
        "ok": True,
        "version": app.version,
        "groq_keys_configured": len(groq_keys),
        "instagram_storage_state_exists": STORAGE_STATE_PATH.exists(),
        "campaign_workbook": str(XLSX_PATH),
        "instagram_mode": "single_shared_browser_context",
        "persistent_cache_dir": str(CACHE_DIR),
        "sentiment_cache_seconds": SENTIMENT_CACHE_SECONDS,
    }


@app.get("/api/campaign")
def campaign():
    try:
        return get_campaign()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/campaign/post/{post_id}")
def campaign_post(post_id: int):
    return get_post(post_id)


@app.get("/api/posts/{post_id}/live")
async def post_live(post_id: int, force: bool = False):
    post = get_post(post_id)
    post_url = str(post.get("postLink", "")).strip()
    if not post_url:
        raise HTTPException(status_code=400, detail="This Excel record has no POST LINK.")

    try:
        live = await fetch_post_preview(post_url, force=force)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Live Instagram fetch failed: {exc}") from exc

    combined = merge_live_post(post, live)
    return {"post": combined, "live": live, "cached": bool(live.get("cacheHit", False))}


@app.post("/api/sentiment/post/{post_id}")
async def sentiment_for_post(post_id: int, force: bool = False):
    post = get_post(post_id)
    post_url = str(post.get("postLink", "")).strip()
    if not post_url:
        raise HTTPException(status_code=400, detail="This Excel record does not contain a POST LINK.")

    if not force:
        cached = _cached_sentiment(post_url)
        if cached:
            live = get_cached_post_data(post_url)
            cached["post"] = merge_live_post(post, live) if live else cached.get("post", post)
            cached["cached"] = True
            print(f"[Sentiment] cache hit for post {post_id}", flush=True)
            return cached

    try:
        print(f"[Sentiment] loading Instagram source for post {post_id}: {post_url}", flush=True)
        source = await fetch_post_analysis_source(
            post_url,
            comment_limit=100,
            force=force,
        )
        comments = list(source.get("commentsData", []))
        print(f"[Sentiment] Instagram returned {len(comments)} extracted comments for post {post_id}", flush=True)

        if not comments:
            raise InstagramFetchError(
                "Instagram opened the post, but no publicly visible comments were extracted."
            )

        analysis = await analyze_comments(comments)
        live_post = merge_live_post(post, source)
        payload = {
            "post": live_post,
            "postUrl": post_url,
            "commentsAvailable": len(comments),
            "analysis": analysis,
            "cached": False,
            "generatedAt": time.time(),
        }
        _save_sentiment(post_url, payload)
        return payload
    except InstagramFetchError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except GroqKeysExhaustedError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        print(f"[Sentiment] ERROR for post {post_id}: {exc}", flush=True)
        raise HTTPException(status_code=500, detail=f"Post sentiment analysis failed: {exc}") from exc


@app.post("/api/sentiment/analyze")
async def sentiment(req: SentimentRequest):
    try:
        return await analyze_comments([item.model_dump() for item in req.comments], req.sample_size)
    except GroqKeysExhaustedError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Sentiment analysis failed: {exc}") from exc
