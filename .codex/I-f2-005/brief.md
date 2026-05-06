# Codex Brief Review — I-f2-005 (ITER 2 of 5)

**HARD ITERATION CAP: 5 per document. This is iter 2 of 5.**
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

**Issue:** I-f2-005 — F2 functional test: BPEI end-to-end
**Phase:** 1 / **Feature:** F2 (disambiguation modal)
**LOC budget:** 100 net per breakdown. **CHARTER §1 hard cap: 200.**

## Iter-1 verdict resolution (REQUEST_CHANGES → addressed in this iter 2)

**P1 (request body shape `{candidates: [...]}` vs bare array):** ADDRESSED. `runDisambiguation()` POSTs `JSON.stringify({ candidates })` matching FastAPI `DisambiguationRequest.candidates`. Playwright mock asserts the request body shape via `route.request().postData()` so a regression caught here.

**P2 #1 (Playwright route patterns must be origin-safe):** ADDRESSED. Routes use `**/api/intake` and `**/api/disambiguation` glob patterns covering both `BACKEND_URL` and Next baseURL origins.

**P2 #2 (singleton-embedding fixture wouldn't produce real 3 clusters):** ADDRESSED. Brief now explicitly notes the fixture is frontend-only mocked and does NOT imply real clusterer behavior on those embeddings.

## Mission

Wire the F2 disambiguation flow end-to-end through the intake page and ship a Playwright functional test asserting `type → submit → modal → 3 candidates → pick → query proceeds`. Ship `runDisambiguation()` API client. Backend writer that *populates* the disambiguation trigger field is explicitly DEFERRED to a named follow-up Issue (`I-f2-005a — Backend: populate `needs_disambiguation` + `candidate_snippets` in intake response`).

## Trigger-condition design (architectural call, locked here)

Three options considered:
- (A) **Selected**: intake response gains `needs_disambiguation: bool` + `candidate_snippets: CandidateSnippet[]` (parallel arrays of text + embedding). Frontend reads, calls `/api/disambiguation`. Backend writer is a follow-up Issue.
- (B) Frontend always fires `/api/disambiguation`. **Rejected** — wasteful and still needs candidate sources.
- (C) Test-only trigger via query param / magic keyword. **Rejected** — pollutes production code for test convenience.

Option (A) is cleanest separation: this Issue ships the frontend reader; `I-f2-005a` ships the backend writer.

## Substrate (HONEST)

- I-f2-002, I-f2-003, I-f2-004 merged: `cluster_candidates`, `label_clusters`, `/api/disambiguation`, `DisambiguationModal` component.
- `web/app/intake/components/intake_form.tsx:32-55`: existing intake submit handler with modal-firing pattern (PICO ambiguity modal already plumbed). Easy to extend with a second modal-firing path.
- `web/lib/api.ts:357-368`: existing `IntakeScopeDecision` type. Adding two optional fields is non-breaking.
- `DisambiguationCluster` currently lives in `web/app/intake/components/disambiguation_modal.tsx` as a local export. Moving to `web/lib/api.ts` centralizes the type and avoids cross-module type duplication.

## Acceptance criteria (binding)

1. **`web/lib/api.ts`** (EDIT):
   - Add to `IntakeScopeDecision`:
     ```ts
     // Optional F2 disambiguation trigger fields. Populated by I-f2-005a backend writer.
     needs_disambiguation?: boolean;
     candidate_snippets?: { text: string; embedding: number[] }[];
     ```
   - Add new exports:
     ```ts
     export type DisambiguationCluster = {
       cluster_id: number;
       label: string;
       sample_snippets: string[];
     };

     export interface DisambiguationResponse {
       is_ambiguous: boolean;
       num_clusters: number;
       clusters: DisambiguationCluster[];
       server_time_utc: string;
     }

     export async function runDisambiguation(
       candidates: { text: string; embedding: number[] }[],
     ): Promise<DisambiguationResponse> { ... }
     ```
     - Mirrors `runIntake()` shape (same fetch + error handling).
     - POSTs to `/api/disambiguation` with body `JSON.stringify({ candidates })` — the FastAPI route binds `DisambiguationRequest.candidates`, so a bare-array payload would 422. (Codex iter-1 P1 fix.)
     - On 503/400, throws an Error with the parsed `code`.
   - LOC: ~30 pre-Prettier.

