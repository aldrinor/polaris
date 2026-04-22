M-48 pass-2 audit — closes pass-1 BLOCKED finding.

## Pass-1 verdict (commit `5e0b447`)

BLOCKED. Blocker: label_rows_with_population_scope() + _m42e_detect_
primary_for_anchor() + v28_retrieval_preflight.py all read
`row.get("title")`, but live retriever rows use `statement` for the
candidate title (live_retriever.py:1157). Labeler + preflight would
return empty for every real sweep row.

Non-blocker findings: variant schema handling sound; query emission
correct; preflight exit-code contract OK but report could include
statement snippets; sweep integration placed at the right stage.

## Pass-2 (commit `e6fd147`)

Fix:
- `evidence_selector._row_title_text`: shared accessor reading
  title / statement / source_title in that precedence order.
- `_m42e_detect_primary_for_anchor` uses accessor.
- `_m42c_row_is_mechanism_rich` uses accessor.
- `label_rows_with_population_scope` uses accessor inline.
- `v28_retrieval_preflight.py` uses accessor inline (+ example_titles
  now sourced via accessor, answering your non-blocker note).

New regression tests:
- `test_live_row_with_statement_only_gets_labeled` — live-schema row
  (statement=cand.title, no `title` key) → labeled correctly.
- `test_m42e_detect_primary_works_on_live_rows` — same fix applied
  at M-42e detector (would have caught this at M-42e time).
- `test_title_takes_precedence_when_both_present` — backwards-compat.

191/191 tests pass across M-35/41/42(a+b/c/d/e)/43/46/48.

## Your pass-2 task

Read the diff between `5e0b447` and `e6fd147`. Verify:
1. Blocker closed: accessor precedence title > statement > source_title
   correct? Covers the live-row schema?
2. All 3 read sites switched (labeler, M-42e, M-42c, preflight)?
3. Backwards-compat: fixture rows with `title` still work?
4. New tests adequate? Any missed edge case (both title and statement
   empty; unicode in statement; etc.)?

Write verdict to `outputs/codex_findings/m48_code_audit_pass2/findings.md`.

Budget: this is plan-pass-2 of the code audit for M-48 (not the plan
review). Independent counter from plan-review ping-pong.
