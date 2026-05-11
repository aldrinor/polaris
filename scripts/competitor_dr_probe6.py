"""ChatGPT final probe: focus composer, type some text, then scan ALL
buttons on the page (entire viewport) to find DR or similar after the
composer 'engages'."""
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
        await chatgpt.goto("https://chatgpt.com/", wait_until="domcontentloaded")
        await chatgpt.wait_for_timeout(3000)

        composer = await chatgpt.query_selector('#prompt-textarea')
        if composer:
            await composer.click()
            await composer.type("hello", delay=30)
            await chatgpt.wait_for_timeout(2000)

        print("\n--- ALL visible buttons after typing in composer ---")
        btns = await chatgpt.query_selector_all("button, [role='button'], [role='switch']")
        seen = 0
        for b in btns:
            try:
                if not await b.is_visible():
                    continue
                aria = await b.get_attribute("aria-label") or ""
                txt = (await b.inner_text() or "")[:80].replace("\n", " ").strip()
                testid = await b.get_attribute("data-testid") or ""
                box = await b.bounding_box()
                if not box:
                    continue
                if aria or txt or testid:
                    print(f"  y={int(box['y']):>4} text={txt!r} aria={aria!r} testid={testid!r}")
                    seen += 1
                    if seen >= 60:
                        break
            except Exception:
                continue

        # Look for any text containing 'research' or 'deep' on the page now
        print("\n--- DOM text containing 'research' or 'deep' ---")
        html = await chatgpt.content()
        for term in ("Deep Research", "Deep research", "deep research", "Research"):
            idx = 0
            hits = 0
            while True:
                i = html.find(term, idx)
                if i < 0:
                    break
                snip = html[max(0,i-80):i+80].replace("\n"," ")
                print(f"  {term!r} @ {i}: ...{snip}...")
                idx = i + len(term)
                hits += 1
                if hits >= 4:
                    break
            if hits == 0:
                print(f"  {term!r}: NOT FOUND")

        # Clear composer
        if composer:
            await composer.click()
            await chatgpt.keyboard.press("Control+A")
            await chatgpt.keyboard.press("Delete")


if __name__ == "__main__":
    asyncio.run(main())
