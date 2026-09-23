from __future__ import annotations

import os
from pathlib import Path

from playwright.sync_api import sync_playwright


BASE_DIR = Path(__file__).resolve().parent

PROFILE_DIR = (
    BASE_DIR
    / "data"
    / "instagram_profile"
)


POST_URL = input(
    "Paste an Instagram post/reel URL: "
).strip()


def main():

    print("\nStarting Instagram test...")
    print(f"Profile: {PROFILE_DIR}")
    print(f"Post:    {POST_URL}\n")

    PROFILE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    with sync_playwright() as p:

        context = (
            p.chromium.launch_persistent_context(
                user_data_dir=str(
                    PROFILE_DIR
                ),
                headless=False,
                viewport={
                    "width": 1440,
                    "height": 1000,
                },
                locale="en-US",
                timezone_id="Asia/Kolkata",
            )
        )

        try:

            page = (
                context.pages[0]
                if context.pages
                else context.new_page()
            )

            print("Opening Instagram...")

            page.goto(
                POST_URL,
                wait_until="domcontentloaded",
                timeout=60000,
            )

            page.wait_for_timeout(
                5000
            )

            print("\n========== PAGE INFO ==========")
            print(
                "Current URL:",
                page.url,
            )

            print(
                "Title:",
                page.title(),
            )

            print(
                "Cookies:",
                len(
                    context.cookies(
                        "https://www.instagram.com"
                    )
                ),
            )

            print(
                "LI elements:",
                page.locator("li").count(),
            )

            print(
                "Article elements:",
                page.locator(
                    "article"
                ).count(),
            )

            print(
                "Buttons:",
                page.get_by_role(
                    "button"
                ).count(),
            )

            print(
                "Links:",
                page.locator("a").count(),
            )

            print("\n========== LOGIN CHECK ==========")

            body_text = page.locator(
                "body"
            ).inner_text(
                timeout=10000
            )

            lower_text = body_text.lower()

            print(
                "Contains 'log in':",
                "log in" in lower_text,
            )

            print(
                "Contains 'sign up':",
                "sign up" in lower_text,
            )

            print(
                "Contains 'comments':",
                "comments" in lower_text,
            )

            print("\n========== PAGE TEXT ==========")

            # Print first 8000 characters only.
            print(
                body_text[:8000]
            )

            print(
                "\n========== SAVING DEBUG FILES =========="
            )

            screenshot_path = (
                BASE_DIR
                / "instagram_debug.png"
            )

            html_path = (
                BASE_DIR
                / "instagram_debug.html"
            )

            page.screenshot(
                path=str(
                    screenshot_path
                ),
                full_page=True,
            )

            html_path.write_text(
                page.content(),
                encoding="utf-8",
            )

            print(
                "Screenshot:",
                screenshot_path,
            )

            print(
                "HTML:",
                html_path,
            )

            print(
                "\nBrowser will stay open."
            )

            print(
                "Look at the Instagram page."
            )

            input(
                "Press ENTER to close..."
            )

        finally:

            context.close()


if __name__ == "__main__":
    main()