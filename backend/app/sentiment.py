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
SAMPLE_SIZE = max(10, min(100, int(os.getenv("GROQ_SENTIMENT_SAMPLE_SIZE", "75"))))
BATCH_SIZE = max(10, min(50, int(os.getenv("GROQ_SENTIMENT_BATCH_SIZE", "40"))))
CONCURRENCY = max(1, int(os.getenv("GROQ_SENTIMENT_CONCURRENCY", "2")))
MAX_RETRIES = max(0, int(os.getenv("GROQ_SENTIMENT_RETRIES", "1")))
LIKED_SHARE = 0.70


class GroqKeysExhaustedError(RuntimeError):
    pass


SYSTEM_PROMPT = """
You are the comment-insights engine for an influencer campaign dashboard.
Analyze Instagram comments about a brand campaign.

Return ONLY JSON.
The top-level object MUST contain a key named `results`.
`results` MUST be an array.
NEVER return `results` as an object and NEVER wrap it in `items`.

For every input comment, return exactly one result using the same id.

Each result must contain:
- id: integer
- sentiment: one of positive, neutral, negative
- confidence: number between 0 and 1
- topic: short label such as product, creative, price, quality, color,
  service, brand, influencer, giveaway, complaint, spam, or other
- emotion: short label such as delight, curiosity, approval, confusion,
  disappointment, anger, neutral, amusement, or other
- reason: concise explanation

Treat slang, Hinglish, emojis, and short comments carefully.
Do not infer demographics or sensitive personal information.
""".strip()


def _keys() -> list[str]:
    return [
        key.strip()
        for key in os.getenv("GROQ_API_KEYS", "").split(",")
        if key.strip()
    ]


def _clients() -> list[AsyncGroq]:
    keys = _keys()
    if not keys:
        raise RuntimeError(
            "GROQ_API_KEYS is not configured. Add one or more comma-separated Groq keys to backend/.env."
        )
    return [AsyncGroq(api_key=key, max_retries=0) for key in keys]


def sample_comments(
    comments: list[dict[str, Any]],
    sample_size: int | None = None,
    seed: int | None = None,
) -> tuple[list[dict[str, Any]], bool]:
    cleaned: list[dict[str, Any]] = []
    for index, item in enumerate(comments):
        text = str(item.get("comment", "")).strip()
        if not text:
            continue
        try:
            likes = max(0, int(item.get("likes", 0) or 0))
        except (TypeError, ValueError):
            likes = 0
        cleaned.append(
            {
                "id": index + 1,
                "comment": text[:1200],
                "likes": likes,
                "post_url": str(item.get("post_url", "") or ""),
                "username": str(item.get("username", "") or ""),
            }
        )

    if not cleaned:
        return [], False

    rng = random.Random(seed)
    target = min(sample_size or SAMPLE_SIZE, len(cleaned), 100)
    has_like_signal = any(row["likes"] > 0 for row in cleaned)

    if target <= 0:
        return [], has_like_signal

    # When per-comment likes exist, bias ~70% toward the higher-liked pool and
    # keep ~30% random to avoid only reading the most popular opinions.
    if has_like_signal and len(cleaned) > 1:
        ranked = sorted(cleaned, key=lambda row: row["likes"], reverse=True)
        liked_pool = ranked[: min(len(ranked), max(target * 2, target))]
        liked_n = min(len(liked_pool), round(target * LIKED_SHARE))
        random_n = target - liked_n

        pool = liked_pool[:]
        weights = [math.sqrt(row["likes"] + 1) for row in pool]
        liked_selected: list[dict[str, Any]] = []
        for _ in range(liked_n):
            if not pool:
                break
            choice = rng.choices(pool, weights=weights, k=1)[0]
            idx = pool.index(choice)
            liked_selected.append(choice)
            pool.pop(idx)
            weights.pop(idx)

        selected_ids = {row["id"] for row in liked_selected}
        random_pool = [row for row in cleaned if row["id"] not in selected_ids]
        selected = liked_selected + rng.sample(
            random_pool,
            min(random_n, len(random_pool)),
        )
        rng.shuffle(selected)
        return selected, True

    return rng.sample(cleaned, target), False


def _normalize_results(parsed: Any, batch: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Accept the model's correct array shape and repair the common items wrapper."""
    if not isinstance(parsed, dict):
        return []

    raw = parsed.get("results")
    if isinstance(raw, list):
        items = raw
    elif isinstance(raw, dict) and isinstance(raw.get("items"), list):
        items = raw["items"]
    elif isinstance(parsed.get("items"), list):
        items = parsed["items"]
    else:
        items = []

    valid_ids = {row["id"] for row in batch}
    seen: set[int] = set()
    normalized: list[dict[str, Any]] = []

    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            item_id = int(item.get("id"))
        except (TypeError, ValueError):
            continue
        if item_id not in valid_ids or item_id in seen:
            continue
        seen.add(item_id)

        sentiment = str(item.get("sentiment", "neutral")).strip().lower()
        if sentiment not in {"positive", "neutral", "negative"}:
            sentiment = "neutral"
        try:
            confidence = float(item.get("confidence", 0))
        except (TypeError, ValueError):
            confidence = 0.0
        confidence = max(0.0, min(1.0, confidence))
        normalized.append(
            {
                "id": item_id,
                "sentiment": sentiment,
                "confidence": confidence,
                "topic": str(item.get("topic", "other")).strip() or "other",
                "emotion": str(item.get("emotion", "neutral")).strip() or "neutral",
                "reason": str(item.get("reason", "")).strip(),
            }
        )
    return normalized


async def _call_batch(client: AsyncGroq, batch: list[dict[str, Any]]) -> list[dict[str, Any]]:
    payload = [
        {"id": row["id"], "comment": row["comment"], "likes": row["likes"]}
        for row in batch
    ]

    last_error: Exception | None = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            response = await client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": (
                            "Classify these comments. Return only JSON. The top-level "
                            "key is `results`, and `results` MUST be an array. Do not "
                            "return `results: {items: [...]}`.\n\n"
                            + json.dumps(payload, ensure_ascii=False)
                        ),
                    },
                ],
                response_format={"type": "json_object"},
                temperature=0,
                max_tokens=6000,
            )
            content = response.choices[0].message.content or '{"results":[]}'
            try:
                parsed = json.loads(content)
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"Groq returned invalid JSON: {exc}") from exc
            return _normalize_results(parsed, batch)
        except RateLimitError:
            raise
        except Exception as exc:
            last_error = exc
            if attempt < MAX_RETRIES:
                await asyncio.sleep(0.5 * (attempt + 1))
    assert last_error is not None
    raise last_error


