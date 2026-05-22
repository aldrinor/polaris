# Codex DIFF review — I-p2-010 (#749): contradiction / refusal panel

HARD ITERATION CAP: 5. iter 1. APPROVE iff zero P0/P1 (code + design rubric, esp. HONESTY framing). Final line MERGE AUTHORIZED if mergeable. Canonical-diff-sha256 `bc6f4efc7e04f9e24a006ac83871ed918bd418d40f8fc9305caee60518b94246`. web/ only. Display component; visual verifies in-context at #759/#756.

## Diff (contradiction_panel.tsx)
- RefusalCard: maps abort_scope_rejected/corpus_inadequate/corpus_approval_denied/no_verified_sections → honest reason; unknown abort_* → "Declined — see run status" (no fabricated reason); refusal-neutral tokens (NOT alarming red); "by design — refuses rather than fabricating".
- ContradictionCard: real ContradictionSignal fields (disagreeing_source_count, kind, summary, sides[]: source_tier, source_id, jurisdiction?, claim_excerpt). amber contradiction tokens.
- Empty state when neither present.

## Review focus
1. HONESTY: refusal mapping faithful + unknown-fallback non-fabricated; refusal framed as feature (calm, not alarming); contradiction uses only real fields?
2. tokens (contradiction amber / refusal neutral, AA); a11y (TriangleAlert aria-hidden, list semantics)?
3. Any P0/P1.

## Output schema
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
merge_decision: MERGE AUTHORIZED | DO NOT MERGE
```
