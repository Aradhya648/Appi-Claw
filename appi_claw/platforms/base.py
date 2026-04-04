"""Base class for all platform adapters."""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class Listing:
    """A job/internship listing to apply to."""
    url: str
    company: str = ""
    role: str = ""
    platform: str = ""
    description: str = ""
    extra: dict | None = None


@dataclass
class ApplicationResult:
    """Result of an application attempt."""
    success: bool
    status: str  # "applied", "draft_sent", "skipped", "failed"
    message: str = ""
    draft: str = ""


class PlatformAdapter(ABC):
    """Base class that every platform adapter must implement."""

    name: str = "base"

    @abstractmethod
    async def login(self, credentials: dict) -> None:
        """Authenticate with the platform."""
        ...

    @abstractmethod
    async def parse_listing(self, url: str) -> Listing:
        """Extract listing details from a URL."""
        ...

    @abstractmethod
    async def fill_and_submit(self, listing: Listing, draft: str, dry_run: bool = True) -> ApplicationResult:
        """Fill the application form and submit (or dry-run)."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """Clean up resources (browser, etc.)."""
        ...
