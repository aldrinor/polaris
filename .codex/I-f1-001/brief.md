# Codex Brief Review — I-f1-001 (ITER 2)

**Issue:** I-f1-001 — Next.js landing page Card grid
**Phase:** 1 / **Feature:** F1 (scope discovery + template browse)
**LOC budget:** 150 net (per `state/polaris_restart/issue_breakdown.md` §I-f1-001)

## Why iter-2 exists

Iter-1 verdict `REQUEST_CHANGES`: P1 — planned diff omitted updates to existing e2e tests `web/tests/e2e/home_walkthrough.spec.ts` (40 LOC) and `web/tests/e2e/demo_walkthrough.spec.ts` (68 LOC) that assert the OLD `demo-slice-*` testids on `/`. Replacing `web/app/page.tsx` per F1 spec WILL break those tests. P2 — `web/scripts/capture_screenshots.mjs` has stale "empty dashboard with 3 template cards" description. Iter-2 expands diff scope to address both.

## Mission

Replace the existing 4-slice "demo" landing page (`web/app/page.tsx`) with the F1 template-browse Card grid showing **3 active + 5 to-build templates**. Each active card links to `/intake?template=<id>`; each to-build card is visually distinguished as "coming soon" (no link). Responsive at 1920 / 1024 / 768 / 375 px. axe-core WCAG-AA clean. 4 viewport Playwright screenshots clean.

Per Carney plan §F1: "Next.js landing page with 8 template cards (3 active + 5 to-build) with scope summaries, in-scope examples, out-of-scope examples; live template-suggestion as user types." (live-suggest is I-f1-003, OUT OF SCOPE here.)

## Reconciling existing tests on `/` (iter-1 P1 closure)

The OLD home page surfaced 4 demo-slice cards (`demo-slice-intake/retrieval/generation/benchmark`). Two tests depend on that contract:

1. **`web/tests/e2e/home_walkthrough.spec.ts`** (40 LOC, 2 tests) — RETIRE entirely. Both tests (`renders walkthrough section with all 4 slice cards` + `each card links to its slice page`) assert the now-removed demo-slice cards. The replacement coverage is the new `landing_template_grid.spec.ts` introduced in this Issue. **Action:** delete the file.
2. **`web/tests/e2e/demo_walkthrough.spec.ts`** (68 LOC) — UPDATE in place. The 4-step demo flow (intake → retrieval → generation → benchmark via direct URL navigation) IS still valid; only the home-page entry-point assertion changes. **Action:**
   - First step: replace `getByTestId("demo-slice-intake").getByRole("link").click()` with `getByTestId("template-card-clinical").getByRole("link").click()` and `waitForURL("**/intake?template=clinical")` (still lands on intake, just with the template query param).
   - Second test (homepage card visibility) — replace `demo-slice-*` assertions with `template-card-clinical/housing/climate` visibility (the 3 active cards) and assertion that 5 disabled to-build cards are present too.
   - Remove the `Step 1`-`Step 4` step-label assertions (those were demo-slice CardDescription text that no longer exists). Keep the 4-page navigation walkthrough body which continues to work.

3. **`web/scripts/capture_screenshots.mjs`** — UPDATE description text "empty dashboard with 3 template cards" to "landing page with 8 template cards (3 active + 5 to-build)" or similar accurate phrase. Single-line change. P2-cosmetic per iter-1.

## Substrate (HONEST, unchanged from iter-1)

- `config/v6_templates/*.json` — 8 template files: `ai_sovereignty`, `canada_us`, `climate`, `clinical`, `defense`, `housing`, `trade`, `workforce`. Each conforms to `TemplateContent` schema (`src/polaris_v6/templates/registry.py:21`).
- `GET /templates` endpoint at `src/polaris_v6/api/templates.py` returns all 8 — but this Issue does NOT call it at runtime (rationale unchanged: landing must work without backend; future I-f1-007 wires runtime fetch).
- `web/app/page.tsx` (current 145 LOC) has 4 hardcoded `DemoSlice` cards — REPLACED.
- shadcn/ui `Card`, `CardContent`, `CardDescription`, `CardHeader`, `CardTitle`, `Button` already imported — keep.
- Tailwind v4 (`web/package.json:tailwindcss:^4`).
- Next.js 16.2.4 — per `web/AGENTS.md`: read `node_modules/next/dist/docs/` for any new feature use. This Issue uses ONLY the pattern already in place (server component + `next/link`), so no new-API risk.

## Active vs to-build classification

- **Active (3, linked to `/intake?template=<id>`):** `clinical`, `housing`, `climate` (have golden test fixtures in tests/v6).
- **To-build (5, "Coming soon" badge, `aria-disabled="true"`, no link):** `ai_sovereignty`, `canada_us`, `defense`, `trade`, `workforce` (alphabetical).

Order in grid: active first (clinical → housing → climate), then to-build alphabetical.

## Acceptance criteria (binding)

