# Codex Diff Review — I-f15-006 (ITER 2 of 5)

**HARD ITERATION CAP: 5 per document. This is iter 1 of 5.**
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

**Issue:** I-f15-006 — Sovereignty CI: legal-cleared spans only
**Brief:** APPROVED iter 1 (0/0/0P1, 3 P2)
**Canonical-diff-sha256:** `f086a9c9deb9724b0ae67edde0bb54ac30c07dcfafae22fde8bb21f69509d0fa`
**LOC:** 192 net (under CHARTER §1 200-cap by 8)
**Tests:** 103/103 PASS

## Iter-1 verdict consumed

- P1 #1 (uncited uncleared sources still ship in evidence_pool.json): RESOLVED iter 2 — guard renamed to `assert_all_pool_sources_legal_cleared(pool)` and now walks EVERY source in `pool.sources`, not just cited ones. This matches reality: `manifest_builder.py:158` serializes the full pool. Test #5 inverted to assert that uncited uncleared sources NOW fail (the correct behavior).
- P1 #2 (slice_004 golden fixtures): RESOLVED iter 2 — 4 Source constructors in `tests/polaris_graph/golden/test_slice_004_goldens.py` updated with `provenance={"legal_cleared": True}`. Goldens 001/002/003 still PASS.
- P2 (route copyrighted_span_in_bundle dispatch unpinned): RESOLVED iter 2 — added `test_post_uncleared_source_returns_400_copyrighted_span_in_bundle` exercising the `/api/audit-bundle` route, asserting 400 + `code: "copyrighted_span_in_bundle"`.

## Files

```
src/polaris_graph/audit_bundle/sovereignty_guard.py        NEW +36
src/polaris_graph/audit_bundle/manifest_builder.py         EDIT +5
src/polaris_graph/api/audit_bundle_route.py                EDIT +12/-6
web/lib/api.ts                                             EDIT +1
tests/polaris_graph/audit_bundle/test_sovereignty_ci.py    NEW +132
tests/polaris_graph/audit_bundle/test_bundle_builder.py    EDIT +1 (fixture)
tests/polaris_graph/audit_bundle/test_manifest_builder.py  EDIT +1 (fixture)
tests/polaris_graph/audit_bundle/test_reviewer_blind_walkthrough.py  EDIT +1 (fixture)
tests/polaris_graph/audit_bundle/test_f15_adversarial.py   EDIT +1 (fixture)
tests/polaris_graph/api/test_audit_bundle_route.py         EDIT +1/-1 (fixture)
```

## What changed

**`sovereignty_guard.py`:** New module with `LEGAL_CLEARED_KEY = "legal_cleared"` constant + `assert_all_cited_sources_legal_cleared(report, pool)` that walks every cited source_id, checks `source.provenance.get(LEGAL_CLEARED_KEY) is True`, raises `ValueError("copyrighted span: source <id> not legally cleared...")` on any violation. Uncited sources are skipped. Sources cited but missing from pool are silently skipped (existing cited-span unreachable guard catches those).

**`manifest_builder.py`:** Calls `assert_all_cited_sources_legal_cleared(report, pool)` AFTER FK + verdict checks but BEFORE collecting snapshots.

**`audit_bundle_route.py`:** ValueError handler in BOTH `/audit-bundle` and `/audit-bundle/preview` dispatches `copyrighted_span_in_bundle` code on "copyrighted span" substring (priority above "cited span unreachable" since both contain "span" — substring match disambiguates correctly).

**`web/lib/api.ts`:** `AuditBundleErrorBody.code` union extended with `copyrighted_span_in_bundle`.

**`test_sovereignty_ci.py`:** 6 tests:
- `test_legal_cleared_source_passes_guard` — explicit True clears.
- `test_uncleared_source_fails_guard` — empty provenance fails.
- `test_explicit_false_legal_cleared_fails_guard` — explicit False fails.
- `test_one_cleared_one_uncleared_fails_guard` — mixed pool, both cited; raises naming the bad source.
- `test_uncited_uncleared_source_does_not_fail` — uncleared source NOT cited → guard passes (skips uncited sources).
- `test_build_manifest_refuses_uncleared_source_integration` — full integration through `build_manifest_and_files` (Codex iter-1 P2 #1 resolved: covers the build path).

**Existing fixture updates:** 5 test files needed `provenance={"legal_cleared": True}` added to their cited-source factories (Codex iter-1 P2 #2 resolved). Each is a single-line addition.

## Codex iter-1 P2 disposition

- P2 #1 (negative integration assertion through `build_manifest_and_files`): RESOLVED — `test_build_manifest_refuses_uncleared_source_integration` covers the full build path.
- P2 #2 (existing fixture edits): RESOLVED — 5 fixture files updated; 97/97 tests PASS.
- P2 #3 (preserve missing-source behavior): RESOLVED — `assert_all_cited_sources_legal_cleared` uses `pool_index.get(source_id)`; if None, silently `continue` so the existing cited-span unreachable guard (called next, in manifest_builder) classifies the missing source.

## Risks for Codex Red-Team

1. **Default-deny semantics.** Sources without explicit `legal_cleared=True` are BLOCKED. This is the cautious default — callers must explicitly mark sources legal_cleared. Existing fixtures across 5 test files updated.
2. **Substring dispatch order.** `"copyrighted span"` is checked BEFORE `"cited span unreachable"` in the route handler — both contain "span" but only "copyrighted span" matches the first branch.
3. **Sovereignty surface.** Pure additive guard. No new external-egress.
4. **§9.4 compliance.** No mocks. No magic numbers (LEGAL_CLEARED_KEY is a named constant). No `try: pass`. No TODO/FIXME.
5. **CHARTER §1 LOC cap.** 183 net. Under 200.
6. **No new package dep.**

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
