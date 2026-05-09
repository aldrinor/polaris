# Claude Audit — I-bug-094 (live OpenRouter entailment canary)

**Date**: 2026-05-09
**Branch**: `bot/I-bug-094-live-integration-test`
**Codex**: APPROVE on brief + diff iter 1, zero P0/P1, 1 P2 acknowledged.

## What this ships

Env-gated live OpenRouter test (`tests/polaris_graph/generator2/test_strict_verify_entailment_live.py`) with 4 audit-derived cases (M2/C2/C1/positive control). Skipped by default in CI; run via `PG_ENTAILMENT_LIVE=1 OPENROUTER_API_KEY=... pytest -m live`. Adds `live` pytest marker to pytest.ini.

## Empirical validation (key result, beyond the canary infrastructure)

Ran the live tests against real OpenRouter Gemma 4 31B before submitting this PR. **4/4 passed in 20.5 seconds**:

```
test_live_m2_fabrication_returns_neutral_or_contradicted PASSED
test_live_c2_specificity_inflation_returns_neutral_or_contradicted PASSED
test_live_c1_unentailed_numbers_returns_neutral_or_contradicted PASSED
test_live_paraphrase_positive_control_returns_entailed PASSED
```

This is the empirical evidence the architectural fix from I-bug-092 actually works on the audit-revealed M2/C2/C1 patterns. The judge prompt + Gemma 4 31B model + wiring all together correctly identify the fabrications and accept legit paraphrases. **This effectively also closes I-bug-093** (warn-mode demo to validate the prompt) on the M2/C2/C1 patterns specifically — the 4 most important audit cases work without any prompt tuning. A broader warn-mode run on a fresh tirzepatide generation is still worth doing, but the prompt-correctness blocker for graduating to enforce mode (I-bug-095) is no longer active.

## Codex P2 advisory (acknowledged, NOT blocker)

Codex flagged that the skip check uses truthy `os.environ.get(...)`, so `PG_ENTAILMENT_LIVE=0` would still run the live tests. Documented semantics say "set to 1." Codex said "not blocking" + accept_remaining, so shipping as-is. Operator typing `=0` thinking they're disabling will accidentally spend ~$0.002 on the canary — that's fine, not actionable. Captured here for completeness; could be a 1-line tightening in a follow-up if it becomes a real footgun.

## Definition-of-done

- [x] 4 new tests pass live against Gemma 4 31B (verified 2026-05-09)
- [x] 232 baseline tests still pass + 4 new SKIPPED in default CI
- [x] Codex APPROVE on brief + diff iter 1, zero P0/P1
- [x] canonical-diff-sha256 = `60b6d60ca16557947c44cff46564c8c2c178686459c0d6babcbced974da067ed`
- [ ] CI gate green
- [ ] Auto-merge per Plan §7.B LOCKED B1
