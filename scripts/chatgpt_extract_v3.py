"""Try multiple text-extraction methods, including iframe and accessibility tree."""
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

        # Method 1: textContent of all elements
        print("Method 1: textContent of entire document")
        all_text = await chatgpt.evaluate("() => document.documentElement.textContent || ''")
        print(f"  total textContent len: {len(all_text)}")
        print(f"  contains 'Sovereign Frontier-LLM': {'Sovereign Frontier-LLM' in all_text}")
        print(f"  contains 'Executive summary': {'Executive summary' in all_text}")
        # Find the start of the report
        if "Sovereign Frontier-LLM" in all_text:
            idx = all_text.find("Sovereign Frontier-LLM")
            print(f"  report starts at offset {idx}; preview:")
            print(f"  {all_text[idx:idx+400]}")

        # Method 2: outerHTML of the conversation turn
        print("\nMethod 2: outerHTML of conversation turn")
        turns = await chatgpt.query_selector_all('[data-testid*="conversation-turn"]')
        for i, t in enumerate(turns):
            html_len = len(await t.evaluate("e => e.outerHTML"))
            inner_text_len = len((await t.inner_text()) or "")
            text_content_len = len(await t.evaluate("e => e.textContent || ''"))
            print(f"  turn[{i}] html={html_len} innerText={inner_text_len} textContent={text_content_len}")

        # Method 3: Accessibility tree snapshot
        print("\nMethod 3: accessibility snapshot")
        try:
            snap = await chatgpt.accessibility.snapshot()
            # Stringify and search
            import json
            s = json.dumps(snap)
            print(f"  accessibility tree size: {len(s)}")
            print(f"  contains 'Sovereign Frontier-LLM': {'Sovereign Frontier-LLM' in s}")
            print(f"  contains 'Executive summary': {'Executive summary' in s}")
        except Exception as e:
            print(f"  error: {e}")

        # If method 1 found content, save it
        if "Sovereign Frontier-LLM" in all_text and "Executive summary" in all_text:
            # Extract from title to end of last citation
            start = all_text.find("Canada's Sovereign Frontier-LLM")
            if start < 0:
                start = all_text.find("Sovereign Frontier-LLM")
            content = all_text[start:start+50000]  # cap at 50k chars
            out = Path("state/compare_chatgpt_q1.md")
            out.write_text(
                f"# CHATGPT Deep Research - Q1\n\n**Question:** {Q1}\n\n---\n\n" + content,
                encoding="utf-8",
            )
            print(f"\nSAVED: {out} ({out.stat().st_size} bytes)")


asyncio.run(main())
