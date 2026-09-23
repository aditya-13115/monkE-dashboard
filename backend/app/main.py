from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .comment_source import (
    InstagramFetchError,
    get_comments_for_post,
)
from .data_loader import load_campaign
from .sentiment import (
    GroqKeysExhaustedError,
    analyze_comments,
)

load_dotenv()


BASE_DIR = Path(__file__).resolve().parents[2]

DEFAULT_XLSX = (
    BASE_DIR
    / "data"
    / "ASIAN PAINTS (1).xlsx"
)


XLSX_PATH = Path(
    os.getenv(
        "CAMPAIGN_XLSX_PATH",
        str(DEFAULT_XLSX),
    )
)


if not XLSX_PATH.is_absolute():
    XLSX_PATH = (
        BASE_DIR / XLSX_PATH
    ).resolve()


app = FastAPI(
    title="Monk-E Campaign Intelligence API",
    version="2.0.0",
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
    comment: str = Field(
        min_length=1
    )

    likes: int = 0

    post_url: str = ""

    username: str = ""


class SentimentRequest(BaseModel):
    comments: list[Comment]

    sample_size: int | None = Field(
        default=None,
        ge=10,
        le=100,
    )


def get_campaign() -> dict[str, Any]:
    global campaign_cache

    if campaign_cache is None:

        if not XLSX_PATH.exists():

            raise FileNotFoundError(
                "Campaign workbook not found: "
                f"{XLSX_PATH}"
            )

        campaign_cache = load_campaign(
            XLSX_PATH
        )

    return campaign_cache


def get_post(
    post_id: int,
) -> dict[str, Any]:

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
        for key in os.getenv(
            "GROQ_API_KEYS",
            "",
        ).split(",")
        if key.strip()
    ]

    return {
        "ok": True,
        "groq_keys_configured": len(
            groq_keys
        ),
        "comment_source": "instagram_web",
        "campaign_workbook": str(
            XLSX_PATH
        ),
    }


@app.get("/api/campaign")
def campaign():

    try:

        return get_campaign()

    except Exception as exc:

        raise HTTPException(
            status_code=500,
            detail=str(exc),
        )


@app.get("/api/campaign/post/{post_id}")
def campaign_post(
    post_id: int,
):

    return get_post(post_id)


@app.post("/api/sentiment/post/{post_id}")
async def sentiment_for_post(
    post_id: int,
):

    post = get_post(post_id)

    post_url = str(
        post.get("postLink", "")
    ).strip()

    if not post_url:

        raise HTTPException(
            status_code=400,
            detail=(
                "This Excel record does not contain "
                "a POST LINK."
            ),
        )

    try:

        # IMPORTANT:
        # The exact POST LINK from the Excel is used.
        comments = await get_comments_for_post(
            username=post.get(
                "username",
                "",
            ),
            post_url=post_url,
        )

        if not comments:

            raise HTTPException(
                status_code=404,
                detail=(
                    "No public comments were found "
                    "on this Instagram post."
                ),
            )

        # Groq does the sampling + analysis.
        analysis = await analyze_comments(
            comments
        )

        return {
            "post": post,
            "postUrl": post_url,
            "commentsAvailable": len(
                comments
            ),
            "analysis": analysis,
        }

    except InstagramFetchError as exc:

        raise HTTPException(
            status_code=503,
            detail=str(exc),
        )

    except GroqKeysExhaustedError as exc:

        raise HTTPException(
            status_code=429,
            detail=str(exc),
        )

    except HTTPException:

        raise

    except RuntimeError as exc:

        raise HTTPException(
            status_code=503,
            detail=str(exc),
        )

    except Exception as exc:

        raise HTTPException(
            status_code=500,
            detail=(
                "Post sentiment analysis failed: "
                f"{exc}"
            ),
        )


# Optional direct JSON sentiment endpoint.
# The frontend does not need this for the post-click workflow,
# but keeping it makes the API useful for future integrations.
@app.post("/api/sentiment/analyze")
async def sentiment(
    req: SentimentRequest,
):

    try:

        return await analyze_comments(
            [
                comment.model_dump()
                for comment in req.comments
            ],
            req.sample_size,
        )

    except GroqKeysExhaustedError as exc:

        raise HTTPException(
            status_code=429,
            detail=str(exc),
        )

    except RuntimeError as exc:

        raise HTTPException(
            status_code=503,
            detail=str(exc),
        )

    except Exception as exc:

        raise HTTPException(
            status_code=500,
            detail=(
                "Sentiment analysis failed: "
                f"{exc}"
            ),
        )