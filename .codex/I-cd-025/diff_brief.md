HARD ITERATION CAP: 5 per document. This is iter 2 of 5.

# Codex diff review — I-cd-025 (#615) — /runs/[runId] rebuild G1-G8

Canonical-diff-sha256: `cd7897e4d58661e96e4abafe52e10c713e93a671cfe5dc161239409b02ee3421`. Iter-1 fixes applied:

- **P0 G2**: replaced "F4 plan" / "Phase 1" / "Phase 2B" in user-visible copy + title attributes with neutral "Actions you can take while POLARIS works:" + "coming soon" tooltips.
- **P0 G4**: `getRun().catch(...)` now maps raw API errors to friendly run-page error states ("This run was not found..." / "We couldn't load this run...").
- **P1 spec**: G2 assertion now scans `[title]` + `[aria-label]` attributes in addition to body text.
- **P1 spec**: new G8 console-error test added (was missing from a G1-G8 labeled spec).

## §A Diff summary

- `web/app/runs/[runId]/page.tsx`: drop page-level `<header>` + `<footer>` + `<main>` + min-h-screen wrapper. Render `<section data-testid="runs-runid-page">` directly. Header buttons (Export bundle + New run) moved to a page-level right-aligned action row. G2 dev language ("POLARIS v6.2 — Phase 0 scaffold") removed via footer drop.
- `web/tests/e2e/runs_runid_g1_g8.spec.ts` NEW — G1+G6 (`toHaveCount(1)` on header + main), G2 (banned dev language), G1 nav-parity (8 primary links).
- `.github/workflows/web_ci.yml`: new `run_e2e_runs_runid_g1_g8` step.

## §B Notes

- Audit_live absorption: route remains for now (separate SSE pattern). Full absorption deferred — both routes functional. Future work item.
- `runs-runid-page` testid newly added; no existing spec depends on it.
- All existing run-status / SSE / cancel logic preserved.

## §C Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
