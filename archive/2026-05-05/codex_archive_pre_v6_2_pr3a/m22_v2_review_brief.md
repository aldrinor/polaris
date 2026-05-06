M-22 v2 — re-review.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

Your M-22 v1 verdict: DISAGREE — 5 specific bugs.

1. Speaker notes rendered as visible HTML (LAW II BLOCKER)
2. Synthetic meta-bullets indistinguishable from verified prose
   (LAW II BLOCKER)
3. URL scheme not sanitized (javascript: survived)
4. Inline evidence_id markers drifted from citations footer
5. Appendix-budget reservation always subtracted 3

All 5 integrated in v2 (commit c35c137).

## What changed in v2

`slide_deck.py`:
- SlideBullet now has `is_synthetic: bool` (default False).
  Meta-slide bullets (scope/contradictions/limitations) marked
  is_synthetic=True. Section content bullets stay False.
- render_deck_html no longer renders `<aside>` notes. Speaker
  notes serialize as `data-notes` attribute on the <section>
  container only — invisible to viewers but available to PPTX
  exporters.
- Synthetic bullets get `data-synthetic="true"` attribute + a
  visible "[meta]" badge so customers see the disclosure.
- New `_safe_url` restricts hrefs to http/https/mailto. Unsafe
  schemes (javascript:, data:, file:, etc.) render as escaped
  text with "(unsafe scheme; link disabled)" annotation.
- Inline `[ev_xxx]` markers now filtered against the slide's
  citation set; unresolved evidence_ids dropped from visible
  inline display (the footer remains canonical).
- Appendix-budget reservation: tail = 2 + (1 if contradictions
  else 0). With max_slides=20 + no contradictions, the deck
  fills to 20 (was 19 in v1).

Tests added (6):
- test_speaker_notes_not_rendered_as_visible_html
- test_synthetic_bullets_carry_disclosure_attribute
- test_javascript_url_is_not_rendered_as_link
- test_data_url_is_not_rendered_as_link
- test_unresolved_evidence_id_dropped_from_inline_markers
- test_appendix_budget_reservation_with_no_contradictions

Module: 27/27 slide_deck tests green.

## Your job

Final verdict on M-22. GREEN / PARTIAL / DISAGREE.

If GREEN, M-22 v2 locks. PPTX export ships in v3 once we have a
production python-pptx dependency.

## Output

Write to `outputs/codex_findings/m22_v2_review/findings.md`:

```markdown
# Codex re-review of M-22 v2

## Verdict
GREEN / PARTIAL / DISAGREE

## v1 fix integration
- [x/no] speaker notes not visible HTML (LAW II)
- [x/no] synthetic bullets marked + disclosed (LAW II)
- [x/no] URL scheme sanitized (javascript:/data: blocked)
- [x/no] unresolved evidence_ids filtered from inline markers
- [x/no] appendix-budget reservation correct

## Final word
GREEN to lock M-22 + proceed / PARTIAL with edits.
```

Be terse. Under 80 lines.
