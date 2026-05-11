"""ChatGPT probe v7: click the + button, then click ONLY the 'More' item
INSIDE the menu that just opened (not the sidebar's 'More'). Use a fresh
new chat and an empty composer."""
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

        # Make sure composer is empty (clear any leftover /hello)
        composer = await chatgpt.query_selector("#prompt-textarea")
        if composer:
            await composer.click()
            await chatgpt.keyboard.press("Control+A")
            await chatgpt.keyboard.press("Delete")
            await chatgpt.wait_for_timeout(400)

        # Click the + button
        plus = await chatgpt.query_selector('[data-testid="composer-plus-btn"]')
        if not plus:
            print("no plus btn")
            return
        await plus.click()
        await chatgpt.wait_for_timeout(1200)

        # Scope to the just-opened popover. Look for a menu/dialog/popover near the composer.
        # Common patterns: role="menu", radix-style data-state="open"
        print("\n--- popovers/menus open after + click ---")
        popovers = await chatgpt.query_selector_all('[role="menu"], [data-state="open"], [role="dialog"]')
        for i, pv in enumerate(popovers):
            try:
                if not await pv.is_visible():
                    continue
                box = await pv.bounding_box()
                if not box or box["y"] < 100:  # skip top-of-page chrome
                    continue
                print(f"\npopover[{i}] y={int(box['y'])} w={int(box['width'])} h={int(box['height'])}")
                items = await pv.query_selector_all('*')
                seen = 0
                for el in items:
                    try:
                        if not await el.is_visible():
                            continue
                        tag = (await el.evaluate("e => e.tagName")).lower()
                        txt = (await el.inner_text() or "")[:80].replace("\n", " ").strip()
                        aria = await el.get_attribute("aria-label") or ""
                        role = await el.get_attribute("role") or ""
                        if tag in ("button", "div", "li", "a") and (txt or aria) and 0 < len(txt) < 80:
                            print(f"    <{tag}> text={txt!r} aria={aria!r} role={role!r}")
                            seen += 1
                            if seen >= 30:
                                break
                    except Exception:
                        pass
            except Exception:
                continue

        # Now find the 'More' element INSIDE one of those popovers (not the sidebar)
        print("\n--- find 'More' inside popover and click ---")
        # Use a CSS selector that constrains 'More' to popover-like ancestors
        more_inside_popover = await chatgpt.query_selector(
            '[role="menu"] >> text=More, [data-state="open"] >> text=More'
        )
        if more_inside_popover:
            print("  found 'More' inside popover. Hovering then clicking.")
            await more_inside_popover.hover()
            await chatgpt.wait_for_timeout(400)
            await more_inside_popover.click()
            await chatgpt.wait_for_timeout(1500)
            # Dump revealed sub-popover
            sub = await chatgpt.query_selector_all('[role="menu"], [data-state="open"]')
            for pv in sub:
                if not await pv.is_visible():
                    continue
                box = await pv.bounding_box()
                if not box or box["y"] < 200:
                    continue
                print(f"\nsub-popover y={int(box['y'])}")
                els = await pv.query_selector_all('*')
                for el in els:
                    try:
                        if not await el.is_visible():
                            continue
                        txt = (await el.inner_text() or "")[:120].replace("\n", " ").strip()
                        if txt and 0 < len(txt) < 80:
                            print(f"    sub-item: {txt!r}")
                    except Exception:
                        pass
        else:
            print("  'More' inside popover NOT found — trying hover on 'More' anywhere with y > 200")
            mores = await chatgpt.query_selector_all('text=More')
            for m in mores:
                box = await m.bounding_box()
                if box and box["y"] > 200 and box["y"] < 800:
                    print(f"  hovering 'More' at y={int(box['y'])}")
                    await m.hover()
                    await chatgpt.wait_for_timeout(1500)
                    sub = await chatgpt.query_selector_all('[role="menu"], [role="menuitem"]')
                    for el in sub:
                        if not await el.is_visible():
                            continue
                        txt = (await el.inner_text() or "")[:120].replace("\n", " ").strip()
                        if txt and 0 < len(txt) < 80:
                            print(f"    after-hover-item: {txt!r}")
                    break

        await chatgpt.keyboard.press("Escape")


if __name__ == "__main__":
    asyncio.run(main())
