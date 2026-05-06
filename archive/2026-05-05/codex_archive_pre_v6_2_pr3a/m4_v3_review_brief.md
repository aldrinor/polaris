M-4 v3 — final GREEN check.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

Your M-4 v2 verdict: STILL-PARTIAL — runtime fixes correct, but the
focus-retention test was structural (string assertion) not behavioral.

## What changed in v3

New file: `tests/polaris_graph/test_inspector_browser.py`. 5 Playwright
tests against the real FastAPI live_server (background uvicorn thread):

1. **test_inspector_page_loads_in_real_browser** — sanity: chromium
   loads /inspector/clinical_tirzepatide_t2dm, matrix-toolbar present.

2. **test_matrix_query_input_preserves_focus_on_typing** — types
   "body" with 30ms delay; asserts input_value=="body",
   activeElement.tagName=="INPUT", data-matrix-filter=="query",
   selectionStart==4.

3. **test_matrix_dom_identity_preserved_across_filter_changes** —
   tags the <input> with a custom dataset marker BEFORE typing,
   asserts the marker survives multiple keystrokes (proves the DOM
   node is the same element, not replaced).

4. **test_matrix_results_update_on_filter_change** — types
   "body weight", waits for #matrix-summary to show a smaller
   filtered count.

5. **test_matrix_clear_button_resets_query** — types nonsense,
   asserts "0 / 14"; clicks clear, asserts "14 / 14" and input is
   empty.

121/121 tests green (was 116). Tests are skipif-gated on chromium
availability so CI without the browser is unaffected.

## Your job

Final verdict on M-4. GREEN / STILL-PARTIAL / DISAGREE.

Quick spot-check:
- Tests 2, 3 actually prove DOM identity / focus retention / caret?
- Tests 4, 5 actually prove behavior (not string presence)?
- Any new issues?
- M-5 ready?

## Output

Write to `outputs/codex_findings/m4_v3_review/findings.md`:

```markdown
# Codex final review of M-4 v3

## Verdict
GREEN / STILL-PARTIAL / DISAGREE

## Behavior test verification
- [x/no] Real DOM identity assertion
- [x/no] Real focus/caret retention
- [x/no] Real results update on filter
- [x/no] Real clear button reset

## New issues
none / list

## Final word
GREEN to lock M-4 / STILL-PARTIAL with edits.
```

Be terse. Under 80 lines.
