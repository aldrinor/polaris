"""Hover over the card to surface action icons, then look for any new clickable elements."""
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright


async def main():
    async with async_playwright() as pw:
        b = await pw.chromium.connect_over_cdp("http://localhost:9222")
        ctx = b.contexts[0]
        chatgpt = next((pg for pg in ctx.pages if "chatgpt.com" in pg.url), None)
        await chatgpt.bring_to_front()

        vp = await chatgpt.evaluate("() => ({w: window.innerWidth, h: window.innerHeight})")
        cx = vp["w"] / 2
        cy = vp["h"] / 2 - 50
        print(f"hovering at center-ish ({cx}, {cy})")
        await chatgpt.mouse.move(cx, cy)
        await chatgpt.wait_for_timeout(1500)
        # Move into title row near right side
        await chatgpt.mouse.move(vp["w"] * 0.85, vp["h"] * 0.20)
        await chatgpt.wait_for_timeout(1500)

        Path("state/dr_snapshots").mkdir(parents=True, exist_ok=True)
        await chatgpt.screenshot(path="state/dr_snapshots/chatgpt_after_hover.png")
        print("snap")

        # Now scan ALL elements at the upper region for clickability
        print("\nAfter hover, scanning all visible clickables in upper viewport:")
        clickables = await chatgpt.evaluate("""
            () => {
                const out = [];
                const all = document.querySelectorAll('*');
                for (const el of all) {
                    const r = el.getBoundingClientRect();
                    if (r.width === 0 || r.height === 0) continue;
                    if (r.y > 400 || r.y < 50) continue;
                    if (r.x < 200) continue;  // skip sidebar
                    const tag = el.tagName.toLowerCase();
                    const role = el.getAttribute('role') || '';
                    const aria = el.getAttribute('aria-label') || '';
                    const onclick = !!el.onclick;
                    const tabindex = el.getAttribute('tabindex');
                    if (tag === 'svg' || tag === 'button' || tag === 'a' || role === 'button' || aria || onclick || tabindex !== null) {
                        out.push({
                            tag, role, aria,
                            x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                            text: (el.innerText || '').slice(0, 40)
                        });
                    }
                }
                return out;
            }
        """)
        for c in clickables:
            print(f"  <{c['tag']}> y={c['y']} x={c['x']} {c['w']}x{c['h']} role={c['role']!r} aria={c['aria']!r} text={c['text']!r}")


asyncio.run(main())
