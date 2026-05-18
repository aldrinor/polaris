# Codex BRIEF review — I-rdy-008 / GH #504 slice 5: migrate the frame-coverage tab to AuditIR

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

---

## 0. Stage

Pre-implementation **brief** review — reviewing the *plan*, NOT a diff. No code written yet.

## 0.1 This is slice 5 of #504, Option A

#504 (I-rdy-008, Phase 3.5 — "wire live runs into the rich UI") is sliced
~12 ways per the Codex arch-decision consult (verdict A: serve the faithful
`AuditIR`; do NOT wholesale-mount the legacy 1400-line `inspector_router.py`).

- **Slices 1-4 shipped**: v6 route (PR #590); `web/lib/api.ts` `AuditIr*`
  types + `getAuditRun()` (PR #591); inspector shell + Executive-summary tab
  (PR #592); verified-sentences tab (PR #593).
- **This is slice 5: migrate the frame-coverage tab** — `FramesTab` in
  `web/app/inspector/[runId]/page.tsx` — off `getBundle()`/`EvidenceContract`
  onto the AuditIR `frame_coverage` (`AuditIrFrameCoverageReport` →
  `AuditIrFrameCoverageEntry` → `AuditIrRetrievalAttempt`).

**Consult key_risk (binding):** "split by tabs/surfaces, not rewritten in one
PR." Slice 5 touches ONLY `FramesTab` (+ its call site + the `frames` tab
count). `ContradictionsTab` / `ChartsTab` / `PoolTab` / `EvidencePane` stay
on `getBundle()` — slices 6-7. Do NOT flag "the other tabs still use
getBundle()" — deliberate.

## 1. Grounded state

### 1.1 The current `FramesTab` (`web/app/inspector/[runId]/page.tsx:478`)

`FramesTab({ bundle })` — iterates the flat `bundle.frame_coverage`
(`{ frame_id, frame_name, sources_assigned, coverage_percent }[]`); per frame
a Card: `frame_id` (description), `frame_name` (title), a progress bar at
`width: coverage_percent%`, `{sources_assigned} sources ·
{coverage_percent}% coverage`. `FramesTab` takes ONLY `bundle` — no
`onSelect`/`evidenceById`/contradiction cross-link (it is the simplest tab).
Call site `page.tsx:241` — `{activeTab === "frames" && <FramesTab
bundle={bundle} />}`. The `frames` tab count (`page.tsx:142`) is
`bundle.frame_coverage.length`.

### 1.2 The AuditIR shape (slice-2 `web/lib/api.ts`, verified vs `loader.py`
+ a real `manifest.json` `frame_coverage_report` block)

`AuditIrRun.frame_coverage` is `AuditIrFrameCoverageReport` — **a report,
not a flat list**:
- summary: `pass_count`, `partial_count`, `frame_gap_count`,
  `pipeline_fault_count`, `total_entities`, `total_slots`,
  `research_question`, `schema_version`, `semantics_warning` (`string|null`).
- `entries` (`AuditIrFrameCoverageEntry[]`): `entity_id`, `entity_type`,
  `section`, `slot_id`, `subsection_title`, `status`, `doi` (`string|null`),
  `pmid` (`string|null`), `failure_reason` (`string|null`),
  `available_artifacts` (`string[]`), `required_fields` (`string[]`),
  `min_fields_for_completion`, `provenance_class`,
  `human_completion_eligible`, `human_curated_provenance` (`string|null`),
  `is_pipeline_fault`, `retrieval_attempt_log` (`AuditIrRetrievalAttempt[]`:
  `attempt_index`, `source`, `url`, `outcome`, `http_status` `number|null`).

**Grounding done** — a real `manifest.json.frame_coverage_report`
(`outputs/carney_demo_rehearsal_smoke/clinical/clinical_tirzepatide_t2dm/`):
15 entries, `pass_count=14` / `partial_count=0` / `frame_gap_count=1` /
`pipeline_fault_count=0` / `total_entities=15` / `total_slots=15`;
`status` values seen `pass` and `fail_min_fields`; `subsection_title` is the
human label (e.g. "SURPASS-1 (Rosenstock et al., Lancet 2021)");
`provenance_class` e.g. "abstract_only". The loader derives `pass_count`/
`partial_count` from the raw `by_status` map; the TS `AuditIr*` types already
mirror the loader's projected shape (slice 2).

## 2. The plan — `web/app/inspector/[runId]/page.tsx` only (1 file)

`FramesTab` — new prop `{ ir: AuditIrRun }` (drop `bundle`):
- Empty-state: `ir.frame_coverage.entries.length === 0` → "No frame coverage."
- **`semantics_warning` banner** — when `ir.frame_coverage.semantics_warning`
  is non-null, render it as a disclosure banner above the list (the report
  measures *retrieval* coverage, not verified-report coverage — loader
  docstring §195).
- **Summary card** — `pass_count` / `partial_count` / `frame_gap_count` /
  `pipeline_fault_count`, plus `total_entities` / `total_slots`.
- **Per-entry list** — each `AuditIrFrameCoverageEntry` → Card:
  `subsection_title` (title), `section · slot_id` (description), a `status`
  badge (color: `pass`→emerald, `partial`→amber, anything else→destructive),
  `provenance_class`, `failure_reason` when non-null, `doi`/`pmid` links when
  non-null, and a collapsible `<details>` with the `retrieval_attempt_log`
  (`attempt_index` · `source` · `outcome` · `http_status` · `url`). Key =
  `${entity_id}:${slot_id}` (index fallback).
- Call site `page.tsx:241` → `<FramesTab ir={ir} />`.
- `frames` tab count → `ir.frame_coverage.entries.length`.

## 3. Scope-boundary calls for Codex — please rule explicitly

**3.1 — no per-entry `coverage_percent`.** The legacy per-frame progress bar
read a flat `coverage_percent` (0-100). AuditIR entries carry a discrete
`status`, NOT a percent — there is no faithful per-entry percentage. Plan:
drop the per-entry progress bar; render the per-entry `status` badge + a
report-level summary card (`pass_count`/`partial_count`/`frame_gap_count`/
`pipeline_fault_count` over `total_entities`). Rule: accept?

**3.2 — `frame_id`/`frame_name` → AuditIR `entity`/`slot` identifiers.**
AuditIR entries have no `frame_id`/`frame_name`; plan uses `subsection_title`
as the card title and `section · slot_id` as the description. Rule: accept?

**3.3 — `semantics_warning` disclosure banner.** The AuditIR
`frame_coverage` is explicitly *retrieval* coverage, not verified-content
coverage (loader docstring). Plan renders `semantics_warning` as a banner
when present. Rule: accept (recommended — honest disclosure).

**3.4 — `retrieval_attempt_log` rendering.** Each entry carries a nested
`retrieval_attempt_log`. Plan: a collapsible `<details>` per entry. Rule:
accept the collapsible, or defer the retrieval log to a later polish slice
(render only the entry status + failure_reason in slice 5)?

**3.5 — `status` is a free string.** The loader stores `status` as a raw
string (`str(raw["status"])`); real data shows `pass` / `fail_min_fields`,
plus `partial` implied by `partial_count`. Plan renders the raw string and
color-codes by `pass`→emerald / `partial`→amber / else→destructive. Rule:
accept the heuristic coloring?

## 4. Scope boundary

- **IN:** `web/app/inspector/[runId]/page.tsx` — `FramesTab` migrates to
  `getAuditRun()`/`AuditIrRun`; its call site; the `frames` tab count.
- **OUT:** `SentencesTab` (slice 4, done) / `ContradictionsTab` / `ChartsTab`
  / `PoolTab` / `EvidencePane` (slices 6-7); `web/lib/api.ts` (slice 2
  shipped the types — no change); `web/components/ui/**`; any `src/` change;
  the `getBundle()` fetch (removed when the last tab migrates).

## 5. Smoke test

Frontend change → the `lint + format + typecheck + build` CI job is IN
SCOPE. Offline: `cd web && npx prettier --write app/inspector/[runId]/page.tsx
&& npm run format:check && npm run lint && npm run typecheck && npm run
build` — all green. No new unit test (a data-source swap in a client
component, no new logic branches — consistent with slices 1-4). The 1
pre-existing inspector-page lint warning (`chartTypes` `exhaustive-deps` in
`ExecutiveSummaryTab`) must not increase.

## 6. Files I have ALSO checked and they're clean

- `web/lib/api.ts` — `AuditIrFrameCoverageReport`/`AuditIrFrameCoverageEntry`/
  `AuditIrRetrievalAttempt` (slice 2); NOT modified.
- `src/polaris_graph/audit_ir/loader.py` — `_parse_frame_coverage` /
  `_parse_frame_coverage_entry` (`frame_coverage` from
  `manifest.json.frame_coverage_report`; `by_status`→`pass_count`/
  `partial_count`); NOT modified.
- `FramesTab` takes only `bundle` today — no `onSelect`/`EvidencePane`
  coupling; the migration has no evidence-resolver blast radius.
- `SentencesTab` / `ContradictionsTab` / `ChartsTab` / `PoolTab` /
  `EvidencePane` — untouched.

## 7. Acceptance criteria for THIS PR (slice 5)

1. `FramesTab` renders `ir.frame_coverage` — `semantics_warning` banner (when
   present), a summary card (pass/partial/gap/fault counts), and the
   per-entry list (`subsection_title`, `section`/`slot_id`, `status` badge,
   `provenance_class`, `failure_reason`, `doi`/`pmid`, retrieval log).
2. The call site passes `ir`; the `frames` tab count reads
   `ir.frame_coverage.entries.length`.
3. `ContradictionsTab` / `ChartsTab` / `PoolTab` / `EvidencePane` unchanged.
4. `format:check` + `lint` + `typecheck` + `build` green; pre-existing
   lint-warning count not increased.
5. Only `web/app/inspector/[runId]/page.tsx` changed; no `web/lib/api.ts` /
   `src/` change.

## 8. Required output schema (§8.3.9)

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
