# Codex Diff Review — I-bug-094 (live OpenRouter entailment canary)

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1.
- "Don't pick bone from egg".
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
- DO NOT call exec / rg / shell tools.
```

## Pre-flight

- Brief APPROVE'd iter 1 (`.codex/I-bug-094/codex_brief_verdict.txt`)
- Diff: `.codex/I-bug-094/codex_diff.patch` (canonical-diff-sha256: `60b6d60ca16557947c44cff46564c8c2c178686459c0d6babcbced974da067ed`)
- Diff scope: 1 new test file + 1 line in pytest.ini for the `live` marker
- Zero production code changes
- 4 tests, all skipif-gated; 0 cost in default CI

## Empirical validation against real OpenRouter

Critical: I ran the live tests AGAINST the real OpenRouter Gemma 4 31B before submitting. **4/4 PASSED in 20.5 seconds**:

```
test_live_m2_fabrication_returns_neutral_or_contradicted PASSED
test_live_c2_specificity_inflation_returns_neutral_or_contradicted PASSED
test_live_c1_unentailed_numbers_returns_neutral_or_contradicted PASSED
test_live_paraphrase_positive_control_returns_entailed PASSED
```

This is the empirical confirmation we did NOT have at I-bug-092 review time:
- The Gemma 4 31B judge **correctly identifies** the M2 fabrication (β-cells/lipid metabolism not in URNCST adipocyte-metabolism span) as NEUTRAL/CONTRADICTED
- The judge **correctly identifies** the C2 specificity inflation (GLP-1 RA class → semaglutide-specific upgrade) as NEUTRAL/CONTRADICTED
- The judge **correctly identifies** the C1 unentailed-numbers claim (69-80% reach ≤6.5% claim not in span) as NEUTRAL/CONTRADICTED
- The judge **correctly accepts** the conservative paraphrase as ENTAILED

So I-bug-094 simultaneously: (a) ships the canary infrastructure, AND (b) provides the empirical evidence that the prompt + model combination from I-bug-092 actually works on the audit-derived patterns. This effectively also closes I-bug-093 (warn-mode demo to validate prompt) on the M2/C2/C1 patterns specifically — the 4 most important audit cases pass without any prompt tuning.

## Implementation matches your iter-1 brief

- ✅ `pytest.mark.skipif` at module level (collect-time skip — clean CI logs)
- ✅ Hard fail on model drift (no warning-only fallback)
- ✅ Registered `live` pytest marker in pytest.ini for `pytest -m live` workflow
- ✅ 4 test cases per your test_surface (M2/C2/C1/positive control)
- ✅ Acceptable verdict for negative cases includes both NEUTRAL and CONTRADICTED (gate drops on either)

## Tests pinned

| Test | Behavior |
|---|---|
| `test_live_m2_fabrication_returns_neutral_or_contradicted` | Real Gemma 4 31B on M2 must NOT say ENTAILED |
| `test_live_c2_specificity_inflation_returns_neutral_or_contradicted` | Real judge on C2 must NOT say ENTAILED |
| `test_live_c1_unentailed_numbers_returns_neutral_or_contradicted` | Real judge on C1 must NOT say ENTAILED |
| `test_live_paraphrase_positive_control_returns_entailed` | Conservative paraphrase MUST say ENTAILED (no over-strictness drift) |

## Operator workflow

Run on demand:
```
PG_ENTAILMENT_LIVE=1 OPENROUTER_API_KEY=<key> \
  pytest tests/polaris_graph/generator2/test_strict_verify_entailment_live.py
```

Or via marker:
```
PG_ENTAILMENT_LIVE=1 OPENROUTER_API_KEY=<key> pytest -m live
```

Default CI: 4 SKIPPED, zero API calls.

## What I want from you

1. **Verdict** APPROVE / REQUEST_CHANGES.
2. **Any P0/P1 you find** — please be exhaustive iter 1.
3. Should the brief module-level docstring also include the empirical "4/4 passed against real OpenRouter on 2026-05-09" evidence? My read: YES, captured in this diff brief; could pull into the test file header too. Lean toward keeping the diff brief as the empirical record + leaving the test file purpose-only.

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
