# Codex round 4 — M-INT-5 v4

## Round-3 close
v3 had 1 MEDIUM (test stub didn't match production shape,
allowing tests to pass for wrong reason).

v4 fix (commit 438b699):
- Shape-compatible LiveRetrievalResult stub matching production:
  classified_sources, evidence_rows, total_candidates_pre_filter,
  candidates_kept_by_scope, candidates_kept_by_offtopic,
  candidates_fetched, candidates_failed_fetch, api_calls, notes
- Explicit `status != "error"` assertion so test fails loudly
  if any M-INT-4/5 path causes outer-fatal abort
- Both regression tests (malformed dict + helper raise) updated

Per Codex round-3 own statement:
> "With a shape-compatible retrieval stub, a direct probe
>  returned normal `fail_no_sources`, not `status="error"`,
>  when `_classify_scope_with_llm` raised
>  `RuntimeError("simulated classifier crash")`."

So the production HIGH fix was already real; v4 makes the
TEST prove it strongly.

## Round summary
- R1: 1 HIGH + 1 MEDIUM (dict KeyError abort, lost domain tag)
- R2: 1 HIGH + 1 MEDIUM (helper raise still escaped, weak test)
- R3: 1 MEDIUM (test stub shape too weak)
- R4: GREEN expected

## Acceptance bar
1-7 all met (re-verified each round)

## Tests
- 12/12 M-INT-5 with strengthened assertions
- 68/68 across M-INT-0a..5

Branch: PL-honest-rebuild-phase-1
Commit: 438b699

## Verdict expected
GREEN — round-3 MEDIUM closed via stronger test stub +
status != "error" assertion. Production fix already
verified by Codex in round-3.
