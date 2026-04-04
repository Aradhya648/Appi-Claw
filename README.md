# Appi-Claw

Automated job application assistant. Parses listings, generates tailored application drafts via Claude, gets your approval on Telegram, fills forms with Playwright, and logs everything to Google Sheets.

## Supported Platforms

1. Internshala
2. LinkedIn Easy Apply
3. Wellfound
4. Cold email
5. Twitter/LinkedIn DM

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt
playwright install chromium

# 2. Set up config
mkdir -p ~/.appi-claw
cp config.example.json ~/.appi-claw/config.json
# Edit ~/.appi-claw/config.json with your credentials

# 3. Run CLI
python cli.py apply "https://internshala.com/..." --dry-run
python cli.py status
python cli.py list-apps
```

## Project Structure

```
appi_claw/
├── config.py              # Config loader
├── draft_gen.py           # Claude-powered draft generator
├── telegram_bot.py        # Telegram approval flow
├── sheets.py              # Google Sheets logging
├── platforms/
│   ├── base.py            # Base adapter class
│   └── (adapters per platform)
└── openclaw/
    └── plugin.py          # OpenClaw/DRUT integration
```

## OpenClaw Plugin

Appi-Claw registers as an OpenClaw plugin. DRUT can call:
- `appi_claw_process(listing)` — full pipeline
- `appi_claw_status()` — queue status
- `appi_claw_list()` — list applications

## License

MIT
