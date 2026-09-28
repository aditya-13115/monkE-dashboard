from __future__ import annotations

import copy
import hashlib
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .admin_auth import admin_auth_enabled, require_admin
from .cache_store import JsonCacheStore
from .campaign_manager import CampaignManager, CampaignManagerError
from .comment_source import InstagramFetchError
from .data_loader import load_campaign
from .instagram_web import (
    STORAGE_STATE_PATH,
    fetch_post_analysis_source,
    fetch_post_preview,
    get_all_cached_post_data,
    get_cached_post_data,
    normalize_instagram_url,
    shutdown_instagram_browser,
)
from .sentiment import GroqKeysExhaustedError, MODEL as SENTIMENT_MODEL, analyze_comments
from .share_store import ShareLinkError, ShareLinkStore

BASE_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BASE_DIR / "backend" / ".env")
DATA_DIR = BASE_DIR / "data"
CACHE_DIR = DATA_DIR / "instagram_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

CAMPAIGN_MANAGER = CampaignManager(BASE_DIR)
SHARE_STORE = ShareLinkStore(DATA_DIR / "share_links.json")
CAMPAIGN_STORE = JsonCacheStore(CACHE_DIR / "campaign.json")
SENTIMENT_STORE = JsonCacheStore(CACHE_DIR / "sentiment.json")
SENTIMENT_CACHE_SECONDS = max(300, int(os.getenv("SENTIMENT_CACHE_SECONDS", "86400")))
DEFAULT_XLSX = BASE_DIR / "data" / "ASIAN PAINTS (1).xlsx"
LEGACY_XLSX_PATH = Path(os.getenv("CAMPAIGN_XLSX_PATH", str(DEFAULT_XLSX)))
if not LEGACY_XLSX_PATH.is_absolute():
    LEGACY_XLSX_PATH = (BASE_DIR / LEGACY_XLSX_PATH).resolve()
DEFAULT_CAMPAIGN_ID = os.getenv("DEFAULT_CAMPAIGN_ID", "").strip()
MAX_UPLOAD_BYTES = max(1_000_000, int(os.getenv("MAX_CAMPAIGN_UPLOAD_BYTES", str(25 * 1024 * 1024))))
PUBLIC_VIEWER_BASE_URL = os.getenv("PUBLIC_VIEWER_BASE_URL", "http://localhost:5173").rstrip("/")

_campaign_memory: dict[str, tuple[int, dict[str, Any]]] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await shutdown_instagram_browser()


app = FastAPI(
    title="Monk-E Campaign Intelligence API",
    version="6.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class SentimentRequest(BaseModel):
    comments: list[dict[str, Any]]
    sample_size: int | None = Field(default=None, ge=10, le=100)


class ShareCreateRequest(BaseModel):
    brand: str = Field(min_length=1)
    campaignIds: list[str] = Field(default_factory=list)
    label: str = ""


def _pct(value: float, denominator: float) -> float:
    return round(value / denominator * 100, 2) if denominator else 0.0


def _catalog() -> list[dict[str, Any]]:
    return CAMPAIGN_MANAGER.list()


def _default_campaign_id() -> str:
    catalog = _catalog()
    if not catalog:
        # Backwards-compatible bootstrap for an older working copy that only
        # has the original workbook and has not created a registry yet.
        if LEGACY_XLSX_PATH.exists():
            item = CAMPAIGN_MANAGER.add_existing(
                "Asian Paints",
                "Main Campaign",
                LEGACY_XLSX_PATH,
            )
            return item["id"]
        raise FileNotFoundError("No campaigns are registered yet.")
    if DEFAULT_CAMPAIGN_ID and any(x.get("id") == DEFAULT_CAMPAIGN_ID for x in catalog):
        return DEFAULT_CAMPAIGN_ID
    return str(catalog[0]["id"])


def _campaign_signature(path: Path) -> int:
    try:
        return int(path.stat().st_mtime_ns)
    except OSError:
        return 0


def _load_base_campaign(campaign_id: str) -> dict[str, Any]:
    item = CAMPAIGN_MANAGER.get(campaign_id)
    path = CAMPAIGN_MANAGER.resolve_file(campaign_id)
    signature = _campaign_signature(path)
    memory = _campaign_memory.get(campaign_id)
    if memory and memory[0] == signature:
        return memory[1]

    cached = CAMPAIGN_STORE.get(f"campaign:{campaign_id}")
    if isinstance(cached, dict) and int(cached.get("workbookMtimeNs", -1)) == signature:
        base = cached.get("data")
        if isinstance(base, dict):
            _campaign_memory[campaign_id] = (signature, base)
            return base

    base = load_campaign(
        path,
        brand=str(item["brand"]),
        campaign_name=str(item["campaign"]),
        campaign_id=campaign_id,
    )
    CAMPAIGN_STORE.set(
        f"campaign:{campaign_id}",
        {"workbookMtimeNs": signature, "data": base},
    )
    _campaign_memory[campaign_id] = (signature, base)
    return base


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


def _campaign_with_live_cache(campaign_id: str) -> dict[str, Any]:
    base = copy.deepcopy(_load_base_campaign(campaign_id))
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
    summary = dict(base.get("summary", {}))
    summary.update(
        {
            "livePostsSynced": live_posts,
            "liveCoveragePct": _pct(live_posts, len(records)),
            "liveLikes": total_live_likes,
            "liveComments": total_live_comments,
            "liveViews": total_live_views,
            "liveEngagement": total_live_engagement,
            "liveEngagementRateOfReach": _pct(total_live_engagement, summary.get("totalReach", 0)),
        }
    )
    base["summary"] = summary

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
        "note": "Public Instagram metrics are persisted when available. Owner-only reach remains the Excel value because it is not reliably public.",
    }
    return base


