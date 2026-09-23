# Monk-E Campaign Intelligence Dashboard

An influencer campaign analytics and AI audience-insights dashboard for Monk-E.

The current application combines:

- Campaign data from an Excel workbook
- React + Vite dashboard
- FastAPI backend
- Playwright + Chromium for Instagram web access
- Persistent Instagram login state
- Live-on-demand public post metrics where Instagram exposes them
- Instagram comment extraction
- Groq-powered sentiment, topic, and emotion analysis

---

## 1. What the project does

Monk-E manages influencer campaigns and stores campaign placements in Excel.

Instead of manually reviewing the spreadsheet, this dashboard provides:

- Campaign overview
- Reach and engagement analytics
- Creator-level analysis
- Category analysis
- Post explorer
- Instagram post links
- Instagram thumbnails
- Live/public post metrics where available
- Post-level comment sentiment analysis
- AI topics and emotions

The Excel workbook remains the campaign mapping/source for:

- Creator
- Profile link
- Post/Reel link
- Category
- Historical/fallback reach
- Historical/fallback engagement
- Other campaign fields

The Instagram browser session is then used to open the exact post URL from Excel.

---

# 2. High-level architecture

```text
                         Excel Workbook
                              |
                              | campaign mapping
                              v
                     +--------------------+
                     |    FastAPI API     |
                     +--------------------+
                         |            |
                         |            |
                         v            v
                  Campaign data   Instagram URL
                                      |
                                      v
                             Playwright + Chromium
                                      |
                           +----------+----------+
                           |                     |
                           v                     v
                    Post metadata            Comments
                           |                     |
                           v                     v
                      Dashboard               Sampling
                                                 |
                                                 v
                                               Groq
                                                 |
                                                 v
                                      Sentiment / topics /
                                      emotions / confidence
```

---

# 3. Important Instagram architecture

The project uses a **persistent Instagram login state**.

You should NOT put your Instagram password or raw session cookie into `.env`.

Instead:

```text
One-time manual login
        |
        v
Playwright Chromium
        |
        v
storage_state.json
        |
        v
Future browser sessions
        |
        v
Instagram already authenticated
```

The login state is stored locally at:

```text
backend/data/instagram_profile/storage_state.json
```

This directory is sensitive and must not be committed.

Add:

```gitignore
data/instagram_profile/
```

to `.gitignore`.

---

# 4. Project structure

```text
monke-campaign-dashboard/
|
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py
│   │   ├── data_loader.py
│   │   ├── sentiment.py
│   │   ├── comment_source.py
│   │   ├── instagram_web.py
│   │   └── instagram_login.py
│   │
│   ├── .env
│   ├── .env.example
│   ├── requirements.txt
│   └── data/
│       └── instagram_profile/
│
├── frontend/
│   ├── src/
│   │   ├── App.jsx
│   │   ├── main.jsx
│   │   └── styles.css
│   ├── public/
│   ├── package.json
│   └── vite.config.js
│
├── data/
│   └── ASIAN PAINTS (1).xlsx
│
└── README.md
```

---

# 5. Technology stack

## Frontend

- React
- Vite
- JavaScript
- Recharts
- Lucide React
- CSS

## Backend

- Python
- FastAPI
- Uvicorn
- Pydantic
- Pandas
- OpenPyXL
- python-dotenv
- Groq SDK
- HTTPX

## Browser automation

- Playwright
- Chromium

## AI

- Groq
- `openai/gpt-oss-20b`

## Data source

- Excel (`.xlsx`)

---

# 6. Requirements

Install:

- Python 3.11+
- Node.js LTS
- uv

Check:

```powershell
python --version
node --version
npm --version
uv --version
```

---

# 7. First-time backend setup

Open PowerShell in:

```text
monke-campaign-dashboard/backend
```

Create the environment:

```powershell
uv venv
```

Install backend packages:

```powershell
uv pip install -r requirements.txt
```

Install Chromium for Playwright:

```powershell
uv run python -m playwright install chromium
```

Verify:

```powershell
uv run python -m playwright --version
```

---

# 8. Environment configuration

Create:

```text
backend/.env
```

Example:

```env
GROQ_API_KEYS=YOUR_KEY_1,YOUR_KEY_2,YOUR_KEY_3
GROQ_SENTIMENT_MODEL=openai/gpt-oss-20b
GROQ_SENTIMENT_CONCURRENCY=2

CAMPAIGN_XLSX_PATH=data/ASIAN PAINTS (1).xlsx

INSTAGRAM_USER_DATA_DIR=data/instagram_profile
INSTAGRAM_HEADLESS=false
INSTAGRAM_TIMEOUT_MS=45000
```

## Variables

### Groq

```env
GROQ_API_KEYS=key1,key2,key3
```

Comma-separated API keys.

They are used as credential failover if a key receives a rate-limit response.

### Sentiment model

```env
GROQ_SENTIMENT_MODEL=openai/gpt-oss-20b
```

### Sentiment concurrency

```env
GROQ_SENTIMENT_CONCURRENCY=2
```

### Workbook

