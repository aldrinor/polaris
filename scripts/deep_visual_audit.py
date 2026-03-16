"""
Deep Visual Audit — Pixel-level screenshot capture for every view, tab, interaction, and screen size.
Captures screenshots for manual review. No auto-pass logic.
"""

import asyncio
import sys
import os
from pathlib import Path
from playwright.async_api import async_playwright

URL = "http://localhost:8771"
OUT = Path("logs/deep_audit_screenshots")
OUT.mkdir(parents=True, exist_ok=True)

VIEWPORTS = [
    ("desktop_1920", 1920, 1080),
    ("laptop_1440", 1440, 900),
    ("tablet_1024", 1024, 768),
    ("mobile_768", 768, 1024),
]


async def wait_loaded(page):
    """Wait for dashboard to fully load with events."""
    await page.wait_for_selector(".app-header", timeout=10000)
    await page.wait_for_timeout(2000)  # let SSE events arrive


async def click_nav(page, view_name):
    """Click a nav button by data-view attribute."""
    btn = page.locator(f'.nav-btn[data-view="{view_name}"]')
    await btn.click()
    await page.wait_for_timeout(800)


async def click_adv_tab(page, tab_text):
    """Click an advanced sub-tab by text content."""
    btn = page.locator(f'.adv-tab-btn:has-text("{tab_text}")')
    await btn.click()
    await page.wait_for_timeout(600)


async def screenshot(page, name, full_page=False):
    """Take a screenshot with a descriptive name."""
    path = OUT / f"{name}.png"
    await page.screenshot(path=str(path), full_page=full_page)
    print(f"  [{name}] saved ({path.stat().st_size // 1024}KB)")


