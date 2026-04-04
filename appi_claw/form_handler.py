"""Smart form question handler for Appi-Claw.

Auto-fills known fields from user profile.
For unknown/open-ended questions, asks user via Telegram and waits for reply.

Auto-fill rules (no Telegram prompt):
  - Graduation year       → from user profile
  - Degree type           → BBA from user profile
  - Availability/start    → "Immediately"
  - GitHub URL            → from user profile
  - Portfolio URL         → from user profile
  - "I agree" checkboxes  → auto-check
  - Referral code         → leave blank
  - Notice period         → "Immediately available"
  - Stipend expectations  → leave blank
  - Location / city       → from user profile
  - Phone / mobile        → leave blank (likely pre-filled)

Telegram prompt (waits up to 15 min):
  - "Why do you want to join" style questions
  - Any open-ended free-text question not matched above
  - Salary/CTC expectations (explicitly required)
  - Any field the handler is not confident about
"""

import asyncio
import re
import time
from playwright.async_api import Page


# --- Auto-fill value resolver ---

def _resolve_auto_value(label: str, field_type: str, user_profile: dict) -> str | None:
    """Return a value to auto-fill, or None if should be left blank or prompted.

    Returns:
        str  → fill with this value
        ""   → leave blank explicitly
        None → ask user via Telegram
    """
    label_l = label.lower().strip()

    # Checkboxes — "agree", "terms", "privacy", "policy" → check it
    if field_type == "checkbox":
        if any(w in label_l for w in ("agree", "terms", "condition", "policy", "privacy", "consent")):
            return "check"
        return None  # Unknown checkbox → ask

    # Leave blank (don't prompt)
    if any(w in label_l for w in ("referral", "promo code", "coupon", "stipend", "salary expectation",
                                   "expected salary", "expected ctc", "current ctc")):
        return ""

    # Notice period / availability / start date
    if any(w in label_l for w in ("notice period", "availability", "available from",
                                   "start date", "joining date", "when can you join",
                                   "earliest start")):
        return "Immediately"

    # Graduation / passing year
    if any(w in label_l for w in ("graduation year", "passing year", "year of graduation",
                                   "expected graduation", "batch")):
        return "2026"

    # Degree / qualification
    if any(w in label_l for w in ("degree", "qualification", "education", "highest qualification")):
        return user_profile.get("degree", "BBA")

    # GitHub
    if "github" in label_l:
        gh = user_profile.get("github", "")
        return f"https://github.com/{gh}" if gh else ""

    # Portfolio / website / linkedin
    if any(w in label_l for w in ("portfolio", "website", "personal site")):
        return ""  # Leave blank — no portfolio URL in profile

    # Location / city
    if any(w in label_l for w in ("city", "location", "current city", "hometown", "preferred location")):
        return user_profile.get("location", "Lucknow, India")

    # Name
    if label_l in ("name", "full name", "your name", "applicant name"):
        return user_profile.get("name", "")

    # Skills
    if label_l in ("skills", "key skills", "technical skills"):
        skills = user_profile.get("skills", [])
        return ", ".join(skills) if skills else None

    # Phone → leave blank (probably pre-filled)
    if any(w in label_l for w in ("phone", "mobile", "contact number")):
        return ""

    # Cover letter / application message / why hire → already handled by draft, skip prompt
    if any(w in label_l for w in ("cover letter", "why should we hire", "application message",
                                   "about yourself", "tell us about")):
        return None  # Caller should use the draft text here

    # Open-ended questions → ask user
    return None


# --- Telegram question asker ---

async def _ask_user(question_text: str, config: dict, timeout_minutes: int = 15) -> str | None:
    """Send a question to user on Telegram and wait for a text reply.

    Returns the user's reply, or None on timeout.
    Reply 'skip' → returns empty string (leave blank).
    """
    from telegram import Bot

    bot = Bot(token=config["telegram"]["bot_token"])
    user_id = config["telegram"]["user_id"]

    prompt = (
        f"Form question needs your answer:\n\n"
        f"{question_text}\n\n"
        f"Reply with your answer, or type 'skip' to leave blank.\n"
        f"(Timeout: {timeout_minutes} min)"
    )
    sent = await bot.send_message(chat_id=user_id, text=prompt)

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
                and update.message.message_id > sent.message_id
            ):
                reply = update.message.text.strip()
                if reply.lower() == "skip":
                    return ""
                return reply

        await asyncio.sleep(2)

    await bot.send_message(
        chat_id=user_id,
        text="No reply received — leaving the field blank.",
    )
    return None


