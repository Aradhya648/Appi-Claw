"""
appi_claw/logger.py

Centralised logging for Appi-Claw.
  - Log file:    ~/appi-claw.log
  - Screenshots: ~/appi-claw-screenshots/<timestamp>_<context>.png

Usage in any module::

    from appi_claw.logger import get_logger
    log = get_logger(__name__)
    log.info("Processing %s", url)
"""

import logging
import os
from datetime import datetime
from pathlib import Path

LOG_FILE       = Path.home() / "appi-claw.log"
SCREENSHOT_DIR = Path.home() / "appi-claw-screenshots"

_configured = False


def _configure_root_logger() -> None:
    global _configured
    if _configured:
        return

    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger("appi_claw")
    root.setLevel(logging.DEBUG)

    fmt = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    root.addHandler(fh)

    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    root.addHandler(ch)

    _configured = True


def get_logger(name: str) -> logging.Logger:
    """Return a child logger under the appi_claw namespace."""
    _configure_root_logger()
    return logging.getLogger(name)


def screenshot_path(context: str = "error") -> Path:
    """Return a timestamped path for a failure screenshot."""
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe = context.replace(" ", "_").replace("/", "_")[:60]
    return SCREENSHOT_DIR / f"{ts}_{safe}.png"


def log_pipeline_error(
    logger: logging.Logger,
    step: str,
    url: str,
    error: Exception,
    screenshot: Path | None = None,
) -> None:
    """Log a pipeline failure with enough context to debug."""
    parts = [
        f"Pipeline error at step '{step}'",
        f"URL: {url}",
        f"Error ({type(error).__name__}): {error}",
    ]
    if screenshot and screenshot.exists():
        parts.append(f"Screenshot: {screenshot}")
    logger.error(" | ".join(parts), exc_info=True)
