## §0 — HARD ITERATION CAP

```
HARD ITERATION CAP: 5. iter 1 of 5. Verdict APPROVE iff zero P0/P1.
```

GH#195 I-bench-002: paid sample evaluator scoring harness.

scripts/run_paid_evaluator_scoring.py + tests. Dry-run by default; --live invokes paid Layer-3 evaluator (GPT-5/Opus 4.7/Gemini 2.5 Pro etc.) per (sentence, span) pair using PRISMA/AMSTAR-2/GRADE rubric. 5 verdicts: VERIFIED/PARTIAL/UNSUPPORTED/FABRICATED/UNREACHABLE (matches CLAUDE.md §-1.1 + I-bakeoff-A-001 audit primitive).

Reuses scripts/run_line_by_line_audit.py primitives (`_normalize_pool`, `_PROVENANCE_TOKEN_RE`, `_split_sentences`) to extract (sentence, span) pairs from a delivered report+pool.

Live-mode requires --evaluator-endpoint/api-key/model. Dry-run emits PENDING stub placeholders so downstream pipeline integration can be verified without spend (Carney v6.2 Phase 0 Task 0.1 evaluator procurement is user-action-blocked).

9 tests pass. ~270 lines harness + ~85 lines tests.

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
