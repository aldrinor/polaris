# Codex Diff Review — I-bug-096 (judge-error telemetry counters)

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding.
- "Don't pick bone from egg" — reserve P0/P1 for real execution risks.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
- DO NOT call exec / rg / shell tools. Brief is self-contained.
```

## Pre-flight

- Brief APPROVE'd iter 1 (`.codex/I-bug-096/codex_brief_verdict.txt`)
- Diff: `.codex/I-bug-096/codex_diff.patch` (canonical-diff-sha256: `a83de66764bc9ac03b8eb84d2017b4659886e4a829f471c6cd163847d62db032`)
- 62 src LOC added (no production code reduction)
- 252 test LOC added (11 tests)
- 81 tests passing across the entailment-related suite (no regressions)

## Implementation matches your iter-1 brief

- ✅ Counter ownership: strict_verify-side (not judge-side) per your verdict
- ✅ Public `reset_judge_telemetry` per your verdict
- ✅ Explicit fixed-keys dict (`calls/entailed/neutral/contradicted/judge_error`) per your verdict
- ✅ Off-mode does NOT tick (cost discipline) per your verdict
- ✅ Helper normalizes judge fail-open into judge_error counter per your verdict ("Make the helper responsible for normalizing judge exceptions into the existing fail-open ENTAILED + judge_error result before counting, so swapped judges cannot bypass the judge_error counter.")

## The key invariant — judge_error vs entailed

The judge fail-open contract is `(verdict="ENTAILED", reason="judge_error: ExceptionClass")`. Without this PR, an operator polling logs would see all the WARNING lines but no concise "X% of gate calls in the last hour failed open." With this PR they can `get_judge_telemetry()` from a health endpoint or scripts/observability tooling and alert on `judge_error / calls > threshold`.

The pivotal test is `test_judge_error_increments_on_fail_open` — fail-open returns ENTAILED but counter ticks `judge_error`, NOT `entailed`. This is what distinguishes "gate accepted the sentence" from "gate failed open and we don't actually know."

## Tests pinned (11 total)

| Test | Behavior |
|---|---|
| `test_telemetry_starts_at_zero` | Fresh process → all 5 counters 0 |
| `test_calls_increments_on_each_judge_invocation` | 5 calls → calls=5 |
| `test_entailed_verdict_increments_entailed` | ENTAILED → entailed=1 |
| `test_neutral_verdict_increments_neutral` | NEUTRAL → neutral=1 |
| `test_contradicted_verdict_increments_contradicted` | CONTRADICTED → contradicted=1 |
| `test_judge_error_increments_on_fail_open` | fail-open ('ENTAILED', 'judge_error: ...') → judge_error=1, entailed=0 |
| `test_judge_error_distinct_from_entailed_in_mixed_run` | 4-call mixed run shows clear category separation |
| `test_off_mode_does_not_tick_calls` | Off mode = zero counters (cost discipline) |
| `test_get_judge_telemetry_returns_snapshot_not_live` | Mutating snapshot does NOT corrupt source |
| `test_reset_judge_telemetry_zeroes_all` | Reset puts all 5 back to 0 |
| `test_reset_judge_telemetry_is_public_callable` | Public name (not _underscore-prefixed) |

## What I want from you

1. **Verdict** APPROVE / REQUEST_CHANGES.
2. **Any P0/P1** — please be exhaustive iter 1.
3. **Snapshot semantics**: I return `dict(_JUDGE_TELEMETRY)` which copies the dict. Sufficient or do you want a frozen mapping (e.g. `MappingProxyType`)? My read: dict copy is enough; the test `test_get_judge_telemetry_returns_snapshot_not_live` proves mutations don't propagate.

## Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
