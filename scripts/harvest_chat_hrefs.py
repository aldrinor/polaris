"""In the original ChatGPT chat (authenticated, /c/<id>) and Gemini
chat (/u/1/app/<id>), look for any <a href> elements anywhere in the
page (including shadow DOM) that point to non-OpenAI/non-Google URLs.
These would be the citation deep-links."""
import asyncio
import json
from pathlib import Path
from playwright.async_api import async_playwright


async def harvest(page, label, exclude_hosts):
    print(f"\n[{label}] url: {page.url}")
    hrefs = await page.evaluate(f"""
        () => {{
            function* walk(root) {{
                const w = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT);
                let n = w.currentNode;
                while (n) {{
                    yield n;
                    if (n.shadowRoot) yield* walk(n.shadowRoot);
                    n = w.nextNode();
                }}
            }}
            const out = [];
            for (const el of walk(document)) {{
                if (el.tagName !== 'A') continue;
                const href = el.href || '';
                if (!href || !href.startsWith('http')) continue;
                const txt = (el.innerText || '').trim().slice(0, 100);
                out.push({{href, text: txt}});
            }}
            return out;
        }}
    """)
    print(f"[{label}] total <a> hrefs: {len(hrefs)}")
    # Filter out chrome/internal
    deep = [h for h in hrefs if not any(host in h["href"] for host in exclude_hosts)]
    print(f"[{label}] non-chrome external hrefs: {len(deep)}")
    seen_urls: set[str] = set()
    out_path = Path(f".codex/I-eval-004/{label}_q1_anchor_urls.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    unique = []
    for h in deep:
        if h["href"] in seen_urls:
            continue
        seen_urls.add(h["href"])
        unique.append(h)
    out_path.write_text(json.dumps(unique, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[{label}] unique: {len(unique)} saved to {out_path}")
    for h in unique[:20]:
        try:
            print(f"  - {h['href'][:100]} | {h['text'][:60]}")
        except UnicodeEncodeError:
            print(f"  - {h['href'][:100]} | (non-ascii text)")


async def main():
    async with async_playwright() as pw:
        b = await pw.chromium.connect_over_cdp("http://localhost:9222")
        ctx = b.contexts[0]

        chatgpt = next((p for p in ctx.pages if "chatgpt.com/c/" in p.url), None)
        if chatgpt:
            await harvest(
                chatgpt, "chatgpt",
                exclude_hosts=["chatgpt.com", "openai.com", "oaistatic.com",
                               "salesforce.com", "developers.openai.com"],
            )

        gemini = next((p for p in ctx.pages if "gemini.google.com" in p.url and "/app/" in p.url), None)
        if gemini:
            await harvest(
                gemini, "gemini",
                exclude_hosts=["google.com/intl", "policies.google.com",
                               "gemini.google.com", "fonts.gstatic",
                               "support.google.com", "youtube.com",
                               "myaccount.google.com", "accounts.google.com",
                               "fonts.googleapis"],
            )


asyncio.run(main())
