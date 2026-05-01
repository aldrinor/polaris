# Cross-review — `61da4ad` batch (cycle 8, a11y/UX lens) — 4 P1s, lock progress 0/2

**Cross-review of:** `outputs/audits/continuous/61da4ad_audit.md` (P0=0, P1=4, P2=2, P3=2)
**Subagent ID:** `a1e58788ce793622c`. Cost: 132,542 tokens / 46 tool uses / 634s wall.
**Lens:** accessibility/UX (cycle 8, v2 protocol — first a11y-focused review)
**Lock status:** Cycle-7 APPROVE_WITH_FIXES + Cycle-8 APPROVE_WITH_FIXES → 0/2 consecutive APPROVE. Lock progress reset.

## Verdict alignment

| | Claude | Subagent |
|---|---|---|
| Verdict | (would have called APPROVE — F-24 closed the axe-flagged surfaces) | **APPROVE_WITH_FIXES** |
| P1 | none expected | **4 NEW P1s** none of cycles 1-7 caught |
| Honesty | F-24 commit message claimed "preempts cycle-8" — overconfident | Subagent: "F-24 closed exactly what cycle-7 P3.2 named — but a deeper a11y probe surfaces 4 distinct P1-class issues" |

**The cycle-8 a11y lens is the strongest single-cycle finding rate so far.** None of cycles 1-7 (correctness/security/perf) caught any of these because they don't fit those probe templates:
- **P1.1**: target-size on 4 surfaces axe missed (axe overlap-detection is loose; subagent measured `getBoundingClientRect()` directly)
- **P1.2**: WCAG 2.1.1 **Level A** keyboard failure on PRIMARY ENTRY FLOW. Template `<Card onClick=...>` survives 7 cycles because axe doesn't see React synthetic listeners on `<div>`. Keyboard-only users literally cannot select non-default templates.
- **P1.3**: WCAG 4.1.3 AA — scope-rejection card has no `aria-live`. Screen readers stay silent on the most important UI feedback.
- **P1.4**: Synthetic Link-as-Button has no target-size guardrail.

## Fix plan — all 4 root_cause + guardrail shipped this cycle

| ID | Source | Fix | Tag |
|---|---|---|---|
| F-25 | P1.1 | Add `min-h-[24px]` (+ `min-w-[24px]` where text-width is small) to: dashboard `remove` button, `browse files` label, EvidenceTooltip provenance-token button, Inspector "contradiction in section →" pill. All 4 surfaces now ≥24×24. | **root_cause** |
| F-26 | P1.2 | Convert dashboard template `<Card onClick>` to `<button role="radio" aria-checked>` inside `<div role="radiogroup" aria-label>`. Native button + role=radio = keyboard-operable + screen-reader announceable. Closes the Level-A failure. | **root_cause** |
| F-27 | P1.3 | Add `role="status" aria-live="polite"` to scope-decision Card AND ambiguity-cluster Card. Screen readers now announce verdict changes. | **root_cause** |
| F-28 | P1.4 | New Playwright sweep at `accessibility.spec.ts` that walks every `button`, `[role="button"]`, `[role="radio"]`, `a[href]`, `label:not([for])` on dashboard + Inspector and asserts ≥24×24 via `getBoundingClientRect()`. Catches what axe misses. Plus a keyboard-operability test for the template radiogroup. | **guardrail** |

Verified live (post-rebuild + restart): **13/13 a11y tests pass** (was 10/10 + 3 new = 13/13 total) + 9/9 inspector + 6/6 perf + 2/2 hover = **30/30**.

## What v2 protocol design enabled

The cycle-8 audit's reviewer-independence statement makes the case directly:
> "I wrote 3 ad-hoc probes that measured `getBoundingClientRect()` on every relevant surface and enumerated tab order on `/dashboard` and `/inspector/golden_clinical_001`, then deleted those probe specs."

A brief-aware reviewer would have anchored on cycle-7's P3.2 (target-size on 3 surfaces) and verified the F-24 fix. The brief-blinded subagent went deeper: enumerated tab order, measured every clickable rect, traced React onClick semantics. That's how it caught the Level-A keyboard failure — by probing the DOM directly rather than reading what the test suite already knew.

This is the clearest demonstration yet that v2's brief-blinding + lens-rotation produces orthogonal findings, not just confirmations.

## Locking math (revised)

| Cycle | Lens | Verdict | Lock progress |
|---|---|---|---|
| 5 | correctness | APPROVE | 1/2 |
| 6 | security | APPROVE | 2/2 — claimed |
| 7 | performance | APPROVE_WITH_FIXES | 0/2 — invalidated |
| 8 | a11y/UX | APPROVE_WITH_FIXES | 0/2 |
| 9 (target — correctness) | correctness | ? | 1/2 if APPROVE |
| 10 (target — security) | security | ? | **2/2 → re-lock** |

Earliest possible re-lock: cycle-10. Honest expectation: cycle-9 might also surface a fresh finding (correctness lens hasn't reviewed F-25..F-28 ARIA changes yet). v3 protocol could consider requiring N=4 distinct lenses to close consecutively rather than 2 — that would actually mean "all four perspectives agree" which is the real lock concept.

## Closure

F-25..F-28 + cycle-8 audit + cross-review committed. Counter for new batch: 1. Cycle-9 (correctness lens, round-robin) fires after K=5 OR manually for next lock attempt.

The triangle continues to find genuine issues. Each lens reveals what others can't see. The "lock" goalpost is real but conservative — every "lock" claim should be tested against fresh lenses, exactly as v2 prescribes.
