HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1.
- "Don't pick bone from egg" — P1 only for real execution risks.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# Codex brief review — I-cd-022 (#612) — / (home) rebuild

## §A Findings from grep (real state of the home page today)

1. **G1 violation (double header)**: `web/app/page.tsx` wraps content in `<HomeKeyboardShell>` which renders its OWN `<header>` (web/app/components/home_keyboard_shell.tsx:40-65). But `web/app/layout.tsx:36` ALREADY wraps every page in `<AppShell>` which has its own `<header>` + nav (web/components/app_shell.tsx:33-65). Result: TWO headers stacked vertically on `/`.
2. **G2 violation (dev language)**: home `<footer>` text "POLARIS v6.2 — slices 1-5 shipped" (page.tsx:214) is user-visible dev language. "slices" is internal terminology.
3. **G2 violation (second instance)**: AppShell docstring references `I-cd-013..030 series` — not user-visible (it's a comment).
4. **G3 (interactive states)**: Template cards have hover + disabled + aria-disabled. Active button has focus-visible ring via shadcn Button. PASS.
5. **G4 (async states)**: home is static — no API call. PASS by default.
6. **G5 (responsive)**: grid uses `md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4`. Tested manually at 1440px + 1024px. PASS.
7. **G6 (a11y)**: existing `aria-labelledby`, `aria-disabled`, semantic `<main>` + `<section>`. Need to verify keyboard nav of CommandPalette + focus ring.
8. **G7 (design tokens)**: page uses `bg-background`, `text-foreground`, `border-border`, `text-muted-foreground` — all token-driven. PASS.
9. **G8 (console clean)**: needs verification via Playwright spec.

## §B Implementation (revised per Codex iter-1 P1)

Iter-1 P1 caught: removing the HomeKeyboardShell header would also remove the `header-sign-in-link` + `signInLinkRef` focus target that 5 existing specs depend on (command_palette*.spec.ts, f1_multi_tab.spec.ts, f1_a11y.spec.ts). Revised plan:

1. **Keep HomeKeyboardShell's header** AS the home route's primary visible header (it has the brand + sign-in + Cmd+K palette). The AppShell's own `<header>` is conditionally hidden on `/`.
2. **AppShell becomes pathname-aware** (iter-2 P1 fix) — a tiny client wrapper uses `usePathname()` to skip BOTH the AppShell `<header>` AND its `<main>` wrapper on `/`. The home route then provides its own `<header>` + `<main>` directly (preserves single-banner + single-main landmarks).
3. Home page provides its own page-level `<main>` (no nested landmarks; AppShell on `/` only renders `{children}` with no wrapping).
4. **Add the AppShell primary nav INTO HomeKeyboardShell's header** so home gets nav parity with all other routes — G1 "global header/sidebar nav is present and identical." Move the `PRIMARY_NAV` constant + `NavLink` rendering into the home header. Both headers (home AppShell-suppressed + non-home AppShell) carry the same nav.
5. **Strip G2 violations**:
   - `page.tsx:214` "POLARIS v6.2 — slices 1-5 shipped" → "POLARIS · Sovereign Canadian deep research"
   - "1 active · 7 to-build" → "1 active · 7 in development"
6. **New Playwright spec** `web/tests/e2e/home_g1_g8.spec.ts`:
   - G1: page has exactly ONE `<header>` element + primary nav links visible
   - G2: text content does NOT match `/slice|scaffold|placeholder|phase 0|post-carney|i-cd-/i`
   - G3: active template card link/button has `focus-visible:ring-*` CSS class (testing the LINK, not the card per iter-1 P2)
   - G6: page has exactly ONE `<main>` landmark element + keyboard-tabbable into the active card link
   - G8: zero console errors during load
7. **Wire into `.github/workflows/web_ci.yml`** — run as a binding CI step.

Estimated canonical diff: **~180 LOC**.

## §C Acceptance check

| Gate | Met by |
|---|---|
| G1: single header on `/` (outside `<main>`, with primary nav) | AppShell suppressed on `/`; HomeKeyboardShell provides the header with PRIMARY_NAV moved into it |
| G2: no dev language in user-visible strings | page.tsx text edits |
| G3: interactive states | existing shadcn Button + hover classes |
| G4: async states | N/A (static page) |
| G5: responsive 1440px + 1024px | existing grid classes |
| G6: a11y | existing semantic + role/aria; spec asserts keyboard navigability |
| G7: design tokens only | existing token usage |
| G8: console clean | Playwright spec mechanical check |
| Acceptance spec runs in CI | wire into `.github/workflows/web_ci.yml` |

## §D Red-team checklist

1. The HomeKeyboardShell currently wraps the CommandPalette keyboard handler in `useEffect` with `Cmd+K`. Removing the header MUST NOT remove that handler.
2. The signInHref prop is currently passed to HomeKeyboardShell to render a "Sign in" button in its header. After refactor, the sign-in surfaces via AppShell's nav OR a route-level link. Either keep the prop and ignore it (back-compat) or remove it from the signature.
3. Strip "slices 1-5" dev language without breaking any existing test that may grep that text.
4. Some existing route tests may grep "POLARIS v6.2" — search before changing.
5. The new Playwright spec MUST wire into `.github/workflows/web_ci.yml` to be a binding gate.
6. Test the spec locally against `next start` in prod mode (matches CI) before pushing.

## §E Files I have ALSO checked and they're clean

- `web/components/app_shell.tsx` — provides the global nav; no change needed.
- `web/app/layout.tsx` — wraps every route in AppShell; no change needed.
- `web/components/nav_link.tsx` — active state styling; no change needed.
- `web/components/ui/button.tsx` — shadcn Button with focus-visible:ring; no change needed.
- Existing Playwright e2e suite has no home-route spec (only inspector, intake, etc).
- `state/polaris_ui_rebuild_matrix.md` — defines G1-G8 verbatim; this brief follows the spec.

## §F Smoke test

```bash
cd web
npx tsc --noEmit
npx eslint
npx prettier --check .
npx playwright test --project=chromium tests/e2e/home_g1_g8.spec.ts --list
```

## §G Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
