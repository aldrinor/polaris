# Codex iter 1 — I-gen-005 Step 1.5 diff review (telemetry fix)

## §8.3.1 canonical cap directive (verbatim)

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by
  Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## What you flagged in the smoke review (2026-05-26)

> P1: `verification_details.json` is not the final per-sentence
> provenance artifact. It is reconstructed by re-running bare
> strict_verify on `sr.rewritten_draft`
> (`scripts/run_honest_sweep_r3.py:2703-2721`) after the pipeline has
> already applied repair/dedup/regen paths. The emitted report
> contains sentences logged as dropped (`report.md:9` vs
> `verification_details.json:173` and `verification_details.json:200`),
> and the section-list counts do not match artifact totals.
>
> proposed_fix: Persist final `SectionResult.kept_sentences_pre_resolve`
> plus final dropped accounting from the generation pipeline, or add
> final dropped sentence objects to `SectionResult`; do not reconstruct
> final verification details by re-running bare strict_verify on
> rewritten drafts.

## What I changed (your proposed fix, implemented)

### 1. `src/polaris_graph/generator/multi_section_generator.py:79-118` — SectionResult fields

Added two FINAL-state tracking fields to SectionResult:

```python
# Per-section FINAL dropped sentences with full SV objects (.sentence,
# .tokens, .failure_reasons). Reflects post-dedup pipeline state.
dropped_sentences_final: list[Any] = field(default_factory=list)
# Sentences dropped by fact_dedup as redundant (LLM consolidation,
# NOT strict_verify failures — tracked separately so the operator
# can see WHY each missing sentence is missing).
dropped_sentences_dedup_redundant: list[str] = field(default_factory=list)
```

### 2. `multi_section_generator.py:1456-1462` — populate at initial strict_verify

```python
return SectionResult(
    ...
    kept_sentences_pre_resolve=list(report.kept_sentences),
    dropped_sentences_final=list(report.dropped_sentences),   # NEW
)
```

### 3. `multi_section_generator.py:~3845` — extend at dedup re-verify

When `_fact_dedup_pass`'s LLM rewrites fail re-strict_verify, those
SVs are now appended to `sr.dropped_sentences_final` (real
strict_verify failures, not consolidations):

```python
sr.dropped_sentences_final.extend(rewrite_report.dropped_sentences)
```

### 4. `multi_section_generator.py:~3865` — track dedup-redundants separately

When `_fact_dedup_pass` removes a redundant via LLM consolidation
(NOT a strict_verify failure), capture the string in the dedup-only
field:

```python
final_str_set = {sv.sentence for sv in final_svs}
sr.dropped_sentences_dedup_redundant.extend(
    s for s in original_strs if s not in final_str_set
)
```

### 5. `scripts/run_honest_sweep_r3.py:2703-2762` — serialize FROM SectionResult

Replaced the bare `strict_verify(sr.rewritten_draft, ev_pool)` re-run
with direct serialization of the FINAL `SectionResult` fields. Added
a separate `dropped_by_dedup_redundant[]` section in the JSON output
plus a `dedup_redundant_count` rollup so the operator can distinguish
the two drop categories.

## Unit test — 8 assertions, all PASS

`scripts/test_i_gen_005_step15_telemetry.py`:

```
PASS: verified sentence is in kept[]
PASS: real strict_verify failure is in dropped[] with failure_reasons
PASS: dedup-redundant is NOT in dropped[] (the pre-fix bug)
PASS: dedup-redundant IS tracked in dropped_by_dedup_redundant[]
PASS: total_kept = 1, total_dropped = 2 (real_failure + dedup_redundant)
PASS: drop_reason_counts excludes dedup-redundant
PASS: dedup_redundant_count = 1
PASS: kept and dedup-redundant cover the same fact (15 mg / 2.30%)
```

The fixture mimics the EXACT bug you flagged: 3 sentences in the
rewritten_draft, 1 kept after dedup, 1 consolidated into the kept one
(dedup-redundant), 1 real strict_verify failure (cancer-50%
fabrication). The pre-fix code would have FALSELY listed the
dedup-redundant in `dropped[]` with bogus failure_reasons (because
re-running strict_verify on the rewritten_draft would have judged it
on its own). The post-fix code correctly routes it to
`dropped_by_dedup_redundant[]`.

## Step 1 adversarial suite — STILL PASSES (no regression)

`scripts/test_i_gen_005_iter2_adversarial.py`: 40+ assertions still
pass. The verifier-helper changes from Step 1 are unaffected.

## Step 1 pytest sample — STILL PASSES

`tests/polaris_graph/test_b3_no_verified_sections.py` (4 tests) +
`tests/polaris_graph/test_m203_outline_collapse.py` (12 tests):
**16 passed in 4.03s**. SectionResult additions are backward-
compatible (default factory=list).

## Files for you to read

| Path | What changed |
|---|---|
| `src/polaris_graph/generator/multi_section_generator.py:79-118` | SectionResult field additions |
| `src/polaris_graph/generator/multi_section_generator.py:1456-1462` | initial population |
| `src/polaris_graph/generator/multi_section_generator.py:~3845-3850` | dedup-fail extension |
| `src/polaris_graph/generator/multi_section_generator.py:~3865-3880` | dedup-redundant tracking |
| `scripts/run_honest_sweep_r3.py:2703-2762` | consumer-side serialization rewrite |
| `scripts/test_i_gen_005_step15_telemetry.py` | unit test (NEW, 8 assertions) |
| `.codex/I-gen-005-step15/codex_diff_iter1.patch` | full 293-line diff |

## Questions for you

1. **Does this close your P1?** The unit test fixture proves the
   dedup-vs-strict-verify distinction is now captured. Does the
   schema (separate `dropped[]` and `dropped_by_dedup_redundant[]`)
   match what you wanted?

2. **Are there OTHER drop categories** I'm missing? E.g., when M-44
   regen replaces a section result entirely (`section_results[idx] =
   regen_result`), the prior result's dropped sentences are lost. Is
   that acceptable for now, or should regen also preserve historical
   drops?

3. **Should `total_in` be the rewritten_draft sentence count** (the
   original strict_verify input), or the post-dedup count? Currently
   I use `kept + strict_dropped + dedup_redundant` which approximates
   the rewritten_draft sentence count. Is that the right semantic?

4. **Any NEW findings** in the iter-1 diff? P0/P1 only — don't pick
   bone from egg.

5. **Approval to commit Step 1 + Step 1.5 together** on a fresh
   branch, then re-run smoke to verify the telemetry now matches the
   emitted report?

## Output schema (verbatim)

```yaml
verdict: APPROVE | REQUEST_CHANGES
diagnosis_alignment: TRUE | FALSE | PARTIAL
closes_step15_p1_from_smoke_review: TRUE | FALSE
p0_or_p1_findings_on_iter1:
  - severity: P0 | P1
    location: <file:line>
    issue: |
      (specific bug)
    proposed_fix: |
      (specific fix)
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
m44_regen_drop_preservation: REQUIRED | OPTIONAL | NOT_RELEVANT
  reasoning: |
    (your call)
approval_to_commit_and_smoke: YES | NO
if_no: |
  (must-fix items)
if_yes: ""
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

EMIT YAML ONLY. The unit test is offline and fast — please run it
yourself to confirm the assertions are real. Don't manufacture
findings to extend the cycle; cap is 5 and we have a real demo
deadline.
