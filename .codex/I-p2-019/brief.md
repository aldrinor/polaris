# Codex DESIGN+DIFF review — I-p2-019 (#758): knowledge-graph page (the snowball)

HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

Canonical-diff-sha256 `dd13cabc97ebcb4a5cfb71fbfa6950f54a93f1d0d329071fe0c8b9589e08e660`. web/ only, 120-line diff (under 200-LOC cap). MERGE AUTHORIZED if mergeable. APPROVE iff zero P0/P1.

## iter-1 → iter-2 delta (your iter-1 P1, fixed)
You flagged: `web/tests/e2e/graph_page_smoke.spec.ts:64` still asserted the removed copy "Failed to load graph". **Fixed** — that 404→error test now asserts the #750 ErrorState title "Couldn't load the graph" + the friendly not-found message "This run was not found". Verified by grep that this was the ONLY staled assertion (the other 4 tests assert `graph-page`/`claim-graph` testids + export downloads, all unaffected by chromeless + relabel). The test file is now part of the canonical diff (hence the new hash + 120 lines).

## Context
#758 = "Page: Knowledge-graph (the snowball)". The page `web/app/runs/[runId]/graph/page.tsx` was ALREADY feature-complete from #751 (I-p2-012): cytoscape ClaimGraph + AccessibleGraphList (a11y fallback) + GraphExportButtons (PNG/JSON) + 2-hop snowball expansion + node search + Open-Inspector deep-link. This PR is the design-system + landmark + honesty delta only — NOT a rebuild.

## Diff (2 files)
1. `web/components/app_shell_gate.tsx`: added `CHROMELESS_PATTERNS = [/^\/runs\/[^/]+\/graph$/]` + `isChromeless()` helper. The graph page renders its OWN `<header>` (with "Back to Inspector") + `<main data-testid="graph-page">`. Before this, AppShellGate wrapped it in AppShell → **G1 double-header + G6 nested-main**. Now the route is chromeless and owns its full viewport, exactly like `/` and `/sign-in`.
2. `web/app/runs/[runId]/graph/page.tsx`:
   - **G2**: header dev-language `POLARIS — F-snowball` → `Knowledge graph` / `How this run's claims + sources connect`.
   - **#750 swap**: hand-rolled error banner (`border-destructive text-destructive`) + hand-rolled spinner (no motion-reduce) → `ErrorState` + `LoadingState` from the #750 kit (design tokens + role=alert/status + motion-reduce honored).
   - **G4 (raw-error leak)**: `.catch` was `setError(e.message)` → leaked `getRunGraph(demo-1) HTTP 500: Internal Server Error` to the user. Now maps to friendly copy ("This run was not found…" / "We couldn't load the knowledge graph right now…"), mirroring the existing `/runs/[runId]` G4 fix.

## Files I have ALSO checked and they're clean
- `web/app/runs/[runId]/graph/components/{claim_graph,accessible_graph_list,graph_export_buttons,snowball,use_graph_state}.tsx` — unchanged; the page only re-labels its header + swaps error/loading. GraphSurface (the actual graph UI) is untouched.
- `web/components/states/state_kit.tsx` — ErrorState(title,message)/LoadingState(label,rows) signatures match the call sites (verified against #755/#757 usage).
- `web/components/app_shell.tsx` — unchanged; AppShellGate is the only gate, single landmark provider for non-chromeless routes.
- Chromeless regex tested against `/runs/demo-1/graph` (matches) and `/runs/demo-1` (does NOT match — the run-detail page stays inside AppShell, correct).

## Claude visual audit (standalone harness @1366, NOT next dev)
Rendered `/runs/demo-1/graph` in the standalone server (no v6 backend → getRunGraph 500 → error path):
- Chromeless verified: `grep -c 'aria-label="Primary"'` = 0 (no global nav), `<header` count = 1 (own header only). No double-header, no nested-main.
- Header reads "KNOWLEDGE GRAPH / How this run's claims + sources connect" + "Back to Inspector" button. No dev-language.
- Error path shows the #750 ErrorState card: "Couldn't load the graph" + friendly "We couldn't load the knowledge graph right now. Please retry shortly." (no HTTP 500 / fn-name leak). Design-token red-tint bordered card, role=alert.

## Review focus
1. Is the chromeless regex correct + scoped (only `/runs/<id>/graph`, not `/runs/<id>` or `/runs/<id>/graph/foo`)? Any route that should NOT be chromeless now caught?
2. ErrorState/LoadingState swaps clean (no unused imports, props match)?
3. G4 error mapping honest (404→not-found, else→generic-retry; no swallowed error)?
4. Any P0/P1 (landmark regression, a11y regression, behavior change to GraphSurface).

## Output schema
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
merge_decision: MERGE AUTHORIZED | DO NOT MERGE
```
