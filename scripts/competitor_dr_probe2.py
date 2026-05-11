"""Deeper probe: dump all visible buttons + search DOM text for 'research'
and 'deep'. Also list `mat-` and `bard-` web-components in Gemini."""
from __future__ import annotations
import asyncio
import re
from playwright.async_api import async_playwright


CDP_URL = "http://localhost:9222"


async def list_buttons(page, label: str) -> None:
    print(f"\n--- {label}: visible buttons (first 40) ---")
    btns = await page.query_selector_all("button")
    seen = 0
    for b in btns:
        try:
            if not await b.is_visible():
                continue
            aria = await b.get_attribute("aria-label")
            txt = (await b.inner_text() or "")[:80].replace("\n", " ")
            data_testid = await b.get_attribute("data-testid")
            if not (aria or txt or data_testid):
                continue
            print(f"  btn aria={aria!r} testid={data_testid!r} text={txt!r}")
            seen += 1
            if seen >= 40:
                break
        except Exception:
            continue


async def search_dom_text(page, label: str, *terms: str) -> None:
    print(f"\n--- {label}: DOM text search for {terms} ---")
    html = await page.content()
    lower = html.lower()
    for t in terms:
        idx = 0
        hits = 0
        t_lower = t.lower()
        while True:
            i = lower.find(t_lower, idx)
            if i < 0:
                break
            ctx_start = max(0, i - 60)
            ctx_end = min(len(html), i + 80)
            snippet = html[ctx_start:ctx_end].replace("\n", " ")
            print(f"  '{t}' @ {i}: ...{snippet}...")
            idx = i + len(t)
            hits += 1
            if hits >= 5:
                break
        if hits == 0:
            print(f"  '{t}': NOT FOUND")


async def list_special_tags(page, *tags: str) -> None:
    print(f"\n--- web components ---")
    for tag in tags:
        els = await page.query_selector_all(tag)
        if not els:
            continue
        for el in els[:8]:
            try:
                aria = await el.get_attribute("aria-label")
                txt = (await el.inner_text() or "")[:60].replace("\n", " ")
                print(f"  <{tag}> aria={aria!r} text={txt!r}")
            except Exception:
                pass


async def main() -> None:
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(CDP_URL)
        ctx = browser.contexts[0]
        chatgpt = next((pg for pg in ctx.pages if "chatgpt.com" in pg.url), None)
        gemini = next((pg for pg in ctx.pages if "gemini.google.com" in pg.url), None)

        if chatgpt:
            print("\n=========================================")
            print("=== ChatGPT deep probe                ===")
            print("=========================================")
            await chatgpt.bring_to_front()
            await list_buttons(chatgpt, "chatgpt")
            await search_dom_text(chatgpt, "chatgpt", "deep research", "Deep Research", "research")

        if gemini:
            print("\n=========================================")
            print("=== Gemini deep probe                 ===")
            print("=========================================")
            await gemini.bring_to_front()
            await list_buttons(gemini, "gemini")
            await search_dom_text(gemini, "gemini", "Deep Research", "deep research", "research")
            await list_special_tags(gemini, "mat-select", "bard-mode-switcher", "bard-mode-list-button")


if __name__ == "__main__":
    asyncio.run(main())
