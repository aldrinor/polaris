M-22 v1 — first review.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

M-22 ships the citation-bound slide deck export per FINAL_PLAN
Phase C deliverable #5. v1 is the deterministic slide-content
builder + HTML/JSON renderers. PPTX/PDF deferred to v2 (operator
can run HTML through wkhtmltopdf for pilot).

LAW II is the central correctness claim: every visible bullet on
every slide must be a VERIFIED sentence verbatim, never
paraphrased; every citation must back-link to a real
bibliography entry; nothing in the rendered HTML can be free-form
prose.

## What changed in v1 (commit 1aab9f7)

New module: `src/polaris_graph/audit_ir/slide_deck.py`

Slide order:
  1. Title (run question + run identity in speaker notes)
  2. Scope + method
  3..N. Per-section content (visible bullets capped at
     max_bullets_per_slide=5; overflow → notes)
  N+1. Contradictions (only if clusters present)
  N+2. Limitations (drop reasons, tier mix)
  N+3. Appendix (full bibliography)

Public API:
- build_slide_deck(ir, max_bullets_per_slide=5, max_slides=20)
- deck_to_dict(deck) — JSON projection
- render_deck_html(deck) — self-contained HTML page

LAW II invariants (covered by tests):
- every visible bullet carries claim_id
- bullet text is verified sentence verbatim
- citations resolve to real bibliography entries (no orphans)
- HTML render includes data-claim-id on every <li>
- HTML render escapes user content (XSS defense)

Tests (21): error-path, deck structure, LAW II, overflow,
citation correctness, contradictions/limitations presence,
slide cap, serialization, HTML render, real-data smoke.

## Your job

Verdict on M-22 v1. GREEN / PARTIAL / DISAGREE.

Look for:

1. **LAW II bypass paths.** Can ANY visible bullet text get into
   the rendered HTML without back-linking to a verified
   ReportSentence? E.g. via slide title (which is taken from
   section title — NOT verified prose), via speaker notes (which
   carries dropped-sentence overflow + scope summaries — also
   NOT verified prose).
2. **Citation drift.** Can a citation appear in `slide.citations`
   that doesn't resolve to a real bibliography entry? My read:
   no — `_citation_from_evidence_id` is keyed on bib_index, and
   the citation list filter is `if eid in bib_index`.
3. **HTML escaping completeness.** test_html_render_escapes_html_
   in_user_content covers `<script>`, but what about
   `<img src=x onerror=...>`, `javascript:` URLs in source URLs,
   broken `&entity;` cases?
4. **Slide-cap edge cases.** What if the run has exactly 20
   sections? Does the appendix get dropped? My code reserves 3
   slides at the end (contradictions+limitations+appendix);
   should that reservation be 2 (when no contradictions) so
   the section budget grows?
5. **Empty-report path.** SlideDeckEmptyReportError raised when
   sentences_verified == 0. Is that the right behavior, or
   should we still produce a "no findings to display" deck? My
   read: raising is correct — a deck with no verified prose
   would mislead a reader.
6. **Anything else worth flagging before M-22 locks.**

If GREEN, M-22 v1 locks. PPTX export ships in v2.

## Output

Write to `outputs/codex_findings/m22_review/findings.md`:

```markdown
# Codex review of M-22 v1

## Verdict
GREEN / PARTIAL / DISAGREE

## LAW II compliance
- [defensible / list bypass paths]

## HTML escaping
- [complete / list issues]

## Slide-cap edge cases
- [defensible / list issues]

## Final word
GREEN to lock M-22 + proceed / PARTIAL with edits.
```

Be terse. Under 100 lines.