# --- Main field handler ---

async def handle_field(
    inp,
    label: str,
    field_type: str,
    user_profile: dict,
    config: dict,
    draft: str = "",
) -> bool:
    """Handle a single form field intelligently.

    Args:
        inp: Playwright locator for the input element.
        label: Detected label text.
        field_type: "text", "textarea", "checkbox", "select", "radio".
        user_profile: From config.
        config: Full app config.
        draft: Current application draft (used for open cover letter fields).

    Returns:
        True if field was handled (filled or skipped), False if error.
    """
    try:
        # Cover letter / why hire → fill with draft
        label_l = label.lower()
        if any(w in label_l for w in ("cover letter", "why should we hire", "application message",
                                       "about yourself", "tell us about")) and field_type == "textarea":
            await inp.fill(draft[:2000])
            return True

        auto_val = _resolve_auto_value(label, field_type, user_profile)

        if auto_val == "check" and field_type == "checkbox":
            if not await inp.is_checked():
                await inp.check()
            return True

        if auto_val == "":
            return True  # Leave blank

        if auto_val is not None:
            # Auto-fill
            if field_type in ("text", "textarea", "email", "url", "number"):
                current = (await inp.input_value()).strip()
                if not current:
                    await inp.fill(auto_val)
            return True

        # Unknown field → ask user via Telegram
        if not label:
            return True  # No label, skip silently

        # Only prompt for text/textarea fields
        if field_type not in ("text", "textarea", "email"):
            return True

        # Don't prompt if already filled
        try:
            current = (await inp.input_value()).strip()
            if current:
                return True
        except Exception:
            pass

        user_answer = await _ask_user(label, config, timeout_minutes=15)
        if user_answer:
            await inp.fill(user_answer)

        return True

    except Exception:
        return False


# --- Page scanner ---

async def handle_all_fields(
    page: Page,
    user_profile: dict,
    config: dict,
    draft: str = "",
) -> dict:
    """Scan a page and intelligently handle all visible form fields.

    Returns summary dict with counts of auto-filled, asked, skipped fields.
    """
    counts = {"auto": 0, "asked": 0, "skipped": 0}

    # --- Text inputs ---
    inputs = page.locator("input[type='text']:visible, input[type='email']:visible, input[type='url']:visible, input[type='number']:visible")
    count = await inputs.count()
    for i in range(count):
        inp = inputs.nth(i)
        label = await _get_label(page, inp)
        handled = await handle_field(inp, label, "text", user_profile, config, draft)
        counts["auto" if handled else "skipped"] += 1

    # --- Textareas ---
    textareas = page.locator("textarea:visible")
    count = await textareas.count()
    for i in range(count):
        ta = textareas.nth(i)
        label = await _get_label(page, ta)
        current = (await ta.input_value()).strip()
        if current:
            continue
        handled = await handle_field(ta, label, "textarea", user_profile, config, draft)
        counts["auto" if handled else "skipped"] += 1

    # --- Checkboxes ---
    checkboxes = page.locator("input[type='checkbox']:visible")
    count = await checkboxes.count()
    for i in range(count):
        cb = checkboxes.nth(i)
        label = await _get_label(page, cb)
        handled = await handle_field(cb, label, "checkbox", user_profile, config, draft)
        counts["auto" if handled else "skipped"] += 1

    return counts


async def _get_label(page: Page, element) -> str:
    """Extract label text for a form element."""
    try:
        # Try aria-label first
        aria = await element.get_attribute("aria-label") or ""
        if aria:
            return aria.strip()

        # Try for= label
        el_id = await element.get_attribute("id")
        if el_id:
            label_el = page.locator(f"label[for='{el_id}']").first
            if await label_el.count() > 0:
                text = await label_el.text_content()
                if text:
                    return text.strip()

        # Try placeholder
        placeholder = await element.get_attribute("placeholder") or ""
        if placeholder:
            return placeholder.strip()

        # Try name attribute
        name = await element.get_attribute("name") or ""
        if name:
            # Convert snake_case/camelCase to readable
            return re.sub(r"[_-]", " ", name).strip()

    except Exception:
        pass

    return ""
