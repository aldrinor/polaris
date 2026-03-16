"""Full visual audit of all Campaign Manager fixes."""
import asyncio
from playwright.async_api import async_playwright

ALIGN_JS = """() => {
    var reset = document.querySelector(".library-reset-btn");
    var appInput = document.querySelector(".library-app-input");
    if (!reset || !appInput) return "NOT FOUND";
    var rr = reset.getBoundingClientRect();
    var ar = appInput.getBoundingClientRect();
    return {
        reset_top: Math.round(rr.top),
        reset_bot: Math.round(rr.bottom),
        reset_h: Math.round(rr.height),
        input_top: Math.round(ar.top),
        input_bot: Math.round(ar.bottom),
        input_h: Math.round(ar.height),
        bot_diff: Math.round(Math.abs(rr.bottom - ar.bottom))
    };
}"""

BTN_JS = """() => {
    var btns = document.querySelectorAll(".cm-toggle-btn");
    var result = [];
    btns.forEach(function(b) {
        var r = b.getBoundingClientRect();
        result.push(b.textContent.trim() + "=" + Math.round(r.width) + "px");
    });
    return result;
}"""

NEW_BTN_JS = """() => {
    var btn = document.querySelector(".cm-new-btn");
    if (!btn) return "NOT FOUND";
    var cs = getComputedStyle(btn);
    return "font=" + cs.fontFamily.split(",")[0] + " weight=" + cs.fontWeight + " size=" + cs.fontSize;
}"""

DROPDOWN_JS = """() => {
    var sel = document.querySelector(".cm-top-bar select");
    if (!sel) return [];
    var opts = [];
    for (var i = 0; i < sel.options.length; i++) {
        opts.push(sel.options[i].text);
    }
    return opts;
}"""

PLACEHOLDER_JS = """() => {
    var inp = document.querySelector(".library-app-input");
    return inp ? inp.placeholder : "NOT FOUND";
}"""

BRIEF_JS = """() => {
    var ta = document.querySelector(".library-brief-textarea");
    return ta ? ta.value.substring(0, 200) : "NOT FOUND (collapsed)";
}"""

ICON_JS = """() => {
    var icon = document.querySelector(".library-edit-icon");
    if (!icon) return "NOT FOUND";
    return "opacity=" + getComputedStyle(icon).opacity;
}"""

WIDTH_JS = """(sel) => {
    var el = document.querySelector(sel);
    if (!el) return "NOT_FOUND";
    var r = el.getBoundingClientRect();
    return Math.round(r.width);
}"""


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1280, "height": 900})
        await page.goto("http://localhost:8765")
        await page.wait_for_timeout(2000)

        # Switch to Console mode
        await page.click("#ws-mode-dropdown button")
        await page.wait_for_timeout(300)
        await page.click('button[data-mode="operator"]')
        await page.wait_for_timeout(1000)

        # Click Campaigns sidebar
        items = await page.query_selector_all(".sidebar-item")
        for i in items:
            txt = await i.inner_text()
            if "Campaign" in txt:
                await i.click()
                break
        await page.wait_for_timeout(1000)

        # CHECK 1: Dropdown
        print("CHECK 1 - Dropdown:", await page.evaluate(DROPDOWN_JS))

        # CHECK 2: Toggle widths
        print("CHECK 2 - Toggle widths:", await page.evaluate(BTN_JS))

        # CHECK 3: New Campaign font
        print("CHECK 3 - New Btn:", await page.evaluate(NEW_BTN_JS))

        await page.screenshot(path="outputs/fix_01_topbar.png", full_page=False)

        # Go to Library
        btns = await page.query_selector_all(".cm-toggle-btn")
        for b in btns:
            if (await b.inner_text()).strip() == "Library":
                await b.click()
                break
        await page.wait_for_timeout(800)

        # CHECK 4: Placeholder
        print("CHECK 4 - Placeholder:", await page.evaluate(PLACEHOLDER_JS))

        # CHECK 5: Alignment
        print("CHECK 5 - Alignment:", await page.evaluate(ALIGN_JS))

        await page.screenshot(path="outputs/fix_02_library_top.png", full_page=False)

        # Expand brief
        await page.click(".library-brief-header")
        await page.wait_for_timeout(400)
        print("CHECK 6 - Brief:", await page.evaluate(BRIEF_JS))
        await page.screenshot(path="outputs/fix_03_brief.png", full_page=False)

        # Collapse brief
        await page.click(".library-brief-header")
        await page.wait_for_timeout(300)

        # CHECK 7: Hover edit icon
        v1 = await page.query_selector(".library-template-text")
        if v1:
            await v1.hover()
            await page.wait_for_timeout(300)
            print("CHECK 7 - Edit icon on hover:", await page.evaluate(ICON_JS))
            await page.screenshot(path="outputs/fix_04_hover.png", full_page=False)

            # Click to edit
            await v1.click()
            await page.wait_for_timeout(500)
            ta = await page.query_selector(".library-vector-edit")
            print("CHECK 7b - Textarea:", ta is not None)
            await page.screenshot(path="outputs/fix_05_editing.png", full_page=False)

        # CHECK 8: Width consistency
        views = [
            ("Map", ".campaign-map-view"),
            ("Planner", ".planner-view"),
            ("Library", ".library-view"),
            ("Results", ".results-view"),
        ]
        for label, sel in views:
            btns = await page.query_selector_all(".cm-toggle-btn")
            for b in btns:
                if (await b.inner_text()).strip() == label:
                    await b.click()
                    break
            await page.wait_for_timeout(500)
            w = await page.evaluate(WIDTH_JS, sel)
            print("CHECK 8 - {} = {}px".format(label, w))

        print("\n=== ALL CHECKS COMPLETE ===")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
