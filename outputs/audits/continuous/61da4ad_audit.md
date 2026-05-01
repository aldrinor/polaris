# Audit — `61da4ad` (2 commits since cycle-7: F-21+F-22+F-23, F-24)

**Verdict:** APPROVE_WITH_FIXES. **Lock progress resets to 0/2.**
**Findings:** P0=0  P1=4  P2=2  P3=2
**Lens:** ACCESSIBILITY/UX (cycle 8, v2 protocol, first invocation of a11y lens)
**Lock check:** Cycle-7 was APPROVE_WITH_FIXES; cycle-8 returns APPROVE_WITH_FIXES. Two consecutive APPROVE not achieved. Lock progress 0/2; cycle-9 (correctness) → cycle-10 (security) needs both APPROVE for re-lock.

Two commits since cycle-7: `5975ca3` ships F-21 (protobuf<5.0.0 fix), F-22 (verify_pip_resolution CI job), F-23 (pip-dry-run protocol discipline) plus the cycle-7 audit/cross-review files. `61da4ad` ships F-24 (target-size: Inspector tabs, chart chips, shadcn Button h-9 default).

## Pre-flight

- **Files read:** `CLAUDE.md` §9 invariants, `.codex/AUDIT_CYCLE_PROTOCOL_v2.md` (incl. F-23 dependency-pin discipline), all 7 prior cycle audits + cross-reviews. **Did NOT read** `.codex/continuous/<sha>_*.md` per v2 brief-blinding.
- **Diffs read end-to-end:** `git show 5975ca3 -- requirements.txt .github/workflows/web_ci.yml .codex/AUDIT_CYCLE_PROTOCOL_v2.md`, `git show 61da4ad -- web/app/inspector/[runId]/page.tsx web/components/ui/button.tsx`. Read affected files at HEAD plus `web/app/dashboard/page.tsx`, `web/app/runs/[runId]/page.tsx`, `web/components/ui/input.tsx`, `web/components/ui/evidence-tooltip.tsx`.
- **Tests run live (servers up at 127.0.0.1:8000 + 3738):**
  - `npx playwright test --project=chromium tests/e2e/accessibility.spec.ts` → **10/10 passed in 20.4s**. F-24's named surfaces are axe-clean.
  - 3 ad-hoc Playwright probes (live measurements + tab-order enumeration) on Inspector + Dashboard; spec files removed after data capture.
- **Cycle-7 P1.1 closure check:** `pip install --dry-run -r requirements.txt` resolves cleanly; pip would install `protobuf-4.25.9` (CVE-2026-0994 vulnerable range starts at 6.30.0rc1 — entirely above the `<5.0.0` ceiling). F-21 closes the regression.
- **Live target-size measurements** (chromium, default viewport):
  - Inspector tab buttons: 44px height (was ~21px effective pre-F-24). PASS.
  - Chart chips: 34px height (target was ≥28px). PASS.
  - Default Button (Inspector "Export bundle JSON", Dashboard "Check scope"/"Start run"): 36px height. PASS.

## Per-criterion forced enumeration (a11y/UX lens)

