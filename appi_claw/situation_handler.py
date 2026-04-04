"""Unhandled situation handler for Appi-Claw.

Detects and handles:
- CAPTCHA → pause browser, notify user, wait for "done" reply (15 min timeout)
- Video question → notify user, switch to non-headless if possible
- Unexpected errors → screenshot, notify user, wait for "retry" or "skip"

All pauses use Telegram polling (not long-running Application)
to avoid conflicting with DRUT. 15 min timeout → auto-skip.
"""

import asyncio
import time
from pathlib import Path
from playwright.async_api import Page

ERROR_SCREENSHOT_PATH = Path.home() / "appi-claw-error.png"
PAUSE_TIMEOUT_MINUTES = 15


# --- Detection helpers ---

async def detect_captcha(page: Page) -> bool:
    """Return True if a CAPTCHA is visible on the page."""
    captcha_selectors = [
        "iframe[src*='recaptcha']",
        "iframe[src*='hcaptcha']",
        ".g-recaptcha",
        "#captcha",
        "[id*='captcha']",
        "[class*='captcha']",
        "img[alt*='captcha' i]",
        "input[name*='captcha' i]",
    ]
    for selector in captcha_selectors:
        try:
            el = page.locator(selector).first
            if await el.count() > 0 and await el.is_visible():
                return True
        except Exception:
            pass

    # Also check page title / URL for common CAPTCHA pages
    url = page.url.lower()
    if any(w in url for w in ("captcha", "challenge", "verify", "robot")):
        return True

    return False


async def detect_video_question(page: Page) -> bool:
    """Return True if a video recording question is on the page."""
    video_selectors = [
        "video[autoplay]",
        "[class*='video-question' i]",
        "[class*='video-interview' i]",
        "button:has-text('Record')",
        "button:has-text('Start recording')",
        "[data-testid*='video' i]",
    ]
    for selector in video_selectors:
        try:
            el = page.locator(selector).first
            if await el.count() > 0 and await el.is_visible():
                return True
        except Exception:
            pass
    return False


# --- Telegram wait helpers ---

async def _wait_for_keyword(
    config: dict,
    after_message_id: int,
    keywords: list[str],
    timeout_minutes: int = PAUSE_TIMEOUT_MINUTES,
) -> str | None:
    """Poll Telegram for a message from the user matching one of the keywords.

    Returns the matched keyword (lowercased), or None on timeout.
    """
    from telegram import Bot

    bot = Bot(token=config["telegram"]["bot_token"])
    user_id = config["telegram"]["user_id"]
    deadline = time.time() + (timeout_minutes * 60)
    offset = 0

    try:
        existing = await bot.get_updates(timeout=1, allowed_updates=["message"])
        if existing:
            offset = existing[-1].update_id + 1
    except Exception:
        pass

    while time.time() < deadline:
        try:
            updates = await bot.get_updates(
                offset=offset,
                timeout=5,
                allowed_updates=["message"],
            )
        except Exception:
            await asyncio.sleep(3)
            continue

        for update in updates:
            offset = update.update_id + 1
            if (
                update.message
                and update.message.from_user
                and update.message.from_user.id == user_id
                and update.message.text
                and update.message.message_id > after_message_id
            ):
                text = update.message.text.strip().lower()
                for kw in keywords:
                    if kw in text:
                        return kw

        await asyncio.sleep(2)

    return None


# --- Situation handlers ---

async def handle_captcha(page: Page, url: str, config: dict) -> str:
    """Pause and notify user to solve CAPTCHA manually.

    Returns "continue" if user replied "done", "skip" if timed out.
    """
    from telegram import Bot
    from appi_claw.telegram_bot import notify

    bot = Bot(token=config["telegram"]["bot_token"])
    user_id = config["telegram"]["user_id"]

    msg = await bot.send_message(
        chat_id=user_id,
        text=(
            f"CAPTCHA detected at:\n{url}\n\n"
            f"Please complete it manually in your browser.\n"
            f"Reply 'done' when finished.\n"
            f"(Auto-skipping in {PAUSE_TIMEOUT_MINUTES} min if no reply)"
        ),
    )

    keyword = await _wait_for_keyword(
        config,
        after_message_id=msg.message_id,
        keywords=["done"],
        timeout_minutes=PAUSE_TIMEOUT_MINUTES,
    )

    if keyword == "done":
        await bot.send_message(
            chat_id=user_id,
            text="Got it — resuming application.",
        )
        return "continue"
    else:
        await bot.send_message(
            chat_id=user_id,
            text=f"No reply in {PAUSE_TIMEOUT_MINUTES} min — skipping this application.",
        )
        return "skip"


async def handle_video_question(page: Page, url: str, config: dict) -> str:
    """Notify user of video question and wait for manual action.

    Returns "skip" — video questions always require full manual handling.
    """
    from telegram import Bot

    bot = Bot(token=config["telegram"]["bot_token"])
    user_id = config["telegram"]["user_id"]

    await bot.send_message(
        chat_id=user_id,
        text=(
            f"Video question detected at:\n{url}\n\n"
            "This requires manual action — please complete it in your browser.\n"
            "Appi-Claw will skip this step automatically."
        ),
    )
    return "skip"


async def handle_unexpected_error(
    page: Page,
    url: str,
    step: str,
    error: str,
    config: dict,
) -> str:
    """Take a screenshot, notify user, and wait for 'retry' or 'skip'.

    Returns "retry" or "skip".
    """
    from telegram import Bot

    bot = Bot(token=config["telegram"]["bot_token"])
    user_id = config["telegram"]["user_id"]

    # Take screenshot
    screenshot_saved = False
    try:
        await page.screenshot(path=str(ERROR_SCREENSHOT_PATH), full_page=False)
        screenshot_saved = True
    except Exception:
        pass

    screenshot_note = (
        f"Screenshot saved at {ERROR_SCREENSHOT_PATH}"
        if screenshot_saved
        else "Screenshot could not be saved."
    )

    msg = await bot.send_message(
        chat_id=user_id,
        text=(
            f"Something unexpected happened at: {step}\n"
            f"URL: {url}\n"
            f"Error: {error}\n\n"
            f"{screenshot_note}\n\n"
            f"Reply 'retry' to try again, or 'skip' to skip this application.\n"
            f"(Auto-skipping in {PAUSE_TIMEOUT_MINUTES} min)"
        ),
    )

    keyword = await _wait_for_keyword(
        config,
        after_message_id=msg.message_id,
        keywords=["retry", "skip"],
        timeout_minutes=PAUSE_TIMEOUT_MINUTES,
    )

    if keyword == "retry":
        await bot.send_message(chat_id=user_id, text="Retrying...")
        return "retry"
    else:
        await bot.send_message(
            chat_id=user_id,
            text=f"Skipping after {PAUSE_TIMEOUT_MINUTES} min timeout.",
        )
        return "skip"


# --- Combined page check (call after each navigation) ---

async def check_page_for_situations(
    page: Page,
    url: str,
    step: str,
    config: dict,
) -> str:
    """Check current page for known problem situations.

    Returns "continue", "skip", or "retry".
    Should be called after each major navigation or click.
    """
    if await detect_captcha(page):
        return await handle_captcha(page, url, config)

    if await detect_video_question(page):
        return await handle_video_question(page, url, config)

    return "continue"
