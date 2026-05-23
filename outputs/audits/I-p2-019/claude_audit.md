# Claude architect audit — I-p2-019 (#758): knowledge-graph page (the snowball)

## Scope
#758 = "Page: Knowledge-graph (the snowball)". The page
`web/app/runs/[runId]/graph/page.tsx` was already feature-complete from #751
(I-p2-012): cytoscape `ClaimGraph` + `AccessibleGraphList` (keyboard/SR a11y
fallback) + `GraphExportButtons` (PNG/JSON) + 2-hop snowball expansion + node
search + Open-Inspector deep-link. This PR is the **design-system + landmark +
honesty delta** only — NOT a rebuild. The interactive graph surface
(`GraphSurface`) is byte-for-byte unchanged.

## What changed (3 fixes, 3 files, 120-line diff)
1. **Chromeless (G1/G6)** — `web/components/app_shell_gate.tsx`. The page
   renders its own `<header>` (with "Back to Inspector") + `<main
   data-testid="graph-page">`. Pre-fix, `AppShellGate` wrapped it in
   `AppShell` → double `<header>` (G1) + nested `<main>` (G6). Added
   `CHROMELESS_PATTERNS = [/^\/runs\/[^/]+\/graph$/]` + an `isChromeless()`
   helper so the route owns its full viewport, exactly like `/` and `/sign-in`.
   Regex is anchored (`$`) so `/runs/<id>` and `/runs/<id>/graph/foo` are NOT
   caught — only the exact graph drill-down.
2. **G2 dev-language** — header `POLARIS — F-snowball` → `Knowledge graph` /
   `How this run's claims + sources connect`. "F-snowball" is an internal
   feature codename; never shown to a clinical/institutional user.
3. **#750 states + G4 raw-error leak** — `web/app/runs/[runId]/graph/page.tsx`.
   Hand-rolled error banner (`border-destructive text-destructive`) + spinner
   (no `motion-reduce`) → `ErrorState`/`LoadingState` (design tokens +
   role=alert/status + `motion-reduce:animate-none`). The `.catch` was
   `setError(e.message)` → leaked `getRunGraph(<id>) HTTP 500: Internal Server
   Error` to the user; now maps 404→not-found copy, else→generic retry copy,
   mirroring the existing `/runs/[runId]` G4 fix.

## Staled-consumer scan
- `grep` for `Failed to load graph` / `F-snowball` / `POLARIS — F`: the only
  staled assertion was `web/tests/e2e/graph_page_smoke.spec.ts:64`. Updated to
  assert the #750 ErrorState title + not-found message. (Codex iter-1 P1 — caught
  + fixed iter 2.)
- The other 4 tests in that spec assert `graph-page`/`claim-graph` testids +
  PNG/JSON export downloads — all unaffected by chromeless + relabel (the
  `data-testid="graph-page"` main still renders).
- `web/lib/api.ts:1270` has an "F-snowball" comment — code comment, not
  user-visible; left as-is.
- `web/components/states/state_kit.tsx` ErrorState(title,message)/
  LoadingState(label,rows) signatures match the call sites (cross-checked vs
  #755/#757 usage). The `GENERIC_MESSAGE` dev-warning regex does not match the
  new friendly copy ("couldn't load" ≠ "failed to load").

## Visual verification (standalone harness @1366, NOT next dev)
Rendered `/runs/demo-1/graph` in the standalone server (no v6 backend →
getRunGraph 500 → error path):
- Chromeless verified: `aria-label="Primary"` count = 0 (no global nav),
  `<header` count = 1 (own header only). No double-header, no nested-main.
- Header reads "KNOWLEDGE GRAPH / How this run's claims + sources connect" +
  "Back to Inspector". No dev-language.
- Error card is the #750 ErrorState (design-token red-tint border, role=alert):
  "Couldn't load the graph" + "We couldn't load the knowledge graph right now.
  Please retry shortly." No HTTP-code / fn-name leak.

## §-1.1 clinical-safety note
No claim/evidence rendering changed. The graph nodes/edges + accessible list
are driven by the same `GraphPayload` from the backend (`getRunGraph`); this PR
does not alter how any claim, citation, or verdict is displayed. No
faithfulness surface touched.

## Build / typecheck
`npm run typecheck` clean; `npm run build` Compiled successfully.

## Verdict
Codex combined DESIGN+DIFF review: **APPROVE at iter 2** (iter 1
REQUEST_CHANGES on the one staled test assertion, fixed), zero P0/P1,
MERGE AUTHORIZED. Diff 120 lines (under the 200-LOC cap).
