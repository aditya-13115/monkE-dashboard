# Monk-E Campaign Intelligence Dashboard

A production-oriented campaign analytics dashboard for Monk-E's influencer campaigns.

## What it does

- Imports the provided Excel workbook and normalizes the five creator buckets.
- Overview KPIs: reach, engagement, followers, engagement rate, average reach/post, active creators.
- Post explorer with category, content type, search, sorting and expandable details.
- Creator analytics with reach/engagement efficiency and follower-to-reach analysis.
- Category analytics with performance distribution.
- Sentiment workspace for Instagram comments:
  - Samples 50–100 comments.
  - 70% of the sample is drawn from the higher-like half of the comments.
  - Remaining 30% is uniformly randomized.
  - Analyzes sentiment in 25-comment batches with Groq.
  - Returns sentiment, confidence, topic, emotion and short rationale.
- CSV comment upload endpoint.
- Groq API key stays on the FastAPI server.

## Stack

- Frontend: React + Vite + Recharts + Lucide
- Backend: FastAPI + Pandas/OpenPyXL
- Sentiment: Groq `openai/gpt-oss-20b` with structured JSON output.

## Run locally

### 1. Backend

```bash
cd backend
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
# source .venv/bin/activate

pip install -r requirements.txt

copy .env.example .env
# edit .env and add GROQ_API_KEY

uvicorn app.main:app --reload --port 8000
```

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

Set `VITE_API_URL=http://localhost:8000` in `frontend/.env.local` if the backend runs on a different URL.

The frontend also has a static `campaign.json` fallback so the UI can be previewed without the backend.

## Comments CSV format

The sentiment endpoint accepts:

```csv
comment,likes,post_url,username
"Love this campaign!",182,https://instagram.com/p/...,user1
"Looks great",74,https://instagram.com/p/...,user2
```

`comment` is required. `likes`, `post_url` and `username` are optional.

## Deployment

- Deploy `frontend/` to Vercel/Netlify.
- Deploy `backend/` to Render/Railway/Fly or any Python host.
- Set `VITE_API_URL` on the frontend.
- Set `GROQ_API_KEY` on the backend only.
