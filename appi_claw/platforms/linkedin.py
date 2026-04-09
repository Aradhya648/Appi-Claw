"""LinkedIn Easy Apply platform adapter.

Handles login, listing parsing, and Easy Apply form filling via Playwright.
LinkedIn is aggressive with bot detection, so this adapter includes:
- Realistic delays between actions
- Human-like mouse movements
- Session cookie persistence to reduce re-logins
"""

import asyncio
import json
import random
from pathlib import Path
from playwright.async_api import async_playwright, Page, Browser
from appi_claw.platforms.base import PlatformAdapter, Listing, ApplicationResult

COOKIES_PATH = Path.home() / ".appi-claw" / "linkedin_cookies.json"


class LinkedInAdapter(PlatformAdapter):
    """Automates LinkedIn Easy Apply via Playwright."""

    name = "linkedin"

    def __init__(self, headless: bool = True, config: dict | None = None):
        self._headless = headless
        self._config = config
        self._browser: Browser | None = None
        self._page: Page | None = None
        self._pw = None
        self._logged_in = False

    async def _ensure_browser(self) -> Page:
        if self._page and not self._page.is_closed():
            return self._page

        self._pw = await async_playwright().start()
        launch_args = ["--no-sandbox", "--disable-blink-features=AutomationControlled"]
        if self._headless:
            launch_args.append("--headless=new")
        self._browser = await self._pw.chromium.launch(
            headless=False,
            args=launch_args,
        )
        context = await self._browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
        )

        # Restore cookies if available
        if COOKIES_PATH.exists():
            try:
                cookies = json.loads(COOKIES_PATH.read_text())
                await context.add_cookies(cookies)
            except Exception:
                pass

        self._page = await context.new_page()
        return self._page

    async def _human_delay(self, min_s: float = 0.5, max_s: float = 2.0):
        """Random delay to appear human."""
        await asyncio.sleep(random.uniform(min_s, max_s))

    async def _save_cookies(self):
        """Persist session cookies to avoid re-login."""
        if self._page:
            try:
                cookies = await self._page.context.cookies()
                COOKIES_PATH.parent.mkdir(parents=True, exist_ok=True)
                COOKIES_PATH.write_text(json.dumps(cookies))
            except Exception:
                pass

    async def login(self, credentials: dict) -> None:
        """Log into LinkedIn."""
        email = credentials.get("email", "")
        password = credentials.get("password", "")
        if not email or not password:
            raise ValueError("LinkedIn credentials (email/password) not set in config.")

        page = await self._ensure_browser()

        # Check if already logged in via cookies
        await page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded")
        await self._human_delay(2, 4)

        if "/feed" in page.url:
            self._logged_in = True
            return

        # Navigate to login
        await page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded")
        await self._human_delay(1, 2)

        await page.fill('#username', email)
        await self._human_delay(0.3, 0.8)
        await page.fill('#password', password)
        await self._human_delay(0.5, 1.0)
        await page.click('button[type="submit"]')

        # Wait for redirect
        try:
            await page.wait_for_url("**/feed/**", timeout=20000)
            self._logged_in = True
            await self._save_cookies()
        except Exception:
            # Check for CAPTCHA first
            if self._config:
                from appi_claw.situation_handler import detect_captcha, handle_captcha
                if await detect_captcha(page):
                    result = await handle_captcha(page, page.url, self._config)
                    if result == "skip":
                        raise RuntimeError("CAPTCHA not resolved — skipping.")
                    if "/feed" in page.url:
                        self._logged_in = True
                        await self._save_cookies()
                        return

            # Could be a security challenge
            current = page.url
            if "checkpoint" in current or "challenge" in current:
                raise RuntimeError(
                    "LinkedIn security challenge detected. "
                    "Log in manually in a browser first, or try with headless=false."
                )
            elif "login" in current:
                raise RuntimeError(
                    f"LinkedIn login failed — still at {current}. Check credentials."
                )
            else:
                # Might be on a different valid page
                self._logged_in = True
                await self._save_cookies()

    async def parse_listing(self, url: str) -> Listing:
        """Navigate to a LinkedIn job listing and extract details."""
        page = await self._ensure_browser()
        await page.goto(url, wait_until="domcontentloaded")
        await self._human_delay(2, 4)

        company = ""
        role = ""
        description = ""

        try:
            # Job title
            title_el = page.locator("h1.t-24, h1.job-details-jobs-unified-top-card__job-title, h1").first
            if await title_el.count() > 0:
                role = (await title_el.text_content() or "").strip()

            # Company name
            company_el = page.locator(
                ".job-details-jobs-unified-top-card__company-name a, "
                ".jobs-unified-top-card__company-name a, "
                ".topcard__org-name-link"
            ).first
            if await company_el.count() > 0:
                company = (await company_el.text_content() or "").strip()

            # Description
            desc_el = page.locator(
                ".jobs-description__content, "
                ".job-details-jobs-unified-top-card__job-description, "
                "#job-details"
            ).first
            if await desc_el.count() > 0:
                description = (await desc_el.text_content() or "").strip()[:1000]
        except Exception:
            pass

        return Listing(
            url=url,
            company=company,
            role=role,
            platform="linkedin",
            description=description,
        )

    async def fill_and_submit(
        self, listing: Listing, draft: str, dry_run: bool = True
    ) -> ApplicationResult:
        """Handle LinkedIn Easy Apply flow."""
        if not self._logged_in:
            return ApplicationResult(
                success=False,
                status="failed",
                message="Not logged in. Call login() first.",
                draft=draft,
            )

        page = await self._ensure_browser()

        # Make sure we're on the listing page
        if listing.url not in page.url:
            await page.goto(listing.url, wait_until="domcontentloaded")
            await self._human_delay(2, 3)

        # Click Easy Apply button
        try:
            easy_apply_btn = page.locator(
                "button.jobs-apply-button, "
                "button:has-text('Easy Apply'), "
                "button:has-text('Apply')"
            ).first
            if await easy_apply_btn.count() == 0:
                return ApplicationResult(
                    success=False,
                    status="failed",
                    message="No Easy Apply button found. This job may require external application.",
                    draft=draft,
                )
            await easy_apply_btn.click()
            await self._human_delay(1, 2)
        except Exception as e:
            return ApplicationResult(
                success=False,
                status="failed",
                message=f"Error clicking Easy Apply: {e}",
                draft=draft,
            )

        # Check for CAPTCHA / video after opening Easy Apply modal
        if self._config:
            from appi_claw.situation_handler import check_page_for_situations
            situation = await check_page_for_situations(page, listing.url, "Easy Apply modal", self._config)
            if situation == "skip":
                return ApplicationResult(success=False, status="failed",
                    message="Skipped due to CAPTCHA or video question.", draft=draft)

        # Handle multi-step Easy Apply modal
        try:
            await self._fill_easy_apply_steps(page, draft, dry_run, listing)
        except Exception as e:
            if self._config:
                from appi_claw.situation_handler import handle_unexpected_error
                action = await handle_unexpected_error(page, listing.url, "Easy Apply form", str(e), self._config)
                if action == "skip":
                    return ApplicationResult(success=False, status="failed",
                        message=f"Skipped after error: {e}", draft=draft)
            return ApplicationResult(
                success=False,
                status="failed",
                message=f"Error during Easy Apply form: {e}",
                draft=draft,
            )

        if dry_run:
            screenshot_path = f"dry_run_linkedin_{listing.company or 'unknown'}.png"
            try:
                await page.screenshot(path=screenshot_path)
            except Exception:
                pass
            # Close the modal without submitting
            try:
                dismiss = page.locator("button[aria-label='Dismiss'], button:has-text('Discard')").first
                if await dismiss.count() > 0:
                    await dismiss.click()
                    await self._human_delay(0.5, 1)
                    # Confirm discard
                    discard_confirm = page.locator("button:has-text('Discard')").first
                    if await discard_confirm.count() > 0:
                        await discard_confirm.click()
            except Exception:
                pass
            return ApplicationResult(
                success=True,
                status="draft_sent",
                message=f"Dry run — Easy Apply form filled but NOT submitted. Screenshot: {screenshot_path}",
                draft=draft,
            )

        # Submit
        try:
            submit_btn = page.locator(
                "button:has-text('Submit application'), "
                "button:has-text('Submit')"
            ).first
            if await submit_btn.count() > 0:
                await submit_btn.click()
                await self._human_delay(2, 3)
                return ApplicationResult(
                    success=True,
                    status="applied",
                    message="LinkedIn Easy Apply submitted.",
                    draft=draft,
                )
            else:
                return ApplicationResult(
                    success=False,
                    status="failed",
                    message="Could not find Submit button in Easy Apply flow.",
                    draft=draft,
                )
        except Exception as e:
            return ApplicationResult(
                success=False,
                status="failed",
                message=f"Error submitting: {e}",
                draft=draft,
            )

    async def _fill_easy_apply_steps(self, page: Page, draft: str, dry_run: bool, listing=None):
        """Navigate through Easy Apply modal steps, filling fields as needed."""
        max_steps = 8
        for step in range(max_steps):
            await self._human_delay(1, 2)

            # Handle file uploads (resume, cover letter, transcript)
            if self._config:
                try:
                    from appi_claw.documents import scan_and_handle_uploads
                    await scan_and_handle_uploads(
                        page, draft,
                        listing.company if listing else "",
                        listing.role if listing else "",
                        self._config,
                    )
                except Exception:
                    pass

            # Smart form field handling
            try:
                from appi_claw.form_handler import handle_all_fields
                user_profile = (self._config or {}).get("user_profile", {})
                await handle_all_fields(page, user_profile, self._config or {}, draft)
                await self._human_delay(0.5, 1)
            except Exception:
                pass

            # Handle dropdowns / select elements (not covered by handle_all_fields)
            selects = page.locator("select:visible")
            sel_count = await selects.count()
            for i in range(sel_count):
                sel = selects.nth(i)
                try:
                    options = sel.locator("option")
                    opt_count = await options.count()
                    if opt_count > 1:
                        val = await options.nth(1).get_attribute("value")
                        if val:
                            await sel.select_option(value=val)
                except Exception:
                    pass

            # Handle radio buttons — select first option in each group
            fieldsets = page.locator("fieldset:visible")
            fs_count = await fieldsets.count()
            for i in range(fs_count):
                fs = fieldsets.nth(i)
                radio = fs.locator("input[type='radio']").first
                if await radio.count() > 0 and not await radio.is_checked():
                    try:
                        await radio.check()
                    except Exception:
                        pass

            # Check if we're on the final review step
            submit_btn = page.locator("button:has-text('Submit application')").first
            if await submit_btn.count() > 0:
                return  # Ready to submit (caller handles)

            # Click Next / Review
            next_btn = page.locator(
                "button:has-text('Next'), "
                "button:has-text('Review'), "
                "button:has-text('Continue')"
            ).first
            if await next_btn.count() > 0:
                await next_btn.click()
                await self._human_delay(1, 2)
            else:
                # No more steps, might be single-page
                return

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
