"""Fetch all cited URLs from ChatGPT + Gemini Q1 DR outputs, save as
source_content_pool.json (equivalent to POLARIS's evidence_pool).
"""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path
from urllib.parse import urlparse


# Re-use the inline-url regex from competitor enumeration
CHATGPT_URL_PATTERN = re.compile(
    r"[\\]+ue200url[\\]+ue202([^\\]+?)[\\]+ue202(https?://[^\\\s]+?)[\\]+ue201",
    re.IGNORECASE,
)


def extract_chatgpt_urls(src: str) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    for m in CHATGPT_URL_PATTERN.finditer(src):
        title, url = m.group(1), m.group(2)
        if url in seen:
            continue
        seen.add(url)
        out.append({"title": title, "url": url})
    return out


def extract_gemini_urls(src: str) -> list[dict]:
    # Gemini's textContent doesn't have inline URL annotations; we'll
    # fall back to grepping for http(s):// in case any leaked through.
    urls = re.findall(r"https?://[^\s)\\]+", src)
    seen: set[str] = set()
    out: list[dict] = []
    for u in urls:
        u = u.rstrip(".,;:")
        if u in seen:
            continue
        seen.add(u)
        out.append({"title": urlparse(u).netloc, "url": u})
    return out


def fetch_url(url: str, timeout: float = 20.0) -> tuple[int, str]:
    """Best-effort fetch. Returns (status_code, text). Text capped at
    20K chars. Status 0 = failed before HTTP."""
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
            body = r.read(2_000_000).decode("utf-8", errors="replace")
            # Strip HTML tags crudely
            body = re.sub(r"<script[^>]*>.*?</script>", " ", body, flags=re.DOTALL | re.IGNORECASE)
            body = re.sub(r"<style[^>]*>.*?</style>", " ", body, flags=re.DOTALL | re.IGNORECASE)
            body = re.sub(r"<[^>]+>", " ", body)
            body = re.sub(r"\s+", " ", body).strip()
            return r.status, body[:20_000]
    except urllib.error.HTTPError as e:
        return e.code, f"HTTP {e.code}: {e.reason}"
    except Exception as e:
        return 0, f"FETCH ERROR: {type(e).__name__}: {e}"


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    out_dir = Path(".codex/I-eval-004")
    out_dir.mkdir(parents=True, exist_ok=True)

    for label, src_path, extract_fn in [
        ("chatgpt", "state/compare_chatgpt_q1.md", extract_chatgpt_urls),
        ("gemini", "state/compare_gemini_q1.md", extract_gemini_urls),
    ]:
        src = Path(src_path).read_text(encoding="utf-8")
        urls = extract_fn(src)
        print(f"[{label}] {len(urls)} unique cited URLs")
        pool: list[dict] = []
        for i, u in enumerate(urls):
            print(f"  [{i+1}/{len(urls)}] {u['url'][:80]}", flush=True)
            status, content = fetch_url(u["url"])
            pool.append({
                "evidence_id": f"{label[:2]}_ev_{i:03d}",
                "title": u["title"],
                "url": u["url"],
                "status_code": status,
                "content": content,
                "content_length": len(content),
            })
            # tiny politeness delay
            time.sleep(0.4)
        out = out_dir / f"{label}_q1_source_content_pool.json"
        out.write_text(json.dumps(pool, ensure_ascii=False, indent=2), encoding="utf-8")
        ok = sum(1 for p in pool if 200 <= p["status_code"] < 300)
        print(f"[{label}] saved {out}: {ok}/{len(pool)} OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
