"""Auto-responder for PageSummaryBatch requests in the loopback queue.

The agentic search loop asks for per-page research notes (url, title, summary,
perspectives, key_facts, knowledge_contribution) across 6 pages per batch.
For loopback validation, quality isn't the goal — pipeline progression is.

Heuristic extraction:
- Parse prompt by "--- PAGE: <title> ---" + "URL: <url>" + "CONTENT:" blocks
- summary: first 3 substantive sentences (>=40 chars, <400 chars) = ~150-200 words
- key_facts: sentences with numbers/percentages/CI/SMD/technical terms (up to 5)
- perspectives: defaults to ["Scientific"] (agentic search derives perspective tags elsewhere)
- knowledge_contribution: one short sentence derived from the first fact

Handles only call_type == 'structured:PageSummaryBatch'. Other requests left alone.
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PENDING = ROOT / "loopback" / "pending"
RESPONSES = ROOT / "loopback" / "responses"

PAYWALL_PATTERNS = re.compile(
    r"INSUFFICIENT_CONTENT|captcha|403 (Forbidden|:)|Cloudflare|Performing security|"
    r"Database connection failed|Just a moment|Sign in|security verification",
    re.I,
)

QUANT_SIGNAL = re.compile(
    r"\d+\s*(%|kg|mg|mmHg|nm|ppm|GPa|MPa|mol|mmol|mL|L|g|IU|bp|years?|months?|weeks?|days?|hours?|participants|patients|adults|subjects)|"
    r"\b(SMD|MD|OR|RR|HR|CI|SD|95%|99%|p\s*[=<>]|n\s*=|r\s*=|R²)\b|"
    r"\b(19|20)\d{2}\b|"
    r"\b\d+\.\d+\b",
    re.I,
)


def parse_pages(prompt: str) -> list[dict]:
    """Split the prompt into per-page blocks: {url, title, content}."""
    # Split on page delimiter
    parts = re.split(r"^--- PAGE:\s*(.+?)\s*---\s*$", prompt, flags=re.MULTILINE)
    pages = []
    # parts[0] is preamble; then title, block, title, block, ...
    for i in range(1, len(parts), 2):
        title = parts[i].strip() if i < len(parts) else ""
        body = parts[i + 1] if i + 1 < len(parts) else ""
        m_url = re.search(r"^URL:\s*(\S+)", body, re.MULTILINE)
        url = m_url.group(1).strip() if m_url else ""
        m_content = re.search(r"^CONTENT:\s*\n(.*?)(?:\n---\s*PAGE:|\Z)", body, re.DOTALL | re.MULTILINE)
        content = m_content.group(1).strip() if m_content else body
        pages.append({"url": url, "title": title, "content": content})
    return pages


def build_note(page: dict) -> dict:
    content = page.get("content") or ""
    url = page.get("url") or ""
    title = page.get("title") or url[:80]

    real_content = re.sub(r"<[^>]+>", "", content)
    is_shell = len(real_content) < 400 or PAYWALL_PATTERNS.search(real_content[:2000]) is not None

    if is_shell:
        return {
            "url": url,
            "title": title,
            "summary": "INSUFFICIENT_CONTENT: page appears to be paywall/captcha/shell.",
            "perspectives": [],
            "key_facts": [],
            "knowledge_contribution": "",
        }

    sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z])", real_content[:10000])
    cleaned = [s.strip() for s in sentences if 40 <= len(s.strip()) <= 400]

    # Summary: first 3 substantive sentences, combined.
    summary_parts = cleaned[:3]
    summary = " ".join(summary_parts)[:1500]

    # Key facts: sentences with quantitative signal.
    facts = []
    for s in cleaned:
        if QUANT_SIGNAL.search(s):
            facts.append(s[:250])
        if len(facts) >= 5:
            break
    # If no quantitative sentences, fall back to 2-3 cleaned ones.
    if not facts:
        facts = [s[:250] for s in cleaned[:3]]

    contribution = (
        f"Adds per-page evidence on the research topic: {facts[0][:140]}"
        if facts else "Provides background context."
    )

    return {
        "url": url,
        "title": title[:200],
        "summary": summary,
        "perspectives": ["Scientific"],
        "key_facts": facts,
        "knowledge_contribution": contribution,
    }


def try_handle(req_path: Path) -> bool:
    try:
        with req_path.open(encoding="utf-8") as f:
            req = json.load(f)
    except Exception:
        return False
    if req.get("call_type", "") != "structured:PageSummaryBatch":
        return False
    prompt = req.get("prompt", "") or ""
    pages = parse_pages(prompt)
    if not pages:
        return False
    notes = [build_note(p) for p in pages]
    result = {"notes": notes}
    req_id = req.get("request_id") or req_path.stem.replace("req_", "")
    resp_path = RESPONSES / f"resp_{req_id}.json"
    tmp = resp_path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(
            {"content": json.dumps(result, ensure_ascii=False),
             "input_tokens": len(prompt) // 4,
             "output_tokens": len(notes) * 100 + 50},
            f,
            ensure_ascii=False,
        )
    tmp.replace(resp_path)
    total_facts = sum(len(n["key_facts"]) for n in notes)
    print(f"  [auto-PAGESUMMARY] {req_path.name} -> {len(notes)} pages, {total_facts} facts total")
    return True


def main() -> int:
    handled_total = 0
    idle_polls = 0
    MAX_IDLE_POLLS = 1800
    while True:
        handled_this_cycle = 0
        for p in sorted(PENDING.glob("req_*.json")):
            try:
                if try_handle(p):
                    handled_this_cycle += 1
                    handled_total += 1
            except Exception as exc:  # noqa: BLE001
                print(f"  [auto-PAGESUMMARY] error on {p.name}: {exc}")
        if handled_this_cycle == 0:
            idle_polls += 1
            if idle_polls >= MAX_IDLE_POLLS:
                break
            time.sleep(1.0)
        else:
            idle_polls = 0
            time.sleep(0.5)
    print(f"[auto-PAGESUMMARY] drained {handled_total} page-summary batches")
    return 0


if __name__ == "__main__":
    sys.exit(main())
