# Per-commit Codex brief — `3fd3d20`

**Commit:** `3fd3d20 PL: v6.2 Phase 2C.1 Playwright e2e — 9/9 tests passing live`
**Format:** v2 minimal (`./REVIEW_BRIEF_FORMAT_v2.md`)
**Files changed (4):**
- `web/tests/e2e/inspector.spec.ts` (new, 105 lines, 9 tests)
- `web/playwright.config.ts` (new, 38 lines)
- `web/package.json` (+@playwright/test, +2 scripts)
- `web/package-lock.json` (lockfile churn)

## What this commit does

Adds the first **cross-feature integration test suite** for the v6 frontend — Playwright e2e exercising live backend + frontend (no mocks, no fixtures-as-mocks; tests hit `tests/v6/fixtures/evidence_contract_v1/*.json` served by the real FastAPI app).

9 tests across 4 describe blocks:
1. **Inspector — golden_clinical_001** (5 tests): KPI cards visible, two-family PASS pattern, Executive summary is default tab, Verified-sentences click renders provenance tokens, Export bundle button present.
2. **Inspector — golden_housing_002** (1 test): Contradictions tab navigation + `noted_both` resolution badge.
3. **Inspector — Charts tab** (1 test): Vega-Lite SVG actually renders inside `.polaris-vega-chart` after click.
4. **Dashboard — scope discovery** (2 tests): clinical-treatment prompt rejected with `clinical_treatment_recommendation` reason + research-framed CMHC question accepted.

Run config: chromium only, 1 worker, fullyParallel:false, baseURL via `SCREENSHOT_BASE_URL`. Verified locally: `9 passed (10.9s)`.

## Acceptance criteria (round-3 brief criteria 25 + new):

1. **No mocks.** Tests must hit the real backend; no `page.route(...)` interception of API endpoints. Verify the file contains zero `route` / `fulfill` / `mock` calls.
2. **Live data only.** Every fixture referenced (`golden_clinical_001`, `golden_housing_002`, `golden_climate_005`) must exist on disk under `tests/v6/fixtures/evidence_contract_v1/` AND be served by the FastAPI `/runs/{id}/bundle` endpoint.
3. **Vega SVG assertion is non-trivial.** The Charts test waits for `.polaris-vega-chart svg` selector with 10s timeout AND counts `>= 1` SVG. Not just "page loaded" — actual SVG node in DOM.
4. **Dashboard scope test exercises both branches.** Reject branch shows category string (`clinical_treatment_recommendation`); accept branch shows `Accepted` text. Each has 8s timeout for backend roundtrip.
5. **No flake-prone assertions.** No `toHaveText` on whitespace-sensitive nodes; uses regex `/PASS .* deepseek-v4-flash/i` for two-family banner since model name and separator may vary.

## Codex focus

- **P0:** Are any of the assertions actually mocked or stubbed in a way I missed? (`page.route`, `fulfill`, `MSW`, hand-written XHR shim).
- **P0:** Does the `noted_both` selector in the contradiction test rely on text that only appears for that specific fixture, or could it false-positive on any contradiction-tab render?
- **P1:** Should `fullyParallel: false` + `workers: 1` be revisited once we have CI? On a single dev box this keeps memory bounded; on CI we'd want parallelism. Document the rationale or open follow-up.
- **P2:** The `Promise.all` parallel-fetch contract from F10c isn't directly tested here — should the Charts/Executive-summary test assert all 3 charts arrive within < 2× single-fetch latency?

## Cross-review

Lands at `outputs/audits/continuous/3fd3d20/cross_review.md` whenever Codex is run offline.
