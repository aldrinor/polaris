# Claude architect audit — I-rdy-008 (#504) slice 7b

**Issue:** GH #504 (I-rdy-008) — Phase 3.5: wire live runs into the rich UI.
**Slice 7b of #504** — the frontend half of the slice-7 split decided by the
Codex architecture consult (`.codex/I-rdy-008/slice7_arch_consult_verdict.txt`):
7a backend evidence-span route → **7b frontend migration** → 7c test rebaseline.
Slices 1-6 + 7a merged (PR #590-#596).
**Branch:** `bot/I-rdy-008-slice7b` off `polaris` HEAD `2e4ef83f`.
**Commit 1:** `3847826c` — `web/app/inspector/[runId]/page.tsx` +
`web/lib/api.ts` + `logs/bug_log.md`.
**Brief:** `.codex/I-rdy-008/brief.md` — Codex brief review iter 1 APPROVE
(0 P0/P1; 3 P2 baked into commit 1).

## 1. What shipped

The inspector page is migrated off the golden-fixture-only `getBundle()`
dependency. Before this slice the page dual-fetched `getAuditRun()` +
`getBundle()` and gated its whole body on `{ir && bundle && (...)}`; for a
live run `getBundle()` 404s (its route `bundle.py` is a hardcoded 7-run
index), so `bundle` stayed null and the body never rendered. The inspector
was therefore golden-fixture-only — #504's live-run goal was unmet.

- **`web/lib/api.ts`** — new `getInspectorEvidence(runId)` client →
  `GET /api/inspector/runs/{runId}/evidence` (the slice-7a route), with
  `AuditIrEvidenceSpan` / `AuditIrEvidenceResponse` types matching that
  route's JSON. `getBundle` / `EvidenceContract` / `SourceSpan` /
  `downloadBundleAsJson` are **retained** — still imported by
  `web/app/runs/[runId]/page.tsx` (verified, see §2).
- **`web/app/inspector/[runId]/page.tsx`** — `bundle` state →
  `evidence: AuditIrEvidenceResponse | null` + `evidenceError: string | null`
  (an independent fetch alongside `getAuditRun()`); `selectedEvidence:
  SourceSpan` → `selectedEvidenceId: string | null`; the body gate +
  tabs-initializer gate drop `&& bundle` (now `ir` only); the bundle Export
  button removed; `PoolTab` + `EvidencePane` rewritten to consume the
  range-keyed evidence spans grouped by `evidence_id`.
- **`logs/bug_log.md`** — the slice-7 §6.2 Degradation Proposal marked
  RESOLVED.

## 2. Per-finding verification (against the APPROVE'd brief)

- **VERIFIED — getBundle() dependency removed from the inspector page.**
  `grep` of `web/app/inspector/[runId]/page.tsx` returns no `getBundle` /
  `EvidenceContract` / `SourceSpan` / `downloadBundleAsJson` references in
  code (only 4 prose comments mention "bundle" historically). The page no
  longer fetches `/runs/{id}/bundle`; for a live run with a completed
  AuditIR the body now renders.
- **VERIFIED — getBundle() retained for the runs page.** `getBundle` /
  `EvidenceContract` / `SourceSpan` / `downloadBundleAsJson` stay exported
  from `web/lib/api.ts`; `web/app/runs/[runId]/page.tsx` still imports them.
  No cross-page regression — slice 7b touches only the inspector page.
- **VERIFIED — P2-1 (PoolTab guards `evidence === null`).** Because the body
  now gates on `ir` only, `PoolTab` is reachable while the evidence fetch is
  still in flight. `PoolTab` branches: `evidenceError` → error panel;
  `evidence === null` → "Loading evidence…"; `evidence.spans` empty → "No
  verified evidence spans"; else the grouped list. No unguarded
  `evidence.spans` dereference.
- **VERIFIED — P2-2 (EvidencePane receives `evidenceError`).** `EvidencePane`
  takes `{evidenceId, spans, evidenceError, onClose}`; when the evidence
  fetch failed it renders an "Evidence unavailable" card carrying the error
  string rather than a misleading empty placeholder.
- **VERIFIED — P2-3 (dead `slugifySection` removed).** The
  `slugifySection` helper and the `SentencesTab` contradiction badge (its
  only consumers) are deleted; `tsc --noEmit` + `eslint` confirm no dead-code
  or unused-symbol error.
- **VERIFIED — evidence-fetch failure degrades only its tab.** The evidence
  fetch is independent of `getAuditRun()`; a failure sets `evidenceError`
  and leaves `ir` intact, so the Summary / Sentences / Frames /
  Contradictions tabs still render. Fail loud — the error string surfaces in
  PoolTab + EvidencePane; no silent fallback, no zero-fill.
- **VERIFIED — range-keyed spans grouped by `evidence_id`.** The slice-7a
  route returns one span per `(evidence_id, start, end)`. `PoolTab` builds a
  `Map<evidence_id, AuditIrEvidenceSpan[]>` (push-or-init), one row per
  source showing `tier` + span count + a preview; `EvidencePane` renders
  every span of the clicked id (`spans[0]` for the shared tier/source_url,
  iterates all spans for the char ranges + `<pre>` bodies).
- **VERIFIED — pool count.** The Pool tab badge counts distinct evidence
  ids: `new Set((evidence?.spans ?? []).map(s => s.evidence_id)).size` —
  `0` while loading/failed, not a crash.
- **VERIFIED — scope.** Only `web/app/inspector/[runId]/page.tsx` +
  `web/lib/api.ts` (code) + `logs/bug_log.md` (the §6.2 record). No backend
  change (7a shipped that), no test change (7c rebaselines the e2e/demo
  fixtures — deferred per the brief, Codex scope ruling 3.5 accept).

## 3. Smoke

`npx prettier --write` — both files reformatted. `npm run format:check` —
188 files flagged, all **pre-existing repo-wide debt** (the 2 slice-7b files
are clean post-prettier). `npm run lint` — **0 errors**, 3 warnings, all
pre-existing (`benchmark_board` unused import; `frame_coverage_panel.spec`
unused var; `page.tsx:705` `chartTypes` `exhaustive-deps` — verified
identical on `origin/polaris` at line 739, the line shift is slice-7b's
dead-code removal). `npm run typecheck` — `tsc --noEmit` clean. `npm run
build` — succeeded; `/inspector/[runId]` present as a dynamic route. No new
unit test (a data-source swap, consistent with slices 3-6); slice 7c
rebaselines the inspector e2e + demo fixtures.

## 4. Codex iteration trail

- **Slice-7 architecture consult** — split into 7a/7b/7c; live runs persist
  span text in `evidence_pool.json`; reject the lossy fallback.
- **Slice 7a** — backend evidence route, merged PR #596.
- **Brief iter 1 APPROVE** — 0 P0/P1; 3 P2 (PoolTab `evidence===null`
  guard; EvidencePane `evidenceError`; dead `slugifySection`) — all baked
  into commit 1.

## 5. Scope + residuals

Slice 7b = the frontend migration. 7c (inspector e2e + demo fixture
rebaseline) follows; #504 stays open. The slice-7a evidence route fails loud
(422) when a run predates `evidence_pool.json` persistence — the inspector
surfaces that as the PoolTab/EvidencePane "Evidence unavailable" state, the
honest UI for an un-renderable run.

## 6. Verdict

Faithful to the APPROVE'd brief and the Codex arch consult: the inspector
page no longer depends on the golden-fixture-only `getBundle()`, so a live
completed run renders; the evidence fetch is independent and fails loud into
its own tab without degrading the rest of the page; all 3 brief P2 guardrails
are in commit 1; `getBundle()` stays for the runs page; prettier / lint
(0 err) / tsc / build green. Ready for Codex diff review.
