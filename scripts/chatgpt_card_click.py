"""Click the card title area directly via coords, snapshot the result."""
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright


async def main():
    async with async_playwright() as pw:
        b = await pw.chromium.connect_over_cdp("http://localhost:9222")
        ctx = b.contexts[0]
        chatgpt = next((pg for pg in ctx.pages if "chatgpt.com" in pg.url), None)
        await chatgpt.bring_to_front()
        await chatgpt.wait_for_timeout(1000)

        size = chatgpt.viewport_size
        print(f"viewport: {size}")

        # Find via JS where 'Canada' appears in title
        info = await chatgpt.evaluate("""
            () => {
                const all = document.querySelectorAll('*');
                for (const el of all) {
                    const t = (el.innerText || el.textContent || '').trim();
                    if (t.startsWith("Canada's Sovereign Frontier-LLM")) {
                        const r = el.getBoundingClientRect();
                        return {x: r.x, y: r.y, w: r.width, h: r.height, tag: el.tagName, id: el.id, cls: el.className};
                    }
                }
                return null;
            }
        """)
        print(f"title rect: {info}")
        if not info:
            return
        # Click at title center
        cx = info["x"] + info["w"] / 2
        cy = info["y"] + info["h"] / 2
        print(f"clicking ({cx}, {cy})")
        await chatgpt.mouse.click(cx, cy)
        await chatgpt.wait_for_timeout(3500)

        # Snapshot
        Path("state/dr_snapshots").mkdir(parents=True, exist_ok=True)
        await chatgpt.screenshot(path="state/dr_snapshots/chatgpt_after_card_click.png", full_page=False)
        print("snap saved")

        # Check body text
        body = await chatgpt.locator("body").inner_text()
        print(f"body len after click: {len(body)}")
        print(f"contains 'Executive summary': {'Executive summary' in body}")


asyncio.run(main())
