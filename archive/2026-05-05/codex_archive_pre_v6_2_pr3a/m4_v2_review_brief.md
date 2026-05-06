M-4 v2 — re-review.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

Your M-4 v1 verdict: PARTIAL with 3 issues. All 3 integrated in v2.

## What changed

1. **Stable toolbar + partial re-render (HIGH fix).** Split
   `renderMatrixView` into:
   - `renderMatrixToolbar(ir, shell)` — rendered ONCE at view init,
     emits `<div class="matrix-toolbar">` + `<div id="matrix-results">`.
   - `renderMatrixResults(ir)` — rebuilds only `#matrix-results`
     and updates `#matrix-summary` text.
   Filter change handlers now call `renderMatrixResults(ir)`, NOT
   `renderMatrixView`. Toolbar `<input>` stays in the DOM with caret
   intact during typing.

2. **Search semantics widened (MEDIUM fix).** `clusterMatchesQuery`
   now also searches `claim.dose`, `claim.arm`, `claim.unit`,
   `claim.value` (stringified), `claim.source_tier`. Whitespace
   trimmed: `"   "` behaves like empty.

3. **Behavior tests (TESTS fix).** 3 new Node-eval splice tests:
   - `test_cluster_matches_query_searches_all_visible_claim_fields`
     (8 query/expectation pairs)
   - `test_apply_matrix_filters_composes_severity_tier_dose_and_query`
     (5-step composition trace)
   - `test_inspector_js_separates_toolbar_from_results_for_focus_retention`

Tests: 113 → 116. All green.

## Your job

Quick verification pass. Verdict: GREEN / STILL-PARTIAL / DISAGREE.

Spot-check:
- Are all 3 fixes integrated correctly?
- Does the toolbar stay stable during query typing?
- Are behavior tests actually testing behavior (not string presence)?
- Any new issues?
- M-5 ready?

## Output

Write to `outputs/codex_findings/m4_v2_review/findings.md`:

```markdown
# Codex re-review of M-4 v2

## Verdict
GREEN / STILL-PARTIAL / DISAGREE

## Fix integration
- [x/no] Stable toolbar + partial re-render
- [x/no] Search covers all visible claim fields + trim
- [x/no] Behavior tests (composition + focus retention)

## New issues
none / list

## Final word
GREEN to lock M-4 / STILL-PARTIAL with edits.
```

Be terse. Under 100 lines.
