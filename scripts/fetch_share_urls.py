"""Open the ChatGPT + Gemini share URLs in the Edge browser, wait for
client-side render, then extract the full report text."""
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

CHATGPT_SHARE = "https://chatgpt.com/s/t_6a0252c45dbc819192dd9f8154f05e6c"
GEMINI_SHARE = "https://gemini.google.com/share/b674b89f3074"

Q1 = "What is the cost-quality-jurisdiction trade-off between Canada operating its own sovereign frontier-LLM compute (SCALE-AI funded clusters, Quebec hydro) versus relying on US-headquartered hyperscalers (Azure, AWS, GCP) for federal-government AI workloads in 2026?"


async def extract(url: str, out_path: Path, label: str) -> None:
    async with async_playwright() as pw:
        b = await pw.chromium.connect_over_cdp("http://localhost:9222")
        ctx = b.contexts[0]
        page = await ctx.new_page()
        try:
            print(f"[{label}] navigating {url}")
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            # Wait for client-side render
            await page.wait_for_timeout(8000)
            # Try several wait strategies
            try:
                await page.wait_for_load_state("networkidle", timeout=12000)
            except Exception:
                pass
            body = await page.locator("body").inner_text()
            print(f"[{label}] body len: {len(body)}")
            text_content = await page.evaluate("() => document.documentElement.textContent || ''")
            print(f"[{label}] textContent len: {len(text_content)}")
            best = body if len(body) > len(text_content) / 2 else text_content
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(
                f"# {label} Deep Research — Q1\n\n**Question:** {Q1}\n\n**Source URL:** {url}\n\n---\n\n" + best,
                encoding="utf-8",
            )
            print(f"[{label}] saved {out_path} ({out_path.stat().st_size} bytes)")
            # Show head
            print(f"[{label}] head: {best[:400]}")
        finally:
            await page.close()


async def main():
    await extract(CHATGPT_SHARE, Path("state/compare_chatgpt_q1.md"), "CHATGPT")
    await extract(GEMINI_SHARE, Path("state/compare_gemini_q1.md"), "GEMINI")


asyncio.run(main())
