# Claude architect audit — I-rdy-008 (#504) slice 7c

**Issue:** GH #504 (I-rdy-008) — Phase 3.5: wire live runs into the rich UI.
**Slice 7c of #504** — the test rebaseline, last slice of the slice-7 split
decided by the Codex architecture consult
(`.codex/I-rdy-008/slice7_arch_consult_verdict.txt`): 7a backend evidence
route → 7b frontend migration → **7c test rebaseline**. Slices 1-6 + 7a + 7b
merged (PR #590-#597).
**Branch:** `bot/I-rdy-008-slice7c` off `polaris` HEAD `91a9a9b8`.
**Commit 1:** `52f6e239` — `web/tests/e2e/inspector.spec.ts`.
**Brief:** `.codex/I-rdy-008/brief.md` — Codex brief review APPROVE iter 2
(iter-1 P1 fixed; 1 P2 accepted).

## 1. What shipped

`web/tests/e2e/inspector.spec.ts` is rebaselined for the slice-7b data-path
migration. Slice 7b (PR #597) removed the inspector page's bundle Export
button and migrated `PoolTab`/`EvidencePane` off `getBundle()` onto
`GET /api/inspector/runs/{id}/evidence`. Two changes:

- **Stale file-header comment fixed.** It claimed "the backend serves real
  EvidenceContract JSON from `tests/v6/fixtures/evidence_contract_v1/*.json`"
  — the inspector page now reads the AuditIR
  (`GET /api/inspector/runs/{id}`) + the evidence route
  (`GET /api/inspector/runs/{id}/evidence`).
- **The `"Export bundle JSON button is present"` test replaced** with
  `"Evidence pool tab settles into a terminal PoolTab state"` — the Export
  button no longer exists; the new test exercises the 7b-rewritten Pool tab.

## 2. Per-finding verification (against the APPROVE'd brief)

- **VERIFIED — only the broken CI-run assertion is touched.** The CI
  `e2e_playwright` job (`.github/workflows/web_ci.yml`) runs exactly 4 specs;
  a grep of `accessibility.spec.ts` / `performance.spec.ts` /
  `evidence_tooltip_perf.spec.ts` for `Export`/`bundle`/`getBundle`/
  `EvidenceContract`/`Pool`/`/evidence` returned zero hits. The only
  slice-7b-broken assertion was `inspector.spec.ts`'s Export-button test.
  Slice 7c modifies only `inspector.spec.ts`.
- **VERIFIED — the transient state is rejected (Codex brief iter-1 P1).**
  The new test's terminal-state locator is the regex
  `/· tier .+ · \d+ span|No verified evidence spans for this run\.|Evidence
  unavailable:/` — matching the three terminal `PoolTab` states only.
  `"Loading evidence…"` (PoolTab's `evidence === null` branch,
  `page.tsx:1001`) is NOT in the locator; the test additionally asserts
  `getByText("Loading evidence…")` has count 0 after the terminal state is
  visible. A test that accepted the transient state would pass even if the
  evidence fetch never resolved — that hole is closed.
- **VERIFIED — the terminal-state strings match the slice-7b PoolTab.**
  Confirmed against `page.tsx`: `Evidence unavailable: {evidenceError}`
  (line 996), `No verified evidence spans for this run.` (line 1006), and
  the grouped-row `<button>` text `{evidenceId} · tier {tier} · {n} span(s)`.
  The Pool tab label `"Evidence pool"` (line 153) is matched by
  `getByRole("button", {name:/Evidence pool/})`.
- **VERIFIED — robust to the golden-fixture open question.** The test
  accepts ANY of the three terminal states, so it passes whether or not the
  golden-run artifact_dirs carry `evidence_pool.json` (grouped rows if
  present; "No verified evidence spans" / "Evidence unavailable:" if not) —
  while still proving the evidence fetch resolved past the loading state.
- **VERIFIED — the other `inspector.spec.ts` tests are untouched.** KPI
  cards, two-family invariant, Executive-summary default tab,
  Verified-sentences provenance tokens, Contradictions `noted_both`, Charts
  Vega-Lite, Dashboard scope — all verbatim; none was slice-7b-affected.
- **VERIFIED — scope.** Only `web/tests/e2e/inspector.spec.ts`. No
  production-code change, no fixture change, no backend change. The 16+
  `sentence_inspector_*.spec.ts` files are not CI-run and are untouched.

## 3. Smoke

`npx prettier --write tests/e2e/inspector.spec.ts` — formatted. `npm run
lint` — **0 errors**, 3 pre-existing warnings (`benchmark_board` unused
import; `page.tsx:739` `chartTypes` exhaustive-deps; `frame_coverage_panel`
unused var) — none in the changed file. `npm run typecheck` — `tsc --noEmit`
clean. `npm run build` — succeeded. The Playwright e2e job itself runs only
in CI (it needs the live backend) and is not part of the offline smoke.

## 4. Codex iteration trail

- **Brief iter 1 REQUEST_CHANGES** — 1 P1: the plan accepted the transient
  `"Loading evidence…"` state as a passing condition. Fixed: the plan now
  waits for a terminal state and explicitly excludes the loading state.
- **Brief iter 2 APPROVE** — 0 P0/P1; 1 P2 (accept scope call 3.3 —
  golden-run `evidence_pool.json` is real follow-up/demo hardening, not
  required for this test rebaseline).

## 5. Scope + residuals

Slice 7c = the inspector e2e spec rebaseline; it is the last slice of the
slice-7 split. #504 continues with slices 8-12. **Accepted residual
(Codex brief iter-2 P2):** the golden-run artifact_dirs may lack
`evidence_pool.json`, so the inspector Pool tab can render "Evidence
unavailable" for golden runs in the demo — adding golden-fixture
`evidence_pool.json` so the Pool tab shows real spans is real demo-hardening
work, tracked as a #504 follow-up, not slice 7c. Slice 7c does not attempt
to fix pre-existing, non-slice-7b `e2e_playwright` CI failures (a documented
loop NON-halt).

## 6. Verdict

Faithful to the APPROVE'd brief: the one CI-run e2e spec with a
slice-7b-broken assertion is rebaselined; the new Pool-tab test waits for a
real terminal state and rejects the transient loading state (the iter-1 P1);
the terminal-state strings are verified against the slice-7b `PoolTab`; no
production/fixture/backend change; prettier / lint (0 err) / tsc / build
green. Ready for Codex diff review.
