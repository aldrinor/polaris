"""Extract ChatGPT DR result from artifact / canvas pane."""
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
        # Try various selectors
        print("--- listing message containers ---")
        for sel in [
            '[data-message-author-role]',
            'article',
            'div.markdown',
            '.prose',
            'main article',
            '[data-testid*="conversation-turn"]',
            'div[role="presentation"]',
        ]:
            els = await chatgpt.query_selector_all(sel)
            print(f"  {sel}: {len(els)}")
            for i, el in enumerate(els[-3:]):
                try:
                    txt = (await el.inner_text() or "")
                    print(f"    [{i}] len={len(txt)} head={txt[:80]!r}")
                except Exception:
                    pass

        # Find the LONGEST visible text block (likely the DR report)
        print("\n--- finding longest visible text ---")
        longest = await chatgpt.evaluate("""
            () => {
                const all = Array.from(document.querySelectorAll('article, div, section'));
                let best = {len: 0, text: '', sel: ''};
                for (const el of all) {
                    if (el.offsetParent === null) continue;
                    const t = el.innerText || '';
                    if (t.length > best.len && t.length < 200000) {
                        best = {len: t.length, text: t, sel: el.tagName + (el.id ? '#' + el.id : '') + (el.className ? '.' + el.className.split(' ')[0] : '')};
                    }
                }
                return best;
            }
        """)
        print(f"longest: {longest['sel']} len={longest['len']}")
        print(f"head: {longest['text'][:300]}")

        if longest["len"] > 3000:
            out = Path("state/compare_chatgpt_q1.md")
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(
                f"# CHATGPT Deep Research - Q1\n\n**Question:** {Q1}\n\n---\n\n" + longest["text"],
                encoding="utf-8",
            )
            print(f"saved: {out} ({out.stat().st_size} bytes)")


asyncio.run(main())
