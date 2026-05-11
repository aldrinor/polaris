"""Probe deeper: ChatGPT '+ → More' submenu, and Gemini model picker
with scroll; also dump ALL composer-right-side buttons on ChatGPT."""
from __future__ import annotations
import asyncio
import sys
from playwright.async_api import async_playwright

CDP_URL = "http://localhost:9222"


async def dump_visible_buttons(page, area_label: str, near_selector: str = None) -> None:
    print(f"\n--- {area_label} ---")
    if near_selector:
        scope = await page.query_selector(near_selector)
        if not scope:
            print(f"  scope selector {near_selector!r} not found")
            return
        btns = await scope.query_selector_all("button, [role='button'], [role='menuitem'], [role='option']")
    else:
        btns = await page.query_selector_all("button, [role='button'], [role='menuitem'], [role='option']")
    seen = 0
    for b in btns:
        try:
            if not await b.is_visible():
                continue
            aria = await b.get_attribute("aria-label") or ""
            txt = (await b.inner_text() or "")[:80].replace("\n", " ").strip()
            testid = await b.get_attribute("data-testid") or ""
            role = await b.get_attribute("role") or ""
            if not (aria or txt or testid):
                continue
            print(f"  text={txt!r} aria={aria!r} role={role!r} testid={testid!r}")
            seen += 1
            if seen >= 50:
                break
        except Exception:
            continue


async def probe_chatgpt(page) -> None:
    await page.bring_to_front()
    print("\n=== ChatGPT: composer-area buttons (near form) ===")
    # Composer area is typically inside a form/footer
    await dump_visible_buttons(page, "composer area", near_selector="form")

    print("\n=== ChatGPT: click + → wait → click 'More' ===")
    plus = await page.query_selector('[data-testid="composer-plus-btn"]')
    if plus:
        await plus.click()
        await page.wait_for_timeout(1200)
        more = await page.query_selector("text='More'")
        if more:
            await more.click()
            await page.wait_for_timeout(1500)
            print("  After clicking More:")
            items = await page.query_selector_all('[role="menuitem"], button, li')
            for el in items[:50]:
                try:
                    if not await el.is_visible():
                        continue
                    txt = (await el.inner_text() or "")[:120].replace("\n", " ").strip()
                    aria = await el.get_attribute("aria-label") or ""
                    if txt and len(txt) < 80:
                        print(f"    text={txt!r} aria={aria!r}")
                except Exception:
                    pass
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(300)
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(300)


async def probe_gemini(page) -> None:
    await page.bring_to_front()

    print("\n=== Gemini: composer-area buttons ===")
    await dump_visible_buttons(page, "near composer", near_selector="rich-textarea")

    print("\n=== Gemini: click Tools → wait → list FULL menu ===")
    tools = await page.query_selector("button:has-text('Tools')")
    if tools:
        await tools.click()
        await page.wait_for_timeout(1500)
        items = await page.query_selector_all('[role="menu"] [role="menuitem"], [role="menu"] button, [role="listbox"] [role="option"], mat-menu-item, mat-option')
        if not items:
            items = await page.query_selector_all('[role="menuitem"], button')
        print(f"  tools-menu items (visible):")
        for el in items[:50]:
            try:
                if not await el.is_visible():
                    continue
                txt = (await el.inner_text() or "")[:160].replace("\n", " ").strip()
                aria = await el.get_attribute("aria-label") or ""
                if txt and len(txt) < 120:
                    print(f"    text={txt!r} aria={aria!r}")
            except Exception:
                pass
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(500)

    print("\n=== Gemini: click model picker (Pro), then look at panel ===")
    picker = await page.query_selector('button[aria-label="Open mode picker"]')
    if picker:
        await picker.click()
        await page.wait_for_timeout(2000)
        # The picker is a dialog or menu — list its visible options
        # Look for elements that say "Deep Research" or similar
        items = await page.query_selector_all('[role="menu"] *, [role="dialog"] *, [role="listbox"] *, mat-option, [class*="model-picker" i] *, [class*="mode-picker" i] *')
        print(f"  picker descendants ({len(items)} total, showing visible):")
        seen = 0
        for el in items[:200]:
            try:
                if not await el.is_visible():
                    continue
                txt = (await el.inner_text() or "")[:140].replace("\n", " ").strip()
                if txt and 4 < len(txt) < 120 and "model" not in txt.lower()[:5]:
                    print(f"    text={txt!r}")
                    seen += 1
                    if seen >= 40:
                        break
            except Exception:
                pass
        # Try scrolling within the picker
        try:
            await page.keyboard.press("End")
            await page.wait_for_timeout(800)
        except Exception:
            pass
        await page.keyboard.press("Escape")


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
