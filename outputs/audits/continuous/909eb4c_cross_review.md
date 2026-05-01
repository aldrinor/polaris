# Cross-review — `909eb4c` batch (cycle 2)

**Cross-review of:** `outputs/audits/continuous/909eb4c_audit.md` (P0=0, P1=1, P2=2, P3=4)
**Triangle status:** subagent dissents on P1.1 (un-enumerated destructive surfaces); cycle does NOT lock yet — need a 3rd audit cycle returning clean (P1=0) to satisfy `REVIEW_BRIEF_FORMAT_v2.md` consecutive-APPROVE locking criterion.

## Verdict alignment

| | Claude | Subagent |
|---|---|---|
| Verdict | APPROVE_WITH_FIXES (per per-commit briefs) | **APPROVE_WITH_FIXES** |
| Production breaker (P0) | none | **none** |
| Honesty / no fake-working | OK (per LAW II) | **OK** — verified base-ui `OPEN_DELAY=600` literal, ran tests live, byte-diff'd bundle vs endpoint |

Subagent's center-of-gravity finding is a **fresh** P1 produced by my own enumeration miss, not a re-rehash of cycle-1. Worth the second cycle — exactly what an adversarial reviewer is for.

## What the subagent caught that I missed

The subagent's grep `grep -nE "text-destructive .* bg-destructive/10" web/app/` returned 0 hits (cycle-1 P1.1 completely closed). But broader `grep -n "text-destructive" web/app/` returned **2 lone uses on light background**:

- `web/app/dashboard/page.tsx:324` — "remove" button on uploaded-file list (parent `bg-background`).
- `web/app/inspector/[runId]/page.tsx:315` — "Dropped: <reason>" annotation inside Card content (`bg-card` ≈ light).

Both fail the same WCAG-AA 4.5:1 contrast floor (~4.04:1 by static math). Both are failure-path / interaction-state — not exercised by any current axe test because golden fixtures don't render them.

The subagent's framing critique is fair: my F-1 commit message said "4 destructive surfaces" (the cycle-1 enumeration) but the underlying root cause is "any `text-destructive` token on a light background" — broader than 4 surfaces. Honest call by the reviewer.

## What the subagent agreed with

- F-1 mechanically converted all 4 cycle-1-enumerated surfaces; pattern matches dae2a9f/07d6c30. **root_cause for the enumerated set** holds.
- F-2 1000ms hover budget verified honest: subagent read `node_modules/@base-ui/react/esm/tooltip/utils/constants.js:1` and confirmed `OPEN_DELAY = 600`. The 400ms render budget on top is the controllable part.
- F-3 budget math holds at upper-bound observed (DOMContentLoaded 450ms → 1000ms = 2.2x; FCP 376ms → 800ms = 2.13x).
- F-6 dead code legitimately unreachable.
- 9bf7346 handover scripts: subprocess env inheritance + exit codes verified by re-running 9/9 PASS.
- 9ccd286 bundle sample: byte-identical to `curl /runs/golden_clinical_001/bundle | python -m json.tool`. Real artefact, not a fixture-cousin.

## Fix plan with root_cause / guardrail / band_aid tags

| ID | Source | Fix | Tag | Rationale |
|---|---|---|---|---|
| F-7 | P1.1 | Convert the 2 lone `text-destructive` surfaces to the same border-only + `text-foreground font-medium` pattern. | **root_cause** (continuation of cycle-1 P1.1). |
| F-7b | P1.1 verify | Add 1 a11y test per failure path (upload-list-with-files; sentence-with-drop-reason). | **guardrail** — locks the regression. |
| F-8 | P3.3 | Update `web/components/ui/button.tsx:19` `variant="destructive"` to use the F-1 pattern (or delete the variant since unused). | **root_cause** — preempts the cycle-3 P1 the next contributor would surface by adopting this variant. |
| Defer | P2.1 | Add explicit "anchored to upper-bound 95th-percentile" comment to perf docstrings. | guardrail (cosmetic) — defer until we have actual percentile data from CI. |
| Defer | P2.2 | Extend testIgnore to `["linux", "darwin"]`. | guardrail — only matters when macOS CI lands; we don't have one. |
| Defer | P3.1, P3.2, P3.4 | Cosmetic / acceptable trade-offs / acceptable-for-v0. |

## Cycle-locking math

Per `REVIEW_BRIEF_FORMAT_v2.md`: lock = two consecutive APPROVE rounds (P1=0).
- Cycle 1: APPROVE_WITH_FIXES (P1=3) → fixes landed → cycle 2.
- Cycle 2: APPROVE_WITH_FIXES (P1=1, new) → fixes (F-7..F-8) land → cycle 3.
- Cycle 3 (target): clean APPROVE (P1=0).
- Cycle 4 (target): clean APPROVE (P1=0) → **LOCK**.

I'm executing F-7 + F-7b + F-8 in this turn. Cycle-3 subagent fires after the 5th post-cycle-2 substrate commit lands.

## Closure

Counter management: the post-909eb4c batch is at 4/5 (commits dbe62e0 / cc10303 / 8ae03b6 / 9fe4de9). The F-7..F-8 fixes are commit 5+ in that batch. After they land + brief, **trigger cycle-3 subagent**.

**Subagent invocation cost (cycle 2):** awaiting completion notification for exact tokens; rough estimate ~80-120k tokens given similar scope to cycle-1.
