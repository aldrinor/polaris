# Codex review — I-p2-002 (#741): design-audit protocol wired into templates

HARD ITERATION CAP: 5. iter 3 (final diff incl. authoring-rule + §9 evidence-required; brief now APPROVE).

This wires the 16-dimension design-audit protocol (from the I-p2-001 APPROVED standard, state/polaris_phase2_ui_breakdown_2026_05_21.md) into the review templates so every later Phase-2 UI task auto-inherits it. Two files:
- .codex/REVIEW_BRIEF_FORMAT.md — added §9 (mandatory DESIGN AUDIT for I-p2-* tasks: dedicated template, screenshot-matrix-in-loop via standalone harness, all 16 dims, APPROVE iff all PASS, artifact path, §8.3.1 cap).
- .codex/DESIGN_AUDIT_BRIEF_FORMAT.md — the dedicated per-task design-audit brief template (cap directive, rendered-evidence-attached requirement, 16-dim audit, YAML output schema).

## Review focus
1. Is the protocol COMPLETE + faithful to the 16-dim standard (no dimension dropped/garbled)?
2. Does it enforce rendered-evidence-in-the-loop (the thing that prevents code-only easy passes)?
3. Internally consistent with REVIEW_BRIEF_FORMAT §0 cap + the v3 verdict rule?
4. Anything that would let a non-top-tier UI pass.

## Output schema
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
merge_decision: MERGE AUTHORIZED | DO NOT MERGE
```