2. **`web/app/intake/components/disambiguation_modal.tsx`** (EDIT, 2-line refactor): drop local `DisambiguationCluster` export; import from `@/lib/api`. The component is functionally unchanged.
   - LOC: -3 / +2 (net -1).

3. **`web/app/(test_harness)/disambiguation_modal_preview/_client.tsx`** (EDIT, 1-line refactor): import `DisambiguationCluster` from `@/lib/api` instead of the modal file.
   - LOC: +0 (1-line change, replace import path).

4. **`web/app/intake/components/intake_form.tsx`** (EDIT):
   - State extension: `[disambigClusters, setDisambigClusters] = useState<DisambiguationCluster[]>([])`, `[disambigOpen, setDisambigOpen] = useState(false)`, `[pickedClusterLabel, setPickedClusterLabel] = useState<string | null>(null)`.
   - After `runIntake()`'s success branch, if `result.decision.needs_disambiguation && result.decision.candidate_snippets`, fire `runDisambiguation(result.decision.candidate_snippets)` → on success, `setDisambigClusters(...)` + `setDisambigOpen(true)`.
   - Add `<DisambiguationModal>` mount at component bottom: `open={disambigOpen}`, `clusters={disambigClusters}`, `onSelectCluster={(cid) => { setPickedClusterLabel(disambigClusters.find(c => c.cluster_id === cid)?.label ?? null); setDisambigOpen(false); }}`, `onCancel={() => setDisambigOpen(false)}`.
   - Add `<output data-testid="disambig-picked-label">` showing `pickedClusterLabel ?? ""` so Playwright can assert post-pick state (NOT just last-clicked-id; this proves state actually flowed to the parent).
   - LOC: ~25 pre-Prettier.

