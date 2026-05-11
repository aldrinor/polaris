"""For each Gemini Q1 claim, find candidate-supporting sources by content
overlap. Numeric tokens (decimals, dollars, years) in the claim must
appear in the source content. Saves a per-claim candidate list for the
Tier-1 v2 audit."""
import json
import re
from pathlib import Path


def extract_numeric_tokens(text: str) -> set[str]:
    """Extract distinctive factual tokens: percentages, dollar amounts, years, large numbers."""
    tokens = set()
    # Percentages and decimals with %
    tokens.update(re.findall(r"\b\d+\.?\d*%", text))
    # Dollar amounts with currency prefix
    tokens.update(re.findall(r"(?:US\$|CAD\$|\$|US\$|C\$)\s?\d[\d,\.]*(?:\s?(?:[Bb]illion|[Mm]illion))?", text))
    tokens.update(re.findall(r"\d+(?:\.\d+)?\s?(?:billion|million|GW|MW|kW|MWh|kWh)", text, re.IGNORECASE))
    # Years 2020-2030
    tokens.update(re.findall(r"\b(?:202[0-9]|201[5-9])\b", text))
    # Distinctive large numbers (3+ digits with commas)
    tokens.update(re.findall(r"\b\d{1,3}(?:,\d{3})+\b", text))
    return tokens


def main():
    pool = json.load(open(".codex/I-eval-004/gemini_q1_source_content_pool.json", encoding="utf-8"))
    pool_ok = [p for p in pool if 200 <= p.get("status_code", 0) < 300]
    print(f"pool entries with OK status: {len(pool_ok)}")

    # Load claims from previous enumeration
    enum_path = ".codex/I-beat-001/gemini_q1_claims_enumeration.yaml"
    text = Path(enum_path).read_text(encoding="utf-8")
    # Parse claim_id + sentence pairs via regex
    pat = re.compile(r"^  - claim_id: (\S+)\n    sentence: (.+?)\n", re.MULTILINE | re.DOTALL)
    claims = []
    for m in re.finditer(r'^  - claim_id: (\S+)\n    sentence: (".*?")\n', text, re.MULTILINE | re.DOTALL):
        cid = m.group(1)
        # JSON-decode sentence
        try:
            sentence = json.loads(m.group(2))
        except Exception:
            sentence = m.group(2).strip('"')
        claims.append({"claim_id": cid, "sentence": sentence})
    print(f"claims: {len(claims)}")

    # For each claim, find candidate URLs
    out = []
    for c in claims:
        tokens = extract_numeric_tokens(c["sentence"])
        candidates = []
        if tokens:
            for p in pool_ok:
                hits = sum(1 for t in tokens if t in p["content"])
                if hits > 0:
                    candidates.append({
                        "evidence_id": p["evidence_id"],
                        "url": p["url"],
                        "matching_tokens": hits,
                        "anchor_text": p.get("anchor_text", "")[:80],
                    })
            candidates.sort(key=lambda x: -x["matching_tokens"])
        out.append({
            "claim_id": c["claim_id"],
            "sentence": c["sentence"],
            "numeric_tokens": list(tokens),
            "candidate_sources_top5": candidates[:5],
            "total_candidates": len(candidates),
        })

    out_path = Path(".codex/I-eval-004/gemini_q1_claim_source_map.json")
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved {out_path}")
    no_candidates = sum(1 for c in out if c["total_candidates"] == 0)
    print(f"claims with 0 candidates: {no_candidates}")
    print(f"claims with >=1 candidate: {len(out) - no_candidates}")


if __name__ == "__main__":
    main()
