# Codex DIFF review — I-p2-011 (#750): empty / loading / error states kit

HARD ITERATION CAP: 5. iter 1. APPROVE iff zero P0/P1 (code + design rubric, a11y + honesty). Final line MERGE AUTHORIZED if mergeable. Canonical-diff-sha256 `4b3437027c23741f146ed69c1ba9f297ab691b7f5860ac964d3759dace448928`. web/ only. Kit (pages adopt on rebuild #752-762; not migrating legacy pages here per brief). Visual verifies in-context as pages adopt it.

## Diff (state_kit.tsx)
- EmptyState {title, description?, icon?, action?}: neutral dashed, centered.
- LoadingState {label?, rows?}: skeleton rows animate-pulse + motion-reduce:animate-none; role=status + aria-busy + sr-only label.
- ErrorState {title?, message (required), onRetry?}: role=alert; dev-only console.warn if message matches generic blocklist; --destructive sparingly; retry focus-visible.

## Review focus
1. a11y: role=status/aria-busy (loading), role=alert (error), sr-only label, focus-visible retry, motion-reduce on the pulse?
2. Honesty (G-CONTENT): message required + dev-warn guardrail; empty=neutral not error; no generic copy baked in (default title "Couldn't load this" operational)?
3. tokens (destructive sparingly, AA). Any P0/P1.

## Output schema
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
merge_decision: MERGE AUTHORIZED | DO NOT MERGE
```
