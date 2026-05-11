"""Periodic monitor: snapshot both DR tabs, auto-click any 'Start research'
or 'Approve plan' button if visible. Designed to be called repeatedly."""
import asyncio
import time
from pathlib import Path
from playwright.async_api import async_playwright


async def auto_advance(page, label):
    for sel in [
        "button:has-text('Start research')",
        "button:has-text('Approve plan')",
        "button:has-text('Begin')",
    ]:
        try:
            el = await page.query_selector(sel)
            if el and await el.is_visible():
                print(f"  [{label}] clicking auto-advance: {sel}")
                await el.click()
                return True
        except Exception:
            continue
    return False


async def snap_and_status(page, label):
    Path("state/dr_snapshots").mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%H%M%S")
    p = f"state/dr_snapshots/{label}_{ts}.png"
    await page.screenshot(path=p, full_page=False)
    body = ""
    try:
        body = await page.locator("body").inner_text(timeout=4000)
    except Exception:
        pass
    keywords = []
    for k in ["Generating research plan", "Researching", "Reading", "Searching",
              "Synthesizing", "Drafting", "Sources", "Bibliography",
              "Start research", "Approve plan", "97 searches", "Looking into",
              "Edit", "Update"]:
        if k.lower() in body.lower():
            keywords.append(k)
    print(f"[{label}] kw={keywords[:6]}")
    print(f"  url={page.url}")
    print(f"  snap={p}")
    return keywords


async def main():
    async with async_playwright() as pw:
        b = await pw.chromium.connect_over_cdp("http://localhost:9222")
        ctx = b.contexts[0]
        chatgpt = next((pg for pg in ctx.pages if "chatgpt.com" in pg.url), None)
        gemini = next((pg for pg in ctx.pages if "gemini.google.com" in pg.url), None)
        if chatgpt:
            await snap_and_status(chatgpt, "chatgpt")
            await auto_advance(chatgpt, "chatgpt")
        if gemini:
            await snap_and_status(gemini, "gemini")
            await auto_advance(gemini, "gemini")


asyncio.run(main())
