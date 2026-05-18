# Claude architect audit — GH #505 (I-rdy-009)

**Issue:** GH #505 (I-rdy-009) — Phase 3.6: wire ambiguity_detector into the
ask/create-run flow. Acceptance: an ambiguous query triggers the
disambiguation modal in the product flow.
**Scope:** settled by a Codex scope consult
(`.codex/I-rdy-009/scope_consult_verdict.txt`, Option B) — the F2
`DisambiguationModal` was already in `/intake` (gates-only, never creates a
run); the residual is the run-creating `/dashboard` flow, which never opened
the modal.
**Branch:** `bot/I-rdy-009` off `polaris` HEAD `f4653974`.
**Commit 1:** `04487bf8` — `web/app/dashboard/page.tsx`.
**Brief:** `.codex/I-rdy-009/brief.md` — Codex brief review APPROVE iter 2
(iter-1 1 P1 + 1 P2 fixed; SB1-SB5 ruled).

## 1. What shipped

`web/app/dashboard/page.tsx` (frontend only — no backend, no `api.ts`, no
`RunRequest` change): the `/dashboard` "Start a research run" flow now opens
the reusable `DisambiguationModal` when an ambiguous query is detected,
before `createRun()`.

## 2. Per-finding verification (against the APPROVE'd brief)

- **VERIFIED — the modal is un-bypassable (Codex brief iter-1 P1).**
  `onSubmit` runs a mandatory ambiguity preflight: when `ambiguity` is not
  fresh for the current `(question, template, document_ids)` key, it
  `await`s `checkAmbiguity` itself; if the result `is_ambiguous` and is not
  resolved, it sets `disambigModalOpen = true` and `return`s WITHOUT calling
  `createRun()`. "Start run" can no longer reach `createRun()` for an
  unresolved ambiguous query — the optional "Check scope" button is no
  longer the only detection path.
- **VERIFIED — SB1: reuse the existing light detector.** The slice calls
  the already-wired `checkAmbiguity()` (`POST /ambiguity`); no
  `/api/disambiguation` embedding path, no new `api.ts` client, no backend
  change.
- **VERIFIED — no fabricated data (clinical-audit rule).** The modal's
  clusters are mapped 1:1 from the real `AmbiguityResult.clusters`:
  `{cluster_id, label: representative_text, sample_snippets:
  [representative_text]}`. `representative_text` is the detector's real
  output; it is reused as the label/snippet, never invented.
- **VERIFIED — distinct resolution modes (Codex brief iter-1 P2 / SB2).**
  `pickedClusterId` (one cluster picked via the modal) and
  `acknowledgedAmbiguity` (run on all clusters) are separate states;
  `resolved = pickedClusterId !== null || acknowledgedAmbiguity`. The inline
  card shows "Focused on Cluster N" when a cluster is picked (the choice is
  visibly represented) and otherwise offers "Pick a meaning…" + "Acknowledge
  ambiguity".
- **VERIFIED — stale-state invalidation (Codex brief iter-1 P2).** Two
  defenses: (1) `ambiguityCheckedKey` — the `onSubmit` preflight re-checks
  when the key no longer matches the current inputs; (2)
  `resetAmbiguityState()` — clears `ambiguity` / `acknowledgedAmbiguity` /
  `pickedClusterId` / `ambiguityCheckedKey` / `disambigModalOpen`, called
  from every question / template / uploads change handler (the `<Input>`
  onChange, the template `<button>` onClick, `handleFiles`, and the upload
  "remove" button). A cluster picked for an earlier query cannot leak into a
  later changed one. The reset lives in the handlers, NOT a `useEffect` —
  resetting state in an effect is the `react-hooks/set-state-in-effect`
  anti-pattern (caught by lint and corrected).
- **VERIFIED — stale-async guard (Codex brief iter-2 P2).** Both
  `runScopeCheck` and the `onSubmit` preflight capture the input key BEFORE
  `await checkAmbiguity`, and discard the result if `currentInputKey()` no
  longer matches after the await — no stale modal / no duplicate submit.
- **VERIFIED — SB4 limitation is honest + documented.** The detector's
  candidate source is unchanged (upload `chunk_preview` rows); a bare query
  with no uploads yields empty candidates and the preflight honestly treats
  it as not-ambiguous (nothing to cluster) — no fabricated ambiguity. This
  is the documented out-of-scope limitation, not a silent gap.
- **VERIFIED — scope.** Only `web/app/dashboard/page.tsx`. The
  `DisambiguationModal` component, `intake_form.tsx`, `api.ts`, and the
  `/ambiguity` backend are consumed/untouched. No `/intake` change (the
  consult ruled against unifying intake/dashboard — that is #510).

## 3. Smoke

`npx prettier --write app/dashboard/page.tsx` — formatted. `npm run lint` —
**0 errors**, 3 warnings, all pre-existing (`benchmark_board` unused import;
`inspector/[runId]/page.tsx:739` `chartTypes` exhaustive-deps;
`frame_coverage_panel.spec` unused var) — none in the changed file. `npm run
typecheck` — `tsc --noEmit` clean. `npm run build` — succeeded. No new e2e
(SB5 — a dashboard disambiguation e2e needs a tunable-ambiguity backend the
CI golden-fixture backend cannot provide; the `DisambiguationModal`
component is harness-covered).

## 4. Codex iteration trail

- Scope consult — Option B (residual = the `/dashboard` flow).
- Brief iter 1 REQUEST_CHANGES — P1: "Start run" could bypass the modal;
  P2: stale modal selection. Brief iter 2 APPROVE — both fixed (mandatory
  `onSubmit` preflight; freshness key + handler-based reset); SB1-SB5 ruled.

## 5. Scope + residuals

#505's whole residual per the scope consult is this dashboard slice — #505
closes on merge. Noted follow-ups (out of #505 scope): passing the picked
cluster to the backend would need a `RunRequest` disambiguation field; and
the dashboard's ambiguity detector only has upload-chunk candidates, so a
bare query with no uploads is not analysed — broadening the detector to
query-text-only ambiguity is a detector change, not a wiring change.

## 6. Verdict

Faithful to the APPROVE'd brief and the Codex scope consult: the `/dashboard`
ask/create-run flow now triggers the `DisambiguationModal` on an ambiguous
query via a mandatory, un-bypassable `onSubmit` preflight; the modal shows
real detector clusters with no fabricated data; resolution modes are
distinct and stale selections are invalidated; prettier / lint (0 err) /
tsc / build green. Ready for Codex diff review.
