# Audit — `909eb4c` batch (5 commits, post-`4fe03f7` F-1..F-6 + handover)

**Verdict:** APPROVE_WITH_FIXES
**Findings:** P0=0  P1=1  P2=2  P3=4

Five-commit window: `9ccd286` → `9bf7346` → `e331b08` (F-1) → `0867df9` (F-3..F-6) → `909eb4c` (F-2). Local re-run on the running 8000+3738 servers: 8/8 a11y in 13.0s, 6/6 perf in 5.4s, 2/2 hover in 4.9s.

## Pre-flight

- Read: `4fe03f7_audit.md` + `4fe03f7_cross_review.md`; per-commit briefs; `git show <sha>` for all 5; `web/app/{dashboard,inspector/[runId],runs/[runId]}/page.tsx`; `web/components/ui/button.tsx`; `web/app/globals.css`; `web/tests/e2e/*.spec.ts`; `web/playwright.config.ts`; `scripts/v6/{cost_summary,replay_pin,run_pin_replay}.py`; `docs/carney_handover/{runbook.md,bundle_export_sample.json}`; `web/node_modules/@base-ui/react/esm/tooltip/utils/constants.{d.ts,js}`.
- Ran: a11y+perf+hover suites locally; `curl /runs/golden_clinical_001/bundle | diff` against the sample → byte-identical (json.tool-normalised).
- Grepped: `text-destructive`, `bg-destructive`, compound `text-destructive .* bg-destructive`, `variant="destructive"`, `OPEN_DELAY`, handover script names.

## Per-criterion forced enumeration

- C1 [F-1 mechanical refactor]: NONE. All 4 surfaces (`dashboard:418`, `inspector:149/667`, `runs:125`) → `border-destructive/60 text-foreground font-medium`, identical to dae2a9f/07d6c30 proven-clean pattern.
- C2 [F-1 verify grep]: `grep -nE "text-destructive .* bg-destructive/10" web/app/` → **0 hits**. Compound pattern eliminated. See P1.1 for residual lone uses.
- C3 [F-1 collateral `<pre>`]: NONE. Light `text-foreground oklch(0.145)` on `bg-muted oklch(0.97)` ≈ 17:1; dark ≈ 14:1. Pass AA easily.
- C4 [F-2 hover honest]: NONE. 1000ms = 600ms (verified `OPEN_DELAY = 600` at `web/node_modules/@base-ui/react/esm/tooltip/utils/constants.js:1`) + 400ms render. Docstring discloses math. Not band-aid.
- C5 [F-3 budgets]: NONE at upper-bound. DOMContentLoaded 452/367ms → 1000ms = 2.2x; FCP 376→800 = 2.13x; Charts ~1.1s→2000 = 1.8x; tab-switch ~100→250 = 2.5x. See P2.1 for lower-bound.
- C6/C7 [F-4/F-5]: see P3.1, P2.2.
- C8 [F-6]: NONE. Throw is unconditional; expect was unreachable. Removed cleanly.
- C9 [Handover scripts]: NONE. `os.environ.copy()` + `PYTHONPATH=src` overlay; 9/9 tests assert exit 0/1/2; ASCII-only stdout.
- C10 [Bundle = live]: NONE. `curl /runs/golden_clinical_001/bundle | json.tool` byte-identical to sample. Production output, not fixture-cousin.

## P0

NONE. No silent failure, no broken auth, no data loss, no missing rollback, no security hole.

## P1

**P1.1 — Two residual `text-destructive` surfaces ship the SAME root-cause as cycle-1 P1.1, on `bg-background` instead of `bg-destructive/10`.** F-1 closed the 4 enumerated surfaces but `grep -n "text-destructive" web/app/` still returns:
- `web/app/dashboard/page.tsx:324` — "remove" button on upload list (parent `bg-background` at :305).
- `web/app/inspector/[runId]/page.tsx:315` — "Dropped: <reason>" text in Card content (default `bg-card` light bg).

Static math: destructive `oklch(0.577 0.245 27.325)` ≈ red #d34a3a on white = **~4.04:1** (< 4.5:1 AA). Same root cause as cycle-1 P1.1 — `text-destructive` token on light background. Not axe-exercised: golden fixtures don't render them (no uploads on `/dashboard` initial; no `drop_reason` in goldens). Failure-path / interaction-state surfaces, same hazard class as cycle-1's banners.

**New in cycle-2, not a rehash**: cycle-1's verify grep was compound-pattern-scoped; lone uses escaped. F-1 followed cycle-1's enumeration mechanically without widening the grep. Same un-enumeration miss, one level out.

