"""Application draft generator using Claude API. (Milestone 2)"""

from appi_claw.platforms.base import Listing


async def generate_draft(listing: Listing, user_profile: dict, api_key: str, model: str) -> str:
    """Generate a platform-appropriate application draft for a listing.

    Implementation comes in Milestone 2.
    """
    raise NotImplementedError("Draft generation not yet implemented — see Milestone 2.")
