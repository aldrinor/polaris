Diff review for GH#429 I-eval-003 — Tier-1 v2 audit enumerator. Output YAML.

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# Diff scope

`scripts/enumerate_tier1_claims.py` (+33 LOC, −7 LOC):

1. Drop the 600-char truncation on `direct_quote` (the iter-1 P1 — supporting figures appearing later in 1.5K-9K char captured quotes were being clipped, producing false UNSUPPORTED verdicts).

2. Surface `missing_biblio_nums` when a cited [N] token has no corresponding bibliography entry, rather than silently dropping (iter-1 P2-2).

3. YAML emitter writes the new `missing_biblio_nums` field when present.

The behavioural change is contained to two functions: `build_enumeration` and `emit_yaml`. No other production code touched. The script is run offline by the audit pipeline; not on a hot path.

# Empirical impact

Re-enumeration produced same claim counts (Q1=31, Q2=46, Q3=61, Q4=51) confirming sentence-extraction logic unchanged. Codex iter-2 audit of 29 batches across Q1-Q4 returned 178V/11P/0U (94% V) vs iter-1's 34V/46P/109U (18% V). Aggregate corrected from "50% UNSUPPORTED" tooling artifact to "93% VERIFIED" real audit signal.

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
