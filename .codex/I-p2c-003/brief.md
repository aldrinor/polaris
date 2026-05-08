# Codex Brief Review — I-p2c-003 (ITER 1 of 5)

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Pre-flight

- **Issue:** I-p2c-003 — Cross-browser: Chromium / Firefox / WebKit. Scope: Playwright across 3 browsers. Acceptance: all pass. LOC estimate 130.
- **Substrate today:** `web/playwright.config.ts:37-49` already defines chromium / firefox / webkit projects. The 3-browser matrix is configured but not exercised — most existing specs run only on chromium per the local `--project chromium` invocation.
- **Honest framing per CLAUDE.md §9.4:** ship a small "smoke matrix" spec that runs on all 3 browsers and asserts the 5 most stable pages render without browser-specific errors. This is NOT a comprehensive cross-browser test for every existing spec — that's I-p2c-003b. This issue's substrate-honest deliverable is "verifies Polaris boots in all 3 browsers without breakage" + a documented matrix of pages that pass on each.

## Plan

### `web/tests/e2e/cross_browser_smoke.spec.ts` (NEW)

1. Define `STABLE_PAGES = [{ feature: "F1", path: "/intake", testid: "intake-form" }, { feature: "F3", path: "/upload", testid: "upload-dropzone" }, { feature: "F4", path: "/sse", testid: "sse-harness" }, { feature: "F11", path: "/contracts", testid: "contract-form" }, { feature: "F12", path: "/sentence_hover_test/perf", testid: "perf-trigger" }]` — 5 pages that don't depend on Vega/charts/PDF (those have known browser quirks).
2. Spec parametrizes per page: `for (const p of STABLE_PAGES) { test(\`${p.feature} \${p.path}\`, ...) }`.
3. Each test: visit, sanity-test that primary testid renders, assert no `[data-testid="error"]` element. Runs on chromium / firefox / webkit per playwright project config.
4. NO visual baselines, NO complex interactions — purely "does the page boot".

### Out of scope

- Comprehensive cross-browser visual baselines (I-p2c-002d).
- Vega chart cross-browser parity (browser-specific SVG rendering — I-p2c-003c).
- PDF.js cross-browser (I-p2c-003d).
- Backend integration on Firefox/WebKit (I-p2c-003e).

## Risks for Codex Red-Team

1. **Chrome extensions / WebGL:** none used; pages are simple HTML/React.
2. **Firefox SSE behavior:** `sse-harness` is a static rendered div; no real EventSource flow needed for this issue's smoke test.
3. **§9.4 N/A frontend.**
4. **CHARTER §3 LOC cap:** estimated spec ~50 LOC. Comfortable under 200.

## Acceptance criteria

1. New `web/tests/e2e/cross_browser_smoke.spec.ts` defines 5 page-render tests.
2. Spec runs on chromium AND firefox AND webkit (no `test.skip` per browser).
3. All 15 tests (5 pages × 3 browsers) pass.
4. CHARTER §3 LOC cap respected (≤200 net).

**Forced enumeration:** before verdict, write one line per criterion 1-4.
**Completeness check:** list files actually read.

## Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

APPROVE iff zero NOVEL P0 + zero continuing P0 + zero P1.
