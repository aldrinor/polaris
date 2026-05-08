# Codex Brief Review — I-p2c-001 (ITER 3 of 5)

## Iter 3 changes per Codex iter 2

- Replace `intake-input` with `intake-question-input` (existing testid in `intake_form.tsx:122`).

## Iter 2 changes per Codex iter 1

- **P1 fix (existing testid contracts):** revised step assertions to match real testids:
  - F1 `/intake`: assert `intake-form` and `intake-question-input` render. Don't try to assert `scope-decision-view` (that requires submit + backend response).
  - F2 `/disambiguation_modal_preview`: assert presence of disambiguation cluster cards via `disambiguation-cluster-*` testid (using `getByTestId('disambiguation-cluster-0')` or first-match).
  - F3 `/upload`: assert `upload-dropzone` renders.
  - F4 `/sse`: assert `sse-harness` renders.
  - F5 `/sentence_hover_test/evidence_tooltip`: assert `evidence-tooltip-harness` and `evidence-tooltip-trigger` render. Don't assert popup (would require hover+debounce).
- **P2 fix:** drop "handoff state survives" claim — this is a navigation-render integration only.

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Pre-flight

- **Issue:** I-p2c-001 — Cross-feature integration testing F1→F2→F3→F4→F5 chain. Acceptance: integration suite green. LOC estimate 180.
- **Substrate today:** each F has its own page + e2e spec (intake/disambiguation, upload, sse_run, inspector). No single test exercises the whole chain.
- **Honest framing per CLAUDE.md §9.4:** ship a Playwright integration spec that NAVIGATES through each F-page in sequence and asserts each page renders + (where applicable) handoff state survives. This is a navigation-and-render integration, not a backend pipeline integration — production end-to-end smoke is still M-LIVE-1 territory. Document explicitly.

## Plan

### `web/tests/e2e/p2c_001_chain.spec.ts` (NEW)

1. F1 step: visit `/intake` → assert `intake-form` + `intake-question-input` render.
2. F2 step: visit `/disambiguation_modal_preview` → assert first `disambiguation-cluster-*` testid renders.
3. F3 step: visit `/upload` → assert `upload-dropzone` renders.
4. F4 step: visit `/sse` → assert `sse-harness` renders.
5. F5 step: visit `/sentence_hover_test/evidence_tooltip` → assert `evidence-tooltip-harness` + `evidence-tooltip-trigger` render.
6. Final: assert all 5 step-counter increments completed (test-local sanity).

### Out of scope

- Backend chain — production end-to-end intake → disambiguation → upload → run → inspector is M-LIVE-1.
- Deep assertions per page (each F already has its own e2e spec).

## Risks for Codex Red-Team

1. **Honest framing:** this is page-render-chain integration, not backend-flow integration. Banner-level honesty in the spec docstring.
2. **Existing page contracts:** spec relies on existing testids — any contract drift in F-pages will surface here, which is the point.
3. **§9.4 N/A frontend.**
4. **CHARTER §3 LOC cap:** estimated ~120 LOC spec. Comfortable under 200.

## Acceptance criteria

1. New `web/tests/e2e/p2c_001_chain.spec.ts` walks F1→F5 page renders.
2. Spec asserts each step's primary testid is visible.
3. CHARTER §3 LOC cap respected (≤200 net).
4. Spec docstring explicitly notes page-render integration, not backend.

**Forced enumeration:** before verdict, write one line per criterion 1-4.
**Completeness check:** list files actually read.

## Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

APPROVE iff zero NOVEL P0 + zero continuing P0 + zero P1.
