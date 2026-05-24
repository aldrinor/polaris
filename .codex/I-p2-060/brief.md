# Codex brief — I-p2-060 (#867): Offline Inspector dropzone S-audit

HARD ITERATION CAP: 5. iter 1. APPROVE iff the plan is sound + doesn't break the contract.

## Output schema (required)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

## Context + plan
/inspector/offline (disconnected-reviewer entry; loaded state reuses the S-tier InspectorView).
Assess-first: crafted drop zone (icon + drag-active brand-tint + motion + rounded-xl + loading
state) replacing the plain box; shared ErrorState replacing the raw bg-rose error. Preserve the
a11y dropzone (role=button + keyboard), loadBundleFromTarGz, the honest SHA-256/GPG copy, testids.

## Note
Already gated downstream: visual `-i` APPROVE iter-1 (desktop A / mobile A-); code diff APPROVE.
This brief records acceptance for the artifact set.
