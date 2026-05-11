"""Retry Gemini Q1 with Deep Research properly enabled. Start a fresh
chat, open Tools menu, snapshot the menu state, click DR with multiple
strategies, submit Q1."""
import asyncio
import time
from pathlib import Path
from playwright.async_api import async_playwright


Q1 = "What is the cost-quality-jurisdiction trade-off between Canada operating its own sovereign frontier-LLM compute (SCALE-AI funded clusters, Quebec hydro) versus relying on US-headquartered hyperscalers (Azure, AWS, GCP) for federal-government AI workloads in 2026?"


async def snap(page, label):
    Path("state/dr_snapshots").mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    p = f"state/dr_snapshots/{label}_{ts}.png"
    await page.screenshot(path=p, full_page=False)
    print(f"  snap: {p}")
    return p


async def main():
    async with async_playwright() as pw:
        b = await pw.chromium.connect_over_cdp("http://localhost:9222")
        ctx = b.contexts[0]
        gemini = next((pg for pg in ctx.pages if "gemini.google.com" in pg.url), None)
        if not gemini:
            print("no gemini tab")
            return

        await gemini.bring_to_front()
        # Click "New chat" in left sidebar to clear state
        print("Starting new Gemini chat")
        new_chat = await gemini.query_selector("button:has-text('New chat')")
        if new_chat:
            await new_chat.click()
        else:
            await gemini.goto("https://gemini.google.com/app", wait_until="domcontentloaded")
        await gemini.wait_for_timeout(3500)

        # Click Tools
        print("Clicking Tools button")
        tools = await gemini.wait_for_selector("button:has-text('Tools')", timeout=8000)
        await tools.click()
        # Wait longer for menu to render — Angular menus can be slow
        await gemini.wait_for_timeout(4500)
        await snap(gemini, "gemini_tools_open")

        # Strategy 1: locator with role + name (Playwright's accessibility query)
        print("Strategy 1: page.get_by_role")
        clicked = False
        try:
            loc = gemini.get_by_role("menuitem", name="Deep research")
            await loc.wait_for(state="visible", timeout=4000)
            await loc.click(timeout=3000)
            clicked = True
            print("  ✓ clicked via get_by_role(menuitem)")
        except Exception as e:
            print(f"  miss: {e}")

        # Strategy 2: get_by_text non-exact (label may have icon prefix)
        if not clicked:
            print("Strategy 2: get_by_text (non-exact)")
            try:
                loc = gemini.get_by_text("Deep research").first
                await loc.wait_for(state="visible", timeout=4000)
                await loc.click(timeout=3000)
                clicked = True
                print("  ✓ clicked via get_by_text")
            except Exception as e:
                print(f"  miss: {e}")

        # Strategy 3: query ALL elements, find clickable one with exact text
        if not clicked:
            print("Strategy 3: scan all visible buttons / list items")
            for sel in [
                "button",
                "[role='menuitem']",
                "[role='option']",
                "li",
                "div[tabindex]",
                "mat-menu-item",
            ]:
                els = await gemini.query_selector_all(sel)
                for el in els:
                    try:
                        if not await el.is_visible():
                            continue
                        txt = (await el.inner_text() or "").strip()
                        if "Deep research" in txt and len(txt) < 50:
                            print(f"  trying {sel} with text {txt!r}")
                            try:
                                await el.click(timeout=2000)
                                clicked = True
                                print("  ✓ clicked")
                                break
                            except Exception as e:
                                print(f"    click failed: {e}")
                    except Exception:
                        continue
                if clicked:
                    break

        # Strategy 4: JS click using mousedown+mouseup events on the right element
        if not clicked:
            print("Strategy 4: JS dispatch mouse events")
            res = await gemini.evaluate("""
                () => {
                    const els = Array.from(document.querySelectorAll('*'));
                    for (const el of els) {
                        const r = el.getBoundingClientRect();
                        if (r.width === 0 || r.height === 0) continue;
                        const t = (el.innerText || '').trim();
                        if (t === 'Deep research') {
                            // Find closest clickable ancestor
                            let cur = el;
                            for (let i = 0; i < 5 && cur; i++) {
                                const tag = cur.tagName.toLowerCase();
                                const role = cur.getAttribute('role') || '';
                                if (tag === 'button' || tag === 'mat-menu-item' || role === 'menuitem' || role === 'option') {
                                    cur.click();
                                    return {clicked: true, tag, role};
                                }
                                cur = cur.parentElement;
                            }
                            // Last resort: click the element itself
                            el.click();
                            return {clicked: true, fallback: 'self'};
                        }
                    }
                    return {clicked: false};
                }
            """)
            print(f"  JS result: {res}")
            if res.get("clicked"):
                clicked = True

        if not clicked:
            print("ALL STRATEGIES FAILED")
            await snap(gemini, "gemini_dr_click_failed")
            return

        await gemini.wait_for_timeout(2500)
        await snap(gemini, "gemini_dr_selected")

        # Type Q1 in composer
        print("Typing Q1")
        composer = None
        for sel in [
            'rich-textarea [contenteditable="true"]',
            '[contenteditable="true"][role="textbox"]',
            '[contenteditable="true"]',
        ]:
            composer = await gemini.query_selector(sel)
            if composer and await composer.is_visible():
                break
        if not composer:
            print("composer not found")
            return
        await composer.click()
        await gemini.keyboard.insert_text(Q1)
        await gemini.wait_for_timeout(800)

        # Submit
        print("Submitting")
        send = await gemini.query_selector('button[aria-label="Send message"]')
        if send and await send.is_enabled():
            await send.click()
            print("  sent via send button")
        else:
            await gemini.keyboard.press("Enter")
            print("  sent via Enter")
        await gemini.wait_for_timeout(3000)
        await snap(gemini, "gemini_dr_submitted")


asyncio.run(main())
