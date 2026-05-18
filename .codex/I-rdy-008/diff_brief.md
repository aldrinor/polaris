# Codex DIFF review — I-rdy-008 / GH #504 slice 5: migrate the frame-coverage tab to AuditIR

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

---

## 1. What you are reviewing

The commit-1 diff for #504 **slice 5** — `git diff origin/polaris...HEAD`
excluding `.codex/I-rdy-008/` and `outputs/audits/I-rdy-008/` (canonical diff
in `.codex/I-rdy-008/codex_diff.patch`, sha256 trailer). Implements the
Codex-APPROVE'd brief `.codex/I-rdy-008/brief.md` (brief APPROVE iter 1, all
5 scope calls accepted). **1 file: `web/app/inspector/[runId]/page.tsx`.**

Slice 5 of ~12 for #504 (Option A). Migrates the inspector page
**frame-coverage tab** (`FramesTab`) off `getBundle()`/`EvidenceContract`
onto the AuditIR `frame_coverage`. `SentencesTab` (slice 4) /
`ContradictionsTab` / `ChartsTab` / `PoolTab` / `EvidencePane` stay on
`getBundle()` — slices 6-7. Do NOT flag "the other tabs still use
getBundle()" — deliberate.

## 2. The change

- `FramesTab` — new prop `{ ir: AuditIrRun }` (was `{ bundle }`); renders
  `ir.frame_coverage` (`AuditIrFrameCoverageReport`): a `semantics_warning`
  banner, a summary card (pass/partial/gap/fault counts, totals,
  schema_version), and a per-entry list (`subsection_title`, `section`/
  `slot_id`, `status` badge, `entity_type`/`provenance_class`,
  `failure_reason`, `doi`/`pmid` links, collapsible `retrieval_attempt_log`).
- New `frameStatusClass(status)` — heuristic color (pass/partial/else).
- `frames` tab count `bundle.frame_coverage.length` →
  `ir.frame_coverage.entries.length`.
- Call site `<FramesTab bundle={bundle} />` → `<FramesTab ir={ir} />`.

## 3. Verify

1. **AuditIR field access faithful.** `fc` = `ir.frame_coverage`
   (`AuditIrFrameCoverageReport`: `pass_count`, `partial_count`,
   `frame_gap_count`, `pipeline_fault_count`, `total_entities`,
   `total_slots`, `schema_version`, `semantics_warning|null`, `entries`);
   each entry (`AuditIrFrameCoverageEntry`: `entity_id`, `entity_type`,
   `section`, `slot_id`, `subsection_title`, `status`, `doi|null`,
   `pmid|null`, `failure_reason|null`, `provenance_class`,
   `is_pipeline_fault`, `retrieval_attempt_log`); each attempt
   (`AuditIrRetrievalAttempt`: `attempt_index`, `source`, `url`, `outcome`,
   `http_status|null`). Cross-check `web/lib/api.ts` (slice 2) +
   `src/polaris_graph/audit_ir/loader.py` `_parse_frame_coverage`.
2. **No fabrication.** Nullable fields (`semantics_warning`,
   `failure_reason`, `doi`, `pmid`, `http_status`) are all guarded before
   render; `subsection_title` falls back to `entity_id`.
3. **`status` is a free string** — `frameStatusClass` renders it raw and
   only color-codes; no enum assumption breaks an unknown value.
4. **`FramesTab` no longer reads `bundle`** — the prop is `ir` only.
5. **The other tabs + `EvidencePane`** are byte-identical to `polaris` HEAD;
   `evidenceById` / `onSelect` chains untouched.
6. **Scope** — only `web/app/inspector/[runId]/page.tsx`; no `web/lib/api.ts`,
   no `web/components/ui/**`, no `src/`.

## 4. Files I have ALSO checked and they're clean

- `web/lib/api.ts` — `AuditIrFrameCoverageReport`/`AuditIrFrameCoverageEntry`/
  `AuditIrRetrievalAttempt` (slice 2); NOT modified.
- `src/polaris_graph/audit_ir/loader.py` — `_parse_frame_coverage` (frame
  coverage from `manifest.json.frame_coverage_report`; `by_status` →
  `pass_count`/`partial_count`); NOT modified.
- `SentencesTab` / `ContradictionsTab` / `ChartsTab` / `PoolTab` /
  `EvidencePane` — untouched.

## 5. Smoke state

`web/`: `prettier --write app/inspector/[runId]/page.tsx` → applied;
`npm run lint` → 0 errors (3 pre-existing warnings, count unchanged —
`chartTypes` `exhaustive-deps` in `ExecutiveSummaryTab` is pre-existing);
`npm run typecheck` → clean; `npm run build` → OK. The `lint + format +
typecheck + build` CI job is in scope for this web/ PR.

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
