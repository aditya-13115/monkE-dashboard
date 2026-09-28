from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pandas as pd

CATEGORY_MAP = {
    "PREMIUM MEME PAGES": "Premium Meme",
    "GENERIC MEME PAGES": "Generic Meme",
    "PAPPARAZI MEME PAGES": "Paparazzi Meme",
    "POP-CULTURE PAGES": "Pop-Culture",
    "MARKETING PAGES": "Marketing",
}

HEADER_ALIASES = {
    "username": {"USERNAME", "USER NAME", "HANDLE", "IG USERNAME"},
    "creator": {"CREATOR", "CREATOR NAME", "SOURCE", "PAGE", "ACCOUNT"},
    "profile": {"PROFILE LINK", "PROFILE LINKS", "PROFILE URL", "PROFILE"},
    "followers": {"FOLLOWERS", "FOLLOWERS COUNT", "FOLLOWER COUNT", "FOLLOWER"},
    "post": {"POST LINK", "POST LINKS", "POST URL", "POST URLS", "INSTAGRAM LINK", "INSTAGRAM URL"},
    "reach": {"REACH", "TOTAL REACH"},
    "engagement": {"ENGAGEMENT", "TOTAL ENGAGEMENT"},
    "category": {"CATEGORY", "CONTENT CATEGORY"},
}


def _norm_header(value: Any) -> str:
    return " ".join(str(value or "").strip().upper().split())


def _find_header(raw: pd.DataFrame) -> int:
    for i, row in raw.iterrows():
        values = {_norm_header(x) for x in row.tolist() if pd.notna(x)}
        has_post = bool(values & HEADER_ALIASES["post"])
        has_identity = bool(values & (HEADER_ALIASES["username"] | HEADER_ALIASES["creator"]))
        if has_post and has_identity:
            return int(i)
    raise ValueError("Could not find a usable campaign table header. Expected a POST LINK column plus USERNAME/CREATOR.")


def _header_map(columns: list[Any]) -> dict[str, int]:
    mapping: dict[str, int] = {}
    for index, column in enumerate(columns):
        normalized = _norm_header(column)
        for canonical, aliases in HEADER_ALIASES.items():
            if normalized in aliases and canonical not in mapping:
                mapping[canonical] = index
                break
    return mapping


def _cell(row: list[Any], mapping: dict[str, int], key: str, default: Any = "") -> Any:
    idx = mapping.get(key)
    if idx is None or idx >= len(row):
        return default
    return row[idx]


def _number(value: Any) -> int:
    if value is None:
        return 0
    try:
        if isinstance(value, str):
            value = value.replace(",", "").strip()
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return 0


def _instagram_short_code(post_url: str) -> str:
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
    _ = post_url
    return ""


def _sheet_category(sheet_name: str, explicit: Any) -> str:
    value = str(explicit or "").strip()
    if value:
        return value
    return CATEGORY_MAP.get(sheet_name, sheet_name.replace("_", " ").title())


def load_campaign(
    path: str | Path,
    *,
    brand: str = "Asian Paints",
    campaign_name: str | None = None,
    campaign_id: str | None = None,
) -> dict[str, Any]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Campaign workbook not found: {path}")

    xls = pd.ExcelFile(path)
    records: list[dict[str, Any]] = []

    for sheet_name in xls.sheet_names:
        raw = pd.read_excel(path, sheet_name=sheet_name, header=None)
        if raw.empty:
            continue
        try:
            header_idx = _find_header(raw)
        except ValueError:
            # Non-table sheets are ignored rather than making an otherwise valid
            # multi-sheet workbook unusable.
            continue

        headers = raw.iloc[header_idx].tolist()
        mapping = _header_map(headers)
        body = raw.iloc[header_idx + 1 :]

        for row_values in body.itertuples(index=False, name=None):
            post = str(_cell(list(row_values), mapping, "post", "") or "").strip()
            if not post or not post.lower().startswith("http"):
                continue

            creator = str(_cell(list(row_values), mapping, "creator", "") or "").strip()
            username = str(_cell(list(row_values), mapping, "username", "") or "").strip().lstrip("@")
            display_name = username or creator or "Instagram creator"
            profile = str(_cell(list(row_values), mapping, "profile", "") or "").strip()
            if profile and not profile.startswith("http"):
                profile = f"https://{profile}"

            followers = _number(_cell(list(row_values), mapping, "followers", 0))
            reach = _number(_cell(list(row_values), mapping, "reach", 0))
            engagement = _number(_cell(list(row_values), mapping, "engagement", 0))
            explicit_category = _cell(list(row_values), mapping, "category", "")
            category = _sheet_category(sheet_name, explicit_category)
            post_type = "Reel" if ("/reel" in post.lower() or "/reels" in post.lower()) else "Post"

            records.append(
                {
                    "id": len(records) + 1,
                    "campaignId": campaign_id or "default",
                    "brand": brand,
                    "campaign": campaign_name or brand,
                    "category": category,
                    "username": display_name,
                    "creator": creator,
                    "profileLink": profile,
                    "postLink": post,
                    "postType": post_type,
                    "shortcode": _instagram_short_code(post),
                    "thumbnailUrl": _instagram_thumbnail_url(post),
                    "followers": followers,
                    "reach": reach,
                    "engagement": engagement,
                    "engagementRateReach": round(engagement / reach * 100, 2) if reach else 0,
                    "engagementRateFollowers": round(engagement / followers * 100, 2) if followers else 0,
                }
            )

    total_followers = sum(r["followers"] for r in records)
    total_reach = sum(r["reach"] for r in records)
    total_engagement = sum(r["engagement"] for r in records)

    categories: list[dict[str, Any]] = []
    for category in sorted({r["category"] for r in records}):
        rows = [r for r in records if r["category"] == category]
        category_reach = sum(r["reach"] for r in rows)
        category_engagement = sum(r["engagement"] for r in rows)
        categories.append(
            {
                "name": category,
                "creators": len({r["username"] for r in rows}),
                "deliverables": len(rows),
                "followers": sum(r["followers"] for r in rows),
                "reach": category_reach,
                "engagement": category_engagement,
                "engagementRate": round(category_engagement / category_reach * 100, 2) if category_reach else 0,
            }
        )

    return {
        "meta": {
            "brand": brand,
            "campaign": campaign_name or brand,
            "platform": "Instagram",
            "plannedProfiles": len({r["username"] for r in records}),
            "plannedDeliverables": len(records),
            "source": path.name,
        },
        "summary": {
            "totalCreators": len({r["username"] for r in records}),
            "totalPosts": len(records),
            "totalFollowers": total_followers,
            "totalReach": total_reach,
            "totalEngagement": total_engagement,
            "engagementRateReach": round(total_engagement / total_reach * 100, 2) if total_reach else 0,
        },
        "categories": categories,
        "records": records,
    }
