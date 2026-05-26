# Codex iter 3 — I-gen-005 Step 1.5 (failed dedup rewrite accounting)

## §8.3.1 canonical cap directive (verbatim)

```
HARD ITERATION CAP: 5 per document. This is iter 3 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by
  Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Iter-2 verdict carry-forward

You CONFIRMED all 3 iter-1 P1s closed:
- `closes_iter1_p1s.contract_section: TRUE`
- `closes_iter1_p1s.m41c_underframed: TRUE`
- `closes_iter1_p1s.dedup_totals: TRUE`

And found ONE new P1 (line 3882): when a fact-dedup rewrite candidate
FAILS strict_verify, the failed SV is appended to
`dropped_sentences_final` but `sr.sentences_dropped` is NOT incremented
for it. That recreates the section-vs-artifact total mismatch on the
failed-rewrite branch.

## Iter-3 fix (your exact prescription)

`src/polaris_graph/generator/multi_section_generator.py:~3878-3892`:

```python
if rewrite_candidates:
    rewrite_report = strict_verify(
        "\n".join(rewrite_candidates), evidence_pool,
    )
    accepted_rewrite_svs = list(rewrite_report.kept_sentences)
    rewrites_re_verified_pass += len(accepted_rewrite_svs)
    rewrites_re_verified_drop += (
        len(rewrite_candidates) - len(accepted_rewrite_svs)
    )
    # Append failed rewrites to dropped_sentences_final (iter-2)
    sr.dropped_sentences_final.extend(
        rewrite_report.dropped_sentences,
    )
    # I-gen-005 Step 1.5 iter-3 (Codex iter-2 P1): increment
    # sentences_dropped for each failed rewrite candidate so
    # multi.total_sentences_dropped matches what the serializer
    # reports as `dropped[]` for this section.
    sr.sentences_dropped += len(
        rewrite_report.dropped_sentences,
    )
```

## Regression test (your exact prescription)

`tests/polaris_graph/test_i_gen_005_step15_telemetry.py::test_iter3_failed_dedup_rewrite_accounting`:

Walks through your exact case:
- 2 originals (A, B) → consolidated rewrite C → C fails strict_verify
- A, B both → `dropped_sentences_dedup_redundant` (size 2)
- C → `dropped_sentences_final` (size 1)
- Asserts: `total_dropped` (serialized) == `sr.sentences_dropped` ==
  `multi.total_sentences_dropped` == 3

Post-iter-3 test result: PASS.

## Test suite status

```
15 passed in 2.75s   (was 14 in iter 2; added test_iter3_failed_dedup_rewrite_accounting)
```

## Regression checks

- Step 1 adversarial suite: 0 failures (40+ assertions)
- `tests/polaris_graph/test_b3_no_verified_sections.py` + `test_m203_outline_collapse.py`: 16 passed

## Files for you to re-read

| Path | What changed since iter 2 |
|---|---|
| `src/polaris_graph/generator/multi_section_generator.py:3878-3892` | +`sr.sentences_dropped += len(rewrite_report.dropped_sentences)` |
| `tests/polaris_graph/test_i_gen_005_step15_telemetry.py` | +`test_iter3_failed_dedup_rewrite_accounting` |
| `.codex/I-gen-005-step15/codex_diff_iter3.patch` | 411-line cumulative diff |

## Questions for you

1. **Does this close your iter-2 P1** (failed dedup rewrite accounting)?
2. **Any OTHER accounting edge cases** I'm missing? Walk through the
   full set of states one more time — strict_verify drops, M-41c
   drops, dedup-redundants (1:1 / 2:1 / 2:2), failed-rewrite — and
   confirm `sr.sentences_dropped` matches `verification_details.json`
   `total_dropped` for each.
3. **Approval to commit Step 1 + Step 1.5 together** and re-run smoke
   to verify the on-disk telemetry matches the emitted report.md?
4. **Any NEW P0/P1** in the iter-3 diff?

## Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
diagnosis_alignment: TRUE | FALSE | PARTIAL
closes_iter2_p1_failed_rewrite_accounting: TRUE | FALSE
p0_or_p1_findings_on_iter3:
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
  (must-fix items; iter 3 of 5, 2 iters remaining before force-APPROVE)
if_yes: ""
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

EMIT YAML ONLY.
