from __future__ import annotations

from .instagram_web import PROFILE_DIR
from playwright.sync_api import sync_playwright


def main() -> None:
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 64)
    print("MONK-E INSTAGRAM LOGIN")
    print("=" * 64)
    print(f"Profile directory: {PROFILE_DIR}")
    print("A Chromium window will open.")
    print("Log in to the Instagram account manually.")
    print("When you can browse the account normally, return here and press ENTER.")

    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=False,
            viewport={"width": 1440, "height": 1000},
            locale="en-US",
            timezone_id="Asia/Kolkata",
        )

        try:
            page = context.pages[0] if context.pages else context.new_page()
            page.goto("https://www.instagram.com/", wait_until="domcontentloaded", timeout=60000)
            input("\nPress ENTER after login/session verification... ")
        finally:
            context.close()

    print("Instagram browser session saved.")
    print(f"Profile: {PROFILE_DIR}")


if __name__ == "__main__":
    main()
