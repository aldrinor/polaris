"""Split Gemini Q1 audit-ready data into Codex batches of 7 claims."""
import json
from pathlib import Path

CODEX_BRIEF_TEMPLATE = """Tier-1 v2 §-1.1 line-by-line audit of Gemini Ultra DR Q1 claims. Output YAML only.

# Context

Auditing Gemini Ultra Deep Research output on Q1 "Canada sovereign frontier-LLM compute vs US hyperscalers for federal AI workloads 2026".
POLARIS comparison: 96.8% V on 31 claims via line-by-line audit vs captured spans.
Now auditing Gemini against ACTUAL cited URLs (harvested from live chat anchor tags, fetched, content excerpted).

# Audit instruction per claim

For each claim, check whether the candidate source content actually supports the claim:
- The specific decimal/dollar/year in the claim must be present in the candidate source content, OR the claim must be a faithful paraphrase of the source.

Tier-1 v2 schema per claim:
- claim_type: economic | regulatory | technical | comparative | geographical | epidemiology | background
- materiality: critical | major | minor | background
- citation_context_match: yes | partial | no | unverifiable
- verdict: VERIFIED | PARTIAL | UNSUPPORTED | FABRICATED | UNREACHABLE
- rationale: one sentence quoting/paraphrasing the supporting evidence text
- reviewer_confidence: 0.0-1.0

# Banned shortcuts

- Do NOT auto-VERIFIED just because a candidate is given. Read the content_excerpt and confirm the specific decimal/year appears.
- Flag UNSUPPORTED if the specific decimal/year in the claim is NOT in any candidate's content.

# Claims to audit (batch {batch_num}, {n_claims} claims)

{batch_json}

# Output schema

```yaml
records:
  - claim_id: GM-Q1-T1-XXX
    claim_type: ...
    materiality: ...
    citation_context_match: ...
    verdict: ...
    rationale: ...
    reviewer_confidence: ...
batch_summary:
  total: {n_claims}
  per_verdict: {{VERIFIED: N, PARTIAL: N, UNSUPPORTED: N, FABRICATED: N, UNREACHABLE: N}}
  per_context_match: {{yes: N, partial: N, no: N, unverifiable: N}}
```
"""


def main():
    data = json.load(open(".codex/I-eval-004/gemini_q1_audit_ready.json", encoding="utf-8"))
    claims = data["claims"]
    out_dir = Path(".codex/I-eval-004/codex_batches")
    out_dir.mkdir(parents=True, exist_ok=True)
    batches = [claims[i:i+7] for i in range(0, len(claims), 7)]
    print(f"{len(claims)} claims -> {len(batches)} batches")
    for n, batch in enumerate(batches, 1):
        # Trim content_excerpts to keep brief manageable
        compact = []
        for c in batch:
            cands = []
            for cand in c["candidate_sources"]:
                cands.append({
                    "evidence_id": cand["evidence_id"],
                    "url": cand["url"],
                    "matching_tokens": cand["matching_tokens"],
                    "content_excerpt": cand["content_excerpt"][:1500],
                })
            compact.append({
                "claim_id": c["claim_id"],
                "sentence": c["sentence"],
                "numeric_tokens": c["numeric_tokens"],
                "candidate_sources": cands,
            })
        brief = CODEX_BRIEF_TEMPLATE.format(
            batch_num=n,
            n_claims=len(batch),
            batch_json=json.dumps(compact, ensure_ascii=False, indent=2),
        )
        (out_dir / f"audit_brief_{n}.md").write_text(brief, encoding="utf-8")
        print(f"  batch {n}: {len(batch)} claims, brief size {len(brief)} chars")


if __name__ == "__main__":
    main()
