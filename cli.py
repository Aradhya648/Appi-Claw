"""Appi-Claw CLI — standalone command-line interface."""

import typer
from appi_claw.config import load_config
from appi_claw.platforms.base import Listing
from appi_claw.draft_gen import generate_draft

app = typer.Typer(
    name="appi-claw",
    help="Automated job application assistant.",
    no_args_is_help=True,
)


@app.command()
def apply(
    url: str = typer.Argument(..., help="Listing URL to apply to"),
    config_path: str = typer.Option(None, "--config", "-c", help="Path to config.json"),
    dry_run: bool = typer.Option(True, "--dry-run/--live", help="Dry-run mode (default: on)"),
):
    """Process a single job/internship listing."""
    typer.echo(f"[Appi-Claw] Processing: {url}")
    typer.echo(f"  dry_run={dry_run}")
    typer.echo("  Full pipeline not yet implemented — see Milestones 3-5.")

    config = load_config(config_path)
    platform = _detect_platform(url)
    listing = Listing(url=url, platform=platform)

    typer.echo(f"  Platform detected: {platform}")
    typer.echo("  Generating draft...")

    draft = generate_draft(listing, config, platform)
    typer.echo("\n--- DRAFT ---")
    typer.echo(draft)
    typer.echo("--- END DRAFT ---")


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
def status():
    """Show current application queue status."""
    typer.echo("[Appi-Claw] Status: No active queue yet — see Milestone 6.")


@app.command()
def list_apps():
    """List pending and completed applications."""
    typer.echo("[Appi-Claw] No applications logged yet — see Milestone 5.")


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
