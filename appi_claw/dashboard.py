"""
appi_claw/dashboard.py

Rich terminal status dashboard — called by `appi-claw status`.

Follow-up column colour logic:
  < 5 days   → "X days left"        (white)
  5-10 days  → "Follow up now"      (yellow)
  > 10 days  → "Consider closed"    (red)
  Interview  → "Prep needed"        (green)
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from appi_claw.logger import get_logger

log = get_logger(__name__)


def _days_since(applied_on: str) -> int | None:
    try:
        return (date.today() - datetime.strptime(applied_on, "%Y-%m-%d").date()).days
    except (ValueError, TypeError):
        return None


def _followup(status: str, applied_on: str) -> tuple[str, str]:
    if status.lower() in ("interview", "interviewing"):
        return "Prep needed", "bold green"
    days = _days_since(applied_on)
    if days is None:
        return "Unknown", "dim"
    if days > 10:
        return "Consider closed", "bold red"
    if days >= 5:
        return "Follow up now", "bold yellow"
    rem = 5 - days
    return f"{rem} day{'s' if rem != 1 else ''} left", "white"


def render_status_dashboard(applications: list[dict[str, Any]]) -> None:
    """Render a rich terminal table of recent applications."""
    try:
        from rich.console import Console
        from rich.table import Table
        from rich import box
    except ImportError:
        log.warning("'rich' not installed — using plain text")
        _plain(applications)
        return

    console = Console()
    if not applications:
        console.print("[yellow]No applications found.[/yellow]")
        return

    t = Table(title="Appi-Claw — Application Tracker",
              box=box.ROUNDED, show_lines=True, highlight=True)
    t.add_column("Company",    style="bold cyan", no_wrap=True)
    t.add_column("Role",       style="white")
    t.add_column("Applied On", style="dim", no_wrap=True)
    t.add_column("Status",     no_wrap=True)
    t.add_column("Follow-up",  no_wrap=True)

    STATUS_STYLES = {
        "applied": "green", "draft sent": "blue", "skipped": "dim",
        "failed": "red", "interview": "bold green", "interviewing": "bold green",
        "waiting": "yellow", "closed": "dim red",
    }

    for app in applications:
        s   = app.get("status", "—")
        ao  = app.get("applied_on", "—")
        fl, fs = _followup(s, ao)
        ss  = STATUS_STYLES.get(s.lower(), "white")
        t.add_row(
            app.get("company", "—"), app.get("role", "—"), ao,
            f"[{ss}]{s}[/{ss}]", f"[{fs}]{fl}[/{fs}]",
        )

    console.print(t)
    total = len(applications)
    counts: dict[str, int] = {}
    for a in applications:
        k = a.get("status", "Unknown")
        counts[k] = counts.get(k, 0) + 1
    parts = [f"[bold]{total} total[/bold]"] + [f"{v} {k}" for k, v in counts.items()]
    console.print("  " + " · ".join(parts) + "\n")


def _plain(apps: list[dict[str, Any]]) -> None:
    if not apps:
        print("No applications found.")
        return
    print(f"\n{'Company':<20} {'Role':<30} {'Applied On':<12} {'Status':<12} Follow-up")
    print("─" * 90)
    for a in apps:
        fl, _ = _followup(a.get("status",""), a.get("applied_on",""))
        print(f"{a.get('company','—')[:19]:<20} {a.get('role','—')[:29]:<30} "
              f"{a.get('applied_on','—'):<12} {a.get('status','—'):<12} {fl}")
    print()