- **C-a11y-target-size-F-24-named-surfaces (probe 1):** PASS. All three F-24-named surfaces measure ≥28px live and clear axe.
- **C-a11y-target-size-other-surfaces (probe 1, deeper):** **FAIL on 4 adjacent surfaces.** See **P1.1**.
- **C-a11y-keyboard-nav-template-cards (probe 2):** **FAIL Level A.** See **P1.2**.
- **C-a11y-keyboard-nav-tab-order (probe 2):** PASS for Inspector. Dashboard has the Level-A blocker (P1.2) which makes tab-order moot — once template cards are made keyboard-reachable they'll need to enter the tab order.
- **C-a11y-focus-management-on-state-change (probe 3):** FAIL. Scope-rejection card on dashboard has no `aria-live`, no `role="status"`, focus stays on Check-scope button. See **P1.3**.
- **C-a11y-skip-links (probe 4):** No skip links on any page. Keep as **P3.1** — best-practice, not strict WCAG-AA.
- **C-a11y-form-error-banners (probe 5):** PASS. Every error banner I checked has `role="alert"` (`dashboard/page.tsx:417`, `inspector/[runId]/page.tsx:119,666`, `runs/[runId]/page.tsx:124`).
- **C-a11y-tab-semantics (probe 6):** Inspector "tabs" are bare `<button>` elements with no `role="tab"`, no `aria-selected`, no `role="tablist"` parent. **P2.1** — visible labels + active state are clear; this degrades screen-reader UX but doesn't fail strict WCAG-AA.
- **C-a11y-color-only-signals (probe 7):** PASS. Two-family-invariant card uses border color + "PASS"/"FAIL" text + model lineage in CardTitle. Color is supplementary.
- **C-a11y-touch-pointer-parity (probe 8):** PASS. Decorative dividers (`bg-foreground` progress bars, frame-coverage gauge) are `<div>` not `<button>`. F-24 didn't accidentally make any decorative element a target.
- **C-a11y-charts-tab-error-page (probe 9):** PASS. Both surfaces axe-clean.
- **C-perf-out-of-lens-cycle7-P1-carryover (probe 10):** **CLOSED by F-21.** Dry-run resolves to protobuf-4.25.9. F-22 CI job exists at `.github/workflows/web_ci.yml:151-175` and gates `pytest_v6_backend`. F-23 protocol-doc text shipped at `AUDIT_CYCLE_PROTOCOL_v2.md:82-94`.
- **C-a11y-heading-hierarchy (probe deeper):** Inspector page exposes only one `<h1>` (the question). Six tab panels are unnamed. Best-practice gap → **P3.2**.

## P0

NONE. No silent failure, no broken auth, no data loss, no perf-budget violation, no a11y blocker that prevents *any* user from completing the primary flow with a non-keyboard input modality.

## P1

**P1.1 — WCAG 2.5.8 target-size failures on 4 surfaces F-24 did NOT scope.** Live measurements show:

| Surface | File:line | Height × width (px) | WCAG 2.5.8 AA (24×24) |
|---|---|---|---|
| Upload-list "remove" button | `web/app/dashboard/page.tsx:317-327` | 16 × 36 | FAIL (height) |
| Dropzone "browse files" label | `web/app/dashboard/page.tsx:282-295` | 20 × 68 | FAIL (height) |
| Provenance token (`[#ev:...]`) | `web/components/ui/evidence-tooltip.tsx:30-38` | 16 × 202 | FAIL (height) |
| "contradiction in section →" pill | `web/app/inspector/[runId]/page.tsx:296-302` | 20 × 170 | FAIL (height) |

These exist alongside (not inside) F-24's three scoped surfaces. The Playwright a11y suite at HEAD passes 10/10 because no probe route exercises these surfaces with the right state — the upload-list test asserts `axe-clean once "remove" button renders` but `target-size` is one of axe's looser rules and only fires when overlap analysis detects a hit-region collision; isolated small targets pass axe but still fail WCAG 2.2 SC 2.5.8 strict reading. Provenance tokens are by far the highest-volume offender (one per evidence reference; potentially hundreds per Inspector page).

Why this matters under a11y lens: WCAG 2.5.8 explicitly targets users with reduced motor precision, hand tremors, or pointing on a touchscreen with thick fingers. A 16-pixel-tall hit target is below the documented threshold even in AA's relaxed 24×24 form (which already softened from AAA's 44×44). All four surfaces are actively-clicked-during-normal-use, not edge cases.

Tag: **root_cause** — F-24 closed the three surfaces axe surfaced under cycle-7 P3.2; this audit's deeper probe finds the adjacent class. Verify by adding a `min-h-[24px]` (and `min-w-[24px]` for the remove button which trims to text-width) to each, or wrapping the icon-text targets in a tappable parent. Add an axe-augmenting Playwright assertion that walks every `<button>`/`<label>`/clickable-`<a>` and asserts `getBoundingClientRect()` height & width ≥ 24.

