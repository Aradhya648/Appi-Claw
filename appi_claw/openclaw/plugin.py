"""OpenClaw plugin wrapper for Appi-Claw.

Exposes tools that DRUT can call:
  - appi_claw_process(listing) — full pipeline: draft → approve → apply → log
  - appi_claw_status()          — current queue status
  - appi_claw_list()            — recent applications from tracker

All functions are synchronous and return JSON-serializable dicts/lists
so DRUT can consume the results directly.
"""

import asyncio
from appi_claw.config import load_config
from appi_claw.draft_gen import generate_draft
from appi_claw.telegram_bot import send_approval_request
from appi_claw.sheets import log_application, _get_worksheet
from appi_claw.platforms.base import Listing, ApplicationResult


def appi_claw_process(listing: dict) -> dict:
    """Process a listing through the full Appi-Claw pipeline.

    Args:
        listing: dict with keys: url (required), company, role, platform, description.

    Returns:
        dict with: status, decision, draft, message.
    """
    config = load_config()

    url = listing.get("url", "")
    if not url:
        return {"status": "error", "message": "Missing required field: url"}

    company = listing.get("company", "")
    role = listing.get("role", "")
    platform = listing.get("platform", "") or _detect_platform(url)
    description = listing.get("description", "")

    listing_obj = Listing(
        url=url,
        company=company,
        role=role,
        platform=platform,
        description=description,
    )

    # Step 1: Generate draft
    try:
        draft = generate_draft(listing_obj, config, platform)
    except Exception as e:
        return {"status": "error", "message": f"Draft generation failed: {e}"}

    # Step 2: Telegram approval
    summary = (
        f"Company: {company or 'Unknown'}\n"
        f"Role: {role or 'Unknown'}\n"
        f"Platform: {platform}\n"
        f"URL: {url}"
    )
    try:
        decision = asyncio.run(send_approval_request(summary, draft, config))
    except Exception as e:
        decision = "skip"
        draft_note = f"Telegram approval failed: {e}"

    # Step 3: Act on decision
    result_status = "Skipped"
    message = ""

    if decision == "apply":
        result = asyncio.run(_run_adapter(listing_obj, draft, config))
        result_status = result.status.title()
        message = result.message
    elif decision == "draft":
        result_status = "Draft Sent"
        message = "User chose draft only."
    else:
        result_status = "Skipped"
        message = "User skipped or timed out."

    # Step 4: Log to Sheets
    try:
        log_application(
            config,
            company=company or "Unknown",
            role=role or "Unknown",
            platform=platform,
            status=result_status,
            url=url,
            draft=draft,
            notes=f"Via DRUT/OpenClaw. {message}",
        )
    except Exception:
        pass  # Non-critical

    return {
        "status": result_status,
        "decision": decision,
        "draft": draft,
        "message": message,
        "company": company,
        "role": role,
        "platform": platform,
        "url": url,
    }


def appi_claw_status() -> dict:
    """Return current application queue status.

    Returns summary stats from the Google Sheets tracker.
    """
    config = load_config()
    try:
        ws = _get_worksheet(config)
        rows = ws.get_all_values()
        if len(rows) <= 1:
            return {"total": 0, "message": "No applications logged yet."}

        data = rows[1:]
        total = len(data)
        statuses = {}
        for row in data:
            s = row[4] if len(row) > 4 else "Unknown"
            statuses[s] = statuses.get(s, 0) + 1

        return {
            "total": total,
            "breakdown": statuses,
            "message": f"{total} applications tracked.",
        }
    except Exception as e:
        return {"total": -1, "message": f"Error reading tracker: {e}"}


def appi_claw_list(limit: int = 10) -> list:
    """List recent applications from the tracker.

    Args:
        limit: Max number of entries to return (default 10).

    Returns:
        List of dicts with application details.
    """
    config = load_config()
    try:
        ws = _get_worksheet(config)
        rows = ws.get_all_values()
        if len(rows) <= 1:
            return []

        headers = [h.lower().replace(" ", "_") for h in rows[0]]
        data = rows[1:]
        recent = data[-limit:] if len(data) > limit else data

        results = []
        for row in reversed(recent):
            entry = {}
            for i, h in enumerate(headers):
                if i < len(row) and row[i]:
                    entry[h] = row[i]
            results.append(entry)

        return results
    except Exception as e:
        return [{"error": str(e)}]


async def _run_adapter(listing: Listing, draft: str, config: dict) -> ApplicationResult:
    """Run platform adapter with dry_run from config."""
    dry_run = config["settings"].get("dry_run", True)
    headless = config["settings"].get("playwright_headless", True)
    platform = listing.platform or "internshala"

    if platform == "internshala":
        from appi_claw.platforms.internshala import InternshalaAdapter
        adapter = InternshalaAdapter(headless=headless)
    elif platform == "linkedin":
        from appi_claw.platforms.linkedin import LinkedInAdapter
        adapter = LinkedInAdapter(headless=headless)
    else:
        return ApplicationResult(
            success=False,
            status="failed",
            message=f"Platform adapter '{platform}' not yet implemented.",
        )

    try:
        creds = config.get("platforms", {}).get(platform, {})
        await adapter.login(creds)
        if not listing.company:
            listing = await adapter.parse_listing(listing.url)
        return await adapter.fill_and_submit(listing, draft, dry_run=dry_run)
    except Exception as e:
        return ApplicationResult(
            success=False,
            status="failed",
            message=str(e),
            draft=draft,
        )
    finally:
        await adapter.close()


def _detect_platform(url: str) -> str:
    """Guess platform from URL."""
    url_lower = url.lower()
    if "internshala" in url_lower:
        return "internshala"
    elif "linkedin" in url_lower:
        return "linkedin"
    elif "wellfound" in url_lower or "angel.co" in url_lower:
        return "wellfound"
    return "internshala"
