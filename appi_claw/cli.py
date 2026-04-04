"""Appi-Claw CLI — standalone command-line interface.

Usage after install:
    appi-claw init
    appi-claw apply "https://internshala.com/..."
    appi-claw draft "https://linkedin.com/..." --company Razorpay --role "Growth Analyst"
    appi-claw status
    appi-claw list-apps --limit 5
"""

import asyncio
import shutil
from pathlib import Path

import typer
from appi_claw.config import load_config, DEFAULT_CONFIG_PATH
from appi_claw.platforms.base import Listing
from appi_claw.draft_gen import generate_draft
from appi_claw.telegram_bot import send_approval_request
from appi_claw.sheets import log_application

app = typer.Typer(
    name="appi-claw",
    help="Automated job application assistant. Draft, approve, apply, log.",
    no_args_is_help=True,
)


@app.command()
def init(
    config_path: str = typer.Option(None, "--config", "-c", help="Custom config path"),
):
    """Set up Appi-Claw config for first use."""
    target = Path(config_path) if config_path else DEFAULT_CONFIG_PATH

    if target.exists():
        typer.echo(f"Config already exists at {target}")
        return

    example = Path(__file__).parent.parent / "config.example.json"
    if not example.exists():
        example = Path.cwd() / "config.example.json"

    if example.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(example, target)
        typer.echo(f"Config created at {target}")
        typer.echo("Edit it with your credentials before using appi-claw.")
    else:
        typer.echo(f"Create {DEFAULT_CONFIG_PATH} manually (see config.example.json in the repo).")


@app.command()
def apply(
    url: str = typer.Argument(..., help="Listing URL to apply to"),
    company: str = typer.Option("", "--company", help="Company name"),
    role: str = typer.Option("", "--role", help="Role title"),
    config_path: str = typer.Option(None, "--config", "-c", help="Path to config.json"),
    dry_run: bool = typer.Option(True, "--dry-run/--live", help="Dry-run mode (default: on)"),
    skip_approval: bool = typer.Option(False, "--skip-approval", help="Skip Telegram approval"),
):
    """Process a single job/internship listing through the full pipeline."""
    config = load_config(config_path)
    platform = _detect_platform(url)
    listing = Listing(url=url, company=company, role=role, platform=platform)

    typer.echo(f"[Appi-Claw] Processing: {url}")
    typer.echo(f"  Platform: {platform} | dry_run={dry_run}")

    # Step 1: Generate draft
    typer.echo("  Generating draft...")
    draft_text = generate_draft(listing, config, platform)
    typer.echo("\n--- DRAFT ---")
    typer.echo(draft_text)
    typer.echo("--- END DRAFT ---\n")

    # Step 2: Telegram approval
    if skip_approval:
        decision = "apply"
        typer.echo("  Approval skipped (--skip-approval).")
    else:
        typer.echo("  Sending to Telegram for approval...")
        summary = f"Company: {company or 'Unknown'}\nRole: {role or 'Unknown'}\nPlatform: {platform}\nURL: {url}"
        decision = asyncio.run(send_approval_request(summary, draft_text, config))
        typer.echo(f"  Decision: {decision}")

    # Step 3: Act on decision
    if decision == "apply":
        result = asyncio.run(_run_adapter(listing, draft_text, config, dry_run))
        typer.echo(f"  Result: {result.status} -- {result.message}")
        _log(config, company, role, platform, result.status, url, draft_text, result.message)
    elif decision == "draft":
        typer.echo("  Draft saved.")
        _log(config, company, role, platform, "Draft Sent", url, draft_text, "User chose draft only")
    else:
        typer.echo("  Skipped.")
        _log(config, company, role, platform, "Skipped", url, draft_text, "User skipped")


@app.command()
def draft(
    url: str = typer.Argument(..., help="Listing URL"),
    company: str = typer.Option("", "--company", help="Company name"),
    role: str = typer.Option("", "--role", help="Role title"),
    platform: str = typer.Option("", "--platform", "-p", help="Override platform detection"),
    config_path: str = typer.Option(None, "--config", "-c", help="Path to config.json"),
):
    """Generate an application draft without applying."""
    config = load_config(config_path)
    detected = platform or _detect_platform(url)
    listing = Listing(url=url, company=company, role=role, platform=detected)

    typer.echo(f"[Appi-Claw] Generating draft for {detected}...")
    result = generate_draft(listing, config, detected)
    typer.echo(result)


@app.command()
def status(
    config_path: str = typer.Option(None, "--config", "-c", help="Path to config.json"),
):
    """Show application tracker summary."""
    from appi_claw.sheets import _get_worksheet
    config = load_config(config_path)
    try:
        ws = _get_worksheet(config)
        rows = ws.get_all_values()
        if len(rows) <= 1:
            typer.echo("[Appi-Claw] No applications logged yet.")
            return

        data = rows[1:]
        total = len(data)
        statuses = {}
        for row in data:
            s = row[4] if len(row) > 4 else "Unknown"
            statuses[s] = statuses.get(s, 0) + 1

        typer.echo(f"[Appi-Claw] {total} applications tracked:")
        for s, count in sorted(statuses.items(), key=lambda x: -x[1]):
            typer.echo(f"  {s}: {count}")
    except Exception as e:
        typer.echo(f"[Appi-Claw] Error: {e}")


@app.command()
def list_apps(
    config_path: str = typer.Option(None, "--config", "-c", help="Path to config.json"),
    limit: int = typer.Option(10, "--limit", "-n", help="Number of recent entries"),
):
    """List recent applications from the tracker."""
    from appi_claw.sheets import _get_worksheet
    config = load_config(config_path)
    try:
        ws = _get_worksheet(config)
        rows = ws.get_all_values()
        if len(rows) <= 1:
            typer.echo("[Appi-Claw] No applications logged yet.")
            return
        headers = rows[0]
        data = rows[1:]
        recent = data[-limit:] if len(data) > limit else data
        for row in reversed(recent):
            line = " | ".join(f"{h}: {v}" for h, v in zip(headers[:5], row[:5]) if v)
            typer.echo(line)
    except Exception as e:
        typer.echo(f"[Appi-Claw] Error reading sheet: {e}")


def _log(config: dict, company: str, role: str, platform: str, status: str, url: str, draft: str, notes: str):
    """Log to Google Sheets, silently skip if it fails."""
    try:
        log_application(
            config,
            company=company or "Unknown",
            role=role or "Unknown",
            platform=platform,
            status=status,
            url=url,
            draft=draft,
            notes=notes,
        )
        typer.echo("  Logged to Google Sheets.")
    except Exception as e:
        typer.echo(f"  Warning: Sheets logging failed: {e}")


async def _run_adapter(listing: Listing, draft: str, config: dict, dry_run: bool):
    """Run the appropriate platform adapter to fill & submit the form."""
    from appi_claw.platforms.base import ApplicationResult

    platform = listing.platform or "internshala"
    headless = config["settings"].get("playwright_headless", True)

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

        result = await adapter.fill_and_submit(listing, draft, dry_run=dry_run)
        return result
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
    """Guess the platform from the URL."""
    url_lower = url.lower()
    if "internshala" in url_lower:
        return "internshala"
    elif "linkedin" in url_lower:
        return "linkedin"
    elif "wellfound" in url_lower or "angel.co" in url_lower:
        return "wellfound"
    return "internshala"


if __name__ == "__main__":
    app()
