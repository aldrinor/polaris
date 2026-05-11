"""Save the completed ChatGPT DR Q1 output to state/compare_chatgpt_q1.md."""
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

Q1 = "What is the cost-quality-jurisdiction trade-off between Canada operating its own sovereign frontier-LLM compute (SCALE-AI funded clusters, Quebec hydro) versus relying on US-headquartered hyperscalers (Azure, AWS, GCP) for federal-government AI workloads in 2026?"


async def main():
    async with async_playwright() as pw:
        b = await pw.chromium.connect_over_cdp("http://localhost:9222")
        ctx = b.contexts[0]
        chatgpt = next((pg for pg in ctx.pages if "chatgpt.com" in pg.url), None)
        if not chatgpt:
            print("no chatgpt tab")
            return
        await chatgpt.bring_to_front()

        # Last assistant message contains the DR report
        asst = await chatgpt.query_selector_all('[data-message-author-role="assistant"]')
        if not asst:
            print("no assistant message")
            return
        last = asst[-1]
        text = await last.inner_text()
        print(f"len: {len(text)}")
        # Save
        out = Path("state/compare_chatgpt_q1.md")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            f"# CHATGPT Deep Research - Q1\n\n**Question:** {Q1}\n\n---\n\n" + text,
            encoding="utf-8",
        )
        print(f"saved: {out} ({out.stat().st_size} bytes)")
        # Print first 500 chars to confirm content
        print(f"head:\n{text[:500]}")


asyncio.run(main())
