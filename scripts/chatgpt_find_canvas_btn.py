"""Find a clickable button that opens DR result in full Canvas."""
import asyncio
from playwright.async_api import async_playwright


async def main():
    async with async_playwright() as pw:
        b = await pw.chromium.connect_over_cdp("http://localhost:9222")
        ctx = b.contexts[0]
        chatgpt = next((pg for pg in ctx.pages if "chatgpt.com" in pg.url), None)
        await chatgpt.bring_to_front()

        print("All visible buttons + role=button on page:")
        btns = await chatgpt.query_selector_all("button, [role='button'], a")
        for b_el in btns:
            try:
                if not await b_el.is_visible():
                    continue
                txt = (await b_el.inner_text() or "")[:60].replace("\n", " ").strip()
                aria = await b_el.get_attribute("aria-label") or ""
                href = await b_el.get_attribute("href") or ""
                if txt or aria:
                    print(f"  text={txt!r} aria={aria!r} href={href[:50]}")
            except Exception:
                continue


asyncio.run(main())
