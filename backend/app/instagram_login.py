from __future__ import annotations

from .instagram_web import PROFILE_DIR, STORAGE_STATE_PATH
from playwright.sync_api import sync_playwright


def main() -> None:
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 68)
    print("MONK-E INSTAGRAM ONE-TIME LOGIN")
    print("=" * 68)
    print(f"Browser profile: {PROFILE_DIR}")
    print(f"Storage state:   {STORAGE_STATE_PATH}")
    print("A Chromium window will open.")
    print("Log into the Instagram account manually.")
    print("Do not close the browser until the session is verified.")

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
            page.goto(
                "https://www.instagram.com/",
                wait_until="domcontentloaded",
                timeout=60_000,
            )
            input("\nAfter login is complete, press ENTER here... ")
            context.storage_state(
                path=str(STORAGE_STATE_PATH),
                indexed_db=True,
            )
        finally:
            context.close()

    print("Instagram storage state saved successfully.")
    print(STORAGE_STATE_PATH)


if __name__ == "__main__":
    main()
