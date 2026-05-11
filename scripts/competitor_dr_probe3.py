"""Click ChatGPT '+' menu and Gemini 'Tools' button, dump what's revealed."""
from __future__ import annotations
import asyncio
import sys
from playwright.async_api import async_playwright

CDP_URL = "http://localhost:9222"


async def probe_chatgpt(page) -> None:
    print("\n=== ChatGPT: clicking composer-plus-btn ===")
    await page.bring_to_front()
    btn = await page.query_selector('[data-testid="composer-plus-btn"]')
    if not btn:
        print("  composer-plus-btn NOT FOUND")
        return
    await btn.click()
    await page.wait_for_timeout(1500)
    items = await page.query_selector_all('[role="menuitem"], button[role="menuitem"], [data-testid*="menu" i] button')
    if not items:
        items = await page.query_selector_all("button")
    print(f"  menu items found: {len(items)}")
    for i, el in enumerate(items[:40]):
        try:
            if not await el.is_visible():
                continue
            txt = (await el.inner_text() or "").strip().replace("\n", " ")[:80]
            aria = await el.get_attribute("aria-label") or ""
            testid = await el.get_attribute("data-testid") or ""
            if not (txt or aria or testid):
                continue
            print(f"    [{i}] text={txt!r} aria={aria!r} testid={testid!r}")
        except Exception:
            pass
    # Close menu so we don't leave UI dirty
    await page.keyboard.press("Escape")
    await page.wait_for_timeout(500)
    print("\n=== ChatGPT: also check 'Instant' model picker ===")
    instant_btns = await page.query_selector_all("button:has-text('Instant')")
    for b in instant_btns:
        if await b.is_visible():
            print("  clicking Instant to open model menu")
            await b.click()
            await page.wait_for_timeout(1500)
            items = await page.query_selector_all('[role="option"], [role="menuitem"], li')
            for el in items[:30]:
                try:
                    if not await el.is_visible():
                        continue
                    txt = (await el.inner_text() or "").strip().replace("\n", " ")[:120]
                    if txt:
                        print(f"    model: {txt!r}")
                except Exception:
                    pass
            await page.keyboard.press("Escape")
            break


async def probe_gemini(page) -> None:
    print("\n=== Gemini: clicking 'Tools' button ===")
    await page.bring_to_front()
    tools = await page.query_selector("button:has-text('Tools')")
    if tools:
        await tools.click()
        await page.wait_for_timeout(1500)
        items = await page.query_selector_all('[role="menuitem"], [role="option"], li, button')
        print(f"  tools-menu items (visible only):")
        for el in items[:30]:
            try:
                if not await el.is_visible():
                    continue
                txt = (await el.inner_text() or "").strip().replace("\n", " ")[:120]
                aria = await el.get_attribute("aria-label") or ""
                if txt and len(txt) < 60:
                    print(f"    text={txt!r} aria={aria!r}")
            except Exception:
                pass
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(500)
    else:
        print("  Tools button NOT FOUND")

    print("\n=== Gemini: clicking model picker (Pro) ===")
    picker = await page.query_selector('button[aria-label="Open mode picker"]')
    if picker:
        await picker.click()
        await page.wait_for_timeout(1500)
        items = await page.query_selector_all('[role="option"], [role="menuitem"], li, button')
        print(f"  mode-picker items (visible only):")
        for el in items[:30]:
            try:
                if not await el.is_visible():
                    continue
                txt = (await el.inner_text() or "").strip().replace("\n", " ")[:160]
                if txt:
                    print(f"    text={txt!r}")
            except Exception:
                pass
        await page.keyboard.press("Escape")
    else:
        print("  Mode picker NOT FOUND")


async def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(CDP_URL)
        ctx = browser.contexts[0]
        chatgpt = next((pg for pg in ctx.pages if "chatgpt.com" in pg.url), None)
        gemini = next((pg for pg in ctx.pages if "gemini.google.com" in pg.url), None)
        if chatgpt:
            await probe_chatgpt(chatgpt)
        if gemini:
            await probe_gemini(gemini)


if __name__ == "__main__":
    asyncio.run(main())
