"""Read-only probe: show current state of chatgpt tab without disturbing
the running runner."""
import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        b = await p.chromium.connect_over_cdp("http://localhost:9222")
        ctx = b.contexts[0]
        chatgpt = next((pg for pg in ctx.pages if "chatgpt.com" in pg.url), None)
        if not chatgpt:
            print("no chatgpt tab")
            return
        print("url:", chatgpt.url)
        # Get any visible "Researching" / "Working" / status indicator
        try:
            body = await chatgpt.locator("body").inner_text(timeout=3000)
            # Look for DR status keywords
            for kw in ("Researching", "Working", "Thinking", "Reading sources", "Deep research", "Synthesizing", "Drafting", "Sources"):
                if kw.lower() in body.lower():
                    idx = body.lower().find(kw.lower())
                    print(f"  saw: '{kw}' at offset {idx}")
            # Last assistant message length
            asst = await chatgpt.query_selector_all('[data-message-author-role="assistant"]')
            print(f"  assistant messages: {len(asst)}")
            if asst:
                last_text = await asst[-1].inner_text()
                print(f"  last assistant len: {len(last_text)}")
                print(f"  last assistant first 200: {last_text[:200]!r}")
        except Exception as e:
            print(f"  error: {e}")

asyncio.run(main())
