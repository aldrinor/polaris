# Brief — I-p2-040 (#827): pin_replay empty state → shared EmptyState kit (P3 consistency)

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the doc is force-APPROVE'd on remaining non-P0/P1 findings.
- If you're holding back a P1 for the next round — DON'T. Surface it now.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## Context
Per your UI-direction decision, P3 = "constrained consistency pass: empty-state treatment".
Grounded scan: `pin_replay` is the ONE cred-independent page that hand-rolls its empty state
(a bare `<p>` "No pin data available yet…") instead of the shared `EmptyState` kit (#750)
that 8 other pages already use (compare/dashboard/intake/plan/runs/source_review/graph). On
the live site its body read as a void.

## Acceptance criteria
- AC1: pin_replay's empty state routes through `EmptyState` (icon + title + description +
  action), matching the kit-using pages.
- AC2: CTA → a PUBLIC route (`/intake`, no dead-end); intro copy explains the feature so the
  empty page is informative, not barren.
- AC3: `data-testid="pin-replay-empty"` preserved; honest copy (no overclaim); "query"→
  "question" (jargon kill).
- AC4: prod build + eslint + prettier green.

## Change (one file: `app/pin_replay/page.tsx`)
`EmptyPinReplay()` now: keeps the page heading (jargon-killed to "question") + an intro
paragraph explaining pin replay, then `<EmptyState icon={History} title="No pinned runs yet"
description="Run a research question and pin its result to start a timeline here."
action={<Button render={<Link href="/intake">Ask a question</Link>} />} />`. Imports added:
History (lucide), Link, EmptyState, Button.

## Files I have ALSO checked and they're clean
- `components/states/state_kit.tsx` (EmptyState signature: title/description?/icon?/action?).
- `tests/e2e/pin_replay_g1_g8.spec.ts`: asserts NO empty-state copy/text (only nav, already
  updated in #826) → copy change breaks no spec.
- The populated pin_replay view (SnapshotCard/timeseries) is UNCHANGED — only the empty branch.

## Verification (LAW II)
- `next build` compiled; eslint clean; prettier `--check` clean.
- Local `next start` screenshot: icon + "No pinned runs yet" + explainer + brand-red
  "Ask a question" CTA in a dashed EmptyState card; void gone.

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
