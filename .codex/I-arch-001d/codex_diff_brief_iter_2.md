HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-arch-001d DIFF REVIEW iter 2

Canonical diff SHA: `3972aef4bb8d731921113ce3316d45d7ac218793fbf0b85e477deef9a06f2193`.

## Iter-1 findings → resolutions

### P1-001 — Depends(get_sign_fn) callable identity

**Resolution**: import `get_sign_fn` at module top in `bundle.py` and use `Depends(get_sign_fn)` directly. The lambda + `_resolve_sign_fn()` helper is removed. `create_app()` registers `app.dependency_overrides[get_sign_fn]`; that override now fires when the route resolves `Depends(get_sign_fn)` because both reference the same callable.

### P2-001 — partial_* PipelineVerdict mapping

**Resolution**: pipeline-A's `partial_*` statuses (partial_outline_fallback / partial_qwen_advisory / partial_thin_corpus / partial_incomplete_corpus / partial_rule_check_warnings) get mapped to `PipelineVerdict="success"` instead of `abort_no_verified_sections`. Rationale: partial runs DID produce kept content; the degradation is recorded on the manifest, not the verdict. Previously these would raise ValidationError because `pipeline_verdict='abort_no_verified_sections'` forbids non-dropped sections.

### P2-002 — Endpoint test coverage

**Resolution**: NEW `tests/polaris_v6/api/test_bundle_endpoint_targz.py` with 5 tests:
- 404 when run missing
- 404 when lifecycle_status != completed (queued)
- 422 when pipeline_status starts with `abort_`
- 503 when signer unconfigured (proves the bridge ran and `Depends(get_sign_fn)` wired properly — would be 500 if the bridge crashed first)
- Non-503 when signer override registered via `app.dependency_overrides[get_sign_fn]` — explicit regression catch for the iter-1 P1-001

## Smoke

`pytest tests/polaris_v6/api/`: **49/49 pass** (22 bridge tests + 5 endpoint tests + 22 pre-existing upload tests).

## Direct questions iter 2

1. Top-of-module `get_sign_fn` import + `Depends(get_sign_fn)` direct call — APPROVE'd?
2. partial_* → "success" PipelineVerdict mapping (degradation goes on manifest, not verdict) — APPROVE'd?
3. Signer-override regression test (asserts status != 503 when override registered) — APPROVE'd as the P1-001 catch?
4. Any P0/P1?

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
