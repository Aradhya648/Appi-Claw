---
name: appi-claw
version: "0.2.0"
description: Automated job application assistant — generates AI drafts, gets Telegram approval, fills forms, logs to Google Sheets.
type: shell
---

# Appi-Claw Skill

Processes job listing URLs through the full application pipeline:
draft generation → Telegram approval → Playwright form filling → Sheets logging.

## Requirements

- Python 3.11+ with `appi-claw` installed (`pip install -e .` in repo root)
- Playwright Chromium: `playwright install chromium`
- Config at `~/.appi-claw/config.json` (see `config.example.json`)

## Commands

### process — Full application pipeline

```bash
appi-claw apply "<url>" [--company "<company>"] [--role "<role>"] [--live]
```

**Arguments:**
- `<url>` — Job or internship listing URL (required)
- `--company "<name>"` — Company name (optional, improves draft quality)
- `--role "<title>"` — Role title (optional, improves draft quality)
- `--live` — Actually submit the form (default is dry-run, form filled but not submitted)

**Output (stdout, JSON):**
```json
{
  "status": "applied",
  "decision": "apply",
  "company": "Razorpay",
  "role": "Growth Analyst Intern",
  "platform": "internshala",
  "message": "Application submitted successfully.",
  "draft": "Dear Hiring Team..."
}
```

**Status values:** `applied` | `draft_sent` | `skipped` | `failed`

**Example invocations:**
```bash
appi-claw apply "https://internshala.com/internship/detail/growth-analyst-internship-at-razorpay123"

appi-claw apply "https://www.linkedin.com/jobs/view/3987654321" --company "Zepto" --role "PM Intern" --live

appi-claw apply "https://internshala.com/internship/detail/abc123" --company "Cred" --role "Product Intern"
```

---

### draft — Generate draft only (no form filling)

```bash
appi-claw draft "<url>" [--company "<company>"] [--role "<role>"]
```

**Output (stdout, JSON):**
```json
{
  "status": "draft_only",
  "company": "Cred",
  "role": "Product Intern",
  "draft": "Dear Hiring Team..."
}
```

---

### status — Tracker summary

```bash
appi-claw status
```

**Output (stdout, JSON):**
```json
{
  "total": 42,
  "breakdown": {
    "Applied": 18,
    "Draft Sent": 7,
    "Skipped": 12,
    "Failed": 5
  }
}
```

---

### list — Recent applications

```bash
appi-claw list-apps [--limit <n>]
```

**Arguments:**
- `--limit <n>` — Number of entries to return (default: 10)

**Output (stdout, JSON):**
```json
[
  {
    "company": "Razorpay",
    "role": "Growth Analyst Intern",
    "platform": "internshala",
    "status": "Applied",
    "url": "https://internshala.com/...",
    "applied_on": "2026-04-04",
    "follow_up": "2026-04-11"
  }
]
```

---

## Setup for OpenClaw

```bash
# 1. Clone and install
git clone https://github.com/Aradhya648/Appi-Claw
cd Appi-Claw
pip install -e .
playwright install chromium

# 2. Configure credentials
cp config.example.json ~/.appi-claw/config.json
# Edit ~/.appi-claw/config.json with your API keys and credentials

# 3. Register skill with OpenClaw
mkdir -p ~/openclaw/skills/appi-claw
cp SKILL.md ~/openclaw/skills/appi-claw/SKILL.md
```

## Notes

- **Dry-run by default** — forms are filled but not submitted unless `--live` is passed
- **Telegram approval** — the `apply` command pauses and sends you a Telegram message to approve/edit/skip before submitting
- **CAPTCHA handling** — if a CAPTCHA appears, Appi-Claw pauses and notifies you via Telegram to solve it manually; reply "done" to resume (15-min timeout → auto-skip)
- **Video questions** — automatically skipped and reported via Telegram
- **Unexpected errors** — screenshot is saved to `~/appi-claw-error.png`, you're notified on Telegram; reply "retry" or "skip"
