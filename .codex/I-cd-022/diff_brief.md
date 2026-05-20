HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1.
- "Don't pick bone from egg" — P1 only for real execution risks.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# Codex diff review — I-cd-022 (#612) — / (home) rebuild G1-G8

Brief APPROVE'd at iter 2 (plan v3 with AppShellGate suppressing BOTH header AND main on `/`). Canonical-diff-sha256: `178a73af757e23247ef0dda2dc53a048226dc154c057e9a02602cfb6c113bb1f`. 6 files / +159/-13 LOC.

## §A Canonical diff summary

- `web/components/app_shell_gate.tsx` NEW (25 LOC) — pathname-aware `"use client"` wrapper. On `/` returns `<>{children}</>` (bare); on any other path wraps in `<AppShell>`.
- `web/app/layout.tsx` MOD (2 LOC) — swap AppShell → AppShellGate.
- `web/app/components/home_keyboard_shell.tsx` MOD (+28 LOC net) — moved `PRIMARY_NAV` constant + `NavLink` rendering INTO the home header so the home route's nav is identical to AppShell's. Brand cell reformatted to match AppShell's "POLARIS · Canada" font-mono style. `header-sign-in-link` testid + `signInLinkRef` PRESERVED (5 existing specs depend on them).
- `web/app/page.tsx` MOD (3 LOC) — G2 strings: "slices 1-5 shipped" → "Sovereign Canadian deep research"; "7 to-build" → "7 in development".
- `web/tests/e2e/home_g1_g8.spec.ts` NEW (90 LOC) — 5 tests covering G1 (single header outside main + primary nav present), G2 (no banned dev language), G3 (active link has focus-visible), G6 (single main + keyboard tab reaches active link), G8 (zero console errors).
- `.github/workflows/web_ci.yml` MOD (+8 LOC) — new `run_e2e_home_g1_g8` step wires the spec into the binding CI gate.

## §B Acceptance check (G1-G8 per state/polaris_ui_rebuild_matrix.md §2)

| Gate | Met by |
|---|---|
| G1 — single global header w/ primary nav on `/` | AppShellGate suppresses AppShell on `/`; HomeKeyboardShell header now hosts PRIMARY_NAV with all 8 entries identical to AppShell |
| G2 — no dev language | page.tsx string edits; spec asserts `/slice|scaffold|placeholder|phase 0|post-carney|i-cd-/i` not in body |
| G3 — interactive states | shadcn Button + Link with `focus-visible:ring-*`; spec asserts active link has `focus-visible` class |
| G4 — async states | N/A (home is static) |
| G5 — responsive 1440 + 1024 | existing `md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4` |
| G6 — a11y + single main | spec asserts `<main>` count==1 + Tab reaches active link |
| G7 — design tokens | existing `bg-background`, `text-foreground`, `border-border`, etc. |
| G8 — console clean | spec captures console errors via `page.on("console")` + asserts empty |
| header-sign-in-link / signInLinkRef preserved (5 existing specs back-compat) | home_keyboard_shell.tsx:55-58 + line 75 ref pass |
| CI gate runs the spec | web_ci.yml new step |

## §C Red-team checklist

1. **AppShellGate is "use client"** — uses `usePathname()` which requires a Client Component. Children rendered through it remain server-rendered where they were before; only the gate itself is client-side. No SSR regression.
2. **No double-render on `/`** — AppShellGate returns `<>{children}</>` on `/`, so children are NOT wrapped in any extra element. The home `<header>` from HomeKeyboardShell is the page's only `<header>`.
3. **All other routes** — AppShellGate falls through to `<AppShell>`, preserving the current behavior (header + main).
4. **PRIMARY_NAV duplication** — the constant is defined in BOTH `web/components/app_shell.tsx` AND `web/app/components/home_keyboard_shell.tsx`. Pragmatic for back-compat with shadcn import paths and pre-existing tests; if reconciliation is wanted, factor into a shared constant in a future PR. Not a blocker for G1.
5. **header-sign-in-link** — exact testid preserved per Codex iter-1 P1.
6. **signInLinkRef** — preserved as a ref attached to the Sign In link. CommandPalette still receives it.
7. **Cmd+K keyboard shortcut** — preserved in `useEffect` block.
8. **No nested landmarks** — verified: page has exactly 1 `<header>` (from HomeKeyboardShell) + exactly 1 `<main>` (from page.tsx). AppShell is bypassed on `/`.
9. **Existing specs that depend on the home structure** — `command_palette*.spec.ts` + `f1_*.spec.ts` use `data-testid="header-sign-in-link"` which is preserved.

## §D Files I have ALSO checked and they're clean

- `web/components/app_shell.tsx` — unchanged, still wraps non-home routes.
- `web/components/nav_link.tsx` — `NavLink` component used in both AppShell and HomeKeyboardShell.
- `web/app/components/command_palette.tsx` — unchanged; receives signInLinkRef.
- `web/tests/e2e/command_palette*.spec.ts` + `f1_*.spec.ts` — depend on `header-sign-in-link`; preserved.

## §E Smoke test

```bash
cd web
npx tsc --noEmit   # rc=0
npx eslint         # no new errors (verified)
npx prettier --check .   # all formatted
```

Playwright e2e requires running `next start`; runs as binding gate in CI workflow.

## §F Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
