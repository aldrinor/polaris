"""Click on the DR result card to open the full Canvas, then scrape."""
import asyncio
import time
from pathlib import Path
from playwright.async_api import async_playwright

Q1 = "What is the cost-quality-jurisdiction trade-off between Canada operating its own sovereign frontier-LLM compute (SCALE-AI funded clusters, Quebec hydro) versus relying on US-headquartered hyperscalers (Azure, AWS, GCP) for federal-government AI workloads in 2026?"


async def main():
    async with async_playwright() as pw:
        b = await pw.chromium.connect_over_cdp("http://localhost:9222")
        ctx = b.contexts[0]
        chatgpt = next((pg for pg in ctx.pages if "chatgpt.com" in pg.url), None)
        await chatgpt.bring_to_front()

        # The card is somewhere in the conversation. Click on the title.
        # From the snap: "Canada's Sovereign Frontier-LLM Compute Versus Hyperscaler..."
        print("Looking for DR card by title fragment")
        candidates = [
            "text=Canada's Sovereign Frontier-LLM Compute",
            "text=Sovereign Frontier-LLM",
            "h2:has-text(\"Sovereign Frontier-LLM\")",
            "h3:has-text(\"Sovereign Frontier-LLM\")",
            "[role=\"button\"]:has-text(\"Sovereign\")",
        ]
        for sel in candidates:
            try:
                el = await chatgpt.wait_for_selector(sel, timeout=3000)
                if el and await el.is_visible():
                    box = await el.bounding_box()
                    print(f"  found {sel} at y={int(box['y']) if box else '?'}")
                    await el.click()
                    print("  clicked")
                    break
            except Exception as e:
                print(f"  {sel}: miss")
        await chatgpt.wait_for_timeout(3500)

        # Take screenshot to see the post-click state
        Path("state/dr_snapshots").mkdir(parents=True, exist_ok=True)
        await chatgpt.screenshot(path="state/dr_snapshots/chatgpt_canvas_opened.png", full_page=False)
        print("  snap saved")

        # Re-check page body for the DR content
        body = (await chatgpt.locator("body").inner_text())
        print(f"body len after click: {len(body)}")
        if len(body) > 5000:
            # Looks like content is now visible
            out = Path("state/compare_chatgpt_q1.md")
            out.write_text(
                f"# CHATGPT Deep Research - Q1\n\n**Question:** {Q1}\n\n---\n\n" + body,
                encoding="utf-8",
            )
            print(f"  saved {out} ({out.stat().st_size} bytes)")
        else:
            print(f"  still small; body head: {body[:300]}")


asyncio.run(main())
