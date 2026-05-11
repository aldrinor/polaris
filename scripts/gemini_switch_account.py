"""Switch Gemini account to Clifford Lam, verify Deep research available,
submit Q1 with DR enabled."""
import asyncio
import time
from pathlib import Path
from playwright.async_api import async_playwright


Q1 = "What is the cost-quality-jurisdiction trade-off between Canada operating its own sovereign frontier-LLM compute (SCALE-AI funded clusters, Quebec hydro) versus relying on US-headquartered hyperscalers (Azure, AWS, GCP) for federal-government AI workloads in 2026?"


async def snap(page, label):
    Path("state/dr_snapshots").mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    p = f"state/dr_snapshots/{label}_{ts}.png"
    await page.screenshot(path=p, full_page=False)
    print(f"  snap: {p}")


async def main():
    async with async_playwright() as pw:
        b = await pw.chromium.connect_over_cdp("http://localhost:9222")
        ctx = b.contexts[0]
        gemini = next((pg for pg in ctx.pages if "gemini.google.com" in pg.url), None)
        if not gemini:
            print("no gemini tab")
            return

        await gemini.bring_to_front()

        # Account picker should already be open from user. If not, open it.
        # Strategy: click on Clifford Lam entry
        print("Looking for Clifford Lam entry…")
        clicked = False
        for sel in [
            'text=Clifford Lam',
            'text=cliffordlamcp@gmail.com',
            'button:has-text("Clifford")',
            'a:has-text("Clifford")',
        ]:
            try:
                loc = gemini.locator(sel).first
                await loc.wait_for(state="visible", timeout=4000)
                await loc.click()
                clicked = True
                print(f"  clicked via {sel}")
                break
            except Exception as e:
                print(f"  {sel}: {e}")
        if not clicked:
            # The account picker might be closed; try clicking the profile avatar first
            print("Trying to open account picker first")
            try:
                avatar = await gemini.query_selector('img[alt*="avatar" i], button[aria-label*="account" i], a[aria-label*="account" i]')
                if avatar:
                    await avatar.click()
                    await gemini.wait_for_timeout(2000)
                    loc = gemini.get_by_text("Clifford Lam").first
                    await loc.wait_for(state="visible", timeout=4000)
                    await loc.click()
                    clicked = True
                    print("  clicked Clifford after opening picker")
            except Exception as e:
                print(f"  fallback failed: {e}")

        if not clicked:
            print("Could not switch account automatically. Please click Clifford manually.")
            await snap(gemini, "gemini_switch_fail")
            return

        # Wait for navigation/reload
        print("Waiting for switch to complete…")
        await gemini.wait_for_timeout(6000)
        await snap(gemini, "gemini_switched")

        # Verify URL still on Gemini
        print(f"  url after switch: {gemini.url}")
        # If on accounts.google.com, wait longer
        if "accounts.google.com" in gemini.url:
            print("  on accounts page, waiting more")
            await gemini.wait_for_timeout(6000)

        # Ensure on /app
        if "/app" not in gemini.url:
            await gemini.goto("https://gemini.google.com/app", wait_until="domcontentloaded")
            await gemini.wait_for_timeout(4000)

        # Confirm new account is Clifford
        body = await gemini.locator("body").inner_text()
        print(f"  body head: {body[:200]!r}")
        if "Clifford" in body[:500]:
            print("  ✓ switched to Clifford")
        else:
            print("  WARN: header doesn't say Clifford — may still be transitioning")

        # Open Tools menu
        await gemini.wait_for_timeout(2000)
        tools = await gemini.wait_for_selector("button:has-text('Tools')", timeout=10000)
        await tools.click()
        await gemini.wait_for_timeout(4000)
        await snap(gemini, "gemini_tools_open_clifford")


asyncio.run(main())
