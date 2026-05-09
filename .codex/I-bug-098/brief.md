# Codex Brief — I-bug-098 (wire entailment gate into PRODUCTION verifier)

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1.
- "Don't pick bone from egg".
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
- DO NOT call exec / rg / shell tools. Brief is self-contained.
```

## What we got wrong before, and what this Issue fixes

The 6 PRs #343-#348 (I-bug-092 / I-cj-008 / I-bug-094..097) wired the entailment judge into `src/polaris_graph/generator2/strict_verify.py`. Crown Jewel locked, telemetry shipped, 4/4 live PASS, default flipped to enforce.

**Empirical falsification just now**: I ran `scripts/run_honest_sweep_r3.py --only clinical_tirzepatide_t2dm` with the new default. The new run:

- cost: $0.0014 (BASELINE $0.0139 — DROPPED, not increased; entailment judge would add ~22 × $0.0005 = ~$0.011)
- drop_reason vocabulary: `no_content_word_overlap_any_cited_span`, `number_not_in_any_cited_span`, `trial_name_mismatch` — **none of my drop reasons** (no `entailment_failed`, no `overlap_too_low`)
- log: zero "entailment NEUTRAL"/"judge_error" lines
- generator2 telemetry counters: untouched (zero calls)

Diagnosis: `scripts/run_honest_sweep_r3.py` imports from `src/polaris_graph/generator/provenance_generator.py:603 verify_sentence_provenance`, NOT from `generator2/strict_verify.py:verify_sentence`. Two parallel verifiers in the codebase. The audit-revealed M2/C2/C1 gap lives in the production path that uses `generator/`. **My 6 PRs of work bound to a different code path; the production audit gap is still open.**

This is the canonical `feedback_substrate_is_not_product.md` failure: substrate locked + tested + Crown-Jewel'd, but the lock isn't on the production door.

## The production verifier

`src/polaris_graph/generator/provenance_generator.py:603` `verify_sentence_provenance(sentence, evidence_pool, *, require_number_match=True) -> SentenceVerification`

Runs 5 checks in order: token validity, span bounds, number-match (decimal subset across aggregated cited spans, with placebo-comparator + threshold strip), integer overlap fallback, content-word overlap (`MIN_CONTENT_WORD_OVERLAP`), trial-name match (M-25a). Returns `SentenceVerification(sentence, tokens, is_verified, failure_reasons, soft_warnings)`.

Failure surface uses `failure_reasons: list[str]` — different vocabulary than `generator2.strict_verify` (which returns `(bool, DropReason | None)`). Not blocking; just need to add an `entailment_failed:<judge_reason>` failure_reason and increment the same telemetry counters.

## Three ways to wire the judge in

### Option A — Cross-module import (tactical)

`src/polaris_graph/generator/provenance_generator.py` imports `_get_judge`, `_record_judge_outcome`, `_entailment_mode` from `polaris_graph.generator2.strict_verify`. Adds the entailment branch as check 6. Reuses the existing telemetry counters + cap directives + family-segregation guard.

- Pros: minimal LOC (~25 src). Tests don't need re-write — same env var `PG_STRICT_VERIFY_ENTAILMENT`. Telemetry already in place.
- Cons: cross-package dependency from `generator/` → `generator2/`. Architecturally smells; `generator2/` is a sibling, not a shared util.

### Option B — Extract shared helper module (clean)

Create `src/polaris_graph/_entailment.py` (or `src/polaris_graph/llm/entailment_judge.py`) with `_EntailmentJudge`, `_get_judge`, `_record_judge_outcome`, `_entailment_mode`, `get_judge_telemetry`, `reset_judge_telemetry`, `_DEFAULT_MODE`, `_UNKNOWN_MODE_WARNED`. Move ALL the helpers there. Have BOTH `generator/provenance_generator.py` AND `generator2/strict_verify.py` import from the shared module.

- Pros: clean architecture, no cross-package coupling, single source of truth, no behavioral change for either generator.
- Cons: more LOC (~50 to extract + 30 to update both verifiers + test reorg). Risk of regression in generator2 tests.

### Option C — Duplicate helper code (anti-pattern)

Copy the judge class + helpers into `generator/provenance_generator.py`. Two telemetry-counter dicts, two singletons, two unknown-mode warning sets.

- Pros: zero coupling.
- Cons: drift surface, two places to update prompts / models / fail-open behavior, two telemetry counters operators have to merge to get a global view. Anti-pattern.

## Plan

I propose **Option A (tactical) for this PR + I-bug-099 (refactor) for the extract-to-shared-module work later**. The reason: closing the production gap NOW is the load-bearing work; getting the architecture pretty can wait. The cross-module import is uglier than Option B but ships in 1 PR rather than 1 PR + a refactor PR.

If you prefer Option B, I'll do Option B in this PR and skip the later refactor.

## Test surface

- New test `tests/polaris_graph/generator/test_provenance_generator_entailment.py` — mirrors `tests/polaris_graph/generator2/test_strict_verify_entailment.py` patterns:
  - M2 / C2 / C1 negative cases against `verify_sentence_provenance` directly with a fake judge
  - Positive control (paraphrase ENTAILED → keep)
  - Off / warn / enforce mode wiring
  - Mechanical short-circuit (number_not_in_any_cited_span runs BEFORE entailment)
  - Telemetry counters tick (calls, neutral, entailed, judge_error)
- Update existing tests/polaris_graph/test_provenance_generator.py: ensure they don't accidentally break under the new gate (autouse off-fixture should already cover this since I added it in I-bug-095).

## Verification (the load-bearing step I missed last time)

After commit, BEFORE PR-open: re-run `scripts/run_honest_sweep_r3.py --only clinical_tirzepatide_t2dm` against the fresh code. Acceptance:
- Cost rises by approximately +$0.011 (entailment judge calls)
- Telemetry counters > 0 (judge_calls, judge_entailed, etc. — log captured)
- Some drops show `entailment_failed:<reason>` in `verification_details.json` IF the generator emits unsupported claims (we'd be lucky; otherwise zero entailment drops + non-zero entailed counts is also evidence of working wiring)

If this verification doesn't show the gate firing in production, the PR isn't ready. No "shipped" claim until empirically validated on the production hot path.

## What I want from you

1. **Verdict** APPROVE / REQUEST_CHANGES on the plan.
2. **Option A vs Option B vs Option C** — which architecture do you recommend?
3. **LOC cap** — Option A is ~25 src + ~150 test = ~25 within the 200 cap. Option B is ~50 src (counts the shared module + 2 import-site changes) + similar test = ~50 within cap. Both fit.
4. **Acceptance gate**: is "judge_calls > 0 in next sweep manifest's evaluator_rule_checks or run log" sufficient empirical proof of wiring, or do you want a specific number/threshold?
5. **Anti-regression**: should this PR also touch `provenance_generator.py:strict_verify` rollup function (line 916) so the failure_reasons list flows through correctly to the manifest's drop_reason_counts dict?

## Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
recommended_option: A | B | C
acceptance_proof_required: <description>
loc_estimate_ok: yes | no
extra_changes_required: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
rationale: <2-3 sentences>
```
