from __future__ import annotations

import csv
import io
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .comment_source import (
    CommentsNotConfiguredError,
    get_comments_for_post,
)
from .data_loader import load_campaign
from .sentiment import GroqKeysExhaustedError, analyze_comments

load_dotenv()

BASE_DIR = Path(__file__).resolve().parents[2]
DEFAULT_XLSX = BASE_DIR / "data" / "ASIAN PAINTS (1).xlsx"

XLSX_PATH = Path(
    os.getenv(
        "CAMPAIGN_XLSX_PATH",
        str(DEFAULT_XLSX),
    )
)
if not XLSX_PATH.is_absolute():
    XLSX_PATH = (BASE_DIR / XLSX_PATH).resolve()

app = FastAPI(
    title="Monk-E Campaign Intelligence API",
    version="1.1.0",
)

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


def get_campaign():
    global campaign_cache
    if campaign_cache is None:
        if not XLSX_PATH.exists():
            raise FileNotFoundError(
                f"Campaign workbook not found: {XLSX_PATH}"
            )
        campaign_cache = load_campaign(XLSX_PATH)
    return campaign_cache


def get_post(post_id: int) -> dict[str, Any]:
    campaign = get_campaign()
    for record in campaign["records"]:
        if int(record["id"]) == post_id:
            return record
    raise HTTPException(
        status_code=404,
        detail=f"Post {post_id} was not found.",
    )


@app.get("/health")
def health():
    groq_keys = [
        key.strip()
        for key in os.getenv("GROQ_API_KEYS", "").split(",")
        if key.strip()
    ]
    return {
        "ok": True,
        "groq_keys_configured": len(groq_keys),
        "instagram_comments_connected": bool(
            os.getenv("META_ACCESS_TOKEN")
            and os.getenv("META_IG_USER_ID")
        ),
    }


@app.get("/api/campaign")
def campaign():
    try:
        return get_campaign()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/sentiment/post/{post_id}")
async def sentiment_for_post(post_id: int):
    post = get_post(post_id)

    try:
        comments = await get_comments_for_post(
            username=post["username"],
            post_url=post["postLink"],
        )

        if not comments:
            raise HTTPException(
                status_code=404,
                detail=(
                    "No comments were found for this post. "
                    "The Instagram account may be private, unavailable to the connected API, "
                    "or the post has no comments."
                ),
            )

        result = await analyze_comments(comments)

        return {
            "post": post,
            "commentsAvailable": len(comments),
            "analysis": result,
        }

    except CommentsNotConfiguredError as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        )
    except GroqKeysExhaustedError as exc:
        raise HTTPException(status_code=429, detail=str(exc))
    except HTTPException:
        raise
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Post sentiment analysis failed: {exc}",
        )


# Kept for backwards compatibility with the old CSV workflow.
@app.post("/api/sentiment/analyze")
async def sentiment(req: SentimentRequest):
    try:
        return await analyze_comments(
            [comment.model_dump() for comment in req.comments],
            req.sample_size,
        )
    except GroqKeysExhaustedError as exc:
        raise HTTPException(status_code=429, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Sentiment analysis failed: {exc}",
        )


# Kept for backwards compatibility with the old CSV workflow.
@app.post("/api/sentiment/analyze-csv")
async def sentiment_csv(
    file: UploadFile = File(...),
    sample_size: int | None = None,
):
    raw = await file.read()

    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("utf-8", errors="replace")

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise HTTPException(
            status_code=400,
            detail="CSV must contain a 'comment' column.",
        )

    normalized_headers = {
        header.strip().lower()
        for header in reader.fieldnames
        if header
    }
    if "comment" not in normalized_headers:
        raise HTTPException(
            status_code=400,
            detail="CSV must contain a 'comment' column.",
        )

    comments = []
    for row in reader:
        normalized = {
            str(key).strip().lower(): value
            for key, value in row.items()
            if key is not None
        }
        comments.append(
            {
                "comment": normalized.get("comment", ""),
                "likes": normalized.get("likes", 0),
                "post_url": normalized.get("post_url", ""),
                "username": normalized.get("username", ""),
            }
        )

    try:
        return await analyze_comments(
            comments,
            sample_size,
        )
    except GroqKeysExhaustedError as exc:
        raise HTTPException(status_code=429, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Sentiment analysis failed: {exc}",
        )
