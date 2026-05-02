M-3 Evidence Inspector View 1 (Report click-to-inspect) — code review.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

M-1 + M-2 GREEN-locked. Now M-3: View 1 (Report click-to-inspect),
the centerpiece interaction of the audit-grade UI moat per FINAL_PLAN.md.

The 30-second demo is: click any [N] citation in the rendered report
-> split-pane reveals the exact evidence span + tier + verified
sentences citing it + contradictions involving it. No competitor
(ChatGPT DR / Gemini DR / Perplexity / NotebookLM / Manus) can build
this without rebuilding their core, because they don't have
strict-verify provenance binding.

## What landed

Files:
- `scripts/static/inspector/markdown.js`: 130-line minimal vanilla
  MD->HTML renderer (headings, paragraphs, github tables, bullet
  lists, [N] citation tokens, HTML escaping)
- `scripts/static/inspector/inspector.js` (rewritten ~280 lines):
  builds evidence index (bibByNum, sentencesByEvidenceId,
  contradictionsByEvidenceId), wires click + keyboard handlers,
  renders right-pane with tier badge + bib + sentences + contradictions
- `scripts/static/inspector/inspector.css`: tier badges (T1-T7+UNKNOWN
  color tokens), severity badges (low/medium/high/critical),
  sentence kept/dropped left-border markers, evidence pane styling
- `scripts/templates/inspector_shell.html`: loads markdown.js before
  inspector.js

Tests: 81 -> 91.
- test_inspector_router.py: 4 new tests for the API surface needed
  for click-to-inspect
- test_inspector_markdown.py: 6 tests via Node subprocess for the
  markdown renderer (citations, consecutive citations, tables,
  headings, HTML escaping, bullet lists)

E2E smoke test through live_server.app: all routes 200 OK, inspector
loads with 26 biblio + 14 contradictions + 6 verified sections + 15
frame coverage entries.

## Your job

Code review for M-3. Verdict: GREEN / PARTIAL / DISAGREE.

## Specific things to validate

1. **Markdown renderer correctness.** Does the vanilla JS markdown
   renderer correctly handle every construct in the V30 report.md?
   Specifically check:
   - Citations inside table cells (Trial Summary table has [1] [2] etc)
   - Multiple consecutive citations [19][20]
   - Citations at end-of-sentence with trailing punctuation
   - HTML escaping (a malicious source statement should not break out)
   - Edge: nested constructs (heading inside list, table after table)

2. **Click-to-inspect contract.** When user clicks [N]:
   - Is the bibliography lookup (bibByNum) deterministic and correct?
   - Are dropped sentences clearly distinguished from verified?
   - Does the right pane actually surface what FINAL_PLAN promised:
     "tier label + evidence span + contradicting evidence with its
     own span"? Or is anything missing?

3. **Keyboard accessibility.** I added Enter/Space activation +
   Escape to close. Is that enough for a11y, or does the citation
   need ARIA descriptions?

4. **Evidence pane data model.** The right pane shows:
   - bib statement + tier + url + evidence_id
   - verified sentences citing this evidence (with section + span +
     status + failure reasons for dropped)
   - contradictions involving this evidence (severity, claim values,
     recommended action)
   Is this the right information density for an audit-grade brief,
   or does it over/under-show?

5. **Performance with 26 biblio + 100+ citations.** The evidence
   index is built once at page load. For Phase A this is fine, but
   should I be more careful about delegated event handling vs
   per-citation listeners?

6. **CSP / XSS.** I'm escaping HTML in the renderer, but the IR
   payload itself contains user-content (bib statements, contradiction
   recommendations, source URLs). Is escHtml() being called on every
   user-supplied value going into the evidence pane?

7. **Phase B prerequisites.** What in M-3 should I revisit when
   we wire progressive in-run surfaces (the t-table from FINAL_PLAN.md:
   pre-flight estimate -> parse progress -> live source discovery ->
   frame coverage filling in -> contradiction queue -> first verified
   claim cards -> final synthesis)? Anything that needs different
   structuring now to avoid a Phase B refactor?

8. **Anything else you'd push back on.**

## What you should output

Write to `outputs/codex_findings/m3_review/findings.md`:

```markdown
# Codex review of M-3

## Verdict
GREEN / PARTIAL / DISAGREE

## Markdown renderer assessment
Concrete bugs / missing constructs.

## Click-to-inspect contract
What works / what's missing / what FINAL_PLAN promised but isn't delivered.

## Specific issues
List concrete bugs / gaps / design problems with file:line.

## Recommended changes
If PARTIAL: specific edits.

## M-4 readiness
Is the IR + Inspector shell ready for the Contradiction Matrix view?

## Final word
GREEN to lock M-3 and proceed to M-4 / PARTIAL with edits / DISAGREE.
```

Be terse. Under 350 lines.
