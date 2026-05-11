"""Submit Q1 to Gemini Deep research manually, with longer waits and a
fallback to JS-click. Then leave Gemini polling its own DR in browser."""
import asyncio
from playwright.async_api import async_playwright


Q1 = "What is the cost-quality-jurisdiction trade-off between Canada operating its own sovereign frontier-LLM compute (SCALE-AI funded clusters, Quebec hydro) versus relying on US-headquartered hyperscalers (Azure, AWS, GCP) for federal-government AI workloads in 2026?"


async def main():
    async with async_playwright() as pw:
        b = await pw.chromium.connect_over_cdp("http://localhost:9222")
        ctx = b.contexts[0]
        gemini = next((pg for pg in ctx.pages if "gemini.google.com" in pg.url), None)
        if not gemini:
            print("no gemini tab")
            return
        await gemini.bring_to_front()
        # Don't re-navigate; just make sure we're on /app
        if "/app" not in gemini.url:
            await gemini.goto("https://gemini.google.com/app", wait_until="domcontentloaded")
            await gemini.wait_for_timeout(4000)

        # Click Tools
        print("Clicking Tools")
        tools = await gemini.wait_for_selector("button:has-text('Tools')", timeout=8000)
        await tools.click()
        await gemini.wait_for_timeout(3500)  # menu render delay

        # Try to click Deep research via Playwright's get_by_text (permissive)
        print("Looking for Deep research")
        try:
            dr = gemini.get_by_text("Deep research", exact=True).first
            await dr.wait_for(state="visible", timeout=5000)
            print("  found via get_by_text. Clicking…")
            await dr.click(timeout=4000)
            print("  clicked")
        except Exception as e:
            print(f"  Playwright click failed: {e}. Trying JS-eval click.")
            try:
                clicked = await gemini.evaluate("""
                    () => {
                        const all = Array.from(document.querySelectorAll('*'));
                        for (const el of all) {
                            const t = (el.innerText || '').trim();
                            if (t === 'Deep research' && el.offsetParent !== null) {
                                el.click();
                                return true;
                            }
                        }
                        return false;
                    }
                """)
                print(f"  JS click result: {clicked}")
            except Exception as e2:
                print(f"  JS click also failed: {e2}")
                return

        await gemini.wait_for_timeout(2000)

        # Focus composer + type Q1
        print("Typing Q1")
        for sel in [
            'rich-textarea [contenteditable="true"]',
            '[contenteditable="true"][role="textbox"]',
            '[contenteditable="true"]',
        ]:
            c = await gemini.query_selector(sel)
            if c and await c.is_visible():
                await c.click()
                await gemini.keyboard.insert_text(Q1)
                break
        await gemini.wait_for_timeout(800)

        # Submit
        send = await gemini.query_selector('button[aria-label="Send message"]')
        if send:
            await send.click()
            print("Sent.")
        else:
            await gemini.keyboard.press("Enter")
            print("Sent via Enter.")


asyncio.run(main())
