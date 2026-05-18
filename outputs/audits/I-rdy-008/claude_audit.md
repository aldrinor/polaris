# Claude architect audit — I-rdy-008 (#504) slice 2

**Issue:** GH #504 (I-rdy-008) — Phase 3.5: wire live runs into the rich UI.
**Slice 2 of ~12** (Codex arch-decision consult, verdict A). Slice 1 (the v6
backend route) merged via PR #590. #504 closes when the last slice lands.
**Branch:** `bot/I-rdy-008-slice2` off `polaris` HEAD `4917e02d`.
**Commit 1:** `e6a7134a` — 1 file, `web/lib/api.ts` +240.
**Brief:** `.codex/I-rdy-008/brief.md` — Codex APPROVE iter 1 (clean).

## 1. What shipped

`web/lib/api.ts` gains the live-run AuditIR client — frontend-lib only, no
`web/app/**` change:
- **17 `AuditIr*` interfaces** mirroring the `to_json_dict()` projection of the
  `AuditIR` dataclass tree (`src/polaris_graph/audit_ir/loader.py`):
  `AuditIrRun` (top-level) + `AuditIrManifest`/`AuditIrEvaluatorGate`/
  `AuditIrRetrievalStats`, `AuditIrBibliographyEntry`,
  `AuditIrVerifiedReport`/`AuditIrSection`/`AuditIrSentence`/
  `AuditIrEvidenceSpanToken`, `AuditIrContradictionCluster`/`AuditIrContradictionClaim`,
  `AuditIrFrameCoverageReport`/`AuditIrFrameCoverageEntry`/`AuditIrRetrievalAttempt`,
  `AuditIrTierMix`, `AuditIrModelProvenance`/`AuditIrRuleCheck`,
  `AuditIrProtocolMetadata`/`AuditIrTierExpectation`, `AuditIrAdequacyGate`,
  `AuditIrCorpusApprovalGate`.
- **`getAuditRun(runId)`** → `GET ${BACKEND_URL}/api/inspector/runs/{run_id}`
  (the slice-1 route) → `asJsonOrThrow<AuditIrRun>`.

## 2. Per-finding verification

- **VERIFIED — faithful shape, no coercion:** the TS interfaces mirror the
  loader dataclasses 1:1 — raw `tier: string` (not a `T1|T2|T3` union),
  `tokens: AuditIrEvidenceSpanToken[]` keeps the range-keyed
  `evidence_id+start+end` spans. This is the Option-A faithfulness that B's
  `EvidenceContract` could not carry.
- **VERIFIED — nullable optionals:** `model_provenance` / `protocol` /
  `adequacy` / `corpus_approval` are `... | null` (the loader returns `None`
  for legacy/abort artifacts); `retrieval_stats`, `doi`, `pmid`,
  `failure_reason`, `human_curated_provenance`, `semantics_warning`,
  `http_status` are nullable per the dataclass field types.
- **VERIFIED — no name collision:** every new symbol is `AuditIr*`-prefixed;
  the existing `EvidenceContract` / `SourceSpan` / `VerifiedSentence` /
  `getBundle()` block is untouched (slice 3 migrates the UI off it).
- **VERIFIED — pattern-consistent:** `getAuditRun` follows the existing
  `getRun`/`getBundle`/`getChart` shape (`authFetch` + `asJsonOrThrow<T>`);
  `BACKEND_URL` (`/api/v6`) + the v6 route prefix (`/api/inspector`) compose
  to the correct path; `runId` is `encodeURIComponent`-escaped.
- **VERIFIED — scope:** no `web/app/**`, no `src/` change. `getAuditReportMarkdown`
  / `getAuditHealth` / bundle helpers deferred — their v6 facade routes are
  not built yet (slice 1 built only `/api/inspector/runs/{run_id}`).

## 3. Smoke

`web/` change → the `lint + format + typecheck + build` CI job is in scope.
Offline (all in `web/`): `npx prettier --check lib/api.ts` → clean;
`npm run typecheck` (`tsc --noEmit`) → no errors; `npm run lint` → 0 errors
(3 pre-existing warnings in `inspector/[runId]/page.tsx` + a frame-coverage
e2e spec — NOT in `lib/api.ts`); `npm run build` → OK.

## 4. Codex iteration trail

- **Brief iter 1 APPROVE** — clean, 0 P0/P1/P2.

## 5. Scope + residuals

Slice 2 = the typed client. The inspector frontend page rewrite to call
`getAuditRun()` instead of `getBundle()` is slice 3; the other surfaces are
slices 4-12. #504 stays open.

## 6. Verdict

Faithful to the APPROVE'd brief; the AuditIR TS shape mirrors the loader
dataclass tree exactly; no collision with the legacy `EvidenceContract`
block; web smoke (format/typecheck/lint/build) all green. Ready for Codex
diff review.