5. **`web/tests/e2e/intake_disambiguation.spec.ts`** (NEW): one Playwright test, hermetic via `page.route()` mocks.
   - **Route patterns**: use `**/api/intake` and `**/api/disambiguation` glob patterns (Codex iter-1 P2 #1 fix). The frontend client's actual fetch target may be `BACKEND_URL=http://127.0.0.1:8000` rather than the Next baseURL `:3738`; bare `/api/...` route patterns would miss off-origin requests. Glob `**/...` matches both.
   - **Mock /api/intake**: returns 200 with `decision.status="in_scope"`, `decision.needs_disambiguation=true`, `decision.candidate_snippets=[3 short snippets with [1,0]/[0,1]/[-1,0] embeddings]`. (Frontend-only mocked fixture — does NOT imply real clusterer would emit 3 clusters from these singleton embeddings; per Codex iter-1 P2 #2.)
   - **Mock /api/disambiguation**: ASSERTS request body shape: `const body = JSON.parse(route.request().postData() ?? "{}"); expect(body.candidates).toHaveLength(3);`. Then introduces a realistic 100ms delay via `setTimeout` before `route.fulfill()`, then returns 200 with `is_ambiguous=true, num_clusters=3, clusters=[{cluster_id:0, label:"syndrome", sample_snippets:["BPEI..."]}, {1, label:"institute", ...}, {2, label:"chemical", ...}]`.
   - Test steps:
     1. `goto /intake`.
     2. Fill `intake-question-input` with "BPEI".
     3. Click `intake-submit`. Capture `t_submit = Date.now()`.
     4. Wait for `disambiguation-cluster-0` visible. Capture `t_modal = Date.now()`.
     5. Assert exactly 3 cluster cards via `[data-testid^="disambiguation-cluster-"]` `toHaveCount(3)`.
     6. Assert `t_modal - t_submit < 500` (acceptance latency requirement).
     7. Click `disambiguation-cluster-1`.
     8. Assert `disambig-picked-label` text equals `"institute"` (proves state flowed to parent — toothless-pattern guard per Codex iter-2 P2 of I-f2-004).
     9. Assert the modal closes (`disambiguation-cluster-0` no longer visible).
   - LOC: ~75 pre-Prettier.

## Planned diff shape

```
web/lib/api.ts                                                NET +30
web/app/intake/components/disambiguation_modal.tsx            NET -1
web/app/(test_harness)/disambiguation_modal_preview/_client.tsx NET +0
web/app/intake/components/intake_form.tsx                     NET +25
web/tests/e2e/intake_disambiguation.spec.ts                   NEW +70
```

LOC: +124 net pre-Prettier. Prettier reflow target: ≤200 (CHARTER §1 hard cap). Pre-budget headroom: 76 lines.

## Out of scope (deferred)

- **Backend writer** for `needs_disambiguation` + `candidate_snippets` in intake response → **`I-f2-005a` follow-up Issue** (the named blocker per advisor #1).
- BPEI 3-cluster real-LLM smoke (beyond mock) → I-f2-006/007/008 evaluator walkthrough.
- Server-side performance budget for the actual `/api/disambiguation` call under real load → out of scope; covered by I-f2-008 evaluator timing.

## Risks for Codex Red-Team

1. **Trigger-condition design (architectural).** Option A locked: intake response carries `needs_disambiguation` flag + `candidate_snippets`. Frontend reads. Backend writer is the named follow-up Issue. Codex should NOT block this PR on backend-writer absence; it should verify the type contract is sound.

2. **`DisambiguationCluster` ownership move.** Currently in modal file. This Issue moves it to `web/lib/api.ts`. Modal + harness import the new path. Type contract identical; only import paths shift.

3. **Realistic mock latency (advisor #3).** Mock /api/disambiguation has an explicit 100ms `setTimeout` before fulfill. The `<500ms` assertion is no longer trivial: it asserts the full pipeline (request → mock fulfill → response → modal render) completes within 500ms. Playwright's default mocks fire instantaneously; without delay the test passes vacuously.

4. **Toothless-pattern guard (advisor #4).** Test asserts `disambig-picked-label === "institute"` after clicking cluster_id=1, NOT just `last-picked-id === "1"`. Proves state flowed to the parent component, not just the modal's local handler.

5. **Empty-clusters defensive (no regression).** Component still renders Title+Description+Cancel only when `clusters=[]`. Not exercised in this test (mock always returns 3 clusters); covered by I-f2-004 tests.

6. **Cancel state doesn't write `pickedClusterLabel`.** Test step #8 assertion implicitly verifies this: a Cancel-only path leaves `disambig-picked-label` empty. Not explicitly tested in this Issue (one-test scope per breakdown); covered by I-f2-004 tests.

7. **Pydantic field optionality.** `needs_disambiguation?: boolean` and `candidate_snippets?: ...[]` are optional (camelCase TypeScript optional, NOT snake_case alteration). Backend response without these fields is non-breaking. Existing intake tests do not regress.

8. **`runDisambiguation()` error handling.** Mirrors `runIntake()` pattern: throws Error on non-200 with parsed `code`. Test does NOT exercise error branches in this Issue (covered by I-f2-003 tests + future I-f2-007 edge); brief notes for completeness.

9. **No new `package.json` dep.**

10. **CHARTER §1 LOC cap.** Estimated 124 net pre-Prettier; conservative 76-line headroom for Prettier reflow. Final target ≤200.

11. **Hermeticity.** `page.route()` mocks /api/intake AND /api/disambiguation. No real backend hit. Test runs against `next start` per `playwright.config.ts`.

12. **Test assertion order.** `t_submit` captured BEFORE the click; `t_modal` captured AFTER `expect(...).toBeVisible()` resolves. The latency window includes Playwright's wait-for-visible polling, which is slightly pessimistic — acceptable since the assertion is `< 500ms`.

13. **Mock embeddings format.** `candidate_snippets[].embedding` is `number[]`; values `[1,0]/[0,1]/[-1,0]` are 2-D placeholders. The backend (mocked here) doesn't validate embeddings; the real backend would.

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
