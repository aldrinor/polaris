"""
Browser Automation with JavaScript Rendering
=============================================
Full browser automation using Playwright.

Features:
- JavaScript execution
- SPA content extraction
- Screenshot capture
- Dynamic content waiting
"""

import logging
import asyncio
from typing import Any, Dict, List, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class BrowserResult:
    """Result from browser automation."""
    url: str
    title: str
    content: str
    screenshot_path: Optional[str]
    links: List[str]
    metadata: Dict[str, Any]


class BrowserAutomation:
    """
    Browser automation with JavaScript support.

    Uses Playwright for full browser rendering.
    """

    def __init__(
        self,
        headless: bool = True,
        timeout_ms: int = 30000,
        viewport_width: int = 1920,
        viewport_height: int = 1080,
    ):
        self.headless = headless
        self.timeout = timeout_ms
        self.viewport = {"width": viewport_width, "height": viewport_height}

        self.browser = None
        self.context = None
        self.playwright = None

    async def start(self):
        """Start browser instance."""
        try:
            from playwright.async_api import async_playwright

            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(headless=self.headless)
            self.context = await self.browser.new_context(
                viewport=self.viewport,
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )

            logger.info("[BROWSER] Started browser")

        except ImportError:
            logger.error("[BROWSER] Playwright not installed. Run: pip install playwright && playwright install")
            raise

    async def stop(self):
        """Stop browser instance."""
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        logger.info("[BROWSER] Stopped browser")

    async def fetch_page(
        self,
        url: str,
        wait_for: str = "networkidle",
        wait_selector: Optional[str] = None,
        execute_js: Optional[str] = None,
        capture_screenshot: bool = False,
    ) -> BrowserResult:
        """
        Fetch page with full JavaScript rendering.

        Args:
            url: URL to fetch
            wait_for: Wait condition ("load", "domcontentloaded", "networkidle")
            wait_selector: Optional CSS selector to wait for
            execute_js: Optional JavaScript to execute
            capture_screenshot: Whether to capture screenshot
        """
        if not self.context:
            await self.start()

        page = await self.context.new_page()
        screenshot_path = None

        try:
            # Navigate
            response = await page.goto(url, wait_until=wait_for, timeout=self.timeout)

            # Wait for selector if specified
            if wait_selector:
                await page.wait_for_selector(wait_selector, timeout=self.timeout)

            # Execute JavaScript if provided
            if execute_js:
                await page.evaluate(execute_js)

            # Get page content
            title = await page.title()
            content = await page.content()

            # Extract text content
            text_content = await page.evaluate("""
                () => {
                    const body = document.body;
                    const clone = body.cloneNode(true);

                    // Remove scripts and styles
                    clone.querySelectorAll('script, style, nav, footer, header').forEach(el => el.remove());

                    return clone.innerText;
                }
            """)

            # Extract links
            links = await page.evaluate("""
                () => Array.from(document.querySelectorAll('a[href]'))
                    .map(a => a.href)
                    .filter(href => href.startsWith('http'))
                    .slice(0, 50)
            """)

            # Capture screenshot
            if capture_screenshot:
                import tempfile
                screenshot_path = f"{tempfile.gettempdir()}/screenshot_{hash(url)}.png"
                await page.screenshot(path=screenshot_path, full_page=True)

            return BrowserResult(
                url=url,
                title=title,
                content=text_content,
                screenshot_path=screenshot_path,
                links=links,
                metadata={
                    "status": response.status if response else None,
                    "content_type": response.headers.get("content-type") if response else None,
                }
            )

        except Exception as e:
            logger.error(f"[BROWSER] Error fetching {url}: {e}")
            return BrowserResult(
                url=url,
                title="Error",
                content=str(e),
                screenshot_path=None,
                links=[],
                metadata={"error": str(e)}
            )

        finally:
            await page.close()

    async def fetch_spa_content(
        self,
        url: str,
        content_selector: str,
        scroll_to_load: bool = True,
        max_scrolls: int = 5,
    ) -> BrowserResult:
        """
        Fetch content from Single Page Applications.

        Handles infinite scroll and lazy loading.
        """
        if not self.context:
            await self.start()

        page = await self.context.new_page()

        try:
            await page.goto(url, wait_until="networkidle", timeout=self.timeout)

            # Wait for content
            await page.wait_for_selector(content_selector, timeout=self.timeout)

            # Handle scrolling
            if scroll_to_load:
                for i in range(max_scrolls):
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await asyncio.sleep(1)  # Wait for content to load

            # Extract content
            content = await page.evaluate(f"""
                () => {{
                    const elements = document.querySelectorAll('{content_selector}');
                    return Array.from(elements).map(el => el.innerText).join('\\n\\n');
                }}
            """)

            title = await page.title()

            return BrowserResult(
                url=url,
                title=title,
                content=content,
                screenshot_path=None,
                links=[],
                metadata={"scroll_count": max_scrolls if scroll_to_load else 0}
            )

        except Exception as e:
            logger.error(f"[BROWSER] SPA error: {e}")
            return BrowserResult(
                url=url,
                title="Error",
                content=str(e),
                screenshot_path=None,
                links=[],
                metadata={"error": str(e)}
            )

        finally:
            await page.close()

    async def execute_and_extract(
        self,
        url: str,
        extraction_script: str,
    ) -> Dict[str, Any]:
        """
        Navigate to URL and execute custom extraction script.
        """
        if not self.context:
            await self.start()

        page = await self.context.new_page()

        try:
            await page.goto(url, wait_until="networkidle", timeout=self.timeout)
            result = await page.evaluate(extraction_script)
            return {"success": True, "data": result}

        except Exception as e:
            return {"success": False, "error": str(e)}

        finally:
            await page.close()

    async def __aenter__(self):
        """Async context manager entry."""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.stop()
