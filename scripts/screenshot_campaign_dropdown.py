"""Verify C-POLAR campaign appears in dropdown."""
import asyncio
from playwright.async_api import async_playwright


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1280, "height": 900})
        await page.goto("http://localhost:8765")
        await page.wait_for_timeout(2000)

        # Console mode
        await page.click("#ws-mode-dropdown button")
        await page.wait_for_timeout(300)
        await page.click('button[data-mode="operator"]')
        await page.wait_for_timeout(1500)

        # Screenshot what we see first
        await page.screenshot(path="outputs/fix_drop_01.png", full_page=False)

        # Check for sidebar OR direct campaign view
        sidebar = await page.query_selector_all(".sidebar-item")
        print("Sidebar items:", len(sidebar))
        for s in sidebar:
            txt = await s.inner_text()
            vis = await s.is_visible()
            if "Campaign" in txt and vis:
                await s.click()
                print("Clicked sidebar:", txt.strip()[:40])
                break
        await page.wait_for_timeout(1000)

        # Check toggle buttons
        btns = await page.query_selector_all(".cm-toggle-btn")
        print("Toggle buttons:", len(btns))

        # Check dropdown
        sel = await page.query_selector(".cm-top-bar select")
        if sel:
            options = await page.evaluate("""() => {
                var sel = document.querySelector(".cm-top-bar select");
                var opts = [];
                for (var i = 0; i < sel.options.length; i++) {
                    opts.push({text: sel.options[i].text, value: sel.options[i].value});
                }
                return opts;
            }""")
            print("Dropdown:", options)

            # Select the C-POLAR campaign
            if len(options) > 1:
                await sel.select_option(index=1)
                await page.wait_for_timeout(500)
        else:
            print("No dropdown found")

        await page.screenshot(path="outputs/fix_drop_02.png", full_page=False)
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
