# Claude architect audit — I-rdy-008 (#504) slice 5

**Issue:** GH #504 (I-rdy-008) — Phase 3.5: wire live runs into the rich UI.
**Slice 5 of ~12** (Codex arch-decision consult, verdict A). Slices 1-4
merged (PR #590/#591/#592/#593). #504 closes when the last slice lands.
**Branch:** `bot/I-rdy-008-slice5` off `polaris` HEAD `54c5660f`.
**Commit 1:** `364f7497` — `web/app/inspector/[runId]/page.tsx`.
**Brief:** `.codex/I-rdy-008/brief.md` — Codex brief review iter 1 APPROVE
(0 P0/P1; all 5 scope-boundary calls ruled accept).

## 1. What shipped

The inspector page **frame-coverage tab** (`FramesTab`) migrates off
`getBundle()`/`EvidenceContract` onto the faithful AuditIR `frame_coverage`
(`AuditIrFrameCoverageReport` → `AuditIrFrameCoverageEntry` →
`AuditIrRetrievalAttempt`).

- `FramesTab` takes `ir`: renders a `semantics_warning` disclosure banner
  (when non-null), a summary card (`pass_count`/`partial_count`/
  `frame_gap_count`/`pipeline_fault_count` over `total_entities`/
  `total_slots`/`schema_version`), and a per-entry list — `subsection_title`,
  `section`/`slot_id`, a `status` badge, `entity_type`/`provenance_class`,
  `failure_reason`, `doi`/`pmid` links, and a collapsible
  `retrieval_attempt_log`.
- New `frameStatusClass` color-codes the `status` string (pass→emerald,
  partial→amber, else→red).
- The `frames` tab count reads `ir.frame_coverage.entries.length`.

## 2. Per-finding verification (against the APPROVE'd brief)

- **VERIFIED — AuditIR field access faithful.** Every `fc.*` / `e.*` /
  `a.*` access cross-checked against the slice-2 `AuditIrFrameCoverageReport`
  / `AuditIrFrameCoverageEntry` / `AuditIrRetrievalAttempt` interfaces
  (`web/lib/api.ts`) and the loader (`_parse_frame_coverage` /
  `_parse_frame_coverage_entry`). Nullable fields (`semantics_warning`,
  `failure_reason`, `doi`, `pmid`, `http_status`) are all guarded.
- **VERIFIED — §3.1 (no coverage_percent).** The legacy per-frame progress
  bar is dropped; AuditIR entries carry a discrete `status`, not a
  percentage. Replaced by the per-entry `status` badge + the report-level
  summary card.
- **VERIFIED — §3.2 (identifiers).** `subsection_title` is the card title
  (falls back to `entity_id` when empty); `section`/`slot_id` is the
  description. No `frame_id`/`frame_name` fabricated.
- **VERIFIED — §3.3 (`semantics_warning` banner).** Rendered as a
  `role="note"` banner above the list when present — honest disclosure that
  this report measures retrieval coverage, not verified-content coverage.
- **VERIFIED — §3.4 (`retrieval_attempt_log`).** Rendered as a collapsible
  `<details>` per entry (`attempt_index`/`source`/`outcome`/`http_status`/
  `url`) — Codex ruled accept-in-slice-5.
- **VERIFIED — §3.5 (`status` coloring).** `frameStatusClass` renders the
  raw `status` string and color-codes `pass`/`partial`/else — Codex ruled
  accept the heuristic.
- **VERIFIED — `FramesTab` had no `onSelect`/`evidenceById`/`EvidencePane`
  coupling.** The migration has zero evidence-resolver blast radius; the tab
  no longer reads `bundle` at all.
- **VERIFIED — scope.** Only `web/app/inspector/[runId]/page.tsx` changed
  (`FramesTab` + its call site + the `frames` tab count). No `web/lib/api.ts`,
  no `web/components/ui/**`, no `src/`. `SentencesTab`/`ContradictionsTab`/
  `ChartsTab`/`PoolTab`/`EvidencePane` untouched.

## 3. Smoke

`web/`: `prettier --write app/inspector/[runId]/page.tsx` → applied;
`npm run lint` → 0 errors (3 repo-wide warnings, all pre-existing —
`chartTypes` `exhaustive-deps` in `ExecutiveSummaryTab`, `benchmark_board.tsx`,
`frame_coverage_panel.spec.ts`; count NOT increased); `npm run typecheck`
→ clean; `npm run build` → OK.

## 4. Codex iteration trail

- **Brief iter 1 APPROVE** — 0 P0/P1; all 5 §3 scope-boundary calls ruled
  accept (no coverage_percent, entity/slot identifiers, semantics_warning
  banner, collapsible retrieval log, raw-status coloring).

## 5. Scope + residuals

Slice 5 = the frame-coverage tab. Remaining per the consult: slice 6
contradictions, slice 7 pool + `EvidencePane`, slices 8-12 charts / compare /
follow-up / pin replay / memory / bundle UX. The `getBundle()` call is
removed when the last tab migrates. #504 stays open.

## 6. Verdict

Faithful to the APPROVE'd brief; the frame-coverage tab renders the AuditIR
`frame_coverage` report 1:1; the legacy progress-bar UX is replaced with the
status-based manifest (the AuditIR-faithful shape); all 5 scope calls
implemented as ruled; `ContradictionsTab`/`ChartsTab`/`PoolTab`/`EvidencePane`
untouched (the consult's split-by-surface discipline); web smoke
(prettier/lint/typecheck/build) all green. Ready for Codex diff review.
