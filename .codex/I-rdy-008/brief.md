# Codex BRIEF review — I-rdy-008 / GH #504 slice 7c: rebaseline the inspector e2e spec for the slice-7b data-path migration

HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

---

## 0. Stage

Pre-implementation **brief** review — reviewing the *plan*, NOT a diff. No code written yet.

## 0.1 This is slice 7c of #504 — the last slice of the slice-7 split

#504 (I-rdy-008, Phase 3.5 — "wire live runs into the rich UI"). Slices 1-6 +
7a + 7b merged (PR #590-#597). Slice 7 was split by a Codex architecture
consult (`.codex/I-rdy-008/slice7_arch_consult_verdict.txt`) into 7a backend
evidence route / 7b frontend migration / **7c test rebaseline**. 7a (PR #596)
shipped `GET /api/inspector/runs/{run_id}/evidence`; 7b (PR #597) migrated the
inspector page off the golden-fixture-only `getBundle()` onto that route.
Slice 7c is the test rebaseline. After 7c, #504 continues with slices 8-12.

This is a NORMAL implementation brief (Codex reviews the plan). The slice-7
architecture is settled.

## 1. What slice 7b changed (the thing 7c must rebaseline against)

PR #597 (`web/app/inspector/[runId]/page.tsx`):
- Removed the **"Export bundle JSON" header button** + `downloadBundleAsJson`.
- Migrated `PoolTab` + `EvidencePane` off `getBundle()`/`EvidenceContract`
  onto `getInspectorEvidence()` → `GET /api/inspector/runs/{id}/evidence`.
- The body gate `ir && bundle` → `ir`; the evidence fetch is now an
  independent fetch — a 422/failure sets `evidenceError` and degrades ONLY
  the Pool tab + `EvidencePane`, never the rest of the page.

## 2. Grounding (done — Codex should VERIFY, not re-discover)

**The CI e2e job runs exactly 4 specs.** `.github/workflows/web_ci.yml` job
`e2e_playwright` starts a real `uvicorn polaris_v6.api.app:app` backend +
`next start`, then runs ONLY: `tests/e2e/inspector.spec.ts` (step
`run_e2e_inspector`), `accessibility.spec.ts`, `performance.spec.ts`,
`evidence_tooltip_perf.spec.ts`. The 16+ `sentence_inspector_*.spec.ts` files
are **NOT CI-run**.

**Only `inspector.spec.ts` carries a slice-7b-broken assertion.** I grepped
all 4 CI-run specs for `Export` / `bundle` / `getBundle` / `EvidenceContract`
/ `downloadBundle` / `Pool` / `/evidence`:
- `accessibility.spec.ts` — zero slice-7b-affected refs.
- `performance.spec.ts` — zero slice-7b-affected refs.
- `evidence_tooltip_perf.spec.ts` — zero slice-7b-affected refs (it exercises
  the `EvidenceTooltip` hover-card on the Verified-sentences tab, which is
  AuditIR-backed since slice 4 — untouched by 7b).
- `inspector.spec.ts` — **one broken test**: `"Export bundle JSON button is
  present"` (lines 47-51) asserts `getByRole("button", {name:/Export bundle
  JSON/})` is visible; slice 7b removed that button. Also the file-header
  comment (lines 3-9) is now stale: it says "the backend serves real
  EvidenceContract JSON from `tests/v6/fixtures/evidence_contract_v1/*.json`"
  — the inspector page now reads `GET /api/inspector/runs/{id}` (AuditIR) +
  `GET /api/inspector/runs/{id}/evidence`.

**No e2e spec currently clicks the Evidence-pool tab** — grep of
`web/tests/e2e/*.spec.ts` for `Evidence pool` / `pool tab` / `Pool` returns
nothing. The Pool tab — the surface 7b rewrote — has zero e2e coverage.

**Open question — golden-run `evidence_pool.json` (a scope-boundary call,
see §3).** The CI backend resolves the golden runs (`golden_clinical_001`
etc.) through `get_inspector_run` → `run_store` → `artifact_dir` →
`load_audit_ir`. The slice-7a `/evidence` route additionally requires
`artifact_dir/evidence_pool.json` and fails loud (422) if absent. I could
not locate where/whether the golden-run artifact_dirs carry
`evidence_pool.json` (no golden-run seeding found in `app.py`, no
`inspector_seed` module; `golden_clinical_001` appears only in `bundle.py`'s
`_GOLDEN_RUN_INDEX`). If the golden artifact_dirs lack `evidence_pool.json`,
the Pool tab renders the honest "Evidence unavailable" state for golden runs
— which is correct slice-7b fail-loud behavior, not a bug.

## 3. Plan

**One file: `web/tests/e2e/inspector.spec.ts`.** No production-code change,
no fixture change, no backend change.

1. **Fix the stale header comment** (lines 3-9) — describe the actual data
   path: the inspector page reads `GET /api/inspector/runs/{id}` (the
   faithful AuditIR) + `GET /api/inspector/runs/{id}/evidence` (the verified
   evidence spans), served by a real `polaris_v6.api.app` backend.
2. **Replace the `"Export bundle JSON button is present"` test** — the
   button no longer exists. Replace it with an **Evidence-pool tab test that
   waits for a FINAL `PoolTab` state**: navigate to `golden_clinical_001`,
   click the "Evidence pool" tab, then assert the tab panel SETTLES into one
   of the three terminal `PoolTab` states — the grouped evidence list (a row
   per `evidence_id`), OR "No verified evidence spans for this run.", OR
   "Evidence unavailable:". Use a Playwright web-first assertion that retries
   until a final state is visible (e.g. `expect(locator).toBeVisible()` on a
   locator that matches any of the three terminal states; or assert the
   transient state has cleared first).
   **The transient "Loading evidence…" state is explicitly NOT an accepted
   pass condition** (Codex brief iter-1 P1): `PoolTab` renders "Loading
   evidence…" whenever `evidence === null` (the pre-fetch state), so a test
   that accepts it would pass even if the evidence request never resolves or
   is mis-wired. The test must wait past "Loading evidence…" to a terminal
   state; it MAY additionally assert "Loading evidence…" is transient (was
   visible, then gone), but must never treat it as terminal. This assertion
   does NOT depend on golden-fixture `evidence_pool.json` being present
   (any of the three terminal states satisfies it), so it is robust to the
   §2 open question — while still proving the evidence fetch actually
   resolved. This gives the 7b-rewritten Pool tab its first e2e coverage.
3. The other `inspector.spec.ts` tests (KPI cards, two-family invariant,
   Executive-summary default tab, Verified-sentences provenance tokens,
   Contradictions `noted_both`, Charts Vega-Lite, Dashboard scope) are NOT
   slice-7b-affected and stay verbatim.

## 4. Scope-boundary calls (Codex: rule accept / adjust)

- **3.1 — `inspector.spec.ts` only.** Slice 7c rebaselines exactly the one
  CI-run spec with a slice-7b-broken assertion. Recommend ACCEPT.
- **3.2 — replace the Export test with a Pool-tab render test** (vs. just
  delete it, vs. a negative "Export button absent" assertion). The Pool tab
  is the surface 7b rewrote and currently has zero e2e coverage; a
  positive render test is the higher-value choice and keeps the spec count
  stable. Recommend ACCEPT the Pool-tab render test.
- **3.3 — the Pool-tab test waits for any of the three TERMINAL states**
  (grouped rows / "No verified evidence spans" / "Evidence unavailable") —
  not specific span content, and explicitly not the transient "Loading
  evidence…" state (Codex brief iter-1 P1, addressed in §3 step 2) — so it
  does not require adding `evidence_pool.json` to the golden fixtures while
  still proving the evidence fetch resolves. Adding golden-fixture
  `evidence_pool.json` so the Pool tab shows real spans in the demo is a
  REAL follow-up (it affects the demo experience for #504) but is fixture
  work beyond a test rebaseline — recommend DEFER to a follow-up issue, not
  slice 7c. Codex: rule whether the state-agnostic test is acceptable for
  7c or whether the fixture work must land here.
- **3.4 — the 16+ `sentence_inspector_*.spec.ts` are NOT CI-run** and are
  out of scope for 7c. Recommend ACCEPT (out of scope; no CI gate depends
  on them).
- **3.5 — slice 7c does not attempt to fix pre-existing, non-slice-7b e2e
  failures.** The `e2e_playwright` CI job has been red across slices (a
  documented loop NON-halt). Slice 7c makes the `inspector.spec.ts`
  assertions CORRECT for the post-7b page; it does not claim to turn the
  whole e2e job green. Recommend ACCEPT.

## 5. Smoke test

`cd web && npx prettier --write tests/e2e/inspector.spec.ts && npm run lint &&
npm run typecheck && npm run build`. The changed file is a Playwright spec
(not built into the Next bundle); lint + typecheck cover it. The e2e job
itself runs only in CI (needs the live backend) — not part of the offline
smoke.

## 6. Files I have ALSO checked and they're clean

- `web/tests/e2e/accessibility.spec.ts`, `performance.spec.ts`,
  `evidence_tooltip_perf.spec.ts` — the 3 other CI-run e2e specs; zero
  slice-7b-affected assertions; NOT modified.
- `.github/workflows/web_ci.yml` — confirms the `e2e_playwright` job runs
  exactly those 4 specs against a live backend; NOT modified.
- `web/app/inspector/[runId]/page.tsx` — the slice-7b page (the thing the
  spec is rebaselined against); NOT modified (7b shipped it).
- `web/components/ui/evidence-tooltip.tsx` — `EvidenceTooltip`, exercised by
  `evidence_tooltip_perf.spec.ts`; AuditIR-backed since slice 4; NOT touched
  by 7b or 7c.
- `web/tests/e2e/sentence_inspector_*.spec.ts` (16+ files) — NOT CI-run, out
  of scope, NOT modified.

## 7. Output schema (§8.3.9)

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
