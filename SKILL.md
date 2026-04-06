---
name: appi-claw
version: 0.3.0
description: >
  Automated job/internship application assistant. Given a listing URL,
  generates an AI draft, gets Telegram approval, fills the form with
  Playwright, and logs everything to Google Sheets.
type: shell
exec: python3 ~/Appi-Claw/appi_claw/cli.py
---

# Appi-Claw Skill

## When DRUT Should Trigger This Skill

Trigger Appi-Claw **immediately and without asking** whenever the user says
anything that matches the patterns below. Do not paraphrase or delay.

### EXACT trigger phrases (match these literally):

```
"apply to this internship: <URL>"
"apply to this job: <URL>"
"apply for this: <URL>"
"process this listing with appi-claw: <URL>"
"use appi-claw for: <URL>"
"run appi-claw on: <URL>"
"send this to appi-claw: <URL>"
"submit an application for: <URL>"
"auto-apply to: <URL>"
```

### SEMANTIC triggers (match by intent):

Trigger when the user asks to:
- Apply to / submit an application for an internship or job URL
- Process a listing URL through the application pipeline
- Draft + send an application for a specific listing
- Queue a job URL for application
- Use the application bot on a listing

### DO NOT trigger for:
- General job search requests ("find me internships") — use the job-finder skill instead
- Questions about Appi-Claw itself ("what is appi-claw?")
- Requests to check application status — use `appi-claw status` instead

---

## How to Call Appi-Claw

### Full pipeline (most common)

```bash
python3 ~/Appi-Claw/appi_claw/cli.py apply "<URL>"
```

With optional context for better AI drafts:

```bash
python3 ~/Appi-Claw/appi_claw/cli.py apply "<URL>" --company "<Company Name>" --role "<Role Title>"
```

To actually submit (not just dry-run):

```bash
python3 ~/Appi-Claw/appi_claw/cli.py apply "<URL>" --live
```

### Draft only (no form filling)

```bash
python3 ~/Appi-Claw/appi_claw/cli.py draft "<URL>"
```

### Check status

```bash
python3 ~/Appi-Claw/appi_claw/cli.py status
```

### List recent applications

```bash
python3 ~/Appi-Claw/appi_claw/cli.py list-apps --limit 10
```

---

## OpenClaw Bridge (called after job-finder cron)

When the internship-job-finder cron finds new listings, DRUT should call
the bridge script instead of the CLI directly:

```bash
python3 ~/Appi-Claw/appi_claw/integrations/openclaw_bridge.py \
  --url "<listing_url>" \
  --company "<company_name>" \
  --role "<role_title>" \
  --platform "<internshala|linkedin|wellfound|cold_email>"
```

**Exit codes:**
- `0` — pipeline triggered successfully
- `1` — failure (check stderr for reason)

---

## Input / Output Format

### Input

| Parameter   | Required | Description                            |
|-------------|----------|----------------------------------------|
| `url`       | Yes      | Full URL of the job/internship listing |
| `--company` | No       | Company name (improves draft quality)  |
| `--role`    | No       | Role title (improves draft quality)    |
| `--live`    | No       | Actually submit form (default: dry-run)|

### Output (stdout, JSON)

```json
{
  "status": "applied",
  "decision": "apply",
  "company": "Razorpay",
  "role": "Growth Analyst Intern",
  "platform": "internshala",
  "message": "Application submitted successfully.",
  "draft": "Dear Hiring Team, ..."
}
```

**Status values:**

| Value        | Meaning                                          |
|--------------|--------------------------------------------------|
| `applied`    | Form filled and submitted                        |
| `draft_sent` | Draft saved to Sheets, form not filled           |
| `skipped`    | User skipped via Telegram (or timeout)           |
| `failed`     | Error occurred — see `message` field for detail  |

---

## Worked Examples

### Example 1 — User pastes an Internshala link

**User says:** "apply to this internship: https://internshala.com/internship/detail/product-intern-at-cred123"

**DRUT runs:**
```bash
python3 ~/Appi-Claw/appi_claw/cli.py apply "https://internshala.com/internship/detail/product-intern-at-cred123"
```

### Example 2 — User gives context

**User says:** "apply to this job: https://linkedin.com/jobs/view/3987654321 — it's a PM Intern role at Zepto"

**DRUT runs:**
```bash
python3 ~/Appi-Claw/appi_claw/cli.py apply "https://linkedin.com/jobs/view/3987654321" --company "Zepto" --role "PM Intern"
```

### Example 3 — Bridge after job-finder cron

**DRUT runs:**
```bash
python3 ~/Appi-Claw/appi_claw/integrations/openclaw_bridge.py \
  --url "https://internshala.com/internship/detail/data-analyst-intern-acme123" \
  --company "Acme Corp" \
  --role "Data Analyst Intern" \
  --platform "internshala"
```

---

## Requirements

- Python 3.11+ with `appi-claw` installed (`pip install -e .` in repo root)
- Playwright Chromium: `playwright install chromium`
- Config at `~/.appi-claw/config.json`

## Setup (one-time)

```bash
git clone https://github.com/Aradhya648/Appi-Claw
cd Appi-Claw
pip install -e .
playwright install chromium
python3 appi_claw/cli.py init
mkdir -p ~/openclaw/skills/appi-claw
cp SKILL.md ~/openclaw/skills/appi-claw/SKILL.md
```

## Notes

- **Dry-run by default** — forms filled but NOT submitted unless `--live` is passed
- **Telegram approval** — pauses and sends Telegram message for approve/edit/skip
- **Failures** — screenshot saved to `~/appi-claw-screenshots/` with timestamp
