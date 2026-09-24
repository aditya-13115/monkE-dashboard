from __future__ import annotations

import json
import sys
import types
from pathlib import Path


# The build environment used for static tests may not have the Groq wheel
# installed. This tiny stub lets us import and test the application contract
# without making any network request.
if "groq" not in sys.modules:
    groq_stub = types.ModuleType("groq")

    class RateLimitError(Exception):
        pass

    class AsyncGroq:  # pragma: no cover - only import compatibility
        def __init__(self, *args, **kwargs):
            pass

    groq_stub.AsyncGroq = AsyncGroq
    groq_stub.RateLimitError = RateLimitError
    sys.modules["groq"] = groq_stub


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.cache_store import JsonCacheStore
from app.data_loader import load_campaign
from app.instagram_web import InstagramBrowser, normalize_instagram_url
from app.sentiment import _normalize_results, sample_comments


def test_campaign_loader_matches_workbook():
    workbook = ROOT.parent / "data" / "ASIAN PAINTS (1).xlsx"
    campaign = load_campaign(workbook)
    assert campaign["summary"]["totalPosts"] == 289
    assert campaign["summary"]["totalFollowers"] == 317471042
    assert campaign["summary"]["totalReach"] == 17796378
    assert campaign["summary"]["totalEngagement"] == 902280
    assert len(campaign["records"]) == 289
    assert campaign["records"][0]["postLink"].startswith("https://www.instagram.com/")


def test_persistent_json_cache_round_trip(tmp_path):
    cache = JsonCacheStore(tmp_path / "cache.json")
    cache.set("post", {"likes": 42, "commentsData": []})
    assert cache.get("post") == {"likes": 42, "commentsData": []}
    assert cache.age_seconds("post") is not None

    other = JsonCacheStore(tmp_path / "cache.json")
    assert other.get("post")["likes"] == 42


def test_instagram_url_normalization():
    assert normalize_instagram_url("https://www.instagram.com/p/ABC123/?utm_source=x") == "https://www.instagram.com/p/ABC123"
    assert normalize_instagram_url("https://www.instagram.com/reel/XYZ/") == "https://www.instagram.com/reel/XYZ"


def test_metric_parser_keeps_like_and_comment_counts_in_order():
    body = """
    Like
    325
    Comment
    18
    Share
    Save
    April 14
    """
    browser = InstagramBrowser()
    metrics = browser._extract_metrics_sync(None, body, "")
    assert metrics["likes"] == 325
    assert metrics["comments"] == 18
    assert metrics["shares"] == 0


def test_comment_parser_handles_current_debug_page_shape():
    body = """
    log.kya.sochenge
    Load more comments
    mamtasuman9649
    23w
    😂😂
    Like
    Reply
    callmevertikaah
    23w
    😂😂😂 Aapni beizaati kra li
    Like
    Reply
    Like
    325
    Comment
    18
    Share
    Save
    April 14
    Log in to like or comment.
    """
    browser = InstagramBrowser()
    comments = browser._extract_comments_from_text_sync(
        body,
        "https://www.instagram.com/p/DXHOcduDxID",
    )
    assert len(comments) == 2
    assert comments[0]["username"] == "mamtasuman9649"
    assert comments[0]["comment"] == "😂😂"
    assert comments[1]["username"] == "callmevertikaah"
    assert comments[1]["comment"] == "😂😂😂 Aapni beizaati kra li"


def test_sentiment_normalizes_model_items_wrapper():
    batch = [
        {"id": 1, "comment": "great", "likes": 2},
        {"id": 2, "comment": "bad", "likes": 1},
    ]
    parsed = {
        "results": {
            "items": [
                {
                    "id": 1,
                    "sentiment": "positive",
                    "confidence": 0.95,
                    "topic": "brand",
                    "emotion": "approval",
                    "reason": "Positive wording.",
                }
            ]
        }
    }
    result = _normalize_results(parsed, batch)
    assert result[0]["id"] == 1
    assert result[0]["sentiment"] == "positive"


def test_sample_is_bounded_and_never_mutates_input():
    source = [
        {"comment": f"comment {i}", "likes": i, "username": f"u{i}"}
        for i in range(150)
    ]
    selected, has_likes = sample_comments(source, sample_size=100, seed=123)
    assert len(selected) == 100
    assert has_likes is True
    assert len(source) == 150
