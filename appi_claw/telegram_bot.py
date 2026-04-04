"""Telegram approval flow for Appi-Claw.

Flow:
  1 = Apply as-is
  2 = Edit draft (user gives feedback → Gemini revises → repeat, max 5 rounds)
  3 = Skip

Edit loop:
  - User taps Edit → bot asks "What should I change?"
  - User replies with feedback text
  - Gemini regenerates draft with feedback
  - New draft sent with same 3 buttons
  - Repeats until Apply or Skip (max 5 rounds → auto-skip)

Timeout: configurable minutes → auto-skip.
Uses getUpdates polling (no long-running Application) to avoid conflict with DRUT.
"""

import asyncio
import time
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup

MAX_EDIT_ROUNDS = 5

DECISION_LABELS = {
    "apply": "Applying!",
    "draft": "Draft saved.",
    "skip": "Skipped.",
}


async def send_approval_request(
    listing_summary: str,
    draft: str,
    config: dict,
    listing=None,
    platform: str | None = None,
) -> tuple[str, str]:
    """Send listing + draft to user on Telegram and run the approval/edit loop.

    Args:
        listing_summary: Short text describing the listing.
        draft: The initial generated draft.
        config: Full app config.
        listing: Listing object (needed for draft revision).
        platform: Platform name (needed for draft revision).

    Returns:
        Tuple of (decision, final_draft) where decision is "apply", "draft", or "skip".
    """
    bot_token = config["telegram"]["bot_token"]
    user_id = config["telegram"]["user_id"]
    timeout_minutes = config["settings"].get("approval_timeout_minutes", 30)

    bot = Bot(token=bot_token)
    current_draft = draft
    edit_round = 0

    while edit_round <= MAX_EDIT_ROUNDS:
        # Send draft with buttons
        message_id = await _send_draft_message(
            bot, user_id, listing_summary, current_draft, timeout_minutes, edit_round
        )

        # Poll for button click
        raw_decision, deadline = await _poll_for_callback(
            bot, user_id, message_id, timeout_minutes
        )

        if raw_decision == "apply":
            await _edit_message_no_buttons(bot, user_id, message_id)
            await bot.send_message(chat_id=user_id, text="Applying!")
            return ("apply", current_draft)

        elif raw_decision == "skip" or raw_decision is None:
            await _edit_message_no_buttons(bot, user_id, message_id)
            if raw_decision is None:
                await bot.send_message(
                    chat_id=user_id,
                    text=f"Timed out after {timeout_minutes} min — auto-skipping.",
                )
            else:
                await bot.send_message(chat_id=user_id, text="Skipped.")
            return ("skip", current_draft)

        elif raw_decision == "edit":
            edit_round += 1
            if edit_round > MAX_EDIT_ROUNDS:
                await _edit_message_no_buttons(bot, user_id, message_id)
                await bot.send_message(
                    chat_id=user_id,
                    text=f"Maximum edit rounds ({MAX_EDIT_ROUNDS}) reached — auto-skipping.",
                )
                return ("skip", current_draft)

            # Ask for feedback
            await _edit_message_no_buttons(bot, user_id, message_id)
            feedback_msg = await bot.send_message(
                chat_id=user_id,
                text=f"What should I change? (Edit round {edit_round}/{MAX_EDIT_ROUNDS})\n\nType your feedback:",
            )

            # Wait for text reply
            feedback = await _poll_for_text_reply(
                bot, user_id, feedback_msg.message_id, timeout_minutes=15
            )

            if feedback is None:
                await bot.send_message(
                    chat_id=user_id,
                    text="No feedback received — auto-skipping.",
                )
                return ("skip", current_draft)

            # Regenerate with feedback
            await bot.send_message(chat_id=user_id, text="Revising draft...")
            try:
                from appi_claw.draft_gen import revise_draft
                current_draft = revise_draft(
                    current_draft, feedback, listing, config, platform
                )
            except Exception as e:
                await bot.send_message(
                    chat_id=user_id, text=f"Revision failed: {e}. Keeping original."
                )
            # Loop continues with new draft

    return ("skip", current_draft)


async def _send_draft_message(
    bot: Bot,
    user_id: int,
    listing_summary: str,
    draft: str,
    timeout_minutes: int,
    edit_round: int,
) -> int:
    """Send draft message with inline keyboard. Returns message_id."""
    max_draft = 1800
    draft_display = draft[:max_draft] + "..." if len(draft) > max_draft else draft

    round_note = f" (Revision {edit_round})" if edit_round > 0 else ""
    text = (
        f"New Application{round_note}\n\n"
        f"{listing_summary}\n\n"
        f"--- Draft ---\n"
        f"{draft_display}\n"
        f"--- End Draft ---\n\n"
        f"Reply within {timeout_minutes} min:"
    )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Apply", callback_data="approve"),
            InlineKeyboardButton("Edit Draft", callback_data="edit"),
            InlineKeyboardButton("Skip", callback_data="skip"),
        ]
    ])

    sent = await bot.send_message(
        chat_id=user_id,
        text=text,
        reply_markup=keyboard,
    )
    return sent.message_id


async def _edit_message_no_buttons(bot: Bot, user_id: int, message_id: int):
    """Remove inline keyboard from a message."""
    try:
        await bot.edit_message_reply_markup(
            chat_id=user_id, message_id=message_id, reply_markup=None
        )
    except Exception:
        pass


async def _poll_for_callback(
    bot: Bot,
    user_id: int,
    message_id: int,
    timeout_minutes: int,
) -> tuple[str | None, float]:
    """Poll getUpdates for a callback_query on our message.

    Returns (decision, deadline) where decision is "approve", "edit", "skip", or None (timeout).
    """
    deadline = time.time() + (timeout_minutes * 60)
    offset = 0

    try:
        existing = await bot.get_updates(timeout=1, allowed_updates=["callback_query"])
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
                    # Map button data to internal decision
                    data = query.data
                    if data == "approve":
                        return ("apply", deadline)
                    elif data == "edit":
                        return ("edit", deadline)
                    else:
                        return ("skip", deadline)

        await asyncio.sleep(2)

    return (None, deadline)


async def _poll_for_text_reply(
    bot: Bot,
    user_id: int,
    after_message_id: int,
    timeout_minutes: int = 15,
) -> str | None:
    """Poll for a plain text message from the user after a given message_id.

    Returns the text, or None on timeout.
    """
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
                return update.message.text.strip()

        await asyncio.sleep(2)

    return None


def send_approval_sync(listing_summary: str, draft: str, config: dict, listing=None, platform: str | None = None) -> tuple[str, str]:
    """Synchronous wrapper for send_approval_request."""
    return asyncio.run(send_approval_request(listing_summary, draft, config, listing, platform))


async def notify(message: str, config: dict) -> None:
    """Send a plain notification to the user on Telegram."""
    bot = Bot(token=config["telegram"]["bot_token"])
    await bot.send_message(chat_id=config["telegram"]["user_id"], text=message)


def notify_sync(message: str, config: dict) -> None:
    """Synchronous wrapper for notify."""
    asyncio.run(notify(message, config))
