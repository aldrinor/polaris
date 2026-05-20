# Codex diff — I-cd-037 (#642) — capacity-confirm runbook

Canonical-diff-sha256: `c9fe1374873fc5afa7d5013d566a6ec3c1797e29c5de1eee8f4365c40c9b6f80` (iter 2; iter-1 P1+P2 fixes folded in). Docs-only.

## Iter-1 fixes
- **P1 (both demo boxes)**: §0 NEW two-box table (Generator 8×H200/H100 + Evaluator 4×H100); §3 email requests BOTH boxes; §4 acceptance requires BOTH from same vendor (or split-vendor VPN bridge fallback).
- **P1 (3-vs-4 vendor)**: consistently "4 vendor paths in parallel"; OVH Canada/France acknowledged as same parent OVHcloud via different regional contacts.
- **P2 (transparency.md disclosure)**: explicitly deferred to I-D-05 / #651 (final accuracy refresh).

## Diff
- `docs/sovereign_gpu_capacity_confirm.md` NEW — operator runbook for the immediate-pre-provisioning capacity confirm.
  - §1 Scope: 4 vendors in parallel (OVH Canada preferred, OVH France / Scaleway / Hetzner per EU-relax 2026-05-18).
  - §2 Dates: 2026-08-31 to 2026-09-06 demo window per carney_delivery_plan_v6_2.md Phase 5.
  - §3 Email template with 5 sovereignty/compliance asks.
  - §4 Operator action checklist (state-file path for replies + acceptance criterion).
  - §5 Why-it-matters: protects against ordered-but-stuck provisioning before demo.
  - §6 References + memory cross-links.

The Issue is operator-action. This PR ships the substrate the operator uses to execute Seq 37.

Output schema:
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
