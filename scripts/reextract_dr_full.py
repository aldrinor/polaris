"""Re-fetch both share URLs with longer wait + scroll-to-bottom to force
the citation/references section to render. Capture the FULL response
range, including any Works Cited / Sources / References section."""
import asyncio
import time
from pathlib import Path
from playwright.async_api import async_playwright


CHAT_SHARE = "https://chatgpt.com/s/t_6a0252c45dbc819192dd9f8154f05e6c"
GEM_SHARE = "https://gemini.google.com/share/b674b89f3074"


async def grab(url: str, label: str, out_raw: Path) -> None:
    async with async_playwright() as pw:
        b = await pw.chromium.connect_over_cdp("http://localhost:9222")
        ctx = b.contexts[0]
        page = await ctx.new_page()
        try:
            await page.bring_to_front()
            print(f"[{label}] {url}")
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(7000)
            # Scroll to bottom multiple times to force render
            for _ in range(8):
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(1500)
            # Try networkidle
            try:
                await page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass
            await page.wait_for_timeout(3000)
            # Take screenshot at bottom of page
            Path("state/dr_snapshots").mkdir(parents=True, exist_ok=True)
            ts = time.strftime("%H%M%S")
            await page.screenshot(path=f"state/dr_snapshots/{label}_reextract_{ts}.png")
            # Grab full textContent
            tc = await page.evaluate("() => document.documentElement.textContent || ''")
            out_raw.write_text(tc, encoding="utf-8")
            print(f"[{label}] saved {out_raw}: {len(tc)} chars")
            # Quick markers check
            for kw in ["Sources", "Works cited", "References", "Bibliography",
                       "[1]", "Citations", "Notes"]:
                if kw in tc:
                    idx = tc.find(kw)
                    print(f"  '{kw}' first at {idx}; preview: {tc[idx:idx+200]!r}")
        finally:
            await page.close()


async def main():
    Path(".codex/I-eval-004").mkdir(parents=True, exist_ok=True)
    await grab(CHAT_SHARE, "chatgpt", Path(".codex/I-eval-004/chatgpt_q1_full_raw.txt"))
    await grab(GEM_SHARE, "gemini", Path(".codex/I-eval-004/gemini_q1_full_raw.txt"))


asyncio.run(main())
