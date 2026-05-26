# Codex — adversarial review of Step 1 iter-5 SMOKE RESULT

## Operator directive (verbatim)

> "Codex review of smoke results first — Confirms my interpretation
> (verifier is correct, not regressed). ~5 min."

You APPROVED iter 5 of the Step 1 diff. The operator then ran the live
smoke against the canonical clinical_tirzepatide_t2dm question. **Pass
rate went DOWN, not up.** I want your adversarial read on whether this
is the verifier becoming CORRECT (my interpretation) or whether I
broke something Codex iter-5 missed.

## §8.3.1 cap directive (verbatim)

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding.
- "Don't pick bone from egg" — reserve P0/P1 for real execution risks.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Empirical results — read these directly

| File | Description |
|---|---|
| `outputs/honest_sweep_r3.step1_iter5_resume/clinical/clinical_tirzepatide_t2dm/manifest.json` | Iter-5 manifest (status=success, $0.096, 2386s) |
| `outputs/honest_sweep_r3.step1_iter5_resume/clinical/clinical_tirzepatide_t2dm/verification_details.json` | Per-sentence drop log |
| `outputs/honest_sweep_r3.step1_iter5_resume/clinical/clinical_tirzepatide_t2dm/report.md` | Generated report |
| `outputs/honest_sweep_r3.step1_iter5_resume/clinical/clinical_tirzepatide_t2dm/evidence_pool.json` | Evidence corpus |
| `outputs/honest_sweep_r3.step1_iter5_resume/clinical/clinical_tirzepatide_t2dm/reasoning_trace.jsonl` | V4 Pro reasoning trace |
| `outputs/honest_sweep_r3.step1_partial/clinical/clinical_tirzepatide_t2dm/manifest.json` | BASELINE (pre-iter-5 fix) for comparison |
| `outputs/honest_sweep_r3.step1_partial/clinical/clinical_tirzepatide_t2dm/verification_details.json` | BASELINE drop log |
| `.codex/I-gen-005/smoke_iter5_dropped_samples.json` | 5 entailment_failed examples with cited evidence spans |

## Numbers I observed

| Metric | Baseline (pre-iter5) | Iter-5 fix | Delta |
|---|---|---|---|
| manifest.status | partial_evaluator_advisory | success | + |
| sentences_verified | 30 | 17 | -13 |
| sentences_dropped | 30 | 43 | +13 |
| sections_kept | 5 | 4 | -1 |
| verified_words | 1,059 | 526 | -533 |
| total_words | 2,812 | 2,676 | -136 |
| pass_rate | 50.0% | **28.3%** | -21.7pp |
| cost_usd | $0.099 | $0.096 | same |
| judge: good | 3 | 4 | +1 |
| judge: needs_revision | 2 | 1 | -1 |

## Drop-reason histogram (the key signal)

| Category | Baseline | Iter-5 | Delta |
|---|---|---|---|
| **entailment_failed** | 15 | **32** | **+17** |
| trial_name_mismatch | 13 | 13 | 0 |
| number_not_in_cited_span | 5 | 3 | **-2** |
| no_integer_overlap | 2 | 0 | **-2** |
| no_content_word_overlap | 1 | 1 | 0 |
| no_provenance_token | 0 | 1 | +1 |

## My interpretation (please confirm or refute)

The pass-rate drop is **the verifier becoming correct**, not a
regression. Reasoning:

1. **Numeric false-positive drops DECREASED** (5→3, 2→0). My iter-5
   token-exact + range-dash fixes ARE working — fewer legit numeric
   sentences are getting dropped.

2. **Entailment failures DOUBLED** (15→32). This is the direct
   consequence of your iter-1 P1 #3 finding: the previous whole-doc
   entailment fallback was passing sentences by finding support
   ANYWHERE in a 25k-char paper. My iter-2 fix localized it to a
   400-char window. So 17 additional sentences that previously passed
   via the loose whole-doc check now correctly fail.

3. **Trial-name mismatches unchanged** (13→13). Step 3 (trial-name
   alias metadata) is needed; not in Step 1 scope.

4. **manifest.status improved** from `partial_evaluator_advisory` to
   `success`. Verifier-rule-checks also identical (12 pass / 1 fail).

5. **Judge ratings IMPROVED** despite fewer verified sentences (3→4
   "good", 2→1 "needs_revision"). Sections that survived are higher
   quality.

So my read: **V4 Pro's true fabrication rate is 72%, not 50%.** The
50% baseline was an artifact of the leaky judge. Steps 2-3 are needed
to raise the floor (Step 2: V4 Pro span rewriter cites correctly;
Step 3: trial-name aliases).

## Questions for you

1. **Is my interpretation correct?** Is the pass-rate drop the
   verifier correctly catching what the leaky judge missed, or did I
   introduce a NEW false-positive class somewhere?

2. **Sample 5 entailment_failed cases** in
   `.codex/I-gen-005/smoke_iter5_dropped_samples.json`. Read them.
   Are these REAL fabrications V4 Pro is producing, or are they
   correctly-grounded sentences that the localized judge is now
   missing because the 400-char window is too narrow?

3. **Should we tighten or loosen** any of the iter-5 thresholds based
   on the smoke result? Specifically:
   - `min_content_overlap=2` for `_find_local_support_window`
   - 400-char window default
   - Pattern B (decimal-anchored left-gap-only) coverage

4. **Should we proceed to Step 2 now**, or are there iter-5 follow-up
   tightenings needed first?

5. **Any signal in the report.md output quality** (length, citation
   density, factuality risk) that would change your APPROVE on the
   Step 1 diff?

## Output schema

```yaml
verdict: CONFIRMS_INTERPRETATION | REFUTES_INTERPRETATION | PARTIAL
my_interpretation_correctness: TRUE | FALSE | PARTIAL
  reasoning: |
    (your read: is iter-5 a correct verifier or a regression?)
entailment_failed_sample_audit:
  - sentence_index: 0
    is_real_fabrication: YES | NO | UNDECIDABLE
    reasoning: |
      (per-sample read from .codex/I-gen-005/smoke_iter5_dropped_samples.json)
  - sentence_index: 1
    ...
follow_up_tightenings_needed_before_step_2:
  - finding: |
      (specific finding; cite file:line)
    severity: P0 | P1 | P2
    proposed_fix: |
      (specific fix)
step_2_readiness: READY | NOT_READY
  if_not_ready: |
    (what must close first)
convergence_call: continue | accept_remaining
```

EMIT YAML ONLY. Reading actual files is more important than my
summary. Don't pick bone from egg — the operator wants real signal
on whether to proceed to Step 2.
