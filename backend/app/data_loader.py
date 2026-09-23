from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pandas as pd

SHEETS = [
    "PREMIUM MEME PAGES",
    "GENERIC MEME PAGES",
    "PAPPARAZI MEME PAGES",
    "POP-CULTURE PAGES",
    "MARKETING PAGES",
]

CATEGORY_MAP = {
    "PREMIUM MEME PAGES": "Premium Meme",
    "GENERIC MEME PAGES": "Generic Meme",
    "PAPPARAZI MEME PAGES": "Paparazzi Meme",
    "POP-CULTURE PAGES": "Pop-Culture",
    "MARKETING PAGES": "Marketing",
}


def _find_header(raw: pd.DataFrame) -> int:
    for i, row in raw.iterrows():
        values = {str(x).strip().upper() for x in row.tolist() if pd.notna(x)}
        if "USERNAME" in values and "POST LINKS" in values:
            return int(i)
    raise ValueError("Could not find the campaign table header.")


def _instagram_short_code(post_url: str) -> str:
    """Extract the Instagram media shortcode from /p/, /reel/ or /reels/ URLs."""
    try:
        path = urlparse(post_url).path.strip("/")
        parts = [part for part in path.split("/") if part]
        for marker in ("p", "reel", "reels"):
            if marker in parts:
                idx = parts.index(marker)
                if idx + 1 < len(parts):
                    return parts[idx + 1]
    except Exception:
        pass
    return ""


def _instagram_thumbnail_url(post_url: str) -> str:
    """
    Instagram's media URL is used as the lightweight thumbnail source.
    If Instagram blocks the request, the frontend falls back to a local card.
    """
    shortcode = _instagram_short_code(post_url)
    if not shortcode:
        return ""

    try:
        path = urlparse(post_url).path.lower()
        kind = "reel" if "/reel" in path else "p"
    except Exception:
        kind = "p"

    return f"https://www.instagram.com/{kind}/{shortcode}/media/?size=l"


def load_campaign(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    xls = pd.ExcelFile(path)
    records: list[dict[str, Any]] = []

    for sheet in SHEETS:
        if sheet not in xls.sheet_names:
            continue

        raw = pd.read_excel(path, sheet_name=sheet, header=None)
        header_idx = _find_header(raw)
        df = raw.iloc[header_idx + 1 :].copy()
        df.columns = [
            "S NO.",
            "USERNAME",
            "PROFILE LINK",
            "FOLLOWERS",
            "POST LINK",
            "REACH",
            "ENGAGEMENT",
        ]

        df = df[df["USERNAME"].notna()].copy()
        for col in ["FOLLOWERS", "REACH", "ENGAGEMENT"]:
            df[col] = (
                pd.to_numeric(df[col], errors="coerce")
                .fillna(0)
                .astype(int)
            )

        for _, row in df.iterrows():
            username = str(row["USERNAME"]).strip()
            profile = str(row["PROFILE LINK"]).strip()
            post = str(row["POST LINK"]).strip()
            post_type = (
                "Reel"
                if ("/reel" in post.lower() or "/reels" in post.lower())
                else "Post"
            )
            reach = int(row["REACH"])
            engagement = int(row["ENGAGEMENT"])
            followers = int(row["FOLLOWERS"])

            records.append(
                {
                    "id": len(records) + 1,
                    "category": CATEGORY_MAP.get(sheet, sheet),
                    "username": username,
                    "profileLink": (
                        profile
                        if profile.startswith("http")
                        else f"https://{profile}"
                    ),
                    "postLink": post,
                    "postType": post_type,
                    "shortcode": _instagram_short_code(post),
                    "thumbnailUrl": _instagram_thumbnail_url(post),
                    "followers": followers,
                    "reach": reach,
                    "engagement": engagement,
                    "engagementRateReach": round(
                        (engagement / reach * 100),
                        2,
                    )
                    if reach
                    else 0,
                    "engagementRateFollowers": round(
                        (engagement / followers * 100),
                        2,
                    )
                    if followers
                    else 0,
                }
            )

    total_followers = sum(r["followers"] for r in records)
    total_reach = sum(r["reach"] for r in records)
    total_engagement = sum(r["engagement"] for r in records)

    categories = []
    for category in sorted({r["category"] for r in records}):
        rows = [r for r in records if r["category"] == category]
        category_reach = sum(r["reach"] for r in rows)
        category_engagement = sum(r["engagement"] for r in rows)
        categories.append(
            {
                "name": category,
                "creators": len(rows),
                "deliverables": len(rows),
                "followers": sum(r["followers"] for r in rows),
                "reach": category_reach,
                "engagement": category_engagement,
                "engagementRate": round(
                    category_engagement / category_reach * 100,
                    2,
                )
                if category_reach
                else 0,
            }
        )

    return {
        "meta": {
            "campaign": "Asian Paints",
            "date": "10 April 2026",
            "platform": "Instagram",
            "plannedProfiles": 289,
            "plannedDeliverables": 289,
            "expectedViews": "15M+",
            "source": path.name,
        },
        "summary": {
            "totalCreators": len(records),
            "totalPosts": len(records),
            "totalFollowers": total_followers,
            "totalReach": total_reach,
            "totalEngagement": total_engagement,
            "engagementRateReach": round(
                total_engagement / total_reach * 100,
                2,
            )
            if total_reach
            else 0,
            "avgReachPerPost": round(
                total_reach / len(records)
            )
            if records
            else 0,
        },
        "categories": categories,
        "records": records,
    }
