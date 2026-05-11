Independent Tier-1 audit of 28 Q5 Pharmacare claims. Output YAML only.

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.

# Task

For EACH of the 28 claims in `.codex/I-eval-002/q5_claims_enumeration.yaml`, independently populate the Tier-1 audit schema (joint Claude+Codex approved, see `.codex/GH400/codex_dr_eval_review_output.txt` ENDORSE_WITH_AMENDMENTS verdict).

Read the enumeration file via PowerShell `Get-Content` if needed. Each claim has:
- claim_id, section, sentence
- cited_evidence with evidence_id, bibliography_num, url, tier, span, title, **span_text** (the actual cited content)

This is **independent** of Claude's pass. Do NOT look at Claude's verdicts file. Use only the enumeration + your own web-search verification + the cited span_text.

# Tier-1 fields to fill per claim

For each claim, emit one record:

```yaml
- claim_id: Q5-T1-NNN
  claim_type: efficacy | safety | diagnostic | dosing | regulatory | mechanism | epidemiology | economic | guideline | background
  materiality: critical | major | minor | background
  citation_context_match: yes | partial | no
  # Does the span_text actually support the claim's specific assertion?
  # yes = span explicitly supports the decimal/range/year/percentage
  # partial = span is on-topic and consistent but doesn't have the exact decimal
  # no = span is about something else, or the decimal/year mismatches
  verdict: VERIFIED | PARTIAL | UNSUPPORTED | FABRICATED | UNREACHABLE
  rationale: "one sentence with the specific support or gap from the span_text"
  reviewer_confidence: 0.0 - 1.0
  # 1.0 = certain after reading span_text
  # 0.7-0.9 = confident but couldn't fully verify decimal
  # < 0.7 = uncertain, flag for human review (deferral)
```

# Decision rules

- **claim_type**: pick the dominant type. "Economic" for cost/savings/spending claims. "Regulatory" for legislative-status claims. "Epidemiology" for population-rate claims. "Background" for context/setup statements.
- **materiality**: 
  - critical = clinical-decision-grade (drug dose, contraindication, safety signal) — N/A for pharmacare; use for safety claims if any
  - major = fiscal-policy-grade or regulatory-status (e.g., Bill C-64 passage date, $11.2B incremental cost)
  - minor = supporting context decimal that policy decision would not turn on
  - background = setup/framing
- **citation_context_match**: read span_text carefully. The decimal in the claim must appear in (or be straightforwardly derivable from) the span_text for `yes`. Off-topic span = `no`.
- **verdict**: weighted by context_match + your independent web check.
- **reviewer_confidence < 0.7 → deferred_to_human**.

# Banned shortcuts

- DO NOT pattern-match on tier or URL alone — read the span_text and assess against claim.
- DO NOT auto-VERIFIED just because span exists. The span must SUPPORT the specific assertion.
- DO NOT skip claims. All 28 must have records.

# Output

Single YAML block. List of 28 records in claim_id order. After the list, add a summary block:

```yaml
codex_summary:
  total_claims: 28
  per_verdict:
    VERIFIED: N
    PARTIAL: N
    UNSUPPORTED: N
    FABRICATED: N
    UNREACHABLE: N
  per_materiality:
    critical: N
    major: N
    minor: N
    background: N
  per_context_match:
    yes: N
    partial: N
    no: N
  deferral_count: N  # reviewer_confidence < 0.7
  mean_reviewer_confidence: 0.0 - 1.0
  notable_findings:
    - claim_id: ...
      finding: "..."
  estimated_minutes_per_claim: N
```

Output the YAML directly. No commentary outside.
