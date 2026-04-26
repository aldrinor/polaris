# Codex review of M-4

## Verdict
PARTIAL

## Filter correctness
`applyMatrixFilters()` composes correctly as `severity AND tier AND dose AND query` and the tier/dose checks are `ANY-claim` membership checks, not row-level equality checks (`scripts/static/inspector/inspector.js:576-586`). Mixed-tier clusters are present in run-14, so the T1/T2 inclusion behavior is real and works.

The dose edge case is mostly theoretical under the current producer: contradiction clustering already groups by `(subject, predicate, unit, dose)`, so mixed-dose clusters should not be emitted today (`src/polaris_graph/retrieval/contradiction_detector.py:581-623`). Empty filter values correctly fall back to `"all"`.

## Search semantics
Current search covers `subject`, `predicate`, `recommended_action`, `claim.evidence_id`, `claim.source_url`, and `claim.context_snippet` (`scripts/static/inspector/inspector.js:554-565`). That matches the placeholder, but it omits rendered claim fields that users will reasonably expect to be searchable: `dose`, `arm`, `value`, `unit`, and `source_tier` (`scripts/static/inspector/inspector.js:612-616`).

I would treat that as a semantics gap, not a redesign. Also trim the query before matching; `"   "` should behave like empty.

## Performance / state
Do not diff-render now. For Phase A / early Phase B, the current full rebuild is acceptable. If you want a cheap scaling step, add a small input debounce and precompute a lowercased search blob per cluster.

State shape is otherwise fine. `_matrixState.expanded` preserving expansion across re-renders is the right tradeoff. I do not see a concurrency problem in the current single-run page model.

## Accessibility
Rows have the minimum viable keyboard contract: `tabindex`, `role="button"`, `aria-expanded`, Enter/Space toggle (`scripts/static/inspector/inspector.js:594, 698-715`). Toolbar controls are labeled.

What is missing is not row keyboarding; it is focus continuity. The live-search path destroys and recreates the focused `<input>` on every keystroke, so keyboard users lose focus/caret mid-search (`scripts/static/inspector/inspector.js:672-687`). Optional polish later: add `aria-controls` from row to claims list and a visible `:focus-visible` style.

## Specific issues
- `scripts/static/inspector/inspector.js:672-687`  
  Live search re-renders the entire shell on every `input` event. Because `shell.innerHTML = html` replaces the active `<input>`, focus/caret will drop after each keystroke. This is the main reason I would not GREEN-lock M-4 yet.

- `scripts/static/inspector/inspector.js:554-565`  
  `clusterMatchesQuery()` does not search `claim.dose`, `claim.arm`, `claim.value`, `claim.unit`, or `claim.source_tier`, even though those fields are visible in expanded rows. Free-text search will feel arbitrarily incomplete.

- `tests/polaris_graph/test_inspector_router.py:365-377`  
  The new “filter” test is only a string-presence test. It does not validate AND-composition, ANY-tier inclusion, ANY-dose inclusion, clear/reset behavior, or the input-focus path. This implementation bug would pass as written.

## Recommended changes
1. Preserve focus/caret when typing in the query box. Easiest fix: keep the toolbar/input node stable and only re-render the results list + summary, or explicitly restore focus/selection after render.
2. Expand `clusterMatchesQuery()` to include the rendered claim fields and trim whitespace before matching.
3. Add one behavior-level test for filter composition and one UI-level regression test for query typing/focus retention.

## M-5 readiness
Mostly yes. The matrix pattern is reusable, and keeping original IR order is acceptable because the producer already severity-sorts upstream (`src/polaris_graph/retrieval/contradiction_detector.py:621-623`). I would not add cross-view jump plumbing yet, but when you do, make `cluster_id` the shared deep-link key instead of wiring view-specific DOM logic twice.

## Final word
PARTIAL with small edits. Fix the query-box re-render/focus bug, widen search semantics to cover the fields you already display, and tighten the tests. After that, M-4 is strong enough to lock and M-5 can build on the same interaction pattern.
