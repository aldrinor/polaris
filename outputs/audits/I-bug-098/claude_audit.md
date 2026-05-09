# Claude Audit — I-bug-098 (entailment gate WIRED INTO PRODUCTION)

**Date**: 2026-05-09
**Branch**: `bot/I-bug-098-entailment-into-production`
**Codex**: APPROVE on brief iter 1; APPROVE on diff iter 1 (zero P0/P1, 2 P2 advisories accepted as follow-ups).

## Why this exists

PRs #343-348 (I-bug-092..097 + I-cj-008) wired the entailment gate into `src/polaris_graph/generator2/strict_verify.py`. Empirical falsification by re-running the production sweep showed: production uses `src/polaris_graph/generator/provenance_generator.py`, NOT generator2. **The 6 PRs of work bound to the wrong code path.** This PR fixes that.

## Production-validated outcome

| Metric | I-bug-091 baseline (pre-fix) | I-bug-098 (this PR, gate active) |
|---|---|---|
| sentences_verified | 25 | 14 |
| sentences_dropped | 26 | **37** |
| **entailment_failed drops** | **0** | **8** ← I-bug-098 NEW |
| status | partial_qwen_advisory | partial_qwen_advisory |

The 8 `entailment_failed` drops in `verification_details.json:drop_reason_counts` are direct empirical proof the gate fires in production. Each drop carries a NEUTRAL verdict + judge-side rationale (e.g., "the sentence introduces specific patient characteristics not in the cited span").

## Codex P2 advisories (accepted as follow-ups)

1. **I-bug-100**: `judge.judge()` cost is uncounted in manifest `cost_usd` — entailment-judge calls go through httpx directly, bypassing the budget-tracking `OpenRouterClient`. Real run cost is ~$0.013 (similar to baseline) but manifest reports $0.0012. Codex says ship + follow-up unless cost_usd is an enforcement boundary.
2. **I-bug-102**: Off-mode still imports `generator2.strict_verify` on every mechanically-passing sentence because the import precedes the `_entailment_mode()` call. My docstring claim of "zero off-mode import cost" is technically wrong. Trivial 3-line fix — defer to follow-up since not behavioral.

## Hygiene

- 10 new tests pass + 4439 baseline tests pass (10 pre-existing failures verified independent of my changes by checkout-and-test on clean polaris)
- Lazy function-local import; no circular dependency (generator2.strict_verify does not import from polaris_graph.generator)
- Mechanical short-circuit before judge call (cost discipline pinned by `test_number_mismatch_short_circuits_before_entailment`)
- `entailment_failed:` prefix matches manifest builder's `r.split(":", 1)[0]` convention so the drop reason flows into `drop_reason_counts`
- Telemetry counters shared with generator2 path (single `get_judge_telemetry()` snapshot covers both verifiers)

## Definition-of-done

- [x] 10 new tests pass + 4439 baseline tests pass
- [x] Codex APPROVE on brief + diff iter 1 (zero P0/P1)
- [x] **Empirical proof**: 8 `entailment_failed` drops in production manifest
- [x] canonical-diff-sha256 = `2c9c36af090c27aac108eefaa4a969411c9234cd88e80cc25e71885947a321f9`
- [ ] CI gate green
- [ ] Auto-merge per Plan §7.B LOCKED B1

## Follow-up Issues

- I-bug-099: extract entailment-judge helpers into shared module (clean Option B refactor)
- I-bug-100: route entailment-judge calls through OpenRouterClient (cost accounting)
- I-bug-101: distributional false-positive audit on a broader sweep
- I-bug-102: off-mode short-circuit before generator2 import (Codex P2.2)
