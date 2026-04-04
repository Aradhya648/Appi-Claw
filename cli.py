"""Appi-Claw CLI — standalone command-line interface."""

import typer
from pathlib import Path

app = typer.Typer(
    name="appi-claw",
    help="Automated job application assistant.",
    no_args_is_help=True,
)


@app.command()
def apply(
    url: str = typer.Argument(..., help="Listing URL to apply to"),
    config: str = typer.Option(None, "--config", "-c", help="Path to config.json"),
    dry_run: bool = typer.Option(True, "--dry-run/--live", help="Dry-run mode (default: on)"),
):
    """Process a single job/internship listing."""
    typer.echo(f"[Appi-Claw] Processing: {url}")
    typer.echo(f"  dry_run={dry_run}")
    typer.echo("  ⚠ Full pipeline not yet implemented — see Milestones 2-5.")


@app.command()
def status():
    """Show current application queue status."""
    typer.echo("[Appi-Claw] Status: No active queue yet — see Milestone 6.")


@app.command()
def list_apps():
    """List pending and completed applications."""
    typer.echo("[Appi-Claw] No applications logged yet — see Milestone 5.")


if __name__ == "__main__":
    app()
