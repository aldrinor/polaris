Brief review for GH#429 I-eval-003 — Tier-1 v2 audit extension to Q1-Q4. Output YAML.

HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# Iter-1 P1 RESOLVED — direct_quote no longer truncated

You caught (iter 1): `scripts/enumerate_tier1_claims.py:114-123 slices span_text to 600 chars` → Q1-T1-003 ($2B Budget 2024) and Q4-T1-011 (0.6%/$2.7-4.3B/$1.6B) marked UNSUPPORTED because the supporting figure appeared later in the captured direct_quote.

Fix: dropped truncation. `direct_quote` is now passed through unchanged (typically 1.5K-9K chars per evidence_id per the four evidence_pool.json files in the four reports).

# Iter-1 P2 also addressed

P2-2 (silent drop of missing bibliography citations): the enumerator now surfaces them in a `missing_biblio_nums` field on the claim record so downstream audit can flag dangling [N] tokens explicitly.

P2-1 (raw Codex CLI transcript output) is acknowledged but not fixed in this PR; the per-batch summaries we parse via grep already give the canonical aggregate. A normalize-to-clean-YAML pass is a Tier-1 v3 follow-up.

# Iter-2 verdict distribution (29 re-run Codex batches across Q1-Q4)

| Report | Claims | VERIFIED | PARTIAL | UNSUPPORTED | %V |
|---|---:|---:|---:|---:|---:|
| Q1 ai_sovereignty | 31 | 30 | 1 | 0 | 96.8% |
| Q2 canada_us | 46 | 38 | 8 | 0 | 82.6% |
| Q3 workforce | 61 | 60 | 1 | 0 | 98.4% |
| Q4 housing | 51 | 50 | 1 | 0 | 98.0% |
| **Q1-Q4 total** | **189** | **178** | **11** | **0** | **94.2%** |
| Q5 (PR #421) | 28 | 24 | 4 | 0 | 85.7% |
| **Q1-Q5 total** | **217** | **202** | **15** | **0** | **93.1%** |

Iter-1 (truncated) -> iter-2 (full span) shift on Q1-Q4: V 18% → 94%; U 58% → 0%. The iter-1 50% UNSUPPORTED was a tooling artifact.

# Deliverables in this PR

1. `scripts/enumerate_tier1_claims.py`: full-span enumeration with missing-citation surfacing.
2. `.codex/I-eval-003/q{1..4}_claims_enumeration.yaml`: 189 audit-grade claims.
3. `.codex/I-eval-003/codex_q{1..4}_batch_{N}_output.txt`: 29 iter-2 Codex batches with full-span verdicts.
4. `.codex/I-eval-003/aggregate_verdict_distribution.md`: corrected aggregate + iter-1→iter-2 delta table.

# §-1.1 alignment

- Line-by-line: 217/217 claims audited by Codex against full direct_quote.
- Both Claude AND Codex: Codex side complete for 217 claims. Claude independent pass complete for Q5 only (PR #421). Claude pass on Q1-Q4 = remaining §-1.1 gap.
- Banned shortcuts: none used.

# Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
