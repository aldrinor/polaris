"""Click the 'Start' button on ChatGPT DR plan dialog."""
import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as pw:
        b = await pw.chromium.connect_over_cdp("http://localhost:9222")
        ctx = b.contexts[0]
        chatgpt = next((pg for pg in ctx.pages if "chatgpt.com" in pg.url), None)
        # Try several variants
        for sel in [
            'button:has-text("Start"):not(:has-text("Started"))',
            'button >> text=Start',
            'text=Start',
        ]:
            try:
                el = await chatgpt.wait_for_selector(sel, timeout=3000)
                if el and await el.is_visible():
                    box = await el.bounding_box()
                    print(f"  clicking {sel} y={int(box['y']) if box else '?'}")
                    await el.click()
                    print("  clicked.")
                    return
            except Exception as e:
                print(f"  {sel}: {e}")
                continue
        print("Start button not found")

asyncio.run(main())