**P1.2 — WCAG 2.1.1 (Keyboard, Level A) failure: Template Cards on dashboard are unreachable by keyboard.** `web/app/dashboard/page.tsx:221-238` renders each of 8 template cards as:

```tsx
<Card key={t.id} className={`cursor-pointer ...`} onClick={() => setTemplate(t.id)}>
```

The `<Card>` primitive renders as a `<div>` (verified live: `tag: "DIV"`, `role: null`, `tabindex: null`). React's `onClick` attaches a synthetic listener but the DOM element exposes no `tabindex`, no `role="button"`, and no keyboard handler. **A keyboard-only user CANNOT select a template at all.** The default selection (`useState<TemplateId>("clinical")`) means the page is technically operable for the clinical template — but for any other template (housing, defense, AI sovereignty, etc.) keyboard users are locked out of the primary-flow entry point.

This is **WCAG 2.1.1 Level A** — strictly more severe than the AA ceiling protection cycle-7 audited. It survived seven prior audit cycles because axe doesn't flag click-on-non-interactive when the React listener is attached via JSX prop (axe inspects DOM attributes, not React's reconciler).

Tag: **root_cause** — convert template cards to either `<button>` elements (with `aria-pressed` for radio-group semantics) or add `role="radio"`/`tabindex="0"` + `onKeyDown` handler matching `Space`/`Enter`. Verify with a Playwright keyboard-only test that lands on `/dashboard`, presses Tab to reach a non-default card, presses `Space`, and asserts the template state changed.

**P1.3 — WCAG 4.1.3 (Status Messages, Level AA) failure: scope-rejection card not announced and focus not moved.** When the user clicks "Check scope" and the backend returns `verdict: "rejected"`, `dashboard/page.tsx:334-367` renders a Card with `border-destructive/60`. Live probe confirms: `aria-live: null`, `role: null`, focus remains on the now-disabled Check-scope button (`focusedTag: "BODY"` after rejection — focus actually escaped to body, an even worse outcome).

For a screen-reader user, the rejection is silent. They press Check scope, hear nothing, and have no signal that they need to reframe. The error banner at `:415-422` does have `role="alert"` — but `error` state is set only on network/parse failures, not on `verdict === "rejected"` (the rejection is a successful-API-call result, not an error).

Tag: **root_cause** — wrap the scope-decision Card in `role="status"` + `aria-live="polite"`, OR move focus to the card's CardTitle on first render via a `useEffect` keyed on `scopeDecision`. Same fix needed for the ambiguity-cluster card at `:369-413` (also async-rendered, no announcement).

**P1.4 — Decorative `<a>` rendered as Cancel "button" gets `role="button"` semantics but no h-9 size guarantee.** `dashboard/page.tsx:425-431` and several places in `runs/[runId]/page.tsx` use `<Button render={<Link href="/" />}>`. Live probe confirms: tag `A`, `role="button"`, height 36px (gets the F-24 h-9). PASS for target-size *currently*. But the pattern is fragile — Base UI's `render` prop forwards class but if anyone adds a Tailwind override that wins specificity (e.g. via `cn(buttonVariants(…), className)` where `className="h-7"`), the link-as-button silently shrinks. There's no enforcement that link-as-button stays ≥24px.

Tag: **guardrail** — add a Playwright assertion that walks every `[role="button"]` (regardless of underlying tag) and asserts ≥24×24. Light-weight version of P1.1's assertion. Closes the synthetic-button surface.

## P2

**P2.1 — Inspector tab buttons lack ARIA tab semantics.** The 6 tab buttons at `inspector/[runId]/page.tsx:194-208` render as bare `<button>` elements: `role: null`, `ariaSelected: null`, `ariaControls: null`. Their parent `<nav>` has no `role="tablist"`. WAI-ARIA Authoring Practices Guide recommends `role="tab"` + `aria-selected="true"` + `aria-controls={tabpanel-id}` + parent `role="tablist"` for this pattern. axe doesn't flag because axe's `tablist`/`tab` rules only fire when *partial* ARIA tab semantics are present (e.g., `role="tab"` without `role="tablist"` parent). Bare-button tabs pass axe but degrade screen-reader UX: NVDA/VoiceOver announce each as "Executive summary 3, button" instead of "Executive summary 3, tab, 1 of 6, selected". Not a strict WCAG-AA failure (visible labels + active state are clear; keyboard nav works via Tab); P2 because it's a known-better pattern with code in scope.

