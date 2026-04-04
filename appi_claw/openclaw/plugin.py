"""OpenClaw plugin wrapper for Appi-Claw. (Milestone 6)

Exposes tools that DRUT can call:
  - appi_claw_process(listing) — main entry point, triggers approval flow
  - appi_claw_status()          — returns current queue status
  - appi_claw_list()            — lists pending/completed applications
"""


def appi_claw_process(listing: dict) -> dict:
    """Process a listing through the full Appi-Claw pipeline.

    Implementation comes in Milestone 6.
    """
    raise NotImplementedError("OpenClaw plugin not yet implemented — see Milestone 6.")


def appi_claw_status() -> dict:
    """Return current queue status."""
    raise NotImplementedError("OpenClaw plugin not yet implemented — see Milestone 6.")


def appi_claw_list() -> list:
    """List pending and completed applications."""
    raise NotImplementedError("OpenClaw plugin not yet implemented — see Milestone 6.")
