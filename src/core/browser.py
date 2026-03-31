"""
Browser Manager - Manages Playwright browser instances with anti-detection.
Handles:
- Persistent browser sessions (stay logged in)
- Stealth mode (avoid bot detection)
- Human-like behavior (random delays, mouse movements)
- Screenshot capture
- Page content extraction
"""

import asyncio
import random
import logging
from pathlib import Path
from typing import Optional

from playwright.async_api import (
    async_playwright,
    Browser,
    BrowserContext,
    Page,
    Playwright,
    TimeoutError as PlaywrightTimeout,
)

from src.core.config import config, PROJECT_ROOT

logger = logging.getLogger("core.browser")


class BrowserManager:
    """
    Manages browser lifecycle with anti-detection and human-like behavior.
    Uses persistent browser context to maintain login sessions.
    """

    def __init__(self):
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None

        # Config
        self._browser_type = config.get("browser", "type", default="chromium")
        self._headless = config.get("app", "headless_browser", default=True)
        self._user_data_dir = PROJECT_ROOT / config.get("browser", "user_data_dir", default="data/browser_profile")
        self._stealth = config.get("browser", "stealth_mode", default=True)
        self._random_delays = config.get("browser", "random_delays", default=True)
        self._min_delay = config.get("browser", "min_delay_ms", default=800) / 1000
        self._max_delay = config.get("browser", "max_delay_ms", default=3000) / 1000
        self._timeout = config.get("browser", "timeout_ms", default=30000)
        self._nav_timeout = config.get("browser", "navigation_timeout_ms", default=60000)
        self._viewport_w = config.get("browser", "viewport_width", default=1920)
        self._viewport_h = config.get("browser", "viewport_height", default=1080)
        self._screenshot_dir = PROJECT_ROOT / "logs" / "screenshots"
        self._screenshot_dir.mkdir(parents=True, exist_ok=True)
        self._max_screenshots = config.get("browser", "max_screenshots", default=200)
        self._geo_lat = config.get("browser", "geolocation_lat", default=18.5204)
        self._geo_lon = config.get("browser", "geolocation_lon", default=73.8567)

        # Proxy config
        self._proxy_enabled = config.get("browser", "proxy", "enabled", default=False)
        self._proxy_server = config.get("browser", "proxy", "server", default="")
        self._proxy_username = config.get("browser", "proxy", "username", default="")
        self._proxy_password = config.get("browser", "proxy", "password", default="")

        # Select a consistent user agent + platform pair at init
        self._user_agent, self._platform = self._get_consistent_identity()

    async def start(self):
        """Launch browser with anti-detection measures."""
        self._playwright = await async_playwright().start()

        # Ensure user data dir exists
        self._user_data_dir.mkdir(parents=True, exist_ok=True)

        browser_launcher = getattr(self._playwright, self._browser_type)

        # Build launch kwargs
        launch_kwargs = dict(
            user_data_dir=str(self._user_data_dir),
            headless=self._headless,
            viewport={"width": self._viewport_w, "height": self._viewport_h},
            locale="en-US",
            timezone_id="Asia/Kolkata",
            user_agent=self._user_agent,
            args=self._get_stealth_args() if self._stealth else [],
            ignore_default_args=["--enable-automation"] if self._stealth else [],
            java_script_enabled=True,
            accept_downloads=True,
            permissions=["geolocation"],
            geolocation={"latitude": self._geo_lat, "longitude": self._geo_lon},
        )

        # Add proxy if configured
        if self._proxy_enabled and self._proxy_server:
            proxy = {"server": self._proxy_server}
            if self._proxy_username:
                proxy["username"] = self._proxy_username
                proxy["password"] = self._proxy_password
            launch_kwargs["proxy"] = proxy
            logger.info(f"Using proxy: {self._proxy_server}")

        # Launch persistent context (keeps cookies/sessions)
        self._context = await browser_launcher.launch_persistent_context(**launch_kwargs)

        # Apply stealth scripts
        if self._stealth:
            await self._apply_stealth_scripts()

        # Import saved cookies (critical for CI/CD headless runs)
        from src.utils.cookies import import_cookies
        imported = await import_cookies(self._context)
        if imported:
            logger.info(f"Restored {imported} session cookies")

        self._page = self._context.pages[0] if self._context.pages else await self._context.new_page()
        self._page.set_default_timeout(self._timeout)
        self._page.set_default_navigation_timeout(self._nav_timeout)

        logger.info(f"Browser started: {self._browser_type}, headless={self._headless}")
        return self._page

    async def stop(self):
        """Gracefully close the browser - refresh cookies before exit."""
        if self._context:
            # Save refreshed cookies for next run
            try:
                from src.utils.cookies import refresh_cookies
                await refresh_cookies(self._context)
            except Exception as e:
                logger.debug(f"Cookie refresh on stop: {e}")
            try:
                await self._context.close()
            except Exception:
                pass
            self._context = None
        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception:
                pass
            self._playwright = None
        self._page = None
        logger.info("Browser stopped")

    def is_alive(self) -> bool:
        """Check if the browser is still functioning."""
        try:
            return (
                self._context is not None
                and self._page is not None
                and not self._page.is_closed()
            )
        except Exception:
            return False

    async def restart(self):
        """Restart the browser (for crash recovery between portals)."""
        logger.info("Restarting browser...")
        try:
            await self.stop()
        except Exception as e:
            logger.debug(f"Error during stop in restart: {e}")
        await asyncio.sleep(1)
        await self.start()
        logger.info("Browser restarted successfully")

    async def ensure_alive(self):
        """Ensure browser is alive; restart if crashed."""
        if not self.is_alive():
            logger.warning("Browser appears dead, restarting...")
            await self.restart()

    @property
    def page(self) -> Optional[Page]:
        return self._page

    @property
    def context(self) -> Optional[BrowserContext]:
        return self._context

    # ── Navigation ──────────────────────────────────────────────

    async def goto(self, url: str, wait_until: str = "domcontentloaded") -> bool:
        """Navigate to a URL with human-like delay."""
        try:
            await self._human_delay()
            await self._page.goto(url, wait_until=wait_until)
            await self._human_delay(short=True)
            logger.info(f"Navigated to: {url}")
            return True
        except PlaywrightTimeout:
            logger.warning(f"Navigation timeout: {url}")
            return False
        except Exception as e:
            logger.error(f"Navigation error: {url} - {e}")
            return False

    async def wait_for_page_load(self, timeout: int = None):
        """Wait for page to be fully loaded."""
        timeout = timeout or self._nav_timeout
        try:
            await self._page.wait_for_load_state("networkidle", timeout=timeout)
        except PlaywrightTimeout:
            logger.debug("Network idle timeout (continuing anyway)")

    # ── Interaction (Human-like) ────────────────────────────────

    async def click(self, selector: str, timeout: int = None) -> bool:
        """Click an element with human-like delay."""
        try:
            await self._human_delay()
            element = await self._page.wait_for_selector(selector, timeout=timeout or self._timeout)
            if element:
                # Scroll into view
                await element.scroll_into_view_if_needed()
                await self._human_delay(short=True)
                await element.click()
                logger.debug(f"Clicked: {selector}")
                return True
        except PlaywrightTimeout:
            logger.warning(f"Click timeout: {selector}")
        except Exception as e:
            logger.warning(f"Click failed: {selector} - {e}")
        return False

    async def type_text(self, selector: str, text: str, clear_first: bool = True) -> bool:
        """Type text with human-like keystroke delays."""
        try:
            await self._human_delay()
            element = await self._page.wait_for_selector(selector, timeout=self._timeout)
            if element:
                await element.scroll_into_view_if_needed()
                if clear_first:
                    await element.click(click_count=3)  # Select all
                    await self._page.keyboard.press("Backspace")
                    await asyncio.sleep(0.2)

                # Type character by character with random delays
                for char in text:
                    await element.type(char, delay=random.randint(30, 120))

                logger.debug(f"Typed into: {selector}")
                return True
        except PlaywrightTimeout:
            logger.warning(f"Type timeout: {selector}")
        except Exception as e:
            logger.warning(f"Type failed: {selector} - {e}")
        return False

    async def select_option(self, selector: str, value: str = None, label: str = None) -> bool:
        """Select an option from a dropdown."""
        try:
            await self._human_delay()
            if label:
                await self._page.select_option(selector, label=label)
            elif value:
                await self._page.select_option(selector, value=value)
            logger.debug(f"Selected option in: {selector}")
            return True
        except Exception as e:
            logger.warning(f"Select failed: {selector} - {e}")
            return False

    async def check_checkbox(self, selector: str, check: bool = True) -> bool:
        """Check or uncheck a checkbox."""
        try:
            await self._human_delay()
            if check:
                await self._page.check(selector)
            else:
                await self._page.uncheck(selector)
            return True
        except Exception as e:
            logger.warning(f"Checkbox failed: {selector} - {e}")
            return False

    async def upload_file(self, selector: str, file_path: str) -> bool:
        """Upload a file to a file input."""
        try:
            await self._page.set_input_files(selector, file_path)
            logger.debug(f"Uploaded file: {file_path}")
            return True
        except Exception as e:
            logger.warning(f"File upload failed: {selector} - {e}")
            return False

    async def press_key(self, key: str):
        """Press a keyboard key."""
        await self._page.keyboard.press(key)

    async def scroll_down(self, pixels: int = 500):
        """Scroll down the page."""
        await self._page.mouse.wheel(0, pixels)
        await self._human_delay(short=True)

    async def scroll_to_bottom(self):
        """Scroll to the bottom of the page."""
        await self._page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await self._human_delay()

    # ── Content Extraction ──────────────────────────────────────

    async def get_page_html(self, clean: bool = True) -> str:
        """Get page HTML content, optionally cleaned for AI analysis."""
        html = await self._page.content()
        if clean:
            html = self._clean_html_for_ai(html)
        return html

    async def get_visible_text(self) -> str:
        """Get all visible text on the page."""
        return await self._page.evaluate("""
            () => {
                return document.body.innerText;
            }
        """)

    async def get_form_fields(self) -> list[dict]:
        """Extract all form fields from the page using JavaScript."""
        return await self._page.evaluate("""
            () => {
                const fields = [];
                const inputs = document.querySelectorAll('input, select, textarea');
                inputs.forEach(el => {
                    const label = el.labels?.[0]?.textContent?.trim() || 
                                  el.getAttribute('aria-label') || 
                                  el.getAttribute('placeholder') ||
                                  el.getAttribute('name') || '';
                    const field = {
                        tag: el.tagName.toLowerCase(),
                        type: el.type || el.tagName.toLowerCase(),
                        id: el.id || '',
                        name: el.name || '',
                        label: label,
                        placeholder: el.placeholder || '',
                        required: el.required || false,
                        value: el.value || '',
                        visible: el.offsetParent !== null,
                        selector: el.id ? `#${el.id}` : 
                                  el.name ? `[name="${el.name}"]` : 
                                  `${el.tagName.toLowerCase()}[type="${el.type}"]`,
                        options: el.tagName === 'SELECT' ? 
                            Array.from(el.options).map(o => ({value: o.value, text: o.text})) : []
                    };
                    fields.push(field);
                });
                return fields;
            }
        """)

    async def get_element_text(self, selector: str) -> str:
        """Get text content of an element."""
        try:
            element = await self._page.query_selector(selector)
            if element:
                return await element.text_content() or ""
        except Exception:
            pass
        return ""

    async def element_exists(self, selector: str) -> bool:
        """Check if an element exists on the page."""
        element = await self._page.query_selector(selector)
        return element is not None

    async def get_current_url(self) -> str:
        """Get current page URL."""
        return self._page.url

    # ── Screenshots ─────────────────────────────────────────────

    async def take_screenshot(self, name: str = "screenshot", full_page: bool = False) -> str:
        """Take a screenshot and return the file path."""
        import datetime
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{name}_{timestamp}.png"
        filepath = self._screenshot_dir / filename
        await self._page.screenshot(path=str(filepath), full_page=full_page)
        logger.debug(f"Screenshot saved: {filepath}")

        # Cleanup old screenshots periodically (every 10th call)
        if not hasattr(self, '_screenshot_counter'):
            self._screenshot_counter = 0
        self._screenshot_counter += 1
        if self._screenshot_counter % 10 == 0:
            self._cleanup_screenshots()

        return str(filepath)

    def _cleanup_screenshots(self):
        """Remove old screenshots, keeping only the most recent ones."""
        try:
            screenshots = sorted(
                self._screenshot_dir.glob("*.png"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            for old in screenshots[self._max_screenshots:]:
                old.unlink(missing_ok=True)
        except Exception as e:
            logger.debug(f"Screenshot cleanup error: {e}")

    # ── Anti-Detection ──────────────────────────────────────────

    def _get_consistent_identity(self) -> tuple[str, str]:
        """Return a consistent (user_agent, platform) pair to avoid fingerprint mismatch."""
        identities = [
            (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                "MacIntel",
            ),
            (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                "Win32",
            ),
            (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.2 Safari/605.1.15",
                "MacIntel",
            ),
            (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                "Linux x86_64",
            ),
        ]
        import os
        # In CI (Linux), prefer a Linux or Windows UA to match reality
        if os.environ.get("CI"):
            identities = [i for i in identities if "Linux" in i[1] or "Win" in i[1]] or identities
        return random.choice(identities)

    def _get_realistic_user_agent(self) -> str:
        """Return the pre-selected user agent."""
        return self._user_agent

    def _get_stealth_args(self) -> list[str]:
        """Get browser args for stealth mode."""
        return [
            "--disable-blink-features=AutomationControlled",
            "--disable-features=IsolateOrigins,site-per-process",
            "--disable-infobars",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-background-timer-throttling",
            "--disable-backgrounding-occluded-windows",
            "--disable-renderer-backgrounding",
            f"--window-size={self._viewport_w},{self._viewport_h}",
        ]

    async def _apply_stealth_scripts(self):
        """Inject JavaScript to avoid bot detection."""
        await self._context.add_init_script("""
            // Override navigator.webdriver
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            
            // Override chrome detection
            window.chrome = { runtime: {} };
            
            // Override permissions
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) =>
                parameters.name === 'notifications'
                    ? Promise.resolve({ state: Notification.permission })
                    : originalQuery(parameters);
            
            // Override plugins
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });
            
            // Override languages
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en', 'hi']
            });
            
            // Override platform (matched to user agent)
            Object.defineProperty(navigator, 'platform', {
                get: () => '""" + self._platform + """'
            });
            
            // Override hardware concurrency  
            Object.defineProperty(navigator, 'hardwareConcurrency', {
                get: () => 8
            });
        """)

    async def _human_delay(self, short: bool = False):
        """Add a human-like random delay."""
        if self._random_delays:
            if short:
                delay = random.uniform(0.2, 0.8)
            else:
                delay = random.uniform(self._min_delay, self._max_delay)
            await asyncio.sleep(delay)

    def _clean_html_for_ai(self, html: str) -> str:
        """Clean HTML to reduce token usage for AI analysis."""
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")

        # Remove script, style, svg, and other non-essential tags
        for tag in soup.find_all(["script", "style", "svg", "noscript", "iframe", "link", "meta"]):
            tag.decompose()

        # Remove hidden elements
        for tag in soup.find_all(attrs={"style": lambda s: s and "display:none" in s.replace(" ", "")}):
            tag.decompose()
        for tag in soup.find_all(attrs={"style": lambda s: s and "visibility:hidden" in s.replace(" ", "")}):
            tag.decompose()

        # Remove data attributes to save tokens
        for tag in soup.find_all(True):
            attrs_to_remove = [attr for attr in tag.attrs if attr.startswith("data-") and attr not in ("data-testid",)]
            for attr in attrs_to_remove:
                del tag[attr]

        result = str(soup)
        # Collapse whitespace
        import re
        result = re.sub(r'\s+', ' ', result)
        return result[:20000]  # Cap at 20k chars for AI context

    # ── Tab Management ──────────────────────────────────────────

    async def new_tab(self, url: str = None) -> Page:
        """Open a new tab."""
        page = await self._context.new_page()
        if url:
            await page.goto(url)
        return page

    async def switch_to_page(self, page: Page):
        """Switch the active page reference."""
        self._page = page

    async def close_extra_tabs(self):
        """Close all tabs except the first one."""
        pages = self._context.pages
        for page in pages[1:]:
            await page.close()
        if pages:
            self._page = pages[0]
