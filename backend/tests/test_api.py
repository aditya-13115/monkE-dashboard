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
from app.main import app


def test_health():
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["version"] == "5.0.0"


def test_campaign_api_returns_real_workbook_data():
    with TestClient(app) as client:
        response = client.get("/api/campaign")
    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["totalPosts"] == 289
    assert len(payload["records"]) == 289
    assert payload["records"][0]["category"] in {
        "Premium Meme",
        "Generic Meme",
        "Paparazzi Meme",
        "Pop-Culture",
        "Marketing",
    }
