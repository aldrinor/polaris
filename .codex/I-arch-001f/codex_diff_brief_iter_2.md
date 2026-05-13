HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings. Don't bank for iter 6 — it doesn't exist.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-arch-001f diff iter 2 — bundleable fixture + unconditional asserts

## Iter-1 P1 addressed

**P1 (continuing iter-1) — bundle 400 cited_span_unreachable_after_snapshot:** the synthetic AuditIR fixture's bibliography statements were 35 chars while sentences cited span 0-100. With no `evidence_pool.json`, `_full_text_for_evidence_id` returned None, so `Source.full_text` was None, so `_snapshot_text` used `snippet` (35 chars), so the 100-char span was unreachable.

### Fix (tests/v6/test_end_to_end_arch_001f.py)

1. **Write evidence_pool.json after manifest patch.** Adds a `sources: [...]` list with `evidence_id` + `full_text` keys; `full_text` is intentionally padded to >100 chars (uses a fixed lorem-style string). The `artifact_to_slice_chain._full_text_for_evidence_id` lookup now finds the long text for both `ev_001` and `ev_002`, span 0-100 is reachable, bundle endpoint returns 200 tar.gz.

2. **Replace `!= 503` with `== 200`.** Per Codex iter-1 P1: drop the guard pattern; assert the explicit success status so any future regression (signer wiring, FK chain, evidence_pool snapshot) blows up loudly.

3. **Drop conditional `if "pool_id" in bundle_manifest:` (Codex iter-1 P2).** `BundleManifest.pool_id` is part of the schema; assert unconditionally.

4. **Drop unused `from pathlib import Path` (Codex iter-1 P3).**

5. **Drop `if bundle_resp.status_code == 200:` guard around tar extraction.** Since step 6 now hard-asserts 200, the guard becomes dead code; extraction runs unconditionally.

## Test result

```
$ python -m pytest tests/v6/test_end_to_end_arch_001f.py -x
1 passed in 1.60s
```

Bundle endpoint now returns 200; tar opens; manifest.yaml + verified_report.json extract; FK chain (`report_id`, `decision_id`, `pool_id`) verifies.

## Direct questions iter 2

1. The 4 iter-1 findings (P1 bundleable fixture, P2 unconditional pool_id, P3 unused Path import, plus the dead-code guard removal) — all addressed; APPROVE'd?
2. PyYAML direct pin to `requirements-v6.txt` deferred — acceptable for iter-2 APPROVE, captured as a separate hygiene PR?
3. Anything else blocking iter-2 APPROVE?

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
