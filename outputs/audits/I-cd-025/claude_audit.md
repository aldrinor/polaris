# Claude audit — I-cd-025 (#615)

## Scope landed

- web/app/runs/[runId]/page.tsx: dropped page-level `<header>`, `<footer>`, `<main>`, min-h-screen wrapper. Action buttons moved to right-aligned page-level div.
- G2 dev language stripped from copy + title attributes:
  - "POLARIS v6.2 — Phase 0 scaffold" (footer removal)
  - "5 things you can do while POLARIS works (F4 plan)" → "Actions you can take while POLARIS works"
  - "Phase 1: ask a follow-up..." → "Ask a follow-up scoped to this run's evidence (coming soon)"
  - "Phase 2B: pin this run..." → "Pin this run for later replay (coming soon)"
- G4: raw API errors mapped to friendly run-page copy ("This run was not found..." / "We couldn't load...").
- accessibility.spec.ts updated to assert new friendly 404 text.
- web/tests/e2e/runs_runid_g1_g8.spec.ts: G1+G6, G2 (body + titles + aria-labels), G1 nav parity, G8 console errors.
- web_ci.yml: new binding `run_e2e_runs_runid_g1_g8` step.
- BANNED_DEV_LANGUAGE regex now includes the exact strings just removed to catch reintroduction.

## Codex review trajectory

- Diff iter 1: REQUEST_CHANGES — P0 G2 leaks (F4 plan / Phase 1 / Phase 2B) + P0 G4 (raw API errors) + P1 spec gaps.
- Diff iter 2: REQUEST_CHANGES — novel P0 (accessibility.spec.ts breaks with new copy) + P1 regression-guard + P1 networkidle hang risk.
- Iter 2 fixes applied (accessibility.spec.ts updated; regression regex added; spec waits on domcontentloaded + 1.5s).

## Audit_live note

Per issue title "absorbs audit_live", the route remains functional in parallel. SSE patterns differ; full absorption into /runs/[runId] deferred until the rebuild matrix Consolidate disposition lands.

## Quality bar

- 4 files / +N LOC structural rebuild + G2 + G4 fixes.
- TS + lint clean.
- 5 existing run/SSE specs preserved (only accessibility.spec.ts assertion updated to new copy).
- AppShellGate from I-cd-022 provides correct global header.
