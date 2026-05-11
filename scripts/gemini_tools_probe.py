"""Open Gemini Tools menu and inspect the Deep research element's actual
tag, role, and selectors so we can click it reliably."""
import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as pw:
        b = await pw.chromium.connect_over_cdp("http://localhost:9222")
        ctx = b.contexts[0]
        gemini = next((pg for pg in ctx.pages if "gemini.google.com" in pg.url), None)
        if not gemini:
            print("no gemini tab")
            return
        await gemini.bring_to_front()
        await gemini.goto("https://gemini.google.com/app", wait_until="domcontentloaded")
        await gemini.wait_for_timeout(3500)
        tools = await gemini.query_selector("button:has-text('Tools')")
        if not tools:
            print("Tools button not found")
            return
        await tools.click()
        await gemini.wait_for_timeout(2000)

        # Find any element containing "Deep research" text
        print("--- elements with 'Deep research' text ---")
        elements = await gemini.query_selector_all("*")
        seen = 0
        for el in elements:
            try:
                if not await el.is_visible():
                    continue
                txt = (await el.inner_text(timeout=300) or "").strip()
                if txt == "Deep research" or (txt.startswith("Deep research") and len(txt) < 40):
                    tag = (await el.evaluate("e => e.tagName")).lower()
                    role = await el.get_attribute("role") or ""
                    aria = await el.get_attribute("aria-label") or ""
                    cls = (await el.get_attribute("class") or "")[:120]
                    parent = await el.evaluate_handle("e => e.parentElement")
                    p_tag = await parent.evaluate("e => e.tagName") if parent else "?"
                    p_role = await parent.evaluate("e => e.getAttribute('role')") if parent else "?"
                    box = await el.bounding_box()
                    y = int(box["y"]) if box else "?"
                    print(f"  <{tag}> y={y} role={role!r} aria={aria!r} class={cls!r}")
                    print(f"     parent <{p_tag}> role={p_role!r}")
                    seen += 1
                    if seen >= 8:
                        break
            except Exception:
                continue


asyncio.run(main())
