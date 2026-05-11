"""Probe Edge via CDP: verify login state on chatgpt.com + gemini.google.com,
discover composer + Deep Research toggle selectors. No DR submission.
"""
from __future__ import annotations
import asyncio
import re
from playwright.async_api import async_playwright


CDP_URL = "http://localhost:9222"


async def probe_chatgpt(page) -> dict:
    await page.bring_to_front()
    print(f"  url: {page.url}")
    print(f"  title: {await page.title()}")
    body = await page.locator("body").inner_text()
    # Login state
    is_login = bool(re.search(r"\blog ?in\b|sign ?in", body[:1000], re.I))
    print(f"  appears_on_login_page: {is_login}")
    # Look for Pro indicators
    has_pro = "Pro" in body[:5000] or "Plus" in body[:5000]
    print(f"  pro_or_plus_in_first_5k: {has_pro}")
    # Hunt for composer
    composer_candidates = [
        ('[data-testid="prompt-textarea"]', "prompt-textarea testid"),
        ('div[contenteditable="true"]', "contenteditable div"),
        ('textarea', "textarea"),
        ('#prompt-textarea', "prompt-textarea id"),
    ]
    for sel, name in composer_candidates:
        try:
            el = await page.query_selector(sel)
            if el:
                visible = await el.is_visible()
                print(f"  composer[{name}] found, visible={visible}")
        except Exception as e:
            print(f"  composer[{name}] error: {e}")
    # Hunt for Deep Research toggle / button / tool
    print("  --- Deep Research hunt ---")
    candidates = [
        'button[aria-label*="Deep Research" i]',
        'button:has-text("Deep Research")',
        'button:has-text("Research")',
        'button[aria-label*="research" i]',
        '[data-testid*="research" i]',
        '[data-testid*="deep" i]',
        'button[aria-label*="tools" i]',
        'button:has-text("Tools")',
        'button[aria-label*="model" i]',
    ]
    for sel in candidates:
        try:
            els = await page.query_selector_all(sel)
            for el in els[:3]:
                if await el.is_visible():
                    aria = await el.get_attribute("aria-label")
                    txt = (await el.inner_text())[:60].replace("\n", " ")
                    print(f"    {sel} → aria={aria!r} text={txt!r}")
        except Exception:
            pass
    return {"url": page.url, "is_login": is_login}


async def probe_gemini(page) -> dict:
    await page.bring_to_front()
    print(f"  url: {page.url}")
    print(f"  title: {await page.title()}")
    if "accounts.google.com" in page.url:
        print("  WARNING: on Google account picker, not logged in")
        return {"url": page.url, "is_login": True}
    body = await page.locator("body").inner_text()
    has_advanced = any(k in body[:5000] for k in ["Advanced", "Deep Research", "Pro"])
    print(f"  advanced_or_dr_in_first_5k: {has_advanced}")
    # Hunt for composer
    for sel, name in [
        ('[contenteditable="true"][role="textbox"]', "contenteditable role=textbox"),
        ('rich-textarea [contenteditable="true"]', "rich-textarea inner"),
        ('[contenteditable="true"]', "any contenteditable"),
        ('textarea', "textarea"),
    ]:
        try:
            el = await page.query_selector(sel)
            if el and await el.is_visible():
                print(f"  composer[{name}] found, visible=True")
        except Exception as e:
            print(f"  composer[{name}] error: {e}")
    # Hunt for Deep Research / model picker
    print("  --- Deep Research / model picker hunt ---")
    candidates = [
        'button:has-text("Deep Research")',
        'button:has-text("Research")',
        'button:has-text("Gemini")',
        '[aria-label*="model" i]',
        '[aria-label*="research" i]',
        'mat-select',
        'bard-mode-switcher',
        '[data-test-id*="model"]',
        'button[aria-label*="advanced" i]',
    ]
    for sel in candidates:
        try:
            els = await page.query_selector_all(sel)
            for el in els[:3]:
                if await el.is_visible():
                    aria = await el.get_attribute("aria-label")
                    txt = (await el.inner_text())[:60].replace("\n", " ")
                    print(f"    {sel} → aria={aria!r} text={txt!r}")
        except Exception:
            pass
    return {"url": page.url, "is_login": False}


async def main() -> None:
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(CDP_URL)
        ctx = browser.contexts[0] if browser.contexts else None
        if not ctx:
            print("ERROR: no browser context")
            return
        chatgpt_pages = [pg for pg in ctx.pages if "chatgpt.com" in pg.url]
        gemini_pages = [pg for pg in ctx.pages if "gemini.google.com" in pg.url]
        print(f"chatgpt tabs: {len(chatgpt_pages)}, gemini tabs: {len(gemini_pages)}")
        if chatgpt_pages:
            print("\n=== ChatGPT probe ===")
            await probe_chatgpt(chatgpt_pages[0])
        else:
            print("WARNING: no chatgpt.com tab found")
        if gemini_pages:
            print("\n=== Gemini probe ===")
            await probe_gemini(gemini_pages[0])
        else:
            print("WARNING: no gemini.google.com tab found")


if __name__ == "__main__":
    asyncio.run(main())
