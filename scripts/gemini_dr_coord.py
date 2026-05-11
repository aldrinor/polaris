"""Click Deep research by mouse coordinates after locating its bounding
box. Fresh chat, then submit Q1."""
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
            print("no gemini")
            return
        await gemini.bring_to_front()

        # Fresh chat
        print("Fresh chat")
        await gemini.goto("https://gemini.google.com/u/1/app", wait_until="domcontentloaded")
        await gemini.wait_for_timeout(4000)

        # Open Tools
        tools = await gemini.wait_for_selector("button:has-text('Tools')", timeout=10000)
        await tools.click()
        await gemini.wait_for_timeout(3500)

        # Find Deep research element + click by coordinates
        print("Finding Deep research bounding box")
        rect = await gemini.evaluate("""
            () => {
                const els = Array.from(document.querySelectorAll('*'));
                for (const el of els) {
                    const r = el.getBoundingClientRect();
                    if (r.width === 0 || r.height === 0) continue;
                    const t = (el.innerText || '').trim();
                    if (t === 'Deep research') {
                        return {x: r.x, y: r.y, w: r.width, h: r.height};
                    }
                }
                return null;
            }
        """)
        print(f"  rect: {rect}")
        if not rect:
            print("Could not find DR rect")
            return
        cx = rect["x"] + rect["w"] / 2
        cy = rect["y"] + rect["h"] / 2
        print(f"  clicking ({cx}, {cy})")
        await gemini.mouse.click(cx, cy)
        await gemini.wait_for_timeout(2500)
        await snap(gemini, "gemini_dr_coord_clicked")

        # Verify DR is now selected — look for a "Deep research" chip near composer
        body = await gemini.locator("body").inner_text()
        dr_visible = "Deep research" in body
        print(f"  Deep research text still visible in body: {dr_visible}")

        # Type Q1
        print("Typing Q1")
        composer = await gemini.query_selector('rich-textarea [contenteditable="true"]')
        if not composer or not await composer.is_visible():
            composer = await gemini.query_selector('[contenteditable="true"]')
        if not composer:
            print("no composer")
            return
        await composer.click()
        await gemini.keyboard.insert_text(Q1)
        await gemini.wait_for_timeout(800)

        # Submit
        send = await gemini.query_selector('button[aria-label="Send message"]')
        if send:
            await send.click()
        else:
            await gemini.keyboard.press("Enter")
        print("Submitted")
        await gemini.wait_for_timeout(5000)
        await snap(gemini, "gemini_dr_coord_submitted")


asyncio.run(main())
