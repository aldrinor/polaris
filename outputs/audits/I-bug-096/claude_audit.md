# Claude Audit — I-bug-096 (judge-error telemetry counters)

**Date**: 2026-05-09
**Branch**: `bot/I-bug-096-judge-error-counters`
**Codex**: APPROVE on brief + diff iter 1, zero P0/P1, 1 P2 advisory acknowledged.

## What this fixes

Captures the **counters half** of Codex's P2 advisory on I-bug-092 diff review:

> "Persistent judge/config failures fail open even in enforce mode... Recommend telemetry/counters plus an env-gated live OpenRouter test."

Process-lifetime counters at `strict_verify._JUDGE_TELEMETRY` keyed `calls/entailed/neutral/contradicted/judge_error`. Public `get_judge_telemetry()` returns a dict snapshot; `reset_judge_telemetry()` zeroes for between-job windows.

The pivotal counter is `judge_error` — distinguishes "gate accepted the sentence" from "gate failed open and we don't actually know." Without this an operator polling logs sees WARNING noise but no concise rate signal; with this they can alert on `judge_error / calls > threshold`.

## Per Codex iter-1 brief

- ✅ Counter ownership strict_verify-side
- ✅ Public `reset_judge_telemetry`
- ✅ Explicit fixed-keys dict
- ✅ Off-mode does NOT tick (cost discipline)
- ✅ Helper normalizes judge fail-open into judge_error counter

## Per Codex iter-1 diff verdict

- 0 P0, 0 P1
- 1 P2: "Concurrent calls/resets/snapshots are unsynchronized — add a small lock later if these counters become alert-critical in concurrent workers." Acknowledged. Not adding `threading.Lock` in this PR.
- Confirmed `dict(_JUDGE_TELEMETRY)` snapshot semantics sufficient (rejected my MappingProxyType question).

## Tests (11)

`test_telemetry_starts_at_zero`, `test_calls_increments_on_each_judge_invocation`, `test_entailed_verdict_increments_entailed`, `test_neutral_verdict_increments_neutral`, `test_contradicted_verdict_increments_contradicted`, `test_judge_error_increments_on_fail_open`, `test_judge_error_distinct_from_entailed_in_mixed_run`, `test_off_mode_does_not_tick_calls`, `test_get_judge_telemetry_returns_snapshot_not_live`, `test_reset_judge_telemetry_zeroes_all`, `test_reset_judge_telemetry_is_public_callable`.

81 passing across the entailment-related test suite (no regressions).

## Definition-of-done

- [x] 11 new tests + 70 baseline = 81 passing
- [x] Codex APPROVE on brief + diff iter 1
- [x] canonical-diff-sha256 = `a83de66764bc9ac03b8eb84d2017b4659886e4a829f471c6cd163847d62db032`
- [ ] CI green
- [ ] Auto-merge per Plan §7.B LOCKED B1
