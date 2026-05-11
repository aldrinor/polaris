"""Submit Q1 to Gemini DR using Clifford ULTRA account (/u/1/)."""
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
            gemini = await ctx.new_page()
        await gemini.bring_to_front()

        print("Navigating to /u/1/app (Clifford ULTRA)")
        await gemini.goto("https://gemini.google.com/u/1/app", wait_until="domcontentloaded")
        await gemini.wait_for_timeout(4500)

        body = (await gemini.locator("body").inner_text())[:300]
        print(f"  header: {body[:100]!r}")

        # Open Tools
        tools = await gemini.wait_for_selector("button:has-text('Tools')", timeout=10000)
        await tools.click()
        await gemini.wait_for_timeout(4000)
        await snap(gemini, "gemini_u1_tools_open")

        # Click Deep research using JS — finds element by exact text and clicks the
        # nearest clickable ancestor
        print("Clicking Deep research via JS")
        res = await gemini.evaluate("""
            () => {
                const els = Array.from(document.querySelectorAll('*'));
                for (const el of els) {
                    const r = el.getBoundingClientRect();
                    if (r.width === 0 || r.height === 0) continue;
                    const t = (el.innerText || '').trim();
                    if (t === 'Deep research') {
                        let cur = el;
                        for (let i = 0; i < 6 && cur; i++) {
                            const role = (cur.getAttribute('role') || '').toLowerCase();
                            const tag = cur.tagName.toLowerCase();
                            if (tag === 'button' || tag === 'mat-menu-item' || role === 'menuitem' || role === 'option' || role === 'button') {
                                cur.click();
                                return {clicked: true, tag: cur.tagName, role};
                            }
                            cur = cur.parentElement;
                        }
                        el.click();
                        return {clicked: true, fallback: 'self', text: t};
                    }
                }
                return {clicked: false};
            }
        """)
        print(f"  result: {res}")
        if not res.get("clicked"):
            print("FAILED to click Deep research")
            return
        await gemini.wait_for_timeout(2500)
        await snap(gemini, "gemini_u1_dr_selected")

        # Type Q1
        print("Typing Q1")
        composer = None
        for sel in [
            'rich-textarea [contenteditable="true"]',
            '[contenteditable="true"][role="textbox"]',
            '[contenteditable="true"]',
        ]:
            composer = await gemini.query_selector(sel)
            if composer and await composer.is_visible():
                break
        if not composer:
            print("composer not found")
            return
        await composer.click()
        await gemini.keyboard.insert_text(Q1)
        await gemini.wait_for_timeout(800)

        # Submit
        print("Submitting")
        send = await gemini.query_selector('button[aria-label="Send message"]')
        if send:
            await send.click()
        else:
            await gemini.keyboard.press("Enter")
        await gemini.wait_for_timeout(4000)
        await snap(gemini, "gemini_u1_submitted")
        print("Submitted. Gemini DR should now be planning + researching.")


asyncio.run(main())
