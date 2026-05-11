"""Capture a screenshot of the chatgpt + gemini tabs to monitor DR progress.
Saves to state/dr_snapshots/{provider}_{ts}.png and prints a summary."""
import asyncio
import time
from pathlib import Path
from playwright.async_api import async_playwright

OUT = Path("state/dr_snapshots")


async def snap(page, label):
    OUT.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    p = OUT / f"{label}_{ts}.png"
    await page.screenshot(path=str(p), full_page=False)
    # Status summary
    try:
        body = await page.locator("body").inner_text(timeout=3000)
        # Look for key status keywords
        status_keywords = [
            "Researching", "Working on", "Reading", "Searching",
            "Drafting", "Synthesizing", "Sources", "Bibliography",
            "Start research", "Approve plan", "clarif",
        ]
        seen = [k for k in status_keywords if k.lower() in body.lower()]
        print(f"  status keywords: {seen}")
        asst = await page.query_selector_all('[data-message-author-role="assistant"]')
        if asst:
            txt = await asst[-1].inner_text()
            print(f"  assistant#{len(asst)} len={len(txt)} head={txt[:160]!r}")
    except Exception as e:
        print(f"  status probe error: {e}")
    print(f"  saved {p}")
    return str(p)


async def main():
    async with async_playwright() as pw:
        b = await pw.chromium.connect_over_cdp("http://localhost:9222")
        ctx = b.contexts[0]
        for label, host in [("chatgpt", "chatgpt.com"), ("gemini", "gemini.google.com")]:
            page = next((pg for pg in ctx.pages if host in pg.url), None)
            if not page:
                print(f"[{label}] tab not found")
                continue
            print(f"\n[{label}] url={page.url}")
            await snap(page, label)


asyncio.run(main())
