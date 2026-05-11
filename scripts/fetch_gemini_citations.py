"""Fetch all 114 cited URLs from Gemini Q1 chat. Save as Gemini's
source_content_pool (the §-1.1 audit substrate, equivalent to
POLARIS's evidence_pool.direct_quote)."""
import json
import re
import time
import urllib.request
import urllib.error
from pathlib import Path


def fetch_url(url: str, timeout: float = 20.0) -> tuple[int, str]:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read(3_000_000).decode("utf-8", errors="replace")
            body = re.sub(r"<script[^>]*>.*?</script>", " ", body, flags=re.DOTALL | re.IGNORECASE)
            body = re.sub(r"<style[^>]*>.*?</style>", " ", body, flags=re.DOTALL | re.IGNORECASE)
            body = re.sub(r"<[^>]+>", " ", body)
            body = re.sub(r"\s+", " ", body).strip()
            return r.status, body[:30_000]
    except urllib.error.HTTPError as e:
        return e.code, f"HTTP {e.code}: {e.reason}"
    except Exception as e:
        return 0, f"FETCH ERROR: {type(e).__name__}: {e}"


def main():
    urls = json.load(open(".codex/I-eval-004/gemini_q1_anchor_urls.json", encoding="utf-8"))
    print(f"fetching {len(urls)} URLs")
    pool = []
    for i, u in enumerate(urls):
        href = u["href"]
        # Strip url= prefix used by Google redirects
        if "url?" in href:
            m = re.search(r"url\?[^&]*&q=([^&]+)", href) or re.search(r"q=([^&]+)", href)
            if m:
                href = urllib.parse.unquote(m.group(1))
        print(f"[{i+1}/{len(urls)}] {href[:80]}")
        status, content = fetch_url(href)
        pool.append({
            "evidence_id": f"gm_ev_{i:03d}",
            "anchor_text": u.get("text", "")[:200],
            "url": href,
            "status_code": status,
            "content": content,
            "content_length": len(content),
        })
        time.sleep(0.3)
    out = Path(".codex/I-eval-004/gemini_q1_source_content_pool.json")
    out.write_text(json.dumps(pool, ensure_ascii=False, indent=2), encoding="utf-8")
    ok = sum(1 for p in pool if 200 <= p["status_code"] < 300)
    print(f"saved {out}: {ok}/{len(pool)} OK status")


if __name__ == "__main__":
    main()
