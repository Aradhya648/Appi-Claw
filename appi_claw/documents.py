"""Document handling for Appi-Claw.

Handles:
- Resume upload from config path
- Cover letter PDF generation via Gemini + fpdf2
- Transcript/marksheet detection → Telegram notification to user
"""

import asyncio
import tempfile
from pathlib import Path

from fpdf import FPDF


def get_resume_path(config: dict) -> Path | None:
    """Return the resolved resume path if it exists, else None."""
    docs = config.get("documents", {})
    raw = docs.get("resume_path", "")
    if not raw:
        return None
    path = Path(raw).expanduser()
    return path if path.exists() else None


def generate_cover_letter_pdf(draft: str, listing_company: str, listing_role: str) -> Path:
    """Generate a cover letter PDF from a draft string.

    Returns path to a temp PDF file (caller should clean up).
    """
    pdf = FPDF()
    pdf.add_page()
    pdf.set_margins(left=20, top=20, right=20)
    pdf.set_auto_page_break(auto=True, margin=20)

    # Header
    pdf.set_font("Helvetica", style="B", size=14)
    pdf.cell(0, 10, "Cover Letter", ln=True, align="C")
    pdf.ln(2)

    pdf.set_font("Helvetica", size=10)
    if listing_company or listing_role:
        subtitle = f"{listing_role} at {listing_company}".strip(" at")
        pdf.cell(0, 8, subtitle, ln=True, align="C")
    pdf.ln(6)

    # Body — wrap long lines
    pdf.set_font("Helvetica", size=11)
    for paragraph in draft.split("\n"):
        paragraph = paragraph.strip()
        if paragraph:
            pdf.multi_cell(0, 7, paragraph)
            pdf.ln(3)
        else:
            pdf.ln(3)

    tmp = tempfile.NamedTemporaryFile(
        suffix=".pdf", prefix="appi_claw_cover_", delete=False
    )
    tmp.close()
    pdf.output(tmp.name)
    return Path(tmp.name)


async def handle_file_upload_field(
    page,
    field_locator,
    draft: str,
    listing_company: str,
    listing_role: str,
    config: dict,
    field_label: str = "",
) -> str:
    """Detect what kind of file upload is needed and handle it.

    Args:
        page: Playwright Page.
        field_locator: Playwright locator for the file input.
        draft: Current application draft (used for cover letter).
        listing_company: Company name.
        listing_role: Role title.
        config: Full app config.
        field_label: Label text of the upload field (used to detect type).

    Returns:
        Status string: "resume_uploaded", "cover_letter_uploaded",
        "transcript_notified", "skipped".
    """
    label_lower = field_label.lower()
    docs = config.get("documents", {})
    auto_upload = docs.get("auto_upload_resume", True)

    # Transcript / marksheet → notify user, don't auto-upload
    if any(w in label_lower for w in ("transcript", "marksheet", "mark sheet", "grade", "academic record")):
        from appi_claw.telegram_bot import notify
        await notify(
            f"Transcript/marksheet required for {listing_company} — {listing_role}.\n"
            "Please upload it manually and reply 'done' when finished.",
            config,
        )
        return "transcript_notified"

    # Cover letter as separate doc
    if any(w in label_lower for w in ("cover letter", "cover_letter", "covering letter")):
        cover_pdf = generate_cover_letter_pdf(draft, listing_company, listing_role)
        try:
            await field_locator.set_input_files(str(cover_pdf))
            return "cover_letter_uploaded"
        except Exception:
            return "skipped"
        finally:
            cover_pdf.unlink(missing_ok=True)

    # Resume / CV / default file upload
    if not auto_upload:
        return "skipped"

    resume_path = get_resume_path(config)
    if resume_path is None:
        from appi_claw.telegram_bot import notify
        await notify(
            f"Resume upload required for {listing_company} — {listing_role}, "
            "but no resume_path is set in config. Please upload manually.",
            config,
        )
        return "skipped"

    try:
        await field_locator.set_input_files(str(resume_path))
        return "resume_uploaded"
    except Exception:
        return "skipped"


async def scan_and_handle_uploads(
    page,
    draft: str,
    listing_company: str,
    listing_role: str,
    config: dict,
) -> list[str]:
    """Scan a page for file upload inputs and handle each one.

    Returns list of status strings for each upload field found.
    """
    results = []
    file_inputs = page.locator("input[type='file']:visible")
    count = await file_inputs.count()

    for i in range(count):
        inp = file_inputs.nth(i)

        # Try to get the label for this input
        field_label = ""
        try:
            input_id = await inp.get_attribute("id")
            aria_label = await inp.get_attribute("aria-label") or ""
            name_attr = await inp.get_attribute("name") or ""

            if input_id:
                label_el = page.locator(f"label[for='{input_id}']").first
                if await label_el.count() > 0:
                    field_label = (await label_el.text_content() or "").strip()

            if not field_label:
                field_label = aria_label or name_attr
        except Exception:
            pass

        status = await handle_file_upload_field(
            page, inp, draft, listing_company, listing_role, config, field_label
        )
        results.append(status)

    return results
