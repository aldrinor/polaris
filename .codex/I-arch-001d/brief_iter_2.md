HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-arch-001d iter 2 — 4 P1s resolved

## P1-001 — Sovereignty cascade through cited tokens

**Code-verified**: `VerifiedSentence.tokens` (`verified_report.py:71-95`) carries `EvidenceSpanToken(evidence_id, start, end)`. If a token's evidence_id is excluded from pool.sources, `build_manifest_and_files` rejects the bundle.

**Resolution** (drop + recompute, NOT fail-loud — completed runs should bundle gracefully):

```python
# After excluding non-cleared sources from pool.sources:
cleared_evidence_ids = {s.source_id for s in cleared_sources}

# Filter each section's verified_sentences: drop sentences whose tokens
# cite any excluded source. Recompute section_verify_pass_rate.
for section_idx, section in enumerate(sections):
    kept = []
    for sent in section.verified_sentences:
        all_tokens_cleared = all(
            t.evidence_id in cleared_evidence_ids for t in sent.tokens
        )
        if all_tokens_cleared:
            kept.append(sent)
        else:
            # Mark as dropped with drop_reason — VerifiedSentence accepts
            # verifier_pass=False + drop_reason. Use "no_provenance_token"
            # (closest legal Literal) and tag provenance.
            kept.append(sent.model_copy(update={
                "verifier_pass": False,
                "drop_reason": "no_provenance_token",
            }))
    # Recompute section pass rate.
    pass_count = sum(1 for s in kept if s.verifier_pass)
    new_section = section.model_copy(update={
        "verified_sentences": kept,
        "section_verify_pass_rate": pass_count / max(len(kept), 1),
    })
    sections[section_idx] = new_section

# Recompute overall_verify_pass_rate at report level
overall = sum(s.section_verify_pass_rate for s in sections) / max(len(sections), 1)
```

If recomputed `overall_verify_pass_rate < verifier_pass_threshold`, the resulting report still satisfies `pipeline_verdict='success'` only if at least one non-dropped section remains. If no non-dropped sections remain after sovereignty filter, the bridge raises `SovereigntyFilterEmptiedReportError` and the GET endpoint returns **422 Unprocessable Entity** with `{"error": "report fully redacted by sovereignty filter; bundle cannot be assembled"}`.

## P1-002 — SourceTier normalization

**Code-verified**: `evidence_pool.SourceTier` is `Literal["T1", "T2", "T3"]` (Enum). Pipeline-A bibliography may write T4/T5/T6/T7/UNKNOWN.

**Resolution**: normalization map in bridge:

```python
def _normalize_tier(raw: str) -> tuple["SourceTier", str]:
    """Map pipeline-A tier label to slice-002 SourceTier.

    Returns (canonical_tier, raw_tier_for_provenance).
    """
    raw_upper = (raw or "").upper().strip()
    if raw_upper in ("T1", "T2", "T3"):
        return raw_upper, raw_upper
    # T4+/UNKNOWN/missing → T3 (lowest tier) with raw kept for transparency
    return "T3", raw_upper or "UNKNOWN"

# In source construction:
canonical_tier, raw_tier = _normalize_tier(entry.tier)
source = Source(
    ...,
    tier=canonical_tier,
    provenance={
        "legal_cleared": True,
        "raw_tier": raw_tier,  # pipeline-A original; transparency for auditor
    },
)
```

## P1-003 — DropReason normalization

**Code-verified**: `DropReason = Literal["numeric_mismatch", "overlap_too_low", "no_provenance_token", "entailment_failed"]` per `verified_report.py:57-62`.

**Resolution**: bridge ONLY emits sentences from pipeline-A's `verification_details.json` that ALREADY have a constrained drop_reason (or no drop_reason for verified_pass=True). For pipeline-A's verification_details.json structure: each verified entry has either:
- `verifier_pass: true` + no drop_reason
- `verifier_pass: false` + a drop_reason string

Map pipeline-A drop reason strings to the Literal:
```python
_DROP_REASON_MAP = {
    "numeric_mismatch": "numeric_mismatch",
    "number_not_in_any_cited_span": "numeric_mismatch",
    "overlap_too_low": "overlap_too_low",
    "low_content_overlap": "overlap_too_low",
    "no_provenance_token": "no_provenance_token",
    "missing_provenance": "no_provenance_token",
    "entailment_failed": "entailment_failed",
}
# Default: any unrecognized reason → "no_provenance_token" (audit-grade
# conservatism — when we can't classify, mark as missing-provenance).
def _normalize_drop_reason(raw: str | None) -> str | None:
    if raw is None:
        return None
    base = raw.split(":")[0].strip().lower()  # "entailment_failed:semantic" → "entailment_failed"
    return _DROP_REASON_MAP.get(base, "no_provenance_token")
```

