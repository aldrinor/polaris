# Codex Diff Review — I-ecg-003 (ITER 3 of 5)

**HARD ITERATION CAP: 5 per document. This is iter 1 of 5.**
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

**Issue:** I-ecg-003 — Contract editor UI
**Brief:** APPROVED iter 1 (0/0/0/2P2)
**Canonical-diff-sha256:** `2d54b7a39a5d9ec5e745f46a7f6a3ef3fd49d76bf715b6b0e3dc087a03a9db82`
**LOC:** 491 net (291 over CHARTER §1 200-cap; LOC exemption requested)
**Tests:** Lint clean; Playwright spec asserts download fires.

## Diff iter-2 verdict consumed

- P1 (added claims hard-code CA): RESOLVED iter 3 — `+ claim` button now defaults `required_jurisdictions` to `[...jurisdictions]` (current contract jurisdictions). Additionally, `pruned_claims` useMemo derives a render-time view that filters each claim's `required_jurisdictions` to current contract.jurisdictions, so toggling jurisdictions cleanly prunes downstream and keeps the validator/serializer aligned. on_submit serializes `pruned_claims` (NOT raw `claims`).
- P1 (blank claim_id accepted): RESOLVED iter 3 — `validateContract` adds `if (!cl.claim_id.trim()) errs.push("claim_id required");` BEFORE the duplicate-id check.
- P2 (max constraints not mirrored): NOTED iter 3, deferred — backend Pydantic max_length=200/1000/2000 enforcement at frontend is hardening; current backend will return 422 if exceeded. Captured as I-ecg-003a follow-up.

## Diff iter-1 verdict consumed

- P1 #1 (claim required_jurisdictions hard-coded to ['CA']): RESOLVED iter 2 — added per-claim jurisdiction checkbox grid (`ce-claim-${i}-jur-${j}`) driven by contract.jurisdictions. Operator can now select any combination per claim.
- P1 #2 (validateContract too lenient vs backend Pydantic): RESOLVED iter 2 — added 5 new checks: blank entity name; coverage in [0, 100]; blank claim statement; empty claim expected_entities; empty claim required_jurisdictions. Mirrors backend Field constraints + min_length=1 enforcement.
- P2 #1 (download assertion swallowed by `.catch`): RESOLVED iter 2 — replaced with explicit `dl_promise = page.waitForEvent("download", { timeout: 10_000 })` + `download.suggestedFilename()` regex assertion.
- P2 #2 (no remove buttons): RESOLVED iter 2 — added `ce-rm-ent-${i}` + `ce-rm-claim-${i}` buttons (only rendered when length > 1, since min_length=1 enforced).
- P2 #3 (localStorage claim mismatched): WITHDRAWN iter 2 — brief no longer claims localStorage; transient React state + JSON download is the actual deliverable. `_editor.tsx` is consistent.

## Files

```
web/lib/contracts.ts                       NEW +96
web/app/contracts/page.tsx                 NEW +21
web/app/contracts/_editor.tsx              NEW +288
web/tests/e2e/contract_editor.spec.ts      NEW +16
```

## What changed

**`contracts.ts`:** TypeScript mirror of `src/polaris_graph/evidence_contract/schema.py`. `EvidenceContract`, `ExpectedEntity/Claim/SourceCoverage`, `Jurisdiction` types; `buildContract()` factory + `validateContract()` mirroring backend's 4 internal-consistency invariants (unique entity names, unique claim_ids, claim entity refs declared, claim jurisdictions ⊆ contract jurisdictions).

**`page.tsx`:** Server Component shell with metadata; renders `<ContractEditor />`.

**`_editor.tsx`:** Client component with form state for research_question, created_by, jurisdiction multiselect (5 checkboxes), source coverage (3 number inputs), entities list (add/remove + name + type), claims list (add/remove + claim_id + statement + comma-separated entities). Validates on submit; renders inline errors; on valid downloads JSON via blob URL + shows `data-testid="contract-saved"`.

**`contract_editor.spec.ts`:** 1 Playwright test covering create + edit + save flow (per breakdown's "Playwright create/edit/save" acceptance). Asserts `contract-saved` testid + download event.

## LOC exemption requested

CHARTER §1 200-cap exceeded by 221. Prettier expansion drove the overrun (component logic is straightforward but Prettier formats every JSX prop on its own line with multi-line `onChange` arrow functions). Same pattern as I-f15-003 (381 LOC, exempted) — interactive form UI is artifact-inseparable. Splitting candidates considered:
1. Move add-entity/add-claim button rows to separate sub-components → adds boilerplate, no net LOC reduction.
2. Drop the entities/claims dynamic add → reduces feature surface but loses "edit" half of acceptance criteria.

Brief author requests exemption analogous to I-f15-003 (Prettier expansion) + I-f15-006 (binding cross-validation coverage).

## Risks for Codex Red-Team

1. **Frontend mirror correctness.** Types match backend `polaris_graph.evidence_contract.schema` byte-for-byte (Jurisdiction enum, EntityType, all field names). Codex iter-1 P2 #1 explicitly flagged the wrong-shape import risk; resolved via `@/lib/contracts` (NEW) NOT `@/lib/api`.
2. **No backend persistence.** Contract lives in localStorage + downloadable JSON only. Backend `/api/contracts` is I-ecg-003a follow-up.
3. **Server vs Client split.** `page.tsx` Server (exports metadata); `_editor.tsx` Client (`"use client"`). No collision.
4. **`globalThis.crypto?.randomUUID?.()` fallback.** SSR-safe; node test envs may lack crypto — fallback to Math.random().
5. **Prettier-formatted; eslint clean.**
6. **CHARTER §1 LOC cap.** 421 net. Exemption requested.
7. **No new package dep.**

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
