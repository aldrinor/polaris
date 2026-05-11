"""Check ChatGPT page frames + shadow roots — DR result is hidden somewhere."""
import asyncio
from playwright.async_api import async_playwright


async def main():
    async with async_playwright() as pw:
        b = await pw.chromium.connect_over_cdp("http://localhost:9222")
        ctx = b.contexts[0]
        chatgpt = next((pg for pg in ctx.pages if "chatgpt.com" in pg.url), None)
        await chatgpt.bring_to_front()

        # List all frames
        print("--- frames ---")
        for fr in chatgpt.frames:
            print(f"  url={fr.url[:80]}")
            try:
                body_len = len(await fr.locator("body").inner_text(timeout=2000))
                print(f"    body len: {body_len}")
            except Exception as e:
                print(f"    body error: {e}")

        # Use JS to find the largest visible text anywhere including shadow DOM
        print("\n--- deep search incl shadow DOM ---")
        result = await chatgpt.evaluate("""
            () => {
                function* walk(root) {
                    const w = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT);
                    let n = w.currentNode;
                    while (n) {
                        yield n;
                        if (n.shadowRoot) {
                            yield* walk(n.shadowRoot);
                        }
                        n = w.nextNode();
                    }
                }
                let best = {len: 0, text: '', tag: ''};
                for (const el of walk(document)) {
                    if (!el.innerText) continue;
                    const t = el.innerText || '';
                    if (t.length > best.len && t.length < 200000) {
                        best = {len: t.length, text: t.slice(0, 8000), tag: el.tagName};
                    }
                }
                return best;
            }
        """)
        print(f"longest in shadow-aware walk: tag={result['tag']} len={result['len']}")
        print(f"head: {result['text'][:500]}")


asyncio.run(main())
