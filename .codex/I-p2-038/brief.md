# Codex DIFF review — I-p2-038 (#805): fix lint lane RED on polaris base

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

Canonical-diff-sha256 `d0dce4e2cd8a59e17fc4c484851ae32b191334fdcca89bb8374a80cf7e070490`. web/ only, 46-line diff (1 file, under 200-LOC cap). MERGE AUTHORIZED if mergeable. APPROVE iff zero P0/P1.

(Issue-id note: GitHub #805. The internal issue_id is **I-p2-038** — I-p2-029 was already taken by the merged #768 (global app shell). Branch `bot/I-p2-038-lint-lane-fix`.)

## Context
URGENT issue: the `lint + format + typecheck + build` GitHub Actions lane was RED
on the `polaris` base branch (merging red since #754), so every Phase-2 PR shows
a red lane. `npm run lint` reported **2 errors + 3 warnings**; only errors fail
the lane (the script is bare `eslint`, no `--max-warnings`). Both errors are in
`web/app/plan/page.tsx` (the #754 plan run-start page). Operator (2026-05-22)
directed: file URGENT issue + fix the errors next, before #759.

## Diff (1 file: web/app/plan/page.tsx)
1. **react-hooks/set-state-in-effect (:105)** — the on-mount `useEffect` called
   `setState({ kind: "error", message: "no-question" })` **synchronously** in the
   no-question guard branch. Fix: the no-question case is render-derived, not an
   async side effect. The render guard already short-circuits on `!question`, so
   the effect now just `if (!question) return;` (skips the intake fetch). Dropped
   the now-dead render clause `state.kind === "error" && state.message ===
   "no-question"` → simplified to `if (!question)`. **Behavior identical**:
   no-question still renders the "Nothing to plan yet" section.
2. **react/no-unescaped-entities (:292)** — `Can't` → `Can&apos;t` in the
   not-in-scope ("Can't start this run") alert.

## Files I have ALSO checked and they're clean
- `grep "no-question"` across web/: ONLY lines 105 (removed) + 150 (the dead
  clause, removed). No other consumer; no test asserts the no-question error
  state.
- `web/tests/e2e/accessibility.spec.ts:61` hits `/plan?q=Should I take ozempic…`
  (WITH a question) and waits for `plan-blocked` — never exercises the
  no-question path, so unaffected.
- `setState` is still used by the async success (`kind:"ready"`) + catch
  (`kind:"error"`) branches; the `State` error variant is still produced. No
  unused type/var introduced.
- The 3 remaining lint WARNINGS are out of scope (do not fail the lane):
  `benchmark_board.tsx:12` unused `BenchmarkDimension`,
  `inspector_bundle_client_loader.ts:130` unused `_status`,
  `frame_coverage_panel.spec.ts:44` unused `_text`. The `_`-prefixed two would
  ideally be silenced via an eslint `varsIgnorePattern` config change — a
  separate concern, not folded here (no scope creep).

## Verification
- `cd web && npm run lint` → exit 0, "3 problems (0 errors, 3 warnings)".
- `npm run typecheck` clean; `npm run build` Compiled successfully.
- Standalone harness @1366: `/plan` (no q) → "Nothing to plan yet" + "Ask a
  question" CTA; `/plan?q=…&template=clinical` → "Review the plan" + question +
  4-step plan (Start disabled offline — correct, gate can't resolve w/o backend).

## Review focus
1. Is the set-state-in-effect fix correct + behavior-preserving (no-question
   still renders, no regression to the async intake gate / disambiguation)?
2. Is dropping the dead `state.message === "no-question"` clause safe (nothing
   sets it post-fix)?
3. Any P0/P1.

## Output schema
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
merge_decision: MERGE AUTHORIZED | DO NOT MERGE
```
