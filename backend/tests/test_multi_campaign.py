from __future__ import annotations

import sys
import types
from pathlib import Path

if "groq" not in sys.modules:
    groq_stub = types.ModuleType("groq")

    class RateLimitError(Exception):
        pass

    class AsyncGroq:
        def __init__(self, *args, **kwargs):
            pass

    groq_stub.AsyncGroq = AsyncGroq
    groq_stub.RateLimitError = RateLimitError
    sys.modules["groq"] = groq_stub

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient

from app.campaign_manager import CampaignManager
from app.data_loader import load_campaign
from app.main import app
from app.share_store import ShareLinkStore


def test_seeded_campaign_catalog_has_multiple_brands():
    with TestClient(app) as client:
        response = client.get("/api/admin/campaigns")
    assert response.status_code == 200
    items = response.json()["campaigns"]
    assert {item["brand"] for item in items} >= {"Asian Paints", "dhanda", "aujla"}


def test_new_excel_campaigns_load_from_post_links():
    for brand in ("dhanda", "aujla"):
        workbook = ROOT.parent / "data" / "campaigns" / brand / f"{brand}_campaign_1.xlsx"
        campaign = load_campaign(workbook, brand=brand, campaign_name="Campaign 1", campaign_id=f"{brand}-campaign-1")
        assert len(campaign["records"]) == 5
        assert all(row["postLink"].startswith("https://www.instagram.com/") for row in campaign["records"])
        assert campaign["meta"]["brand"] == brand


def test_campaign_manager_add_delete_round_trip(tmp_path):
    manager = CampaignManager(tmp_path)
    source = tmp_path / "test.xlsx"
    source.write_bytes((ROOT.parent / "data" / "campaigns" / "dhanda" / "dhanda_campaign_1.xlsx").read_bytes())
    item = manager.add_existing("test-brand", "Campaign 1", source)
    assert manager.get(item["id"])["recordCount"] == 5
    deleted = manager.delete(item["id"])
    assert deleted["brand"] == "test-brand"
    assert manager.list() == []


def test_share_store_round_trip(tmp_path):
    store = ShareLinkStore(tmp_path / "shares.json")
    created = store.create("dhanda", ["dhanda-campaign-1"], "POC")
    assert store.get(created["token"])["brand"] == "dhanda"
    assert store.delete(created["token"]) is True
    assert store.get(created["token"]) is None


def test_public_share_returns_readonly_campaign_data():
    from app.main import SHARE_STORE

    item = SHARE_STORE.create("dhanda", ["dhanda-campaign-1-7bc571a1f3"], "Test POC")
    try:
        with TestClient(app) as client:
            response = client.get(f"/api/share/{item['token']}")
        assert response.status_code == 200
        payload = response.json()
        assert payload["readonly"] is True
        assert payload["brand"] == "dhanda"
        assert len(payload["campaigns"]) == 1
        assert payload["campaigns"][0]["meta"]["brand"] == "dhanda"
        assert "source" not in payload["campaigns"][0]["meta"]
    finally:
        SHARE_STORE.delete(item["token"])


def test_admin_upload_endpoint_accepts_excel_and_registers_campaign():
    source = ROOT.parent / "data" / "campaigns" / "dhanda" / "dhanda_campaign_1.xlsx"
    with TestClient(app) as client:
        with source.open("rb") as handle:
            response = client.post(
                "/api/admin/campaigns/upload",
                data={"brand": "upload-test", "campaign": "Campaign 1"},
                files={"file": ("upload-test.xlsx", handle, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            )
    assert response.status_code == 200
    item = response.json()["campaign"]
    try:
        assert item["brand"] == "upload-test"
        assert item["recordCount"] == 5
    finally:
        with TestClient(app) as client:
            client.delete(f"/api/admin/campaigns/{item['id']}")


def test_campaign_sync_endpoint_creates_background_job(monkeypatch):
    from app import main

    async def fake_sync(job_id, campaign_id, force):
        return None

    monkeypatch.setattr(main, "_run_campaign_sync_job", fake_sync)
    with TestClient(app) as client:
        response = client.post("/api/campaigns/dhanda-campaign-1-7bc571a1f3/sync?force=true")
    assert response.status_code == 200
    payload = response.json()
    assert payload["kind"] == "sync"
    assert payload["campaignId"] == "dhanda-campaign-1-7bc571a1f3"
    main.JOB_STORE.finish_active(payload["jobId"])


def test_campaign_sentiment_endpoint_creates_background_job(monkeypatch):
    from app import main

    async def fake_sentiment_job(job_id, campaign_id, force):
        return None

    monkeypatch.setattr(main, "_run_campaign_sentiment_job", fake_sentiment_job)
    with TestClient(app) as client:
        response = client.post("/api/campaigns/dhanda-campaign-1-7bc571a1f3/sentiment?force=true")
    assert response.status_code == 200
    payload = response.json()
    assert payload["kind"] == "campaign-sentiment"
    assert payload["campaignId"] == "dhanda-campaign-1-7bc571a1f3"
    main.JOB_STORE.finish_active(payload["jobId"])


def test_public_share_includes_cached_campaign_sentiment(monkeypatch):
    from app import main

    campaign_id = "dhanda-campaign-1-7bc571a1f3"
    main.CAMPAIGN_SENTIMENT_STORE.set(
        main._campaign_sentiment_key(campaign_id),
        {
            "campaignId": campaign_id,
            "analysis": {
                "summary": {"positive": 4, "neutral": 1, "negative": 0, "positivePct": 80, "neutralPct": 20, "negativePct": 0},
                "topics": [{"topic": "brand", "count": 3}],
                "emotions": [{"emotion": "approval", "count": 3}],
                "mediaMix": [{"type": "Reel", "count": 2}],
                "collection": {"attemptedPosts": 5, "postsWithComments": 4, "totalCommentsCollected": 12, "sampledComments": 5, "reels": 3, "reelsWithComments": 2},
                "postBreakdown": [],
                "sample": {"selected": 5},
                "model": "openai/gpt-oss-20b",
            },
            "generatedAt": 1,
        },
    )
    share = main.SHARE_STORE.create("dhanda", [campaign_id], "Test")
    try:
        with TestClient(app) as client:
            response = client.get(f"/api/share/{share['token']}")
        assert response.status_code == 200
        sentiment = response.json()["campaigns"][0]["campaignSentiment"]
        assert sentiment["summary"]["positive"] == 4
        assert sentiment["collection"]["reelsWithComments"] == 2
        assert "results" not in sentiment
    finally:
        main.SHARE_STORE.delete(share["token"])
        main.CAMPAIGN_SENTIMENT_STORE.delete(main._campaign_sentiment_key(campaign_id))
