M-3 v2 — re-review.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

Your M-3 v1 verdict: PARTIAL with 7 issues. All 7 integrated in v2.

## What changed in v2

HIGH:
1. **Layout fix**: aside.evidence-pane was OUTSIDE .inspector-main; the
   2-column grid was applied only to main, so the pane never split.
   Now the pane lives INSIDE .inspector-main as a flex sibling of
   .inspector-views (a new wrapper around the views).
   - CSS: .inspector-main = flex row; .inspector-views = flex:1;
     .evidence-pane = 480px (380px on small screens), sticky position.

2. **Full cluster rendering**: pane now renders every claim in each
   contradiction cluster, not only the matching one.
   - Active claim highlighted via cluster-claim-active class.
   - Each claim shows tier + evidence_id + value + dose + arm +
     context_snippet + sanitized URL.

3. **URL-stem resolver**: ID drift between bibliography (surpass_X)
   and contradictions (ev_NNN). New urlStem() normalizer (strips
   scheme/www/query/trailing slash). New clustersByUrlStem index.
   findClustersForBibEntry() = primary evidence_id match UNION
   secondary URL-stem match.

MEDIUM:
4. **URL protocol sanitization**: sanitizeUrl() returns "" for
   non-http(s) schemes. javascript:/data:/mailto: collapses to inert
   "URL omitted (non-http(s) scheme blocked)" message.

5. **Tier/severity enum validation**: VALID_TIERS + VALID_SEVERITIES
   sets; validateTier()/validateSeverity() coerce unknown values to
   UNKNOWN before HTML injection.

6. **A11y**: citation anchors get aria-controls + aria-expanded +
   aria-label (with tier + statement preview). Pane has
   aria-labelledby + tabindex="-1" on body. Open moves focus into
   pane; close returns focus to triggering citation.

LOW:
7. **Horizontal rule + adjacent tables**: markdown.js now renders
   ---/***/___ as <hr>. Adjacent-tables parser fixed (current table
   closes when next line is followed by another separator).

Tests: 91 -> 99 (8 new tests).

## Your job

Quick verification pass. Verdict: GREEN / STILL-PARTIAL / DISAGREE.

Spot-check:
- Are all 7 fixes integrated correctly?
- Layout: does the pane actually appear as a sibling column to the
  views, not stacked below?
- Cluster rendering: does the pane really render all claims with
  context_snippet, or is anything still missing for the side-by-side?
- URL-stem resolver: is the normalization correct? Does it actually
  bridge surpass_X (no URL) ↔ ev_NNN (URL) gaps in run-14?
- a11y: does focus management actually work on open/close?
- Any new issues introduced?
- M-4 ready?

## Output

Write to `outputs/codex_findings/m3_v2_review/findings.md`:

```markdown
# Codex re-review of M-3 v2

## Verdict
GREEN / STILL-PARTIAL / DISAGREE

## Fix integration check
- [x/no] Layout split-pane structure
- [x/no] Full cluster rendering
- [x/no] URL-stem resolver
- [x/no] URL protocol sanitization
- [x/no] Tier/severity enum validation
- [x/no] A11y attributes + focus management
- [x/no] Horizontal rule + adjacent tables

## New issues introduced
none / list

## Final word
GREEN to lock M-3 and proceed to M-4 / STILL-PARTIAL with edits.
```

Be terse. Under 150 lines.
