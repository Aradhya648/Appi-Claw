# Appi-Claw

Automated job application assistant for Indian students and professionals.

Appi-Claw takes a listing URL, generates a tailored application draft using Gemini AI, sends it to you on Telegram for approval, fills the form with Playwright, and logs everything to Google Sheets — all from one command.

```
appi-claw apply "https://internshala.com/internship/detail/..."
```

---

## Features

- **AI-generated drafts** — Platform-aware cover letters and application notes via Gemini 2.5 Flash
- **Telegram approval flow** — Review the draft and choose Apply / Draft Only / Skip before anything is submitted
- **Playwright form filling** — Headless browser automation for Internshala and LinkedIn Easy Apply
- **Google Sheets logging** — Every action logged with company, role, status, draft, and follow-up date
- **OpenClaw / DRUT integration** — Expose tools that your AI agent can call directly
- **Dry-run by default** — Forms are filled but never submitted unless you pass `--live`

---

## Supported Platforms

| Platform | Status |
|---|---|
| Internshala | Full (login, parse, fill, submit) |
| LinkedIn Easy Apply | Full (login, parse, multi-step modal) |
| Wellfound | Adapter coming soon |
| Cold email | Draft generation supported |
| Twitter/LinkedIn DM | Draft generation supported |

---

## Quick Start

### 1. Install

```bash
git clone https://github.com/Aradhya648/Appi-Claw
cd Appi-Claw
pip install -e .
playwright install chromium
```

### 2. Configure

```bash
appi-claw init
# Opens ~/.appi-claw/config.json — fill in your credentials
```

Or copy manually:

```bash
cp config.example.json ~/.appi-claw/config.json
```

Edit `~/.appi-claw/config.json`:

```json
{
  "gemini": {
    "api_key": "YOUR_GEMINI_API_KEY",
    "model": "gemini-2.5-flash"
  },
  "telegram": {
    "bot_token": "YOUR_BOT_TOKEN",
    "user_id": YOUR_TELEGRAM_USER_ID
  },
  "google_sheets": {
    "key_file": "~/path/to/service-account.json",
    "sheet_id": "YOUR_SHEET_ID"
  },
  "platforms": {
    "internshala": { "email": "you@email.com", "password": "..." },
    "linkedin":    { "email": "you@email.com", "password": "..." }
  },
  "settings": {
    "dry_run": true,
    "approval_timeout_minutes": 30,
    "playwright_headless": true
  }
}
```

### 3. Run

```bash
# Process a listing — full pipeline (dry-run by default)
appi-claw apply "https://internshala.com/internship/detail/product-intern123"

# With known company/role for better drafts
appi-claw apply "https://internshala.com/..." --company "Razorpay" --role "Growth Analyst"

# Actually submit (remove dry-run)
appi-claw apply "https://internshala.com/..." --live

# Just generate a draft
appi-claw draft "https://linkedin.com/jobs/view/123" --company "Zepto" --role "PM Intern"

# Check tracker summary
appi-claw status

# List recent applications
appi-claw list-apps --limit 5
```

---

## CLI Reference

| Command | Description |
|---|---|
| `appi-claw init` | Create `~/.appi-claw/config.json` from template |
| `appi-claw apply <url>` | Full pipeline: draft → approve → fill → log |
| `appi-claw draft <url>` | Generate draft only, no form filling |
| `appi-claw status` | Tracker summary (total + status breakdown) |
| `appi-claw list-apps` | Recent applications from Google Sheets |

### `apply` flags

| Flag | Default | Description |
|---|---|---|
| `--company` | — | Company name (improves draft quality) |
| `--role` | — | Role title (improves draft quality) |
| `--dry-run / --live` | `--dry-run` | Dry-run fills form but skips submit |
| `--skip-approval` | off | Skip Telegram prompt, go straight to apply |
| `--config` | `~/.appi-claw/config.json` | Custom config path |

---

## Telegram Approval Flow

When you run `appi-claw apply`, a Telegram message is sent to your bot with the listing summary and draft. You get three buttons:

- **Apply** — proceeds to fill and submit the form
- **Draft Only** — saves the draft to Sheets, no form filling
- **Skip** — logs as Skipped

If you don't respond within `approval_timeout_minutes` (default 30), it auto-skips.

---

## Google Sheets Tracker

Appi-Claw logs to a sheet with columns:

| COMPANY | ROLE | Platform | Applied On | Status | Link | Application drafts | Follow up dates | Notes |
|---|---|---|---|---|---|---|---|---|

Get the Sheets API service account key from Google Cloud Console:
1. Create a project → Enable Google Sheets API
2. Create a Service Account → Download JSON key
3. Share your sheet with the service account email

---

## OpenClaw / DRUT Integration

Register Appi-Claw as an OpenClaw plugin so your AI agent DRUT can call it:

```
Plugin manifest: openclaw.plugin.json
```

Tools exposed to DRUT:

```python
appi_claw_process({"url": "...", "company": "...", "role": "..."})
appi_claw_status()
appi_claw_list(limit=10)
```

---

## Adding a New Platform

1. Create `appi_claw/platforms/your_platform.py`
2. Subclass `PlatformAdapter` from `appi_claw/platforms/base.py`
3. Implement `login()`, `parse_listing()`, `fill_and_submit()`, `close()`
4. Register in `appi_claw/cli.py` and `appi_claw/openclaw/plugin.py`
5. Add platform draft hints in `appi_claw/draft_gen.py` → `PLATFORM_HINTS`

---

## Project Structure

```
appi_claw/
├── cli.py              # CLI entry point (appi-claw command)
├── config.py           # Config loader (~/.appi-claw/config.json)
├── draft_gen.py        # Gemini-powered draft generator
├── telegram_bot.py     # Telegram approval flow
├── sheets.py           # Google Sheets logging
├── platforms/
│   ├── base.py         # PlatformAdapter ABC, Listing, ApplicationResult
│   ├── internshala.py  # Internshala adapter
│   └── linkedin.py     # LinkedIn Easy Apply adapter
└── openclaw/
    └── plugin.py       # OpenClaw/DRUT plugin wrapper
config.example.json     # Config template
openclaw.plugin.json    # OpenClaw plugin manifest
pyproject.toml          # Package config (pip install -e .)
```

---

## Requirements

- Python 3.11+
- Gemini API key (free tier works)
- Telegram bot token + user ID
- Google Sheets service account JSON
- Platform credentials (Internshala, LinkedIn)

---

## License

MIT — see [LICENSE](LICENSE)
