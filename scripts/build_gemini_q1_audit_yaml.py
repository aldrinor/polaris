"""Build Gemini Q1 §-1.1 audit YAML: enumerate claims, map each to
candidate-supporting URLs by numeric-token overlap, embed top candidate
contents inline so Codex can do per-claim line-by-line check."""
import json
import re
from pathlib import Path

REPORT_SRC = Path("state/compare_gemini_q1.md")
POOL_PATH = Path(".codex/I-eval-004/gemini_q1_source_content_pool.json")

NUMERIC_PAT = re.compile(
    r"(?:US\$|CAD\$|C\$|\$)\s?\d[\d,\.]*(?:\s?(?:billion|million|Bn|M))?"
    r"|\b\d+\.?\d*%"
    r"|\b\d+(?:\.\d+)?\s?(?:gigawatts?|GW|megawatts?|MW|kW|MWh|kWh|TWh)\b"
    r"|\b(?:202[0-9]|201[5-9])\b"
    r"|\b\d{1,3}(?:,\d{3})+\b"
    r"|\b\d+\s?(?:billion|million)\b",
    re.IGNORECASE,
)


def split_sentences(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text)
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z\[])", text)
    return [p.strip() for p in parts if p.strip()]


def numeric_tokens(text: str) -> set[str]:
    out = set()
    for m in NUMERIC_PAT.finditer(text):
        out.add(m.group(0))
    return out


def main():
    src = REPORT_SRC.read_text(encoding="utf-8")
    # Strip the markdown header
    src = re.sub(r"^#.*$", "", src, count=2, flags=re.MULTILINE)
    sentences = split_sentences(src)
    claims = []
    for s in sentences:
        if len(s) < 40:
            continue
        if s.startswith("I've completed your research"):
            continue
        toks = numeric_tokens(s)
        if not toks:
            continue
        claims.append({"sentence": s, "tokens": list(toks)})
    print(f"audit-grade claims: {len(claims)}")

    pool = json.load(open(POOL_PATH, encoding="utf-8"))
    pool_ok = [p for p in pool if 200 <= p.get("status_code", 0) < 300]
    print(f"source pool OK: {len(pool_ok)}")

    out = {"schema_version": "tier1_v2_with_substrate", "report": str(REPORT_SRC), "claims": []}
    for i, c in enumerate(claims, 1):
        cid = f"GM-Q1-T1-{i:03d}"
        candidates = []
        for p in pool_ok:
            hits = [t for t in c["tokens"] if t.lower() in p["content"].lower()]
            if hits:
                candidates.append({
                    "evidence_id": p["evidence_id"],
                    "url": p["url"],
                    "anchor_text": p.get("anchor_text", "")[:120],
                    "matching_tokens": hits,
                    "content_excerpt": p["content"][:3000],  # cap to keep YAML manageable
                })
        candidates.sort(key=lambda x: -len(x["matching_tokens"]))
        out["claims"].append({
            "claim_id": cid,
            "sentence": c["sentence"],
            "numeric_tokens": c["tokens"],
            "candidate_sources": candidates[:3],  # top 3 candidates by token-match
            "no_candidates": len(candidates) == 0,
        })
    out_path = Path(".codex/I-eval-004/gemini_q1_audit_ready.json")
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    n_with = sum(1 for c in out["claims"] if not c["no_candidates"])
    print(f"saved {out_path}: {len(out['claims'])} claims, {n_with} with >=1 candidate")


if __name__ == "__main__":
    main()
