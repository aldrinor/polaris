# Claude architect audit — I-rdy-008 (#504) slice 6

**Issue:** GH #504 (I-rdy-008) — Phase 3.5: wire live runs into the rich UI.
**Slice 6 of ~12** (Codex arch-decision consult, verdict A). Slices 1-5
merged (PR #590/#591/#592/#593/#594). #504 closes when the last slice lands.
**Branch:** `bot/I-rdy-008-slice6` off `polaris` HEAD `a365938f`.
**Commit 1:** `4bf6f1c4` — `web/app/inspector/[runId]/page.tsx`.
**Brief:** `.codex/I-rdy-008/brief.md` — Codex brief review iter 1 APPROVE
(0 P0/P1; all 6 scope-boundary calls ruled accept; 1 P2 baked in).

## 1. What shipped

The inspector page **contradictions tab** (`ContradictionsTab`) migrates off
`getBundle()`/`EvidenceContract` onto the faithful AuditIR `contradictions`
(`AuditIrContradictionCluster` → `AuditIrContradictionClaim`).

- `ContradictionsTab` takes `{ ir, onSelect }`: maps `ir.contradictions` —
  per **cluster** Card (`key = cluster_id`): a `severity` badge + the
  numeric disagreement (`absolute_difference`/`relative_difference`) in the
  description, `subject` — `predicate` title, `recommended_action` line, and
  an N-row claims list. Per **claim** row: `value` `unit` +
  `endpoint_phrase`, `arm`/`dose`/`source_tier`, `context_snippet`, a
  clickable `evidence_id` button, and a `source_url` link.
- New `contradictionSeverityClass` color-codes the `severity` string.

## 2. Per-finding verification (against the APPROVE'd brief)

- **VERIFIED — AuditIR field access faithful.** Every `c.*` / `claim.*`
  access cross-checked against the slice-2 `AuditIrContradictionCluster` /
  `AuditIrContradictionClaim` interfaces (`web/lib/api.ts`) and the loader
  (`_parse_contradictions` / `_parse_contradiction_claim`). `cluster_id` is
  the loader-assigned enumerate index (line 569).
- **VERIFIED — §3.1 (N-claim list).** The legacy 2-column `claim_a`/
  `claim_b` grid is replaced by a per-cluster header + an N-row
  `cluster.claims[]` list — the faithful AuditIR shape.
- **VERIFIED — §3.2 (no section_id/contradiction_id).** The legacy
  `contradiction_id · section_id · resolution` header is dropped;
  `cluster_id` is the React key only (not displayed). The header is
  `subject` — `predicate` + `severity`.
- **VERIFIED — §3.3 (`recommended_action`).** Rendered as the
  `resolution`-successor line under the header (gated on non-empty).
- **VERIFIED — §3.4 (`onSelect` bundle-backed).** Each claim's `evidence_id`
  button calls `onSelect(evidence_id)` → the `InspectorPage` closure
  resolves it via the bundle `evidenceById` → `EvidencePane`
  (bundle-backed; migrates with the pool surface). Click chain functional in
  the dual-fetch state.
- **VERIFIED — §3.5 (full claim detail).** `value`/`unit`/`endpoint_phrase`/
  `arm`/`dose`/`source_tier`/`context_snippet`/`source_url` all rendered.
- **VERIFIED — P2 (`source_url` non-empty guard).** The `source` link is
  gated on `claim.source_url &&` — the loader defaults a missing
  `source_url` to `""`, so no empty-href anchor renders.
- **VERIFIED — §3.6 (SentencesTab badge untouched).** `SentencesTab`'s
  `bundle.contradictions[].section_id` contradiction-in-section badge is
  byte-unchanged — independent of `ContradictionsTab`'s data source.
- **VERIFIED — scope.** Only `web/app/inspector/[runId]/page.tsx` changed
  (`ContradictionsTab` + its call site + the `contradictions` tab count).
  No `web/lib/api.ts`, no `web/components/ui/**`, no `src/`. `SentencesTab`/
  `FramesTab`/`ChartsTab`/`PoolTab`/`EvidencePane` untouched.

## 3. Smoke

`web/`: `prettier --write app/inspector/[runId]/page.tsx` → applied;
`npm run lint` → 0 errors (3 repo-wide warnings, all pre-existing —
`chartTypes` `exhaustive-deps` in `ExecutiveSummaryTab`, `benchmark_board.tsx`,
`frame_coverage_panel.spec.ts`; count NOT increased); `npm run typecheck`
→ clean; `npm run build` → OK.

## 4. Codex iteration trail

- **Brief iter 1 APPROVE** — 0 P0/P1; all 6 §3 scope-boundary calls ruled
  accept (N-claim list, cluster_id key-only header, recommended_action
  successor, bundle-backed onSelect, full claim detail, no SentencesTab
  action); 1 P2 (source_url non-empty guard) baked into commit 1.

## 5. Scope + residuals

Slice 6 = the contradictions tab. Remaining per the consult: slice 7 pool +
`EvidencePane`, slices 8-12 charts / compare / follow-up / pin replay /
memory / bundle UX. The `getBundle()` call is removed when the last tab
migrates. #504 stays open.

## 6. Verdict

Faithful to the APPROVE'd brief; the contradictions tab renders the AuditIR
N-claim cluster shape 1:1; the legacy 2-sided A/B layout is replaced with the
cluster+claims structure (the AuditIR-faithful shape); all 6 scope calls
implemented as ruled; `SentencesTab`/`FramesTab`/`ChartsTab`/`PoolTab`/
`EvidencePane` untouched (the consult's split-by-surface discipline); web
smoke (prettier/lint/typecheck/build) all green. Ready for Codex diff review.
