"""Enumerate audit-grade claims from competitor (ChatGPT / Gemini) DR
outputs. Both use prose-with-inline-URL style citations rather than
POLARIS's [N]+bibliography. We extract:

  - Sentences containing at least one numeric fact (decimal, %, $, year),
    OR sentences containing an inline URL annotation
  - The most-proximate URL or citation_id

Saves YAML in the same Tier-1 v2 schema used for POLARIS.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path


# ChatGPT inline url marker: url<title><url>
# Decoded form (after JSON unescape): "urlAmazon Web Serviceshttps://aws.amazon.com"
# Both providers use Latin-1 private-use chars U+E200/E201/E202 as delimiters
CHATGPT_URL_PATTERN = re.compile(
    r"[\\]+ue200url[\\]+ue202([^\\]+?)[\\]+ue202(https?://[^\\\s]+?)[\\]+ue201",
    re.IGNORECASE,
)
CHATGPT_CITE_PATTERN = re.compile(
    r"[\\]+ue200cite[\\]+ue202([^\\]+?)[\\]+ue201",
    re.IGNORECASE,
)

# Numeric/fact-bearing patterns
NUMERIC_PATTERN = re.compile(
    r"(?:US\$|CAD\$?|\$|€|£)\s?\d[\d,\.]*(?:\s?(?:[KMB]illion|[kmb]illion|trillion|[KMBTkmbt]))?"
    r"|\d+\.\d+%"
    r"|\d{4}-\d{2,4}"
    r"|\b(?:19|20)\d{2}\b"
    r"|\b\d+%"
    r"|\b\d+\s?(?:GB|TB|MB|GW|MW|kW|kWh|MWh)\b"
    r"|\b\d{3,}\s+(?:GPUs?|servers?)"
)

# Sentence splitter — handles the corrupted whitespace + escaped-newline mess
def split_sentences(text: str) -> list[str]:
    # Normalize escaped newlines that survived the JSON unescape
    text = text.replace("\\\\n", " ").replace("\\n", " ")
    text = re.sub(r"\s+", " ", text)
    # Split on .|!|? followed by space + capital
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z\[])", text)
    return [p.strip() for p in parts if p.strip()]


def enumerate_chatgpt(src: str, prefix: str) -> list[dict]:
    sentences = split_sentences(src)
    claims: list[dict] = []
    cidx = 0
    for s in sentences:
        # Strip the ChatGPT inline annotations to get a cleaner sentence
        urls = CHATGPT_URL_PATTERN.findall(s)
        cites = CHATGPT_CITE_PATTERN.findall(s)
        has_numeric = bool(NUMERIC_PATTERN.search(s))
        # Keep claims with EITHER a citation OR numeric content
        if not (urls or cites or has_numeric):
            continue
        # Clean the sentence
        clean = CHATGPT_URL_PATTERN.sub(lambda m: m.group(1), s)
        clean = CHATGPT_CITE_PATTERN.sub("", clean)
        clean = re.sub(r"\s+", " ", clean).strip()
        if len(clean) < 30:
            continue
        cidx += 1
        claims.append({
            "claim_id": f"{prefix}-T1-{cidx:03d}",
            "sentence": clean,
            "cited_urls": [{"title": t, "url": u} for t, u in urls],
            "cited_turn_ids": cites,
            "has_numeric_fact": has_numeric,
        })
    return claims


def enumerate_gemini(src: str, prefix: str) -> list[dict]:
    # Gemini's textContent has citations rendered very differently.
    # Citations appear inline as superscripts that got dropped in textContent.
    # We extract sentences with numeric fact and let Codex audit them
    # against the URL list from the Sources section if present.
    sentences = split_sentences(src)
    claims: list[dict] = []
    cidx = 0
    for s in sentences:
        if not NUMERIC_PATTERN.search(s):
            continue
        if len(s) < 30:
            continue
        # Skip the boilerplate
        if s.startswith("I've completed your research"):
            continue
        cidx += 1
        claims.append({
            "claim_id": f"{prefix}-T1-{cidx:03d}",
            "sentence": s.strip(),
            "cited_urls": [],
            "has_numeric_fact": True,
        })
    return claims


def emit_yaml(claims: list[dict], header: str, out: Path) -> None:
    lines = [f"# {header}", f"# Total claims: {len(claims)}", ""]
    lines.append("schema_version: tier1_v2_competitor")
    lines.append("claims:")
    for c in claims:
        lines.append(f"  - claim_id: {c['claim_id']}")
        lines.append(f"    sentence: {json.dumps(c['sentence'])}")
        if c.get("cited_urls"):
            lines.append("    cited_urls:")
            for ev in c["cited_urls"]:
                lines.append(f"      - title: {json.dumps(ev['title'])}")
                lines.append(f"        url: {json.dumps(ev['url'])}")
        if c.get("cited_turn_ids"):
            lines.append(f"    cited_turn_ids: {json.dumps(c['cited_turn_ids'])}")
        lines.append(f"    has_numeric_fact: {str(c.get('has_numeric_fact', False)).lower()}")
        lines.append("")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    chatgpt_src = Path("state/compare_chatgpt_q1.md").read_text(encoding="utf-8")
    gemini_src = Path("state/compare_gemini_q1.md").read_text(encoding="utf-8")
    chat_claims = enumerate_chatgpt(chatgpt_src, "CG-Q1")
    gem_claims = enumerate_gemini(gemini_src, "GM-Q1")
    print(f"ChatGPT claims: {len(chat_claims)}")
    print(f"Gemini claims: {len(gem_claims)}")
    emit_yaml(chat_claims, "ChatGPT DR Q1 Tier-1 v2 enumeration", Path(".codex/I-beat-001/chatgpt_q1_claims_enumeration.yaml"))
    emit_yaml(gem_claims, "Gemini DR Q1 Tier-1 v2 enumeration", Path(".codex/I-beat-001/gemini_q1_claims_enumeration.yaml"))
    print("yaml saved")
    return 0


if __name__ == "__main__":
    sys.exit(main())
