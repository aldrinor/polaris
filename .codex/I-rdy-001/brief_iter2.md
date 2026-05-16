# Codex review iter 2 — I-rdy-001 (#497): docs/polaris_locked_scope.md

**Type:** REVIEW, iter 2 of 5. Iter 1 = REQUEST_CHANGES: 1 P1 + 2 P2. All fixed.

## §0. Cap directive: front-load all findings. APPROVE iff zero P0 and zero P1.

## §1. Iter-1 findings and the fixes applied
- **P1** (§1.2 OVH over-claim "zero GPU SKUs"): FIXED — line now reads "its Canadian datacentre (Beauharnois, Québec) has only old V100/V100S GPUs, which lack FP4/FP8 and cannot run V4 Pro; OVH's Hopper-class H100/H200/A100 are France-only" with a citation to state/canada_gpu_research_2026_05_15.md.
- **P2** (F15 status missing clean-machine qualifier): FIXED — F15 row now ends "clean-machine verification not proven".
- **P2** (§2 change-gate term inconsistent: "operator-signed" vs "operator-acknowledged"): FIXED — §2's line now says "operator-acknowledged change to §2 (per the §5 change protocol)", consistent with §5.

## §2. Verify `docs/polaris_locked_scope.md`
1. All 3 iter-1 findings correctly fixed.
2. No new error introduced.
3. The doc is accurate, complete, internally consistent.

## §3. Output schema
```yaml
verdict: APPROVE | REQUEST_CHANGES
iter1_findings_fixed: yes | no | partial
new_issues: [...]
residual: [...]
verdict_reasoning: <text>
```
