# Contributing to Appi-Claw

Thanks for your interest! Appi-Claw is built for Indian job-seekers and welcomes contributions.

## Ways to Contribute

- **New platform adapters** — Wellfound, Naukri, Internshala referrals, etc.
- **Bug fixes** — especially around form selectors (they break when sites update)
- **Draft prompt improvements** — better system prompts for different roles/industries
- **Anti-bot improvements** — better stealth for Playwright sessions

## Adding a Platform Adapter

1. Create `appi_claw/platforms/<platform_name>.py`
2. Subclass `PlatformAdapter` from `appi_claw/platforms/base.py`:
   ```python
   from appi_claw.platforms.base import PlatformAdapter, Listing, ApplicationResult

   class YourPlatformAdapter(PlatformAdapter):
       name = "your_platform"

       async def login(self, credentials: dict) -> None: ...
       async def parse_listing(self, url: str) -> Listing: ...
       async def fill_and_submit(self, listing, draft, dry_run=True) -> ApplicationResult: ...
       async def close(self) -> None: ...
   ```
3. Register in `appi_claw/cli.py` (`_run_adapter`) and `appi_claw/openclaw/plugin.py`
4. Add platform-specific draft hints in `appi_claw/draft_gen.py` → `PLATFORM_HINTS`
5. Add credentials slot in `config.example.json`

## Development Setup

```bash
git clone https://github.com/Aradhya648/Appi-Claw
cd Appi-Claw
pip install -e .
playwright install chromium
cp config.example.json ~/.appi-claw/config.json
# Fill in credentials
```

## Guidelines

- Always default `dry_run=True` — never submit forms without an explicit flag
- Never hardcode credentials — always load from config
- Keep platform adapters independent — no shared state between them
- Add `--no-sandbox` to all Playwright launches (required for WSL2/CI)
- Test with `--dry-run` and verify the screenshot before testing live
- English only in code and comments

## Pull Requests

- One platform or feature per PR
- Include a brief description of what you tested
- Screenshots of dry-run output are helpful for form-filling PRs
