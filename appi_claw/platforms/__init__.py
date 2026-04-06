"""
appi_claw/platforms/__init__.py

Platform registry and URL-based auto-detection.

Usage::

    from appi_claw.platforms import detect_platform
    platform = detect_platform("https://internshala.com/internship/detail/abc")
    # → "internshala"
"""

from __future__ import annotations
import re
from typing import Literal

PlatformName = Literal["internshala", "linkedin", "wellfound", "cold_email"]

_PLATFORM_PATTERNS: list[tuple[re.Pattern[str], PlatformName]] = [
    (re.compile(r"internshala\.com",  re.IGNORECASE), "internshala"),
    (re.compile(r"linkedin\.com/jobs", re.IGNORECASE), "linkedin"),
    (re.compile(r"wellfound\.com",    re.IGNORECASE), "wellfound"),
    (re.compile(r"angel\.co",         re.IGNORECASE), "wellfound"),
]


def detect_platform(url: str) -> PlatformName:
    """
    Detect the job platform from a listing URL.

    Returns one of: "internshala", "linkedin", "wellfound", "cold_email".
    Falls back to "cold_email" if no pattern matches.

    Examples::

        detect_platform("https://internshala.com/internship/detail/abc")
        # → "internshala"

        detect_platform("https://www.linkedin.com/jobs/view/123")
        # → "linkedin"

        detect_platform("https://some-startup.com/careers")
        # → "cold_email"
    """
    for pattern, platform in _PLATFORM_PATTERNS:
        if pattern.search(url):
            return platform
    return "cold_email"
