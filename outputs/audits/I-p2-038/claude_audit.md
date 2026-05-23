# Claude architect audit — I-p2-038 (#805): fix lint lane RED on polaris base

## Scope
URGENT (operator-directed 2026-05-22, surfaced on PR #804). The
`lint + format + typecheck + build` GitHub Actions lane was RED on the `polaris`
base branch and has been merging red since #754. `npm run lint` = 2 errors + 3
warnings; only errors fail the lane (script is bare `eslint`, no
`--max-warnings`). Both errors live in `web/app/plan/page.tsx` (the #754 plan
run-start page). 1-file, 46-line diff.

(issue_id note: GitHub #805; internal id **I-p2-038** because I-p2-029 belongs to
the merged #768. Initial mis-id was caught + corrected before push — branch
`bot/I-p2-038-lint-lane-fix`, and the clobbered `.codex/I-p2-029/codex_diff.patch`
was restored via `git checkout`; my commit only touches `web/app/plan/page.tsx`.)

## Fixes
1. **react-hooks/set-state-in-effect (:105)** — the on-mount `useEffect` called
   `setState({ kind: "error", message: "no-question" })` synchronously in the
   no-question guard. The no-question state is render-derived, not an async side
   effect: the render guard already short-circuits on `!question`, so the effect
   now `if (!question) return;` (skips the intake fetch) and the dead render
   clause `state.message === "no-question"` is dropped → `if (!question)`.
   Behavior identical — no-question still renders "Nothing to plan yet" + "Ask a
   question" CTA.
2. **react/no-unescaped-entities (:292)** — `Can't` → `Can&apos;t` in the
   not-in-scope alert.

## Staled-consumer scan
- `grep "no-question"` web/: only the two lines I removed. No test asserts the
  no-question error state.
- `accessibility.spec.ts:61` uses `/plan?q=…` (has a question) → never hits the
  no-question path.
- `setState` still used by the async `kind:"ready"` + catch `kind:"error"`
  branches; `State` error variant still produced. No unused symbol introduced.
- 3 residual lint WARNINGS (unused `BenchmarkDimension`, `_status`, `_text`) are
  out of scope, non-blocking; the `_`-prefixed ones want an eslint
  `varsIgnorePattern` config change — separate concern, not folded (no creep).

## §-1.1 clinical-safety note
No claim/evidence/verdict rendering touched. The /plan intake gate (clinical +
PICO classifier via `runIntake`) and disambiguation flow are byte-identical; the
only behavioral surface is the no-question short-circuit, which renders the same
"Nothing to plan yet" UI as before. No faithfulness surface affected.

## Verification
- `cd web && npm run lint` → exit 0 ("3 problems (0 errors, 3 warnings)"). CI runs
  the same `npm run lint` (web_ci.yml:42), so the lane goes GREEN.
- `npm run typecheck` clean; `npm run build` Compiled successfully.
- Standalone harness @1366: `/plan` (no q) → "Nothing to plan yet" + "Ask a
  question"; `/plan?q=…&template=clinical` → "Review the plan" + question + 4-step
  plan (Start safely disabled offline). Both screenshot-verified.

## Verdict
Codex DIFF review: **APPROVE at iter 1**, zero P0/P1, MERGE AUTHORIZED.
46-line diff (under 200-LOC cap).
