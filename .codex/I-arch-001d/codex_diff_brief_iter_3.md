HARD ITERATION CAP: 5 per document. This is iter 3 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-arch-001d DIFF REVIEW iter 3

Canonical diff SHA: `c29faf9d1e2036c249e57ced708b00141fc5ca13cfccbe9dfd4d7683c2aaf49c`.

## Iter-2 P1-002-novel → resolution

### release_allowed gate at endpoint

Per Codex iter-2: collapsing partial_* into PipelineVerdict='success' erased the release gate. A partial_qwen_advisory with release_allowed=false would download as a clean signed bundle — audit-grade incorrect.

**Resolution**: endpoint reads raw manifest.release_allowed BEFORE invoking build_slice_chain. If False → 422 with bundleable=false + original pipeline_status surfaced.

```python
# bundle.py — added after artifact_dir.is_dir() check, BEFORE build_slice_chain:
manifest_raw = json.loads((artifact_dir / "manifest.json").read_text(encoding="utf-8"))
if not manifest_raw.get("release_allowed", False):
    raise HTTPException(
        status_code=422,
        detail={
            "error": f"run release-blocked: pipeline_status={info.pipeline_status!r}, release_allowed=False. Bundle cannot ship until release gate clears.",
            "bundleable": False,
            "pipeline_status": info.pipeline_status,
        },
    )
```

Partial runs that PASS the release gate (release_allowed=true) still ship. Only release-BLOCKED partials are refused.

NEW test `test_get_bundle_targz_422_when_release_blocked`:
- Synthetic run with status="partial_qwen_advisory" + release_allowed=False
- Asserts 422 + body['bundleable']==False + body['pipeline_status']=='partial_qwen_advisory'

## Smoke

`pytest tests/polaris_v6/api/test_bundle_endpoint_targz.py`: **6/6 pass** (404 missing + 404 not-completed + 422 aborted + 503 unsigned + 422 release-blocked + signer-override-fires).

## Direct questions iter 3

1. release_allowed gate reads raw manifest.release_allowed (not run_store column) — APPROVE'd, or want a run_store column for it?
2. 422 with `pipeline_status` surfaced in body — APPROVE'd?
3. Partial runs WITH release_allowed=true still ship as clean bundles (since slice-chain collapses to "success") — APPROVE'd, or want a different signal in the bundle metadata so consumers can see the original partial_* status?
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