Verify: a `/dashboard upload list is WCAG-AA clean` test in post-upload state + an inspector fixture with `drop_reason` set both fire color-contrast violations.

Tag: **root_cause** — eliminate `text-destructive` on light backgrounds globally (or extract a `<DestructiveText>` component). Surface-by-surface continues working but signals "we keep finding these one cycle at a time".

## P2

**P2.1 — F-3 DOMContentLoaded slack is 3.7x at lower-bound.** Author claims `~2× baseline_observed`. Honest at upper-bound (1000/450 = 2.2x), but at lower-bound 270ms it's 3.7x. The docstring shows the range without saying which one anchors the budget. Either (a) note "anchored to 95th-percentile observed" or (b) explain bimodal cold/warm distribution. Verify: capture 10 cold-loads, confirm 95th percentile near 450ms not 270ms.

**P2.2 — F-5 only covers Linux, not Darwin.** `playwright.config.ts:23`: `process.platform === "linux" ? ["**/visual.spec.ts"] : undefined`. Baselines are `*-chromium-win32.png` only. On macOS, snapshots resolve to `*-chromium-darwin.png` (missing) and Playwright auto-baselines silently — same hazard F-5 prevents on Linux. Either extend to `["linux","darwin"].includes(process.platform)` or gate by baseline-presence. Verify: run on macOS with no `*-darwin.png` and observe loud-error vs silent-snapshot.

## P3

**P3.1 — F-4 trade-off.** `waitFor({timeout: 5_000})` is correct for budget-failure diagnostics but a fully-broken selector now waits 5s instead of 1s. ~+8s total wall on a UI-broken negative-path. Acceptable.

**P3.2 — F-1 axe coverage on 2-of-4 refactored surfaces.** New tests cover inspector 404 banner + runs 404 banner. Dashboard form error, inspector charts-tab error, and two-family-fail card are mechanically refactored to identical class strings but not directly axe-exercised. Class-string identity makes dynamic omission low-risk; cosmetic.

**P3.3 — Latent destructive Button variant.** `web/components/ui/button.tsx:19` carries the cycle-1 P1.1 compound pattern (`bg-destructive/10 text-destructive`). `grep -rn 'variant="destructive"' web/` returns no current usage; first user re-introduces the cycle-1 bug. Either delete the variant or update its class string.

**P3.4 — Handover scripts are runbook-only.** `grep -rn "scripts/v6/(cost_summary|replay_pin|run_pin_replay)" src/ scripts/` returns only the scripts + runbook. CLI shells over real substrate covered by 9 subprocess tests. Carney's office invoking from runbook is the protection surface; runbook-signature drift would not be caught automatically (cycle-1 had a similar miss, fixed in `fe82d57`). Acceptable for v0 handover.

## Cross-cycle integrity

- Cycle-1 P2.2 (`requirements.txt` install bloat): `git diff 4fe03f7..HEAD -- requirements.txt` empty — no regression.
- Cycle-1 P3.3 (counter file gitignored): unchanged; `.codex/continuous/*` per-commit briefs continue providing the redundant trail.

## Reviewer independence statement

I read actual diffs (`git show <sha>` for all 5 commits + cycle-1 audit + cross-review), grepped 4 patterns under `web/app/` and `web/components/`, and ran a11y + perf + hover suites locally. The base-ui `OPEN_DELAY = 600` is verified by reading `web/node_modules/@base-ui/react/esm/tooltip/utils/constants.js:1` directly — F-2's math grounded in lib source, not assertion.

AGREE: F-1 closed cycle-1 P1.1's 4 enumerated surfaces (root_cause for those 4); F-2 closed P1.2 honestly; F-3 budget math at upper-bound; F-4/F-5/F-6 as labeled. None are band_aid.

DISAGREE: F-1's "all destructive surfaces fixed" framing is too strong. Compound-pattern surfaces are fixed; lone `text-destructive` on light backgrounds (P1.1) ships unfixed in 2 places — an enumeration miss, not a workaround (so not band_aid strictly), but root_cause work that didn't land.

**Verdict: APPROVE_WITH_FIXES.** P0 = 0; nothing breaks production. P1.1 should land as F-7 (root_cause) before the cycle locks. Cycle-1 was APPROVE_WITH_FIXES; cycle-2 is APPROVE_WITH_FIXES with a fresh P1, so the two-consecutive-APPROVE locking criterion in `REVIEW_BRIEF_FORMAT_v2.md` does NOT yet apply. After F-7 lands and a third audit returns P1=0, the lock applies.
