# Codex iter 2 — I-gen-005 Step 1.5 telemetry fix (3 P1 fixes from iter 1)

## §8.3.1 canonical cap directive (verbatim)

```
HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by
  Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## All 3 of your iter-1 P1s are now closed

### P1 #1 — `contract_section_runner.py:683` (contract section telemetry)

**Status: FIXED.**

You flagged that contract sections instantiate SectionResult WITHOUT
populating `kept_sentences_pre_resolve` or `dropped_sentences_final`,
so PG_V30_PHASE2_ENABLED runs would serialize `total_in=0, kept=[], dropped=[]`.

The fix at `src/polaris_graph/generator/contract_section_runner.py:683-700`:

```python
# Rescued sentences (line 525) move from `dropped_sentences` to
# `kept_sentences`, so the FINAL dropped list excludes them.
rescued_ids = {id(sv) for sv in rescued}
final_dropped_svs = [
    sv for sv in dropped_sentences if id(sv) not in rescued_ids
]
result = section_result_cls(
    ...
    kept_sentences_pre_resolve=list(kept_sentences),
    dropped_sentences_final=final_dropped_svs,
)
```

This explicitly excludes rescued SVs from the final dropped list per
your proposed_fix wording: *"Remove rescued SVs from
dropped_sentences_final because they are final kept sentences."*

Unit test: `test_iter2_contract_kept_populated` + `test_iter2_contract_dropped_excludes_rescued`.

### P1 #2 — `multi_section_generator.py:1426` (M-41c policy drops)

**Status: FIXED.**

You flagged that M-41c post-filter drops were invisible — gone from
kept[], gone from dropped[], gone from dedup[]. The fix adds a new
SectionResult field:

```python
dropped_sentences_m41c_underframed: list[Any] = field(default_factory=list)
```

Populated at SectionResult construction (line ~1465) from
`report_dropped_m41c`. Included in `sentences_dropped` aggregate so
section-level totals match (line ~1452):

```python
m41c_drop_count = len(report_dropped_m41c) if report_dropped_m41c else 0
return SectionResult(
    ...
    sentences_dropped=report.total_dropped + m41c_drop_count,
    ...
    dropped_sentences_m41c_underframed=list(report_dropped_m41c or []),
)
```

Serialized in `run_honest_sweep_r3.py` as `dropped_by_m41c_underframed[]`
with its own `m41c_underframed_count` rollup.

Unit tests:
- `test_iter2_m41c_drops_serialized_separately`
- `test_iter2_m41c_drops_not_in_strict_verify_dropped`
- `test_iter2_m41c_drops_counted_in_total_dropped`
- `test_iter2_m41c_underframed_count_rollup`

### P1 #3 — `multi_section_generator.py:3887` (dedup totals mismatch)

**Status: FIXED.**

You flagged that for a 2→1 dedup consolidation:
- `sr.sentences_dropped += 1` (net length delta = 0 for 1:1 replacement)
- `dropped_sentences_dedup_redundant` got both originals (count = 2)
- Section-vs-artifact mismatch

The fix uses **set semantics** (ACTUAL removed originals):

```python
final_str_set = {sv.sentence for sv in final_svs}
actually_removed = [
    s for s in original_strs if s not in final_str_set
]
if actually_removed:
    sr.sentences_dropped += len(actually_removed)  # set delta, not net delta
    sr.dropped_sentences_dedup_redundant.extend(actually_removed)
```

Now `sr.sentences_dropped` increment equals the number of strings in
`dropped_sentences_dedup_redundant` for that section.

Unit tests:
- `test_iter2_dedup_section_total_matches_sentences_dropped`
- `test_iter2_dedup_multi_totals_match_section_sums`

## Unit test suite (PYTEST-COLLECTABLE this iter)

Moved from `scripts/` to `tests/polaris_graph/test_i_gen_005_step15_telemetry.py`.

**14 tests collected, 14 PASS** (was 0 collected per your iter-1 finding):

```
test_iter1_verified_in_kept PASSED
test_iter1_real_failure_in_dropped_with_reasons PASSED
test_iter1_dedup_redundant_not_in_dropped PASSED
test_iter1_section_totals PASSED
test_iter1_drop_reason_counts_excludes_dedup PASSED
test_iter1_dedup_redundant_count PASSED
test_iter2_contract_kept_populated PASSED                    # P1 #1
test_iter2_contract_dropped_excludes_rescued PASSED          # P1 #1
test_iter2_m41c_drops_serialized_separately PASSED           # P1 #2
test_iter2_m41c_drops_not_in_strict_verify_dropped PASSED    # P1 #2
test_iter2_m41c_drops_counted_in_total_dropped PASSED        # P1 #2
test_iter2_m41c_underframed_count_rollup PASSED              # P1 #2
test_iter2_dedup_section_total_matches_sentences_dropped PASSED  # P1 #3
test_iter2_dedup_multi_totals_match_section_sums PASSED      # P1 #3
```

## Regression checks (no regressions)

- **Step 1 adversarial suite:** 0 failures (40+ assertions)
- **`tests/polaris_graph/test_b3_no_verified_sections.py` + `test_m203_outline_collapse.py`:** 16 passed in 3.54s

## Files changed (iter 2)

| Path | Change |
|---|---|
| `src/polaris_graph/generator/multi_section_generator.py` | +`dropped_sentences_m41c_underframed` field; +`sentences_dropped` aggregation includes M-41c; dedup uses set semantics |
| `src/polaris_graph/generator/contract_section_runner.py` | Contract `SectionResult` now populates `kept_sentences_pre_resolve` + `dropped_sentences_final` (rescued SVs excluded from drops) |
| `scripts/run_honest_sweep_r3.py` | Serializer adds `dropped_by_m41c_underframed[]` + `m41c_underframed_count` rollup |
| `tests/polaris_graph/test_i_gen_005_step15_telemetry.py` | NEW — 14 pytest tests covering iter-1 + iter-2 fixes |
| `.codex/I-gen-005-step15/codex_diff_iter2.patch` | 400-line full diff |

## Files for you to read

1. `src/polaris_graph/generator/contract_section_runner.py:683-704` (P1 #1)
2. `src/polaris_graph/generator/multi_section_generator.py:102-128` (field defs)
3. `src/polaris_graph/generator/multi_section_generator.py:1449-1475` (M-41c populate)
4. `src/polaris_graph/generator/multi_section_generator.py:~3855-3895` (dedup set-semantics)
5. `scripts/run_honest_sweep_r3.py:2703-2790` (consumer)
6. `tests/polaris_graph/test_i_gen_005_step15_telemetry.py` (14 tests)

## Questions for you

1. **Do these three diffs CLOSE all three iter-1 P1s?**
2. **Any NEW P0/P1** I missed? (e.g., M-44 regen historical drops you
   marked OPTIONAL — am I right to NOT preserve them?)
3. **Is the section_sentences_dropped_counter vs serialized total
   semantics correct now**? My unit test asserts they match for the
   2→1 dedup case; please confirm by reading the dedup path.
4. **Approval to commit Step 1 + Step 1.5 together** and re-run smoke?

## Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
diagnosis_alignment: TRUE | FALSE | PARTIAL
closes_iter1_p1s:
  contract_section: TRUE | FALSE
  m41c_underframed: TRUE | FALSE
  dedup_totals: TRUE | FALSE
p0_or_p1_findings_on_iter2:
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
approval_to_commit_and_smoke: YES | NO
if_no: |
  (must-fix items; iter 2 of 5, 3 iters remaining before force-APPROVE)
if_yes: ""
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

EMIT YAML ONLY.
