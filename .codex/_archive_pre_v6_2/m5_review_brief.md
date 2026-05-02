M-5 Evidence Inspector View 3 (Frame Coverage Manifest) — code review.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

M-1, M-2, M-3, M-4 GREEN-locked. Now M-5: View 3 (Frame Coverage
Manifest), per FINAL_PLAN.md "the antidote to ChatGPT DR's silent
omissions" — every contract slot rendered with pass/partial/gap.

## What landed

Files modified:
- `scripts/static/inspector/inspector.js` (+~190 lines for coverage
  renderer + helpers + interaction)
- `scripts/static/inspector/inspector.css` (+~200 lines for
  coverage-summary, coverage-bar, coverage-warning, coverage-row,
  coverage-action-btn etc.)
- `tests/polaris_graph/test_inspector_router.py` (+5 tests)
- `tests/polaris_graph/test_inspector_browser.py` (+3 tests)

Behavior:
- Visual coverage bar at top (pass/partial/gap/pipeline-fault
  segments scaled by count)
- V30 retrieval-coverage warning preserved verbatim from IR
- Section-grouped (Efficacy, Mechanism, Regulatory) with counts
- Per-row: status badge + entity_id + section + subsection_title +
  identifiers (DOI/PMID linked) + failure_reason + required_fields
  chips + available_artifacts chips + retrieval_attempt_log preview
- Gap-eligible rows expose resolve-gap button that emits a
  polaris:resolve-gap CustomEvent (Phase A wiring, Phase B replaces
  with modal + POST)

Tests: 121 → 129. 3 real-browser tests verify the visual bar +
V30 warning, section grouping, and CustomEvent emission on gap
button click.

## Your job

Code review for M-5. Verdict: GREEN / PARTIAL / DISAGREE.

## Specific things to validate

1. **FINAL_PLAN compliance.** "Frame Coverage Manifest = literal
   antidote to ChatGPT DR's silent omissions." Does this view
   actually expose every contract slot (15/15 in run-14) with
   declared status, or is anything hidden?

2. **Visual coverage bar correctness.** Segments are flex:count/total.
   For run-14 (14 pass + 1 fail_min_fields + 0 partial + 0
   pipeline_fault), the bar should show ~93% green + ~7% red. Right?

3. **V30 semantics warning placement.** The warning is rendered
   AFTER the coverage bar. Should it be BEFORE so users see the
   caveat first? Or is the current placement fine because the bar
   is more visually scannable?

4. **Section grouping.** I group by `entry.section || "(no section)"`.
   In run-14 all 15 entities have a section, so the fallback never
   fires. Good?

5. **Identifiers exposure.** I link DOI to https://doi.org/{doi}
   and PMID to https://pubmed.ncbi.nlm.nih.gov/{pmid}/. Both pass
   through sanitizeUrl. Are there other identifiers I should
   expose (e.g., crossref links, NCT trial IDs if present)?

6. **Required vs available artifacts chips.** Both shown. Should I
   visually differentiate? Currently identical chip styling.

7. **Operator workflow.** Phase A: emits CustomEvent on click.
   Phase B will hook a modal. Is the CustomEvent contract right
   (just `{entity_id}`)? Or should it also pass the full entry
   payload so operator tooling has context?

8. **Retrieval log preview shows first 4 attempts.** Good or
   should it show all? Run-14's worst-case is ~6 attempts per
   entity.

9. **A11y.** role="img" + aria-label on the coverage bar.
   coverage-warning has role="note". Action buttons have
   aria-label. Anything missing?

10. **Cross-view linking.** Phase A: clicking a coverage row
    doesn't jump anywhere. Phase B nice-to-have: click → jump
    to Report view + scroll to that subsection. Should I plumb
    the cluster_id-equivalent for coverage now (entity_id is the
    natural key)?

11. **Anything else you'd push back on.**

## Output

Write to `outputs/codex_findings/m5_review/findings.md`:

```markdown
# Codex review of M-5

## Verdict
GREEN / PARTIAL / DISAGREE

## FINAL_PLAN compliance
Does the view actually surface every silent omission?

## Specific issues
File:line bugs / gaps.

## Recommended changes
If PARTIAL.

## M-6 readiness
Is the IR + render pattern ready for the Methods + Provenance Bundle?

## Final word
GREEN to lock M-5 / PARTIAL with edits / DISAGREE.
```

Be terse. Under 300 lines.
