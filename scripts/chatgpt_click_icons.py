"""Click the tiny icons at the right edge of the DR card title row.
Try each x-coordinate at y=98 from the snapshot."""
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright


async def main():
    async with async_playwright() as pw:
        b = await pw.chromium.connect_over_cdp("http://localhost:9222")
        ctx = b.contexts[0]
        chatgpt = next((pg for pg in ctx.pages if "chatgpt.com" in pg.url), None)
        await chatgpt.bring_to_front()
        await chatgpt.wait_for_timeout(800)

        # Get actual viewport via JS
        vp = await chatgpt.evaluate("() => ({w: window.innerWidth, h: window.innerHeight})")
        print(f"viewport: {vp}")

        # The card title row is at ~y=100. Right edge icons at ~94% of width.
        # Try clicking each of 3 likely positions
        for label, frac_x, y in [
            ("icon1", 0.92, 100),
            ("icon2", 0.94, 100),
            ("icon3", 0.96, 100),
            ("icon4_lower", 0.96, 110),
        ]:
            x = int(vp["w"] * frac_x)
            print(f"click {label}: ({x}, {y})")
            await chatgpt.mouse.click(x, y)
            await chatgpt.wait_for_timeout(2500)
            Path("state/dr_snapshots").mkdir(parents=True, exist_ok=True)
            await chatgpt.screenshot(path=f"state/dr_snapshots/chatgpt_after_{label}.png")
            # check body length growth
            body_len = len(await chatgpt.locator("body").inner_text(timeout=3000))
            print(f"  body len: {body_len}")
            if body_len > 5000:
                print(f"  CANVAS OPENED — saving")
                txt = await chatgpt.locator("body").inner_text()
                Path("state/compare_chatgpt_q1.md").write_text(
                    f"# CHATGPT Deep Research - Q1\n\n---\n\n" + txt, encoding="utf-8")
                print(f"  saved")
                return


asyncio.run(main())