Tag: **band_aid → root_cause** — small refactor to add roles + arrow-key cycling. Could also consider Base UI's `Tabs` primitive (likely already available given the dependency).

**P2.2 — Input field height is `h-8` (32px) — passes 2.5.8 AA (24×24) but inconsistent with the F-24 Button bump.** `web/components/ui/input.tsx:12` keeps `h-8`. The F-24 author explicitly noted "h-8 reported as ~21px effective by axe due to inner text-bounding-box measurement quirks" and bumped Button to h-9 for safety. The same axe behavior likely applies to `<Input>`, but the a11y suite passes because dashboard's `#question` Input is the only Input on tested routes and its native-text-input nature gives axe a heuristic pass. Cycle-9 (correctness lens) or cycle-12 (next a11y rotation) may probe deeper. Not a P1 because: live measurement was 32px, axe passes, and `<Input>` heights are typically less safety-margin-needed than buttons (browsers render text inputs with implicit padding). Tag: **guardrail** — keep an eye on it; if any cycle catches axe flagging Input target-size, bump to h-9 for parity.

## P3

**P3.1 — No "skip to main content" link on any page.** Long Inspector pages (verified-sentences with hundreds of provenance tokens) make Tab-to-main-content tedious for keyboard users. Best-practice (WCAG 2.4.1 has a Level A bypass-blocks SC, but it's satisfied by the heading-based navigation that screen readers expose; sighted keyboard-only users without screen readers don't get that affordance). Tag: **out-of-scope-observed** — adding a skip-link is a polish item.

**P3.2 — Inspector heading hierarchy is shallow.** Only one `<h1>` (the question). The 6 tab panels rendered into `<main>` use `CardTitle` (likely `<div>` or styled `<p>` per shadcn defaults). A screen-reader user navigating by heading (`H` key in NVDA) skips immediately past the question to next-page. Best-practice; not a strict WCAG-AA failure. Tag: **out-of-scope-observed.**

## Cross-cycle integrity

