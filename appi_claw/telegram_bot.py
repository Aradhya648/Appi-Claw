"""Telegram approval flow for Appi-Claw. (Milestone 3)

Sends listing to user, waits for:
  1 = auto-apply
  2 = draft only
  3 = skip
Timeout after 30 min → auto-skip.
"""


async def send_approval_request(listing_summary: str, config: dict) -> str:
    """Send listing to user and wait for approval decision.

    Returns: "apply", "draft", or "skip".
    Implementation comes in Milestone 3.
    """
    raise NotImplementedError("Telegram approval flow not yet implemented — see Milestone 3.")
