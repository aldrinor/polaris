HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-arch-001d — artifact_to_slice_chain bridge + AuditIR loader extension + verifier-span resolution

GH#466. Days 7-8 critical path. Carries the 3 residuals from I-carney-001 brief v2 iter-5 force-APPROVE.

## Scope

New module `src/polaris_v6/api/artifact_to_slice_chain.py` that converts a pipeline-A canonical artifact dir into the slice-chain Pydantic shape (`ScopeDecision`, `EvidencePool`, `VerifiedReport`) that `/api/audit-bundle` POST and the new GET `/runs/{run_id}/bundle.tar.gz` expect.

Plus extending `src/polaris_v6/api/bundle.py` to surface a GET `/runs/{run_id}/bundle.tar.gz` endpoint that:
1. Resolves run_id → artifact_dir via run_store
2. Calls `build_slice_chain(artifact_dir)` → (ScopeDecision, EvidencePool, VerifiedReport)
3. Builds the signed audit-bundle through existing `audit_bundle_route.post_audit_bundle` path

## 3 carried residuals (from I-carney-001 brief_v2 iter-5 force-APPROVE)

### Residual 1 — Verifier-span text → Source.full_text for legal-cleared sources

Per Codex iter-5 P1 of brief_v2: cited spans in `verification_details.json` reference offsets like 9300-9800. If `Source.full_text` is None or just the short bibliography statement, `build_manifest_and_files` rejects the cited spans (out of bounds). Need to populate Source.full_text from `evidence_pool.json` (which has the actual fetched body text per evidence_id) for legal-cleared sources.

### Residual 2 — Pydantic Literal validity

Per Codex iter-5: `ScopeStatus`/`ScopeClassValue`/`PipelineVerdict` are Literal aliases, not enums. Verified at `scope_decision.py:34-50`:
- `ScopeStatus = Literal["in_scope", "out_of_scope", "ambiguous_needs_clarification", "refused"]`
- `ScopeClassValue = Literal["clinical_efficacy", "clinical_safety", "clinical_diagnosis", "clinical_prognosis", "out_of_scope", "uncertain"]`