## P1-004 — FastAPI Depends injection on GET

**Resolution**: declare `sign_fn = Depends(get_sign_fn)` on the GET route and pass explicitly:

```python
# src/polaris_v6/api/bundle.py
from polaris_graph.api.audit_bundle_route import get_sign_fn, post_audit_bundle, AuditBundleRequest

@router.get("/{run_id}/bundle.tar.gz")
def get_run_bundle(
    run_id: str,
    sign_fn = Depends(get_sign_fn),
):
    info = run_store.get_run(run_id)
    if info is None:
        raise HTTPException(404, detail={"error": "run not found"})
    if info.lifecycle_status != "completed":
        raise HTTPException(404, detail={"error": f"run not completed: {info.lifecycle_status}"})
    if info.pipeline_status and info.pipeline_status.startswith("abort_"):
        raise HTTPException(422, detail={"error": f"run aborted: {info.pipeline_status}", "bundleable": False})
    if not info.artifact_dir:
        raise HTTPException(404, detail={"error": "run has no artifact_dir recorded"})

    try:
        decision, pool, report = build_slice_chain(Path(info.artifact_dir))
    except SovereigntyFilterEmptiedReportError as exc:
        raise HTTPException(422, detail={"error": str(exc)}) from exc
    except FileNotFoundError as exc:
        raise HTTPException(404, detail={"error": f"artifact_dir incomplete: {exc}"}) from exc

    return post_audit_bundle(
        AuditBundleRequest(decision=decision, pool=pool, report=report),
        sign_fn=sign_fn,
    )
```

## P2 acknowledged (no changes from iter 1 stance)

- **Q2 caveat**: bridge reads manifest.domain (always present) when template_id missing; maps clinical/clinical_* → "clinical_efficacy", anything else → "uncertain"
- **Q3 timestamp fallback**: prefer `manifest.protocol_sha256` block / `manifest.retrieval.*_at` keys when present; else parse from run_store row `started_at` + `finished_at`; absolute-last-resort `decided_at_utc` for both timestamps + `latency_ms=0`
- **Abort/missing handling**: explicit 404 + 422 paths (see P1-004 endpoint code)

## P3 cosmetic resolution

```python
# Import aliases to disambiguate the two VerifiedReport classes
from polaris_graph.audit_ir.loader import (
    AuditIR,
    VerifiedReport as AuditIRVerifiedReport,
    load_audit_ir,
)
from polaris_graph.generator2.verified_report import (
    VerifiedReport as SliceChainVerifiedReport,
    Section,
    VerifiedSentence,
    DropReason,
    PipelineVerdict,
)
```

## Updated acceptance criteria

1. `build_slice_chain(artifact_dir) -> (ScopeDecision, EvidencePool, SliceChainVerifiedReport)` with:
   - Sovereignty cascade through tokens (P1-001)
   - Tier normalization with raw_tier in provenance (P1-002)
   - Drop reason normalization (P1-003)
   - Manifest.json fields read directly for retrieval timestamps + decision_id + models
2. New `SovereigntyFilterEmptiedReportError` raised when cleared-sources cascade leaves no non-dropped sections
3. GET `/runs/{run_id}/bundle.tar.gz` endpoint with proper `Depends(get_sign_fn)` + explicit 404/422 paths for not-found / aborted / empty-after-sovereignty
4. Tests (5+):
   - happy path: synthetic AuditIR fixture → 3 valid Pydantic models
   - cited-span integrity (Source.full_text resolves token offsets)
   - sovereignty cascade (non-cleared excluded + cited sentences marked dropped + section rates recomputed)
   - tier normalization (T4 input → T3 canonical + raw_tier="T4")
   - drop_reason normalization (pipeline-A freeform → Literal)
   - endpoint 404 (run missing / not completed)
   - endpoint 422 (run aborted / sovereignty-emptied)
   - endpoint 200 (run completed → signed tar.gz)
5. LOC budget ~350 (bridge ~200 + endpoint ~50 + tests ~150)

## Direct questions iter 2

1. Sovereignty cascade pattern (drop sentences citing excluded sources, recompute pass rates) — APPROVE'd?
2. SourceTier normalization map (T4+/UNKNOWN → T3 + raw_tier provenance) — APPROVE'd?
3. DropReason normalization map (4 canonical + default "no_provenance_token") — APPROVE'd?
4. SovereigntyFilterEmptiedReportError → 422 — APPROVE'd?
5. abort_* → 422 (not 404, since the run completed lifecycle but pipeline aborted gracefully) — APPROVE'd?
6. Anything else blocking iter-2 APPROVE?

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
