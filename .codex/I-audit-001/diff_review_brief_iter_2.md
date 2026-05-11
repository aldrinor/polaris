```
HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

# I-audit-001 — DIFF review iter 2

## Output schema (binding)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

## Iter-1 P1 fix recap

Iter-1 P1: present-but-empty pool entry yielded PARTIAL not UNREACHABLE
(silent fallback). Fixed at `scripts/run_line_by_line_audit.py` in the
`_load_sentences_with_resolved_citations` loop: when `entry.get("direct_quote", "")`
is empty, route through the same sentinel pattern as unresolved-[N] —
synthesize token with `__empty_text_<ev_id>__` ev_id that is guaranteed
absent from the pool, so audit_sentence's `unknown_evidence_id` short-
circuit fires and returns UNREACHABLE with diagnostic reason.

New test `test_resolved_ev_id_present_but_empty_text_yields_unreachable`
exercises this. Asserts UNREACHABLE count + PARTIAL count == 0 + alert=True
+ reason contains `__empty_text_ev_a__`.

## Diff

Read `.codex/I-audit-001/codex_diff.patch` (766 lines, 2 files).

## Test results

```
$ python -m pytest tests/scripts/test_run_line_by_line_audit.py -v
==================== 28 passed in 4.03s =====================
```

(17 pre-existing + 11 new resolved-mode tests including the iter-1 fix.)

## What changed since iter-1 diff submission

```diff
+            if not span_text:
+                # I-audit-001 diff iter-1 P1 fix: pool entry exists but
+                # its normalized evidence text is empty (broken
+                # substrate). MUST fail loudly as UNREACHABLE, not
+                # silently degrade to PARTIAL via the empty-span
+                # content-check path. Route through the same sentinel
+                # pattern as unresolved citation nums: synthesize an
+                # ev_id guaranteed missing from the pool.
+                tokens.append(f"[#ev:__empty_text_{ev_id}__:0-0]")
+                continue
```

Plus one test added.

## Open questions

Iter-1 sandbox could not run pytest due to PermissionError on temp dirs.
The test suite runs cleanly in my local environment: 28/28 pass. Codex
should verify by reading the test bodies + the SUT side-by-side.
