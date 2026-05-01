# Cross-review — `4f20140` batch (cycle 10, security lens) — APPROVE, lock 1/2

**Cross-review of:** `outputs/audits/continuous/4f20140_audit.md` (P0=0, P1=0, P2=2, P3=2)
**Subagent ID:** `abbaea6cb225fb6db`. Cost: 118,174 tokens / 52 tool uses / 511s wall.
**Lens:** security (cycle 10, v2 protocol — second invocation of security lens after cycle-6)
**Cycle-9 status:** rate-limited at Anthropic API tier; produced no audit. Cycle-10 reviewed the same scope (F-25..F-28) under security lens instead.
**Lock progress:** Cycle-7 + 8 returned APPROVE_WITH_FIXES. Cycle-10 = APPROVE. **1/2 toward re-lock.**

## Verdict alignment

| | Claude self-assessment | Subagent verdict |
|---|---|---|
| Verdict | (was hopeful — F-26 felt clean) | **APPROVE** |
| P0 / P1 | none expected | **none** |
| Critical detail I had right but didn't realize | `type="button"` on `<button role="radio">` | Subagent verified this is **load-bearing**: without it, Space-press fires `onSubmit` prematurely, bypassing the scope-check user-intent gate |

**The single most valuable finding from cycle-10 is what it CONFIRMED, not what it found.** I added `type="button"` to the new template radio buttons because shadcn's pattern uses it elsewhere. The subagent's security-lens analysis identified that the missing-`type` failure mode wouldn't be a UX bug — it would be a **scope-check bypass**: keyboard user presses Space to select a template, and instead the form submits, kicking off `createRun(...)` before they've clicked Check scope.

This is the kind of "what's the security-relevant failure mode of this code" question only the security lens probes. Correctness lens would have asked "does Space change aria-checked?" Performance lens would have asked "is the click handler hot?" Security asks "what does this implicitly bypass?"

## What was clean

- **No ARIA-attribute injection.** All ARIA values are static literals or React-bound booleans. Backend-derived `t.title`/`t.domain` flow through JSX text children (escaped), not attribute values.
- **Supply-chain integrity holds.** `git diff 5975ca3..4f20140 -- requirements.txt` is empty since cycle-7's F-21 protobuf<5.0.0 pin landed. CVE-2026-0994 mitigation untouched.
- **Audit-trail discipline applied.** Commit `4f20140`'s message carries both required `audit-trail-edit:` lines per F-20 protocol.
- **No secrets, no §9.1 invariant disturbance.** The cycle-8 diff didn't touch generator/evaluator/strict_verify/corpus-approval code paths.
- **Tab semantics don't leak auth state.** Inspector `<nav>` only renders inside `{bundle && (...)}` — error/unauthorized paths show only the error banner, no tab labels.

## P2 / P3 carryovers

The audit's 2 P2 + 2 P3 findings are out-of-scope-observed (not security-class):
- Inspector tab buttons should ideally have `role="tab"` + `aria-selected` for screen-reader UX (cycle-8 P2.1, deferred)
- BACKEND_URL build-time enforcement is "process discipline" not security
- Radiogroup arrow-key cycling (ARIA APG roving tabindex) is best-practice
- F-28 sweep test should run on Firefox + WebKit (currently chromium-only)

None of these block the lock. They're polish items the audit honestly classified as out-of-lens-observed.

## Locking math (revised)

| Cycle | Lens | Verdict | Lock progress |
|---|---|---|---|
| 5 | correctness | APPROVE | 1/2 |
| 6 | security | APPROVE | 2/2 — claimed |
| 7 | performance | APPROVE_WITH_FIXES | 0/2 — invalidated |
| 8 | a11y/UX | APPROVE_WITH_FIXES | 0/2 |
| 9 | (correctness, rate-limited) | no audit | n/a |
| **10** | **security** | **APPROVE** | **1/2** |
| 11 (target) | perf or a11y or correctness | ? | **2/2 → re-lock** if APPROVE |

**Earliest possible re-lock: cycle-11 if it returns APPROVE.** This time the lock would have meaningful diversity behind it: cycle-10 (security) + cycle-11 (whatever lens) on F-25..F-28 substrate that has already survived cycle-8 (a11y) deep probing during fix-generation.

## Closure

No fix commits needed (no P1). I write only the cross-review + commit.

Cycle-11 fires next. Round-robin suggests **performance** (cycle-7 was perf, then a11y-correctness-security; perf is due again). But the F-25..F-28 changes are CSS sizing + ARIA attributes — perf-lens probes (bundle size, layout cost, paint time) have low expected yield on this scope. **Higher-quality lens for cycle-11: a11y again.** Cycle-8's a11y subagent caught 4 P1s; running a11y a second time on the F-25..F-28 fixes would test "did the fixes actually close the issues" with the same lens that found them. Counter-argument: same-lens probably finds same things (or nothing), violating the diversity principle.

Honest call: **fire cycle-11 with performance lens** as the round-robin dictates, accept that yield will be low, and if it returns clean APPROVE the lock is meaningful BECAUSE the lens didn't have to find anything to validate. A clean perf-lens APPROVE on a CSS-sizing diff is a stronger signal than a clean a11y-lens APPROVE because perf has no priors to confirm.

Counter-counter: cycle-8's findings were on the SAME scope cycle-10 just APPROVED. If cycle-11 (perf) APPROVES, the cycle-8 P1 fixes (F-25..F-28) get implicit cross-validation across 3 lenses (a11y → security → perf). That's stronger than the cycle-5+6 lock which was 2 lenses on different scope.
