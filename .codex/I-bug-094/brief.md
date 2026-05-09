# Codex Brief — I-bug-094 (env-gated live OpenRouter entailment test)

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding.
- "Don't pick bone from egg" — reserve P0/P1 for real execution risks.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
- DO NOT call exec / rg / shell tools. Brief is self-contained.
```

## Context

Captured as Codex P2 on I-bug-092 diff review:

> "Persistent judge/config failures fail open even in enforce mode... Recommend telemetry/counters PLUS an env-gated live OpenRouter test."

I-bug-096 shipped the counters half. I-bug-094 ships the **live test half** — an env-gated test that constructs the real `_EntailmentJudge`, hits live OpenRouter with the audit-derived M2/C2/C1 sentence/span pairs, and asserts the judge returns NEUTRAL/CONTRADICTED on each. This catches model-behavior changes that the unit-test mocks cannot detect (e.g. Gemma 4 31B response format changes, OpenRouter starts returning a different JSON shape, or the model's recall on M2-style fabrications regresses).

## Test design

Single test file `tests/polaris_graph/generator2/test_strict_verify_entailment_live.py` with `pytest.mark.skipif(not os.getenv("PG_ENTAILMENT_LIVE"), reason="...")` skip decorator.

When the skip is bypassed (operator sets `PG_ENTAILMENT_LIVE=1` AND has `OPENROUTER_API_KEY`):
- 4 tests instantiate `_EntailmentJudge` (NOT FakeJudge) with default Gemma 4 31B
- Each test sends a real audit-derived sentence + span to live OpenRouter
- Assertions:
  - **M2** (β-cells/lipid metabolism/energy storage inserted) → expect NEUTRAL
  - **C2** (semaglutide-specific upgrade from GLP-1 RA class) → expect NEUTRAL
  - **C1** (69-80% reach ≤6.5% claim not in span) → expect NEUTRAL
  - **Positive control** (conservative paraphrase) → expect ENTAILED

If a verdict is CONTRADICTED, that's also acceptable — it's the right direction; the test asserts `verdict in ("NEUTRAL", "CONTRADICTED")` for negative cases.

If any assertion fails on live, that signals: model behavior drift OR the audit-derived patterns are no longer being recognized. Operator can then look at the prompt + judge output to recalibrate.

## Execution model

- Default CI run: skipped (env var unset). Zero cost.
- Operator opt-in: `PG_ENTAILMENT_LIVE=1 OPENROUTER_API_KEY=... pytest tests/polaris_graph/generator2/test_strict_verify_entailment_live.py`. Cost: ~4 OpenRouter calls × ~$0.0005 = ~$0.002.
- Can be added to a periodic out-of-band CI job (weekly cron) as canary if operator wants ongoing model-drift detection. Out of scope for this PR — just the test.

## Test surface

- `test_live_m2_fabrication_returns_neutral_or_contradicted` — M2 verbatim from audit
- `test_live_c2_specificity_inflation_returns_neutral_or_contradicted` — C2 verbatim
- `test_live_c1_unentailed_numbers_returns_neutral_or_contradicted` — C1 verbatim
- `test_live_paraphrase_positive_control_returns_entailed` — positive control

## Implementation surface

`tests/polaris_graph/generator2/test_strict_verify_entailment_live.py` — ~120 LOC, 4 tests, no production code change.

## What I want from you

1. **Verdict** APPROVE / REQUEST_CHANGES.
2. **Skip decorator**: `pytest.mark.skipif` (current proposal, skip at collect-time) vs `pytest.skip()` inside test body (skip at run-time)? I lean skipif so CI logs cleanly show "SKIPPED PG_ENTAILMENT_LIVE not set" rather than burying the skip inside test setup.
3. **Failure tolerance**: should a model-recall regression on M2 fail the test (current proposal) or just log a warning? My read: fail it. The whole point is to catch model drift early; silent warnings get ignored.
4. **Cost concern**: ~$0.002 per run. Per CLAUDE.md `feedback_no_cost_mentions.md` cost is not a concern; flagging just for completeness.
5. **Should we register this as a pytest marker** (`@pytest.mark.live`) so operators can run `pytest -m live` to invoke just the live tests? Adds ~3 LOC for marker registration in conftest. I lean yes.

## Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
skip_mechanism: skipif | runtime_skip | other
failure_on_model_drift: hard_fail | warning
register_pytest_marker: yes | no
extra_test_cases: [...]
loc_estimate_ok: yes | no
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
rationale: <2-3 sentences>
```
