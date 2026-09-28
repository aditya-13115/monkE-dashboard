from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any


def aggregate_campaign_sentiment(
    analysis: dict[str, Any],
    sampled_comments: list[dict[str, Any]],
    *,
    attempted_posts: int,
    posts_with_comments: int,
    total_comments_collected: int,
    reel_posts: int,
    reel_posts_with_comments: int,
) -> dict[str, Any]:
    results = analysis.get("results") if isinstance(analysis, dict) else []
    results = results if isinstance(results, list) else []

    post_map: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "postId": None,
        "postType": "Post",
        "username": "",
        "postUrl": "",
        "sampled": 0,
        "positive": 0,
        "neutral": 0,
        "negative": 0,
    })

    meta_by_id: dict[int, dict[str, Any]] = {}
    for row in sampled_comments:
        try:
            rid = int(row.get("id"))
        except (TypeError, ValueError):
            continue
        meta_by_id[rid] = row

    for result in results:
        try:
            rid = int(result.get("id"))
        except (TypeError, ValueError):
            continue
        source = meta_by_id.get(rid, {})
        post_id = str(source.get("sourcePostId") or source.get("post_id") or "unknown")
        bucket = post_map[post_id]
        bucket["postId"] = source.get("sourcePostId")
        bucket["postType"] = source.get("postType", "Post")
        bucket["username"] = source.get("username", "")
        bucket["postUrl"] = source.get("post_url", "")
        bucket["sampled"] += 1
        sentiment = str(result.get("sentiment", "neutral"))
        if sentiment not in {"positive", "neutral", "negative"}:
            sentiment = "neutral"
        bucket[sentiment] += 1

    post_breakdown = []
    for item in post_map.values():
        total = item["sampled"]
        post_breakdown.append(
            {
                **item,
                "positivePct": round(item["positive"] / total * 100, 1) if total else 0,
                "neutralPct": round(item["neutral"] / total * 100, 1) if total else 0,
                "negativePct": round(item["negative"] / total * 100, 1) if total else 0,
            }
        )
    post_breakdown.sort(key=lambda row: (-row["sampled"], str(row.get("username", ""))))

    emotions = Counter(str(row.get("emotion", "neutral") or "neutral") for row in results)
    topics = Counter(str(row.get("topic", "other") or "other") for row in results)
    media = Counter(str(row.get("postType", "Post") or "Post") for row in sampled_comments)

    collection = {
        "attemptedPosts": attempted_posts,
        "postsWithComments": posts_with_comments,
        "postsWithoutComments": max(0, attempted_posts - posts_with_comments),
        "totalCommentsCollected": total_comments_collected,
        "sampledComments": len(sampled_comments),
        "reels": reel_posts,
        "reelsWithComments": reel_posts_with_comments,
        "reelsWithoutComments": max(0, reel_posts - reel_posts_with_comments),
    }

    return {
        "summary": analysis.get("summary", {}),
        "topics": analysis.get("topics", []),
        "emotions": [
            {"emotion": emotion, "count": count}
            for emotion, count in emotions.most_common(12)
        ],
        "mediaMix": [
            {"type": media_type, "count": count}
            for media_type, count in media.items()
        ],
        "collection": collection,
        "postBreakdown": post_breakdown[:50],
        "sample": analysis.get("sample", {}),
        "model": analysis.get("model"),
        "partial": bool(analysis.get("partial")),
        "errors": list(analysis.get("errors", []))[:5],
    }
