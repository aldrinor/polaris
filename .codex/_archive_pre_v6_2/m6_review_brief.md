M-6 Evidence Inspector View 4 (Methods + Provenance Bundle) — code review.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

M-1..M-5 GREEN-locked. Now M-6: View 4 (Methods + Provenance Bundle),
the audit-bundle header per FINAL_PLAN.md. Includes one-click PDF
audit-bundle export endpoint.

## What landed

Files:
- `src/polaris_graph/audit_ir/inspector_router.py`: new endpoint
  GET /api/inspector/runs/{slug}/audit-bundle.zip — streams a zip
  with INDEX.txt + canonical V30 artifacts (report, manifest, biblio,
  contradictions, verification_details, protocol, evaluator_rule_checks,
  qwen_judge_output, completeness, corpus_adequacy, corpus_approval,
  human_gap_tasks).
- `scripts/static/inspector/inspector.js` (+~200 lines):
  renderMethodsView + helpers + two-family invariant banner.
- `scripts/static/inspector/inspector.css` (+~200 lines): methods-grid,
  methods-card, methods-section, methods-kv-table, methods-rule-list,
  methods-export-btn, methods-two-family-banner.

Visual:
- Top-line export button (green CTA) → audit-bundle.zip
- Two-family invariant banner (run-14: deepseek vs qwen → holds)
- 6 top-line cards: Run ID, Protocol SHA-256, Cost, Verified/Dropped,
  Evaluator gate, Contradictions
- Model provenance, Retrieval, Evaluator gate detail, V30 warnings,
  13 rule checks, Protocol metadata, Expected vs actual tier
  distribution sections

Tests: 135 → 145.

## Your job

Code review for M-6. Verdict: GREEN / PARTIAL / DISAGREE.

## Specific things to validate

1. **FINAL_PLAN compliance.** "Methods + Provenance Bundle" is
   defined as: run hash + model versions + retrieval queries +
   abort gates + reproducibility hash + one-click PDF audit-bundle
   export. Does the view actually deliver all of these?

2. **Audit bundle endpoint.** /api/inspector/runs/{slug}/audit-bundle.zip
   streams an in-memory ZIP. Concerns:
   - Is streaming the right pattern, or should this be cached
     per-run on disk?
   - INDEX.txt content acceptable for procurement?
   - Are there canonical V30 files I should ADD or REMOVE from
     the bundle?
   - Should the ZIP be signed (HMAC) for tamper-evidence?

3. **Two-family invariant banner.** I check generator_family vs
   evaluator_family and display green-banner if different. Run-14:
   deepseek vs qwen → holds. Edge cases:
   - Missing model_provenance (legacy run): banner is suppressed
     entirely. Should it instead show a warning banner?
   - Same family (hypothetical violation): I show a
     methods-two-family-banner-violation class but the CSS doesn't
     define a distinct red style. Should fix that gap.

4. **Expected vs actual tier distribution.** I render in-band /
   out-of-band per tier from `proto.expected_tier_distribution` vs
   `tier_mix.fractions`. Any edge cases?

5. **Rule checks display.** I render 13 rule-check rows with
   pass/fail. Run-14 has 1 fail (PT13 advisory_unhedged_superlatives)
   that should appear in the list. The "details" line is rendered
   as a sub-row. Acceptable visual hierarchy?

6. **Performance / security.** The audit-bundle endpoint reads
   files from disk and returns the bytes. For Phase A run-14 this
   is fine. Any concerns about path traversal, race conditions
   while artifacts are being written, or DoS via large artifact
   directories?

7. **Anything else you'd push back on.**

## Output

Write to `outputs/codex_findings/m6_review/findings.md`:

```markdown
# Codex review of M-6

## Verdict
GREEN / PARTIAL / DISAGREE

## FINAL_PLAN compliance
What's covered / what's missing.

## Audit-bundle endpoint
Streaming/caching/signing concerns.

## Specific issues
File:line bugs / gaps.

## Recommended changes
If PARTIAL.

## M-7 readiness
Is the IR ready for the Source Tier Mix view (last view in Phase A)?

## Final word
GREEN to lock M-6 / PARTIAL with edits / DISAGREE.
```

Be terse. Under 300 lines.
