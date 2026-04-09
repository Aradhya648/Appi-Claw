"""Internshala platform adapter — login, parse listing, fill & submit.

Login strategy:
  1. First try: open browser visibly so user can solve CAPTCHA if needed.
  2. Save session cookies to ~/.appi-claw/internshala_session.json
  3. On future runs: restore cookies and skip login entirely.
"""

import asyncio
import json
import os
from pathlib import Path
from playwright.async_api import async_playwright, Page, Browser
from appi_claw.platforms.base import PlatformAdapter, Listing, ApplicationResult
from appi_claw.logger import get_logger

log = get_logger(__name__)

SESSION_FILE = Path.home() / ".appi-claw" / "internshala_session.json"


class InternshalaAdapter(PlatformAdapter):
    """Automates Internshala internship applications via Playwright."""

    name = "internshala"

    def __init__(self, headless: bool = True, config: dict | None = None):
        self._headless = headless
        self._config = config or {}
        self._browser: Browser | None = None
        self._page: Page | None = None
        self._context = None
        self._pw = None
        self._logged_in = False

    async def _ensure_browser(self, headless: bool | None = None) -> Page:
        """Launch browser if not already running."""
        if self._page and not self._page.is_closed():
            return self._page

        # Use Xvfb display if available (WSL2 headless fix)
        if "DISPLAY" not in os.environ:
            os.environ["DISPLAY"] = ":99"
        use_headless = headless if headless is not None else self._headless

        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(
            headless=use_headless,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
            ],
        )
        self._context = await self._browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
        )

        # Restore saved cookies if they exist
        if SESSION_FILE.exists():
            try:
                cookies = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
                await self._context.add_cookies(cookies)
                log.info("Restored Internshala session from %s", SESSION_FILE)
            except Exception as e:
                log.debug("Could not restore session: %s", e)

        self._page = await self._context.new_page()

        # Hide automation markers
        await self._page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        """)

        return self._page

    async def _save_session(self) -> None:
        """Save cookies to disk for future runs."""
        try:
            if self._context:
                cookies = await self._context.cookies()
                SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
                SESSION_FILE.write_text(
                    json.dumps(cookies, indent=2), encoding="utf-8"
                )
                log.info("Saved Internshala session to %s", SESSION_FILE)
        except Exception as e:
            log.debug("Could not save session: %s", e)

    async def _is_logged_in(self, page: Page) -> bool:
        """Check if current session is already authenticated."""
        try:
            await page.goto(
                "https://internshala.com/student/dashboard",
                wait_until="domcontentloaded",
                timeout=15000,
            )
            await asyncio.sleep(2)
            return "dashboard" in page.url and "login" not in page.url
        except Exception:
            return False

    async def login(self, credentials: dict) -> None:
        """Log into Internshala, using saved session if available."""
        email    = credentials.get("email", "")
        password = credentials.get("password", "")
        if not email or not password:
            raise ValueError(
                "Internshala credentials (email/password) not set in config."
            )

        # Always open browser visibly for login so user can handle CAPTCHA
        page = await self._ensure_browser(headless=False)

        # Try saved session first
        if SESSION_FILE.exists():
            log.info("Trying saved session cookies...")
            if await self._is_logged_in(page):
                self._logged_in = True
                log.info("Logged in via saved session!")
                return
            else:
                log.info("Saved session expired — doing fresh login")
                SESSION_FILE.unlink(missing_ok=True)

        # Fresh login
        log.info("Opening Internshala login page...")
        await page.goto(
            "https://internshala.com/login/user",
            wait_until="domcontentloaded",
        )
        await asyncio.sleep(3)

        # Fill credentials
        try:
            await page.fill('input[id="email"]', email)
            await asyncio.sleep(1)
            await page.fill('input[id="password"]', password)
            await asyncio.sleep(1)
            await page.click('button[id="login_submit"]')
        except Exception as e:
            raise RuntimeError(f"Could not fill login form: {e}")

        # Wait for result — up to 60 seconds so user can solve CAPTCHA
        log.info(
            "Waiting for login... (solve CAPTCHA in the browser window if it appears)"
        )
        print(
            "\n  ⚠️  A browser window has opened. "
            "If you see a CAPTCHA, solve it there.\n"
            "  Waiting up to 60 seconds for login to complete...\n"
        )

        for _ in range(60):
            await asyncio.sleep(1)
            current_url = page.url
            if "dashboard" in current_url or (
                "internshala.com" in current_url and "login" not in current_url
            ):
                self._logged_in = True
                await self._save_session()
                log.info("Login successful! Session saved.")
                print("  ✓  Logged in successfully!\n")
                return

        # Still on login page after 60s
        if "login" in page.url:
            raise RuntimeError(
                "Login timed out after 60 seconds. "
                "Please check your credentials and try again."
            )

        self._logged_in = True
        await self._save_session()

    async def parse_listing(self, url: str) -> Listing:
        """Navigate to listing URL and extract details."""
        page = await self._ensure_browser()
        await page.goto(url, wait_until="domcontentloaded")
        await asyncio.sleep(2)

        company = role = description = ""

        try:
            company_el = page.locator(
                ".company-name, .company_name, .heading_4_5 a"
            ).first
            if await company_el.count() > 0:
                company = (await company_el.text_content() or "").strip()

            role_el = page.locator(
                ".profile, .heading_4_5, h1.heading_4_5"
            ).first
            if await role_el.count() > 0:
                role = (await role_el.text_content() or "").strip()

            desc_el = page.locator(
                ".internship_details .text-container, "
                ".about_company_text_container"
            ).first
            if await desc_el.count() > 0:
                description = (
                    await desc_el.text_content() or ""
                ).strip()[:1000]
        except Exception:
            pass

        return Listing(
            url=url,
            company=company,
            role=role,
            platform="internshala",
            description=description,
        )

    async def fill_and_submit(
        self, listing: Listing, draft: str, dry_run: bool = True
    ) -> ApplicationResult:
        """Click Apply, fill the form, and optionally submit."""
        if not self._logged_in:
            return ApplicationResult(
                success=False,
                status="failed",
                message="Not logged in. Call login() first.",
                draft=draft,
            )

        page = await self._ensure_browser()

        # Navigate to listing
        if listing.url not in page.url:
            await page.goto(listing.url, wait_until="domcontentloaded")
            await asyncio.sleep(2)

        # Check for CAPTCHA
        if self._config:
            from appi_claw.situation_handler import check_page_for_situations
            situation = await check_page_for_situations(
                page, page.url, "listing page", self._config
            )
            if situation == "skip":
                return ApplicationResult(
                    success=False, status="failed",
                    message="Skipped — CAPTCHA or video question.",
                    draft=draft,
                )

        # Click Apply
        try:
            apply_btn = page.locator(
                "#continue_button, .btn.btn-primary.easy_apply, "
                "button:has-text('Apply now'), button:has-text('Continue')"
            ).first
            if await apply_btn.count() > 0:
                await apply_btn.click()
                await asyncio.sleep(2)
            else:
                return ApplicationResult(
                    success=False, status="failed",
                    message="Could not find Apply/Continue button.",
                    draft=draft,
                )
        except Exception as e:
            return ApplicationResult(
                success=False, status="failed",
                message=f"Error clicking Apply: {e}",
                draft=draft,
            )

        # Handle file uploads
        try:
            from appi_claw.documents import scan_and_handle_uploads
            await scan_and_handle_uploads(
                page, draft,
                listing.company or "", listing.role or "",
                self._config,
            )
        except Exception:
            pass

        # Fill form fields
        try:
            from appi_claw.form_handler import handle_all_fields
            user_profile = self._config.get("user_profile", {})
            await handle_all_fields(page, user_profile, self._config, draft)
        except Exception as e:
            # Fallback: fill first visible textarea
            try:
                textareas = page.locator("textarea:visible")
                if await textareas.count() > 0:
                    await textareas.first.fill(draft)
            except Exception:
                return ApplicationResult(
                    success=False, status="failed",
                    message=f"Error filling form: {e}",
                    draft=draft,
                )

        if dry_run:
            from appi_claw.logger import screenshot_path
            shot = screenshot_path("dry_run_internshala")
            try:
                await page.screenshot(path=str(shot))
                msg = f"Dry run complete — form filled but NOT submitted. Screenshot: {shot}"
            except Exception:
                msg = "Dry run complete — form filled but NOT submitted."
            return ApplicationResult(
                success=True, status="draft_sent",
                message=msg, draft=draft,
            )

        # Submit
        try:
            submit_btn = page.locator(
                "#submit, button[type='submit'], "
                "button:has-text('Submit'), input[type='submit']"
            ).first
            if await submit_btn.count() > 0:
                await submit_btn.click()
                await asyncio.sleep(3)
                return ApplicationResult(
                    success=True, status="applied",
                    message="Application submitted successfully!",
                    draft=draft,
                )
            return ApplicationResult(
                success=False, status="failed",
                message="Could not find Submit button.",
                draft=draft,
            )
        except Exception as e:
            return ApplicationResult(
                success=False, status="failed",
                message=f"Error submitting: {e}",
                draft=draft,
            )

    async def close(self) -> None:
        """Close browser and clean up."""
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._pw:
            await self._pw.stop()
            self._pw = None
        self._page = None
        self._logged_in = False
