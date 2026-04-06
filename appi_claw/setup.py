"""
appi_claw/setup.py

Interactive first-run setup wizard.
Called by:  appi-claw init

Walks the user through every required config field, tests each
integration live (Telegram, Gemini, Google Sheets), and saves a
completed config to ~/.appi-claw/config.json.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from appi_claw.logger import get_logger

log = get_logger(__name__)

CONFIG_DIR  = Path.home() / ".appi-claw"
CONFIG_PATH = CONFIG_DIR / "config.json"


# ── tiny UI helpers ───────────────────────────────────────────────────────────

def _ask(prompt: str, default: str = "") -> str:
    display = f"{prompt} [{default}]: " if default else f"{prompt}: "
    try:
        value = input(display).strip()
    except (EOFError, KeyboardInterrupt):
        print("\nSetup cancelled.")
        sys.exit(0)
    return value or default


def _ask_bool(prompt: str, default: bool = True) -> bool:
    hint = "(Y/n)" if default else "(y/N)"
    raw  = _ask(f"{prompt} {hint}", "y" if default else "n")
    return raw.lower() in ("y", "yes", "1", "true")


def _ask_list(prompt: str, example: str = "") -> list[str]:
    hint = f" (comma-separated, e.g. {example})" if example else " (comma-separated)"
    raw  = _ask(f"{prompt}{hint}")
    return [x.strip() for x in raw.split(",") if x.strip()]


def _sep(title: str = "") -> None:
    w = 58
    if title:
        pad = (w - len(title) - 2) // 2
        print("\n" + "─" * pad + f" {title} " + "─" * pad)
    else:
        print("\n" + "─" * w)


def _ok(m):   print(f"  ✓  {m}")
def _warn(m): print(f"  ⚠  {m}")


# ── integration tests ─────────────────────────────────────────────────────────

def _test_telegram(token: str, user_id: int) -> bool:
    try:
        import urllib.request
        url  = f"https://api.telegram.org/bot{token}/sendMessage"
        data = json.dumps({"chat_id": user_id, "text": "✅ Appi-Claw connected!"}).encode()
        req  = urllib.request.Request(url, data=data,
                                      headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read()).get("ok", False)
    except Exception as e:
        log.debug("Telegram test failed: %s", e)
        return False


def _test_gemini(api_key: str, model: str) -> bool:
    try:
        import urllib.request
        url  = (f"https://generativelanguage.googleapis.com/v1beta/models/"
                f"{model}:generateContent?key={api_key}")
        data = json.dumps({"contents": [{"parts": [{"text": "Reply with: ok"}]}]}).encode()
        req  = urllib.request.Request(url, data=data,
                                      headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as r:
            return "candidates" in json.loads(r.read())
    except Exception as e:
        log.debug("Gemini test failed: %s", e)
        return False


def _test_sheets(key_file: str, sheet_id: str) -> bool:
    try:
        import gspread  # type: ignore
        from oauth2client.service_account import ServiceAccountCredentials  # type: ignore
        scope = ["https://spreadsheets.google.com/feeds",
                 "https://www.googleapis.com/auth/drive"]
        creds  = ServiceAccountCredentials.from_json_keyfile_name(
                     os.path.expanduser(key_file), scope)
        client = gspread.authorize(creds)
        client.open_by_key(sheet_id)
        return True
    except ImportError:
        log.debug("gspread not installed — skipping sheets test")
        return False
    except Exception as e:
        log.debug("Sheets test failed: %s", e)
        return False


# ── wizard sections ───────────────────────────────────────────────────────────

def _profile() -> dict[str, Any]:
    _sep("Your Profile")
    print("Used by the AI to write personalised application drafts.\n")
    return {
        "name":             _ask("Full name"),
        "degree":           _ask("Degree & major", "e.g. B.Tech CS, 3.8 GPA"),
        "skills":           _ask_list("Skills", "Python, Excel, SQL"),
        "projects":         _ask_list("Projects", "My App, My Research"),
        "experience":       _ask("Brief experience summary", "e.g. 1 fintech internship"),
        "target_roles":     _ask_list("Target roles", "Software Intern, PM Intern"),
        "location":         _ask("Location", "e.g. Mumbai, India"),
        "remote_preference":_ask("Remote preference", "remote preferred"),
        "github":           _ask("GitHub username (optional)", ""),
        "portfolio_url":    _ask("Portfolio URL (optional)", ""),
        "graduation_year":  _ask("Graduation year", "2026"),
    }


def _telegram() -> tuple[dict, bool]:
    _sep("Telegram Bot")
    print("Create a bot via @BotFather. Get your user ID from @userinfobot.\n")
    token = _ask("Bot token")
    uid_s = _ask("Your Telegram user ID (numbers only)")
    try:
        uid = int(uid_s)
    except ValueError:
        _warn("Invalid user ID — must be numbers only.")
        return {"bot_token": token, "user_id": 0}, False
    print("  Testing connection...")
    ok = _test_telegram(token, uid)
    _ok("Connected! Check Telegram for a test message.") if ok else _warn("Could not verify — check token and ID.")
    return {"bot_token": token, "user_id": uid}, ok


def _gemini() -> tuple[dict, bool]:
    _sep("Gemini API")
    print("Get a free key at https://aistudio.google.com/\n")
    key   = _ask("API key")
    model = _ask("Model", "gemini-2.5-flash")
    print("  Testing API key...")
    ok = _test_gemini(key, model)
    _ok("API key valid.") if ok else _warn("Could not verify key.")
    return {"api_key": key, "model": model}, ok


def _sheets() -> tuple[dict, bool]:
    _sep("Google Sheets")
    print("Enable Sheets API, create a service account, share your sheet with it.\n")
    kf = _ask("Path to service account JSON", "~/service-account.json")
    sid = _ask("Google Sheet ID")
    print("  Testing connection...")
    ok = _test_sheets(kf, sid)
    _ok("Sheets connected.") if ok else _warn("Could not verify (gspread may not be installed yet).")
    return {"key_file": kf, "sheet_id": sid}, ok


def _resume() -> dict[str, Any]:
    _sep("Resume")
    path = _ask("Path to resume PDF", "~/resume.pdf")
    if os.path.isfile(os.path.expanduser(path)):
        _ok(f"Found resume at {path}")
    else:
        _warn(f"File not found: {path} — update path before running")
    return {
        "resume_path":              path,
        "auto_upload_resume":       _ask_bool("Auto-upload resume when applying?"),
        "cover_letter_auto_generate": _ask_bool("Auto-generate cover letter?"),
    }


def _platforms() -> dict[str, Any]:
    _sep("Platform Credentials")
    print("Press Enter to skip any platform you don't use.\n")
    out: dict[str, Any] = {}
    for key, label in [("internshala","Internshala"),("linkedin","LinkedIn"),("wellfound","Wellfound")]:
        email = _ask(f"{label} email (Enter to skip)", "")
        out[key] = {"email": email, "password": _ask(f"{label} password") if email else ""}
    return out


def _settings() -> dict[str, Any]:
    _sep("Settings")
    return {
        "dry_run":                   _ask_bool("Dry-run by default (fill but don't submit)?"),
        "approval_timeout_minutes":  int(_ask("Telegram approval timeout (minutes)", "30")),
        "playwright_headless":       _ask_bool("Run browser headless (background)?"),
        "max_draft_edits":           int(_ask("Max AI re-draft rounds", "5")),
        "draft_tone":                _ask("Draft tone (professional/casual/startup-friendly)", "professional"),
        "draft_length":              _ask("Draft length (short/medium/long)", "medium"),
    }


# ── main entry point ──────────────────────────────────────────────────────────

def run_setup_wizard() -> None:
    """Run the interactive setup wizard and save config."""
    print("\n" + "═" * 60)
    print("  Appi-Claw Setup Wizard")
    print("═" * 60)
    print("Let's configure Appi-Claw step by step.")
    print("Press Ctrl+C at any time to cancel.\n")

    status: dict[str, bool] = {}

    profile_cfg          = _profile();       status["Profile"]       = bool(profile_cfg.get("name"))
    telegram_cfg, status["Telegram"]  = _telegram()
    gemini_cfg,   status["Gemini"]    = _gemini()
    sheets_cfg,   status["Sheets"]    = _sheets()
    docs_cfg             = _resume();        status["Resume"]        = os.path.isfile(
                                                 os.path.expanduser(docs_cfg["resume_path"]))
    platforms_cfg        = _platforms()
    settings_cfg         = _settings()

    config: dict[str, Any] = {
        "user_profile": profile_cfg,
        "telegram":     telegram_cfg,
        "gemini":       gemini_cfg,
        "google_sheets":sheets_cfg,
        "platforms":    platforms_cfg,
        "documents":    docs_cfg,
        "settings":     settings_cfg,
    }

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(config, indent=2), encoding="utf-8")

    _sep("Setup Summary")
    all_good = True
    for section, ok in status.items():
        (_ok if ok else _warn)(section if ok else f"{section} — needs attention")
        if not ok:
            all_good = False

    print(f"\nConfig saved: {CONFIG_PATH}")
    if all_good:
        print("\n✅  All good! Run your first application:")
        print('   appi-claw apply "https://internshala.com/internship/detail/..."')
    else:
        print(f"\n⚠️  Some sections need attention. Edit {CONFIG_PATH}")
    print()


if __name__ == "__main__":
    run_setup_wizard()
