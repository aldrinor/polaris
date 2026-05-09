# Codex Diff Review — I-bug-092 (entailment judge as 6th strict_verify check)

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
- DO NOT call exec / rg / shell tools. Brief is self-contained.
```

## Context (one paragraph)

This implements the architectural fix you APPROVE'd at iter 1 in `.codex/I-bug-092/codex_brief_verdict.txt` (recommended_option: B, fix_location: `src/polaris_graph/generator2/strict_verify.py:after content-word overlap check in verify_sentence()`). The 2026-05-09 audit (`outputs/audits/v32_baseline_content_audit/CROSS_REVIEW.md`) found 1 fabricated mechanistic claim (M2), 1 specificity inflation (C2), and 1 unverifiable specificity claim (C1) — all of which passed the existing 5 mechanical strict_verify checks because lexical overlap implies topic-match, not content-fidelity. Option B adds a 6th check: an LLM-as-judge entailment call to the two-family evaluator (Gemma 4 31B by default), gated by `PG_STRICT_VERIFY_ENTAILMENT={off,warn,enforce}` defaulting to `off`.

## What you APPROVE'd at brief stage

```yaml
verdict: APPROVE
recommended_option: B
fix_location: "src/polaris_graph/generator2/strict_verify.py:after content-word overlap check in verify_sentence()"
loc_estimate: 90
crown_jewel_candidate: yes
false_positive_risk: "Legitimate paraphrases may be dropped when the judge is overly literal or the cited span is too narrow."
rollback_plan: "Gate behind an env flag such as PG_STRICT_VERIFY_ENTAILMENT with warn-only telemetry mode before disabling hard rejection."
test_surface:
  - "M2: span mentions insulin secretion/adipocyte metabolism, sentence adds beta-cells/lipid metabolism/energy storage -> reject"
  - "C2: span supports GLP-1 RA class comparison, sentence upgrades to semaglutide/highest studied doses -> reject"
  - "C1: span contains nearby numbers but does not entail <=6.5% 69-80% claim -> reject"
  - "Positive control: exact or conservative paraphrase fully entailed by span -> accept"
  - "Synthesis exemption: is_synthesis_claim=True keeps existing exemption behavior unless the claim has explicit cited factual assertions"
