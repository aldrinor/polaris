"""Try gemini.google.com/u/0..3/app to find which user index is Clifford,
then verify Deep research appears in Tools."""
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

        for idx in range(4):
            url = f"https://gemini.google.com/u/{idx}/app"
            print(f"\n=== Trying /u/{idx}/ ===")
            try:
                await gemini.goto(url, wait_until="domcontentloaded", timeout=15000)
            except Exception as e:
                print(f"  goto error: {e}")
                continue
            await gemini.wait_for_timeout(3500)
            body = (await gemini.locator("body").inner_text())[:300]
            for name in ["Hi Clifford", "Hi Aldrin"]:
                if name in body:
                    print(f"  -> {name} (user index {idx})")
            # Check for ULTRA badge in body or model-picker text
            if "ULTRA" in body[:1000] or "Ultra" in body[:1000]:
                print(f"  -> ULTRA tier visible")
            # Try Tools menu
            try:
                tools = await gemini.query_selector("button:has-text('Tools')")
                if tools:
                    await tools.click()
                    await gemini.wait_for_timeout(3500)
                    # Look for Deep research
                    html = await gemini.content()
                    if "Deep research" in html:
                        print(f"  YES Deep research IS available at /u/{idx}/")
                        return
                    else:
                        print(f"  Deep research NOT in tools menu at /u/{idx}/")
                    # Close menu
                    await gemini.keyboard.press("Escape")
                    await gemini.wait_for_timeout(500)
            except Exception as e:
                print(f"  tools probe error: {e}")


asyncio.run(main())
