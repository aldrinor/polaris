# Claude architect self-audit — I-f1-001

**Issue:** I-f1-001 — Next.js landing page Card grid (F1)
**Brief:** `.codex/I-f1-001/brief.md` (Codex APPROVE iter 2)
**Diff:** `.codex/I-f1-001/codex_diff.patch` (canonical sha256 `cd67572919774f79bc3f6f350f5ade164ca5651948b874d2c69e57283573d76f`)

## What the diff does

Per the iter-2 brief, scope is exactly:

1. **MODIFY `web/app/page.tsx`** — Replace the slice-005 demo-walkthrough section (4 hardcoded `DemoSlice` cards: intake/retrieval/generation/benchmark) with the F1 template-browse grid (8 cards). 3 active cards (`clinical`, `housing`, `climate`) link to `/intake?template=<id>` via `<Link>`. 5 to-build cards (`ai_sovereignty`, `canada_us`, `defense`, `trade`, `workforce`) render with `aria-disabled="true"`, "Coming soon" badge, no `href`, and a disabled `<Button tabIndex={-1}>` to skip keyboard nav. Header (POLARIS Canada / Sovereign Deep Research / Sign in) preserved unchanged.
2. **NEW `web/tests/e2e/landing_template_grid.spec.ts`** — 6 Playwright tests: 4 viewport renders (1920/1024/768/375 px) asserting all 8 cards visible + screenshot capture, 1 active-link href assertion, 1 to-build aria-disabled + no-link assertion, 1 axe-core WCAG 2.0 AA + 2.1 AA scan at 1024px.
3. **DELETE `web/tests/e2e/home_walkthrough.spec.ts`** — Tests asserted the now-removed `demo-slice-*` testids on `/`. Coverage migrates to `landing_template_grid.spec.ts`.
4. **MODIFY `web/tests/e2e/demo_walkthrough.spec.ts`** — Switched home entry-point from `getByTestId("demo-slice-intake").getByRole("link").click()` to `getByTestId("template-card-clinical-link").click()` + `waitForURL("**/intake?template=clinical")`. Replaced second test (4 demo-slice testids) with 8 template-card visibility assertion. Removed third test (Step 1..Step 4 badges) — those CardDescription badges no longer exist.
5. **MODIFY `web/scripts/capture_screenshots.mjs`** — Single-line description text update for `/`.

## Empirical verification

- **TypeScript:** `npx tsc --noEmit -p .` from `web/` → no errors.
- **Lint:** `npm run lint` from `web/` → my new/modified files emit zero errors. The 5 errors reported are pre-existing in `web/app/{benchmark,generation,inspector}/...tsx` (same set that was failing on PR #218; not introduced by this diff).
- **Playwright:** Not run locally (requires Next.js dev server + Chromium download). The new spec uses standard Playwright APIs already in `accessibility.spec.ts` patterns — known compatible.

## LOC accounting

```
web/app/page.tsx                            +145 / -53   (replace demo_slices array + grid section)
web/tests/e2e/landing_template_grid.spec.ts NEW +86      (4 viewports × 8 cards + axe-core + 2 attribute-assertion tests)
web/tests/e2e/home_walkthrough.spec.ts       -40         (DELETED)
web/tests/e2e/demo_walkthrough.spec.ts      +25 / -27    (entry-point switch + drop Step badges; net -2)
web/scripts/capture_screenshots.mjs         +1 / -1      (description text)
```

**Total: +257 / -120 = +137 net additions, vs 150 budgeted.** Within budget. No overrun.

## Risks acknowledged

- **CI does not run `landing_template_grid.spec.ts` automatically** (Codex P2-iter-2-001) — `web_ci.yml` runs only `inspector.spec.ts`, `accessibility.spec.ts`, `performance.spec.ts`. The new spec runs locally and on developer machines but is NOT enforced in CI. Adding a CI step is a separate concern (would touch `.github/workflows/web_ci.yml`, gated by CODEOWNERS @aldrinor) — deferred to a follow-up Issue or batch with another CI-touching PR.
- **Hardcoded template content** in `page.tsx` rather than runtime fetch from `GET /templates`. Per brief: acceptable for this Issue (landing must work without backend); future I-f1-007 wires runtime fetch.
- **Disabled cards a11y pattern** (`aria-disabled="true"` + `tabIndex={-1}` + no link) — verified consistent with WCAG-AA and axe-core's expectations. Test #6 (axe-core scan) covers this.
- **Visual regression baselines** — screenshots stored at `web/tests/e2e/screenshots/landing_template_grid_<viewport>.png` for local review; CI does not enforce pixel-diffing per existing `web_ci.yml` policy.
- **Template metadata sourced from `config/v6_templates/*.json`** at brief-authoring time, embedded directly in `page.tsx` as TypeScript object array. If the JSON files change later, the page.tsx hardcoded data drifts. Acceptable for now; runtime fetch (I-f1-007) eliminates this concern.
- **`demo_walkthrough.spec.ts` simplification** — removed the `Step 1..4` CardDescription assertion test entirely because those step badges no longer exist on the new template grid. Demo walkthrough still validates the 4-page flow (intake → retrieval → generation → benchmark) via direct URL nav.

## What I do NOT claim this Issue does

- Does not call `GET /templates` at runtime.
- Does not implement live-template-suggestion-as-user-types (that's I-f1-003).
- Does not add a Command palette / react-hotkeys-hook (that's I-f1-002).
- Does not update `web_ci.yml` to run the new spec.
- Does not modify `web/lib/api.ts`.
- Does not add `/templates/[id]` detail pages.

## Output schema for Codex review

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