```env
CAMPAIGN_XLSX_PATH=data/ASIAN PAINTS (1).xlsx
```

### Instagram profile

```env
INSTAGRAM_USER_DATA_DIR=data/instagram_profile
```

### Browser visibility

For development/testing:

```env
INSTAGRAM_HEADLESS=false
```

For normal background operation:

```env
INSTAGRAM_HEADLESS=true
```

### Browser timeout

```env
INSTAGRAM_TIMEOUT_MS=45000
```

---

# 9. One-time Instagram login

Do this once on a machine where the dashboard will run.

From:

```text
backend/
```

run:

```powershell
uv run python -m app.instagram_login
```

A Chromium window opens.

### Then:

1. Log into the authorized Instagram account manually.
2. Make sure Instagram is fully loaded.
3. Return to the terminal.
4. Press Enter.

The login script saves:

```text
backend/data/instagram_profile/storage_state.json
```

Future app sessions reuse this stored browser state.

---

# 10. Important: do not keep the login browser open

After running:

```powershell
uv run python -m app.instagram_login
```

and saving the session, close the login browser.

The dashboard does NOT use the persistent browser profile directly.

Instead it loads:

```text
storage_state.json
```

into a new browser context.

This avoids the error:

```text
Opening in existing browser session.
This usually means that the profile is already in use by another
instance of Chromium.
```

---

# 11. Start the backend

From:

```text
backend/
```

run:

```powershell
uv run uvicorn app.main:app --reload --port 8000
```

Backend:

```text
http://localhost:8000
```

Swagger:

```text
http://localhost:8000/docs
```

Health:

```text
http://localhost:8000/health
```

---

# 12. Start the frontend

Open another PowerShell:

```powershell
cd C:\path\to\monke-campaign-dashboard\frontend
```

Install packages:

```powershell
npm install
```

Start:

```powershell
npm run dev
```

Open the Vite URL, normally:

```text
http://localhost:5173
```

---

# 13. Normal startup after initial setup

You only need two terminals.

## Terminal 1

```powershell
cd C:\path\to\monke-campaign-dashboard\backend
uv run uvicorn app.main:app --reload --port 8000
```

## Terminal 2

```powershell
cd C:\path\to\monke-campaign-dashboard\frontend
npm run dev
```

Then open:

```text
http://localhost:5173
```

You do NOT need to run `instagram_login.py` again unless the saved login state becomes invalid or needs to be re-authenticated.

---

# 14. How the campaign data works

The workbook is currently the campaign source.

Typical data includes:

```text
USERNAME
PROFILE LINK
FOLLOWERS
POST LINK
REACH
ENGAGEMENT
CATEGORY
```

The backend reads the workbook through:

```text
backend/app/data_loader.py
```

The frontend receives campaign data through:

```http
GET /api/campaign
```

---

# 15. Post-level sentiment flow

When the user selects a post:

```text
Excel record
    |
    v
POST LINK
    |
    v
FastAPI
    |
    v
Playwright browser
    |
    v
Instagram post
    |
    v
Publicly visible comments
    |
    v
Sample up to 100
    |
    v
Groq
    |
    v
Sentiment result
```

The current sampling logic uses a higher share of comments with greater visible engagement and a random component.

Target:

```text
70% higher-liked
30% random
```

Maximum sample:

```text
100 comments
```

Comments are sent to Groq in batches.

---

# 16. Sentiment output

The AI pipeline can return fields such as:

```json
{
  "comment": "Love this!",
  "likes": 120,
  "username": "example",
  "sentiment": "positive",
  "confidence": 0.94,
  "topic": "creative",
  "emotion": "delight",
  "reason": "The commenter explicitly praises the campaign."
}
```

The dashboard aggregates:

- Positive
- Neutral
- Negative
- Sentiment percentages
- Topic distribution
- Emotion distribution
- Comment-level results

---

# 17. Instagram thumbnails

The dashboard attempts to use the actual Instagram page metadata, such as the `og:image` image exposed by the page.

This is preferable to inventing an image URL from the post ID.

If Instagram does not expose a thumbnail to the browser, the frontend should fall back gracefully rather than breaking the card.

---

# 18. Live/public Instagram metrics

The browser-based version can retrieve metrics that are publicly exposed on the Instagram post page, depending on what Instagram renders to the logged-in browser.

Examples can include:

- Likes
- Comments
- Views / plays

However:

## Reach is different

Reach is an account-level insight and is not normally a public field on a post page.

Therefore the current browser approach should treat:

```text
Instagram public metrics
```

and:

```text
Excel reach / historical campaign metrics
```

as separate sources.

For reliable owner-side reach/impressions/insight data in production, use the authorized Instagram/Meta API for the professional account.

---

# 19. Useful API endpoints

## Campaign

```http
GET /api/campaign
```

Returns campaign records.

## Individual post

```http
GET /api/campaign/post/{post_id}
```

Returns one campaign record.

## Post sentiment

```http
POST /api/sentiment/post/{post_id}
```

Runs:

```text
Excel post URL
→ Instagram
→ comments
→ sampling
→ Groq
```

