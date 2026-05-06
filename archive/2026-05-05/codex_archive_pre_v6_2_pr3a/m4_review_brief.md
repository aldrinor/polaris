M-4 Evidence Inspector View 2 (Contradiction Matrix) — code review.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

M-1, M-2, M-3 GREEN-locked. Now M-4: View 2 (Contradiction Matrix),
the first-class disagreement-disclosure view per FINAL_PLAN.md. No
competitor surfaces contradictions as a primary view — this amplifies
the audit-grade moat.

## What landed

Files modified:
- `scripts/static/inspector/inspector.js` (+~190 lines for matrix
  renderer + helpers + interaction wiring)
- `scripts/static/inspector/inspector.css` (+~150 lines for
  matrix-toolbar, matrix-row, matrix-claim styles)
- `tests/polaris_graph/test_inspector_router.py` (+5 tests)

Behavior:
- Toolbar: severity / tier / dose dropdowns + free-text search +
  clear button + "N/14 clusters" live summary
- Each row: severity badge + subject·predicate + value range +
  per-cluster tier badges + Δ (absolute) + rel% + claim count +
  recommended_action
- Click row → expand to show ALL claims side-by-side (tier,
  evidence_id, value, dose, arm, context_snippet, sanitized URL)
- Keyboard: Enter/Space to expand, role="button", aria-expanded
- Live filter on input + change events; reuses validateTier,
  validateSeverity, sanitizeUrl, escHtml from M-3

Tests: 108 → 113.

E2E smoke: run-14 returns 14 clusters with 8 distinct tiers (T1-T7
+ UNKNOWN), 5+ doses, severity 'high'.

## Your job

Code review for M-4. Verdict: GREEN / PARTIAL / DISAGREE.

## Specific things to validate

1. **Matrix correctness.** Does the filter logic compose correctly
   (severity AND tier AND dose AND query)? Edge cases:
   - Cluster with mixed tier claims: filtering by T1 includes the
     cluster if ANY claim is T1
   - Cluster with multiple doses: filtering by "10 mg" includes the
     cluster if ANY claim has dose "10 mg"
   - Empty filter values fall back to "all"

2. **Search semantics.** clusterMatchesQuery scans subject, predicate,
   recommended_action, claim.evidence_id, claim.source_url,
   claim.context_snippet. Is this the right surface, or am I missing
   anything?

3. **Performance.** The renderer rebuilds the entire matrix on every
   filter change (full innerHTML replace). For 14 clusters this is
   fine, but for Phase B/C with hundreds of clusters this would be
   sluggish. Should I diff-render now or defer?

4. **State management.** _matrixState is module-scoped (lives across
   re-renders) and `_matrixState.expanded` is a Set. Toggling expand
   updates DOM directly + state. Re-render preserves expanded state.
   Any concurrency or staleness issues?

5. **Cluster ordering.** Currently iterates over IR
   contradictions[] in original order (the order Codex emits them).
   Should I sort by severity or relative_difference DESC? The 14
   run-14 clusters all have severity=high so it doesn't matter for
   the demo, but Phase B may have mixed severities.

6. **Accessibility.** rows are <li> with role="button" + tabindex=0
   + aria-expanded. Keyboard: Enter/Space toggles. Filter <select>
   and <input> have aria-label. Anything missing?

7. **CSS.** matrix-row.expanded shows .matrix-row-claims via
   `display: flex`. matrix-toolbar wraps on small screens. Any
   layout issues at < 800px width?

8. **Cross-view interaction.** When a user clicks a citation in the
   Report view (M-3) and the right pane shows contradiction clusters,
   should clicking one of those clusters jump to the Matrix view +
   pre-expand that cluster? (Phase B nice-to-have, but should the
   plumbing be in place now?)

9. **Anything else you'd push back on.**

## Output

Write to `outputs/codex_findings/m4_review/findings.md`:

```markdown
# Codex review of M-4

## Verdict
GREEN / PARTIAL / DISAGREE

## Filter correctness
Edge cases and composition.

## Search semantics
Coverage gaps if any.

## Performance / state
Concrete issues at Phase B scale.

## Accessibility
Missing attributes / focus issues.

## Specific issues
File:line references.

## Recommended changes
If PARTIAL.

## M-5 readiness
Is the matrix done well enough that Frame Coverage view can build on
the same patterns?

## Final word
GREEN to lock M-4 / PARTIAL with edits / DISAGREE.
```

Be terse. Under 300 lines.
