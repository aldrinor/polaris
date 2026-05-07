# Codex Diff Review — I-f15-005 (ITER 1 of 5)

**HARD ITERATION CAP: 5 per document. This is iter 1 of 5.**
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

**Issue:** I-f15-005 — F15 adversarial: paywalled, 500MB resumable, partial run
**Brief:** APPROVED iter 2 (0/0/0/0)
**Canonical-diff-sha256:** `29b6fd88ff6b9f698acd7b4a6581b19d3396dd5af95556d42440a4a94ae9ef51`
**LOC:** 142 net (under CHARTER §1 200-cap by 58)
**Tests:** 3/3 PASS

## Files

```
tests/polaris_graph/audit_bundle/test_f15_adversarial.py   NEW +142
```

## What changed

- `test_paywalled_source_falls_back_to_snippet`: Source with `full_text=None`, `snippet=PAYWALL_SNIPPET (47 chars)`. Sentence cites `[#ev:src-A:0-47]`. Asserts `sources/src-A.txt` content equals the snippet.
- `test_500mb_per_source_capped`: 5 sources × 250KB full_text + sentences citing each. Asserts each `sources/<id>.txt` ≤ MAX_SOURCE_TEXT_BYTES + 500 (per-source cap with 500-byte buffer for truncation note).
- `test_partial_run_aborts_bundle_build`: All-dropped section + `pipeline_verdict="abort_no_verified_sections"`. Asserts `build_manifest_and_files` raises ValueError matching "verdict".

## Risks for Codex Red-Team

1. **Per-source cap test scoped correctly.** Asserts only `sources/*.txt` files; does NOT assert total bundle bytes (evidence_pool.json contains full_text — out-of-scope per iter-1 P1 resolution).
2. **Paywall fixture realism.** `full_text=None` + `snippet=PAYWALL_SNIPPET` mirrors how the retrieval layer flags paywalled sources at HEAD.
3. **Partial-run assertion uses VerifiedReport's existing validator.** `pipeline_verdict="abort_no_verified_sections"` requires every section dropped (`verified_report.py:155-161`). Test fixture obeys.
4. **Heap cost.** ~1.25MB pre-truncation in test #2. Acceptable per CLAUDE.md §8.4.
5. **§9.4 compliance.** No mocks. No magic numbers. No `try: pass`. No TODO/FIXME.
6. **CHARTER §1 LOC cap.** 142 net. Under 200.
7. **No new package dep.**

## Output schema (mandatory)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

APPROVE iff zero NOVEL P0 + zero continuing P0 + zero P1.