def get_campaign(campaign_id: str | None = None) -> dict[str, Any]:
    return _campaign_with_live_cache(campaign_id or _default_campaign_id())


def get_post(campaign_id: str, post_id: int) -> dict[str, Any]:
    campaign = get_campaign(campaign_id)
    for record in campaign.get("records", []):
        if int(record["id"]) == post_id:
            return record
    raise HTTPException(status_code=404, detail=f"Post {post_id} was not found in campaign {campaign_id}.")


def _sentiment_key(post_url: str) -> str:
    normalized = normalize_instagram_url(post_url)
    return hashlib.sha256(f"{SENTIMENT_MODEL}|{normalized}".encode("utf-8")).hexdigest()


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


def _catalog_public() -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in _catalog():
        result.append(
            {
                "id": item["id"],
                "brand": item["brand"],
                "campaign": item["campaign"],
                "recordCount": item.get("recordCount", 0),
                "sourceName": item.get("sourceName", ""),
                "updatedAt": item.get("updatedAt"),
            }
        )
    return result


def _sanitize_share_campaign(campaign: dict[str, Any]) -> dict[str, Any]:
    clean = copy.deepcopy(campaign)
    clean.get("meta", {}).pop("source", None)
    clean["readonly"] = True
    return clean


@app.get("/health")
def health():
    groq_keys = [x.strip() for x in os.getenv("GROQ_API_KEYS", "").split(",") if x.strip()]
    return {
        "ok": True,
        "version": app.version,
        "groq_keys_configured": len(groq_keys),
        "instagram_storage_state_exists": STORAGE_STATE_PATH.exists(),
        "campaigns_registered": len(_catalog()),
        "admin_auth_enabled": admin_auth_enabled(),
        "public_viewer_base_url": PUBLIC_VIEWER_BASE_URL,
        "persistent_cache_dir": str(CACHE_DIR),
        "sentiment_cache_seconds": SENTIMENT_CACHE_SECONDS,
    }


@app.get("/api/admin/status")
def admin_status():
    return {"authEnabled": admin_auth_enabled()}


@app.get("/api/admin/campaigns")
def admin_campaigns(_: None = Depends(require_admin)):
    return {"campaigns": _catalog_public()}