1. **8 template cards on `/`.** Each shows: template_name, summary (≥20 chars per schema), 1 in-scope sample_question, 1 out-of-scope example (if non-empty). Each card has `data-testid="template-card-<id>"`.

2. **Active cards link to `/intake?template=<id>`.** `<Link href="/intake?template=clinical">` etc. Click → Next.js navigation.

3. **To-build cards disabled.** `aria-disabled="true"`, "Coming soon" badge, muted styling, NO link, `tabIndex={-1}` to skip in keyboard nav. Screen reader announces "disabled."

4. **Responsive grid at 4 viewports.** 1920px → 4 cols (`xl:grid-cols-4`); 1024px → 3 cols (`lg:grid-cols-3`); 768px → 2 cols (`md:grid-cols-2`); 375px → 1 col (base).

5. **WCAG-AA axe-core clean** for `/` at 1024px. Test in new `web/tests/e2e/landing_template_grid.spec.ts`.

6. **4 viewport tests.** New `landing_template_grid.spec.ts` asserts 8 cards render at 1920×1080, 1024×768, 768×1024, 375×667. Active cards have `href` set; to-build have `aria-disabled="true"` + no `href`. Each viewport takes a screenshot stored at `web/tests/e2e/screenshots/landing_template_grid_<viewport>.png`. CI does not enforce screenshot-diffing on Linux per existing `web_ci.yml` policy; the test asserts DOM presence.

7. **Header preserved.** Keep "POLARIS Canada / Sovereign Deep Research" + "Sign in" button. Replace ONLY main content.

8. **Delete `home_walkthrough.spec.ts`.** Coverage migrates to `landing_template_grid.spec.ts`.

9. **Update `demo_walkthrough.spec.ts`.** Switch first-step entry from `demo-slice-intake` click to `template-card-clinical` click → `waitForURL("**/intake?template=clinical")`. Remove `Step 1..Step 4` text assertions. Keep the URL-navigation 4-page walkthrough.

10. **Update `web/scripts/capture_screenshots.mjs`.** One-line description update for `/` to reflect new content.

## Planned diff shape (revised iter-2)

```
web/app/page.tsx                                   MOD    +120/-80   (replace demo_slices with templates array + grid; net delta vs current 145 LOC)
web/tests/e2e/landing_template_grid.spec.ts        NEW    +90        (4 viewports × 8 cards + axe-core)
web/tests/e2e/home_walkthrough.spec.ts             DEL    -40        (retire — coverage in landing_template_grid)
web/tests/e2e/demo_walkthrough.spec.ts             MOD    +15/-25    (entry-point switch from demo-slice-intake → template-card-clinical; drop Step labels)
web/scripts/capture_screenshots.mjs                MOD    +1/-1      (description text)
```

LOC accounting: page.tsx delta net +40 (120-80) + new test +90 - retired test -40 + walkthrough mod -10 (15-25) + screenshots mod 0 (+1/-1) = **+80 net**. Within 150 LOC budget. Actual numbers may shift slightly; final disclosure in claude_audit.md.

## Out of scope (deferred to follow-up Issues per breakdown)

- Live template-suggestion as user types → I-f1-003
- Command palette + react-hotkeys-hook → I-f1-002
- BPEI false-positive adversarial test → I-f1-004
- Broader F1 axe coverage → I-f1-005
- Multi-tab safety → I-f1-006
- Runtime `GET /templates` fetch on landing → future I-f1-007 (post-runtime-cluster)

## Non-acceptance / explicit exclusions

- Does NOT call `GET /templates` at runtime — hardcoded in page.tsx (8 entries derived from `config/v6_templates/*.json` content at build time). Acceptable per F1 scope; landing must work without backend.
- Does NOT add `/templates/[id]` detail page.
- Does NOT add filtering or search UI (I-f1-002/003).
- Does NOT modify `web/lib/api.ts`.

## Risks for Codex Red-Team (revised iter-2)

1. **Hardcoding template data** vs runtime fetch — same as iter-1. Acceptable; future I-f1-007.
2. **Active vs to-build classification** — clinical/housing/climate active; rest to-build. Confirm matches plan intent.
3. **Tailwind v4 grid breakpoint mapping** — `xl` ≥1280 (4-col); `lg` ≥1024 (3-col); `md` ≥768 (2-col); base (1-col). Viewport tests: 1920→xl→4-col; 1024→lg→3-col; 768→md→2-col; 375→base→1-col. Consistent.
4. **Disabled cards a11y** — `aria-disabled="true"` + omit link + `tabIndex={-1}`. Verify axe-core does not flag.
5. **Visual regression baselines** — Linux CI skips visual diff per existing policy; test asserts DOM, not pixel-equality.
6. **Retiring `home_walkthrough.spec.ts`** — coverage moves to `landing_template_grid.spec.ts`. No regression in Issue surface.
7. **Demo walkthrough flow** — kept via direct URL navigation; only entry-point assertion changes.

## Output schema (mandatory)

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

List ALL findings this iteration. Do NOT hold any back to drip-feed across iterations. Same quality bar regardless of iteration count. No hard cap on iterations.
