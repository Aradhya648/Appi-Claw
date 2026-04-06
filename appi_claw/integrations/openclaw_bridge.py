"""
appi_claw/integrations/openclaw_bridge.py

Bridge script: DRUT job-finder cron → Appi-Claw pipeline.

DRUT calls this after finding new listings.  It triggers the full
pipeline (draft → Telegram approval → apply → log) and exits with
code 0 on success or 1 on failure.

Usage::

    python3 ~/Appi-Claw/appi_claw/integrations/openclaw_bridge.py \\
        --url "<listing_url>" \\
        --company "<company_name>" \\
        --role "<role_title>" \\
        --platform "<internshala|linkedin|wellfound|cold_email>"

Exit codes:
    0 — pipeline triggered successfully
    1 — failure; stderr contains the reason
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from appi_claw.logger import get_logger
from appi_claw.platforms import detect_platform

log = get_logger(__name__)

_CLI_PATH = Path(__file__).resolve().parents[2] / "appi_claw" / "cli.py"


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="openclaw_bridge",
        description="Bridge: DRUT job-finder → Appi-Claw pipeline",
    )
    p.add_argument("--url",      required=True, help="Listing URL")
    p.add_argument("--company",  default="",    help="Company name (optional)")
    p.add_argument("--role",     default="",    help="Role title (optional)")
    p.add_argument("--platform", default="",    help="Platform override (auto-detected if omitted)")
    p.add_argument("--live",     action="store_true", default=False,
                   help="Actually submit the form (default: dry-run)")
    return p.parse_args()


def _build_cmd(args: argparse.Namespace) -> list[str]:
    cmd = [sys.executable, str(_CLI_PATH), "apply", args.url]
    if args.company:
        cmd += ["--company", args.company]
    if args.role:
        cmd += ["--role", args.role]
    if args.live:
        cmd.append("--live")
    return cmd


def _run(args: argparse.Namespace) -> int:
    platform = args.platform or detect_platform(args.url)
    log.info(
        "Bridge triggered | url=%s | company=%s | role=%s | platform=%s",
        args.url, args.company or "(none)", args.role or "(none)", platform,
    )

    if not _CLI_PATH.exists():
        msg = f"CLI not found at {_CLI_PATH}. Is Appi-Claw installed?"
        log.error(msg)
        print(msg, file=sys.stderr)
        return 1

    try:
        result = subprocess.run(
            _build_cmd(args), capture_output=True, text=True, timeout=600,
        )
    except subprocess.TimeoutExpired:
        msg = f"Pipeline timed out (10 min) for: {args.url}"
        log.error(msg)
        print(msg, file=sys.stderr)
        return 1
    except Exception as exc:
        msg = f"Failed to launch pipeline: {exc}"
        log.error(msg, exc_info=True)
        print(msg, file=sys.stderr)
        return 1

    if result.stdout:
        print(result.stdout)

    if result.returncode != 0:
        log.error("Pipeline failed (code %d): %s", result.returncode, result.stderr.strip())
        print(result.stderr, file=sys.stderr)
        return 1

    try:
        out = json.loads(result.stdout)
        log.info("Pipeline done | status=%s | company=%s | role=%s",
                 out.get("status"), out.get("company"), out.get("role"))
    except Exception:
        log.info("Pipeline completed")

    return 0


def main() -> None:
    sys.exit(_run(_parse_args()))


if __name__ == "__main__":
    main()
