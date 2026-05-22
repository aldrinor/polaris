# Codex BRIEF review — I-p2-002 (#741): wire the design-audit protocol into review templates

HARD ITERATION CAP: 5. iter 2 (iter-1 P1 authoring-rule + P2 where-applicable fixed). APPROVE iff the acceptance criteria are correct + complete. Docs/templates only.

## Task
Wire the 16-dimension Codex design-audit protocol (from the I-p2-001 APPROVED standard, state/polaris_phase2_ui_breakdown_2026_05_21.md) into the review templates so every later Phase-2 UI task auto-inherits it.

## Acceptance criteria
1. `.codex/REVIEW_BRIEF_FORMAT.md` gains a §9 making the design audit MANDATORY for I-p2-* UI tasks (dedicated template, screenshot-matrix-in-loop via the production standalone harness, all 16 dimensions, APPROVE iff all PASS, artifact paths, §8.3.1 cap).
2. New `.codex/DESIGN_AUDIT_BRIEF_FORMAT.md` — dedicated per-task design-audit brief template: verbatim §8.3.1 cap block, rendered-evidence-attached requirement (matrix incl. 200%/400% zoom, forced-colors, print, focus-visible, all states; traces + axe + keyboard + screen-reader + evidence-click REQUIRED), all 16 dims audited, YAML output schema with per-dimension PASS/NEEDS-WORK.
3. Internally consistent with REVIEW_BRIEF_FORMAT §0 + the v3 verdict rule. Prevents code-only easy passes.

## Files I have ALSO checked and they're clean
- state/polaris_phase2_ui_breakdown_2026_05_21.md (the 16-dim source of truth — the templates mirror it).

## Output schema
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
```
