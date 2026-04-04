"""Telegram approval flow for Appi-Claw.

Sends listing + draft to user via inline keyboard, waits for callback.
Uses direct Bot API calls (no long-polling) to avoid conflicts with
other bot instances (e.g., DRUT) using the same token.
"""

import asyncio
import time
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup

DECISION_MAP = {
    "approve": "apply",
    "draft_only": "draft",
    "skip": "skip",
}

DECISION_LABELS = {
    "apply": "Applying!",
    "draft": "Draft saved.",
    "skip": "Skipped.",
}


async def send_approval_request(
    listing_summary: str,
    draft: str,
    config: dict,
) -> str:
    """Send listing + draft to user on Telegram and wait for a decision.

    Returns: "apply", "draft", or "skip".
    """
    bot_token = config["telegram"]["bot_token"]
    user_id = config["telegram"]["user_id"]
    timeout_minutes = config["settings"].get("approval_timeout_minutes", 30)

    bot = Bot(token=bot_token)

    # Truncate draft if too long for Telegram (4096 char limit)
    max_draft = 2000
    draft_display = draft[:max_draft] + "..." if len(draft) > max_draft else draft

    message_text = (
        f"New Application\n\n"
        f"{listing_summary}\n\n"
        f"--- Draft ---\n"
        f"{draft_display}\n"
        f"--- End Draft ---\n\n"
        f"Reply within {timeout_minutes} min:"
    )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Apply", callback_data="approve"),
            InlineKeyboardButton("Draft Only", callback_data="draft_only"),
            InlineKeyboardButton("Skip", callback_data="skip"),
        ]
    ])

    sent = await bot.send_message(
        chat_id=user_id,
        text=message_text,
        reply_markup=keyboard,
    )

    # Poll for callback query using getUpdates with short intervals
    decision = await _poll_for_callback(bot, user_id, sent.message_id, timeout_minutes)

    # Edit the original message to show the decision
    label = DECISION_LABELS.get(decision, "Done.")
    try:
        await bot.edit_message_reply_markup(
            chat_id=user_id,
            message_id=sent.message_id,
            reply_markup=None,
        )
        await bot.send_message(chat_id=user_id, text=label)
    except Exception:
        pass  # Non-critical if edit fails

    return decision


async def _poll_for_callback(
    bot: Bot,
    user_id: int,
    message_id: int,
    timeout_minutes: int,
) -> str:
    """Poll getUpdates for callback_query matching our message.

    Uses a short-lived getUpdates call with offset to avoid conflicting
    with other long-running bot instances on the same token.
    """
    deadline = time.time() + (timeout_minutes * 60)
    offset = 0

    # Get current update_id to skip old updates
    try:
        existing = await bot.get_updates(timeout=1)
        if existing:
            offset = existing[-1].update_id + 1
    except Exception:
        pass

    while time.time() < deadline:
        try:
            updates = await bot.get_updates(
                offset=offset,
                timeout=5,
                allowed_updates=["callback_query"],
            )
        except Exception:
            await asyncio.sleep(3)
            continue

        for update in updates:
            offset = update.update_id + 1
            if update.callback_query:
                query = update.callback_query
                if (
                    query.message
                    and query.message.message_id == message_id
                    and query.from_user
                    and query.from_user.id == user_id
                ):
                    try:
                        await query.answer()
                    except Exception:
                        pass
                    return DECISION_MAP.get(query.data, "skip")

        await asyncio.sleep(2)

    # Timed out
    try:
        await bot.send_message(
            chat_id=user_id,
            text=f"Timed out after {timeout_minutes} min - auto-skipping.",
        )
    except Exception:
        pass

    return "skip"


def send_approval_sync(listing_summary: str, draft: str, config: dict) -> str:
    """Synchronous wrapper for send_approval_request."""
    return asyncio.run(send_approval_request(listing_summary, draft, config))