@app.post("/api/admin/campaigns/upload")
async def upload_campaign(
    brand: str = Form(...),
    campaign: str = Form(...),
    file: UploadFile = File(...),
    _: None = Depends(require_admin),
):
    filename = file.filename or "campaign.xlsx"
    if not filename.lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(status_code=400, detail="Only Excel .xlsx or .xlsm files are supported.")

    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"Excel file is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.")

    try:
        item = CAMPAIGN_MANAGER.add_uploaded_bytes(brand, campaign, filename, content)
        _campaign_memory.pop(item["id"], None)
        return {"campaign": item}
    except (CampaignManagerError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/api/admin/campaigns/{campaign_id}")
def delete_campaign(campaign_id: str, _: None = Depends(require_admin)):
    try:
        deleted = CAMPAIGN_MANAGER.delete(campaign_id)
        _campaign_memory.pop(campaign_id, None)
        return {"deleted": deleted}
    except CampaignManagerError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/admin/share-links")
def create_share_link(req: ShareCreateRequest, _: None = Depends(require_admin)):
    campaigns = [x for x in _catalog() if x.get("brand") == req.brand]
    valid_by_id = {str(x["id"]): x for x in campaigns}
    ids = req.campaignIds or list(valid_by_id)
    if not ids:
        raise HTTPException(status_code=400, detail="The selected brand has no campaigns.")
    if any(cid not in valid_by_id for cid in ids):
        raise HTTPException(status_code=400, detail="All shared campaigns must belong to the selected brand.")
    item = SHARE_STORE.create(req.brand, ids, req.label)
    return {
        "share": item,
        "url": f"{PUBLIC_VIEWER_BASE_URL}/share/{item['token']}",
    }


@app.get("/api/admin/share-links")
def list_share_links(_: None = Depends(require_admin)):
    return {
        "links": [
            {**item, "url": f"{PUBLIC_VIEWER_BASE_URL}/share/{item['token']}"}
            for item in SHARE_STORE.list()
        ]
    }


@app.delete("/api/admin/share-links/{token}")
def delete_share_link(token: str, _: None = Depends(require_admin)):
    if not SHARE_STORE.delete(token):
        raise HTTPException(status_code=404, detail="Share link was not found.")
    return {"deleted": True}


@app.get("/api/share/{token}")
def public_share(token: str):
    item = SHARE_STORE.get(token)
    if not item:
        raise HTTPException(status_code=404, detail="This read-only share link is invalid or expired.")

    selected: list[dict[str, Any]] = []
    for campaign_id in item.get("campaignIds", []):
        try:
            selected.append(_sanitize_share_campaign(get_campaign(str(campaign_id))))
        except Exception:
            continue

    if not selected:
        raise HTTPException(status_code=404, detail="No campaigns are available for this share link.")

    return {
        "readonly": True,
        "brand": item.get("brand", "Brand"),
        "label": item.get("label", ""),
        "campaigns": selected,
        "generatedAt": item.get("createdAt"),
    }


@app.get("/api/campaign")
def campaign(_: None = Depends(require_admin)):
    try:
        return get_campaign()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/campaigns/{campaign_id}")
def campaign_by_id(campaign_id: str, _: None = Depends(require_admin)):
    try:
        return get_campaign(campaign_id)
    except CampaignManagerError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/campaign/post/{post_id}")
def legacy_campaign_post(post_id: int, _: None = Depends(require_admin)):
    return get_post(_default_campaign_id(), post_id)


@app.get("/api/campaigns/{campaign_id}/post/{post_id}")
def campaign_post(campaign_id: str, post_id: int, _: None = Depends(require_admin)):
    return get_post(campaign_id, post_id)


async def _post_live(campaign_id: str, post_id: int, force: bool = False) -> dict[str, Any]:
    post = get_post(campaign_id, post_id)
    post_url = str(post.get("postLink", "")).strip()
    if not post_url:
        raise HTTPException(status_code=400, detail="This Excel record has no POST LINK.")
    try:
        live = await fetch_post_preview(post_url, force=force)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Live Instagram fetch failed: {exc}") from exc
    combined = merge_live_post(post, live)
    return {"post": combined, "live": live, "cached": bool(live.get("cacheHit", False))}


@app.get("/api/posts/{post_id}/live")
async def legacy_post_live(post_id: int, force: bool = False, _: None = Depends(require_admin)):
    return await _post_live(_default_campaign_id(), post_id, force)


@app.get("/api/campaigns/{campaign_id}/posts/{post_id}/live")
async def post_live(campaign_id: str, post_id: int, force: bool = False, _: None = Depends(require_admin)):
    return await _post_live(campaign_id, post_id, force)


async def _sentiment_for_post(campaign_id: str, post_id: int, force: bool = False) -> dict[str, Any]:
    post = get_post(campaign_id, post_id)
    post_url = str(post.get("postLink", "")).strip()
    if not post_url:
        raise HTTPException(status_code=400, detail="This Excel record does not contain a POST LINK.")

    if not force:
        cached = _cached_sentiment(post_url)
        if cached:
            live = get_cached_post_data(post_url)
            cached["post"] = merge_live_post(post, live) if live else cached.get("post", post)
            cached["cached"] = True
            print(f"[Sentiment] cache hit for {campaign_id}/{post_id}", flush=True)
            return cached

    try:
        print(f"[Sentiment] loading Instagram source for {campaign_id}/{post_id}: {post_url}", flush=True)
        source = await fetch_post_analysis_source(post_url, comment_limit=100, force=force)
        comments = list(source.get("commentsData", []))
        print(f"[Sentiment] Instagram returned {len(comments)} extracted comments for {campaign_id}/{post_id}", flush=True)
        if not comments:
            raise InstagramFetchError("Instagram opened the post, but no publicly visible comments were extracted.")
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
        print(
            f"[Sentiment] complete: positive={analysis.get('summary', {}).get('positive', 0)} "
            f"neutral={analysis.get('summary', {}).get('neutral', 0)} "
            f"negative={analysis.get('summary', {}).get('negative', 0)}",
            flush=True,
        )
        return payload
    except InstagramFetchError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except GroqKeysExhaustedError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        print(f"[Sentiment] ERROR for {campaign_id}/{post_id}: {exc}", flush=True)
        raise HTTPException(status_code=500, detail=f"Post sentiment analysis failed: {exc}") from exc


@app.post("/api/sentiment/post/{post_id}")
async def legacy_sentiment(post_id: int, force: bool = False, _: None = Depends(require_admin)):
    return await _sentiment_for_post(_default_campaign_id(), post_id, force)


@app.post("/api/campaigns/{campaign_id}/sentiment/post/{post_id}")
async def sentiment_for_post(campaign_id: str, post_id: int, force: bool = False, _: None = Depends(require_admin)):
    return await _sentiment_for_post(campaign_id, post_id, force)


@app.post("/api/sentiment/analyze")
async def sentiment(req: SentimentRequest, _: None = Depends(require_admin)):
    try:
        return await analyze_comments(req.comments, req.sample_size)
    except GroqKeysExhaustedError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Sentiment analysis failed: {exc}") from exc
