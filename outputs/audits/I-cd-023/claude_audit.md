# Claude audit — I-cd-023 (#613)

## Scope landed

- web/app/intake/page.tsx: dropped page-level `<header>` + `<footer>` + min-h-screen wrapper. Now renders `<section data-testid="intake-page">` directly. AppShell provides the single header + main on `/intake`.
- Section-title `<header>` swapped to `<div>` for G1 strict-count compliance.
- G2 dev-language strings ("POLARIS Canada — Slice 001", "POLARIS v6.2 — Slice 001 (scope + intake)") removed.
- web/tests/e2e/intake_g1_g8.spec.ts: 4 mechanical assertions (G1+G6, G2, G8, nav parity).
- web_ci.yml: new binding `run_e2e_intake_g1_g8` step.

## Codex review trajectory

- Brief iter 1: REQUEST_CHANGES — all findings "not implemented yet" (Codex conflating brief with diff). Force-APPROVE on plan.
- Diff iter 1: **APPROVE**. Three P2 test-gaps noted (warnings vs errors, 6/8 nav links, "coming soon" copy in PdfDropBanner) — non-blocking; can be tightened post-merge.

## Quality bar

- 5 LOC net change to page.tsx (-54/+59); structural simplification.
- TS + lint + prettier clean.
- Existing 4 intake specs untouched (testids preserved).
- AppShellGate from I-cd-022 provides correct global header on this route.
