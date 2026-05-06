# Codex Brief Review — I-f1-005 (ITER 3 of 5)

## Iter-1 + iter-2 fixes
- **iter-1 P1 palette listbox `aria-required-children`:** add `role="option"` + `aria-selected` to each `<li>`.
- **iter-2 P1 palette listbox needs accessible name:** add `aria-label="Template results"` to the `<ul role="listbox">`. Closes axe `aria-input-field-name` (wcag2a, serious).
- **iter-2 P2 brief exclusion contradiction:** removed "Does NOT modify production components" from non-acceptance list.
- **iter-1 P2 WCAG_TAGS drift:** use the 4-tag set matching landing_template_grid (`wcag2a/wcag2aa/wcag21a/wcag21aa`).

**HARD ITERATION CAP: 5 per document. This is iter 3 of 5.**
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

**Issue:** I-f1-005 — F1 axe-core WCAG-AA compliance test
**Phase:** 1 / **Feature:** F1
**LOC budget:** 60 net per `state/polaris_restart/issue_breakdown.md`. **CHARTER §1 hard cap: 200.**

## Mission

Add axe-core WCAG-AA scans for the F1 surfaces NOT yet covered by existing specs:
- `/` with command palette OPEN (Ctrl+K, palette + backdrop visible — built in I-f1-002).
- `/intake?template=clinical` (the page F1 cards link to — built in I-f1-001).

Existing coverage:
- `web/tests/e2e/landing_template_grid.spec.ts` already scans `/` at 1024px (palette CLOSED). Don't duplicate.
- `web/tests/e2e/accessibility.spec.ts` already scans `/dashboard` + `/inspector/*`. Don't duplicate.

## Substrate (HONEST)

- `@axe-core/playwright` ^4.11.3 already in `web/package.json` (used at landing_template_grid + accessibility specs).
- The shared helper `expectNoA11yViolations(page)` lives in `accessibility.spec.ts` but is NOT exported. To stay LOC-tight, reuse `AxeBuilder` directly with the same `WCAG_TAGS` array (`wcag2a, wcag2aa, wcag21a, wcag21aa`).
- I-f1-002 added `<DialogPrimitive.Title className="sr-only">` (screen-reader-only "Search templates" label) so the open-palette dialog has the required title. Should pass axe.
- `/intake?template=clinical` exists per slice 001; it's the target of F1 active cards. Need to confirm it loads cleanly without backend (no API call required for first render).

## Acceptance criteria (binding)

1. **`web/tests/e2e/f1_a11y.spec.ts`** (NEW) — 2 tests, each at 1024×768 viewport:
   - **Test 1 — `/` with palette OPEN is WCAG-AA clean:** goto `/`, wait header-sign-in-link visible, press `Control+k`, wait `command-palette` visible, run AxeBuilder scan, assert `results.violations` filtered for impact ∈ {`serious`, `critical`} is empty (issue spec: "zero serious/critical violations").
   - **Test 2 — `/intake?template=clinical` initial render is WCAG-AA clean:** goto `/intake?template=clinical`, wait `intake-page` testid visible, run AxeBuilder, assert serious/critical empty.

2. **`web/app/components/command_palette.tsx`** (MODIFY): (a) add `role="option"` + `aria-selected={i === clamped}` to each `<li>` (closes axe `aria-required-children`); (b) add `aria-label="Template results"` to the `<ul role="listbox">` (closes axe `aria-input-field-name`). ~4 LOC.

3. **Filter on impact severity (`serious` + `critical` only)** per issue spec; non-critical (e.g. `moderate`, `minor`) violations are NOT blocking. This matches the issue acceptance criterion "zero serious/critical violations" rather than "zero violations of any severity."

## Planned diff shape

```
web/app/components/command_palette.tsx       MOD +2/-1   (role="option" + aria-selected on <li>)
web/tests/e2e/f1_a11y.spec.ts                 NEW +50
```

LOC: +52/-1 = +51 net. Under 60 budget AND under CHARTER §1 200-cap.

## Out of scope (deferred per breakdown)

- Multi-tab safety → I-f1-006

## Non-acceptance / explicit exclusions

(prior "no production code change" exclusion REMOVED iter-2; small a11y fixes to `command_palette.tsx` are in scope per AC #2).
- Does NOT scan `/dashboard` or `/inspector/*` (existing coverage).
- Does NOT scan `/` with palette CLOSED (existing landing_template_grid coverage).
- Does NOT add CI step to run this spec automatically (`web_ci.yml` runs only inspector/accessibility/performance per existing policy; this spec runs locally).

## Risks for Codex Red-Team

1. **Severity filter (`serious` + `critical` only).** Issue spec explicitly says "zero serious/critical violations" — not "zero violations." Filter `results.violations.filter(v => v.impact === "serious" || v.impact === "critical")`. Acceptable per issue acceptance criterion.

2. **Open-palette state requires Ctrl+K press AFTER hydration.** Test waits for `header-sign-in-link` visible before pressing (hydration race avoidance, same pattern as I-f1-002 + I-f1-003). axe runs after `command-palette` testid is visible (proves Dialog mounted in portal).

3. **`/intake?template=clinical` may emit network calls** (intake form may auto-load template metadata). If those calls fail without backend, axe still scans the rendered DOM; `waitUntil: "networkidle"` may stall on retried fetches. Use `waitUntil: "domcontentloaded"` + explicit wait on `intake-page` testid as the hydration signal — proves React rendered. Acceptable trade-off.

4. **Sr-only DialogPrimitive.Title.** I-f1-002 added the screen-reader title. axe `aria-required-children` and `dialog-name` rules check for accessible names; should pass.

5. **Reuse vs export `expectNoA11yViolations`.** Current accessibility.spec.ts has the helper but doesn't export. Importing across test files is awkward. Inlining the AxeBuilder call adds ~6 LOC × 2 tests = 12 LOC vs ~3 LOC × 2 + helper. Stays under budget either way; choose inline for fewer cross-file dependencies.

6. **Backdrop interactivity / z-index a11y.** When palette is open, the backdrop has `bg-black/20` and the popup has `z-50`. axe `tabindex` rule may flag if focus traps are mis-set; @base-ui/dialog handles focus management internally. Should pass.

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
