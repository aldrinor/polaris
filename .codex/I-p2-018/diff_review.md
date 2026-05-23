# Codex DESIGN+DIFF review — I-p2-018 (#757): compare / follow-up consistency

HARD ITERATION CAP: 5. iter 1. Canonical-diff-sha256 `ae62259f78bbe46db8fca46ef917ff00438f107a42225bbe3c9a26f2294f05b4`. web/ only. MERGE AUTHORIZED if mergeable. APPROVE iff zero P0/P1.

## Context
#757 = "Compare / follow-up (anchored to a claim)". Both surfaces already built + functional (#543 compare run-vs-run, #542 follow-up run-scoped). This PR is the design-system consistency delta.

## Diff
- web/app/compare/page.tsx + web/app/runs/[runId]/components/followup_panel.tsx: replaced the hand-rolled error banners (border-destructive/60 ...) with the #750 ErrorState (tokens + role=alert + specific message). + ErrorState imports.

## Honesty note (NOT faking claim-anchoring)
"anchored to a claim": the follow-up is RUN-scoped (askFollowup(runId, question) — the real backend capability; no per-claim anchor param). The placeholder frames claim-level questions ("What did the trial show for the subgroup over 65?"). True click-a-claim→anchored-follow-up needs a backend anchor param + report↔followup wiring — a deliberate follow-up, NOT faked here.

## Claude visual audit (standalone @1366, sent to operator): compare page clean (run-vs-run framing, honest empty-state CTA, comparison view: shared-evidence %, flags, evidence columns). Canadian-hosted mark (post #762).

## Review focus
1. ErrorState swaps clean (no unused imports, role=alert)? Both surfaces honest (run-scoped follow-up not overclaiming claim-anchor; compare distinct from benchmark)?
2. Any P0/P1.

## Output schema
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
merge_decision: MERGE AUTHORIZED | DO NOT MERGE
```
