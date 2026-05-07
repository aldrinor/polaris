# Codex Brief Review — I-f15-001 (ITER 1 of 5)

**HARD ITERATION CAP: 5 per document. This is iter 1 of 5.**
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

**Issue:** I-f15-001 — audit bundle schema
**Phase:** 1 / **Feature:** F15
**LOC budget:** 200 per breakdown. **CHARTER §1 hard cap: 200.**

## Mission + verification

Per breakdown: `src/polaris_graph/audit_bundle/schema.py`; manifest + 6 component files + reviewer README; Pydantic models; jsonschema validates.

**Verification at HEAD (post-I-f3-010 merge):**
- Schema substrate ALREADY EXISTS at `src/polaris_graph/audit_bundle/bundle_schema.py` (note: `bundle_schema.py` not `schema.py`; equivalent module). Defines `FileEntry`, `BundleManifest`, `BundleBuildError` Pydantic models.
- Existing 17 unit tests PASS via `PYTHONPATH=src python -m pytest tests/polaris_graph/audit_bundle/test_bundle_schema.py -v` → 17 passed in 3.28s.
- Bundle builder + manifest builder + GPG signer + snapshot_sources substrate are also in place from prior slice 004 work.

**Gap analysis vs breakdown:**
- "manifest + 6 component files + reviewer README" — `BundleManifest.files: list[FileEntry]` supports any number of components; reviewer README is currently NOT a hard-coded enum. The breakdown's "6 component files + reviewer README" is a binding shape constraint Codex may want to assert at the schema level (e.g. minimum 7 entries, one with kind=`reviewer_readme`).
- "jsonschema validates" — Pydantic v2 models export jsonschema via `model_json_schema()`. Existing tests verify this implicitly.

## Acceptance criteria (binding)

This Issue ships verification artifacts only, since the schema is in place at HEAD:

1. **`outputs/audits/I-f15-001/verification.md`** (NEW): documents:
   - Schema location: `src/polaris_graph/audit_bundle/bundle_schema.py`.
   - Existing 17/17 tests PASS (output captured).
   - jsonschema export verified via runtime `BundleManifest.model_json_schema()` returning dict.
   - Gap acknowledgment: 6-component+README enum-level constraint is NOT enforced at schema level (any FileEntry shape passes); follow-up I-f15-001a if Codex requires hard enum.

2. **`outputs/audits/I-f15-001/claude_audit.md`** (NEW): standard audit confirming verification.

## Planned diff shape

```
outputs/audits/I-f15-001/verification.md           NEW (audit-excluded)
outputs/audits/I-f15-001/claude_audit.md           NEW (audit-excluded)
.codex/I-f15-001/{brief, verdict, diff, audit}     NEW (codex-excluded)
```

LOC: 0 net source-code changes.

## Out of scope

- 6-component+README enum-level constraint → I-f15-001a follow-up if Codex insists.
- Actual bundle generation against a real run → I-f15-002+ down the chain.
- Real-key smoke (signing, etc.) → I-f15-005 adversarial.

## Risks for Codex Red-Team

1. **Empty canonical diff.** Deliverable in audit-excluded paths.
2. **Verification reproducibility:** `PYTHONPATH=src python -m pytest tests/polaris_graph/audit_bundle/test_bundle_schema.py -v` → 17 passed.
3. **6-component constraint deferred.** Per scope-split rationale.
4. **CHARTER §1 LOC cap.** 0 source-code LOC.

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
