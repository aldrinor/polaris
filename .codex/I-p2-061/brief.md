# Codex brief — I-p2-061 (#869): WCAG 2.2 AA fixes

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
A focused @axe-core/playwright sweep (wcag2a/2aa/21aa/22aa) found real AA violations on live pages
the visual gate can't catch (contrast is numerical): opacity-reduced muted text below 4.5:1 (footer
+ 3 page captions + ErrorState message + a code element), missing input/select accessible names,
and a nested-interactive dropzone. Plan: bump the failing muted opacities to full token / darker
token; add aria-labels; un-nest the upload file input. Re-verify axe → 0. Preserve all logic/testids.

## Note
Already gated downstream: axe re-run = 0 violations across 15 routes (the objective check); visual
`-i` APPROVE (darker text legible); code diff APPROVE. This brief records acceptance.
