# Codex Brief Review — I-p2c-002 (ITER 5 of 5)

## Iter 5 changes per Codex iter 4

- **P1 fix:** F12 `/sentence_hover_test/perf` testid corrected to `perf-trigger` (verified at `web/app/sentence_hover_test/_demo_perf.tsx:113`).

## Iter 4 changes per Codex iter 3

- **P1 fix:** PAGES table corrected (verified against repo at write-time):
  - F7 → testid `frame-coverage-gaps`
  - F11 → testid `contract-form`
  - F12 → DROP (no fixture page); replace with one of the F-x existing fixtures so we still hit 15 features. Use `/sentence_hover_test/perf` as F12 (covers SSE-perf surface).
- **P2 fix:** F13 `/pin_replay` waits for ALL `vega-chart svg` elements (count=2) BEFORE screenshot.
- **P2 fix:** dynamic pages (F14 `/memory`, F15 `/benchmark`) use page.route mocks for backend so screenshots aren't dependent on backend state.

### Final PAGES table

```ts
const PAGES = [
  { feature: "F1",  path: "/intake",                              testid: "intake-form",                wait_svg_count: 0 },
  { feature: "F2",  path: "/disambiguation_modal_preview",        testid: "disambiguation-cluster-0",   wait_svg_count: 0 },
  { feature: "F3",  path: "/upload",                              testid: "upload-dropzone",            wait_svg_count: 0 },
  { feature: "F4",  path: "/sse",                                 testid: "sse-harness",                wait_svg_count: 0 },
  { feature: "F5",  path: "/sentence_hover_test/evidence_tooltip",testid: "evidence-tooltip-harness",   wait_svg_count: 0 },
  { feature: "F6",  path: "/sentence_hover_test",                 testid: "kept-sentence",              wait_svg_count: 0 },
  { feature: "F7",  path: "/sentence_hover_test/coverage",        testid: "frame-coverage-gaps",        wait_svg_count: 0 },
  { feature: "F8",  path: "/sentence_hover_test",                 testid: "kept-sentence",              wait_svg_count: 0 },
  { feature: "F9",  path: "/sentence_hover_test/evaluator_edge",  testid: "kept-sentence",              wait_svg_count: 0 },
  { feature: "F10", path: "/charts_test/forest_plot",             testid: "vega-chart",                 wait_svg_count: 1, mock_backend: false },
  { feature: "F11", path: "/contracts",                           testid: "contract-form",              wait_svg_count: 0 },
  { feature: "F12", path: "/sentence_hover_test/perf",            testid: "perf-trigger",               wait_svg_count: 0 },
  { feature: "F13", path: "/pin_replay",                          testid: "pin-snapshot-a",             wait_svg_count: 2 },
  { feature: "F14", path: "/memory",                              testid: "memory-banner",              wait_svg_count: 0, mock_memory: true },
  { feature: "F15", path: "/benchmark",                           testid: "benchmark-page",             wait_svg_count: 0, mock_benchmark: true },
];
```

For F14/F15 mocks, use `page.route('**/workspaces/ws_demo/memory', ...)` and `page.route('**/api/benchmark/**', ...)` returning seeded JSON.

## Iter 3 changes per Codex iter 2

- **P1 fix (Vega readiness):** for chart-bearing pages (F10 `/charts_test/forest_plot`, F13 `/pin_replay`), wait for `vega-chart svg` to be visible BEFORE screenshot. Add per-page optional `wait_for_selector` field to PAGES table.
- **P2 fix (testid corrections):** F7 → `frame-coverage-gaps`; F11 → `contract-form`; F12 → use `/intake` as proxy (no dashboard fixture id) OR drop F12 and use 14 features × 4 viewports + 1 extra page; let me use `/runs/r-demo` proxy with `runs-shell` testid if exists, otherwise drop F12 from coverage and document.
- **P2 fix (SSE):** use `domcontentloaded` for `/sse` plus `sse-harness` wait (no networkidle).

## Iter 2 changes per Codex iter 1

- **P1 fix (OS/browser gating):** restrict `visual_60_baselines.spec.ts` to Windows + chromium ONLY using `test.skip(...)` per-test based on `process.platform !== "win32" || testInfo.project.name !== "chromium"`. Document why in the spec docstring (single-OS baseline strategy; Linux + firefox/webkit baselines are follow-up I-p2c-002d).
- **P2 fix (CI not running visual):** acknowledged. Spec ships locally-runnable; CI Windows job lands later. Brief retracts CI-pixel-gating claim.
- **P2 fix (PAGES table):** enumerate all 15 entries explicitly in the brief and the spec. Backend-only features use closest fixture page (e.g., F11 corpus → `/corpus_brief_demo` if exists; otherwise `/intake` as proxy). Real fixture pages will be verified at write-time.
- **P2 fix (waitUntil):** use `await page.goto(p.path, { waitUntil: "networkidle" })` plus per-page sanity-testid wait BEFORE screenshot.

### PAGES enumeration (will be verified against actual web/app routes at write-time)

