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
    assert normalize_instagram_url("https://www.instagram.com/reels/XYZ/?igsh=abc") == "https://www.instagram.com/reel/XYZ"


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


def test_embedded_instagram_json_comment_extraction():
    browser = InstagramBrowser()
    payload = {
        "comments_connection": {
            "edges": [
                {
                    "node": {
                        "pk": "1",
                        "user": {"username": "alice"},
                        "text": "great reel",
                        "comment_like_count": 3,
                        "__typename": "XIGComment",
                    }
                }
            ]
        }
    }
    output = []
    browser._extract_comments_from_json_sync(
        payload,
        "https://www.instagram.com/reel/XYZ",
        output,
        set(),
    )
    assert len(output) == 1
    assert output[0]["username"] == "alice"
    assert output[0]["comment"] == "great reel"
    assert output[0]["likes"] == 3


def test_reel_debug_html_embedded_comments_are_extracted():
    fixture = Path('/mnt/data/work-debug/instagram_debug.html')
    if not fixture.exists():
        return
    browser = InstagramBrowser()
    output = []
    browser._extract_comments_from_html_sync(
        fixture.read_text(encoding='utf-8', errors='ignore'),
        'https://www.instagram.com/reel/DXHOcduDxID',
        output,
        set(),
    )
    assert len(output) >= 2
    assert {row['username'] for row in output} >= {'mamtasuman9649', 'callmevertikaah'}


def test_embedded_json_metrics_are_parsed():
    browser = InstagramBrowser()
    metrics = {'likes': 0, 'comments': 0, 'views': 0, 'shares': 0, 'saves': 0}
    browser._extract_metrics_from_json_sync(
        {
            'like_count': 1234,
            'comment_count': 87,
            'play_count': 98765,
            'reshare_count': 12,
            'save_count': 34,
        },
        metrics,
    )
    assert metrics == {'likes': 1234, 'comments': 87, 'views': 98765, 'shares': 12, 'saves': 34}


def test_campaign_sampling_can_keep_all_presampled_comments():
    from app.sentiment import sample_comments
    source = [
        {'comment': f'comment {i}', 'likes': 0, 'username': f'u{i}', 'sourcePostId': i, 'postType': 'Reel'}
        for i in range(120)
    ]
    selected, _ = sample_comments(source, sample_size=80, max_sample_size=500, randomize=False)
    assert len(selected) == 80
    assert selected[0]['sourcePostId'] == 0


def test_campaign_sample_ids_are_preserved_for_cross_post_aggregation():
    from app.sentiment import sample_comments
    source = [
        {"id": 11, "comment": "one", "likes": 0, "sourcePostId": 1, "postType": "Reel"},
        {"id": 12, "comment": "two", "likes": 0, "sourcePostId": 2, "postType": "Post"},
    ]
    selected, _ = sample_comments(source, sample_size=2, max_sample_size=500, randomize=False)
    assert [row["id"] for row in selected] == [11, 12]
