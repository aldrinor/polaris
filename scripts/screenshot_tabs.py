"""Screenshot all Campaign Manager tabs and measure widths at multiple viewports."""
import asyncio
import sys
from playwright.async_api import async_playwright

VIEWS = [
    ("Map", ".campaign-map-view"),
    ("Planner", ".planner-view"),
    ("Library", ".library-view"),
    ("Results", ".results-view"),
]

MEASURE_JS = """(sel) => {
    var el = document.querySelector(sel);
    if (!el) return "NOT_FOUND";
    var r = el.getBoundingClientRect();
    return { width: Math.round(r.width), left: Math.round(r.left) };
}"""


async def main():
    widths = [1280, 1024, 768]
    if len(sys.argv) > 1:
        widths = [int(x) for x in sys.argv[1:]]

    async with async_playwright() as p:
        browser = await p.chromium.launch()

        for vw in widths:
            page = await browser.new_page(viewport={"width": vw, "height": 900})
            await page.goto("http://localhost:8765")
            await page.wait_for_timeout(2000)

            # Switch to Console mode
            await page.click("#ws-mode-dropdown button")
            await page.wait_for_timeout(300)
            await page.click('button[data-mode="operator"]')
            await page.wait_for_timeout(1000)

            print("--- Viewport: {}px ---".format(vw))
            for label, sel in VIEWS:
                btns = await page.query_selector_all(".cm-toggle-btn")
                for b in btns:
                    txt = await b.inner_text()
                    if label == txt.strip():
                        await b.click()
                        break
                await page.wait_for_timeout(600)
                fname = "outputs/ss_resp_{}_{}.png".format(label.lower(), vw)
                await page.screenshot(path=fname, full_page=False)
                w = await page.evaluate(MEASURE_JS, sel)
                print("  {}: {}".format(label, w))

            await page.close()

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
