"""
Playwright visual audit script for POLARIS dashboard.
Captures full-page and per-section screenshots for UI documentation.
"""

import asyncio
from pathlib import Path

from playwright.async_api import async_playwright


SECTION_IDS = [
    "overview",
    "planning",
    "search-fetch",
    "storm",
    "evidence",
    "verification",
    "iterations",
    "synthesis",
    "quality-gates",
    "llm-calls",
]


async def audit():
    output_dir = Path(r"C:\POLARIS\outputs\dashboard_audit")
    output_dir.mkdir(parents=True, exist_ok=True)

    html_path = Path(r"C:\POLARIS\outputs\dashboard_PG_TEST_060_BTG.html")
    if not html_path.exists():
        print(f"ERROR: Dashboard file not found at {html_path}")
        return

    url = f"file:///{html_path.as_posix()}"
    print(f"Opening: {url}")

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1920, "height": 1080})
        await page.goto(url, wait_until="networkidle")
        await page.wait_for_timeout(1000)

        # --- Screenshot 00: Full page, collapsed state ---
        await page.screenshot(
            path=str(output_dir / "00_full_page_collapsed.png"), full_page=True
        )
        print("Captured: 00_full_page_collapsed.png")

        # --- Screenshot 01: Above the fold ---
        await page.screenshot(path=str(output_dir / "01_above_fold.png"))
        print("Captured: 01_above_fold.png")

        # --- Expand ALL <details> elements ---
        details_count = await page.evaluate("""() => {
            const details = document.querySelectorAll('details');
            details.forEach(d => d.open = true);
            return details.length;
        }""")
        print(f"Expanded {details_count} <details> elements")
        await page.wait_for_timeout(500)

        # --- Screenshot 02: Full page, all expanded ---
        await page.screenshot(
            path=str(output_dir / "02_full_page_expanded.png"), full_page=True
        )
        print("Captured: 02_full_page_expanded.png")

        # --- Screenshot 03: Navigation sidebar ---
        nav = await page.query_selector("nav")
        if nav:
            box = await nav.bounding_box()
            if box:
                await page.screenshot(
                    path=str(output_dir / "03_nav_sidebar.png"),
                    clip={
                        "x": box["x"],
                        "y": box["y"],
                        "width": box["width"],
                        "height": min(box["height"], 1080),
                    },
                )
                print("Captured: 03_nav_sidebar.png")

        # --- Screenshot 04: Header / meta bar ---
        header = await page.query_selector("header")
        if header:
            box = await header.bounding_box()
            if box:
                await page.screenshot(
                    path=str(output_dir / "04_header_meta.png"),
                    clip={
                        "x": box["x"],
                        "y": box["y"],
                        "width": min(box["width"], 1920),
                        "height": box["height"],
                    },
                )
                print("Captured: 04_header_meta.png")

        # --- Per-section screenshots ---
        for idx, section_id in enumerate(SECTION_IDS):
            section = await page.query_selector(f"section#{section_id}")
            if not section:
                print(f"WARNING: Section #{section_id} not found, skipping")
                continue

            await section.scroll_into_view_if_needed()
            await page.wait_for_timeout(300)
            box = await section.bounding_box()
            if box:
                # Clip height to max 6000px to avoid huge screenshots
                clip_height = min(box["height"], 6000)
                clip_width = min(box["width"], 1920)
                await page.screenshot(
                    path=str(
                        output_dir
                        / f"section_{idx + 1:02d}_{section_id.replace('-', '_')}.png"
                    ),
                    clip={
                        "x": max(box["x"], 0),
                        "y": max(box["y"], 0),
                        "width": clip_width,
                        "height": clip_height,
                    },
                )
                print(
                    f"Captured: section_{idx + 1:02d}_{section_id}.png "
                    f"({clip_width:.0f}x{clip_height:.0f})"
                )
            else:
                print(f"WARNING: No bounding box for section #{section_id}")

        await browser.close()

    # Print summary
    captured = sorted(output_dir.glob("*.png"))
    print(f"\n--- Audit Complete ---")
    print(f"Total screenshots: {len(captured)}")
    print(f"Output directory: {output_dir}")
    for f in captured:
        size_kb = f.stat().st_size / 1024
        print(f"  {f.name:45s} {size_kb:>8.1f} KB")


if __name__ == "__main__":
    asyncio.run(audit())
