"""Test typing speed in Application Name input."""
import asyncio
import time
from playwright.async_api import async_playwright


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1280, "height": 900})
        await page.goto("http://localhost:8765")
        await page.wait_for_timeout(2000)

        # Console mode
        await page.click("#ws-mode-dropdown button")
        await page.wait_for_timeout(300)
        await page.click('button[data-mode="operator"]')
        await page.wait_for_timeout(1000)

        # Campaigns sidebar
        items = await page.query_selector_all(".sidebar-item")
        for i in items:
            txt = await i.inner_text()
            if "Campaign" in txt:
                await i.click()
                break
        await page.wait_for_timeout(1000)

        # Library tab
        btns = await page.query_selector_all(".cm-toggle-btn")
        for b in btns:
            if (await b.inner_text()).strip() == "Library":
                await b.click()
                break
        await page.wait_for_timeout(800)

        # Click input
        inp = await page.query_selector("#library-app-input")
        await inp.click()
        await page.wait_for_timeout(200)

        # Type fast — 30ms per char (realistic fast typing)
        test_text = "Hospital HVAC System"
        t0 = time.time()
        await page.keyboard.type(test_text, delay=30)
        t1 = time.time()
        print("Typing {} chars took {:.1f}ms".format(len(test_text), (t1 - t0) * 1000))

        # Wait for final debounce
        await page.wait_for_timeout(200)

        # Check value
        val = await page.evaluate("""() => {
            var inp = document.getElementById("library-app-input");
            return inp ? inp.value : "NOT FOUND";
        }""")
        print("Value: '{}'".format(val))
        print("MATCH:", val == test_text)

        # Check focus retained
        focused = await page.evaluate("""() => {
            return document.activeElement ? document.activeElement.id : "none";
        }""")
        print("Focus:", focused)

        # Check previews updated (count filled spans)
        filled = await page.evaluate("""() => {
            return document.querySelectorAll(".library-preview-filled").length;
        }""")
        print("Preview filled spans:", filled)

        await page.screenshot(path="outputs/fix_typing_fast.png", full_page=False)
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
