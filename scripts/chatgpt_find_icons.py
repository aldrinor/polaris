"""Inventory icons/clickables within the DR card area."""
import asyncio
from playwright.async_api import async_playwright


async def main():
    async with async_playwright() as pw:
        b = await pw.chromium.connect_over_cdp("http://localhost:9222")
        ctx = b.contexts[0]
        chatgpt = next((pg for pg in ctx.pages if "chatgpt.com" in pg.url), None)
        await chatgpt.bring_to_front()

        # All clickable items: buttons + links + role=button + things with onclick
        print("All visible clickables with aria-label or title:")
        els = await chatgpt.query_selector_all("button, a, [role='button'], [onclick], [tabindex]")
        for el in els:
            try:
                if not await el.is_visible():
                    continue
                box = await el.bounding_box()
                if not box:
                    continue
                aria = await el.get_attribute("aria-label") or ""
                title = await el.get_attribute("title") or ""
                testid = await el.get_attribute("data-testid") or ""
                txt = ((await el.inner_text(timeout=500)) or "")[:60].replace("\n", " ").strip()
                if aria or title or testid:
                    print(f"  y={int(box['y']):>4} x={int(box['x']):>4} aria={aria!r} title={title!r} testid={testid!r} text={txt!r}")
            except Exception:
                continue


asyncio.run(main())
