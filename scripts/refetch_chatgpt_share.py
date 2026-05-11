"""Re-fetch ChatGPT share URL with longer wait + scroll-to-load."""
import asyncio
import time
from pathlib import Path
from playwright.async_api import async_playwright


URL = "https://chatgpt.com/s/t_6a0252c45dbc819192dd9f8154f05e6c"


async def main():
    async with async_playwright() as pw:
        b = await pw.chromium.connect_over_cdp("http://localhost:9222")
        ctx = b.contexts[0]
        # Open in a NEW page so we don't disturb the existing chat tab
        page = await ctx.new_page()
        await page.bring_to_front()
        print("navigating")
        await page.goto(URL, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(5000)
        # Wait for the report container to appear
        for attempt in range(6):
            await page.wait_for_timeout(5000)
            try:
                body = await page.locator("body").inner_text(timeout=4000)
                tc = await page.evaluate("() => document.documentElement.textContent || ''")
                print(f"  attempt {attempt}: body={len(body)} textContent={len(tc)}")
                if "Executive summary" in tc or "Sovereign Frontier-LLM" in tc:
                    print("  ! report markers found")
                    break
            except Exception as e:
                print(f"  attempt {attempt} err: {e}")
        # Save snapshot to verify
        Path("state/dr_snapshots").mkdir(parents=True, exist_ok=True)
        await page.screenshot(path="state/dr_snapshots/chatgpt_share_loaded.png")
        # Save textContent
        tc = await page.evaluate("() => document.documentElement.textContent || ''")
        Path("state/compare_chatgpt_q1_raw.md").write_text(tc, encoding="utf-8")
        print(f"saved raw textContent ({len(tc)} chars)")
        print(f"contains 'Executive summary': {'Executive summary' in tc}")
        print(f"contains 'Sovereign Frontier-LLM': {'Sovereign Frontier-LLM' in tc}")
        print(f"contains 'Canada': {'Canada' in tc}")


asyncio.run(main())