```

## LOC accounting (158 src/ vs your 90 estimate)

The 90-LOC estimate assumed minimal wiring. Actual: 158 src/ LOC net (excluding tests). The drift comes from:

1. **Lazy singleton + httpx import** (`_get_judge`, `_JUDGE_SINGLETON`, the local `import httpx` in `__init__`) — ~10 LOC. Necessary so off-mode pays zero import / connection cost; tests demonstrate `_install_fake_judge` cleanly replaces this.
2. **Two-family invariant enforcement** (per §9.1.1) — `check_family_segregation(evaluator_model=self._model)` call in `__init__` plus the lazy `from polaris_graph.llm.openrouter_client import check_family_segregation` and 6-line explanation comment. ~10 LOC. Without this, an operator setting `PG_ENTAILMENT_MODEL` to a DeepSeek variant when `PG_GENERATOR_MODEL` is also DeepSeek silently violates invariant 1. Adds a regression test (`test_judge_construction_fails_when_judge_same_family_as_generator`).
3. **Mode helper + env parsing** (`_entailment_mode()`) — ~5 LOC. Lets unknown values fall back to off rather than crash at runtime.
4. **Fail-open behavior on transient OpenRouter errors** — wraps the `judge()` call in try/except returning `("ENTAILED", "judge_error: ...")` so a 503 outage does not nuke a run. ~7 LOC.
5. **Prompt + docstrings** — ~30 LOC. The judge prompt is pinned as a module-level constant rather than inline in `judge()`; the docstring explains the architectural rationale (provenance presence vs. provenance correctness) so a future reader doesn't repeat the audit.
6. **Logger import + warn-mode logging** — ~5 LOC.

Test file: 430 LOC of test coverage (12 wiring tests + 11 mode-parsing parametrized + 2 mechanical-short-circuit + 2 family-segregation = 27 tests). All 27 pass; baseline 155 strict_verify.py + 23 verified_report.py tests still pass (203 total in generator2 suite).

If you want me to drop to ≤90 src/ LOC, the only meaningful trim is removing the family-segregation check + its test (~15 LOC). I do NOT recommend this — that check is the structural enforcement of §9.1.1 against operator misconfiguration. Deferring it to a follow-up issue accepts a real soft-fail surface.

## Files changed (3 files, 605 lines total)

| File | LOC delta | Purpose |
|---|---|---|
| `src/polaris_graph/generator2/strict_verify.py` | +175/-2 | Add `_EntailmentJudge` class, `_get_judge`, `_entailment_mode`, check 6 inside `verify_sentence`, updated docstring |
| `src/polaris_graph/generator2/verified_report.py` | +1 | Add `entailment_failed` to `DropReason` Literal |
| `tests/polaris_graph/generator2/test_strict_verify_entailment.py` | +430 (new) | 27 tests: M2/C2/C1 negative + positive control + synthesis variants + mode parsing + mechanical short-circuit + two-family enforcement |

## Critical implementation choices (please review)

### 1. Order of checks: entailment is LAST (after all mechanical checks)

Tests `test_numeric_mismatch_short_circuits_before_judge` and `test_overlap_too_low_short_circuits_before_judge` pin this. Rationale: the cheap mechanical gates run first; the expensive LLM call runs only on sentences that already cleared lexical hygiene. Cost discipline.

### 2. Synthesis-claim-with-tokens still runs entailment (NOT exempt)

Per your test_surface: "is_synthesis_claim=True keeps existing exemption behavior unless the claim has explicit cited factual assertions." I implemented this as: the no-token short-circuit at line ~262 still exempts synthesis claims with no tokens. But if `is_synthesis_claim=True` AND tokens are present, the entailment check still fires. Tests `test_synthesis_claim_with_tokens_still_runs_entailment` and `test_synthesis_claim_without_tokens_skips_entailment` pin this exact behavior.

### 3. Three modes (off/warn/enforce), default off

Off mode pays zero cost: `_entailment_mode()` returns `"off"`, the `if mode in ("warn", "enforce")` guard skips the judge call, and `_get_judge` (which would lazy-init the httpx client) is never invoked. Tests `test_off_mode_skips_judge_even_when_set_explicitly` and `test_unknown_mode_falls_back_to_off` pin that we never call the judge in off-mode.

Warn mode logs `WARNING: entailment NEUTRAL/CONTRADICTED ...` but does NOT change the verifier_pass return value. Test `test_warn_mode_does_not_drop_on_neutral` pins this.

Enforce mode drops on NEUTRAL or CONTRADICTED. Tests for M2, C2, C1, generic CONTRADICTED case all pin this.

### 4. Judge fail-open on API/parse error

If OpenRouter returns 503 or returns malformed JSON, `_EntailmentJudge.judge()` returns `("ENTAILED", "judge_error: TimeoutError")` — i.e. the sentence is kept. Reasoning: a transient outage should not nuke a generation run; warn mode would surface this in logs. The fail-loud principle applies to data integrity (LAW II), not to a defense-in-depth check.

### 5. Two-family invariant enforced at judge construction (§9.1.1)

`check_family_segregation(evaluator_model=self._model)` is called in `_EntailmentJudge.__init__`, after API-key check. If an operator sets `PG_ENTAILMENT_MODEL=deepseek/deepseek-v3.2-exp` when `PG_GENERATOR_MODEL` is also DeepSeek, this raises RuntimeError. Test `test_judge_construction_fails_when_judge_same_family_as_generator` pins this. Default `google/gemma-4-31b-it` is in a different family from DeepSeek by construction.

### 6. Lazy import of openrouter_client + httpx

Both imports are local to `_EntailmentJudge.__init__`. Reasoning: when `PG_STRICT_VERIFY_ENTAILMENT=off` (the default for now), the off-mode codepath never imports openrouter_client or httpx, preserving cold-import time for the strict_verify module.

## What I want from you

1. **Iter 1 verdict (APPROVE / REQUEST_CHANGES)** with the schema below.
2. **Any P0 / P1 you find on the diff itself** — please be exhaustive in iter 1; do not bank for iter 2+.
3. Specific gaps you want closed in this PR vs. follow-up Issues:
    - Do you want a live-OpenRouter integration test (env-gated) in this PR, or follow-up?
    - Do you want this graduated to enforce mode in a follow-up Issue, or do you want to run warn mode for one full demo cycle first to collect telemetry?
    - Do you want I-cj-008 (Crown Jewel binding test "no claim survives strict_verify if cited span doesn't entail it") created in this PR, or follow-up?

## Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
follow_up_issues_recommended: [...]
```
