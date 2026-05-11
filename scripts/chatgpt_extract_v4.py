"""Use Playwright Locator API which can see content rendered via React
Portal / Shadow DOM that querySelector misses."""
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

Q1 = "What is the cost-quality-jurisdiction trade-off between Canada operating its own sovereign frontier-LLM compute (SCALE-AI funded clusters, Quebec hydro) versus relying on US-headquartered hyperscalers (Azure, AWS, GCP) for federal-government AI workloads in 2026?"


async def main():
    async with async_playwright() as pw:
        b = await pw.chromium.connect_over_cdp("http://localhost:9222")
        ctx = b.contexts[0]
        chatgpt = next((pg for pg in ctx.pages if "chatgpt.com" in pg.url), None)
        await chatgpt.bring_to_front()

        # Use locator + has-text to find any element containing Executive summary
        print("Locator search for 'Executive summary'")
        loc = chatgpt.locator("text=Executive summary")
        count = await loc.count()
        print(f"  matches: {count}")
        for i in range(count):
            try:
                el = loc.nth(i)
                txt = await el.text_content()
                visible = await el.is_visible()
                print(f"  [{i}] visible={visible} text_content_len={len(txt or '')}")
            except Exception as e:
                print(f"  [{i}] err: {e}")

        # Walk up the DOM from the title element to find the parent that
        # contains the full report
        print("\nWalking up from 'Sovereign Frontier-LLM' title")
        try:
            title = chatgpt.locator("text=Sovereign Frontier-LLM").first
            await title.wait_for(state="attached", timeout=3000)
            # Get parent's parent's... look for the largest parent
            for level in range(10):
                parent = chatgpt.locator(f"text=Sovereign Frontier-LLM").first.locator(f"xpath=ancestor::*[{level + 1}]")
                try:
                    t = await parent.text_content(timeout=1500)
                    inner = await parent.inner_text(timeout=1500)
                    print(f"  level {level + 1}: textContent={len(t or '')} innerText={len(inner or '')}")
                    if t and len(t) > 5000:
                        # Found the container
                        print(f"  → saving from level {level + 1}")
                        # Pull innerText for cleaner formatting
                        out = Path("state/compare_chatgpt_q1.md")
                        out.write_text(
                            f"# CHATGPT Deep Research - Q1\n\n**Question:** {Q1}\n\n---\n\n" + (inner or t),
                            encoding="utf-8",
                        )
                        print(f"  saved {out} ({out.stat().st_size} bytes)")
                        return
                except Exception as e:
                    print(f"  level {level + 1}: err {e}")
                    break
        except Exception as e:
            print(f"  title not found: {e}")


asyncio.run(main())
