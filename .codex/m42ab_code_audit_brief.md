You are auditing M-42a+b — second item in the M-42 bundle per
Codex plan approval. Two coordinated changes: M-42a is a
prompt-rule extension; M-42b is a deterministic trial-table +
timeline builder.

## Plan reference

`outputs/audits/v25/fix_plan.md` items M-42a and M-42b. Codex plan
approval at `outputs/audits/v25/codex_plan_review_pass3.md` — pass-3
was APPROVED with explicit source-content contract: primary source
is `EvidenceRow.direct_quote`; fallback options are `statement` for
disambiguation, refetch via new `refetch_for_extraction(url)`
helper, or skip row.

## Diff

Commit at HEAD. Four files:

1. `src/polaris_graph/generator/multi_section_generator.py`:
   - **M-42a**: rule #12c inserted between #12b (M-38) and
     EVIDENCE TIER DISCIPLINE. Anaphoric + group bypass patterns.
     Examples use `[STUDY NAME]` / `[INTERVENTION]` / etc.
     placeholders (no drug names) to satisfy M-32 discipline.
   - **M-42b** deterministic builder: `_m42b_extract_from_quote`
     (7-pattern regex extractor), `_m42b_year_from_row`,
     `_m42b_find_ref_num`, `build_trial_summary_and_timeline_from_evidence`.
   - `MultiSectionResult` gets `trial_timeline_text` field.
   - `generate_multi_section_report` accepts `primary_trial_anchors`
     kwarg. New behavior: try M-42b deterministic first; if <2
     rows, fall back to M-36 LLM path.

2. `src/polaris_graph/retrieval/live_retriever.py`:
   - New public `refetch_for_extraction(url, max_chars=2000)`.
   - Exact signature Codex recommended in pass-3 review.

3. `scripts/run_honest_sweep_r3.py`:
   - Passes `primary_trial_anchors=_primary_anchors` into
     `generate_multi_section_report`.
   - Emits "### Trial Program Timeline" after "### Trial Summary"
     when the deterministic builder produces both.

4. `tests/polaris_graph/test_m42ab_anaphoric_and_builder.py`: 22
   tests covering rule #12c presence + ordering, builder full-frame
   extraction, partial-frame, refetch fallback, invalid citation
   drop, no-anchor no-op, refetch signature, schema fields.

## What to verify

1. **M-42a placeholder-only discipline**: the rule body uses
   [STUDY NAME], [INTERVENTION_ARM], [COMPARATOR_ARM], [ENDPOINT],
   [SAMPLE_SIZE], [TIMEPOINT], [EFFECT_SIZE]. Does ANY drug name
   slip through? The full-suite M-32 test passes, but eyeball.

2. **Source-content contract honored**: M-42b reads `direct_quote`
   first, `statement` only for fallback, NEVER generated prose.
   Trace the builder function to confirm.

3. **Refetch integration**: `refetch_for_extraction` is imported
   in a try/except so the builder works without it (e.g. in tests
   that monkey-patch). Does the import failure mode degrade
   gracefully?

4. **Citation validation**: `_m42b_find_ref_num` matches by
   evidence_id OR URL. Returns None if row has no matching biblio
   entry. Row dropped. Test coverage confirms.

5. **Builder threshold**: >=4 of 7 cells populated per row. Is 4
   the right threshold? Codex plan review said "at least 4
   populated frame cells per row". Confirm.

6. **Timeline chronological sort**: sorts by `(year_int, trial)`
   ascending; rows with year=0 (unknown) go to end. Reasonable?

7. **LLM fallback path**: when deterministic builder returns empty
   (<2 rows), M-36 `_call_trial_summary_table` runs. Not broken?

8. **Generator integration**: the M-42b builder receives `evidence`
   parameter (the flat evidence list). Is this the same as
   `selected_rows`? (Yes — `evidence` in the generator IS the
   selected subset from evidence_selector.)

## What counts as a blocker vs medium

- **BLOCKER**: any path where M-42b emits a table with fabricated
  cells (regex matching in unrelated text); any path where refetch
  fails and the builder crashes instead of returning empty; any
  test that fails; any regression of M-32 placeholder discipline.
- **MEDIUM**: regex tightening (e.g. baseline detection misses
  common patterns), threshold tuning (4 cells vs 5), timeline sort
  choice.
- **LOW**: naming / comments.

## Deliverable

Write `outputs/codex_findings/m42ab_code_audit/findings.md` with:
- Final verdict (READY | BLOCKED | CONDITIONAL)
- Blockers (zero if READY)
- Mediums
- Per-item assessment: M-42a prompt rule + M-42b builder

Keep under 1500 words.