- Cycle-7 P1.1 (protobuf install break): **CLOSED by F-21.** Dry-run resolves to protobuf-4.25.9 (CVE-clean). Verified live.
- Cycle-7 P2.1 (verify_pip_resolution CI guardrail): **CLOSED by F-22.** Job at `.github/workflows/web_ci.yml:151-175` runs before `pytest_v6_backend` (added to that job's `needs:` list).
- Cycle-7 P3.1 (audit-trail integrity protocol gap): **CLOSED by F-23.** New section "Dependency-pin discipline" at protocol doc requires `pip-dry-run: PASSED` line on pin-change commits. F-21's commit message includes that line.
- Cycle-7 P3.2 (target-size out-of-lens observed): **PARTIALLY CLOSED by F-24** — the three named surfaces (Inspector tabs, chart chips, Button h-9). New P1.1 above identifies the adjacent un-scoped class.
- Cycle-7 P3.3 (commit-message verification phrasing): **STRENGTHENED by F-23 discipline.** F-21's commit message includes specific verification evidence (`pip-dry-run: PASSED` plus targeted dry-run output).
- Earlier-cycle items (cycle-1 through cycle-6 carryover): unchanged.
- F-22 needs-graph correctness: `pytest_v6_backend.needs: [lint_format_typecheck_build, verify_pip_resolution]`. The latter also needs `lint_format_typecheck_build`. Diamond dependency is fine in GitHub Actions; verified by reading the YAML.

## Reviewer independence statement

I am the brief-blinded cycle-8 subagent invoked per protocol v2 (accessibility/UX lens). I read CLAUDE.md, `architecture.md`, the protocol doc (incl. F-23 additions), all 7 prior cycle-level audits + cross-reviews. **I did NOT read any file under `.codex/continuous/<sha>_*.md`** (per v2 brief-blinding).

I read the cycle-8 diffs (`git show 5975ca3` + `git show 61da4ad`), inspected modified files end-to-end including `web/app/dashboard/page.tsx`, `web/components/ui/input.tsx`, `web/components/ui/evidence-tooltip.tsx`, ran the Playwright a11y suite live (10/10 passed), wrote 3 ad-hoc probes that measured `getBoundingClientRect()` on every relevant surface and enumerated tab order on `/dashboard` and `/inspector/golden_clinical_001`, then deleted those probe specs.

I confirmed F-21's pip resolution by running `pip install --dry-run --no-deps -r requirements.txt` (no ResolutionImpossible; would install protobuf-4.25.9). I confirmed F-22's CI job structure by reading `web_ci.yml`. I confirmed F-23's protocol-doc text by reading the diff and the file at HEAD.

AGREE with cycle-7's claim that F-21 closes P1.1 and that F-24 fixed its three named surfaces. F-22 + F-23 are clean guardrails with no a11y/UX cost.

DISAGREE with the implicit framing in `61da4ad`'s commit message that F-24 "preempts cycle-8 (a11y lens) re-flagging them as P1." F-24 closed exactly what cycle-7 P3.2 named — but a deeper a11y probe (running tab-order enumeration, measuring every clickable hit-target in the DOM, inspecting tab semantics, checking focus management on async state changes) surfaces 4 distinct P1-class issues that cycles 1-7 missed because earlier lenses didn't probe DOM-level interactivity at the precision a11y requires. P1.2 (template-card keyboard inaccessibility) is the strongest of these — a Level-A failure on the primary-flow entry screen that survived seven cycles of review.

The cycle-8 finding rate is exactly what v2's rotating-lens design targeted: lenses are lossy filters, and lens-rotation each cycle peels back another layer.

## Verdict

**APPROVE_WITH_FIXES.** P0 = 0; P1 = 4. The cycle-8 batch ships clean closures of all three cycle-7 outstanding items (F-21/F-22/F-23) plus targeted touch-target fixes for the three F-24-scoped surfaces. But the a11y lens, on first invocation in 8 cycles, surfaces 4 P1-class issues spanning target-size (P1.1, 4 surfaces), keyboard accessibility (P1.2 — Level A), status-message announcement (P1.3), and synthetic-button safety (P1.4).

**LOCK PROGRESS: 0/2.** Cycle-7 was APPROVE_WITH_FIXES; cycle-8 returns APPROVE_WITH_FIXES. Two consecutive APPROVE not achieved. Per v2 protocol, lock progress resets — cycle-9 (correctness, per round-robin) and cycle-10 (security) need both APPROVE for re-lock.

Required for cycle-9 (correctness lens) re-attempt:
- **F-25 (P1.1, root_cause):** Add `min-h-[24px]` (+ `min-w-[24px]` where text-width is variable) to: dashboard `remove` button, `browse files` label, EvidenceTooltip provenance-token button, contradiction-in-section pill. Add Playwright assertion walking all `<button>`/`<label>`/`<a role="button">` for ≥24×24.
- **F-26 (P1.2, root_cause):** Make dashboard template `<Card>` keyboard-operable. Convert to `<button>` (or add `role="button"`/`tabindex="0"`/keyboard handler). Add Playwright keyboard-only test for non-default template selection.
- **F-27 (P1.3, root_cause):** Add `role="status"` + `aria-live="polite"` to scope-decision Card (and ambiguity-cluster Card). Optionally move focus to CardTitle on first render via `useEffect`.
- **F-28 (P1.4, guardrail):** Playwright assertion walking every `[role="button"]` (any tag) for ≥24×24.

Carryover non-blocking: P2.1 (ARIA tab semantics), P2.2 (Input h-8 vs h-9 parity), P3.1 (skip links), P3.2 (heading hierarchy). Cycle-12 (next a11y rotation) should re-probe.
