HARD ITERATION CAP: 5 per document. This is iter 1 of 5.

# Codex brief — I-cd-024 (#614) — /dashboard rebuild G1-G8

Same structural pattern as I-cd-022 (home) + I-cd-023 (intake):
- Drop page-level `<header>` + `<footer>` + `<main>` (AppShellGate from I-cd-022 provides them).
- Strip G2 dev language ("POLARIS v6.2 — Phase 0 scaffold" footer).
- Swap nested `<main>` for `<section data-testid="dashboard-page">`.
- New `dashboard_g1_g8.spec.ts` — G1 + G6 (single header/main), G2 (no dev language), G1 nav parity (8 primary links), G8 (no console errors).
- Wire spec into `web_ci.yml`.

Estimated diff: ~100 LOC net (the 650-line stat is prettier reformatting from indent collapse).
