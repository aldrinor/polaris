"""Harvest <a href> from the ChatGPT share URL too."""
import asyncio
import json
from pathlib import Path
from playwright.async_api import async_playwright

URL = "https://chatgpt.com/s/t_6a0252c45dbc819192dd9f8154f05e6c"


async def main():
    async with async_playwright() as pw:
        b = await pw.chromium.connect_over_cdp("http://localhost:9222")
        ctx = b.contexts[0]
        page = await ctx.new_page()
        await page.bring_to_front()
        await page.goto(URL, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(8000)
        # Scroll a few times to ensure full render
        for _ in range(6):
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(1200)
        hrefs = await page.evaluate("""
            () => {
                function* walk(root) {
                    const w = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT);
                    let n = w.currentNode;
                    while (n) {
                        yield n;
                        if (n.shadowRoot) yield* walk(n.shadowRoot);
                        n = w.nextNode();
                    }
                }
                const out = [];
                for (const el of walk(document)) {
                    if (el.tagName !== 'A') continue;
                    const href = el.href || '';
                    if (!href.startsWith('http')) continue;
                    out.push({href, text: (el.innerText || '').trim().slice(0, 100)});
                }
                return out;
            }
        """)
        print(f"total <a>: {len(hrefs)}")
        exclude = ["chatgpt.com", "openai.com", "oaistatic.com",
                   "developers.openai.com", "salesforce.com",
                   "platform.openai.com", "login.salesforce.com",
                   "help.openai.com", "help.salesforce.com"]
        deep = [h for h in hrefs if not any(host in h["href"] for host in exclude)]
        print(f"non-chrome external: {len(deep)}")
        seen: set[str] = set()
        unique = []
        for h in deep:
            if h["href"] not in seen:
                seen.add(h["href"])
                unique.append(h)
        print(f"unique: {len(unique)}")
        Path(".codex/I-eval-004/chatgpt_q1_share_anchor_urls.json").write_text(
            json.dumps(unique, ensure_ascii=False, indent=2), encoding="utf-8")
        for h in unique[:30]:
            try:
                print(f"  - {h['href'][:90]} | {h['text'][:50]}")
            except UnicodeEncodeError:
                print(f"  - {h['href'][:90]} | (non-ascii)")


asyncio.run(main())
