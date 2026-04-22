# M-48 Code Audit Pass 2 Findings

Verdict: APPROVED.

## Findings

No blocking findings.

## Verification

1. Blocker closure: confirmed. `evidence_selector._row_title_text()` reads title-like text in the requested precedence order: `title` > `statement` > `source_title` > `""`. This covers the live retriever schema at `src/polaris_graph/retrieval/live_retriever.py:1157`, where candidate titles are emitted as `statement: cand.title[:300]` and no `title` key is present.

2. Read-site migration: confirmed.
   - `src/polaris_graph/retrieval/evidence_selector.py:303` uses `_row_title_text()` in `_m42c_row_is_mechanism_rich()`.
   - `src/polaris_graph/retrieval/evidence_selector.py:325` uses `_row_title_text()` in `_m42e_detect_primary_for_anchor()`.
   - `src/polaris_graph/retrieval/primary_trial_expander.py:243` uses equivalent `title` / `statement` / `source_title` precedence in `label_rows_with_population_scope()`.
   - `scripts/v28_retrieval_preflight.py:137` uses equivalent precedence for any-title coverage and `example_titles`.

3. Backwards compatibility: confirmed. Existing title-based fixture rows still pass, and `test_title_takes_precedence_when_both_present` verifies that `title` wins when both `title` and `statement` are populated.

4. Test adequacy: adequate for the pass-1 blocker. The new live-row tests cover the exact production shape that failed: `statement` populated, no `title`. The M-42e detector regression would have caught the earlier detector miss. The precedence regression protects existing fixture and retriever rows that still use `title`.

## Non-Blocking Notes

- Edge-case coverage could be expanded with a direct `source_title` fallback test and a whitespace-only `title` plus populated `statement` test. I do not consider this blocking because live rows omit `title` entirely and empty-string `title` already falls through to `statement`; the remaining gap is mostly defensive hardening around malformed rows.
- Unicode in `statement` is not a special risk here: matching uses Python string `.lower()` and substring checks, and the configured anchors are ASCII trial identifiers.
- Rows with all title-like fields empty now deterministically produce `""`, so they remain unlabeled and do not create false primary detections.

## Tests Run

`python -m pytest tests/polaris_graph/test_m48_anchor_variants_and_scope.py tests/polaris_graph/test_m42e_primary_trial_floor.py tests/polaris_graph/test_m42c_mechanism_floor_and_prompt.py tests/polaris_graph/test_m46_selector_no_bypass.py -q`

Result: 78 passed, 1 pytest cache warning caused by denied access to `.pytest_cache`.
