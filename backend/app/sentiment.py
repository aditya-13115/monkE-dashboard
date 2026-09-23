from __future__ import annotations

import asyncio
import json
import math
import os
import random
from collections import Counter
from typing import Any

from dotenv import load_dotenv
from groq import AsyncGroq, RateLimitError

load_dotenv()

MODEL = os.getenv("GROQ_SENTIMENT_MODEL", "openai/gpt-oss-20b")
SAMPLE_MIN = 50
SAMPLE_MAX = 100
LIKED_SHARE = 0.70
BATCH_SIZE = 25
CONCURRENCY = max(1, int(os.getenv("GROQ_SENTIMENT_CONCURRENCY", "2")))


class GroqKeysExhaustedError(RuntimeError):
    pass


SYSTEM_PROMPT = """You are the comment-insights engine for an influencer campaign dashboard.
Analyze Instagram comments about a brand campaign.

Rules:
- sentiment must be exactly positive, neutral, or negative.
- confidence must be between 0 and 1.
- topic should be a short campaign-relevant label such as product, creative, price,
  quality, color, service, brand, influencer, giveaway, complaint, spam, or other.
- emotion should be one short label such as delight, curiosity, approval, confusion,
  disappointment, anger, neutral, amusement, or other.
- Treat slang, Hinglish, emojis, and short comments carefully.
- Do not infer demographics.
- Return one result for every input id.
"""


SCHEMA = {
    "type": "object",
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "sentiment": {
                        "type": "string",
                        "enum": ["positive", "neutral", "negative"],
                    },
                    "confidence": {"type": "number"},
                    "topic": {"type": "string"},
                    "emotion": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": [
                    "id",
                    "sentiment",
                    "confidence",
                    "topic",
                    "emotion",
                    "reason",
                ],
                "additionalProperties": False,
            },
        }
    },
    "required": ["results"],
    "additionalProperties": False,
}


def get_groq_api_keys() -> list[str]:
    raw = os.getenv("GROQ_API_KEYS", "")
    return [key.strip() for key in raw.split(",") if key.strip()]


def create_groq_clients() -> list[AsyncGroq]:
    keys = get_groq_api_keys()
    if not keys:
        raise RuntimeError(
            "GROQ_API_KEYS is not configured. "
            "Add one or more comma-separated Groq API keys to backend/.env."
        )

    # max_retries=0 is intentional: application-level failover handles 429s.
    return [AsyncGroq(api_key=key, max_retries=0) for key in keys]


def sample_comments(
    comments: list[dict[str, Any]],
    sample_size: int | None = None,
    seed: int | None = None,
) -> list[dict[str, Any]]:
    clean: list[dict[str, Any]] = []

    for idx, item in enumerate(comments):
        text = str(item.get("comment", "")).strip()
        if not text:
            continue

        try:
            likes = max(0, int(item.get("likes", 0) or 0))
        except (ValueError, TypeError):
            likes = 0

        clean.append(
            {
                "id": idx + 1,
                "comment": text[:1200],
                "likes": likes,
                "post_url": str(item.get("post_url", "") or ""),
                "username": str(item.get("username", "") or ""),
            }
        )

    if not clean:
        return []

    rng = random.Random(seed)
    target = (
        sample_size
        if sample_size is not None
        else SAMPLE_MAX
        if len(clean) >= SAMPLE_MAX
        else SAMPLE_MIN
        if len(clean) >= SAMPLE_MIN
        else len(clean)
    )
    target = min(target, len(clean), SAMPLE_MAX)
    if target <= 0:
        return []

    ranked = sorted(clean, key=lambda x: x["likes"], reverse=True)
    liked_pool_size = min(
        len(ranked),
        max(target * 2, math.ceil(len(ranked) * 0.5)),
    )
    liked_pool = ranked[:liked_pool_size]
    liked_n = min(len(liked_pool), round(target * LIKED_SHARE))
    random_n = target - liked_n

    weights = [math.sqrt(c["likes"] + 1) for c in liked_pool]
    liked_selected: list[dict[str, Any]] = []

    if liked_n:
        if sum(weights) == 0:
            liked_selected = rng.sample(
                liked_pool,
                min(liked_n, len(liked_pool)),
            )
        else:
            pool = liked_pool[:]
            pool_weights = weights[:]
            for _ in range(liked_n):
                if not pool:
                    break
                chosen = rng.choices(pool, weights=pool_weights, k=1)[0]
                index = pool.index(chosen)
                liked_selected.append(chosen)
                pool.pop(index)
                pool_weights.pop(index)

    selected_ids = {comment["id"] for comment in liked_selected}
    fallback_pool = [comment for comment in clean if comment["id"] not in selected_ids]
    random_selected = (
        rng.sample(fallback_pool, min(random_n, len(fallback_pool)))
        if random_n > 0
        else []
    )

    selected = liked_selected + random_selected
    rng.shuffle(selected)
    return selected