async def _call_with_failover(clients: list[AsyncGroq], batch: list[dict[str, Any]]) -> list[dict[str, Any]]:
    last_error: Exception | None = None
    for index, client in enumerate(clients):
        try:
            print(
                f"[Sentiment] Groq batch starting: {len(batch)} comments "
                f"(key {index + 1}/{len(clients)})",
                flush=True,
            )
            result = await _call_batch(client, batch)
            print(
                f"[Sentiment] Groq batch complete: {len(result)}/{len(batch)} results",
                flush=True,
            )
            return result
        except RateLimitError as exc:
            last_error = exc
            print(
                f"[Sentiment] Groq key {index + 1} rate limited; trying next key.",
                flush=True,
            )
            continue
        except Exception as exc:
            last_error = exc
            print(
                f"[Sentiment] Groq batch failed: {exc}",
                flush=True,
            )
            break
    if isinstance(last_error, RateLimitError):
        raise GroqKeysExhaustedError("All configured Groq API keys are currently rate limited.") from last_error
    raise RuntimeError(str(last_error) if last_error else "Groq analysis failed.")


async def analyze_comments(
    comments: list[dict[str, Any]],
    sample_size: int | None = None,
) -> dict[str, Any]:
    selected, has_like_signal = sample_comments(comments, sample_size=sample_size)
    print(
        f"[Sentiment] selected {len(selected)} of {len(comments)} available comments",
        flush=True,
    )

    if not selected:
        return {
            "model": MODEL,
            "sample": {
                "requested": sample_size or SAMPLE_SIZE,
                "selected": 0,
                "likedShare": 0,
                "hasLikeSignal": False,
                "strategy": "No usable comments were available.",
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

    clients = _clients()
    batches = [selected[i : i + BATCH_SIZE] for i in range(0, len(selected), BATCH_SIZE)]
    semaphore = asyncio.Semaphore(min(CONCURRENCY, len(batches)))

    async def limited(index: int, batch: list[dict[str, Any]]) -> list[dict[str, Any]]:
        async with semaphore:
            print(
                f"[Sentiment] analyzing batch {index + 1}/{len(batches)}",
                flush=True,
            )
            return await _call_with_failover(clients, batch)

    responses = await asyncio.gather(
        *(limited(index, batch) for index, batch in enumerate(batches)),
        return_exceptions=True,
    )

    analyses: list[dict[str, Any]] = []
    failures: list[str] = []
    for response in responses:
        if isinstance(response, Exception):
            failures.append(str(response))
        else:
            analyses.extend(response)

    # Never throw away a complete UI result just because one batch failed.
    # Missing IDs receive an explicit neutral fallback and the error is exposed
    # in the metadata below.
    by_id = {row["id"]: row for row in analyses}
    results: list[dict[str, Any]] = []
    for comment in selected:
        result = by_id.get(
            comment["id"],
            {
                "id": comment["id"],
                "sentiment": "neutral",
                "confidence": 0.0,
                "topic": "other",
                "emotion": "neutral",
                "reason": "No model result was returned for this comment.",
            },
        )
        results.append({**comment, **result})

    counts = Counter(row["sentiment"] for row in results)
    topics = Counter(row["topic"] for row in results)
    total = len(results)
    liked = sum(1 for row in selected if row["likes"] > 0)

    analysis = {
        "model": MODEL,
        "sample": {
            "requested": sample_size or SAMPLE_SIZE,
            "selected": total,
            "likedShare": round(liked / total * 100, 1) if total else 0,
            "hasLikeSignal": has_like_signal,
            "strategy": (
                "70% weighted toward higher-liked comments + 30% random"
                if has_like_signal
                else "Random sample because Instagram did not expose per-comment like counts."
            ),
        },
        "results": results,
        "summary": {
            "positive": counts.get("positive", 0),
            "neutral": counts.get("neutral", 0),
            "negative": counts.get("negative", 0),
            "positivePct": round(counts.get("positive", 0) / total * 100, 1) if total else 0,
            "neutralPct": round(counts.get("neutral", 0) / total * 100, 1) if total else 0,
            "negativePct": round(counts.get("negative", 0) / total * 100, 1) if total else 0,
        },
        "topics": [{"topic": topic, "count": count} for topic, count in topics.most_common(10)],
        "partial": bool(failures),
        "errors": failures[:3],
    }

    print(
        "[Sentiment] complete: "
        f"positive={analysis['summary']['positive']} "
        f"neutral={analysis['summary']['neutral']} "
        f"negative={analysis['summary']['negative']}",
        flush=True,
    )
    return analysis