async def audit_viewport(browser, vp_name, width, height):
    """Run full audit at a specific viewport size."""
    print(f"\n{'='*60}")
    print(f"VIEWPORT: {vp_name} ({width}x{height})")
    print(f"{'='*60}")

    context = await browser.new_context(viewport={"width": width, "height": height})
    page = await context.new_page()

    # Collect JS errors
    js_errors = []
    page.on("pageerror", lambda err: js_errors.append(str(err)))

    await page.goto(URL)
    await wait_loaded(page)

    # ── 1. Research View (default) ──
    print("\n[Research View]")
    await screenshot(page, f"{vp_name}_01_research_full")

    # Scroll reasoning stream
    reasoning = page.locator(".reasoning-stream")
    if await reasoning.count() > 0:
        await reasoning.evaluate("el => el.scrollTop = el.scrollHeight")
        await page.wait_for_timeout(400)
        await screenshot(page, f"{vp_name}_02_research_scrolled")
        await reasoning.evaluate("el => el.scrollTop = 0")

    # Expand a phase block if collapsed
    phase_headers = page.locator(".phase-block-header")
    count = await phase_headers.count()
    if count > 0:
        # Click first collapsed block
        first_block = page.locator(".phase-block:not(.expanded)").first
        if await first_block.count() > 0:
            await first_block.locator(".phase-block-header").click()
            await page.wait_for_timeout(400)
            await screenshot(page, f"{vp_name}_03_research_phase_expanded")

    # Scroll pipeline column
    pipeline = page.locator(".pipeline-column")
    if await pipeline.count() > 0:
        await pipeline.evaluate("el => el.scrollTop = el.scrollHeight")
        await page.wait_for_timeout(400)
        await screenshot(page, f"{vp_name}_04_research_pipeline_scrolled")
        await pipeline.evaluate("el => el.scrollTop = 0")

    # ── 2. Evidence View ──
    print("\n[Evidence View]")
    await click_nav(page, "evidence")
    await screenshot(page, f"{vp_name}_05_evidence_full")

    # Click a filter chip (Gold, Silver, Bronze)
    gold_chip = page.locator('.filter-chip[data-tier="gold"]')
    if await gold_chip.count() > 0:
        await gold_chip.click()
        await page.wait_for_timeout(400)
        await screenshot(page, f"{vp_name}_06_evidence_gold_filter")
        # Reset
        all_chip = page.locator('.filter-chip[data-tier="all"]')
        if await all_chip.count() > 0:
            await all_chip.click()
            await page.wait_for_timeout(300)

    # Click an evidence card to open detail panel
    ev_card = page.locator(".ev-card").first
    if await ev_card.count() > 0:
        await ev_card.click()
        await page.wait_for_timeout(600)
        await screenshot(page, f"{vp_name}_07_evidence_detail_panel")

        # Close detail panel
        close_btn = page.locator(".detail-panel-close")
        if await close_btn.count() > 0:
            await close_btn.click()
            await page.wait_for_timeout(1000)  # extra time for mobile fullscreen overlay to close + re-render

    # Debug: check if panel is still open
    panel_open = await page.locator(".evidence-detail-panel.open").count()
    if panel_open:
        print(f"  WARNING: Detail panel still open after close click!")
        # Try pressing Escape as fallback
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(500)

    # Hover over graph node (if any SVG circles exist)
    circles = page.locator("svg circle")
    circle_count = await circles.count()
    print(f"  SVG circles found: {circle_count}")
    if circle_count > 3:
        box = await circles.nth(2).bounding_box()
        print(f"  Circle bounding box: {box}")
        if box and box["width"] > 0 and box["height"] > 0:
            await page.mouse.move(box["x"] + box["width"]/2, box["y"] + box["height"]/2)
            await page.wait_for_timeout(500)
            await screenshot(page, f"{vp_name}_08_evidence_graph_hover")
        else:
            # Circles exist in DOM but not visible — take screenshot anyway for debugging
            await screenshot(page, f"{vp_name}_08_evidence_graph_hover")

    # ── 3. Report View ──
    print("\n[Report View]")
    await click_nav(page, "report")
    await page.wait_for_timeout(500)
    await screenshot(page, f"{vp_name}_09_report_top")

    # Scroll down to see full report
    report_view = page.locator(".report-view")
    if await report_view.count() > 0:
        await report_view.evaluate("el => el.scrollTop = 400")
        await page.wait_for_timeout(400)
        await screenshot(page, f"{vp_name}_10_report_body")

        await report_view.evaluate("el => el.scrollTop = el.scrollHeight")
        await page.wait_for_timeout(400)
        await screenshot(page, f"{vp_name}_11_report_bottom_bib")

        await report_view.evaluate("el => el.scrollTop = 0")

    # Click a citation link
    cite_link = page.locator(".cite-link, .cite-ref").first
    if await cite_link.count() > 0:
        await cite_link.click()
        await page.wait_for_timeout(500)
        await screenshot(page, f"{vp_name}_12_report_citation_popover")
        # Dismiss popover
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(300)

    # ── 4. Advanced View — Queries ──
    print("\n[Advanced View]")
    await click_nav(page, "advanced")
    await page.wait_for_timeout(500)
    await screenshot(page, f"{vp_name}_13_adv_queries")

    # ── 4b. Advanced — Sources ──
    await click_adv_tab(page, "Sources")
    await screenshot(page, f"{vp_name}_14_adv_sources")

    # ── 4c. Advanced — STORM ──
    await click_adv_tab(page, "STORM")
    await screenshot(page, f"{vp_name}_15_adv_storm_personas")

    # Scroll STORM pane to see transcript
    storm_pane = page.locator('.adv-pane.active')
    if await storm_pane.count() > 0:
        await storm_pane.evaluate("el => el.scrollTop = 600")
        await page.wait_for_timeout(400)
        await screenshot(page, f"{vp_name}_16_adv_storm_transcript")
        await storm_pane.evaluate("el => el.scrollTop = 0")

    # ── 4d. Advanced — Trace ──
    await click_adv_tab(page, "Trace")
    await screenshot(page, f"{vp_name}_17_adv_trace")

    # ── 4e. Advanced — Cost ──
    await click_adv_tab(page, "Cost")
    await screenshot(page, f"{vp_name}_18_adv_cost")

    # ── JS Error Report ──
    print(f"\n  JS Errors: {len(js_errors)}")
    for err in js_errors:
        print(f"    ERROR: {err[:120]}")

    await context.close()
    return js_errors


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        all_errors = []

        for vp_name, w, h in VIEWPORTS:
            errors = await audit_viewport(browser, vp_name, w, h)
            all_errors.extend(errors)

        await browser.close()

    # Summary
    total_screenshots = len(list(OUT.glob("*.png")))
    print(f"\n{'='*60}")
    print(f"DEEP AUDIT COMPLETE")
    print(f"  Screenshots: {total_screenshots}")
    print(f"  JS Errors: {len(all_errors)}")
    print(f"  Output: {OUT}")
    print(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(main())