## Health

```http
GET /health
```

Use this to check whether the backend is alive.

---

# 20. Debugging Instagram

For debugging:

```env
INSTAGRAM_HEADLESS=false
```

Then restart FastAPI:

```powershell
uv run uvicorn app.main:app --reload --port 8000
```

When a post is analyzed, Chromium opens visibly.

You can confirm:

- Correct Instagram URL
- Logged-in state
- Comments visible
- Page loaded correctly

---

# 21. Test the Instagram session directly

If sentiment fails, run:

```powershell
uv run python debug_instagram.py
```

Paste the exact Instagram POST LINK from the Excel.

The debug script checks:

- Current URL
- Page title
- Cookie count
- Comment text visibility
- Page text
- Login state
- Rendered Instagram content

It can also save a screenshot and HTML snapshot for debugging.

---

# 22. Common problems

## Problem: `No module named playwright`

Run:

```powershell
uv pip install playwright
uv run python -m playwright install chromium
```

---

## Problem: `Opening in existing browser session`

Do not use the persistent profile as a browser context for the running dashboard.

The production flow should use:

```text
storage_state.json
```

with:

```python
browser.new_context(
    storage_state="..."
)
```

not:

```python
launch_persistent_context(
    user_data_dir="..."
)
```

The provided `instagram_web.py` follows this architecture.

---

## Problem: `Sync API inside asyncio loop`

The dashboard uses:

```python
await asyncio.to_thread(...)
```

around the synchronous Playwright operation.

This keeps Playwright's Sync API out of FastAPI's event-loop thread.

---

## Problem: comments are visible but extractor returns zero

Use:

```env
INSTAGRAM_HEADLESS=false
```

Run the debug script and inspect the page.

Instagram frequently changes its DOM structure, so the extractor intentionally uses rendered body text in addition to structured DOM extraction.

---

## Problem: no comments

Possible reasons:

- Post has no comments
- Comments are disabled
- Instagram is requiring authentication
- Instagram is showing a challenge/login page
- The page returned limited content
- Instagram changed its page structure

---

# 23. Security

Never commit:

```text
backend/.env
backend/data/instagram_profile/
```

Do not publish:

- Groq keys
- Instagram passwords
- Instagram session state
- `storage_state.json`
- Browser profile directories

Recommended `.gitignore`:

```gitignore
.env
.env.*
!.env.example

.venv/
__pycache__/
*.pyc

node_modules/
dist/

data/instagram_profile/
```

Treat `storage_state.json` like an authentication credential.

---

# 24. Current limitations

The current version is a prototype.

### Excel is still the campaign source

Campaign mapping and fallback/historical metrics come from the workbook.

### Instagram is browser-driven

The Instagram web extractor depends on what Instagram renders to the browser.

It can break if Instagram changes:

- DOM structure
- labels
- public page behavior
- login requirements
- comment loading behavior

### Public metrics are not the same as owner insights

Likes/comments/views may be visible publicly.

Reach and other account insights may require authorized professional-account analytics.

---

# 25. Recommended future architecture

A production system should move toward:

```text
                 React Dashboard
                        |
                        v
                     FastAPI
                        |
            +-----------+-----------+
            |                       |
            v                       v
        PostgreSQL                Redis
            |
            +---------------------------+
            |                           |
            v                           v
      Campaign data                AI results
            |
            v
      Instagram ingestion
            |
            +-----------------------+
            |                       |
            v                       v
       Authorized API          Browser fallback
            |
            v
        Metrics/comments
            |
            v
           Groq
```

Recommended improvements:

1. Replace the Excel-as-database approach with PostgreSQL.
2. Keep Excel as an import/export format.
3. Add campaign upload/import validation.
4. Add OAuth for authorized Instagram professional accounts.
5. Store post metrics over time.
6. Cache sentiment results.
7. Add historical sentiment trends.
8. Add creator benchmarking.
9. Add campaign-level AI summaries.
10. Add anomaly detection.
11. Add user authentication and campaign permissions.
12. Run Instagram ingestion and AI analysis as background jobs.

---

# 26. Short explanation for a demo/interview

> Monk-E Campaign Intelligence is an influencer campaign analytics platform. It converts Monk-E's existing Excel campaign data into an interactive React dashboard. For AI audience insights, a user selects a specific campaign post, the backend opens that exact Instagram URL using a saved authenticated Playwright session, extracts the comments that Instagram exposes, samples up to 100 comments with a higher weight toward higher-liked comments, and sends them to Groq for sentiment, topic and emotion analysis. The architecture keeps Instagram access and Groq credentials server-side and leaves a path for moving from the current Excel/browser prototype to a database plus authorized Instagram data-ingestion system.

---

# 27. Quick setup checklist

First machine:

```powershell
cd backend
uv venv
uv pip install -r requirements.txt
uv run python -m playwright install chromium
uv run python -m app.instagram_login
```

Then run backend:

```powershell
uv run uvicorn app.main:app --reload --port 8000
```

Second terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open:

```text
http://localhost:5173
```

Done.
