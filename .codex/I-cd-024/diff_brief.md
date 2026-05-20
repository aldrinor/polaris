HARD ITERATION CAP: 5 per document. This is iter 1 of 5.

# Codex diff review — I-cd-024 (#614) — /dashboard rebuild G1-G8

Canonical-diff-sha256: `d4a6d0f5884b3d3cea5da6574a8bf302393d69630fd2bcc31365562aa81e39be`. 3 files / +382/-333 LOC (most of dashboard/page.tsx delta is prettier indent collapse from removing outer `<div>` wrapper; structural change is ~25 LOC).

## §A Canonical diff summary

- `web/app/dashboard/page.tsx` — drop page-level `<header>` + `<footer>` + min-h-screen `<div>` wrapper + `<main>`. Page now renders `<section data-testid="dashboard-page">` directly. AppShell provides the single header + main on `/dashboard`.
- `web/tests/e2e/dashboard_g1_g8.spec.ts` NEW — G1 + G6 (`toHaveCount(1)` on `<header>` and `<main>`), G2 (banned dev language regex), G1 nav parity (8 primary links), G8 (zero console errors).
- `.github/workflows/web_ci.yml` — `run_e2e_dashboard_g1_g8` step wires the spec as binding CI gate.

## §B Acceptance check

| Gate | Met by |
|---|---|
| G1 — single header (AppShell-only) + nav parity | page header dropped; spec asserts |
| G2 — no dev language | "POLARIS v6.2 — Phase 0 scaffold" removed; spec regex-asserts |
| G3 — interactive states | existing template radio buttons + form controls preserved |
| G4 — async states | existing scopeChecking + ambiguity + uploads loading flows |
| G5 — responsive | existing max-w-4xl preserved |
| G6 — single main | `<main>` swap for `<section>`; spec asserts |
| G7 — design tokens | preserved |
| G8 — console clean | spec asserts |

## §C Red-team checklist

1. **All existing form state** (template radios, question input, scope-check, ambiguity, uploads, disambiguation modal, submit) — preserved exactly.
2. **`dashboard-page` testid** — newly added on the `<section>`; no existing dashboard spec exists to break.
3. **All onChange handlers, useEffect, useRef** — preserved as-is.
4. **Form submission flow** — preserved.
5. **No new dependencies**.
6. **TypeScript clean** confirmed.

## §D Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