async def _analyze_batch(
    client: AsyncGroq,
    batch: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    payload = [
        {
            "id": row["id"],
            "comment": row["comment"],
            "likes": row["likes"],
        }
        for row in batch
    ]

    response = await client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "Classify these comments. Return JSON matching the supplied schema.\n"
                    + json.dumps(payload, ensure_ascii=False)
                ),
            },
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "comment_sentiment_batch",
                "strict": True,
                "schema": SCHEMA,
            },
        },
        temperature=0,
    )

    content = response.choices[0].message.content or '{"results":[]}'
    return json.loads(content)["results"]


async def _analyze_batch_with_failover(
    clients: list[AsyncGroq],
    batch: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    for index, client in enumerate(clients):
        try:
            return await _analyze_batch(client, batch)
        except RateLimitError:
            print(
                f"[Groq] key {index + 1}/{len(clients)} hit 429; "
                "trying next configured key without SDK retry."
            )
            continue

    raise GroqKeysExhaustedError(
        "All configured Groq API keys are currently rate limited."
    )


async def analyze_comments(
    comments: list[dict[str, Any]],
    sample_size: int | None = None,
) -> dict[str, Any]:
    selected = sample_comments(comments, sample_size=sample_size)

    if not selected:
        return {
            "model": MODEL,
            "sample": {
                "requested": sample_size or SAMPLE_MAX,
                "selected": 0,
                "likedShare": 0,
                "strategy": "70% weighted toward higher-liked comments + 30% random",
            },
            "results": [],
            "summary": {
                "positive": 0,
                "neutral": 0,
                "negative": 0,
                "positivePct": 0,
                "neutralPct": 0,
                "negativePct": 0,
            },
            "topics": [],
        }

    clients = create_groq_clients()
    batches = [
        selected[i : i + BATCH_SIZE]
        for i in range(0, len(selected), BATCH_SIZE)
    ]
    semaphore = asyncio.Semaphore(min(CONCURRENCY, len(batches)))

    async def limited(batch: list[dict[str, Any]]) -> list[dict[str, Any]]:
        async with semaphore:
            return await _analyze_batch_with_failover(clients, batch)

    nested = await asyncio.gather(*(limited(batch) for batch in batches))
    analyses = [item for sublist in nested for item in sublist]

    by_id = {analysis["id"]: analysis for analysis in analyses}
    rows = []

    for comment in selected:
        analysis = by_id.get(
            comment["id"],
            {
                "id": comment["id"],
                "sentiment": "neutral",
                "confidence": 0.0,
                "topic": "other",
                "emotion": "neutral",
                "reason": "No model result.",
            },
        )
        rows.append({**comment, **analysis})

    counts = Counter(row["sentiment"] for row in rows)
    topics = Counter(row["topic"] for row in rows)
    total = len(rows)
    liked = sum(1 for row in selected if row["likes"] > 0)

    return {
        "model": MODEL,
        "sample": {
            "requested": sample_size or SAMPLE_MAX,
            "selected": total,
            "likedShare": round(liked / total * 100, 1) if total else 0,
            "strategy": "70% weighted toward higher-liked comments + 30% random",
        },
        "results": rows,
        "summary": {
            "positive": counts.get("positive", 0),
            "neutral": counts.get("neutral", 0),
            "negative": counts.get("negative", 0),
            "positivePct": round(counts.get("positive", 0) / total * 100, 1) if total else 0,
            "neutralPct": round(counts.get("neutral", 0) / total * 100, 1) if total else 0,
            "negativePct": round(counts.get("negative", 0) / total * 100, 1) if total else 0,
        },
        "topics": [
            {"topic": topic, "count": count}
            for topic, count in topics.most_common(10)
        ],
    }
