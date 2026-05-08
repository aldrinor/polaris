# Codex Diff Review — I-p2c-001 (ITER 1 of 5)

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Static review only — DO NOT spawn dev servers.

**Issue:** I-p2c-001 — Cross-feature integration testing F1→F5 chain
**Brief:** APPROVED iter 3 (after iter-1/iter-2 P1 fixes on testid contracts)
**Canonical-diff-sha256:** `efb29cb6fd2114a174f7a26919f3470a04dd9ed0d86f41b88b8ccbfe96e694ea`
**LOC:** 43 net (well under CHARTER §3 200-cap)

## Files

```
web/tests/e2e/p2c_001_chain.spec.ts   NEW +43  (single page-render-chain spec)
```

## What changed

### `p2c_001_chain.spec.ts`
- Single test walks F1→F5 fixture pages in sequence:
  - F1: `/intake` → `intake-form` + `intake-question-input`.
  - F2: `/disambiguation_modal_preview` → `disambiguation-cluster-0`.
  - F3: `/upload` → `upload-dropzone`.
  - F4: `/sse` → `sse-harness`.
  - F5: `/sentence_hover_test/evidence_tooltip` → `evidence-tooltip-harness` + `evidence-tooltip-trigger`.
- Asserts step-counter array matches `["F1", "F2", "F3", "F4", "F5"]` at the end.
- Spec docstring explicitly notes page-render integration, not backend pipeline.

## Verification

- `npx tsc --noEmit`: exit 0.
- `npx eslint tests/e2e/p2c_001_chain.spec.ts`: exit 0.
- `npx prettier --check`: exit 0.
- `npx playwright test p2c_001_chain.spec.ts --project chromium`: 1/1 passing in 2.4s.

## Risks for Codex Red-Team

1. **Honest framing:** spec docstring spells out "page-render navigation integration, NOT backend pipeline".
2. **Existing testid contracts:** spec uses real testids verified against current pages (per Codex iter-2 P1 fix that surfaced the wrong selectors in earlier iter).
3. **§9.4 N/A frontend.**
4. **CHARTER §3 LOC cap:** 43 net. Well under 200.

## Output schema (mandatory)

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
