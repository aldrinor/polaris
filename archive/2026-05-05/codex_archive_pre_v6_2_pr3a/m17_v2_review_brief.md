M-17 v2 — re-review.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

Your M-17 v1 verdict: PARTIAL with one specific edit:

> Missing exported-report check: `check_citation_health()` only
> walks bibliography + `verified_report` tokens, but shipped
> `report.md` `[N]` citations are a first-class contract for the
> inspector/audit bundle. Add an ERROR/red check for any
> `report.md` citation number with no bibliography entry.

Integrated in v2 (commit 59b4f0f).

## What changed in v2

`citation_health.py`:
- New `CitationIssueCode.BROKEN_REPORT_CITATION` (ERROR severity).
- New `_check_report_citations(report_md, bibliography)` helper:
  - Strips fenced code blocks (```...```) before scanning so
    documentation examples in code don't surface.
  - Strips inline backtick spans (`...`) so usage hints don't
    surface.
  - Strips provenance tokens (`[#ev:...]`) so the integers inside
    `[#ev:ev_001:5-10]` are not misread as `[N]` markers.
  - Walks bare `[N]` patterns; for each unique N, checks against
    the set of bibliography nums; reports ERROR if missing.

The check fires alongside the existing token-level broken_ref
check — they're orthogonal:
  - broken_ref → token's evidence_id not in bibliography
    (verified_report integrity)
  - broken_report_citation → bibliography lookup `[N]` not in
    bibliography (renderer contract)

Both can fail independently.

Tests added (5 new):
  + test_broken_report_citation_surfaces_as_error
    (report mentions [3] and [99]; only [1]/[2] in bibliography
    → 2 ERROR alerts, status=red)
  + test_intact_report_citations_do_not_surface
  + test_provenance_token_inner_integers_not_treated_as_citations
    (`[#ev:ev_001:5-10]` doesn't trigger broken_report_citation
    on '5')
  + test_code_block_citations_do_not_surface
  + test_inline_code_citations_do_not_surface

Module: 25/25 citation_health tests green.

## Your job

Final verdict on M-17. GREEN / PARTIAL / DISAGREE.

If GREEN, M-17 locks and Phase C continues to M-18 / M-23.

## Output

Write to `outputs/codex_findings/m17_v2_review/findings.md`:

```markdown
# Codex re-review of M-17 v2

## Verdict
GREEN / PARTIAL / DISAGREE

## v1 fix integration
- [x/no] report.md `[N]` citations checked against bibliography nums
- [x/no] code blocks + provenance tokens stripped (no false positives)
- [x/no] severity = ERROR (red status)

## Final word
GREEN to lock M-17 + proceed / PARTIAL with edits.
```

Be terse. Under 80 lines.
