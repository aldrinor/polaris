# Codex DIFF review — GH #505 (I-rdy-009): wire the disambiguation modal into the /dashboard flow

HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

---

## 0. Iter-1 finding — addressed (VERIFY the fix)

Iter 1 returned REQUEST_CHANGES with 1 P1 (0 P0):

**P1 `stale_async_guard_uses_stale_render_closure`** — the `onSubmit`
ambiguity preflight re-read `currentInputKey()` AFTER `await
checkAmbiguity` to detect a mid-flight input change, but the re-read used
the SAME render closure's `question`/`template`/`uploads` — it could
never observe a change that occurred during the await, so the stale guard
was a dead no-op. Required fix: "Capture an immutable input snapshot
before async work, compare against a latest-key ref after awaits before
setting ambiguity/modal state or proceeding to `createRun()`, and only
treat `pickedClusterId`/`acknowledgedAmbiguity` as resolving the ambiguity
when it belongs to the fresh checked key."

**Fix applied (commit `30a9d67e`), web/app/dashboard/page.tsx:**
- `currentInputKey` is now a **render-computed const** (was a function);
  a no-dep `useEffect` mirrors it into `latestInputKeyRef` — a ref WRITE,
  not `setState`, so it does not trip `react-hooks/set-state-in-effect`.
  Async code now compares a captured key against `latestInputKeyRef
  .current` (the LATEST committed inputs), never a stale closure re-read.
- `onSubmit` and `runScopeCheck` capture `const key = currentInputKey`
  BEFORE the await and guard with `latestInputKeyRef.current !== key`.
- New `resolvedForKey` state binds a resolution (a modal cluster pick or
  an acknowledge-all) to the input key it was made for. `resolved` is now
  `resolvedForKey === key && (pickedClusterId !== null ||
  acknowledgedAmbiguity)` — a resolution recorded for an earlier query
  can no longer unblock a later, changed one.
- `resetAmbiguityState()` clears `resolvedForKey`; `onSelectCluster` and
  the inline-card acknowledge toggle both `setResolvedForKey(
  currentInputKey)`.

**VERIFY:** confirm the iter-1 P1 is closed — the post-await guard now
reads `latestInputKeyRef`, the resolution is key-bound, and no new P0/P1
was introduced (e.g. the `latestInputKeyRef` effect is lint-clean; the
`resolved` key-binding does not wrongly re-block a still-valid pick).

---

## 1. What you are reviewing

The commit-1 diff for #505 (I-rdy-009) — `git diff origin/polaris...HEAD`
excluding `.codex/I-rdy-009/` and `outputs/audits/I-rdy-009/` (canonical
diff in `.codex/I-rdy-009/codex_diff.patch`, sha256 trailer). Implements the
Codex-APPROVE'd brief `.codex/I-rdy-009/brief.md` (brief APPROVE iter 2;
0 P0/P1; 5 P2 baked in). **1 code file: `web/app/dashboard/page.tsx`**
(+ `state/polaris_restart/iteration_trajectory.md` process metadata).

## 2. The change

A Codex scope consult (`.codex/I-rdy-009/scope_consult_verdict.txt`, Option
B) settled #505: the F2 `DisambiguationModal` was already wired into
`/intake` (gates-only — never creates a run); the residual is the
run-creating `/dashboard` flow (`createRun()` → `POST /runs`), which only
rendered an inline ambiguity card and never opened the modal.

`web/app/dashboard/page.tsx` (frontend only — no backend / `api.ts` /
`RunRequest` change):
- New state: `disambigModalOpen`, `pickedClusterId`, `ambiguityCheckedKey`.
- `onSubmit` runs a **mandatory ambiguity preflight** before `createRun()`:
  if `ambiguity` is not fresh for the current `(question, template,
  document_ids)` key it `await`s `checkAmbiguity` itself; if `is_ambiguous`
  and not resolved → opens the modal + returns (no run). This closes the
  iter-1 P1 bypass (clicking "Start run" without "Check scope").
- The `DisambiguationModal` is rendered; clusters mapped from the real
  `AmbiguityResult` (`{cluster_id, label: representative_text,
  sample_snippets: [representative_text]}`).
- `onSelectCluster` sets `pickedClusterId`; `acknowledgedAmbiguity` is the
  distinct "run on all" mode; `resolved = pickedClusterId !== null ||
  acknowledgedAmbiguity`. The inline card shows "Focused on Cluster N".
- `resetAmbiguityState()` is called from every question/template/uploads
  change handler (not a `useEffect`) to clear stale result + selection.
- `runScopeCheck` ("Check scope") also opens the modal on `is_ambiguous`
  and sets the freshness key — it is now a convenience, not the only path.

## 3. Verify

1. **The modal cannot be bypassed.** Confirm `onSubmit` cannot reach
   `createRun()` for an `is_ambiguous` + unresolved query: the preflight
   runs `checkAmbiguity` when the result is not fresh, and the
   `amb?.is_ambiguous && !resolved` gate opens the modal + `return`s before
   `createRun()`.
2. **No fabricated data.** The modal clusters are a 1:1 map of the real
   `AmbiguityResult.clusters`; `representative_text` (real detector output)
   is reused as `label` + `sample_snippets`. No invented label/snippet.
3. **Stale-state invalidation.** `resetAmbiguityState()` is called from the
   `<Input>` onChange, the template `<button>` onClick, `handleFiles`, and
   the upload "remove" button — and the `ambiguityCheckedKey` freshness key
   forces an `onSubmit` re-check on a changed input. Confirm a cluster
   picked for an earlier query cannot unblock a later, changed one.
4. **Stale-async guard.** Both `runScopeCheck` and the `onSubmit` preflight
   capture the input key before `await checkAmbiguity` and discard the
   result if the key changed during the await.
5. **`submitting` state.** Confirm every early-return path in `onSubmit`
   (stale discard, ambiguity-check error, modal-opened) clears `submitting`
   so the "Start run" button is not left disabled.
6. **Scope.** Only `web/app/dashboard/page.tsx` (+ the trajectory metadata
   file). No backend, no `api.ts`, no `RunRequest`, no `/intake` change.

## 4. Files I have ALSO checked and they're clean

- `web/app/intake/components/disambiguation_modal.tsx` — the reusable
  modal; consumed as-is, NOT modified.
- `web/lib/api.ts` — `checkAmbiguity` / `AmbiguityResult` /
  `AmbiguityCandidate` / `DisambiguationCluster` / `createRun`; consumed
  as-is, NOT modified.
- `src/polaris_v6/api/ambiguity.py` — the `/ambiguity` backend; the slice
  reuses it via the existing client; NOT modified.
- `web/app/intake/components/intake_form.tsx` — the modal-wiring reference
  pattern; `/intake` is out of scope; NOT modified.
- `web/tests/e2e/inspector.spec.ts`, `accessibility.spec.ts` — the CI-run
  e2e specs touching `/dashboard`; their dashboard tests exercise scope
  check (no ambiguity); the modal is closed-by-default; NOT modified.

## 5. Smoke state

`npx prettier --write app/dashboard/page.tsx` — formatted. `npm run lint` —
0 errors, 3 pre-existing warnings (none in the changed file). `npm run
typecheck` — `tsc --noEmit` clean. `npm run build` — succeeded. No new e2e
(SB5 — accepted: the CI golden-fixture backend cannot force an ambiguous
response; the modal component is harness-covered).

## 6. Required output schema (§8.3.9)

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
