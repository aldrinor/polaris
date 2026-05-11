# Tier-1 v2 audit verdict distribution — Q1-Q5 + tirzepatide-pending

Per CLAUDE.md §-1.1 line-by-line standard, every claim audited claim-by-claim against the full cited direct_quote span (typically 1.5K-9K chars per evidence_id) captured in the report's `evidence_pool.json`.

**Critical correction:** The first pass of this audit (iter 1) truncated `direct_quote` to 600 chars and produced a 50% UNSUPPORTED aggregate. Codex iter-1 brief review caught the truncation bug (P1: `scripts/enumerate_tier1_claims.py:114-123 slices span_text to 600 chars`). Iter 2 re-runs with full direct_quote spans and inverts the picture: POLARIS verified-findings claims verify against their cited spans at 93% across Q1-Q5.

## Codex per-report verdict totals (full-span audit, iter 2)

| Report | Domain | Claims | VERIFIED | PARTIAL | UNSUPPORTED | %V |
|---|---|---:|---:|---:|---:|---:|
| Q1 | ai_sovereignty | 31 | 30 | 1 | 0 | 96.8% |
| Q2 | canada_us / CUSMA | 46 | 38 | 8 | 0 | 82.6% |
| Q3 | workforce / GenAI | 61 | 60 | 1 | 0 | 98.4% |
| Q4 | policy / housing | 51 | 50 | 1 | 0 | 98.0% |
| Q5 | policy / Pharmacare (PR #421 pilot) | 28 | 24 | 4 | 0 | 85.7% |
| **TOTAL** | | **217** | **202** | **15** | **0** | **93.1%** |

## Headline finding

POLARIS verified-findings claims verify against their cited evidence_pool direct_quote spans at 93.1% across all 5 BEAT-BOTH reports. Zero FABRICATED, zero UNSUPPORTED.

Q2 (CUSMA / canada_us) is the lowest at 82.6% V; the 8 PARTIAL there cluster on figures where the span is on-topic and broadly consistent but the specific decimal/year only appears in adjacent sentences not captured in the direct_quote field.

## Iter-1 → iter-2 verdict shift (Codex P1 fix)

| Report | Iter-1 V (truncated) | Iter-1 U (truncated) | Iter-2 V (full span) | Iter-2 U (full span) | Delta-V | Delta-U |
|---|---:|---:|---:|---:|---:|---:|
| Q1 | 8 (26%) | 13 (42%) | 30 (97%) | 0 (0%) | +22 | −13 |
| Q2 | 3 (7%) | 28 (61%) | 38 (83%) | 0 (0%) | +35 | −28 |
| Q3 | 11 (18%) | 38 (62%) | 60 (98%) | 0 (0%) | +49 | −38 |
| Q4 | 12 (24%) | 30 (59%) | 50 (98%) | 0 (0%) | +38 | −30 |
| **TOTAL Q1-Q4** | **34 (18%)** | **109 (58%)** | **178 (94%)** | **0 (0%)** | **+144** | **−109** |

Iter-1 audit was tooling-bounded, not POLARIS-bounded. The 600-char truncation in the enumerator removed the supporting context that POLARIS's strict_verify NLI gate had access to. With the audit operating on the same span POLARIS verified against, claims overwhelmingly hold.

## Method (iter-2)

1. `scripts/enumerate_tier1_claims.py` parses each report's verified-findings sections (truncated at Analyst Synthesis marker) and emits Tier-1 v2 YAML records keyed by sentence-with-citations.
2. Each `[N]` is resolved through `bibliography.json` to its `evidence_id`, then to its FULL `direct_quote` field from `evidence_pool.json` — no truncation.
3. Codex `exec` audits each claim against its cited spans, populating `claim_type`, `materiality`, `citation_context_match`, `verdict`, `rationale`, `reviewer_confidence`.
4. Batches of ≤7 claims to keep individual Codex runs under ~60s; 29 batches total across Q1-Q4.

## §-1.1 alignment

- **Line-by-line:** 217/217 claims audited claim-by-claim by Codex. No sampling.
- **Both Claude AND Codex:** Codex pass is complete for 217 claims (Q1-Q4 in this PR; Q5 in PR #421). Claude's independent parallel pass is complete only for Q5 (28 claims) per PR #421. Claude independent pass on Q1-Q4 is the remaining §-1.1 gap to close in a follow-up Issue.
- **Industrial frameworks:** Codex prompt enforces PRISMA/AMSTAR-2-aligned `claim_type` × `materiality` × `citation_context_match` taxonomy. No string-presence shortcut, no metadata framing.
- **Banned shortcuts:** no metadata comparison, no word/citation counts, no pattern presence, no sample-based audit, no string-presence PASS/FAIL.

## Per-batch verdict detail (iter 2)

### Q1 — 31 claims, 5 batches
- B1 (7): 7V / 0P / 0U
- B2 (7): 7V / 0P / 0U
- B3 (7): 7V / 0P / 0U
- B4 (7): 6V / 1P / 0U
- B5 (3): 3V / 0P / 0U

### Q2 — 46 claims, 7 batches
- B1 (7): 6V / 1P / 0U
- B2 (7): 5V / 2P / 0U
- B3 (7): 6V / 1P / 0U
- B4 (7): 4V / 3P / 0U
- B5 (7): 6V / 1P / 0U
- B6 (7): 7V / 0P / 0U
- B7 (4): 4V / 0P / 0U

### Q3 — 61 claims, 9 batches
- B1 (7): 7V / 0P / 0U
- B2 (7): 7V / 0P / 0U
- B3 (7): 7V / 0P / 0U
- B4 (7): 7V / 0P / 0U
- B5 (7): 7V / 0P / 0U
- B6 (7): 7V / 0P / 0U
- B7 (7): 7V / 0P / 0U
- B8 (7): 6V / 1P / 0U
- B9 (5): 5V / 0P / 0U

### Q4 — 51 claims, 8 batches
- B1 (7): 7V / 0P / 0U
- B2 (7): 7V / 0P / 0U
- B3 (7): 7V / 0P / 0U
- B4 (7): 7V / 0P / 0U
- B5 (7): 7V / 0P / 0U
- B6 (7): 7V / 0P / 0U
- B7 (7): 7V / 0P / 0U
- B8 (2): 1V / 1P / 0U

## Status

GH#429 (I-eval-003) Tier-1 v2 audit pass on Q1-Q4: Codex side COMPLETE with full direct_quote spans (29 iter-2 batches across 4 reports). Aggregate 178V/11P/0U on Q1-Q4 (94% V). Combined with Q5 (PR #421): 202V/15P/0U across 217 claims (93% V). Claude independent pass + cross-review reconciliation for Q1-Q4 INCOMPLETE — only Q5 has paired Claude pass. Tirzepatide triple still pending per GH#403.
