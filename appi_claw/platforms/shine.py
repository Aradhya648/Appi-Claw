"""Shine.com platform adapter — login, parse listing, fill & submit."""

import asyncio
import os
import random
from pathlib import Path
from playwright.async_api import async_playwright, Page, Browser
from appi_claw.platforms.base import PlatformAdapter, Listing, ApplicationResult

COOKIES_PATH = Path.home() / ".appi-claw" / "shine_cookies.json"


class ShineAdapter(PlatformAdapter):
    """Automates shine.com job applications via Playwright."""

    name = "shine"

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

        # Use Xvfb display if available (WSL2 headless fix)
        if "DISPLAY" not in os.environ:
            os.environ["DISPLAY"] = ":99"

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

    async def _human_delay(self, min_s: float = 0.3, max_s: float = 1.5):
        """Random delay to appear human."""
        await asyncio.sleep(random.uniform(min_s, max_s))

    async def _save_cookies(self):
        """Persist session cookies to avoid re-login."""
        if self._page:
            try:
                import json
                cookies = await self._page.context.cookies()
                COOKIES_PATH.parent.mkdir(parents=True, exist_ok=True)
                COOKIES_PATH.write_text(json.dumps(cookies))
            except Exception:
                pass

    async def login(self, credentials: dict) -> None:
        """Log into shine.com."""
        email = credentials.get("email", "")
        password = credentials.get("password", "")
        if not email or not password:
            raise ValueError("Shine credentials (email/password) not set in config.")

        page = await self._ensure_browser()

        # Check if already logged in
        await page.goto("https://www.shine.com/myshine/dashboard/", wait_until="domcontentloaded")
        await self._human_delay(2, 4)
        if "login" not in page.url.lower():
            self._logged_in = True
            return

        # Navigate to login
        await page.goto("https://www.shine.com/myshine/login/", wait_until="domcontentloaded")
        await self._human_delay(1, 2)

        # Fill login form — try common selectors for shine.com
        try:
            email_input = page.locator('input[type="email"], input[name="email"], input[id="email"], input[placeholder*="email" i]').first
            await email_input.fill(email)
            await self._human_delay(0.3, 0.8)
        except Exception:
            pass

        try:
            pwd_input = page.locator('input[type="password"], input[name="password"], input[id="password"]').first
            await pwd_input.fill(password)
            await self._human_delay(0.3, 0.8)
        except Exception:
            pass

        try:
            submit_btn = page.locator('button[type="submit"], input[type="submit"], button:has-text("Login"), button:has-text("Sign In")').first
            await submit_btn.click()
        except Exception:
            pass

        await self._human_delay(3, 6)

        # Check for CAPTCHA
        if self._config:
            from appi_claw.situation_handler import detect_captcha, handle_captcha
            if await detect_captcha(page):
                result = await handle_captcha(page, page.url, self._config)
                if result == "skip":
                    raise RuntimeError("CAPTCHA not resolved — skipping.")

        if "login" not in page.url.lower():
            self._logged_in = True
            await self._save_cookies()
        else:
            raise RuntimeError(f"Shine login may have failed — ended up at {page.url}.")

    async def parse_listing(self, url: str) -> Listing:
        """Navigate to listing URL and extract details."""
        page = await self._ensure_browser()
        await page.goto(url, wait_until="domcontentloaded")
        await self._human_delay(2, 4)

        company = ""
        role = ""
        description = ""

        try:
            # Company name
            company_el = (
                page.locator(".job_cmp_name, .company-name, h2:has(a), [class*='company']").first
            )
            if await company_el.count() > 0:
                company = (await company_el.text_content() or "").strip()

            # Role
            role_el = page.locator("h1, .job_title, [class*='title']").first
            if await role_el.count() > 0:
                role = (await role_el.text_content() or "").strip()

            # Description
            desc_el = page.locator(".job_detail, .description, [class*='description']").first
            if await desc_el.count() > 0:
                description = (await desc_el.text_content() or "").strip()[:1000]
        except Exception:
            pass

        return Listing(
            url=url,
            company=company,
            role=role,
            platform="shine",
            description=description,
        )

    async def fill_and_submit(
        self, listing: Listing, draft: str, dry_run: bool = True
    ) -> ApplicationResult:
        """Click Apply, fill form fields, and optionally submit."""
        if not self._logged_in:
            return ApplicationResult(
                success=False,
                status="failed",
                message="Not logged in. Call login() first.",
                draft=draft,
            )

        page = await self._ensure_browser()

        # Navigate to listing
        await page.goto(listing.url, wait_until="domcontentloaded")
        await self._human_delay(2, 4)

        # Check for CAPTCHA after navigation
        if self._config:
            from appi_claw.situation_handler import check_page_for_situations
            situation = await check_page_for_situations(page, page.url, "listing page", self._config)
            if situation == "skip":
                return ApplicationResult(
                    success=False, status="failed",
                    message="Skipped due to CAPTCHA or video question.", draft=draft
                )

        # Click the Apply button
        apply_clicked = False
        try:
            apply_btn = page.locator(
                'button:has-text("Apply"), a:has-text("Apply"), [class*="apply-btn"], [class*="apply_btn"]'
            ).first
            if await apply_btn.count() > 0:
                await apply_btn.click()
                apply_clicked = True
                await self._human_delay(2, 4)
        except Exception:
            pass

        if not apply_clicked:
            # Try opening apply URL directly
            job_id = listing.url.split("/")[4] if len(listing.url.split("/")) > 4 else ""
            apply_url = f"https://www.shine.com/myshine/apply/{job_id}/"
            try:
                await page.goto(apply_url, wait_until="domcontentloaded")
                await self._human_delay(2, 3)
                apply_clicked = True
            except Exception:
                pass

        if not apply_clicked:
            return ApplicationResult(
                success=False,
                status="failed",
                message="Could not find or click Apply button.",
                draft=draft,
            )

        # --- Fill form fields ---
        try:
            # Name field
            name_input = page.locator(
                'input[name="name"], input[id="name"], input[placeholder*="name" i]'
            ).first
            if await name_input.count() > 0:
                await name_input.fill("")
                await self._human_delay(0.2, 0.5)
        except Exception:
            pass

        try:
            # Phone field
            phone_input = page.locator(
                'input[name="phone"], input[id="phone"], input[type="tel"]'
            ).first
            if await phone_input.count() > 0:
                await phone_input.fill("")
                await self._human_delay(0.2, 0.5)
        except Exception:
            pass

        # Cover letter / Why should you be hired
        try:
            cover_field = page.locator(
                'textarea[name="cover_letter"], textarea[id="cover_letter"], '
                'textarea[placeholder*="cover" i], textarea[name*="question"], '
                'textarea[name*="why"], input[name*="question"]'
            ).first
            if await cover_field.count() > 0:
                await cover_field.fill(draft)
                await self._human_delay(0.5, 1.5)
        except Exception:
            pass

        if dry_run:
            # Save screenshot for review
            screenshot_path = Path.home() / "appi-claw-dry-run.png"
            try:
                await page.screenshot(path=str(screenshot_path), full_page=True)
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
                'button[type="submit"], input[type="submit"], '
                'button:has-text("Submit"), button:has-text("Apply")'
            ).first
            if await submit_btn.count() > 0:
                await submit_btn.click()
                await self._human_delay(3, 5)
                return ApplicationResult(
                    success=True,
                    status="applied",
                    message="Application submitted successfully on shine.com.",
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
