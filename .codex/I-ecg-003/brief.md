# Codex Brief Review — I-ecg-003 (ITER 1 of 5)

**HARD ITERATION CAP: 5 per document. This is iter 1 of 5.**
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

**Issue:** I-ecg-003 — Contract editor UI
**Phase:** 1 / **Feature:** ECG
**LOC budget:** 200 net per breakdown. **CHARTER §1 hard cap: 200.**

## Mission

Per breakdown: `web/app/contracts/page.tsx` — Playwright create/edit/save.

## Substrate (HONEST at HEAD)

- I-ecg-001 + I-ecg-002 ship the backend contract schema + gate.
- No frontend contract substrate at HEAD; no `web/app/contracts/`.
- `web/lib/api.ts` has the v6 EvidenceContract patterns (download bundle, generation, etc.) — same shape conventions to reuse.
- No backend `/api/contracts` route exists; this Issue scopes to PURE FRONTEND. The form serializes the contract to localStorage (or downloads JSON) — no backend persistence. Backend persistence is I-ecg-003a follow-up.

## Approach

**Part 1 — `web/lib/contracts.ts`** (NEW, ~50 LOC):
- TypeScript interfaces mirroring backend `EvidenceContract`: `Jurisdiction` enum, `ExpectedEntity`, `ExpectedClaim`, `ExpectedSourceCoverage`, `EvidenceContract`.
- `buildContract(form: ContractFormState) -> EvidenceContract` — composes from form state with uuid + timestamp.
- `validateContract(contract): string[]` — minimal cross-validation mirroring backend's `_internal_consistency` (unique entity names + claim ids + claim entity refs + claim jurisdictions ⊆ contract jurisdictions).

**Part 2 — `web/app/contracts/page.tsx`** (NEW, ~30 LOC):
- Server Component shell with metadata + nav header. Slots in the Client editor.

**Part 3 — `web/app/contracts/_editor.tsx`** (NEW, ~110 LOC):
- Client component (`"use client"`).
- Form state: research_question, created_by, jurisdictions (multiselect), entities (add/remove), claims (add/remove), source_coverage (3 number inputs).
- Validate on submit; render errors inline.
- On valid: download JSON via blob URL + show `data-testid="contract-saved"` confirmation.

**Part 4 — `web/tests/e2e/contract_editor.spec.ts`** (NEW, ~10 LOC):
- 1 test: navigate `/contracts`, fill min fields, submit, assert `contract-saved` appears.

## Acceptance criteria (binding)

1. `web/lib/contracts.ts` NEW — types + builder + validator.
2. `web/app/contracts/page.tsx` NEW — Server Component shell.
3. `web/app/contracts/_editor.tsx` NEW — Client form.
4. `web/tests/e2e/contract_editor.spec.ts` NEW — Playwright create/edit/save flow.

## Planned diff shape

```
web/lib/contracts.ts                       NEW +50
web/app/contracts/page.tsx                 NEW +30
web/app/contracts/_editor.tsx              NEW +110
web/tests/e2e/contract_editor.spec.ts      NEW +10
```

LOC: +200 net. AT CHARTER §1 200-cap. Brief author commits to inline minification (no Prettier-expansion overrun) per I-f15-003 lessons.

## Out of scope

- Backend `/api/contracts` POST/GET persistence → I-ecg-003a follow-up.
- Contract version migration UI → I-ecg-004.
- Server-side validation roundtrip → relies on existing Pydantic at `/api/generation` when contract is sent there.
- Multi-jurisdiction multiselect with checkbox-grid UX → simple comma-separated input v1.

## Risks for Codex Red-Team

1. **No backend persistence.** Operator's contract lives in localStorage + downloadable JSON. Re-uploading from JSON is post-Sep-6.
2. **Server vs Client component split.** `page.tsx` is Server (no useState/useEffect, can export `metadata`); `_editor.tsx` is Client. Same pattern as `web/app/intake/page.tsx` + `_client.tsx`.
3. **Playwright e2e via dev server only.** No mock route fulfillment needed — local-only flow.
4. **Prettier expansion risk.** Brief author commits to running `npx prettier --write` post-impl + verifying LOC stays under 200.
5. **§9.4 N/A** (frontend code).
6. **CHARTER §1 LOC cap.** 200 net. AT cap; trim if Prettier expands.
7. **No new package.json dep.**

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
