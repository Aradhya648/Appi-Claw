"""Config loader for Appi-Claw. Reads from ~/.appi-claw/config.json."""

import json
import os
from pathlib import Path

DEFAULT_CONFIG_PATH = Path.home() / ".appi-claw" / "config.json"


def load_config(path: str | None = None) -> dict:
    """Load config from the given path, or the default location."""
    config_path = Path(path) if path else DEFAULT_CONFIG_PATH

    if not config_path.exists():
        raise FileNotFoundError(
            f"Config not found at {config_path}. "
            f"Copy config.example.json to {DEFAULT_CONFIG_PATH} and fill in your credentials."
        )

    with open(config_path, "r") as f:
        config = json.load(f)

    _validate(config)
    _expand_paths(config)
    return config


def _validate(config: dict) -> None:
    """Check that required keys exist."""
    required_sections = ["user_profile", "telegram", "anthropic", "google_sheets", "settings"]
    for section in required_sections:
        if section not in config:
            raise ValueError(f"Missing required config section: '{section}'")

    if not config["telegram"].get("bot_token") or config["telegram"]["bot_token"] == "YOUR_TELEGRAM_BOT_TOKEN":
        raise ValueError("Set a real Telegram bot_token in config.")

    if not config["anthropic"].get("api_key") or config["anthropic"]["api_key"] == "YOUR_ANTHROPIC_API_KEY":
        raise ValueError("Set a real Anthropic api_key in config.")


def _expand_paths(config: dict) -> None:
    """Expand ~ in file paths."""
    sheets = config.get("google_sheets", {})
    if "key_file" in sheets:
        sheets["key_file"] = str(Path(sheets["key_file"]).expanduser())


def get_config(path: str | None = None) -> dict:
    """Convenience wrapper — loads and caches config."""
    if not hasattr(get_config, "_cache"):
        get_config._cache = load_config(path)
    return get_config._cache
