from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .comment_source import InstagramFetchError, get_comments_for_post
from .data_loader import load_campaign
from .instagram_web import fetch_post_preview
from .sentiment import GroqKeysExhaustedError, analyze_comments

load_dotenv()

BASE_DIR = Path(__file__).resolve().parents[2]
DEFAULT_XLSX = BASE_DIR / "data" / "ASIAN PAINTS (1).xlsx"
XLSX_PATH = Path(os.getenv("CAMPAIGN_XLSX_PATH", str(DEFAULT_XLSX)))
if not XLSX_PATH.is_absolute():
    XLSX_PATH = (BASE_DIR / XLSX_PATH).resolve()

app = FastAPI(title="Monk-E Campaign Intelligence API", version="3.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

campaign_cache: dict[str, Any] | None = None


class Comment(BaseModel):
    comment: str = Field(min_length=1)
    likes: int = 0
    post_url: str = ""
    username: str = ""


class SentimentRequest(BaseModel):
    comments: list[Comment]
    sample_size: int | None = Field(default=None, ge=10, le=100)


def get_campaign() -> dict[str, Any]:
    global campaign_cache
    if campaign_cache is None:
        if not XLSX_PATH.exists():
            raise FileNotFoundError(f"Campaign workbook not found: {XLSX_PATH}")
        campaign_cache = load_campaign(XLSX_PATH)
    return campaign_cache


def get_post(post_id: int) -> dict[str, Any]:
    campaign = get_campaign()
    for record in campaign.get("records", []):
        if int(record["id"]) == post_id:
            return record
    raise HTTPException(status_code=404, detail=f"Post {post_id} was not found.")


@app.get("/health")
def health():
    groq_keys = [x.strip() for x in os.getenv("GROQ_API_KEYS", "").split(",") if x.strip()]
    return {
        "ok": True,
        "groq_keys_configured": len(groq_keys),
        "instagram_profile_dir": os.getenv("INSTAGRAM_USER_DATA_DIR", "data/instagram_profile"),
        "campaign_workbook": str(XLSX_PATH),
        "live_metrics_mode": "instagram_web",
    }


@app.get("/api/campaign")
def campaign():
    try:
        return get_campaign()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/campaign/post/{post_id}")
def campaign_post(post_id: int):
    return get_post(post_id)


@app.get("/api/posts/{post_id}/live")
async def post_live(post_id: int):
    post = get_post(post_id)
    post_url = str(post.get("postLink", "")).strip()
    if not post_url:
        raise HTTPException(status_code=400, detail="This Excel record has no POST LINK.")

    try:
        live = await fetch_post_preview(post_url)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Live Instagram fetch failed: {exc}") from exc

    reach = int(post.get("reach", 0) or 0)
    live_engagement = int(live.get("engagement", 0) or 0)
    combined = dict(post)
    combined.update({
        "thumbnailUrl": live.get("thumbnailUrl") or post.get("thumbnailUrl", ""),
        "liveLikes": int(live.get("likes", 0) or 0),
        "liveComments": int(live.get("comments", 0) or 0),
        "liveViews": int(live.get("views", 0) or 0),
        "liveEngagement": live_engagement,
        "engagement": live_engagement if live_engagement else int(post.get("engagement", 0) or 0),
        "liveDataAvailable": True,
        "liveDataSource": "instagram_web",
    })
    # Reach is not a public post-page metric. Keep the workbook reach and explicitly mark the source.
    if reach > 0:
        combined["engagementRateReach"] = round(live_engagement / reach * 100, 2)
    return {"post": combined, "live": live}


@app.post("/api/sentiment/post/{post_id}")
async def sentiment_for_post(post_id: int):
    post = get_post(post_id)
    post_url = str(post.get("postLink", "")).strip()
    if not post_url:
        raise HTTPException(status_code=400, detail="This Excel record does not contain a POST LINK.")

    try:
        comments = await get_comments_for_post(
            username=post.get("username", ""),
            post_url=post_url,
        )
        analysis = await analyze_comments(comments)
        return {
            "post": post,
            "postUrl": post_url,
            "commentsAvailable": len(comments),
            "analysis": analysis,
        }
    except InstagramFetchError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except GroqKeysExhaustedError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
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