Bridge MUST use literal string values (NOT `ScopeStatus.IN_SCOPE`-style enum access). For completed runs from pipeline-A: status = `"in_scope"`. scope_class derivation: derive from `manifest.scope.classification` if present, else map from template_id (e.g., clinical templates → `"clinical_efficacy"`; non-clinical → `"uncertain"` since the Literal doesn't admit policy classes).

### Residual 3 — VerifiedReport required fields

Per Codex iter-5: `VerifiedReport` requires `verifier_pass_threshold`, `started_at_utc`, `finished_at_utc`, `latency_ms`, `cost_usd`. Verified at `verified_report.py:442-446`. Bridge derives:
- `verifier_pass_threshold` = 0.4 (default per POLARIS §9.2 strict_verify per-section threshold) OR read from manifest if pipeline-A wrote it
- `started_at_utc` / `finished_at_utc` / `latency_ms` = read from raw `manifest.json` retrieval block (which loader doesn't expose) or compute from run lifecycle timestamps
- `cost_usd` = manifest.cost_usd (exposed via loader.RunManifest)

## Files I have ALSO checked clean (§-1.2 #2)

- `src/polaris_graph/audit_ir/loader.py:44-52` — `BibliographyEntry` has num/evidence_id/statement/tier/url ONLY (per Codex iter-4 finding)
- `src/polaris_graph/audit_ir/loader.py:376-396` — `RunManifest` lacks scope/retrieval start-finish fields (loader needs extension OR bridge reads raw manifest.json)
- `src/polaris_graph/audit_ir/loader.py:961-1008` — `load_audit_ir` signature; AuditIR exposes bibliography as `tuple[BibliographyEntry, ...]`, NOT `.entries`
- `src/polaris_graph/audit_bundle/sovereignty_guard.py:17-26` — `assert_all_pool_sources_legal_cleared` iterates pool.sources; every source needs `provenance.legal_cleared = True`
- `src/polaris_graph/audit_bundle/manifest_builder.py:163` (Codex iter-5 reference) — validates cited token spans against Source.full_text length
- `src/polaris_graph/retrieval2/evidence_pool.py:54-100` — `Source` model: source_id, url (HttpUrl), domain, tier, title, publication_date, authors, snippet, full_text_available, full_text, fetched_at_utc, provenance (dict), retracted
- `src/polaris_graph/retrieval2/evidence_pool.py:101-130` — `AdequacyVerdict` model (is_adequate, failure_reason, adequacy_score)
- `src/polaris_graph/retrieval2/evidence_pool.py:131-180` — `EvidencePool` model: pool_id, decision_id, sources, adequacy, queries_executed, retrieval_started_at_utc, retrieval_finished_at_utc, latency_ms, cost_usd
- `src/polaris_graph/generator2/verified_report.py:71-100` — `VerifiedSentence` model (claim_id, section, text, tokens, verifier_pass, etc.)
- `src/polaris_graph/generator2/verified_report.py:386-405` — `Section` model (section_id, section_title, verified_sentences, section_verify_pass_rate, section_status)
- `src/polaris_graph/generator2/verified_report.py:410-456` — `VerifiedReport` model with the 5 required additional fields
- `src/polaris_v6/api/bundle.py:39-40` — current GET /runs/{run_id}/bundle returns EvidenceContract (placeholder)

## Acceptance criteria

1. NEW module `src/polaris_v6/api/artifact_to_slice_chain.py`:
   - `build_slice_chain(artifact_dir: Path) -> tuple[ScopeDecision, EvidencePool, VerifiedReport]`
   - Reads via `load_audit_ir(artifact_dir)` + direct `json.loads((artifact_dir / "manifest.json").read_text())` for fields loader doesn't expose
   - Reads `evidence_pool.json` for full_text per evidence_id (legal-cleared filter)
   - Returns 3 Pydantic models with valid Literal values + all required fields
2. NEW endpoint GET `/runs/{run_id}/bundle.tar.gz` in `bundle.py`:
   - Resolve run_id → artifact_dir via run_store
   - 404 if run not found or lifecycle_status != completed
   - Call build_slice_chain → AuditBundleRequest → existing post_audit_bundle returns signed tar.gz
3. Sovereignty filter: non-legal-cleared sources excluded from pool.sources entirely (per sovereignty_guard.py:17-26 contract)
4. Tests:
   - 1 happy-path: synthetic AuditIR-shape fixture artifact dir → build_slice_chain → 3 Pydantic models valid
   - 1 cited-span integrity: Source.full_text long enough that cited token spans (offsets > 1000) resolve in-bounds
   - 1 sovereignty: non-cleared sources excluded from output pool
   - 1 endpoint: GET /runs/{uuid}/bundle.tar.gz returns 200 with content-type application/gzip when run completed
   - 1 endpoint: 404 when run_id missing OR not yet completed
5. LOC budget: ~280 (bridge ~150 + endpoint ~30 + tests ~100)

## Direct questions iter 1

1. Bridge reads manifest.json directly for fields AuditIR loader doesn't expose (no loader extension this Issue; deferred to follow-up if needed) — APPROVE'd?
2. `ScopeStatus="in_scope"` + `scope_class` derived from template_id (clinical → "clinical_efficacy"; non-clinical → "uncertain") — APPROVE'd?
3. Defaults for missing fields: `verifier_pass_threshold=0.4` (POLARIS §9.2), retrieval timestamps from manifest if present else `decided_at_utc` — APPROVE'd, or want stricter (fail loud if any field missing)?
4. Source.full_text loaded from evidence_pool.json keyed by evidence_id — APPROVE'd?
5. Non-cleared sources EXCLUDED from pool.sources (not just flagged) — APPROVE'd?
6. New endpoint `GET /runs/{run_id}/bundle.tar.gz` placement in bundle.py (replacing or alongside existing placeholder?) — APPROVE'd?
7. Anything else blocking iter-1 APPROVE?

## Resource discipline

No pipeline-A real runs; pure code + fixture tests. One codex exec at a time per §8.4.

## Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
p3_cosmetic: [...]
convergence_call: continue | accept_remaining
remaining_blockers: [...]
```
