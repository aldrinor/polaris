# Codex Diff Review — I-f15-004 (ITER 1 of 5)

**HARD ITERATION CAP: 5 per document. This is iter 1 of 5.**
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

**Issue:** I-f15-004 — Standalone-verifiable test (reviewer-blind walkthrough)
**Brief:** APPROVED iter 5 (0/0/0P1, 1 P2 cosmetic; cap-hit but no remaining blockers)
**Canonical-diff-sha256:** `1f1e16e5827a59080715707a09580ed6d7e8a7ed760c012a111b39354b4a6dd6`
**LOC:** 303 net (103 over CHARTER §1 200-cap; LOC exemption requested below)
**Tests:** 28/28 PASS (4 new + 24 neighboring kept passing).

## Files

```
src/polaris_graph/audit_bundle/snapshot_sources.py   EDIT +42
src/polaris_graph/audit_bundle/manifest_builder.py   EDIT +58/-13
src/polaris_graph/audit_bundle/REVIEWER_README.md    NEW +42
src/polaris_graph/api/audit_bundle_route.py          EDIT +24
web/lib/api.ts                                       EDIT +1
tests/polaris_graph/audit_bundle/test_reviewer_blind_walkthrough.py  NEW +162
```

## What changed

**`snapshot_sources.py`:** Added `SnapshotEntry(NamedTuple): text, reachable_chars` + `_snapshot_entry()` + `snapshot_sources_with_reachable(report, pool) -> dict[str, SnapshotEntry]`. Existing `snapshot_sources()` returning `dict[str, str]` UNCHANGED — existing test_snapshot_sources.py 11/11 still PASS.

**`manifest_builder.py`:** Added `FILE_REVIEWER_README` constant. Switched bundle path to `snapshot_sources_with_reachable`. New `_assert_cited_spans_reachable(report, snapshots)` walks every kept verified sentence's tokens (UNION of `extract_tokens(sentence_text)` + `extract_tokens(t) for t in provenance_tokens`, deduped by `token.raw`); raises `ValueError("cited span unreachable...")` for missing source_id OR `span_end > entry.reachable_chars`. README bytes read from `Path(__file__).parent / "REVIEWER_README.md"` and included in files dict.

**`audit_bundle_route.py`:** ValueError handler in BOTH `/audit-bundle` and `/audit-bundle/preview` dispatches `cited_span_unreachable_after_snapshot` code on "cited span unreachable" substring. AuditBundleErrorResponse code Literal docstring extended.

**`web/lib/api.ts`:** `AuditBundleErrorBody.code` union extended with `cited_span_unreachable_after_snapshot`.

**`REVIEWER_README.md`:** Plain-language reviewer guide — file layout, GPG verification, SHA256 verification, random-claim audit procedure (CHARACTER offsets explicit), truncation note explanation, sovereignty note.

**`test_reviewer_blind_walkthrough.py`:** 4 tests — happy-path + 3 fail paths (truncation boundary using `MAX_SOURCE_TEXT_BYTES + 100 = 204_900`, token only in sentence_text, missing source).

## LOC exemption requested

CHARTER §1 200-cap exceeded by 103. Brief author requests exemption analogous to I-f15-003 (381), I-f3-007 (230). Drivers:
- Test file is 162 LOC because it covers 4 distinct paths + builds full Pydantic fixture chains (cannot use bundle_builder fixture without code-sharing helpers; one-off here is correct).
- manifest_builder gained 58 LOC for the cited-span guard + REVIEWER_README inclusion + snapshot dual-API switch — the guard is the binding "ship-or-fail-loudly" deliverable.
- snapshot_sources gained 42 LOC for the SnapshotEntry refactor that backward-compat preserves existing callers.

Splitting candidates considered:
1. Drop fail-paths #2 + #3 to a follow-up I-f15-004a → drops 35 LOC, lands at 268. Loss: less coverage of the "token in sentence_text" guard path (the surface most likely to regress).
2. Drop the 3rd fail-path test only → 285 LOC.
3. Inline REVIEWER_README into a Python string constant inside manifest_builder → drops the .md file (-42) but loses standalone reviewability.

Brief author prefers exemption since the binding work is one coherent change (cited-span guard + reviewer doc + walkthrough test); splitting creates non-functional interim states.

## Risks for Codex Red-Team

1. **Cited-span guard correctness.** Iter 5 brief P2-only (1 cosmetic). Tested against real fail paths (truncation boundary @ 204900, token-only-in-sentence-text, missing source). All 4 tests PASS.

2. **`snapshot_sources()` backward-compat.** Existing 11 tests pass against the unchanged `dict[str, str]` API.

3. **REVIEWER_README delivery.** Read from `Path(__file__).parent / "REVIEWER_README.md"` at bundle-build time. importlib.resources path would be more portable for installed wheels — out of scope per breakdown.

4. **API error mapping.** Both `/audit-bundle` (download) and `/audit-bundle/preview` ValueError handlers dispatch on "cited span unreachable" substring.

5. **§9.4 compliance.** No mocks (`unittest.mock` not used); no magic numbers (`MAX_SOURCE_TEXT_BYTES + 100` derives from constant); no `try: pass`; no TODO/FIXME.

6. **Sovereignty surface.** No new external-egress.

7. **Fixture realism.** `_decision`, `_pool`, `_report` factories construct minimum-valid Pydantic chains — same shape as `tests/polaris_graph/audit_bundle/test_bundle_builder.py` fixtures.

8. **CHARTER §1 LOC cap.** 303 net. Exemption requested.

9. **No new package dep.**

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
