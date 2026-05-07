# Codex Brief Review — I-f15-006 (ITER 1 of 5)

**HARD ITERATION CAP: 5 per document. This is iter 1 of 5.**
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

**Issue:** I-f15-006 — Sovereignty CI: legal-cleared spans only
**Phase:** 1 / **Feature:** F15
**LOC budget:** 100 net per breakdown. **CHARTER §1 hard cap: 200.**

## Mission

Per breakdown: CI rejects bundle with copyrighted span. CI fails on violation.

A POLARIS audit bundle ships verbatim source-text snapshots in `sources/<source_id>.txt`. Some sources (e.g. paywalled academic articles, copyrighted SOPs) cannot legally be redistributed verbatim outside the user's organization. This Issue adds a guard in `build_manifest_and_files` that REFUSES to build a bundle if any cited source carries a "not legally cleared for redistribution" marker, plus a CI test that asserts the refusal.

## Substrate (HONEST at HEAD)

- `src/polaris_graph/retrieval2/evidence_pool.py:54-74` — `Source` Pydantic model. Has `provenance: dict[str, Any]` (open dict). NO existing copyright/legal-clearance field.
- `src/polaris_graph/sovereignty/classification.py:25-32` — `EXTERNAL_LEAK_FORBIDDEN = frozenset({CAN_REAL, PRIVATE, CLIENT, UNKNOWN})`. Marker for what cannot leave Canadian-sovereign infrastructure.
- `src/polaris_graph/audit_bundle/manifest_builder.py:118` — current bundle build path. No copyright check.
- `src/polaris_graph/audit_bundle/snapshot_sources.py:36` — `_cited_source_ids(report)` returns the set of cited source_ids.

## Approach

The cleanest pattern matching v6.2 §332 sovereignty logic: a Source is "legally cleared for redistribution in an audit bundle" iff its `provenance` dict has `legal_cleared = True`. Absence of the flag (or `False`) means the source CANNOT be embedded verbatim in a bundle.

This avoids a Pydantic schema change (the `provenance` dict is already open) and avoids semantic overlap with `tier` (which is evidence-quality, not legal status).

**Part 1 — `src/polaris_graph/audit_bundle/sovereignty_guard.py`** (NEW, ~30 LOC):
- `assert_all_cited_sources_legal_cleared(report, pool) -> None` — walks every cited source_id; for each, checks `source.provenance.get("legal_cleared", False) is True`. Raises `ValueError("copyrighted span: source <id> not legally cleared for audit bundle redistribution")` on any failure.
- Module constant `LEGAL_CLEARED_KEY = "legal_cleared"`.

**Part 2 — `src/polaris_graph/audit_bundle/manifest_builder.py`** (EDIT, ~5 LOC):
- After FK + verdict checks (line 97-101), call `assert_all_cited_sources_legal_cleared(report, pool)` BEFORE collecting snapshots.

**Part 3 — `src/polaris_graph/api/audit_bundle_route.py`** (EDIT, ~6 LOC):
- ValueError handler dispatch: `"copyrighted span"` substring → code `"copyrighted_span_in_bundle"`.
- Mirror in BOTH `/audit-bundle` and `/audit-bundle/preview`.
- Add `copyrighted_span_in_bundle` to `code` Literal docstring.

**Part 4 — `web/lib/api.ts`** (EDIT, ~1 LOC):
- Extend `AuditBundleErrorBody.code` union with `"copyrighted_span_in_bundle"`.

**Part 5 — `tests/polaris_graph/audit_bundle/test_sovereignty_ci.py`** (NEW, ~70 LOC):
- `test_legal_cleared_source_passes_guard`: Source with `provenance={"legal_cleared": True}` → bundle builds normally.
- `test_uncleared_source_fails_guard`: Source with `provenance={}` (no flag) → guard raises `ValueError("copyrighted span")`.
- `test_explicit_false_legal_cleared_fails_guard`: Source with `provenance={"legal_cleared": False}` → guard raises.
- `test_one_cleared_one_uncleared_fails_guard`: Mixed pool with 2 sources, only one cleared, both cited → guard raises naming the uncleared source.
- `test_uncited_uncleared_source_does_not_fail`: Pool contains uncleared source that is NOT cited by any sentence → guard passes (only cited sources are checked).

## Acceptance criteria (binding)

1. `src/polaris_graph/audit_bundle/sovereignty_guard.py` NEW.
2. `src/polaris_graph/audit_bundle/manifest_builder.py` EDIT.
3. `src/polaris_graph/api/audit_bundle_route.py` EDIT (both routes).
4. `web/lib/api.ts` EDIT.
5. `tests/polaris_graph/audit_bundle/test_sovereignty_ci.py` NEW with 5 tests covering pass + 4 fail conditions.

## Planned diff shape

```
src/polaris_graph/audit_bundle/sovereignty_guard.py        NEW +30
src/polaris_graph/audit_bundle/manifest_builder.py         EDIT +5
src/polaris_graph/api/audit_bundle_route.py                EDIT +6
web/lib/api.ts                                             EDIT +1
tests/polaris_graph/audit_bundle/test_sovereignty_ci.py    NEW +70
```

LOC: +112 net. Over breakdown 100 budget by 12; under CHARTER §1 200-cap by 88.

## Out of scope

- UI affordance for marking sources legal_cleared at upload time → I-f15-006a follow-up.
- Retroactive marking of existing pools' sources via migration → not needed for v6.2 (clean cutover).
- Distinguishing "copyrighted" from "legally restricted under HIPAA / PHIPA" → both share the same redistribution restriction; one flag suffices for v6.2. Multi-axis legal-clearance is post-Sep-6.

## Risks for Codex Red-Team

1. **`provenance.get("legal_cleared", False)` default to False.** The cautious default: a source without explicit clearance metadata is BLOCKED from bundle. Callers must explicitly mark legal_cleared=True. This may break existing fixtures elsewhere — brief author commits to verifying that NO existing fixtures rely on un-marked sources reaching the audit bundle path. If such fixtures exist, they update to add `provenance={"legal_cleared": True}`.

2. **bundle_builder integration tests.** `tests/polaris_graph/audit_bundle/test_bundle_builder.py` calls `build_manifest_and_files` indirectly. Brief author commits to running the FULL audit_bundle test suite after implementation; any test breakage gets explicit `legal_cleared=True` markers in fixtures.

3. **API error mapping** in BOTH routes. Same dispatch pattern as I-f15-004's cited-span unreachable.

4. **Sovereignty surface.** Pure additive guard; no new external-egress.

5. **§9.4 compliance.** No mocks. No magic numbers (LEGAL_CLEARED_KEY is a named constant). No `try: pass`. No TODO/FIXME.

6. **CHARTER §1 LOC cap.** 112 net. Under 200.

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
