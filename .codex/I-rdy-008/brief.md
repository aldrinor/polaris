# Codex BRIEF review — I-rdy-008 / GH #504 slice 2: frontend AuditIR client helper + types

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

## 0.1 This is slice 2 of #504, Option A

#504 (I-rdy-008, Phase 3.5) is sliced ~12 ways (Codex arch-decision consult,
`.codex/I-rdy-008/arch_decision_verdict.txt`, verdict A). **Slice 1 shipped**
(PR #590, merged): the v6 backend route `GET /api/inspector/runs/{run_id}` →
faithful AuditIR JSON. **This is slice 2: the frontend client helper + types.**
No UI migration — the inspector page rewrite is slice 3. #504 closes when the
last slice lands. Do NOT flag "the UI still uses getBundle()" — that is slice 3.

## 1. Grounded state

- Slice 1 added `src/polaris_v6/api/inspector.py` — `GET /api/inspector/runs/{run_id}`
  returns `to_json_dict(load_audit_ir(artifact_dir))`, i.e. the full faithful
  `AuditIR` JSON.
- `web/lib/api.ts` — `BACKEND_URL = "/api/v6"`; helpers follow the pattern
  `export async function getX(...): Promise<T> { const r = await
  authFetch(\`${BACKEND_URL}/...\`); return asJsonOrThrow<T>(r); }`.
- `web/lib/api.ts` already has an unrelated `EvidenceContract` /
  `SourceSpan` / `VerifiedSentence` / `getBundle()` block (the golden-fixture
  path slice 3 will migrate *off*). The new AuditIR types must be NAMED
  DISTINCTLY so there is no collision.
- The `AuditIR` JSON shape is the `to_json_dict` projection of the dataclass
  tree in `src/polaris_graph/audit_ir/loader.py`: top-level
  `ir_schema_version`, `run_id`, `artifact_dir`, `report_md`, `manifest`
  (`RunManifest`), `bibliography[]` (`BibliographyEntry`), `contradictions[]`
  (`ContradictionCluster`→`ContradictionClaim`), `frame_coverage`
  (`FrameCoverageReport`→`FrameCoverageEntry`→`RetrievalAttempt`), `tier_mix`
  (`TierMix`), `verified_report` (`VerifiedReport`→`ReportSection`→
  `ReportSentence`→`EvidenceSpanToken`), `model_provenance`
  (`ModelProvenance`|null, → `RuleCheck`), `protocol` (`ProtocolMetadata`|null,
  → `TierExpectation`), `adequacy` (`AdequacyGate`|null), `corpus_approval`
  (`CorpusApprovalGate`|null).

## 2. The plan

**One file: `web/lib/api.ts`.**

1. Add TypeScript interfaces mirroring the `AuditIR` JSON shape, prefixed
   `AuditIr*` (e.g. `AuditIrRun`, `AuditIrManifest`, `AuditIrSentence`,
   `AuditIrEvidenceSpanToken`, `AuditIrContradictionCluster`, …) so they do
   not collide with the existing `EvidenceContract`/`SourceSpan` block.
   `model_provenance` / `protocol` / `adequacy` / `corpus_approval` are
   `... | null` (the loader returns `None` for legacy/abort artifacts).
   `tier_mix.fractions` and `verified_report.drop_reason_counts` are
   `Record<string, number>`.
2. Add `export async function getAuditRun(runId: string):
   Promise<AuditIrRun>` → `authFetch(\`${BACKEND_URL}/api/inspector/runs/${encodeURIComponent(runId)}\`)`
   → `asJsonOrThrow<AuditIrRun>`. (`BACKEND_URL` is `/api/v6`; the v6 route
   prefix is `/api/inspector` — the composed path is correct.)

## 3. Scope boundary

- IN: `web/lib/api.ts` — new `AuditIr*` types + `getAuditRun()`.
- OUT: any UI / `web/app/**` change (slice 3+); `getAuditReportMarkdown()` /
  `getAuditHealth()` / audit-bundle helpers — those need v6 facade routes
  that slice 1 did NOT build (only `/api/inspector/runs/{run_id}` exists);
  they come with their backend slices. The existing `EvidenceContract` /
  `getBundle()` block is left untouched (slice 3 migrates the UI off it).

## 4. Smoke test

This is a frontend-lib change, so the `lint + format + typecheck + build` CI
job is IN SCOPE and must pass. Offline: `cd web && npm run format:check &&
npm run lint && npm run typecheck && npm run build` — all green. No new unit
test (a type+fetch-helper addition with no logic branches; consistent with how
`getRun`/`getBundle`/`getChart` were added). If `npm run typecheck` flags the
new interfaces, fix before commit.

## 5. Files I have ALSO checked and they're clean

- `src/polaris_v6/api/inspector.py` (slice 1) — the route the helper targets;
  NOT modified.
- `src/polaris_graph/audit_ir/loader.py` — the `AuditIR` dataclass tree the TS
  types mirror; NOT modified.
- `web/lib/api.ts` `EvidenceContract` block — distinct names, no collision;
  NOT modified.

## 6. Acceptance criteria for THIS PR (slice 2)

1. `web/lib/api.ts` gains `AuditIr*` interfaces faithfully mirroring the
   `AuditIR` JSON shape + `getAuditRun(runId)`.
2. No name collision with the existing `EvidenceContract` block.
3. `npm run format:check` + `lint` + `typecheck` + `build` all green.
4. No `web/app/**` / `src/` change.

## 7. Required output schema (§8.3.9)

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
