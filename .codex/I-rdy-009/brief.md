# Codex BRIEF review — GH #505 (I-rdy-009): wire the disambiguation modal into the /dashboard ask/create-run flow

HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

---

## 0. Stage

Pre-implementation **brief** review — reviewing the *plan*, NOT a diff. No code written yet.

## 0.1 Context — #505 (I-rdy-009), scope settled by a Codex consult

#505 "Phase 3.6: wire ambiguity_detector into the ask/create-run flow.
Acceptance: an ambiguous query triggers the disambiguation modal in the
product flow." A Codex scope consult
(`.codex/I-rdy-009/scope_consult_verdict.txt`, Option B) settled the
residual: the F2 `DisambiguationModal` is already wired into the `/intake`
page, but `/intake` is gates-only and never creates a run; the actual
ask/create-run flow is `/dashboard` → `createRun()` → `POST /runs`, and
`/dashboard` never opens the `DisambiguationModal`. #505 = wire the
disambiguation modal into the `/dashboard` flow. Narrow scope — dashboard
only; NOT an intake/dashboard unification (that is #510).

## 1. Grounded current state (`polaris` HEAD f4653974)

`web/app/dashboard/page.tsx` ("Start a research run" — the run-creating
flow) ALREADY has ambiguity detection, but renders it as an inline card,
never the modal:
- `runScopeCheck()` (the "Check scope" button, `page.tsx:129-155`): calls
  `checkScope()`; then **iff `verdict === "accepted"` AND `uploads.length >
  0`**, builds `candidates` from the uploaded-doc `chunk_preview` text and
  calls `checkAmbiguity(question, candidates)` → `AmbiguityResult`.
- When `ambiguity?.is_ambiguous`, `page.tsx:386-434` renders an inline
  `<Card>` listing `ambiguity.clusters[].representative_text` + an
  "Acknowledge ambiguity" toggle button (`acknowledgedAmbiguity`).
- `onSubmit` (`page.tsx:167-172`) blocks `createRun()` if
  `ambiguity?.is_ambiguous && !acknowledgedAmbiguity`.

The reusable modal: `web/app/intake/components/disambiguation_modal.tsx` —
`DisambiguationModal({open, clusters: DisambiguationCluster[],
onSelectCluster, onCancel})`. `DisambiguationCluster` (`api.ts:423`) =
`{cluster_id: number, label: string, sample_snippets: string[]}`. It is
rendered today in `intake_form.tsx` (real) + the
`disambiguation_modal_preview` test harness.

`AmbiguityCluster` (`api.ts:184`) = `{cluster_id: number,
representative_text: string, member_source_ids: string[]}`.

## 2. The data-contract scope-boundary call (Codex consult flagged this — RULE IT)

The consult flagged: the true-F2 `/api/disambiguation` route needs embedded
candidate snippets; the dashboard's current candidates are upload chunk
text fed to the light `/ambiguity` detector. Two options:

- **(a) Reuse the dashboard's existing light `checkAmbiguity()` detector**
  — no new backend contract; map its `AmbiguityResult.clusters
  (AmbiguityCluster)` → `DisambiguationCluster` and render the modal off
  that.
- **(b) Wire the heavier F2 `/api/disambiguation` embedding path** into the
  dashboard — a new client call + an embedding source the dashboard does
  not currently have.

**Recommend (a).** The dashboard ALREADY runs a real ambiguity detector
(`/ambiguity`); #505's acceptance is "triggers the disambiguation modal,"
not "swap the detector." (a) reuses the real, already-wired detection and
only changes presentation + interaction — the smallest honest slice. (b)
would add an embedding pipeline the dashboard lacks (scope creep, and the
consult explicitly said keep #505 narrow). Codex: rule (a) vs (b).

## 3. Plan (assuming Codex accepts (a)) — REVISED per Codex brief iter-1 P1

**One file: `web/app/dashboard/page.tsx`** (frontend only; no backend, no
new api.ts client, no `RunRequest` change).

**Codex brief iter-1 P1 — the modal must be un-bypassable.** "Start run"
can call `createRun()` without ever clicking the optional "Check scope"
button; the current `onSubmit` gate (`ambiguity?.is_ambiguous &&
!acknowledgedAmbiguity`) is a no-op when `ambiguity` is still `null`. So an
ambiguous query could create a run with the modal never shown. Fix: the
ambiguity check is wired into the `onSubmit` path itself as a mandatory
preflight — `createRun()` cannot run until ambiguity has been checked for
the current inputs and resolved.

1. Add state: `disambigModalOpen: boolean`, `pickedClusterId: number |
   null`, and `ambiguityCheckedKey: string | null` — a key identifying the
   `(question, template, document_ids)` the ambiguity result is valid for
   (e.g. a JSON.stringify of those). `ambiguity` is "fresh" iff
   `ambiguityCheckedKey === currentInputKey`.
2. **`onSubmit` becomes the mandatory preflight** (after the existing
   length / `scopeDecision==="rejected"` guards): if `ambiguity` is NOT
   fresh for the current inputs, `await checkAmbiguity(question,
   candidates)` now, store the result + set `ambiguityCheckedKey`. Then: if
   `is_ambiguous` AND not resolved (no `pickedClusterId` AND not
   `acknowledgedAmbiguity`) → set `disambigModalOpen = true` and RETURN
   (do NOT call `createRun()`). Only when ambiguity is fresh AND
   (not `is_ambiguous` OR resolved) does `onSubmit` proceed to
   `createRun()`. `runScopeCheck()` (the "Check scope" button) stays as a
   convenience that pre-populates the same `ambiguity` + key (and also
   opens the modal on `is_ambiguous`), so a user who checks scope first
   sees the modal early — but submit no longer DEPENDS on them doing so.
   (`candidates` are the upload `chunk_preview` rows, same as today; a
   bare query with no uploads yields empty candidates → the light
   detector returns `is_ambiguous=false` → submit proceeds. Honest: with
   no candidate snippets there is nothing to disambiguate.)
3. Render `<DisambiguationModal>` in the dashboard form, clusters mapped
   from `AmbiguityResult`: each `AmbiguityCluster` → `{cluster_id, label:
   representative_text, sample_snippets: [representative_text]}` — an
   honest 1:1 reuse of the real `representative_text`, no fabricated
   label/snippet.
4. `onSelectCluster(cluster_id)`: record `pickedClusterId`, set
   `acknowledgedAmbiguity = true` (picking IS disambiguating), close the
   modal. The inline `<Card>` then shows a "Focused on: Cluster N" line so
   the choice is **visibly represented** (Codex brief iter-1 P2 / SB2).
5. `onCancel`: close the modal only. Ambiguity stays unresolved; the inline
   `<Card>` (kept — SB3) remains with the "acknowledge all clusters"
   fallback so the user is never stuck. A subsequent "Start run" with
   ambiguity still fresh + unresolved re-opens the modal.
6. **Stale-state invalidation (Codex brief iter-1 P2).** When `question`,
   `template`, or `uploads` change, clear `ambiguity`,
   `acknowledgedAmbiguity`, `pickedClusterId`, `ambiguityCheckedKey`, and
   set `disambigModalOpen = false` — otherwise a modal selection made for
   an earlier query could wrongly unblock a later, changed query. (The
   `ambiguityCheckedKey` mechanism in step 2 also defends this: a changed
   input makes the stored `ambiguity` non-fresh, forcing a re-check on
   submit. Implement BOTH the explicit clear and the freshness key.)
7. The existing inline ambiguity `<Card>` is KEPT (the modal is additive —
   it opens on detection; the Card is the persistent on-page record +
   acknowledge-all fallback + the "Focused on" indicator from step 4).

## 4. Scope-boundary calls (Codex: rule accept / adjust)

- **SB1 — detection source: (a) reuse light `checkAmbiguity` vs (b) F2
  `/api/disambiguation`.** Recommend (a) — see §2.
- **SB2 — what cluster-selection does** (Codex brief iter-1: accepted for
  this slice, with "the choice should be visibly represented"). The slice
  treats `onSelectCluster` as client-side disambiguation: record the
  choice + unblock submit + show a "Focused on: Cluster N" line in the
  inline `<Card>` (§3 step 4 — the visible representation). It does NOT
  pass the picked interpretation to the backend — `RunRequest`
  (`{template, question, document_ids}`) has no disambiguation field, and
  adding one is a backend contract change beyond #505's "trigger the
  modal" scope. "Pass the picked cluster to the run" is a noted follow-up.
- **SB3 — keep the inline ambiguity `<Card>`.** The modal is additive;
  the Card stays as the acknowledge-all path + the persistent on-page
  record (a modal, once cancelled, leaves no trace). Recommend ACCEPT keep.
- **SB4 — ambiguity detection is a mandatory `onSubmit` preflight**
  (REVISED per Codex brief iter-1 P1; the iter-1 "leave it on Check-scope
  only" plan is withdrawn). `onSubmit` itself runs `checkAmbiguity` when
  the result is not fresh for the current inputs, so the modal cannot be
  bypassed by clicking "Start run" without "Check scope" (§3 step 2).
  What stays out of scope: the *detector's candidate source* is unchanged
  — `candidates` are still the upload `chunk_preview` rows, so a bare
  query with no uploads has nothing to cluster and the light detector
  honestly returns `is_ambiguous=false`. Broadening the detector to infer
  ambiguity from the query text alone (with no candidates) would be a
  detector change, not a wiring change — OUT OF SCOPE for #505, noted as a
  known limitation. Codex: confirm the preflight wiring closes the
  bypass and that not broadening the candidate source is acceptable.

## 5. Smoke test

`cd web && npx prettier --write app/dashboard/page.tsx && npm run lint &&
npm run typecheck && npm run build`. No new unit test (a frontend
presentation+interaction change; the `DisambiguationModal` component is
already covered by the `disambiguation_modal_preview` harness). The CI e2e
job runs `inspector.spec.ts` (which has "Dashboard — scope discovery flow"
tests — scope check only, no ambiguity, unaffected) + `accessibility.spec
.ts` (the modal is closed-by-default → not in the DOM → no a11y delta).
Whether to add a dashboard-disambiguation e2e is SB5.

- **SB5 — e2e coverage.** Recommend NO new e2e in this slice: a dashboard
  disambiguation e2e needs a live backend returning `is_ambiguous` (the CI
  e2e backend serves golden fixtures, not a tunable ambiguity response),
  and the modal component itself is harness-covered. Codex: rule.

## 6. Files I have ALSO checked and they're clean

- `web/app/intake/components/disambiguation_modal.tsx` — the reusable
  modal; consumed as-is, NOT modified.
- `web/app/intake/components/intake_form.tsx` — the reference pattern for
  wiring the modal; NOT modified (intake is out of scope).
- `web/lib/api.ts` — `checkAmbiguity` / `AmbiguityResult` /
  `DisambiguationCluster` / `createRun`; all consumed as-is, NOT modified.
- `src/polaris_v6/api/ambiguity.py` — the `/ambiguity` backend; unchanged
  (the slice reuses it via the existing `checkAmbiguity` client).
- `web/tests/e2e/inspector.spec.ts`, `accessibility.spec.ts` — the CI-run
  e2e specs that touch `/dashboard`; their dashboard tests exercise scope
  check, not ambiguity; NOT modified.

## 7. Output schema (§8.3.9)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

Loose verdict prose is rejected — emit the schema.