```ts
const PAGES = [
  { feature: "F1",  path: "/intake",                              testid: "intake-form" },
  { feature: "F2",  path: "/disambiguation_modal_preview",        testid: "disambiguation-cluster-0" },
  { feature: "F3",  path: "/upload",                              testid: "upload-dropzone" },
  { feature: "F4",  path: "/sse",                                 testid: "sse-harness" },
  { feature: "F5",  path: "/sentence_hover_test/evidence_tooltip",testid: "evidence-tooltip-harness" },
  { feature: "F6",  path: "/sentence_hover_test",                 testid: "kept-sentence" },
  { feature: "F7",  path: "/sentence_hover_test/coverage",        testid: "frame-coverage-panel" },
  { feature: "F8",  path: "/sentence_hover_test",                 testid: "kept-sentence" },
  { feature: "F9",  path: "/sentence_hover_test/evaluator_edge",  testid: "kept-sentence" },
  { feature: "F10", path: "/charts_test/forest_plot",             testid: "vega-chart" },
  { feature: "F11", path: "/contracts",                           testid: "contracts-page" },
  { feature: "F12", path: "/dashboard",                           testid: "dashboard" },
  { feature: "F13", path: "/pin_replay",                          testid: "pin-snapshot-a" },
  { feature: "F14", path: "/memory",                              testid: "memory-banner" },
  { feature: "F15", path: "/benchmark",                           testid: "benchmark-page" },
];
```

If a path/testid doesn't actually exist when the spec runs, downgrade that entry to the nearest stable fixture and document in the spec.

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Pre-flight

- **Issue:** I-p2c-002 — Visual regression: 60 baselines (4 viewports × 15 features). Scope: Playwright + percy.io baselines. Acceptance: zero unintended pixel diffs. LOC estimate 200.
- **Substrate today:** existing `web/tests/e2e/visual.spec.ts` (per playwright.config.ts F-5 note) covers some baselines but not the 60-screenshot 4×15 matrix.
- **Honest framing per CLAUDE.md §9.4 + LAW II + §8.4:**
  - **Percy.io integration deferred to follow-up I-p2c-002b** — percy.io is paid SaaS requiring user-side credentials + sign-up. Per "API-first, no paid SaaS in autonomous loops" memory feedback. This issue ships ONLY the Playwright-native `toHaveScreenshot()` baselines (stored as PNG snapshots alongside specs).
  - **Spec generates baselines on first `--update-snapshots`; subsequent runs assert pixel-equality.** Initial baselines committed in this PR cover stable fixture pages. Volatile pages (LLM-output reports) are excluded from this PR's matrix; that subset is I-p2c-002c.
  - **Subset choice:** 15 features = the 15 F-pages listed in `state/polaris_restart/issue_breakdown.md` F1-F15. Of those, several are backend-only (no UI page) — for I-p2c-002 we use the closest fixture/preview page for each.

## Plan

### `web/tests/e2e/visual_60_baselines.spec.ts` (NEW)

1. Define `VIEWPORTS = [{ name: "mobile", width: 375, height: 667 }, { name: "tablet", width: 768, height: 1024 }, { name: "laptop", width: 1280, height: 800 }, { name: "desktop", width: 1920, height: 1080 }]`.
2. Define `PAGES` array with 15 entries: `{ feature, path, primary_testid }` covering F1..F15 (use closest fixture page for backend-only features; mark with comment).
3. Parametrize: `for (const viewport of VIEWPORTS) { for (const p of PAGES) { test(\`F${...} ${viewport.name}\`, async ({ page }) => { ... }); } }` → 60 tests.
4. Each test: `page.setViewportSize(viewport)`; `page.goto(p.path)`; `await expect(page.getByTestId(p.primary_testid)).toBeVisible()` (sanity); `await expect(page).toHaveScreenshot(\`${p.feature}-${viewport.name}.png\`, { animations: "disabled", maxDiffPixelRatio: 0.01 })`.
5. Skip on Linux per existing `playwright.config.ts:23` convention (only Windows-chromium baselines committed first).

### Initial baselines

6. Run `npx playwright test visual_60_baselines.spec.ts --project chromium --update-snapshots` to generate the 60 PNG snapshots in `tests/e2e/visual_60_baselines.spec.ts-snapshots/`.
7. Commit the PNG snapshots so subsequent CI runs can assert against them.

### Out of scope

- Percy.io integration (follow-up I-p2c-002b — needs user-side credentials).
- Volatile-content baselines (e.g., live LLM report pages — follow-up I-p2c-002c).
- Cross-OS baselines beyond Windows-chromium (follow-up).

## Risks for Codex Red-Team

1. **PNG asset size:** 60 PNGs (~500 KB each) ≈ 30 MB. Substantive but committed to repo for CI parity.
2. **Brittleness:** any UI change to a fixture page breaks baseline; expected and intentional (regression detection works).
3. **Window scaling / fonts:** Playwright pins viewport size + DPR=1 in playwright.config.ts; fonts come from default system stack on Win32.
4. **§9.4 N/A frontend.**
5. **CHARTER §3 LOC cap:** estimated spec ~80-120 LOC. Under 200. PNG binary assets are NOT line-counted.

## Acceptance criteria

1. New `web/tests/e2e/visual_60_baselines.spec.ts` defines 60 `toHaveScreenshot` tests (4 viewports × 15 features).
2. Initial baseline PNGs committed under `tests/e2e/visual_60_baselines.spec.ts-snapshots/` (chromium-win32 variant).
3. CHARTER §3 LOC cap respected (≤200 net text additions; PNG binaries are out-of-band).
4. Spec docstring explicitly notes percy.io is follow-up I-p2c-002b.

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
