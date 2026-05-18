# Codex DIFF review — I-rdy-008 / GH #504 slice 7c: rebaseline the inspector e2e spec for the slice-7b data-path migration

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

---

## 1. What you are reviewing

The commit-1 diff for #504 **slice 7c** — `git diff origin/polaris...HEAD`
excluding `.codex/I-rdy-008/` and `outputs/audits/I-rdy-008/` (canonical diff
in `.codex/I-rdy-008/codex_diff.patch`, sha256 trailer). Implements the
Codex-APPROVE'd brief `.codex/I-rdy-008/brief.md` (brief APPROVE iter 2;
0 P0/P1; 1 P2). **1 code file: `web/tests/e2e/inspector.spec.ts`**
(+ `state/polaris_restart/iteration_trajectory.md` process metadata).

Slice 7c is the test-rebaseline slice of the slice-7 split your architecture
consult decided (`.codex/I-rdy-008/slice7_arch_consult_verdict.txt`): 7a
backend evidence route (PR #596) / 7b frontend migration (PR #597) / 7c test
rebaseline. After 7c, #504 continues with slices 8-12.

## 2. The change

Slice 7b (PR #597) removed the inspector page's bundle "Export" button and
migrated `PoolTab`/`EvidencePane` off the golden-fixture-only `getBundle()`
onto `GET /api/inspector/runs/{id}/evidence`. Slice 7c rebaselines the one
CI-run e2e spec whose assertions broke:

- **`web/tests/e2e/inspector.spec.ts` header comment** — was "the backend
  serves real EvidenceContract JSON from `tests/v6/fixtures/
  evidence_contract_v1/*.json`"; updated to describe the actual data path
  (`GET /api/inspector/runs/{id}` AuditIR + `GET /api/inspector/runs/{id}/
  evidence`).
- **The `"Export bundle JSON button is present"` test** (the button was
  removed by slice 7b) is replaced by `"Evidence pool tab settles into a
  terminal PoolTab state"`: click the "Evidence pool" tab, then a web-first
  assertion waits for the panel to settle into one of the three TERMINAL
  `PoolTab` states — grouped evidence rows (`/· tier .+ · \d+ span/`), or
  "No verified evidence spans for this run.", or "Evidence unavailable:".
  It then asserts `"Loading evidence…"` has count 0.

## 3. Verify

1. **The transient state cannot satisfy the test.** `PoolTab` renders
   "Loading evidence…" while `evidence === null` (`web/app/inspector/
   [runId]/page.tsx:1001`). The new test's terminal-state locator regex does
   NOT include "Loading evidence…", and the test additionally asserts
   `getByText("Loading evidence…")` has count 0. Confirm a never-resolving /
   mis-wired evidence fetch would FAIL this test (this was the brief iter-1
   P1 — confirm it is closed).
2. **The terminal-state strings match the slice-7b `PoolTab`.** Confirm
   against `web/app/inspector/[runId]/page.tsx`: `Evidence unavailable:
   {evidenceError}` (line 996), `No verified evidence spans for this run.`
   (line 1006), the grouped-row button text `{evidenceId} · tier {tier} ·
   {n} span(s)`, and the tab label `"Evidence pool"` (line 153).
3. **The regex is correct.** `/· tier .+ · \d+ span|No verified evidence
   spans for this run\.|Evidence unavailable:/` — the first alternative
   matches a grouped row, the `.` in "run." is escaped, "Evidence
   unavailable:" matches the PoolTab error panel.
4. **Scope.** Only `web/tests/e2e/inspector.spec.ts` changes (plus the
   trajectory process-metadata file). No production code, no fixture, no
   backend, no other spec. The other 3 CI-run e2e specs and the 16+
   non-CI-run `sentence_inspector_*.spec.ts` are untouched.
5. **The other `inspector.spec.ts` tests are byte-unchanged** — KPI cards,
   two-family invariant, Executive-summary tab, Verified-sentences tokens,
   Contradictions `noted_both`, Charts Vega-Lite, Dashboard scope.

## 4. Files I have ALSO checked and they're clean

- `web/app/inspector/[runId]/page.tsx` — the slice-7b page the spec is
  rebaselined against; `PoolTab` terminal-state strings + the "Evidence
  pool" tab label verified; NOT modified.
- `web/tests/e2e/accessibility.spec.ts`, `performance.spec.ts`,
  `evidence_tooltip_perf.spec.ts` — the 3 other CI-run e2e specs; zero
  slice-7b-affected assertions; NOT modified.
- `.github/workflows/web_ci.yml` — the `e2e_playwright` job runs exactly
  those 4 specs against a live `polaris_v6.api.app` backend; NOT modified.
- `web/tests/e2e/sentence_inspector_*.spec.ts` (16+ files) — NOT CI-run,
  out of scope, NOT modified.

## 5. Smoke state

`npx prettier --write tests/e2e/inspector.spec.ts` — formatted. `npm run
lint` — 0 errors, 3 pre-existing warnings (none in the changed file). `npm
run typecheck` — `tsc --noEmit` clean. `npm run build` — succeeded. The
Playwright e2e job runs only in CI (it needs the live backend) and is not
part of the offline smoke; slice 7c makes the `inspector.spec.ts`
assertions correct for the post-7b page and does not claim to turn the
pre-existing-red `e2e_playwright` job fully green.

## 6. Accepted residual (brief iter-2 P2)

The golden-run artifact_dirs may lack `evidence_pool.json`, so the inspector
Pool tab can render "Evidence unavailable" for golden runs — the new test is
deliberately terminal-state-agnostic so it passes either way. Adding
golden-fixture `evidence_pool.json` (so the Pool tab shows real spans in the
demo) is real demo-hardening, tracked as a #504 follow-up — NOT slice 7c.

## 7. Required output schema (§8.3.9)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

Loose verdict prose is rejected — emit the schema.
