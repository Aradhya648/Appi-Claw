"""Internshala platform adapter — login, parse listing, fill & submit."""

import asyncio
from playwright.async_api import async_playwright, Page, Browser
from appi_claw.platforms.base import PlatformAdapter, Listing, ApplicationResult


class InternshalaAdapter(PlatformAdapter):
    """Automates Internshala internship applications via Playwright."""

    name = "internshala"

    def __init__(self, headless: bool = True, config: dict | None = None):
        self._headless = headless
        self._config = config
        self._browser: Browser | None = None
        self._page: Page | None = None
        self._pw = None
        self._logged_in = False

    async def _ensure_browser(self) -> Page:
        """Launch browser if not already running."""
        if self._page and not self._page.is_closed():
            return self._page

        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(
            headless=self._headless,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
        )
        context = await self._browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            )
        )
        self._page = await context.new_page()
        return self._page

    async def login(self, credentials: dict) -> None:
        """Log into Internshala with email/password."""
        email = credentials.get("email", "")
        password = credentials.get("password", "")
        if not email or not password:
            raise ValueError("Internshala credentials (email/password) not set in config.")

        page = await self._ensure_browser()
        await page.goto("https://internshala.com/login", wait_until="domcontentloaded")
        await asyncio.sleep(2)

        # Fill login form
        await page.fill('input[id="email"]', email)
        await page.fill('input[id="password"]', password)
        await page.click('button[id="login_submit"]')

        # Wait for navigation after login
        try:
            await page.wait_for_url("**/student/dashboard**", timeout=15000)
            self._logged_in = True
        except Exception:
            # Check if we're on a different post-login page
            if "internshala.com" in page.url and "login" not in page.url:
                self._logged_in = True
            else:
                raise RuntimeError(
                    f"Login may have failed — ended up at {page.url}. "
                    "Check credentials or handle CAPTCHA manually."
                )

    async def parse_listing(self, url: str) -> Listing:
        """Navigate to listing URL and extract details."""
        page = await self._ensure_browser()
        await page.goto(url, wait_until="domcontentloaded")
        await asyncio.sleep(2)

        company = ""
        role = ""
        description = ""

        try:
            # Company name
            company_el = page.locator(".company-name, .company_name, .heading_4_5 a").first
            if await company_el.count() > 0:
                company = (await company_el.text_content() or "").strip()

            # Role/profile name
            role_el = page.locator(".profile, .heading_4_5, h1.heading_4_5").first
            if await role_el.count() > 0:
                role = (await role_el.text_content() or "").strip()

            # Description
            desc_el = page.locator(".internship_details .text-container, .about_company_text_container").first
            if await desc_el.count() > 0:
                description = (await desc_el.text_content() or "").strip()[:1000]
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
        """Click Apply, fill the cover letter / 'Why should you be hired', and submit."""
        if not self._logged_in:
            return ApplicationResult(
                success=False,
                status="failed",
                message="Not logged in. Call login() first.",
                draft=draft,
            )

        page = await self._ensure_browser()

        # Make sure we're on the listing page
        if page.url != listing.url:
            await page.goto(listing.url, wait_until="domcontentloaded")
            await asyncio.sleep(2)

        # Click the Apply / Continue button
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
                    success=False,
                    status="failed",
                    message="Could not find Apply/Continue button.",
                    draft=draft,
                )
        except Exception as e:
            return ApplicationResult(
                success=False,
                status="failed",
                message=f"Error clicking apply: {e}",
                draft=draft,
            )

        # Handle file uploads (resume, cover letter, transcript)
        try:
            from appi_claw.documents import scan_and_handle_uploads
            if self._config:
                await scan_and_handle_uploads(
                    page, draft,
                    listing.company or "", listing.role or "",
                    self._config,
                )
        except Exception:
            pass  # Non-critical

        # Fill textarea(s) — cover letter / why hire you
        try:
            textareas = page.locator(
                "textarea.textarea, textarea[name='cover_letter'], "
                "textarea[placeholder*='cover'], textarea[placeholder*='hire'], "
                "#cover_letter_textarea, .ql-editor, textarea"
            )
            count = await textareas.count()
            if count > 0:
                for i in range(count):
                    ta = textareas.nth(i)
                    if await ta.is_visible():
                        await ta.fill(draft)
                        break
        except Exception as e:
            return ApplicationResult(
                success=False,
                status="failed",
                message=f"Error filling form: {e}",
                draft=draft,
            )

        if dry_run:
            # Take a screenshot for verification
            screenshot_path = f"dry_run_{listing.company or 'unknown'}.png"
            try:
                await page.screenshot(path=screenshot_path)
            except Exception:
                pass
            return ApplicationResult(
                success=True,
                status="draft_sent",
                message=f"Dry run — form filled but NOT submitted. Screenshot: {screenshot_path}",
                draft=draft,
            )

        # Actually submit
        try:
            submit_btn = page.locator(
                "#submit, button[type='submit'], "
                "button:has-text('Submit'), input[type='submit']"
            ).first
            if await submit_btn.count() > 0:
                await submit_btn.click()
                await asyncio.sleep(3)
                return ApplicationResult(
                    success=True,
                    status="applied",
                    message="Application submitted successfully.",
                    draft=draft,
                )
            else:
                return ApplicationResult(
                    success=False,
                    status="failed",
                    message="Could not find Submit button.",
                    draft=draft,
                )
        except Exception as e:
            return ApplicationResult(
                success=False,
                status="failed",
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
