# Claude Architect Audit — I-f2-005 (F2 BPEI end-to-end)

**Branch:** bot/I-f2-005 / **Diff SHA256:** `694fabdda24b738ba88532532bff95a98e187c9b354d4db422b4e667f6387003`
**LOC:** 155 net insertions / 23 deletions (well under CHARTER §1 200-cap)
**Type-check:** `npx tsc --noEmit` clean.
**Format:** `npx prettier --check` clean.

## Files

```
web/lib/api.ts                                                       EDIT  +35 / -0
web/app/intake/components/disambiguation_modal.tsx                   EDIT  +1 / -5
web/app/(test_harness)/disambiguation_modal_preview/_client.tsx      EDIT  +2 / -4
web/app/intake/components/intake_form.tsx                            EDIT  +37 / -0
web/tests/e2e/intake_disambiguation.spec.ts                          NEW   +84
```

## Iter-2 brief P2 advisory — addressed in implementation

- **P2 (open disambiguation modal only when `is_ambiguous && clusters.length > 1`):** ADDRESSED. `intake_form.tsx:67-71`: `if (dis.is_ambiguous && dis.clusters.length > 1) { ... }`. Empty/unambiguous responses do not surface a modal.

## Architecture review

1. **Trigger-condition design (Option A locked).** Intake response carries `needs_disambiguation?` + `candidate_snippets?`. Frontend reads. Backend writer is the named follow-up: `I-f2-005a — Backend: populate `needs_disambiguation` + `candidate_snippets` in intake response`.

2. **`DisambiguationCluster` ownership move.** `web/lib/api.ts` now owns the type. Modal + harness import from `@/lib/api`. No type duplication.

3. **`runDisambiguation()` request body shape (Codex iter-1 P1 fix).** `JSON.stringify({ candidates })` matches FastAPI `DisambiguationRequest.candidates`. Bare-array regression caught by Playwright assertion `expect(body.candidates).toHaveLength(3)`.

4. **Origin-safe Playwright glob patterns (Codex iter-1 P2 #1 fix).** `**/api/intake` and `**/api/disambiguation` cover both `BACKEND_URL=http://127.0.0.1:8000` and Next baseURL `:3738`.

5. **Realistic mock latency (advisor recommendation #3).** `await new Promise(resolve => setTimeout(resolve, 100))` introduces a deterministic delay before fulfill, making the `<500ms` assertion meaningful (vacuous-pass guard).

6. **Toothless-pattern guard (advisor recommendation #4).** Test asserts `disambig-picked-label === "institute"` after click on cluster_id=1, proving state flowed from modal → parent component (not just modal-local handler).

7. **Cancel idempotency preserved.** Modal's `is_cancelled_ref` (from I-f2-004) still in effect. Test does not re-cover it (covered by I-f2-004 tests).

8. **Modal trigger condition (Codex iter-2 P2 fix).** Three guards: `is_ambiguous=true`, `clusters.length > 1`, AND `needs_disambiguation=true` from intake. No empty-modal regression.

## LAW + invariant checks

- **LAW II:** No silent fallbacks. Empty cluster response → modal does not open. ✓
- **LAW V:** snake_case file names; PascalCase exports for types/functions. ✓
- **LAW VI:** Config from `BACKEND_URL` env (existing pattern). ✓
- **§9.4:** No `unittest.mock`; FakeClient harness pattern reused. ✓
- **§8.4:** No real LLM/network call in tests; route mocks. ✓
- **CHARTER §1 200-cap:** 155 net insertions; well under. ✓

## Test plan coverage

Single Playwright e2e test covering:
- Mock /api/intake + /api/disambiguation via origin-safe globs.
- Type "BPEI" → submit.
- Latency `t_modal - t_submit < 500ms` (with realistic 100ms backend delay).
- Exact 3-card count assertion.
- Click cluster_id=1 → assert `disambig-picked-label === "institute"`.
- Modal closes after pick.
- Mock asserts request body shape `{ candidates: [...] }` with length 3.

## Out of scope (deferred)

- **Backend writer for `needs_disambiguation` + `candidate_snippets`** → `I-f2-005a` follow-up Issue.
- BPEI 3-cluster real-LLM smoke → I-f2-006 / I-f2-007 / I-f2-008 evaluator walkthrough.
- Server-side performance budget for real `/api/disambiguation` calls → I-f2-008.

## Verdict

APPROVE for Codex diff review.
