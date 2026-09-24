from __future__ import annotations

import asyncio
from pathlib import Path

from app.instagram_web import fetch_post_analysis_source


async def main() -> None:
    url = input("Paste Instagram post/reel URL: ").strip()
    result = await fetch_post_analysis_source(
        url,
        comment_limit=20,
        force=True,
    )

    print("\n=== POST ===")
    print("URL:", result.get("postUrl"))
    print("Thumbnail:", result.get("thumbnailUrl"))
    print("Likes:", result.get("likes"))
    print("Comments metric:", result.get("comments"))
    print("Views:", result.get("views"))
    print("Engagement:", result.get("engagement"))
    print("Comments extracted:", result.get("commentsExtracted"))

    print("\n=== COMMENTS ===")
    for i, row in enumerate(result.get("commentsData", []), 1):
        print(
            f"{i:02d}. @{row.get('username', '')} "
            f"(likes={row.get('likes', 0)}): {row.get('comment', '')}"
        )


if __name__ == "__main__":
    asyncio.run(main())
