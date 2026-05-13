# Claude architect audit — I-arch-001d

**Canonical PR diff SHA256:** `c29faf9d1e2036c249e57ced708b00141fc5ca13cfccbe9dfd4d7683c2aaf49c`

## Acceptance criteria

| Criterion | Status |
|---|---|
| `build_slice_chain(artifact_dir) → 3 valid Pydantic models` | ✓ |
| Sovereignty cascade through cited tokens | ✓ |
| Sentences rebuilt via constructor (validators), NOT `model_copy` | ✓ |
| `evaluator_agrees=False` when `verifier_pass=False` | ✓ |
| `section_status="dropped"` when no passing sentences | ✓ |
| `SovereigntyFilterEmptiedReportError` → 422 | ✓ |
| `SourceTier` normalization (T4+/UNKNOWN → T3 + raw_tier) | ✓ |
| `DropReason` normalization (10 pipeline-A → 6 Literal + default) | ✓ |
| Canonical `PROVENANCE_TOKEN_RE` import with fallback | ✓ |
| `Depends(get_sign_fn)` direct (matches `app.dependency_overrides` key) | ✓ |
| 404/422/503 status codes | ✓ |
| `release_allowed=False` gate (refuses release-blocked partials) | ✓ |
| Partial_* PipelineVerdict mapping | ✓ |
| Tests: 27 new, all pass | ✓ |

## Codex review trail

| Iter | Verdict | Findings |
|---|---|---|
| Brief 1 | REQUEST_CHANGES | 4 P1s (sovereignty cascade tokens / SourceTier norm / DropReason norm / Depends shape) |
| Brief 2 | REQUEST_CHANGES | P1-001-continuing (section_status recomputation) + 2 P2 nudges |
| Brief 3 | REQUEST_CHANGES | P1-002-novel (model_copy validator bypass + evaluator_agrees consistency) |
| Brief 4 | **APPROVE** | zero findings |
| Diff 1 | REQUEST_CHANGES | P1-001 (lambda Depends breaks override) + 2 P2 (partial_* mapping, endpoint test coverage) |
| Diff 2 | REQUEST_CHANGES | P1-002-novel (release_allowed gate erased by partial_* collapse) |
| Diff 3 | **APPROVE** | zero findings + 1 P2 (optional original_pipeline_status in bundle metadata) |

## Force-APPROVE iter-5 residuals from umbrella brief v2 — CLOSED

| Residual | Status | Implementation |
|---|---|---|
| Verifier-span text → `Source.full_text` for legal-cleared sources | ✓ | `_full_text_for_evidence_id` reads evidence_pool.json |
| Pydantic Literal validity (ScopeStatus/ScopeClassValue/PipelineVerdict) | ✓ | `_derive_scope_class` + `"in_scope"` literal + partial_* mapping |
| VerifiedReport required fields (verifier_pass_threshold etc.) | ✓ | report constructor includes all 5 required fields |

All 3 residuals from I-carney-001 brief v2 iter-5 force-APPROVE are now closed in I-arch-001d.

## Smoke

- 22 bridge tests pass
- 6 endpoint tests pass
- 49 total in tests/polaris_v6/api/
- 448 pre-existing tests/polaris_v6 + tests/v6 pass (zero regressions in earlier check)

## Verdict

SHIP.
