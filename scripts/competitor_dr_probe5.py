"""ChatGPT: navigate to fresh /?model=... new chat, scan TOP-of-page header
for the model picker and any DR-related toggle. Try clicking what looks
like the conversation-header model name."""
from __future__ import annotations
import asyncio
import sys
from playwright.async_api import async_playwright

CDP_URL = "http://localhost:9222"


async def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(CDP_URL)
        ctx = browser.contexts[0]
        chatgpt = next((pg for pg in ctx.pages if "chatgpt.com" in pg.url), None)
        if not chatgpt:
            print("no chatgpt tab")
            return

        await chatgpt.bring_to_front()
        # Navigate to fresh chat
        print("Navigating to /")
        await chatgpt.goto("https://chatgpt.com/", wait_until="domcontentloaded")
        await chatgpt.wait_for_timeout(3500)

        # Dump ALL visible buttons in the top header area (above the composer)
        print("\n--- ALL visible buttons (whole page) ---")
        btns = await chatgpt.query_selector_all("button, [role='button']")
        seen = 0
        for b in btns:
            try:
                if not await b.is_visible():
                    continue
                box = await b.bounding_box()
                if not box:
                    continue
                y = box["y"]
                aria = await b.get_attribute("aria-label") or ""
                txt = (await b.inner_text() or "")[:80].replace("\n", " ").strip()
                testid = await b.get_attribute("data-testid") or ""
                if y < 200 and (aria or txt or testid):
                    print(f"  y={int(y)} text={txt!r} aria={aria!r} testid={testid!r}")
                    seen += 1
            except Exception:
                continue
        print(f"  (top-area buttons shown: {seen})")

        # Try clicking the visible model name near the top (e.g., "ChatGPT", "Auto", "5"...)
        print("\n--- Click 'ChatGPT' or similar top-header label ---")
        candidates = [
            'button:has-text("ChatGPT")',
            'button:has-text("Auto")',
            'button:has-text("GPT-5")',
            'button:has-text("o1")',
            'button:has-text("o3")',
            'button:has-text("5")',
        ]
        for sel in candidates:
            try:
                el = await chatgpt.query_selector(sel)
                if el and await el.is_visible():
                    box = await el.bounding_box()
                    if box and box["y"] < 100:
                        print(f"  clicking {sel}")
                        await el.click()
                        await chatgpt.wait_for_timeout(1800)
                        # Dump revealed menu
                        items = await chatgpt.query_selector_all('[role="menu"] *, [role="listbox"] *, [role="dialog"] *')
                        for item in items[:80]:
                            try:
                                if not await item.is_visible():
                                    continue
                                txt = (await item.inner_text() or "")[:200].replace("\n", " ").strip()
                                if txt and 3 < len(txt) < 150:
                                    print(f"    panel-item: {txt!r}")
                            except Exception:
                                pass
                        await chatgpt.keyboard.press("Escape")
                        break
            except Exception as e:
                print(f"  {sel} error: {e}")

        # Also try keyboard '/' to open a slash-command picker (ChatGPT-Plus often has this)
        print("\n--- Type '/' to test slash-command picker ---")
        composer = await chatgpt.query_selector('#prompt-textarea')
        if composer:
            await composer.click()
            await composer.type("/", delay=50)
            await chatgpt.wait_for_timeout(1500)
            items = await chatgpt.query_selector_all('[role="listbox"] *, [role="menu"] *, li')
            for item in items[:40]:
                try:
                    if not await item.is_visible():
                        continue
                    txt = (await item.inner_text() or "")[:140].replace("\n", " ").strip()
                    if txt and 3 < len(txt) < 100:
                        print(f"    slash-option: {txt!r}")
                except Exception:
                    pass
            # Clear
            await chatgpt.keyboard.press("Escape")
            await composer.click()
            await chatgpt.keyboard.press("Control+A")
            await chatgpt.keyboard.press("Delete")


if __name__ == "__main__":
    asyncio.run(main())
