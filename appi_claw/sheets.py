"""Google Sheets tracker integration.

Logs every application action to the DRUT internship tracker.
Columns: COMPANY | ROLE | Platform | Applied On | Status | Link | Application drafts | Follow up dates | Notes
"""

from datetime import datetime, timedelta
from pathlib import Path

import gspread
from google.oauth2.service_account import Credentials

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def _get_worksheet(config: dict):
    """Authenticate and return the first worksheet."""
    sheets_config = config["google_sheets"]
    key_file = sheets_config["key_file"]
    sheet_id = sheets_config["sheet_id"]

    creds = Credentials.from_service_account_file(key_file, scopes=SCOPES)
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(sheet_id)
    return sh.sheet1


def log_application(
    config: dict,
    company: str = "",
    role: str = "",
    platform: str = "",
    status: str = "",
    url: str = "",
    draft: str = "",
    notes: str = "",
    follow_up_days: int = 7,
) -> None:
    """Append a row to the Google Sheets tracker.

    Args:
        config: Full app config (needs google_sheets section).
        company: Company name.
        role: Role / position title.
        platform: Platform name (internshala, linkedin, etc.).
        status: Applied / Draft Sent / Skipped / Failed.
        url: Listing URL.
        draft: Application draft text.
        notes: Any extra notes.
        follow_up_days: Days from now to set follow-up date (default 7).
    """
    ws = _get_worksheet(config)

    applied_on = datetime.now().strftime("%Y-%m-%d %H:%M")
    follow_up = (datetime.now() + timedelta(days=follow_up_days)).strftime("%Y-%m-%d")

    row = [
        company,
        role,
        platform,
        applied_on,
        status,
        url,
        draft[:2000] if draft else "",  # Truncate long drafts
        follow_up,
        notes,
    ]

    ws.append_row(row, value_input_option="USER_ENTERED")
